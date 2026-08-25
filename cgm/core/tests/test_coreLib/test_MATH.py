"""
------------------------------------------
cgm.core.tests.test_coreLib.test_MATH
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya-free unit tests for cgm.core.lib.math_utils list/float helpers.
Does not create scene nodes. Importing MATH still loads Maya cmds.
Old lib names stay on leftover cgm.lib.cgmMath, not on MATH.
================================================================
"""
import unittest
import logging

from cgm.core.lib import math_utils as MATH

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_float_equivalent(unittest.TestCase):
    def test_zeros(self):
        self.assertTrue(MATH.is_float_equivalent(-0.0, 0.0))


class Test_vectors(unittest.TestCase):
    def test_mag_3_4_5(self):
        self.assertAlmostEqual(MATH.mag([3, 4, 0]), 5.0)

    def test_list_add(self):
        self.assertEqual(MATH.list_add([1, 2, 3], [4, 5, 6]), [5, 7, 9])

    def test_list_subtract(self):
        self.assertEqual(MATH.list_subtract([4, 5, 6], [1, 2, 3]), [3, 3, 3])


class Test_norm(unittest.TestCase):
    def test_sum_to_one(self):
        res = MATH.normalizeListToSum([0.2, 0.5], 1.0)
        self.assertAlmostEqual(sum(res), 1.0)
        self.assertAlmostEqual(res[0], 0.2 / 0.7)
        self.assertAlmostEqual(res[1], 0.5 / 0.7)

    def test_normalizeTo_is_multiply_not_divide(self):
        """Core wins vs leftover lib normSumList (lib divided by normalizeTo)."""
        res = MATH.normalizeListToSum([1.0, 1.0], 2.0)
        self.assertAlmostEqual(sum(res), 2.0)
