"""
------------------------------------------
cgm.core.tests.test_coreLib.test_RIGGING
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Core callers use TRANS.group_me / copy_pivot, not lib groupMeObject / copyPivot.
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import transform_utils as TRANS

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_group_me_maya(unittest.TestCase):
    def test_parent_false_does_not_parent(self):
        loc = mc.spaceLocator()[0]
        grp = TRANS.group_me(loc, parent=False, maintainParent=False)
        self.assertTrue(mc.objExists(grp))
        self.assertFalse(mc.listRelatives(loc, parent=True))
