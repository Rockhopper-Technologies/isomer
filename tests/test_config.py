# Copyright 2021-2022 Avram Lubkin, All Rights Reserved

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Test related to configuration file locating and parsing
"""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

import isomer
from tests.common import (
    FLAVOR_CONFIG, TESTDATA, FLAVOR_PATH, FLAVOR2_PATH, set_directory, write_temp_file
)


class TestGetConfigFile(unittest.TestCase):
    """
    Tests for isomer.get_config_file()
    """

    def test_flavor_is_file(self):
        """Flavor is a file path"""

        self.assertEqual(
            isomer.get_config_file(FLAVOR_PATH), FLAVOR_PATH
        )

    def test_flavor_in_cwd(self):
        """Flavor is current working directory"""

        with set_directory(TESTDATA / 'cfg'):
            self.assertEqual(
                isomer.get_config_file(Path('flavor')), FLAVOR_PATH
            )

    def test_flavor_in_cfg_dir(self):
        """Flavor is configuration directory"""

        with patch.dict(os.environ, {'ISOMER_CFG_DIR': str(TESTDATA / 'cfg')}):
            self.assertEqual(
                isomer.get_config_file(Path('flavor')), FLAVOR_PATH
            )

    def test_flavor_not_found(self):
        """Flavor can't be found"""

        self.assertIsNone(isomer.get_config_file(Path('flavor')))


class TestParseCfg(unittest.TestCase):
    """
    Tests for isomer.parse_cfg()
    """

    def test_no_file(self):
        """File can't be found"""

        with self.assertRaisesRegex(ValueError, 'Unable to locate'):
            isomer.parse_cfg('/not/a/real/file.cfg')

    def test_clean_parse(self):
        """Successful parse of supported syntax"""

        self.assertEqual(isomer.parse_cfg(FLAVOR_PATH), FLAVOR_CONFIG)

    def test_include_absolute(self):
        """Include function given absolute path to file"""

        configfile = write_temp_file(f"include('{FLAVOR2_PATH}')\n")
        self.assertEqual(isomer.parse_cfg(configfile.name), {'answer': 42})

    def test_bad_syntax(self):
        """File contains invalid Python syntax"""

        configfile = write_temp_file('foo)\n')
        with self.assertRaisesRegex(SyntaxError, 'unmatched'):
            isomer.parse_cfg(configfile.name)

    def test_unsupported_syntax(self):
        """File contains valid, but unsupported Python syntax"""

        configfile = write_temp_file('foo\n')
        with self.assertRaisesRegex(SyntaxError, 'Unsupported'):
            isomer.parse_cfg(configfile.name)

    def test_non_literal(self):
        """File contains assignment to a non-literal value"""

        configfile = write_temp_file('foo = bar()\n')
        with self.assertRaisesRegex(SyntaxError, 'Non-literal'):
            isomer.parse_cfg(configfile.name)

    def test_include_no_quotes(self):
        """include() passed a name instead of a string"""

        configfile = write_temp_file('include(filename)\n')
        with self.assertRaisesRegex(SyntaxError, 'Missing quotes'):
            isomer.parse_cfg(configfile.name)
