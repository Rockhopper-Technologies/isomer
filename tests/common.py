# Copyright 2021-2022 Avram Lubkin, All Rights Reserved

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Common test data and utilities
"""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

TESTDATA = Path(__file__).parent / 'testdata'
FLAVOR_PATH = TESTDATA / 'cfg' / 'flavor.cfg'
FLAVOR2_PATH = TESTDATA / 'cfg' / 'flavor2.cfg'
KICKSTART = TESTDATA / 'ks.cfg'
TEST_SRC = TESTDATA / 'src'

FLAVOR_CONFIG = {
    'source': '/mnt',
    'checksum': True,
    'include': {'Apps': '/srv/repos/Apps', 'Base': '/srv/repos/Base'},
    'grub_template': "\nTis but a scratch\nA scratch? Your arm's off!\n",
    'answer': 42,
}


@contextmanager
def set_directory(path):
    """
    Context manager for temporarily changing the current working directory
    """

    cwd = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


def write_temp_file(text):
    """
    Create a named temporary file with the given context
    """

    # pylint: disable=consider-using-with
    temp = tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8')
    temp.write(text)
    temp.seek(0)

    return temp


def compare_dirs(src: Path, dest: Path):
    """
    Compare source and destination directories
    """

    src_only = []
    differ = []

    for root, dirs, files in os.walk(src):
        root_path = Path(root)

        for dirname in dirs[:]:
            entry_src = root_path / dirname
            rel_path = entry_src.relative_to(src)
            entry_dest = dest / rel_path

            if not entry_dest.exists():
                src_only.append(str(rel_path))

            elif entry_dest.is_symlink() or not entry_dest.is_dir():
                differ.append(str(rel_path))
                dirs.remove(dirname)

        for filename in files:
            entry_src = root_path / filename
            rel_path = entry_src.relative_to(src)
            entry_dest = dest / rel_path

            if not entry_dest.exists():
                src_only.append(str(rel_path))

            elif not entry_dest.is_symlink() or Path(os.readlink(entry_dest)) != entry_src:
                differ.append(str(rel_path))

    dest_only = []
    for root, dirs, files in os.walk(dest):
        root_path = Path(root)

        for dirname in dirs[:]:
            entry_dest = root_path / dirname
            rel_path = entry_dest.relative_to(dest)
            entry_src = src / rel_path

            if not entry_src.exists():
                dest_only.append(str(rel_path))
                dirs.remove(dirname)

        for filename in files:
            entry_dest = root_path / filename
            rel_path = entry_dest.relative_to(dest)
            entry_src = src / rel_path

            if not entry_src.exists():
                dest_only.append(str(rel_path))

    return differ, src_only, dest_only
