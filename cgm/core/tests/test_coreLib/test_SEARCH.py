"""
------------------------------------------
cgm.core.tests.test_coreLib.test_SEARCH
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya contract tests for search_utils time / parent queries.
Does not hit Channel Box or timeline-selection (needs UI).
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import search_utils as SEARCH

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_get_time(unittest.TestCase):
    def test_current(self):
        mc.currentTime(12)
        self.assertEqual(SEARCH.get_time('current'), 12)

    def test_slider_and_scene(self):
        mc.playbackOptions(min=5, max=20, animationStartTime=1, animationEndTime=40)
        self.assertEqual(SEARCH.get_time('slider'), [5, 20])
        self.assertEqual(SEARCH.get_time('scene'), [1, 40])


class Test_parents_get(unittest.TestCase):
    def test_chain_top_last(self):
        a = mc.group(em=True, name='cgmSrchA')
        b = mc.group(em=True, name='cgmSrchB')
        c = mc.group(em=True, name='cgmSrchC')
        mc.parent(c, b)
        mc.parent(b, a)
        parents = SEARCH.parents_get(c, fullPath=True)
        self.assertEqual(len(parents), 2)
        self.assertTrue(parents[0].endswith('|cgmSrchB'))
        self.assertTrue(parents[-1].endswith('|cgmSrchA'))
