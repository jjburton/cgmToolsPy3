"""
------------------------------------------
cgm.core.tests.test_coreLib.test_NODES
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Core callers use NODES.create / setup_offset_cycle_speed,
not lib createNamedNode / offsetCycleSpeedControlNodeSetup.
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import node_utils as NODES

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_create(unittest.TestCase):
    def test_condition_utility(self):
        node = NODES.create('picker', 'condition')
        self.assertTrue(mc.objExists(node))
        self.assertEqual(mc.nodeType(node), 'condition')
        self.assertIn('condNode', node)

    def test_multiplyDivide(self):
        node = NODES.create('speedMult', 'multiplyDivide')
        self.assertEqual(mc.nodeType(node), 'multiplyDivide')
        self.assertIn('mdNode', node)


class Test_setup_offset_cycle_speed(unittest.TestCase):
    def test_keys_and_speed_md(self):
        loc = mc.spaceLocator()[0]
        mc.addAttr(loc, ln='offset', at='double', k=True)
        mc.addAttr(loc, ln='speed', at='double', k=True, dv=1)
        md = NODES.setup_offset_cycle_speed(loc, loc + '.speed', 10, -20)
        self.assertEqual(mc.nodeType(md), 'multiplyDivide')
        self.assertTrue(mc.isConnected('time1.outTime', md + '.input1X'))
        self.assertTrue(mc.isConnected(loc + '.speed', md + '.input2X'))
        anim = loc + '_offset'
        self.assertTrue(mc.objExists(anim))
        self.assertTrue(mc.isConnected(md + '.outputX', anim + '.input'))
        self.assertEqual(mc.keyframe(loc + '.offset', q=True, kc=True), 2)
