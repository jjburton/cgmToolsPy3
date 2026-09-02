"""
------------------------------------------
cgm.core.tests.test_coreLib.test_SHARED
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya-free unit tests for cgm.core.lib.shared_data axis/color maps.
Canonical data is _d_* / _l_axis_by_string. Old lib names stay on
leftover cgm.lib.dictionary.
================================================================
"""
import unittest
import logging

from cgm.core.lib import shared_data as SHARED

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_axis_maps(unittest.TestCase):
    def test_string_to_vector_x_plus(self):
        self.assertEqual(SHARED._d_axis_string_to_vector['x+'], (1, 0, 0))

    def test_string_to_vector_missing(self):
        self.assertNotIn('nope', SHARED._d_axis_string_to_vector)

    def test_vector_to_string_compact(self):
        self.assertEqual(SHARED._d_axis_vector_to_string['[0,1,0]'], 'y+')

    def test_axis_order(self):
        self.assertEqual(SHARED._l_axis_by_string[0], 'x+')


class Test_state_color(unittest.TestCase):
    def test_help(self):
        self.assertEqual(SHARED._d_gui_state_colors['help'], (0.8, 0.8, 0.8))

    def test_ready_is_core_green(self):
        self.assertEqual(SHARED._d_gui_state_colors['ready'][1], 0.5)


class Test_side_color_index(unittest.TestCase):
    """getSettingsColors pairs match cgmSettings.conf colorLeft/Right/Center."""
    def test_left_is_main_sub(self):
        d = SHARED._d_side_colors_index['left']
        self.assertEqual([d['main'], d['sub']], ['blueBright', 'blueSky'])

    def test_center_conf_is_sub_aux(self):
        d = SHARED._d_side_colors_index['center']
        self.assertEqual([d['sub'], d['aux']], ['yellowBright', 'peach'])


class Test_getSettingsColors(unittest.TestCase):
    def test_left(self):
        from cgm.core.lib import meta_Utils as metaUtils
        self.assertEqual(metaUtils.getSettingsColors('left'), ['blueBright', 'blueSky'])

    def test_center(self):
        from cgm.core.lib import meta_Utils as metaUtils
        self.assertEqual(metaUtils.getSettingsColors('center'), ['yellowBright', 'peach'])
