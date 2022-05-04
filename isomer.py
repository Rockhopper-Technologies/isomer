# Copyright 2021-2022 Avram Lubkin, All Rights Reserved

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Utility for creating ISO images based on an existing image or template

Required commands:
    implantisomd5
    xorrisofs

"""

import argparse
import ast
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

__version__ = '0.8.0'

LOGGER = logging.getLogger('isomer')
LOGGER.addHandler(logging.NullHandler())
IMPLANTISOMD5 = 'implantisomd5'
XORRISOFS = 'xorrisofs'
KS_REL_PATH = 'ks.cfg'
GRUB_REL_PATH = 'EFI/BOOT/grub.cfg'
EPILOG = '''\
Flavor is evaluated in the following order:
    1. As a file path
    2. As a .cfg file in the current directory
    3. As a .cfg file in the configuration directory
'''
DESCRIPTION = 'Template-base ISO generator'
DEF_CFG_DIR = '/etc/isomer'
ENVIRON_CFG_DIR = 'ISOMER_CFG_DIR'


def clean_dir(dirpath):
    """
    Clean directory without otherwise changing it
    """

    # Delete all files and directories
    for entry in os.scandir(dirpath):
        if entry.is_file() or entry.is_symlink():
            os.unlink(entry)
        elif entry.is_dir():  # pragma: no branch
            shutil.rmtree(entry)


def _get_details(node, configfile):
    """
    Generate a SyntaxError-compatible details tuple
    """

    if sys.version_info[:2] >= (3, 10):  # pragma: no branch
        return (configfile, node.lineno, node.col_offset,
                ast.get_source_segment(configfile.read_text('utf-8'), node),
                node.end_lineno, node.end_col_offset)

    return (configfile, node.lineno, node.col_offset,  # pragma: no cover
            ast.get_source_segment(configfile.read_text('utf-8'), node))


def parse_cfg(configfile):
    """
    Parse configuration file
    """

    configfile = Path(configfile)
    if not configfile.is_file():
        raise ValueError(f'Unable to locate config file at {configfile}')

    # This will raise a Syntax Error if file has bad syntax
    parsed = ast.parse(configfile.read_text('utf-8'), filename=configfile, mode='exec')

    rtn = {}
    for node in parsed.body:

        # Look for assignment nodes
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # Attempt to evaluate to literal type
                try:
                    rtn[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as e:
                    raise SyntaxError(
                        f'Unsupported syntax (Non-literal): {e}', _get_details(node, configfile)
                    ) from None

            continue

        # Check for 'include' call
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and
                node.value.func.id == 'include'):
            for arg in node.value.args:

                if not isinstance(arg, ast.Constant):
                    raise SyntaxError('Unsupported syntax (Missing quotes?)',
                                      _get_details(node, configfile))

                include_file = Path(arg.value)
                if not include_file.is_absolute():
                    include_file = configfile.parent / include_file
                rtn.update(parse_cfg(include_file))

            continue

        raise SyntaxError('Unsupported syntax', _get_details(node, configfile))

    return rtn


class ISO:  # pylint: disable=too-many-instance-attributes,too-many-arguments
    """
    Class for creating ISOs
    """

    def __init__(self, source, outfile, config, working=None, quiet=False, volume_id=None):

        # Source to base new ISO on
        self.source = Path(source)
        if not self.source.is_dir():
            raise ValueError(f"Source directory does not exist: '{source}'")

        # Output ISO filename
        self.outfile = Path(outfile)
        if not self.outfile.parent.is_dir():
            raise ValueError(f'Destination directory does not exist: {self.outfile.parent}')

        # Temporary working directory
        if working is None:
            # pylint: disable=consider-using-with
            self._working = TemporaryDirectory(prefix='isomer_')
            self.working = Path(self._working .name)
        else:
            self.working = Path(working)
            if not self.working.is_dir():
                raise ValueError(f"Working directory does not exist: '{working}'")

        # Logging level
        self.quiet = quiet

        # Store initial volume_id
        self.volume_id = volume_id

        # Parse flavor configuration
        self.parse_config(config)

    def __del__(self):

        # Make sure temp directories get cleaned
        if hasattr(self, '_working'):
            self._working.cleanup()

    def parse_config(self, config):
        """
        Parse flavor configuration into class attributes
        """

        self.fields = {}

        # Volume ID label. For Joliet complains if over 16 characters, but it still works
        if 'volume_id' not in config and self.volume_id is None:
            raise TypeError("Missing required field: 'volume_id'")

        self.volume_id = self.fields['volume_id'] = config.pop('volume_id', self.volume_id)

        if not isinstance(self.volume_id, str):
            raise TypeError(
                'volume_id must be a str '
                f'not a {self.volume_id.__class__.__name__}: {self.volume_id}'
            )

        # Anaconda doesn't like whitespace in labels even if they are quoted
        if re.search(r'\s', self.volume_id):
            raise ValueError(f"Volume ID contains whitespace: '{self.volume_id}'")

        # Exclude accepts wildcards and partial paths. See pathlib.Path.match()
        exclude = config.pop('exclude', None)
        if isinstance(exclude, str):
            self.exclude = [exclude]
        elif exclude:
            self.exclude = list(exclude)
        else:
            self.exclude = []

        # Include paths are relative to source
        # {iso_path: target}
        # Will create a link symlink to the specified target
        # Will override existing files
        self.include = config.pop('include', {})
        if not isinstance(self.include, dict):
            raise TypeError(
                f'include must be a dict not a {self.include.__class__.__name__}: {self.include}'
            )

        if kickstart := config.pop('kickstart', None):
            if not Path(kickstart).is_file():
                raise ValueError(f'Unable to find kickstart file: {kickstart}')
            self.include[KS_REL_PATH] = kickstart
            self.fields['ks_path'] = KS_REL_PATH

        # Grub configuration
        self.grub_template = config.pop('grub_template', None)
        if self.grub_template:
            self.exclude.append(GRUB_REL_PATH)

        # Generate and inject checksum
        self.checksum = config.pop('checksum', True)

        # Boot options
        self.bios_boot = config.pop('bios_boot', False)
        self.efi_boot = config.pop('efi_boot', True)

        # Save any remaining in fields
        self.fields.update(config.pop('extra_fields', {}))

        # Warn about any unsupported fields
        if config:
            LOGGER.warning(
                'Ignoring unsupported fields in flavor configuration: %s', ', '.join(config)
            )

    def populate_working(self):
        """
        Create directory structure and link files in working directory
        """

        # Make sure directory is empty
        clean_dir(self.working)

        # Walk source recursively
        for root, dirs, files in os.walk(self.source):
            root_path = Path(root)

            # Iterate directories
            for dirname in dirs[:]:
                dirpath = root_path / dirname
                relative_path = dirpath.relative_to(self.source)

                # Check if directory is excluded
                if any(map(relative_path.match, self.exclude)):
                    dirs.remove(dirname)
                    LOGGER.info('Excluded directory: %s', dirpath)
                    continue

                if target := self.include.pop(str(relative_path), None):
                    dirs.remove(dirname)
                    (self.working / relative_path).symlink_to(target)
                    LOGGER.info('%s -> %s', relative_path, target)
                    continue

                # Create directory
                (self.working / relative_path).mkdir(mode=0o755)
                LOGGER.info('Created directory: %s', relative_path)

            # Iterate files
            for filepath in (root_path / filename for filename in files):
                relative_path = filepath.relative_to(self.source)

                # Check if file is excluded
                if any(map(relative_path.match, self.exclude)):
                    LOGGER.info('Excluded file: %s', filepath)
                    continue

                # Check if file is overridden
                target = self.include.pop(str(relative_path), filepath)

                # Create symlink
                (self.working / relative_path).symlink_to(target)
                LOGGER.info('%s -> %s', relative_path, target)

        # Handle any additional included files
        for source, target in self.include.items():
            working_path = self.working / source
            relative_path = working_path.relative_to(self.working)

            # Create directory, if needed
            working_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)

            # Create symlink
            LOGGER.info('%s -> %s', relative_path, target)
            working_path.symlink_to(target)

        if self.grub_template:
            self.generate_grub()

    def gen_iso(self):
        """
        Generate ISO image
        """

        args = [
            XORRISOFS,  # Command
            '-v',  # Verbose
            '-follow-links',  # Resolve symlinks

            # RH Recommended file options
            '-J',  # Generate Joliet records for Windows
            '-joliet-long',  # Support Joliet names up to 103 characters
            '-r',  # Set file ownership and modes to sane values
            '-U',  # Support more filenames

            # RH Recommended Metadata
            # '-A', self.volume_id,  # Application ID (not set in RHEL 9 ISO)
            '-V', self.volume_id,  # Volume ID
            # '-volset', self.volume_id,  # Volume Set ID (not set in RHEL 9 ISO)

        ]

        # BIOS Boot - Disable by default
        if self.bios_boot:
            args.extend([
                '-b', 'isolinux/isolinux.bin',  # BIOS boot image
                '-c', 'isolinux/boot.cat',  # El Torito boot catalog
                '-no-emul-boot',  # Boot image for El Torito does not require emulation
                '-boot-load-size', '4',  # Number of sectors to load of boot image
                '-boot-info-table',  # El Torito boot table
                '-eltorito-alt-boot',  # Finalize El Torito boot entry and start new one
            ])

        # EFI Boot
        if self.efi_boot:
            args.extend([
                '-e', 'images/efiboot.img',  # EFI boot image
                '-no-emul-boot',  # Boot image for El Torito does not require emulation
            ])

        args.extend([
            '-o', str(self.outfile),  # Output file
            str(self.working),  # source directory
        ])

        LOGGER.info('Running command: %s', {" ".join(args)})
        kwargs = {'stdout': subprocess.DEVNULL} if self.quiet else {}

        try:
            subprocess.run(args, check=True, **kwargs)
        except subprocess.CalledProcessError as e:
            LOGGER.error('Failed to generate ISO: %s', e)
            return False

        return True

    def implant_checksum(self):
        """
        Implant checksum in ISO.
        Used MD5 because it's an old spec
        """

        args = (IMPLANTISOMD5, str(self.outfile))
        LOGGER.info('Running command: %s', {" ".join(args)})
        if not self.quiet:
            print('Calculating md5sum: ', end='', flush=True)
        kwargs = {'stdout': subprocess.DEVNULL} if self.quiet else {}
        with subprocess.Popen(args, **kwargs) as process:

            # The process doesn't give status when calculating, so wrap so we know it's working
            while process.poll() is None:
                if not self.quiet:
                    print('.', end='', flush=True)
                time.sleep(0.5)

            if process.returncode:
                LOGGER.error('Failed to implant checksum (returncode: %d)', process.returncode)

            return not process.returncode

    def generate(self):
        """
        Generate ISO
        """

        # Stage
        LOGGER.info('Using work directory: %s', self.working)
        self.populate_working()

        # Create
        if self.gen_iso() and self.checksum:
            self.implant_checksum()

    def generate_grub(self):
        """
        Generate GRUB configuration file
        """

        LOGGER.info('Generating boot menu: %s', GRUB_REL_PATH)
        grub_path = self.working / GRUB_REL_PATH
        if not grub_path.parent.exists():
            grub_path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)

        with grub_path.open('w') as grub:
            try:
                grub.write(self.grub_template.format_map(self.fields))
            except KeyError as e:
                LOGGER.error("Unknown field %s in grub_template: %s", e, self.grub_template)


def get_config_file(flavor: Path):
    """
    Determine configuration file to use based on flavor
    """

    # If flavor is a path to a file, use it
    if flavor.is_file():
        return flavor

    cfg = flavor.with_suffix('.cfg')

    # If flavor is a file in the current working directory, use it
    cfg_in_cwd = Path.cwd() / cfg
    if cfg_in_cwd.is_file():
        return cfg_in_cwd

    # If favor is a file in configuration directory, use it
    cfg_in_cfg_dir = Path(os.environ.get(ENVIRON_CFG_DIR, DEF_CFG_DIR)) / cfg
    if cfg_in_cfg_dir.is_file():
        return cfg_in_cfg_dir

    return None


def cli(args=None):
    """
    Run as a command
    """

    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-f', '--flavor', metavar='FLAVOR or FILE', type=Path, required=True,
                        help='Flavor or path to flavor file')
    parser.add_argument('-s', '--source',  metavar='DIR', required=True,
                        help='Source directory')
    parser.add_argument('-o', '--outfile',  metavar='FILE', required=True,
                        help='Output file')
    parser.add_argument('-w', '--working',  metavar='DIR',
                        help='Working directory, contents overwritten')
    parser.add_argument('-q', '--quiet', action='store_true', default=False,
                        help='Suppress output')

    options = parser.parse_args(args)

    # Configure logging
    log_level = logging.WARNING if options.quiet else logging.INFO
    logging.basicConfig(level=log_level)

    # Try to locate flavor configuration
    configfile = get_config_file(options.flavor)
    if configfile is None:
        sys.exit(f'Unable to locate flavor or file: {options.flavor}')

    LOGGER.info('Using configuration file: %s', configfile)

    # Parse flavor configuration
    config = parse_cfg(configfile)

    # Create class instance and generate ISO
    kwargs = vars(options)
    del kwargs['flavor']
    ISO(config=config, **kwargs).generate()


if __name__ == '__main__':
    cli()
