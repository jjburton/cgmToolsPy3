"""
------------------------------------------
cgm.core.tests.test_coreLib.test_SNAP
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

move_point_snap / move_orient_snap are not SNAP.go
(go converts rotateOrder when they differ).
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import snap_utils as SNAP

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_move_snaps(unittest.TestCase):
    def setUp(self):
        self.src = mc.spaceLocator(name='cgmSnapSrc')[0]
        self.dst = mc.spaceLocator(name='cgmSnapDst')[0]
        mc.xform(self.src, ws=True, t=(10, 2, -3))
        mc.xform(self.src, ws=True, ro=(0, 45, 0))
        mc.xform(self.src, roo='xyz')
        mc.xform(self.dst, roo='zyx')

    def tearDown(self):
        for o in (self.src, self.dst):
            if mc.objExists(o):
                mc.delete(o)

    def test_point_matches_world_rp(self):
        SNAP.move_point_snap(self.dst, self.src)
        src_rp = mc.xform(self.src, q=True, ws=True, rp=True)
        dst_rp = mc.xform(self.dst, q=True, ws=True, rp=True)
        for a, b in zip(src_rp, dst_rp):
            self.assertAlmostEqual(a, b, places=4)
        self.assertEqual(mc.xform(self.dst, q=True, roo=True), 'zyx')

    def test_orient_keeps_rotateOrder(self):
        """SNAP.go with rotateOrder=True would copy roo. move_orient_snap must not."""
        SNAP.move_orient_snap(self.dst, self.src)
        self.assertEqual(mc.xform(self.dst, q=True, roo=True), 'zyx')

    def test_orient_same_roo_matches(self):
        mc.xform(self.dst, roo='xyz')
        SNAP.move_orient_snap(self.dst, self.src)
        src_ro = mc.xform(self.src, q=True, ws=True, ro=True)
        dst_ro = mc.xform(self.dst, q=True, ws=True, ro=True)
        for a, b in zip(src_ro, dst_ro):
            self.assertAlmostEqual(a, b, places=4)
