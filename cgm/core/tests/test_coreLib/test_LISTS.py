"""
------------------------------------------
cgm.core.tests.test_coreLib.test_LISTS
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya-free unit tests for cgm.core.lib.list_utils.
Does not create scene nodes. Safe to run after the runner's file-new.
================================================================
"""
import unittest
import logging

from cgm.core.lib import list_utils as LISTS

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_chunks(unittest.TestCase):
    def test_even(self):
        self.assertEqual(LISTS.get_chunks([1, 2, 3, 4, 5, 6], 2),
                         [[1, 2], [3, 4], [5, 6]])

    def test_remainder(self):
        self.assertEqual(LISTS.get_chunks([1, 2, 3, 4, 5], 2),
                         [[1, 2], [3, 4], [5]])


class Test_noDuplicates(unittest.TestCase):
    def test_order_preserved(self):
        self.assertEqual(LISTS.get_noDuplicates([1, 2, 2, 3, 1]), [1, 2, 3])

    def test_empty(self):
        self.assertEqual(LISTS.get_noDuplicates([]), [])


class Test_pairs(unittest.TestCase):
    def test_consecutive(self):
        self.assertEqual(
            LISTS.get_listPairs(['dog', 'cat', 'pig', 'monkey']),
            [['dog', 'cat'], ['cat', 'pig'], ['pig', 'monkey']])

    def test_two(self):
        self.assertEqual(LISTS.get_listPairs([1, 2]), [[1, 2]])


class Test_match(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(LISTS.get_matchList([1, 2, 3], [2, 3, 4]), [2, 3])

    def test_none(self):
        self.assertEqual(LISTS.get_matchList([1, 2], [3, 4]), [])


class Test_keys(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(sorted(LISTS.get_keys_from_dict({'a': 1, 'b': 2})),
                         ['a', 'b'])


class Test_reorder(unittest.TestCase):
    def test_up(self):
        l = ['a', 'b', 'c', 'd']
        self.assertEqual(LISTS.reorder_in_place(l, ['c'], direction=0),
                         ['a', 'c', 'b', 'd'])

    def test_down(self):
        l = ['a', 'b', 'c', 'd']
        self.assertEqual(LISTS.reorder_in_place(l, ['b'], direction=1),
                         ['a', 'c', 'b', 'd'])


class Test_split(unittest.TestCase):
    def test_even_mode0(self):
        self.assertEqual(LISTS.get_split([1, 2, 3, 4, 5, 6], mode=0),
                         [[1, 2, 3], [3, 4, 5, 6]])

    def test_even_mode1(self):
        self.assertEqual(LISTS.get_split([1, 2, 3, 4, 5, 6], mode=1),
                         [[1, 2, 3, 4], [4, 5, 6]])

    def test_too_short(self):
        self.assertRaises(Exception, LISTS.get_split, [1, 2])


class Test_firstMidLast(unittest.TestCase):
    def test_seven(self):
        self.assertEqual(LISTS.get_first_mid_last([0, 1, 2, 3, 4, 5, 6]),
                         [0, 4, 6])


class Test_missing(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(LISTS.get_missing([1, 2], [2, 3, 4]), [3, 4])

    def test_difference_empty_base(self):
        self.assertEqual(LISTS.get_difference([], [1, 2]), [1, 2])


class Test_indexEntries(unittest.TestCase):
    def test_remove(self):
        data = [['cgmName', 'x'], ['tx', '1'], ['cgmType', 'y']]
        self.assertEqual(LISTS.remove_matched_index_entries(data, 'cgm'),
                         [['tx', '1']])

    def test_keep(self):
        data = [['cgmName', 'x'], ['tx', '1']]
        self.assertEqual(LISTS.get_matched_index_entries(data, 'cgm'),
                         [['cgmName', 'x']])


class Test_namePairs(unittest.TestCase):
    def test_left_right(self):
        names = ['arm_left', 'arm_right', 'leg_left']
        self.assertEqual(LISTS.get_matched_stripped_end(names),
                         [['arm_left', 'arm_right']])

    def test_replace(self):
        self.assertEqual(
            LISTS.get_replaced_name_list(['arm_left', 'leg_left']),
            ['arm_right', 'leg_right'])


class Test_cvSimplify(unittest.TestCase):
    def test_ends(self):
        self.assertEqual(LISTS.simplify_cv_list(['a', 'b', 'c', 'd'], 1),
                         ['a', 'd'])

    def test_all(self):
        src = ['a', 'b', 'c']
        self.assertEqual(LISTS.simplify_cv_list(src, 6), src)


class Test_shimNames(unittest.TestCase):
    """Old import path must resolve after cgm.lib.lists is a shim. Old names live on the shim, not list_utils."""
    def test_lib_reexport(self):
        from cgm.lib import lists as oldLists
        self.assertIs(oldLists.get_chunks, LISTS.get_chunks)
        self.assertEqual(oldLists.returnListChunks([1, 2, 3, 4], 2),
                         [[1, 2], [3, 4]])
        self.assertIs(oldLists.returnListChunks, LISTS.get_chunks)

    def test_old_names_not_on_core(self):
        self.assertFalse(hasattr(LISTS, 'returnListChunks'))
        self.assertFalse(hasattr(LISTS, 'parseListToPairs'))
