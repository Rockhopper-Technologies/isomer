# Copyright 2021-2022 Avram Lubkin, All Rights Reserved

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Test related to the ISO class
"""

from contextlib import redirect_stdout
import functools
from io import StringIO
import logging
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import isomer
from tests.common import FLAVOR2_PATH, FLAVOR_PATH, KICKSTART, TESTDATA, TEST_SRC, compare_dirs


class TestInit(unittest.TestCase):
    """
    Tests for isomer.ISO initialization
    """

    def setUp(self):
        self.iso_partial = functools.partial(
            isomer.ISO, source=TESTDATA, outfile='test.iso', volume_id='test_1_2_3'
        )

    def test_defaults(self):
        """Test with only required values"""

        iso = self.iso_partial(config={})

        # source is path
        self.assertEqual(iso.source, TESTDATA)

        # working is created with prefix
        self.assertIsInstance(iso.working, Path)
        self.assertTrue(iso.working.is_dir())
        self.assertTrue(iso.working.name.startswith('isomer_'))

        # exclude is empty
        self.assertEqual(iso.exclude, [])

        # Grub configuration is None
        self.assertIsNone(iso.grub_template)

        # include is empty
        self.assertEqual(iso.include, {})

        # output file is path
        self.assertEqual(iso.outfile, Path('test.iso'))

        # volume_id is set
        self.assertEqual(iso.volume_id, 'test_1_2_3')

        # checksum is True
        self.assertTrue(iso.checksum)

        # bios_boot is False
        self.assertFalse(iso.bios_boot)

        # efi_boot is True
        self.assertTrue(iso.efi_boot)

        # fields only contains volume_id
        self.assertEqual(iso.fields, {'volume_id': 'test_1_2_3'})

    def test_source(self):
        """source errors"""

        # Happy path in defaults

        # Does not exist
        with self.assertRaisesRegex(ValueError, 'directory does not exist'):
            isomer.ISO(
                source='/path/does/not/exist', outfile='test.iso',
                config={'volume_id': 'test_1_2_3'}
            )

    def test_working(self):
        """working directory provided"""

        # Prepopulate to make sure it gets cleared
        _working = TemporaryDirectory(prefix='isomer_test_')  # pylint: disable=consider-using-with
        working = Path(_working.name)
        (working / 'file1').touch()  # File
        (working / 'dir1').mkdir()  # Directory
        (working / 'dir1' / 'file2').touch()  # Nested File

        _target = TemporaryDirectory(prefix='isomer_test_')  # pylint: disable=consider-using-with
        target_dir = Path(_target.name)
        (working / 'ln_dir').symlink_to(target_dir)  # Symlink to Directory

        target_file = target_dir / 'target_file'
        target_file.touch()
        (working / 'ln_file').symlink_to(target_file)

        # Happy path
        iso = self.iso_partial(working=working, config={})

        self.assertEqual(iso.working, working)

        # Make sure directory was cleared correctly
        isomer.clean_dir(working)
        self.assertEqual(os.listdir(working), [])
        self.assertTrue(target_dir.is_dir())
        self.assertTrue(target_file.is_file())

        # Clean temporary directories
        _working.cleanup()
        _target.cleanup()

        # Directory does not exist
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            self.iso_partial(working='some/dir/path', config={})

    def test_exclude(self):
        """exclude provided"""

        # Single item coerced to list
        iso = self.iso_partial(config={'exclude': 'foo'})
        self.assertEqual(iso.exclude, ['foo'])

        # Tuple coerced to list
        iso = self.iso_partial(config={'exclude': ('foo',)})
        self.assertEqual(iso.exclude, ['foo'])

    def test_grub_template(self):
        """grub_template provided"""

        iso = self.iso_partial(config={'grub_template': 'foo'})

        # grub_template is populated
        self.assertEqual(iso.grub_template, 'foo')

        # GRUB path is excluded
        self.assertEqual(iso.exclude, [isomer.GRUB_REL_PATH])

    def test_include(self):
        """include provided"""

        # Happy path
        iso = self.iso_partial(config={'include': {'foo': 'bar'}})
        self.assertEqual(iso.include, {'foo': 'bar'})

        # Not a dictionary
        with self.assertRaisesRegex(TypeError, 'must be a dict'):
            iso = self.iso_partial(config={'include': 'foo'})

    def test_outfile(self):
        """output file provided"""

        # Happy path
        iso = self.iso_partial(outfile=TESTDATA, config={})
        self.assertEqual(iso.outfile, TESTDATA)

        # Parent doesn't exist
        with self.assertRaisesRegex(ValueError, 'directory does not exist'):
            iso = self.iso_partial(outfile='/not/a/real/path/test.iso', config={})

    def test_volume_id(self):
        """volume_id errors"""

        # Happy path in defaults

        # Not provide
        with self.assertRaisesRegex(TypeError, "Missing required field: 'volume_id'"):
            isomer.ISO(source=TESTDATA, outfile='test.iso', config={})

        # Not a string
        with self.assertRaisesRegex(TypeError, 'volume_id must be a str'):
            isomer.ISO(source=TESTDATA, outfile='test.iso', config={'volume_id': [1, 2, 3]})

        # Contains whitespace
        with self.assertRaisesRegex(ValueError, 'contains whitespace'):
            isomer.ISO(source=TESTDATA, outfile='test.iso', config={'volume_id': 'test 1 2 3'})

    def test_kickstart(self):
        """kickstart provided"""

        # Happy path
        iso = self.iso_partial(config={'kickstart': KICKSTART})
        self.assertEqual(iso.include, {isomer.KS_REL_PATH: KICKSTART})
        self.assertEqual(
            iso.fields, {'volume_id': 'test_1_2_3', 'ks_path':  f'/{isomer.KS_REL_PATH}'}
        )

        # Doesn't exist
        with self.assertRaisesRegex(ValueError, 'Unable to find'):
            iso = self.iso_partial(config={'kickstart': '/not/a/real/path/test.iso'})

    def test_booleans(self):
        """Booleans provided"""

        iso = self.iso_partial(config={'checksum': True, 'bios_boot': True, 'efi_boot': True})
        self.assertTrue(iso.checksum)
        self.assertTrue(iso.bios_boot)
        self.assertTrue(iso.efi_boot)

        iso = self.iso_partial(config={'checksum': False, 'bios_boot': False, 'efi_boot': False})
        self.assertFalse(iso.checksum)
        self.assertFalse(iso.bios_boot)
        self.assertFalse(iso.efi_boot)

    def test_extra_keywords(self):
        """Extra keywords saved in fields"""

        iso = self.iso_partial(config={'foo': 1, 'bar': 'two', 'doo': (1, 2, 3)})
        self.assertEqual(
            iso.fields, {'volume_id': 'test_1_2_3', 'foo': 1, 'bar': 'two', 'doo': (1, 2, 3)}
        )


class TestPopulateWorking(unittest.TestCase):
    """
    Tests for isomer.ISO.populate_working()
    """

    def setUp(self):
        self.log_level = isomer.LOGGER.level
        isomer.LOGGER.setLevel(logging.CRITICAL)

        self._wdr = TemporaryDirectory(prefix='isomer_test_')  # pylint: disable=consider-using-with
        self.working = Path(self._wdr.name)
        self.iso_partial = functools.partial(
            isomer.ISO, quiet=True, source=TEST_SRC, volume_id='test_1_2_3',
            outfile='test.iso', working=self.working
        )

    def tearDown(self):
        isomer.LOGGER.setLevel(self.log_level)
        self._wdr.cleanup()

    def test_defaults(self):
        """Test with minimal configuration"""

        iso = self.iso_partial(config={})
        with patch('subprocess.run') as xorrisofs:
            with patch('subprocess.Popen') as implantisomd5:
                with implantisomd5() as process:
                    process.poll.side_effect = (None, 0)
                    process.returncode = 0
                    iso.generate()

        # Check directories match
        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, [])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, [])

        self.assertEqual(
            xorrisofs.call_args.args[0],
            ['xorrisofs', '-v', '-follow-links', '-J', '-joliet-long', '-r', '-U', '-V',
             'test_1_2_3', '-e', 'images/efiboot.img', '-no-emul-boot', '-o',
             'test.iso', str(self.working)])

        self.assertEqual(implantisomd5.call_args.args[0], ('implantisomd5', 'test.iso'))

    def test_no_quiet(self):
        """Test with quiet disabled"""

        iso = isomer.ISO(
            source=TEST_SRC, outfile='test.iso', working=self.working, config={'volume_id': '4_5_6'}
        )

        with patch('subprocess.run'):
            with redirect_stdout(StringIO()) as output:
                with patch('subprocess.Popen') as implantisomd5:
                    with implantisomd5() as process:
                        process.poll.side_effect = (None, 0)
                        process.returncode = 0
                        iso.generate()

        # Check directories match
        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, [])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, [])

        self.assertRegex(output.getvalue(), 'Calculating md5sum')

    def test_checksum_fails(self):
        """Checksum command fails"""

        iso = self.iso_partial(config={})
        with patch('subprocess.run'):
            with patch('subprocess.Popen') as implantisomd5:
                with implantisomd5() as process:
                    process.returncode = 5
                    with self.assertLogs(isomer.LOGGER, logging.ERROR) as logs:
                        iso.generate()

        self.assertRegex(logs.output[0], 'Failed to implant checksum')

    def test_exclude(self):
        """Test excluded files"""

        iso = self.iso_partial(config={'exclude': ('foo', 'misc')})
        with patch('subprocess.run'), patch('subprocess.Popen'):
            iso.generate()

        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, [])
        self.assertCountEqual(src_only, ['foo', 'misc', 'misc/bar'])
        self.assertCountEqual(working_only, [])

    def test_include(self):
        """Test excluded files"""

        iso = self.iso_partial(config={
            'include': {'foo': FLAVOR_PATH, 'misc/test': FLAVOR2_PATH, 'Base': TEST_SRC / 'Apps'}
        })

        with patch('subprocess.run'), patch('subprocess.Popen'):
            iso.generate()

        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, ['Base', 'foo'])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, ['misc/test'])

    def test_kickstart(self):
        """Test kickstart included"""

        iso = self.iso_partial(config={'kickstart': KICKSTART})

        with patch('subprocess.run'), patch('subprocess.Popen'):
            iso.generate()

        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, [])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, ['ks.cfg'])

        self.assertEqual(Path(os.readlink(self.working / 'ks.cfg')), KICKSTART)

    def test_swap_boot(self):
        """Swap EFI boot for BIOS"""

        iso = self.iso_partial(config={'bios_boot': True, 'efi_boot': False})

        with patch('subprocess.run') as xorrisofs:
            with patch('subprocess.Popen'):
                iso.generate()

        self.assertEqual(
            xorrisofs.call_args.args[0],
            ['xorrisofs', '-v', '-follow-links', '-J', '-joliet-long', '-r', '-U', '-V',
             'test_1_2_3',
             '-b', 'isolinux/isolinux.bin', '-c', 'isolinux/boot.cat', '-no-emul-boot',
             '-boot-load-size', '4', '-boot-info-table', '-eltorito-alt-boot',
             '-o', 'test.iso', str(self.working)])

    def test_grub(self):
        """Test grub generation"""

        iso = self.iso_partial(config={'grub_template': '{volume_id}, {extra}', 'extra': 'foobar'})

        with patch('subprocess.run'), patch('subprocess.Popen'):
            iso.generate()

        differ, src_only, working_only = compare_dirs(TEST_SRC, self.working)
        self.assertCountEqual(differ, [isomer.GRUB_REL_PATH])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, [])

        self.assertEqual(
            (self.working / isomer.GRUB_REL_PATH).read_text(),
            'test_1_2_3, foobar'
        )

    def test_grub_no_dir(self):
        """Test grub generation (no directory)"""

        iso = isomer.ISO(
            quiet=True, source=TEST_SRC / 'misc', outfile='test.iso', working=self.working,
            config={'volume_id': '45_6', 'grub_template': '{volume_id}, {extra}', 'extra': 'foobar'}
        )

        with patch('subprocess.run'), patch('subprocess.Popen'):
            iso.generate()

        differ, src_only, working_only = compare_dirs(TEST_SRC / 'misc', self.working)
        self.assertCountEqual(differ, [])
        self.assertCountEqual(src_only, [])
        self.assertCountEqual(working_only, ['EFI'])

        self.assertEqual(
            (self.working / isomer.GRUB_REL_PATH).read_text(),
            '45_6, foobar'
        )

    def test_xorrisofs_fails(self):
        """xorrisofs command fails"""

        iso = self.iso_partial(config={})
        with patch('subprocess.run') as xorrisofs:
            with patch('subprocess.Popen') as implantisomd5:
                xorrisofs.side_effect = subprocess.CalledProcessError(2, 'xorrisofs')
                iso.generate()

        xorrisofs.assert_called_once()
        implantisomd5.assert_not_called()
