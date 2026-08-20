"""
------------------------------------------
arrange_utils: cgm.core.lib.distance_utils
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

"""
__MAYALOCAL = 'ARRANGE'

# From Python =============================================================
import copy
import re
import sys

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# From Maya =============================================================
import maya.cmds as mc
import maya.mel as mel

# From Red9 =============================================================

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGen
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.lib import shared_data as SHARED
from cgm.core.lib import search_utils as SEARCH
from cgm.core.lib import math_utils as MATH
from cgm.core.lib import node_utils as NODE
from cgm.core.lib import attribute_utils as ATTR
import cgm.core.lib.position_utils as POS
import cgm.core.lib.transform_utils as TRANS
import cgm.core.lib.distance_utils as DIST
import cgm.core.lib.snap_utils as SNAP
import cgm.core.lib.curve_Utils as CURVES

#>>> Utilities
#===================================================================


def layout_byColumn(objList,columns=3,startPos = [0,0,0]):
    """
    Get a uv position in world space. UV should be normalized.
    
    :parameters:
        objList(list) | list of objects to arrange
        uValue(float) | uValue  
        vValue(float) | vValue 

    :returns
        pos(double3)

    """        
    _str_func = 'layout_byColumn'
    
    sizeXBuffer = []
    sizeYBuffer = []
    for obj in objectList:
        sizeBuffer = distance.returnBoundingBoxSize(obj)
        sizeXBuffer.append(sizeBuffer[0])
        sizeYBuffer.append(sizeBuffer[1])

    for obj in objList:
        mc.move(0,0,0,obj,a=True)

    sizeX = max(sizeXBuffer) * 1.75
    sizeY = max(sizeYBuffer) * 1.75

    startX = startPos[0]
    startY = startPos[1]
    startZ = startPos[2]

    col=1
    objectCnt = 0
    #sort the list

    sortedList = lists.returnListChunks(objectList,columns)
    bufferY = startY
    for row in sortedList:
        bufferX = startX
        for obj in row:
            mc.xform(obj,os=True,t=[bufferX,bufferY,startZ])
            bufferX += sizeX
        bufferY -= sizeY  
        
_d_arrangeLine_ann = {'linearEven':"Layout on line from first to last item evenly",
                      'linearSpaced':'Layout on line from first to last item closest as possible to original position',
                      'cubicEven':'Layout evenly on a curve created from the list',
                      'cubicArcEven':'Layout evenly on an arc defined by start,mid,last',
                      'cubicArcSpaced':'Layout spaced on an arc defined by start,mid,last',
                      'targetEven':'Last selected must be a curve; remaining objects even along the whole curve (first at start, last at end)',
                      'targetClosest':'Last selected must be a curve; remaining objects snap to closest point on the curve',                      
                      'cubicRebuild2Even':'Layout evenly on a 2 span rebuild curve from the list.',
                      'cubicRebuild3Even':'Layout evenly on a 2 span rebuild curve from the list.',
                      'cubicRebuild2Spaced':'Layout spaced on a 2 span rebuild curve from the list.',
                      'cubicRebuild3Spaced':'Layout spaced on a 2 span rebuild curve from the list.'}

PHI = 1.618033988749895

_d_arrangeRatio_ann = {
    'ratioGoldenLinear': 'Redistribute middles along first-to-last; each segment is phi times the next (root segment longest); endpoints fixed',
    'ratioGoldenCubic': 'Same golden chain spacing along a cubic curve through the selection; endpoints fixed',
    'ratioFingerLinear': 'Redistribute middle controls with phi on the first segment and equal segments after; endpoints fixed',
    'ratioFingerCubic': 'Finger ratio spacing along a cubic curve through the selection; endpoints fixed',
    'ratioCustomLinear': 'Prompt for a ratio or comma-separated segment weights; linear path; endpoints fixed',
    'ratioCustomCubic': 'Prompt for a ratio or comma-separated segment weights; cubic curve path; endpoints fixed',
    'ratioGoldenTarget': 'Last selected must be a curve; golden chain along the whole curve (first at start, last at end)',
    'ratioFingerTarget': 'Last selected must be a curve; finger ratio along the whole curve (first at start, last at end)',
    'ratioCustomTarget': 'Last selected must be a curve; prompt for ratio or segment weights along the whole curve (first at start, last at end)',
    'ratioSlider': 'Drag to live-redistribute the selection. 1 = even, 1.618 = golden. Path from Linear / Curve / To Curve.',
}

_d_ratioPresets = ('golden_all', 'finger')


def _ratio_weights(preset, segmentCount):
    """Segment weights for *segmentCount* intervals between consecutive controls."""
    if segmentCount < 1:
        raise ValueError('Need at least one segment for ratio weights')
    if preset == 'golden_all':
        # phi^(n-1), phi^(n-2), ... phi^0 — each segment phi x the next toward the tip
        return [PHI ** (segmentCount - 1 - i) for i in range(segmentCount)]
    if preset == 'finger':
        return [PHI] + [1.0] * (segmentCount - 1)
    raise ValueError('Unknown ratio preset: {0}'.format(preset))


def _ratio_default_prompt_text(segmentCount, style='golden'):
    """Default prompt string for custom ratio entry."""
    if segmentCount < 1:
        return '{0}'.format(PHI)
    if style == 'finger':
        return ','.join([str(PHI)] + ['1'] * (segmentCount - 1))
    return '{0}'.format(PHI)


def _ratio_parse_weights_input(text, segmentCount):
    """
    Parse prompt input into segment weights (root to tip).

    One positive number — geometric chain (ratio^(n-1), ..., ratio^0).
    Comma-separated list — explicit weight per segment; count must match *segmentCount*.
    """
    if segmentCount < 1:
        raise ValueError('Need at least one segment for ratio weights')
    if not text or not str(text).strip():
        raise ValueError('No ratio input')
    _parts = [p.strip() for p in str(text).replace(';', ',').split(',') if p.strip()]
    _values = [float(p) for p in _parts]
    if len(_values) == 1:
        _ratio = _values[0]
        if _ratio <= 0:
            raise ValueError('Ratio must be positive')
        return [_ratio ** (segmentCount - 1 - i) for i in range(segmentCount)]
    if len(_values) != segmentCount:
        raise ValueError(
            'Need {0} segment weight(s) for this selection; got {1}'.format(
                segmentCount, len(_values)))
    if any(v <= 0 for v in _values):
        raise ValueError('Segment weights must be positive')
    return _values


def _ratio_cumulative_fractions(weights):
    """Cumulative arc fractions [0, ..., 1] for len(weights)+1 joints."""
    _sum = float(sum(weights))
    _acc = 0.0
    _out = [0.0]
    for _w in weights:
        _acc += float(_w)
        _out.append(_acc / _sum)
    _out[-1] = 1.0
    return _out


def _ratio_curve_shape(curveBuffer):
    """Resolve a single nurbsCurve shape from alongLine-style curve buffer."""
    _use = curveBuffer[-1] if isinstance(curveBuffer, (list, tuple)) else curveBuffer
    if VALID.get_mayaType(_use) == 'nurbsCurve':
        return _use
    _shapes = TRANS.shapes_get(_use, True) or []
    for _shape in _shapes:
        if VALID.get_mayaType(_shape) == 'nurbsCurve':
            return _shape
    raise ValueError('No nurbsCurve shape found on: {0}'.format(_use))


def _ratio_closest_curve_percentage(shape, position, poci, samples=64):
    """turnOnPercentage parameter on *shape* closest to *position*."""
    _best_pct = 0.0
    _best_dist = None
    for _i in range(samples + 1):
        _pct = _i / float(samples)
        ATTR.set(poci, 'parameter', _pct)
        _p = [
            ATTR.get(poci, 'positionX'),
            ATTR.get(poci, 'positionY'),
            ATTR.get(poci, 'positionZ'),
        ]
        _d = DIST.get_distance_between_points(position, _p)
        if _best_dist is None or _d < _best_dist:
            _best_dist = _d
            _best_pct = _pct
    return _best_pct


def _ratio_build_curve(objList, curve, spans):
    """Build temporary reference curve (alongLine-style). Returns (shape, deleteList)."""
    _len = len(objList)
    curveBuffer = []
    if curve == 'linear':
        return None, []
    if curve in ['cubic', 'cubicRebuild']:
        l_pos = [POS.get(o) for o in objList]
        knot_len = len(l_pos) + 3 - 1
        crv1 = mc.curve(d=3, ep=l_pos, k=[i for i in range(0, knot_len)], os=True)
        curveBuffer = [crv1]
        if curve == 'cubicRebuild':
            curveBuffer.append(
                mc.rebuildCurve(
                    crv1, ch=0, rpo=0, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0,
                    s=spans, d=3, tol=0.001)[0])
    elif curve == 'target':
        _type = VALID.get_mayaType(objList[-1])
        if _type != 'nurbsCurve':
            raise ValueError(
                "Last selected must be curve. Found: '{}' | type: '{}'".format(
                    objList[-1], _type))
        curveBuffer = [objList[-1]]
    elif curve == 'cubicArc':
        _mid = MATH.get_midIndex(_len)
        l_pos = [POS.get(o) for o in [objList[0], objList[_mid], objList[-1]]]
        knot_len = len(l_pos) + 3 - 1
        curveBuffer = [mc.curve(d=3, ep=l_pos, k=[i for i in range(0, knot_len)], os=True)]
    else:
        raise ValueError('unknown curve setup: {0}'.format(curve))
    return _ratio_curve_shape(curveBuffer), curveBuffer


def alongRatio(objList=None, preset='golden_all', curve='linear', spans=2, move=True,
               segmentWeights=None, quiet=False):
    """
    Arrange controls along a path using proportional segment weights.

    linear / cubic / cubicRebuild / cubicArc — first and last stay fixed; middles move.
    target — last selected must be a nurbsCurve; remaining objects cover U 0→1
    (first at curve start, last at curve end).

    :parameters:
        objList(list): ordered objects (selection order)
        preset(str): 'golden_all' | 'finger'
        curve(str): 'linear' | 'cubic' | 'cubicRebuild' | 'cubicArc' | 'target'
        spans(int): rebuild spans when curve is 'cubicRebuild'
        move(bool): apply positions
        segmentWeights(list): optional explicit weights (overrides preset)
        quiet(bool): skip Script Editor weight log (slider drag)

    :returns:
        list of world positions (all objects; unchanged entries match current pos)
    """
    _str_func = 'alongRatio'
    objList = VALID.mNodeStringList(objList)
    objListBase = copy.copy(objList)

    log.debug('|{0}| >> ObjList: {1}'.format(_str_func, objList))

    objListWork = list(objList)
    if curve == 'target':
        if not objListWork:
            raise ValueError('|{0}| >> Nothing selected'.format(_str_func))
        if VALID.get_mayaType(objListWork[-1]) != 'nurbsCurve':
            raise ValueError(
                "Last selected must be curve. Found: '{}' | type: '{}'".format(
                    objListWork[-1], VALID.get_mayaType(objListWork[-1])))
        objListWork = objListWork[:-1]
    _min_work = 2 if curve == 'target' else 3
    if len(objListWork) < _min_work:
        raise ValueError(
            '|{0}| >> Need at least {1} objects'.format(_str_func, _min_work))

    _seg_count = len(objListWork) - 1
    if segmentWeights is not None:
        _weights = [float(w) for w in segmentWeights]
        if len(_weights) != _seg_count:
            raise ValueError(
                '|{0}| >> Expected {1} segment weights; got {2}'.format(
                    _str_func, _seg_count, len(_weights)))
        if any(w <= 0 for w in _weights):
            raise ValueError('|{0}| >> Segment weights must be positive'.format(_str_func))
    else:
        if preset not in _d_ratioPresets:
            raise ValueError('|{0}| >> Unknown preset: {1}'.format(_str_func, preset))
        _weights = _ratio_weights(preset, _seg_count)

    _pos_start = POS.get(objListWork[0])
    _pos_end = POS.get(objListWork[-1])
    _cumulative = _ratio_cumulative_fractions(_weights)
    _label = 'custom' if segmentWeights is not None else preset
    if not quiet:
        log.info('|{0}| >> {1} | weights: {2} | cumulative: {3}'.format(
            _str_func, _label, _weights, _cumulative))

    _l_pos = [_pos_start]
    for _o in objListWork[1:-1]:
        _l_pos.append(POS.get(_o))
    _l_pos.append(_pos_end)

    _curve_delete = []
    if curve != 'linear':
        _curve_shape, _curve_delete = _ratio_build_curve(objList, curve, spans)

    if curve == 'linear':
        _vec = MATH.get_vector_of_two_points(_pos_start, _pos_end)
        _total = DIST.get_distance_between_points(_pos_start, _pos_end)
        for _i, _o in enumerate(objListWork[1:-1], start=1):
            _dist = _cumulative[_i] * _total
            _p = DIST.get_pos_by_vec_dist(_pos_start, _vec, _dist)
            _l_pos[_i] = _p
            if move:
                POS.set(_o, _p)
    else:
        _poci = CURVES.create_pointOnInfoNode(_curve_shape, turnOnPercentage=True)
        try:
            if curve == 'target':
                _pct_start = 0.0
                _pct_end = 1.0
                _indices = range(len(objListWork))
            else:
                _pct_start = _ratio_closest_curve_percentage(_curve_shape, _pos_start, _poci)
                _pct_end = _ratio_closest_curve_percentage(_curve_shape, _pos_end, _poci)
                if _pct_start > _pct_end:
                    _pct_start, _pct_end = _pct_end, _pct_start
                _indices = range(1, len(objListWork) - 1)
            _pct_span = _pct_end - _pct_start
            for _i in _indices:
                _o = objListWork[_i]
                _pct = _pct_start + _cumulative[_i] * _pct_span
                ATTR.set(_poci, 'parameter', _pct)
                _p = [
                    ATTR.get(_poci, 'positionX'),
                    ATTR.get(_poci, 'positionY'),
                    ATTR.get(_poci, 'positionZ'),
                ]
                _l_pos[_i] = _p
                if move:
                    POS.set(_o, _p)
        finally:
            mc.delete(_poci)

    if _curve_delete and curve != 'target':
        mc.delete(_curve_delete)

    mc.select(objListBase)
    return _l_pos


def alongRatio_prompt(objList=None, curve='linear', spans=2, move=True, default=None,
                      defaultStyle='golden'):
    """
    Prompt for ratio / segment weights, then run alongRatio.

    One value — geometric chain from root to tip.
    Comma list — one weight per segment (root to tip).

    defaultStyle: 'golden' (single phi) | 'finger' (phi,1,1,...)
    """
    _str_func = 'alongRatio_prompt'
    if not objList:
        objList = mc.ls(sl=1)
    objList = VALID.mNodeStringList(objList)
    if not objList:
        raise ValueError('|{0}| >> Nothing selected'.format(_str_func))

    _work = list(objList)
    if curve == 'target':
        if VALID.get_mayaType(_work[-1]) != 'nurbsCurve':
            raise ValueError(
                "Last selected must be curve. Found: '{}' | type: '{}'".format(
                    _work[-1], VALID.get_mayaType(_work[-1])))
        _work = _work[:-1]
    _min_work = 2 if curve == 'target' else 3
    if len(_work) < _min_work:
        raise ValueError(
            '|{0}| >> Need at least {1} objects'.format(_str_func, _min_work))

    _seg_count = len(_work) - 1
    if default is None:
        default = _ratio_default_prompt_text(_seg_count, defaultStyle)
    _msg = (
        'Root to tip — {0} segment(s):\n'
        '  One number — geometric chain (e.g. 1.618)\n'
        '  Comma list — weight per segment (e.g. 1.618,1,1)'.format(_seg_count))
    _result = mc.promptDialog(
        title='Arrange Ratio',
        message=_msg,
        button=['OK', 'Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel',
        text=default)
    if _result != 'OK':
        log.info('|{0}| >> Cancelled'.format(_str_func))
        return False

    _text = mc.promptDialog(query=True, text=True)
    _weights = _ratio_parse_weights_input(_text, _seg_count)
    return alongRatio(
        objList, preset='golden_all', curve=curve, spans=spans, move=move,
        segmentWeights=_weights)


def alongRatio_value(objList=None, ratio=None, curve='linear', spans=2, move=True,
                     quiet=False):
    """
    Arrange from a single geometric ratio (slider / one-number custom).

    ratio^(n-1) … ratio^0 per segment. ratio=1 is even; phi is golden.
    """
    _str_func = 'alongRatio_value'
    if not objList:
        objList = mc.ls(sl=1)
    objList = VALID.mNodeStringList(objList)
    if not objList:
        raise ValueError('|{0}| >> Nothing selected'.format(_str_func))
    if ratio is None:
        ratio = PHI
    _ratio = float(ratio)
    if _ratio <= 0:
        raise ValueError('|{0}| >> Ratio must be positive'.format(_str_func))

    _work = list(objList)
    if curve == 'target':
        if VALID.get_mayaType(_work[-1]) != 'nurbsCurve':
            raise ValueError(
                "Last selected must be curve. Found: '{}' | type: '{}'".format(
                    _work[-1], VALID.get_mayaType(_work[-1])))
        _work = _work[:-1]
    _min_work = 2 if curve == 'target' else 3
    if len(_work) < _min_work:
        raise ValueError(
            '|{0}| >> Need at least {1} objects'.format(_str_func, _min_work))

    _seg_count = len(_work) - 1
    _weights = [_ratio ** (_seg_count - 1 - i) for i in range(_seg_count)]
    return alongRatio(
        objList, preset='golden_all', curve=curve, spans=spans, move=move,
        segmentWeights=_weights, quiet=quiet)


def alongLine(objList = None, mode = 'even', curve = 'linear',spans = 2):
    """    
    Arrange a list of objects evenly along a vector from first to last
    
    :parameters:
        objList(list): objects to layout
        mode(string)
            'even' - evenly distributed along line
            'spaced' - distribute along line as close as possible to current position

    :returns
        list of constraints(list)
    """   
    _str_func = 'alongLine'
    objList = VALID.mNodeStringList(objList)
    objListBase = copy.copy(objList)
    
    log.debug("|{0}| >> ObjList: {1} ".format(_str_func,objList))             
    _len = len(objList)
    if _len < 3:
        raise ValueError("|{0}| >> Need at least 3 objects".format(_str_func))
    
    _pos_start = POS.get(objList[0])
    _pos_end = POS.get(objList[-1])    
    curveBuffer = []
    if curve == 'linear':
        if mode != 'even':
            curveBuffer = mc.curve (d=1, ep = [_pos_start,_pos_end])
    elif curve in ['cubic','cubicRebuild']:
        l_pos = [POS.get(o) for o in objList]
        knot_len = len(l_pos)+3-1		
        crv1 = mc.curve (d=3, ep = l_pos, k = [i for i in range(0,knot_len)], os=True)
        curveBuffer = [crv1]
        if curve == 'cubicRebuild':
            curveBuffer.append(mc.rebuildCurve (crv1, ch=0, rpo=0, rt=0, end=1, kr=0, kcp=0, kep=1, kt=0, s=spans, d=3, tol=0.001)[0])
    elif curve == 'target':
        _type = VALID.get_mayaType(objList[-1])
        if _type != 'nurbsCurve':
            raise ValueError("Last selected must be curve. Found: '{}' | type: '{}'".format(objList[-1], _type))
        curveBuffer = objList.pop(-1)
        _len -=1

    elif curve == 'cubicArc':
        _mid = MATH.get_midIndex(_len)
        log.debug("|{0}| >> cubicArc | mid: {1} ".format(_str_func,_mid))
        
        l_pos = [POS.get(o) for o in [objList[0],objList[_mid],objList[-1]]]
        knot_len = len(l_pos)+3-1		
        curveBuffer = mc.curve (d=3, ep = l_pos, k = [i for i in range(0,knot_len)], os=True)
    else:
        raise ValueError("|{0}| >>unknown curve setup: {1}".format(_str_func,curve))
    
    if mode == 'even':
        if curve == 'linear':
            _vec = MATH.get_vector_of_two_points(_pos_start, _pos_end)
            _offsetDist = DIST.get_distance_between_points(_pos_start,_pos_end) / (_len - 1)
            _l_pos = [ DIST.get_pos_by_vec_dist(_pos_start, _vec, (_offsetDist * i)) for i in range(_len)]
            log.debug("|{0}| >> offset: {1} ".format(_str_func,_offsetDist))   
            log.debug("|{0}| >> l_pos: {1} ".format(_str_func,_l_pos)) 
            for i,o in enumerate(objList[1:-1]):
                POS.set(o,_l_pos[i+1])        
        else:
            _l_pos = CURVES.getUSplitList(curveBuffer,points = _len,rebuild=1)
        
        if curve == 'target':
            for i,o in enumerate(objList):
                POS.set(o,_l_pos[i])            
        else:
            for i,o in enumerate(objList[1:-1]):
                POS.set(o,_l_pos[i+1])
            
    elif mode == 'spaced':
        _l_pos = []
        
        if curve == 'target':
            for i,o in enumerate(objList):
                p = DIST.get_by_dist(o,curveBuffer,resMode='pointOnSurface')
                POS.set(o,p)
                _l_pos.append(p)        
        else:
            for i,o in enumerate(objList[1:-1]):
                #SNAP.go(o,curveBuffer,pivot= 'closestPoint')
                p = DIST.get_by_dist(o,curveBuffer,resMode='pointOnSurface')
                POS.set(o,p)
                _l_pos.append(p)

        
        
    else:
        try:raise ValueError("{0} >> mode not supported: {1}".format(sys._getframe().f_code.co_name, mode))
        except:raise ValueError("mode not supported: {0}".format(mode))
        
        
    if curveBuffer and curve != 'target':
        mc.delete(curveBuffer)
    mc.select(objListBase)
    return _l_pos


def dag_sort(objList = None):
    """    
    Dag sort children under their parent
    
    """   
    _str_func = 'dag_sort'
    if not objList:
        objList = mc.ls(sl=1)
    else:
        objList = VALID.mNodeStringList(objList)
    log.info("|{0}| >> ObjList: {1} ".format(_str_func,objList))
    
    d_p = {}
    l_p = []
    l_world = []
    
    for o in objList:
        p = TRANS.parent_get(o)
        if not p:
            l_world.append(o)
        elif p not in l_p:
            l = TRANS.children_get(p) or []
            l.sort()
            l.reverse()
            for c in l:
                try:
                    mc.reorder(c,front=True)
                except Exception as err:
                    print(err)
    
    if l_world:
        l_world.sort()
        for o in l_world:
            try:
                mc.reorder(o,front=True)
            except Exception as err:
                print(err)            



    
