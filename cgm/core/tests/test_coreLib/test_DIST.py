"""
------------------------------------------
cgm.core.tests.test_coreLib.test_DIST
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya-free unit tests for point/list helpers on cgm.core.lib.distance_utils.
Does not create scene nodes. Importing DIST still loads Maya cmds.
Old lib names stay on leftover cgm.lib.distance, not on DIST.
================================================================
"""
import unittest
import logging

from cgm.core.lib import distance_utils as DIST

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_between_points(unittest.TestCase):
    def test_unit_axis(self):
        self.assertEqual(DIST.get_distance_between_points([0, 0, 0], [1, 0, 0]), 1.0)

    def test_3_4_5(self):
        self.assertAlmostEqual(DIST.get_distance_between_points([0, 0, 0], [3, 4, 0]), 5.0)


class Test_average_position(unittest.TestCase):
    def test_midpoint(self):
        self.assertEqual(DIST.get_average_position([[0, 0, 0], [2, 2, 2]]), [1.0, 1.0, 1.0])


class Test_posList(unittest.TestCase):
    def test_closest(self):
        self.assertEqual(DIST.get_closest_from_posList([0, 0, 0], [[5, 0, 0], [1, 0, 0], [9, 0, 0]]),
                         [1, 0, 0])

    def test_furthest(self):
        self.assertEqual(DIST.get_furthest_from_posList([0, 0, 0], [[5, 0, 0], [1, 0, 0], [9, 0, 0]]),
                         [9, 0, 0])

    def test_closest_posList_is_not_surface(self):
        self.assertIsNot(DIST.get_closest_from_posList, DIST.get_closest_point)

    def test_sorted_by_distance(self):
        self.assertEqual(
            DIST.get_positions_sorted_by_distance([0, 0, 0], [[9, 0, 0], [1, 0, 0], [5, 0, 0]]),
            [[1, 0, 0], [5, 0, 0], [9, 0, 0]])
