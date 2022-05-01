# Copyright 2021-2022 Avram Lubkin, All Rights Reserved

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Tests related to CLI operations
"""

import logging
import unittest
from unittest.mock import patch

import isomer

from tests.common import FLAVOR_PATH, FLAVOR_CONFIG, TEST_SRC


class TestCLI(unittest.TestCase):
    """
    Tests for isomer.cli()
    """

    def setUp(self):
        self.log_level = isomer.LOGGER.level
        isomer.LOGGER.setLevel(logging.CRITICAL)

    def tearDown(self):
        isomer.LOGGER.setLevel(self.log_level)

    def test_required(self):
        """No flavor is provided"""

        with patch('argparse.ArgumentParser.error', side_effect=RuntimeError()) as error:

            # Missing output file
            with self.assertRaises(RuntimeError):
                isomer.cli(['-f', str(FLAVOR_PATH), '-s', str(TEST_SRC)])
            self.assertRegex(error.call_args.args[0], 'required: -o/--outfile')

            # Missing source
            with self.assertRaises(RuntimeError):
                isomer.cli(['-f', str(FLAVOR_PATH), '-o', 'test.iso'])
            self.assertRegex(error.call_args.args[0], 'required: -s/--source')

            # Missing flavor
            with self.assertRaises(RuntimeError):
                isomer.cli(['-s', str(TEST_SRC), '-o', 'test.iso'])
            self.assertRegex(error.call_args.args[0], 'required: -f/--flavor')

    def test_no_file(self):
        """Unable to locate file"""

        with self.assertRaisesRegex(SystemExit, 'Unable to locate flavor'):
            isomer.cli(['-f', '/not/a/real/file/path', '-s', str(TEST_SRC), '-o', 'test.iso'])

    def test_success_mock(self):
        """Mock successful CLI call"""

        with patch('isomer.ISO') as mock_iso:
            isomer.cli(['-f', str(FLAVOR_PATH), '-s', str(TEST_SRC), '-o', 'test.iso'])
            self.assertEqual(mock_iso.call_args.kwargs['config'], FLAVOR_CONFIG)
