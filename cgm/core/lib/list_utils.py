"""
------------------------------------------
list_utils: cgm.core.lib.list_utils
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Canonical list helpers. Maya-free — do not import maya.cmds here.
"""
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

__MAYALOCAL = 'LISTS'


#>>> Utilities
#===================================================================
def get_noDuplicates(l):
    """
    Get a list with no duplicates (order preserved).
    """
    _l = []
    for v in l:
        if v not in _l:
            _l.append(v)
    return _l

def get_chunks(l, n):
    """
    Split a list into chunks of size n.

    :parameters:
        l(list) | list of things to chunkify
        n(int) | chunk size

    :returns
        List of chunks(list)

    SOURCE:
    http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks-in-python/312644#312644
    """
    return [l[i:i+n] for i in range(0, len(l), n)]

def get_listPairs(dataList):
    """
    Consecutive pairs. [dog,cat,pig,monkey] → [[dog,cat],[cat,pig],[pig,monkey]]
    """
    nestedPairList = []
    cnt = 1
    for itemA in dataList[:-1]:
        itemB = dataList[cnt]
        nestedPairList.append([itemA, itemB])
        cnt += 1
    return nestedPairList

def get_matchList(list1, list2):
    """Items in list1 that are also in list2. Empty list if none (not False)."""
    matchList = []
    if list1 and list2:
        for item in list1:
            if item in list2:
                matchList.append(item)
    return matchList

def get_keys_from_dict(d):
    return list(d.keys())

def reorder_in_place(l, subL, direction=0):
    """
    Reorder items of subL inside l.
    direction 0 = toward index 0, 1 = toward the end.
    Mutates l and returns it.
    """
    returnList = l
    for i in subL:
        if i in returnList:
            idx = returnList.index(i)
            if not direction and idx != 0:
                if idx - 1 in range(len(returnList)):
                    if returnList[idx - 1] not in subL:
                        returnList.remove(i)
                        returnList.insert(idx - 1, i)
            elif direction and idx != len(returnList):
                if idx + 1 in range(len(returnList)):
                    if returnList[idx + 1] not in subL:
                        returnList.remove(i)
                        returnList.insert(idx + 1, i)
            else:
                log.info("List is already in order. No change.")
        else:
            log.info("'%s' not in the target list. Try again..." % i)
    return returnList

def get_split(listToSplit, mode=0, popMid=False):
    """
    Split a list in two with overlap on the middle item.
    mode 0 favors the front; mode 1 favors the rear.
    Length must be 3 or greater.
    """
    _str_funcName = 'get_split'
    if not len(listToSplit) >= 3:
        raise Exception("%s >>> list length must be 3 or greater. len : %s | list: %s" % (
            _str_funcName, len(listToSplit), listToSplit))
    half = len(listToSplit) // 2
    if len(listToSplit) % 2 == 0:
        if mode == 0:
            halfA = listToSplit[:half]
            halfB = listToSplit[half - 1:]
        else:
            halfA = listToSplit[:half + 1]
            halfB = listToSplit[half:]
    else:
        halfA = listToSplit[:half + 1]
        halfB = listToSplit[half:]
    if popMid:
        mid = listToSplit[int(len(listToSplit) / 2.0)]
        if mid in halfA:
            halfA.remove(mid)
        if mid in halfB:
            halfB.remove(mid)
    return [halfA, halfB]

def get_first_mid_last(seq):
    """First, middle, last items (constraint weighting helper)."""
    return [seq[0], seq[int(round((len(seq)) * 1 / 2))], seq[-1]]

def get_factored_constraint_list(listToFactor, factor):
    """
    Factor a list for multi-target constrain sets.
    """
    loopCnt = (len(listToFactor) // (factor))
    culledList = []
    keepSplittingList = []
    if len(listToFactor) > (factor + 1):
        culledList.append(get_first_mid_last(listToFactor))
        bufferList = get_split(listToFactor, mode=1)
        for sub in bufferList:
            if len(sub) > (factor + 1):
                culledList.append(get_first_mid_last(sub))
                splitBuffer = get_split(sub, mode=1)
                for sublist in splitBuffer:
                    keepSplittingList.append(sublist)
            else:
                culledList.append(sub)
    else:
        return culledList
    if len(keepSplittingList) > 0:
        while loopCnt > 0:
            for sub in list(keepSplittingList):
                if len(sub) > (factor + 1):
                    culledList.append(get_first_mid_last(sub))
                    splitBuffer = get_split(sub, mode=1)
                    for subList in splitBuffer:
                        keepSplittingList.append(subList)
                else:
                    if sub in keepSplittingList:
                        keepSplittingList.remove(sub)
                    culledList.append(sub)
            loopCnt -= 1
    return culledList

def get_pos_no_duplicates(posSearchList, decimalPlaces=4):
    """Drop duplicate positions after rounding each component."""
    decimalFormat = '%s%i%s' % ("%.", decimalPlaces, "f")
    formattedList = []
    for pos in posSearchList:
        posBuffer = []
        for n in pos:
            posBuffer.append(float(decimalFormat % (n)))
        formattedList.append(posBuffer)
    matchList = []
    returnList = []
    cnt = 0
    for pos in formattedList:
        if pos not in matchList:
            matchList.append(pos)
            returnList.append(posSearchList[cnt])
        cnt += 1
    return returnList

def get_missing(baseList, searchList):
    """Items in searchList not found in baseList."""
    missingList = []
    if baseList and searchList:
        for item in searchList:
            if item not in baseList:
                missingList.append(item)
    return missingList

def get_difference(baseList, newList):
    """Items in newList not in baseList (does not require both to be truthy)."""
    missingList = []
    for item in newList:
        if item not in baseList:
            missingList.append(item)
    return missingList

def remove_matched_index_entries(searchList, searchTerm):
    """Nested list: keep rows whose first cell does not contain searchTerm."""
    newList = []
    for term in searchList:
        if searchTerm not in term[0]:
            newList.append(term)
    return newList

def get_matched_index_entries(searchList, searchTerm):
    """Nested list: keep rows whose first cell contains searchTerm."""
    newList = []
    for term in searchList:
        if searchTerm in term[0]:
            newList.append(term)
    return newList

def get_matched_stripped_end(searchList, searchTerms=None):
    """
    Pair names that share a prefix and differ by suffix tokens (default left/right).
    """
    if searchTerms is None:
        searchTerms = ['left', 'right']
    newList = []
    for term in searchList:
        currentIndex = searchList.index(term)
        if searchTerms[0] in term:
            splitBuffer = term.split('_')
            nameBuffer = splitBuffer[:-1]
            baseName = '_'.join(nameBuffer)
            for searchTerm in searchList:
                if searchTerm != searchList[currentIndex]:
                    if searchTerms[1] in searchTerm:
                        newSplitBuffer = searchTerm.split('_')
                        newNameBuffer = newSplitBuffer[:-1]
                        newSearchTerm = '_'.join(newNameBuffer)
                        if newSearchTerm == baseName:
                            newList.append([term, searchTerm])
    return newList

def get_replaced_name_list(searchList, replaceWith=None):
    """Replace substrings in names. replaceWith is {old: new}."""
    if replaceWith is None:
        replaceWith = {'left': 'right'}
    newList = []
    for term in searchList:
        for q in list(replaceWith.keys()):
            if q in term:
                newList.append(term.replace(q, replaceWith[q]))
    return newList

def simplify_cv_list(listToSimplify, mode):
    """
    Simplify a CV list.
    mode: 0 mid only, 1 ends only, 2 mid and ends, 3 odds, 4 evens,
          5 all except start/end anchors, 6 all
    """
    culledList = []
    listLength = len(listToSimplify)
    if mode == 0:
        culledList.append(listToSimplify[int(round(listLength * 1 / 2))])
    elif mode == 1:
        culledList.append(listToSimplify[0])
        culledList.append(listToSimplify[-1])
    elif mode == 2:
        culledList.append(listToSimplify[0])
        culledList.append(listToSimplify[int(round(listLength * 1 / 2))])
        culledList.append(listToSimplify[-1])
    elif mode == 3:
        tmpList = []
        tmpList.append(listToSimplify[0])
        midBuffer = listToSimplify[2:-3]
        for item in midBuffer:
            tmpList.append(item)
        tmpList.append(listToSimplify[-1])
        cnt = 1
        if len(tmpList) % 2 == 0:
            for n in range(int(round(len(tmpList) * 1 / 2)) - 1):
                culledList.append(tmpList[cnt])
                cnt += 2
            culledList.append(listToSimplify[-3])
        else:
            for n in range(int(round(len(tmpList) * 1 / 2))):
                culledList.append(tmpList[cnt])
                cnt += 2
            culledList.append(tmpList[-1])
    elif mode == 4:
        tmpList = []
        tmpList.append(listToSimplify[0])
        midBuffer = listToSimplify[2:-3]
        for item in midBuffer:
            tmpList.append(item)
        tmpList.append(listToSimplify[-1])
        cnt = 0
        if len(tmpList) % 2 == 0:
            for n in range(int(round(len(tmpList) * 1 / 2))):
                culledList.append(tmpList[cnt])
                cnt += 2
            culledList.append(tmpList[-1])
        else:
            for n in range(int(round(len(tmpList) * 1 / 2))):
                culledList.append(tmpList[cnt])
                cnt += 2
            culledList.append(listToSimplify[-3])
    elif mode == 5:
        culledList.append(listToSimplify[0])
        midBuffer = listToSimplify[2:-2]
        for item in midBuffer:
            culledList.append(item)
        culledList.append(listToSimplify[-1])
    elif mode == 6:
        culledList = listToSimplify
    return culledList
