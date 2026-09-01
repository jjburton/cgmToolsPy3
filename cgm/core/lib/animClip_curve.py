"""
AnimClip curve IO — Phase 1 snapshot/rebuild + Phase 2a key-range slice.

Snapshot / rebuild time-based animCurve* nodes. Query the curve node, not the plug.
Driven/unitless types are out of scope. Capture uses ATTR.get_keyed / ATTR.get_driver
then snapshot; slice_keys drops keys outside Start/End; ensure_boundary_keys samples
unkeyed Start/End when capture requests it; offset_keys makes times relative to Start.
apply_to_plug keys dest.attr (Replace/Merge/Insert). Optional animLayer
adds dest controls to that Maya animLayer, then keys the preferred layer.
"""
import logging

import maya.cmds as mc
try:
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma
except ImportError:
    om = None
    oma = None

from cgm.core import cgm_General as cgmGEN
import cgm.core.lib.search_utils as SEARCH

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
    """Keep keys whose time is in [start, end]. Absolute times."""
    if dat is None:
        return None
    if start is None or end is None:
        return dat
    lo, hi = (start, end) if start <= end else (end, start)
    out = dict(dat)
    out['keys'] = [k for k in (dat.get('keys') or [])
                   if lo <= k.get('time', 0) <= hi]
    return out


def ensure_boundary_keys(dat, curve, start=None, end=None):
    """
    If start/end are unkeyed, insert evaluated samples on a copy.
    Absolute times. Evaluates curve.output; does not listConnections.
    Sampled keys use linear tangents. Does not mutate the Maya curve.

    Do not sample Start when it falls before the first key and preInfinity
    is not constant. Do not sample End when it falls after the last key
    and postInfinity is not constant. Interior unkeyed bounds still sample.
    """
    if dat is None:
        return None
    if start is None and end is None:
        return dat
    if not curve or not mc.objExists(curve):
        return dat
    out = dict(dat)
    keys = list(dat.get('keys') or [])
    times = [float(k.get('time', 0)) for k in keys]
    first_t = min(times) if times else None
    last_t = max(times) if times else None
    pri = _infinity_to_name(dat.get('preInfinity'))
    poi = _infinity_to_name(dat.get('postInfinity'))

    bounds = []
    if start is not None:
        t = float(start)
        in_pre = first_t is not None and t < first_t and not _close(t, first_t)
        if not (in_pre and pri != 'constant'):
            bounds.append(t)
    if end is not None and (start is None or not _close(float(end), float(start))):
        t = float(end)
        in_post = last_t is not None and t > last_t and not _close(t, last_t)
        if not (in_post and poi != 'constant'):
            bounds.append(t)

    changed = False
    for t in bounds:
        if any(_close(k.get('time', 0), t) for k in keys):
            continue
        k = empty_key_dat()
        k['time'] = t
        k['value'] = _as_float(mc.getAttr('{}.output'.format(curve), time=t))
        k['inTangentType'] = 'linear'
        k['outTangentType'] = 'linear'
        keys.append(k)
        changed = True
    if changed:
        keys.sort(key=lambda x: x.get('time', 0))
        out['keys'] = keys
    return out


def offset_keys(dat, origin=0.0):
    """Subtract origin from each key time. Clip-level relative time (Phase 2b)."""
    if dat is None:
        return None
    origin = float(origin or 0)
    if origin == 0:
        return dat
    out = dict(dat)
    keys = []
    for k in (dat.get('keys') or []):
        nk = dict(k)
        nk['time'] = float(k.get('time', 0)) - origin
        keys.append(nk)
    out['keys'] = keys
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
    v = _first(v, 'constant')
    if isinstance(v, str):
        key = v.strip()
        if key.isdigit():
            try:
                return _INF_NAMES[int(key)]
            except Exception:
                return 'constant'
        for name in _INF_NAMES:
            if name.lower() == key.lower():
                return name
        return 'constant'
    try:
        return _INF_NAMES[int(v)]
    except Exception:
        return 'constant'


def _mfn_anim_curve(curve):
    if om is None or oma is None:
        return None
    sl = om.MSelectionList()
    sl.add(curve)
    return oma.MFnAnimCurve(sl.getDependNode(0))


def _om_inf_enums():
    if oma is None:
        return {}
    return {
        'constant': oma.MFnAnimCurve.kConstant,
        'linear': oma.MFnAnimCurve.kLinear,
        'cycle': oma.MFnAnimCurve.kCycle,
        'cycleRelative': oma.MFnAnimCurve.kCycleRelative,
        'oscillate': oma.MFnAnimCurve.kOscillate,
    }


def _om_inf_name(val):
    for name, enum in _om_inf_enums().items():
        if int(val) == int(enum):
            return name
    try:
        return _INF_NAMES[int(val)]
    except Exception:
        return 'constant'


def _om_call(fn, name, *args):
    attr = getattr(fn, name)
    if args:
        return attr(*args)
    return attr() if callable(attr) else attr


def read_curve_infinity(curve):
    """pre/post infinity names. MFnAnimCurve first — cmds.getAttr often stays constant."""
    try:
        fn = _mfn_anim_curve(curve)
        if fn is not None:
            pri = _om_inf_name(_om_call(fn, 'preInfinityType'))
            poi = _om_inf_name(_om_call(fn, 'postInfinityType'))
            return pri, poi
    except Exception:
        pass
    pri = _infinity_to_name(mc.getAttr('{}.preInfinity'.format(curve)))
    poi = _infinity_to_name(mc.getAttr('{}.postInfinity'.format(curve)))
    return pri, poi


def set_curve_infinity(curve, pri=None, poi=None):
    """Set pre/post infinity via MFnAnimCurve. cmds.setInfinity does not stick on many animCurves."""
    d = _om_inf_enums()
    try:
        fn = _mfn_anim_curve(curve)
        if fn is not None:
            if pri is not None and pri in d:
                _om_call(fn, 'setPreInfinityType', d[pri])
            if poi is not None and poi in d:
                _om_call(fn, 'setPostInfinityType', d[poi])
            return read_curve_infinity(curve)
    except Exception:
        pass
    if pri is not None and pri in _INF_NAMES:
        mc.setAttr('{}.preInfinity'.format(curve), _INF_NAMES.index(pri))
    if poi is not None and poi in _INF_NAMES:
        mc.setAttr('{}.postInfinity'.format(curve), _INF_NAMES.index(poi))
    try:
        kw = {}
        if pri is not None:
            kw['pri'] = pri
        if poi is not None:
            kw['poi'] = poi
        if kw:
            mc.setInfinity(curve, **kw)
    except Exception:
        pass
    return read_curve_infinity(curve)


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

    pri, poi = read_curve_infinity(curve)

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

    pri = _infinity_to_name(dat.get('preInfinity'))
    poi = _infinity_to_name(dat.get('postInfinity'))
    set_curve_infinity(node, pri=pri, poi=poi)

    log.debug(log_msg(_str_func, '{} | {} keys'.format(node, len(keys))))
    return node


def is_base_anim_layer(layer):
    """True when paste should hit Base (None, empty, Base, BaseAnimation)."""
    if layer is None:
        return True
    s = str(layer).strip()
    if not s:
        return True
    return s.lower() in ('base', 'baseanimation')


def ensure_anim_layer(layer, override=None):
    """Return the animLayer node, creating it if needed. None for Base.
    override True=Override, False=Additive; applied only when the layer is created."""
    if is_base_anim_layer(layer):
        return None
    name = str(layer).strip()
    if not name or name.lower() == 'new':
        return None
    if mc.objExists(name):
        try:
            if mc.nodeType(name) == 'animLayer':
                return name
        except Exception:
            pass
    kws = {}
    if override is not None:
        kws['override'] = bool(override)
    created = mc.animLayer(name, **kws)
    node = created or name
    if override is not None and node and mc.objExists(node):
        try:
            mc.animLayer(node, e=True, override=bool(override))
        except Exception:
            pass
    return node


def _anim_layer_names():
    names = list(SEARCH.animLayers_get(includeBase=True) or [])
    seen = set(n.lower() for n in names)
    for n in mc.ls(type='animLayer') or []:
        short = str(n).split('|')[-1]
        if short.lower() not in seen:
            seen.add(short.lower())
            names.append(short)
    return names


def _attr_long(node, attr):
    try:
        return mc.attributeQuery(attr, node=node, longName=True) or attr
    except Exception:
        return attr


def anim_layer_add_nodes(layer, nodes):
    """Put dest transforms on the animLayer (addSelectedObjects). Restores selection."""
    if not layer or is_base_anim_layer(layer):
        return
    to_add = []
    for n in nodes or []:
        if n and mc.objExists(n) and n not in to_add:
            to_add.append(n)
    if not to_add:
        return
    sel = mc.ls(sl=True) or []
    try:
        try:
            if mc.animLayer(layer, q=True, lock=True):
                mc.animLayer(layer, e=True, lock=False)
        except Exception:
            pass
        mc.select(to_add, replace=True)
        mc.animLayer(layer, e=True, addSelectedObjects=True)
    finally:
        if sel:
            try:
                mc.select(sel, replace=True)
            except Exception:
                pass
        else:
            mc.select(clear=True)


def anim_layer_add_plug(layer, node, attr):
    """Add node.attr to the animLayer if it is not already there."""
    if not layer or not node or not attr:
        return
    long_attr = _attr_long(node, attr)
    plugs = []
    for n in (node, (mc.ls(node, long=True) or [node])[0],
              (mc.ls(node, shortNames=True) or [node])[0]):
        plugs.append('{}.{}'.format(n, attr))
        if long_attr != attr:
            plugs.append('{}.{}'.format(n, long_attr))
    existing = mc.animLayer(layer, q=True, attribute=True) or []
    if any(p in existing for p in plugs):
        return
    last_err = None
    for p in plugs:
        try:
            mc.animLayer(layer, e=True, addAttribute=p)
            return
        except Exception as err:
            last_err = err
    if last_err:
        log.warning(log_msg('anim_layer_add_plug', '{}.{} | {}'.format(node, attr, last_err)))


def anim_layer_ensure_plug(layer, node, attr):
    """Add the dest control to the layer, then the plug if needed. True if on the layer."""
    if SEARCH.animLayer_contains(layer, node, attr=attr):
        return True
    anim_layer_add_nodes(layer, [node])
    if SEARCH.animLayer_contains(layer, node, attr=attr):
        return True
    anim_layer_add_plug(layer, node, attr)
    return SEARCH.animLayer_contains(layer, node, attr=attr)


def anim_layer_curve_for_plug(layer, node, attr):
    """Layer animCurve for node.attr, or None."""
    if not layer or not node or not attr:
        return None
    long_attr = _attr_long(node, attr)
    plugs = []
    for n in ((mc.ls(node, long=True) or [node])[0], node,
              (mc.ls(node, shortNames=True) or [node])[0]):
        plugs.append('{}.{}'.format(n, attr))
        if long_attr != attr:
            plugs.append('{}.{}'.format(n, long_attr))
    for plug in plugs:
        try:
            found = mc.animLayer(layer, q=True, findCurveForPlug=plug)
        except Exception:
            found = None
        if found:
            if isinstance(found, (list, tuple)):
                return found[0] if found else None
            return found
    return None


def anim_layer_push(layer):
    """Prefer the target layer (or BaseAnimation). Unlock it for keying. Return restore state."""
    state = []
    for l in _anim_layer_names():
        try:
            state.append((l,
                          bool(mc.animLayer(l, q=True, selected=True)),
                          bool(mc.animLayer(l, q=True, preferred=True)),
                          bool(mc.animLayer(l, q=True, lock=True))))
        except Exception:
            pass
    target = ensure_anim_layer(layer)
    for l in _anim_layer_names():
        try:
            mc.animLayer(l, e=True, selected=False, preferred=False)
        except Exception:
            pass
    if target:
        try:
            mc.animLayer(target, e=True, lock=False)
        except Exception:
            pass
        mc.animLayer(target, e=True, selected=True, preferred=True)
    elif mc.objExists('BaseAnimation'):
        try:
            mc.animLayer('BaseAnimation', e=True, selected=True, preferred=True)
        except Exception:
            pass
    return state, target


def anim_layer_pop(state):
    for item in state or []:
        if len(item) < 3:
            continue
        l, sel, pref = item[0], item[1], item[2]
        lock = item[3] if len(item) > 3 else None
        if not mc.objExists(l):
            continue
        try:
            mc.animLayer(l, e=True, selected=sel, preferred=pref)
        except Exception:
            pass
        if lock is not None:
            try:
                mc.animLayer(l, e=True, lock=lock)
            except Exception:
                pass


def _shift_keys_after(node, attr, after_time, delta, animLayer=None):
    """Move keys on node.attr that are strictly after after_time by delta. No-op if none.
    Caller must prefer the target animLayer so keyframe hits that layer, not Base."""
    if delta <= 0:
        return
    existing = mc.keyframe(node, attribute=attr, q=True, timeChange=True) or []
    later = [float(t) for t in existing
             if float(t) > after_time and not _close(t, after_time)]
    if not later:
        return
    mc.keyframe(node, attribute=attr, edit=True, relative=True,
                timeChange=delta, time=(min(later), max(later)))


def apply_to_plug(dat, node, attr, timeOffset=0.0, mode='replace', animLayer=None):
    """
    Write clip keys onto node.attr. Does not look up animCurve node names.
    Replace cuts keys in the dest window first. Merge keeps other keys.
    Insert shifts dest keys after the first pasted time by the clip span, then writes.
    Tangents are set by time, not index. Insert does not change infinity.
    animLayer: None/Base writes Base; any other name adds the dest control
    to that Maya animLayer (created if missing) and keys the preferred layer.
    Dest list / mapping are the caller's job.
    """
    _str_func = 'apply_to_plug'
    log.debug(log_start(_str_func))
    if not dat:
        raise ValueError('No curve dat')
    if not node or not mc.objExists(node):
        raise ValueError('Node does not exist: {}'.format(node))
    if not attr or not mc.attributeQuery(attr, node=node, exists=True):
        raise ValueError('Missing attr: {}.{}'.format(node, attr))
    mode = (mode or 'replace').lower()
    if mode not in ('replace', 'merge', 'insert'):
        raise ValueError('Unknown apply mode: {}'.format(mode))

    keys = dat.get('keys') or []
    off = float(timeOffset or 0)
    dest_times = [float(k.get('time', 0)) + off for k in keys]
    state, layer_node = anim_layer_push(animLayer)
    try:
        if layer_node and not anim_layer_ensure_plug(layer_node, node, attr):
            raise ValueError('Could not add {}.{} to animLayer {}'.format(
                node, attr, layer_node))
        if mode == 'replace' and dest_times:
            mc.cutKey(node, attribute=attr,
                      time=(min(dest_times), max(dest_times)), clear=True)
        elif mode == 'insert' and dest_times:
            _shift_keys_after(node, attr, min(dest_times),
                              max(dest_times) - min(dest_times),
                              animLayer=layer_node)

        weighted = bool(dat.get('weightedTangents'))
        for k, t in zip(keys, dest_times):
            mc.setKeyframe(node, attribute=attr,
                           time=t,
                           value=k['value'],
                           breakdown=bool(k.get('breakdown')))

        if keys:
            kt_obj = node
            kt_kw = {'attribute': attr}
            if layer_node:
                layer_curve = anim_layer_curve_for_plug(layer_node, node, attr)
                if layer_curve:
                    kt_obj = layer_curve
                    kt_kw = {}
            mc.keyTangent(kt_obj, edit=True, weightedTangents=weighted, **kt_kw)
            for k, t in zip(keys, dest_times):
                tm = (t, t)
                itt = k.get('inTangentType') or 'auto'
                ott = k.get('outTangentType') or 'auto'
                use_fixed = itt in _FIXED_TANGENTS or ott in _FIXED_TANGENTS
                mc.keyTangent(kt_obj, time=tm, edit=True, lock=False, **kt_kw)
                if weighted and use_fixed:
                    mc.keyTangent(kt_obj, time=tm, edit=True,
                                  inWeight=_as_float(k.get('inWeight'), 1.0),
                                  outWeight=_as_float(k.get('outWeight'), 1.0),
                                  **kt_kw)
                mc.keyTangent(kt_obj, time=tm, edit=True,
                              inTangentType=itt, outTangentType=ott, **kt_kw)
                if use_fixed:
                    mc.keyTangent(kt_obj, time=tm, edit=True,
                                  inAngle=_as_float(k.get('inAngle')),
                                  outAngle=_as_float(k.get('outAngle')),
                                  **kt_kw)
                if weighted and use_fixed:
                    mc.keyTangent(kt_obj, time=tm, edit=True,
                                  weightLock=bool(k.get('weightLock', True)),
                                  **kt_kw)
                mc.keyTangent(kt_obj, time=tm, edit=True,
                              lock=bool(k.get('lock', True)), **kt_kw)

            if mode == 'replace':
                pri = dat.get('preInfinity') or 'constant'
                poi = dat.get('postInfinity') or 'constant'
                if not isinstance(pri, str):
                    pri = _infinity_to_name(pri)
                if not isinstance(poi, str):
                    poi = _infinity_to_name(poi)
                try:
                    if kt_kw:
                        mc.setInfinity(kt_obj, at=attr, pri=pri, poi=poi)
                    else:
                        mc.setInfinity(kt_obj, pri=pri, poi=poi)
                except Exception:
                    pass
    finally:
        anim_layer_pop(state)

    log.debug(log_msg(_str_func, '{}.{} | {} keys | {}{}'.format(
        node, attr, len(keys), mode,
        ' | {}'.format(layer_node) if layer_node else '')))
    return '{}.{}'.format(node, attr)


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
