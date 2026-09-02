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


class Test_transfer_fromTo(unittest.TestCase):
    def test_copies_cluster_to_unskinned(self):
        src = mc.polyCube(name='cgmSkinSrc')[0]
        dst = mc.polyCube(name='cgmSkinDst')[0]
        jnt = mc.joint(name='cgmSkinJnt')
        mc.skinCluster(jnt, src, tsb=True)
        SKIN.transfer_fromTo(src, [dst])
        found = SKIN.get_cluster(dst)
        self.assertTrue(found)
        self.assertEqual(mc.nodeType(found), 'skinCluster')
        self.assertIn(jnt, SKIN.get_influences_fromCluster(found))

    def test_missing_source_cluster_logs(self):
        src = mc.polyCube(name='cgmSkinBare')[0]
        dst = mc.polyCube(name='cgmSkinBareDst')[0]
        SKIN.transfer_fromTo(src, [dst])
        self.assertEqual(SKIN.get_cluster(dst), '')
