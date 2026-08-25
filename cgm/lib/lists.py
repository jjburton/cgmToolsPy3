#=================================================================================================================================================
#	lists - compatibility shim (cgmTools)
#=================================================================================================================================================
#
# Canonical implementation: cgm.core.lib.list_utils
# Keep this module so `from cgm.lib import lists` continues to work.
# Old names live here, not on list_utils.
#
#=================================================================================================================================================
from cgm.core.lib.list_utils import *

returnListChunks = get_chunks
returnListNoDuplicates = get_noDuplicates
parseListToPairs = get_listPairs
returnMatchList = get_matchList
reorderListInPlace = reorder_in_place
returnSplitList = get_split
returnFirstMidLastList = get_first_mid_last
returnFactoredConstraintList = get_factored_constraint_list
returnPosListNoDuplicates = get_pos_no_duplicates
returnMissingList = get_missing
returnDifference = get_difference
removeMatchedIndexEntries = remove_matched_index_entries
returnMatchedIndexEntries = get_matched_index_entries
returnMatchedStrippedEndList = get_matched_stripped_end
returnReplacedNameList = get_replaced_name_list
cvListSimplifier = simplify_cv_list
