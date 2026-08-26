"""
AnimClip curve IO — Phase 1 snapshot/rebuild + Phase 2a key-range slice.

Snapshot / rebuild time-based animCurve* nodes. Query the curve node, not the plug.
Driven/unitless types are out of scope. Capture uses ATTR.get_keyed / ATTR.get_driver
then snapshot; slice_keys drops keys outside Start/End. Relative time / boundary
samples later.
"""
import logging

import maya.cmds as mc

from cgm.core import cgm_General as cgmGEN

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

log_msg = cgmGEN.logString_msg
log_start = cgmGEN.logString_start

TIME_CURVE_TYPES = ('animCurveTL', 'animCurveTA', 'animCurveTU', 'animCurveTT')
_INF_NAMES = ('constant', 'linear', 'cycle', 'cycleRelative', 'oscillate')
_FIXED_TANGENTS = ('fixed',)
_FLOAT_KEYS = ('time', 'value', 'inAngle', 'outAngle', 'inWeight', 'outWeight')


def slice_keys(dat, start=None, end=None):
    """Keep keys whose time is in [start, end]. Absolute times. No boundary samples."""
    if dat is None:
        return None
    if start is None or end is None:
        return dat
    lo, hi = (start, end) if start <= end else (end, start)
    out = dict(dat)
    out['keys'] = [k for k in (dat.get('keys') or [])
                   if lo <= k.get('time', 0) <= hi]
    return out


def _first(v, default=None):
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        if not v:
            return default
        return v[0]
    return v


def _as_bool(v, default=False):
    x = _first(v, default)
    if x is None:
        return default
    return bool(x)


def _as_float(v, default=0.0):
    x = _first(v, default)
    if x is None:
        return default
    return float(x)


def _infinity_to_name(v):
    if isinstance(v, str):
        return v
    try:
        return _INF_NAMES[int(v)]
    except Exception:
        return 'constant'


def is_time_curve(node):
    if not node or not mc.objExists(node):
        return False
    return mc.nodeType(node) in TIME_CURVE_TYPES


def empty_key_dat():
    return {
        'time': 0.0,
        'value': 0.0,
        'inTangentType': 'auto',
        'outTangentType': 'auto',
        'inAngle': 0.0,
        'outAngle': 0.0,
        'inWeight': 1.0,
        'outWeight': 1.0,
        'lock': True,
        'weightLock': True,
        'breakdown': False,
    }


def empty_curve_dat():
    return {
        'curveType': 'animCurveTL',
        'preInfinity': 'constant',
        'postInfinity': 'constant',
        'weightedTangents': False,
        'nodeName': '',
        'color': None,
        'keys': [],
    }


def snapshot(curve):
    """Read one time-based animCurve* into the frozen curve dict."""
    _str_func = 'snapshot'
    log.debug(log_start(_str_func))
    if not curve or not mc.objExists(curve):
        raise ValueError('Curve does not exist: {}'.format(curve))
    ctype = mc.nodeType(curve)
    if ctype not in TIME_CURVE_TYPES:
        raise ValueError('Not a time-based animCurve ({}): {}'.format(ctype, curve))

    n = int(mc.keyframe(curve, q=True, keyframeCount=True) or 0)
    times = mc.keyframe(curve, q=True, timeChange=True) or []
    values = mc.keyframe(curve, q=True, valueChange=True) or []
    weighted = _as_bool(mc.keyTangent(curve, q=True, weightedTangents=True), False)

    pri = _infinity_to_name(mc.getAttr('{}.preInfinity'.format(curve)))
    poi = _infinity_to_name(mc.getAttr('{}.postInfinity'.format(curve)))

    color = None
    try:
        if mc.attributeQuery('curveColor', node=curve, exists=True):
            color = list(mc.getAttr('{}.curveColor'.format(curve))[0])
    except Exception:
        color = None

    keys = []
    for i in range(n):
        idx = (i, i)
        k = empty_key_dat()
        k['time'] = _as_float(times[i] if i < len(times) else 0.0)
        k['value'] = _as_float(values[i] if i < len(values) else 0.0)
        k['inTangentType'] = str(_first(
            mc.keyTangent(curve, index=idx, q=True, inTangentType=True), 'auto'))
        k['outTangentType'] = str(_first(
            mc.keyTangent(curve, index=idx, q=True, outTangentType=True), 'auto'))
        k['inAngle'] = _as_float(mc.keyTangent(curve, index=idx, q=True, inAngle=True))
        k['outAngle'] = _as_float(mc.keyTangent(curve, index=idx, q=True, outAngle=True))
        k['inWeight'] = _as_float(mc.keyTangent(curve, index=idx, q=True, inWeight=True), 1.0)
        k['outWeight'] = _as_float(mc.keyTangent(curve, index=idx, q=True, outWeight=True), 1.0)
        k['lock'] = _as_bool(mc.keyTangent(curve, index=idx, q=True, lock=True), True)
        if weighted:
            k['weightLock'] = _as_bool(
                mc.keyTangent(curve, index=idx, q=True, weightLock=True), True)
        k['breakdown'] = _as_bool(mc.keyframe(curve, index=idx, q=True, breakdown=True), False)
        keys.append(k)

    dat = empty_curve_dat()
    dat['curveType'] = ctype
    dat['preInfinity'] = pri
    dat['postInfinity'] = poi
    dat['weightedTangents'] = weighted
    dat['nodeName'] = mc.ls(curve, shortNames=True)[0]
    dat['color'] = color
    dat['keys'] = keys
    log.debug(log_msg(_str_func, '{} | {} keys'.format(ctype, n)))
    return dat


def rebuild(dat, name=None):
    """Create a new animCurve* from a curve dict. Does not connect to a plug."""
    _str_func = 'rebuild'
    log.debug(log_start(_str_func))
    if not dat:
        raise ValueError('No curve dat')
    ctype = dat.get('curveType')
    if ctype not in TIME_CURVE_TYPES:
        raise ValueError('Not a time-based curveType: {}'.format(ctype))

    kw = {}
    if name:
        kw['name'] = name
    node = mc.createNode(ctype, **kw)

    keys = dat.get('keys') or []
    weighted = bool(dat.get('weightedTangents'))

    for k in keys:
        mc.setKeyframe(node,
                       time=(k['time'],),
                       value=k['value'],
                       breakdown=bool(k.get('breakdown')))

    if keys:
        mc.keyTangent(node, edit=True, weightedTangents=weighted)
        for i, k in enumerate(keys):
            idx = (i, i)
            itt = k.get('inTangentType') or 'auto'
            ott = k.get('outTangentType') or 'auto'
            use_fixed = itt in _FIXED_TANGENTS or ott in _FIXED_TANGENTS
            mc.keyTangent(node, index=idx, edit=True, lock=False)
            if weighted and use_fixed:
                mc.keyTangent(node, index=idx, edit=True,
                              inWeight=_as_float(k.get('inWeight'), 1.0),
                              outWeight=_as_float(k.get('outWeight'), 1.0))
            mc.keyTangent(node, index=idx, edit=True,
                          inTangentType=itt, outTangentType=ott)
            if use_fixed:
                mc.keyTangent(node, index=idx, edit=True,
                              inAngle=_as_float(k.get('inAngle')),
                              outAngle=_as_float(k.get('outAngle')))
            if weighted and use_fixed:
                mc.keyTangent(node, index=idx, edit=True,
                              weightLock=bool(k.get('weightLock', True)))
            mc.keyTangent(node, index=idx, edit=True, lock=bool(k.get('lock', True)))

    pri = dat.get('preInfinity') or 'constant'
    poi = dat.get('postInfinity') or 'constant'
    if not isinstance(pri, str):
        pri = _infinity_to_name(pri)
    if not isinstance(poi, str):
        poi = _infinity_to_name(poi)
    if keys:
        mc.setInfinity(node, pri=pri, poi=poi)
    else:
        if pri in _INF_NAMES:
            mc.setAttr('{}.preInfinity'.format(node), _INF_NAMES.index(pri))
        if poi in _INF_NAMES:
            mc.setAttr('{}.postInfinity'.format(node), _INF_NAMES.index(poi))

    log.debug(log_msg(_str_func, '{} | {} keys'.format(node, len(keys))))
    return node


def _close(a, b, places=4):
    return abs(float(a) - float(b)) < (10 ** (-places))


def compare(src, dst, places=4):
    """
    Compare two curve dicts (or node names). Ignores nodeName / color.

    Returns a list of mismatch strings (empty if equal).
    """
    if not isinstance(src, dict):
        src = snapshot(src)
    if not isinstance(dst, dict):
        dst = snapshot(dst)

    errs = []
    if src.get('curveType') != dst.get('curveType'):
        errs.append('curveType {} != {}'.format(src.get('curveType'), dst.get('curveType')))
    if src.get('preInfinity') != dst.get('preInfinity'):
        errs.append('preInfinity {} != {}'.format(src.get('preInfinity'), dst.get('preInfinity')))
    if src.get('postInfinity') != dst.get('postInfinity'):
        errs.append('postInfinity {} != {}'.format(src.get('postInfinity'), dst.get('postInfinity')))
    if bool(src.get('weightedTangents')) != bool(dst.get('weightedTangents')):
        errs.append('weightedTangents {} != {}'.format(
            src.get('weightedTangents'), dst.get('weightedTangents')))

    sk = src.get('keys') or []
    dk = dst.get('keys') or []
    if len(sk) != len(dk):
        errs.append('key count {} != {}'.format(len(sk), len(dk)))
        return errs

    for i, (a, b) in enumerate(zip(sk, dk)):
        for fk in _FLOAT_KEYS:
            if not _close(a.get(fk, 0.0), b.get(fk, 0.0), places):
                errs.append('key[{}].{} {} != {}'.format(i, fk, a.get(fk), b.get(fk)))
        for tk in ('inTangentType', 'outTangentType'):
            if str(a.get(tk)) != str(b.get(tk)):
                errs.append('key[{}].{} {} != {}'.format(i, tk, a.get(tk), b.get(tk)))
        if bool(a.get('lock')) != bool(b.get('lock')):
            errs.append('key[{}].lock {} != {}'.format(i, a.get('lock'), b.get('lock')))
        if bool(src.get('weightedTangents')):
            if bool(a.get('weightLock')) != bool(b.get('weightLock')):
                errs.append('key[{}].weightLock {} != {}'.format(
                    i, a.get('weightLock'), b.get('weightLock')))
        if bool(a.get('breakdown')) != bool(b.get('breakdown')):
            errs.append('key[{}].breakdown {} != {}'.format(
                i, a.get('breakdown'), b.get('breakdown')))
    return errs
