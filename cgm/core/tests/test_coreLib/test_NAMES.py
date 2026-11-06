"""
------------------------------------------
cgm.core.tests.test_coreLib.test_NAMES
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya-free string-split tests for get_base.
================================================================
"""
import unittest
import logging

from cgm.core.lib import name_utils as NAMES

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_get_base(unittest.TestCase):
    def test_strips_path_and_namespace(self):
        self.assertEqual(NAMES.get_base('|grp|ns:joint1'), 'joint1')

    def test_plain_name(self):
        self.assertEqual(NAMES.get_base('joint1'), 'joint1')
