"""
------------------------------------------
cgm.core.tests.test_coreLib.test_SKIN
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Core callers use SKIN.get_cluster / get_influences_fromCluster,
not lib querySkinCluster / queryInfluences.
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import skin_utils as SKIN

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_get_cluster(unittest.TestCase):
    def test_unskinned_empty(self):
        cube = mc.polyCube()[0]
        self.assertEqual(SKIN.get_cluster(cube), '')

    def test_skinned_finds_cluster(self):
        cube = mc.polyCube()[0]
        jnt = mc.joint()
        mc.skinCluster(jnt, cube, tsb=True)
        found = SKIN.get_cluster(cube)
        self.assertTrue(found)
        self.assertEqual(mc.nodeType(found), 'skinCluster')
        self.assertTrue(SKIN.get_influences_fromCluster(found))
