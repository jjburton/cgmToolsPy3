"""
AnimClip Dat — JSON Dat + Phase 0 UI + Phase 1 curve fixture wrap + Phase 2 capture.

Curve snapshot/rebuild lives in animClip_curve.py. Capture uses ATTR.get_keyed /
ATTR.get_driver, then snapshot + slice_keys + offset_keys. keyStartEnd optionally
runs ensure_boundary_keys. Apply matches the target object, then keys each channel
attr via apply_to_plug (Replace/Merge/Insert). Mapping: Auto/Name/Index plus
PoseManager match methods via r9Core.matchNodeLists. Dest list is the Maya
selection when anything is picked, else a global Name map. Apply Layer is
Base or a specified Maya animLayer.
"""
__MAYALOCAL = 'ANIMCLIPDAT'

import os
import time
import getpass

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

from cgm.core import cgm_Dat as CGMDAT
from cgm.core import cgm_General as cgmGEN
from cgm.core.classes import GuiFactory as CGMUI
import cgm.core.cgmPy.path_Utils as PATHS
import cgm.core.lib.shared_data as CORESHARE
import cgm.core.lib.string_utils as CORESTRINGS
import cgm.core.lib.search_utils as SEARCH
import cgm.core.lib.attribute_utils as ATTR
import cgm.core.lib.name_utils as NAMES
import cgm.core.lib.math_utils as MATH
import cgm.core.lib.animClip_curve as ANIMCLIPCURVE
import Red9.core.Red9_CoreUtils as r9Core
import Red9.core.Red9_Meta as r9Meta

mUI = CGMUI.mUI
__version__ = cgmGEN.__RELEASESTRING

log_msg = cgmGEN.logString_msg
log_start = cgmGEN.logString_start

_CLIP_VERSION = 1


def reload_dependencies():
    """Reload AnimClip backend modules (tool open / ui.reload)."""
    from cgm.core import cgm_Dat as _CGMDAT
    import cgm.core.lib.animClip_curve as _animClip_curve
    import cgm.core.lib.search_utils as _SEARCH
    cgmGEN._reloadMod(_CGMDAT)
    cgmGEN._reloadMod(_SEARCH)
    cgmGEN._reloadMod(_animClip_curve)
    global ANIMCLIPCURVE, SEARCH
    ANIMCLIPCURVE = _animClip_curve
    SEARCH = _SEARCH
    return ANIMCLIPCURVE


def _clip_name(uiDat, loadedFile):
    if loadedFile:
        return os.path.splitext(os.path.basename(loadedFile))[0]
    d = (uiDat.dat if uiDat else None) or {}
    if d.get('name'):
        return d['name']
    return 'untitled'


def _clip_frame_count(d):
    start = d.get('sourceStart')
    end = d.get('sourceEnd')
    if start is None or end is None:
        return None
    return int(end) - int(start) + 1


def _clip_duration(d):
    """Span from sourceStart to sourceEnd. 0 if missing or a single frame."""
    start = d.get('sourceStart')
    end = d.get('sourceEnd')
    if start is None or end is None:
        return 0
    return abs(int(end) - int(start))


def _clip_curve_count(d):
    n = 0
    for obj in d.get('objects') or []:
        n += len(obj.get('channels') or [])
    return n


def _progress_begin(maxValue, status):
    try:
        return CGMUI.doStartMayaProgressBar(
            stepMaxValue=max(int(maxValue), 1),
            statusMessage=status,
            interruptableState=True)
    except Exception:
        return None


def _progress_tick(bar, progress, maxValue, status):
    if not bar:
        return False
    try:
        if mc.progressBar(bar, query=True, isCancelled=True):
            return True
        mc.progressBar(bar, edit=True,
                       status=status,
                       progress=progress,
                       maxValue=max(int(maxValue), 1))
    except Exception:
        pass
    return False


def _progress_end(bar):
    if not bar:
        return
    try:
        CGMUI.doEndMayaProgressBar(bar)
    except Exception:
        pass

_l_applyModes = ('Replace', 'Merge', 'Insert')
_l_applyMapping = ('Auto', 'Name', 'Index',
                   'base', 'stripPrefix', 'metaData', 'mirrorIndex', 'mirrorIndex_ID')
_l_poseMapping = ('base', 'metaData', 'stripPrefix', 'mirrorIndex', 'mirrorIndex_ID')
_APPLY_LAYER_BASE = 'Base'
_APPLY_LAYER_NEW = 'New'
_l_applyLayerKind = ('Override', 'Additive')


def _option_menu_replace_items(menu, items, current=None):
    """Replace optionMenu entries. Uses MelOptionMenu.append (same as Mode/Mapping)."""
    name = str(menu)
    try:
        full = mc.control(name, q=True, fullPathName=True) or name
    except Exception:
        full = name
    try:
        old = mc.optionMenu(full, q=True, itemListLong=True) or []
    except Exception:
        old = []
    for it in old:
        try:
            mc.deleteUI(it)
        except Exception:
            pass
    for item in items:
        menu.append(item)
    if not items:
        return None
    pick = current if current in items else items[0]
    try:
        menu.setValue(pick, executeChangeCB=False)
    except Exception:
        try:
            mc.optionMenu(full, edit=True, value=pick)
        except Exception:
            pass
    return pick
_d_rangeAnn = {
    'slider': 'Push the slider range values to the int fields',
    'selected': 'Push the selected timeline range (if active)',
    'scene': 'Push scene range values to the int fields',
}


def empty_clip_dat():
    return {
        'version': _CLIP_VERSION,
        'sourceStart': None,
        'sourceEnd': None,
        'fps': None,
        'linearUnit': None,
        'angularUnit': None,
        'timeUnit': None,
        'user': None,
        'date': None,
        'scene': None,
        'includeStatic': False,
        'keyStartEnd': False,
        'relative': False,
        'namespace': '',
        'objects': [],
    }


def _node_namespace(node):
    """Maya namespace of a DAG node. Uses NAMES.get_short / get_base."""
    short = NAMES.get_short(node)
    base = NAMES.get_base(node)
    leaf = short.split('|')[-1]
    if leaf.endswith(base) and ':' in leaf:
        return leaf[:-len(base)].rstrip(':')
    return ''


def _long_without_ns(node):
    """DAG path with namespaces stripped from each token."""
    longName = NAMES.get_long(node)
    return '|'.join(p.split(':')[-1] for p in longName.split('|'))


def _object_identity(node):
    """Identity for Phase 4 matching. Names are stored without namespace."""
    short = NAMES.get_base(node)
    longName = _long_without_ns(node)
    uuid = ''
    try:
        uuid = mc.ls(node, uuid=True)[0]
    except Exception:
        pass
    cgmName = ''
    cgmType = ''
    cgmDirection = ''
    for attr in ('cgmName', 'cgmType', 'cgmDirection'):
        if not mc.attributeQuery(attr, node=node, exists=True):
            continue
        try:
            v = ATTR.get(node, attr)
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ''
            if v not in (None, False):
                if attr == 'cgmName':
                    cgmName = str(v)
                elif attr == 'cgmType':
                    cgmType = str(v)
                else:
                    cgmDirection = str(v)
        except Exception:
            pass
    rotateOrder = None
    if mc.attributeQuery('rotateOrder', node=node, exists=True):
        try:
            rotateOrder = ATTR.get(node, 'rotateOrder')
        except Exception:
            rotateOrder = None
    metaData = {}
    try:
        raw = r9Meta.MetaClass.getNodeConnectionMetaDataMap(node)
        if isinstance(raw, dict) and raw:
            metaData = raw
    except Exception:
        pass
    return {
        'shortName': short,
        'longName': longName,
        'cgmName': cgmName,
        'cgmType': cgmType,
        'cgmDirection': cgmDirection,
        'uuid': uuid,
        'rotateOrder': rotateOrder,
        'metaData': metaData,
        'channels': [],
    }


def _selected_transforms():
    sel = mc.ls(sl=True, type='transform', long=True) or []
    if not sel:
        raw = mc.ls(sl=True, objectsOnly=True, long=True) or []
        sel = mc.ls(raw, type='transform', long=True) or []
        if not sel and raw:
            sel = mc.listRelatives(raw, parent=True, type='transform', fullPath=True) or []
    seen = set()
    ordered = []
    for n in sel:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _normalize_nodes(nodes):
    """Unique transform long names from a node list (names or meta)."""
    ordered = []
    seen = set()
    for n in nodes or []:
        raw = n
        try:
            if hasattr(n, 'mNode'):
                raw = n.mNode
        except Exception:
            raw = n
        if not raw:
            continue
        hits = []
        try:
            hits = mc.ls(raw, type='transform', long=True) or []
        except Exception:
            hits = []
        if not hits:
            try:
                parent = mc.listRelatives(raw, parent=True, type='transform',
                                         fullPath=True) or []
                hits = parent
            except Exception:
                hits = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                ordered.append(h)
    return ordered


def _scene_node_by_name(obj, clip_ns=''):
    short = obj.get('shortName') or ''
    if short:
        short = short.split('|')[-1].split(':')[-1]
    longName = obj.get('longName') or ''
    if longName and mc.objExists(longName):
        return mc.ls(longName, long=True)[0]
    names = []
    for ns in str(clip_ns or obj.get('namespace') or '').split(';'):
        ns = ns.strip()
        if ns and short:
            names.append('{}:{}'.format(ns, short))
    if short:
        names.append(short)
    for name in names:
        if not name or not mc.objExists(name):
            continue
        hits = mc.ls(name, type='transform', long=True) or []
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            log.warning(log_msg('_scene_node_by_name',
                                'Ambiguous name {} ({} hits)'.format(name, len(hits))))
    return None


def _clip_src_token(obj, mapping, clip_ns=''):
    """Name string or live node for r9Core.matchNodeLists."""
    short = obj.get('shortName') or ''
    if mapping in ('metaData', 'mirrorIndex', 'mirrorIndex_ID'):
        live = _scene_node_by_name(obj, clip_ns)
        if live:
            return live
        return None
    return short or None


def _sel_long_set(sel):
    out = set()
    for n in sel or []:
        try:
            out.add(NAMES.get_long(n))
        except Exception:
            if n:
                out.add(n)
    return out


def _name_destinations(objects, namespace='', sel=None):
    """Global Name map. If sel is set, keep hits only when they are in that list."""
    allowed = _sel_long_set(sel) if sel else None
    dests = []
    for obj in objects:
        hit = _scene_node_by_name(obj, namespace)
        if hit and allowed is not None:
            try:
                hl = NAMES.get_long(hit)
            except Exception:
                hl = hit
            if hl not in allowed and hit not in allowed:
                hit = None
        dests.append(hit)
    return dests


def _pair_lookup(pairs):
    """matchNodeLists pair keys as given plus long/base aliases."""
    by_src = {}
    for a, b in pairs or []:
        by_src[a] = b
        try:
            by_src[NAMES.get_long(a)] = b
        except Exception:
            pass
        try:
            by_src[NAMES.get_base(a)] = b
        except Exception:
            pass
    return by_src


def _meta_map(node_or_dat):
    """Red9 {metaAttr, metaNodeID} or None."""
    if isinstance(node_or_dat, dict):
        raw = node_or_dat
    else:
        try:
            raw = r9Meta.MetaClass.getNodeConnectionMetaDataMap(node_or_dat)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    if not raw.get('metaAttr') and not raw.get('metaNodeID'):
        return None
    return raw


def _match_lists(src_tokens, dest_pool, mapping):
    if not src_tokens or not dest_pool:
        return []
    try:
        return r9Core.matchNodeLists(src_tokens, dest_pool, matchMethod=mapping) or []
    except Exception as err:
        log.warning(log_msg('_match_destinations', '{} | {}'.format(mapping, err)))
        return []


def _fill_from_pairs(dests, tokens, idx_for, dest_pool, mapping):
    """Write matchNodeLists hits into dests; return remaining dests."""
    pairs = _match_lists(tokens, dest_pool, mapping)
    by_src = _pair_lookup(pairs)
    used = set()
    for tok, i in zip(tokens, idx_for):
        hit = by_src.get(tok)
        if not hit:
            try:
                hit = by_src.get(NAMES.get_long(tok))
            except Exception:
                hit = None
        if not hit:
            continue
        try:
            hit = NAMES.get_long(hit)
        except Exception:
            pass
        dests[i] = hit
        used.add(hit)
    if not used:
        return dest_pool
    left = []
    for d in dest_pool:
        try:
            dl = NAMES.get_long(d)
        except Exception:
            dl = d
        if d in used or dl in used:
            continue
        left.append(d)
    return left


def _match_meta_destinations(objects, dest_pool, clip_ns=''):
    """PoseSaver-style metaData: stored map, live wires, then stripPrefix."""
    dests = [None] * len(objects)
    remaining = list(dest_pool)

    dest_maps = []
    for d in remaining:
        dest_maps.append((d, _meta_map(d)))
    for i, obj in enumerate(objects):
        stored = _meta_map(obj.get('metaData'))
        if not stored:
            continue
        for j, (d, dmap) in enumerate(dest_maps):
            if dmap and dmap == stored:
                dests[i] = d
                dest_maps.pop(j)
                break
    remaining = [d for d, _m in dest_maps]

    need = [i for i, d in enumerate(dests) if d is None]
    tokens = []
    idx_for = []
    for i in need:
        tok = _clip_src_token(objects[i], 'metaData', clip_ns)
        if tok:
            tokens.append(tok)
            idx_for.append(i)
    if tokens:
        remaining = _fill_from_pairs(dests, tokens, idx_for, remaining, 'metaData')

    need = [i for i, d in enumerate(dests) if d is None]
    tokens = []
    idx_for = []
    for i in need:
        n = objects[i].get('shortName') or ''
        if n:
            tokens.append(n)
            idx_for.append(i)
    if tokens:
        remaining = _fill_from_pairs(dests, tokens, idx_for, remaining, 'stripPrefix')

    nHit = sum(1 for d in dests if d)
    if nHit < len(objects):
        log.warning(log_msg('_match_destinations',
                            'metaData {}/{} matched (stored wire, live wire, stripPrefix)'.format(
                                nHit, len(objects))))
    return dests


def _match_mirror_id_destinations(objects, dest_pool, clip_ns=''):
    """PoseSaver mirrorIndex_ID: match live getMirrorIndex (slot only, not side)."""
    import Red9.core.Red9_AnimationUtils as r9Anim
    get_id = r9Anim.MirrorHierarchy().getMirrorIndex
    dests = [None] * len(objects)
    remaining = []
    for d in dest_pool:
        try:
            remaining.append((d, get_id(d)))
        except Exception:
            remaining.append((d, None))
    for i, obj in enumerate(objects):
        tok = _clip_src_token(obj, 'mirrorIndex_ID', clip_ns)
        if not tok:
            continue
        try:
            src_id = get_id(tok)
        except Exception:
            src_id = None
        if src_id is None:
            continue
        for j, (d, did) in enumerate(remaining):
            if did is None or did != src_id:
                continue
            dests[i] = d
            remaining.pop(j)
            break
    nHit = sum(1 for d in dests if d)
    if nHit < len(objects):
        log.warning(log_msg('_match_destinations',
                            'mirrorIndex_ID {}/{} matched'.format(nHit, len(objects))))
    return dests


def _match_pose_destinations(objects, mapping, dest_pool, clip_ns=''):
    if mapping == 'metaData':
        return _match_meta_destinations(objects, dest_pool, clip_ns)
    if mapping == 'mirrorIndex_ID':
        return _match_mirror_id_destinations(objects, dest_pool, clip_ns)
    src = [_clip_src_token(obj, mapping, clip_ns) for obj in objects]
    valid = [(i, s) for i, s in enumerate(src) if s]
    if not valid:
        log.warning(log_msg('_match_destinations',
                            '{} needs captured node names (or live nodes for {})'.format(
                                mapping, mapping)))
        return [None] * len(objects)
    dests = [None] * len(objects)
    tokens = [s for _i, s in valid]
    idx_for = [i for i, _s in valid]
    _fill_from_pairs(dests, tokens, idx_for, dest_pool, mapping)
    return dests


def _match_destinations(objects, mapping='Name', namespace='', dests=None):
    mapping = mapping or 'Name'
    if dests is not None:
        sel = _normalize_nodes(dests)
        if not sel:
            return [None] * len(objects or [])
    else:
        sel = _selected_transforms()
        if not sel:
            return _name_destinations(objects, namespace)
    if mapping == 'Index':
        if len(sel) < len(objects):
            log.warning(log_msg('_match_destinations',
                                'Index mapping needs {} selected, got {}'.format(
                                    len(objects), len(sel))))
        dests = []
        for i, obj in enumerate(objects):
            dests.append(sel[i] if i < len(sel) else None)
        return dests
    if mapping == 'Auto' and len(sel) == len(objects):
        return list(sel)
    if mapping in _l_poseMapping:
        return _match_pose_destinations(objects, mapping, sel, namespace)
    return _name_destinations(objects, namespace, sel=sel)


def _preview_mapping(objects, mapping='Name', namespace='', dests=None):
    """Clip shortName → dest shortName (or None) for the current mapping. Does not paste."""
    dests = _match_destinations(objects, mapping, namespace, dests=dests) or []
    pairs = []
    nHit = 0
    for obj, dest in zip(objects, dests):
        src = obj.get('shortName') or obj.get('longName') or '--'
        dst = None
        if dest and mc.objExists(dest):
            dst = NAMES.get_base(dest)
            nHit += 1
        pairs.append((src, dst))
    return pairs, nHit


class AnimClip(CGMDAT.data):
    _ext = 'cgmAnimClip'
    _dataFormat = 'json'
    _startDir = ['cgmDat', 'anim']

    def __init__(self, filepath=None, dat=None, **kws):
        kws.setdefault('dataFormat', self._dataFormat)
        super().__init__(filepath, **kws)
        self.structureMode = 'workspace'
        if dat:
            self.dat = dat

    def from_curve(self, curve):
        """Phase 1 fixture: wrap one curve dict in a clip. No matching, no range slice."""
        _str_func = 'AnimClip.from_curve'
        log.debug(log_start(_str_func))
        snap = ANIMCLIPCURVE.snapshot(curve)
        clip = empty_clip_dat()
        clip['scene'] = mc.file(q=True, sn=True) or ''
        clip['user'] = getpass.getuser()
        clip['date'] = time.strftime('%Y-%m-%d %H:%M')
        clip['fps'] = mc.currentUnit(q=True, time=True)
        clip['timeUnit'] = clip['fps']
        clip['linearUnit'] = mc.currentUnit(q=True, linear=True)
        clip['angularUnit'] = mc.currentUnit(q=True, angle=True)
        clip['objects'] = [{
            'shortName': snap.get('nodeName') or '',
            'longName': '',
            'cgmName': '',
            'cgmType': '',
            'cgmDirection': '',
            'uuid': '',
            'rotateOrder': None,
            'metaData': {},
            'channels': [{
                'attr': '',
                'plug': '',
                'curve': snap,
            }],
        }]
        self.dat = clip
        log.info(log_msg(_str_func, '{} | {} keys'.format(
            snap.get('curveType'), len(snap.get('keys') or []))))
        return self.dat

    def get(self, start=None, end=None, includeStatic=False, keyStartEnd=False,
            nodes=None):
        _str_func = 'AnimClip.get'
        log.debug(log_start(_str_func))
        if nodes is None:
            sel = _selected_transforms()
        else:
            sel = _normalize_nodes(nodes)
        clip = empty_clip_dat()
        clip['scene'] = mc.file(q=True, sn=True) or ''
        clip['user'] = getpass.getuser()
        clip['date'] = time.strftime('%Y-%m-%d %H:%M')
        clip['fps'] = mc.currentUnit(q=True, time=True)
        clip['timeUnit'] = clip['fps']
        clip['linearUnit'] = mc.currentUnit(q=True, linear=True)
        clip['angularUnit'] = mc.currentUnit(q=True, angle=True)
        if start is None:
            start = mc.playbackOptions(q=True, min=True)
        if end is None:
            end = mc.playbackOptions(q=True, max=True)
        clip['sourceStart'] = start
        clip['sourceEnd'] = end
        clip['includeStatic'] = bool(includeStatic)
        clip['keyStartEnd'] = bool(keyStartEnd)
        clip['relative'] = True
        nss = []
        for n in sel:
            ns = _node_namespace(n)
            if ns and ns not in nss:
                nss.append(ns)
        clip['namespace'] = nss[0] if len(nss) == 1 else ';'.join(nss)

        objects = []
        nCurves = 0
        nSel = len(sel)
        _pb = _progress_begin(nSel, 'cgmAnimClip | Capture...') if nSel else None
        try:
            for i, n in enumerate(sel):
                ident = _object_identity(n)
                if _progress_tick(_pb, i + 1, nSel,
                                  'cgmAnimClip | Capture {0}/{1} | {2}'.format(
                                      i + 1, nSel, ident.get('shortName') or n)):
                    log.warning(log_msg(_str_func, 'Capture cancelled'))
                    break
                chans = []
                for attr in ATTR.get_keyed(n) or []:
                    driver = ATTR.get_driver(n, attr, getNode=True, skipConversionNodes=True)
                    if not driver:
                        continue
                    if not ANIMCLIPCURVE.is_time_curve(driver):
                        log.warning(log_msg(_str_func,
                                            'Skip {}.{} | driver is {} (need time-based animCurve)'.format(
                                                ident['shortName'], attr, mc.nodeType(driver))))
                        continue
                    dat = ANIMCLIPCURVE.snapshot(driver)
                    if keyStartEnd:
                        dat = ANIMCLIPCURVE.ensure_boundary_keys(dat, driver, start, end)
                    dat = ANIMCLIPCURVE.slice_keys(dat, start, end)
                    dat = ANIMCLIPCURVE.offset_keys(dat, start)
                    if not dat or not dat.get('keys'):
                        continue
                    chans.append({
                        'attr': attr,
                        'plug': '{}.{}'.format(ident['shortName'], attr),
                        'curve': dat,
                    })
                ident['channels'] = chans
                nCurves += len(chans)
                objects.append(ident)
        finally:
            _progress_end(_pb)
        clip['objects'] = objects
        self.dat = clip

        extra = ''
        if includeStatic:
            extra += ' | includeStatic'
        if keyStartEnd:
            extra += ' | keyStartEnd'
        if nCurves:
            log.info(log_msg(_str_func, '{} objects | {} curves | {}-{}{}'.format(
                len(sel), nCurves, start, end, extra)))
        else:
            log.info(log_msg(_str_func,
                             '{} objects | 0 curves | {}-{}{} (no time-based keys in range)'.format(
                                 len(sel), start, end, extra)))
        return self.dat

    def apply(self, atFrame=None, mode='Replace', mapping='Name', layer=None,
              layerOverride=None, dests=None):
        """Paste clip keys onto matched dest.attr at atFrame. Replace/Merge/Insert. Auto/Name/Index plus Pose match methods. Dest list is selection, or Name map if nothing is selected, unless dests is a list (empty list = no dests). layer is Base or a Maya animLayer (created if missing; dests are added to the layer, then keyed). layerOverride True=Override / False=Additive is applied only when the layer is created."""
        _str_func = 'AnimClip.apply'
        log.debug(log_start(_str_func))
        clip = self.dat or {}
        objects = clip.get('objects') or []
        if not objects:
            log.warning(log_msg(_str_func, 'No clip objects to paste'))
            return 0
        mode = mode or 'Replace'
        if layer and str(layer).strip().lower() == 'new':
            log.warning(log_msg(_str_func, 'Layer New is UI-only; pass a layer name'))
            return 0
        if atFrame is None:
            _slider = SEARCH.get_time('slider') or [1, 24]
            atFrame = _slider[0]
        timeOffset = float(atFrame) if clip.get('relative') else 0.0
        dests = _match_destinations(objects, mapping, clip.get('namespace') or '',
                                   dests=dests)
        layer_node = ANIMCLIPCURVE.ensure_anim_layer(layer, override=layerOverride)
        if layer_node:
            dest_ok = []
            for d in dests:
                if d and mc.objExists(d) and d not in dest_ok:
                    dest_ok.append(d)
            ANIMCLIPCURVE.anim_layer_add_nodes(layer_node, dest_ok)
            for d in dest_ok:
                if not SEARCH.animLayer_contains(layer_node, d):
                    log.warning(log_msg(_str_func,
                                        'Not on animLayer {} | {}'.format(layer_node, d)))
        nApplied = 0
        nTotal = _clip_curve_count(clip)
        _pb = _progress_begin(nTotal, 'cgmAnimClip | Paste...') if nTotal else None
        iStep = 0
        try:
            for obj, dest in zip(objects, dests):
                name = obj.get('shortName') or obj.get('longName') or '--'
                chans = obj.get('channels') or []
                destShort = NAMES.get_base(dest) if dest else name
                if not dest or not mc.objExists(dest):
                    log.warning(log_msg(_str_func, 'No match | {}'.format(name)))
                    iStep += len(chans)
                    if _progress_tick(_pb, iStep, nTotal,
                                      'cgmAnimClip | Paste {0}/{1} | skip {2}'.format(
                                          iStep, nTotal, name)):
                        log.warning(log_msg(_str_func, 'Paste cancelled'))
                        break
                    continue
                for ch in chans:
                    iStep += 1
                    attr = ch.get('attr')
                    curveDat = ch.get('curve')
                    if _progress_tick(_pb, iStep, nTotal,
                                      'cgmAnimClip | Paste {0}/{1} | {2}.{3}'.format(
                                          iStep, nTotal, destShort, attr or '--')):
                        log.warning(log_msg(_str_func, 'Paste cancelled'))
                        return nApplied
                    if not attr or not curveDat:
                        continue
                    if not mc.attributeQuery(attr, node=dest, exists=True):
                        log.warning(log_msg(_str_func, 'Missing attr | {}.{}'.format(dest, attr)))
                        continue
                    driver = ATTR.get_driver(dest, attr, getNode=True, skipConversionNodes=True)
                    if driver and not ANIMCLIPCURVE.is_time_curve(driver):
                        ntype = ''
                        try:
                            ntype = mc.nodeType(driver) or ''
                        except Exception:
                            pass
                        allow_blend = bool(layer_node) and ntype.startswith('animBlend')
                        if not allow_blend:
                            log.warning(log_msg(_str_func,
                                                'Skip {}.{} | driver is {}'.format(
                                                    dest, attr, ntype or driver)))
                            continue
                    try:
                        ANIMCLIPCURVE.apply_to_plug(curveDat, dest, attr,
                                                    timeOffset=timeOffset, mode=mode,
                                                    animLayer=layer_node)
                        nApplied += 1
                    except Exception as err:
                        log.warning(log_msg(_str_func, '{}.{} | {}'.format(dest, attr, err)))
        finally:
            _progress_end(_pb)
        extra = ' | {}'.format(layer_node) if layer_node else ''
        log.info(log_msg(_str_func, '{} curves | {} at {} | {}{}'.format(
            nApplied, mode, atFrame, mapping, extra)))
        return nApplied


class ui(CGMDAT.ui):
    USE_Template = 'cgmUITemplate'
    _toolname = 'cgmAnimClip'
    TOOLNAME = 'ui_cgmAnimClip'
    WINDOW_NAME = '{}UI'.format(TOOLNAME)
    WINDOW_TITLE = 'AnimClip | {0}'.format(__version__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = False
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True
    DEFAULT_SIZE = 560, 700

    _datClass = AnimClip

    def reload(self):
        reload_dependencies()
        cgmGEN._reloadMod(__import__(__name__))
        super().reload()

    def insert_init(self, *args, **kws):
        CGMDAT.ui.insert_init(self, *args, **kws)
        _def = self.__class__.DEFAULT_SIZE
        self.DEFAULT_SIZE = _def
        _win = self.__class__.WINDOW_NAME
        try:
            if mc.windowPref(_win, exists=True):
                w = mc.windowPref(_win, q=True, width=True)
                h = mc.windowPref(_win, q=True, height=True)
                if w >= _def[0] and h >= _def[1]:
                    self.DEFAULT_SIZE = (w, h)
        except Exception:
            pass
        self.create_guiOptionVar('animClip_includeStatic', defaultValue=0)
        self.create_guiOptionVar('animClip_keyStartEnd', defaultValue=0)
        self.create_guiOptionVar('animClip_captureFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_clipFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_contentsFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_applyFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_applyMode', defaultValue='Replace')
        self.var_animClip_applyMode.setType('string')
        self.create_guiOptionVar('animClip_applyMapping', defaultValue='Auto')
        self.var_animClip_applyMapping.setType('string')
        self.create_guiOptionVar('animClip_applyLayer', defaultValue=_APPLY_LAYER_BASE)
        self.var_animClip_applyLayer.setType('string')
        self.create_guiOptionVar('animClip_applyLayerKind', defaultValue='Override')
        self.var_animClip_applyLayerKind.setType('string')
        self._mapPreview = None

    def post_init(self, *args, **kws):
        CGMDAT.ui.post_init(self, *args, **kws)
        self.uiFunc_capture_refresh_count()

    def _clip_capture_nodes(self):
        return _selected_transforms()

    def _clip_apply_dests(self):
        """None = default matching (sel or global Name). List = dest pool."""
        return None

    def _clip_source_label(self):
        return 'From the current Maya selection.'

    def _clip_empty_capture_msg(self):
        return 'Select controls to capture'

    def _clip_empty_apply_msg(self):
        return 'No dests to paste'

    def uiBuild_pinned_chrome(self, parent):
        """Optional widget pinned under the Dat file bar. None = no extra chrome."""
        return None

    def _ui_kv_row(self, parent, label, value):
        _row = mUI.MelHSingleStretchLayout(parent, padding=5)
        mUI.MelSpacer(_row, w=10)
        mUI.MelLabel(_row, label='{}:'.format(label))
        _row.setStretchWidget(mUI.MelSeparator(_row))
        if value in (None, ''):
            _s = '--'
        else:
            _s = str(value)
            if label in ('scene',) and len(_s) > 40:
                _s = CORESTRINGS.short(_s, max=40, start=8)
        mUI.MelLabel(_row, label=_s)
        mUI.MelSpacer(_row, w=10)
        _row.layout()

    def uiBuild_capture(self, parent):
        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=10)
        mUI.MelLabel(_row, label=self._clip_source_label())
        _row.setStretchWidget(mUI.MelSeparator(_row))
        self.uiLabel_captureCount = mUI.MelLabel(_row, label='0 controls')
        mUI.MelSpacer(_row, w=10)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l='Set Timeline Range')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        _slider = SEARCH.get_time('slider') or [1, 24]
        mUI.MelLabel(_row, l='Start')
        self.uiIF_captureStart = mUI.MelIntField(_row, width=40, value=int(_slider[0]))
        mUI.MelLabel(_row, l='End')
        self.uiIF_captureEnd = mUI.MelIntField(_row, width=40, value=int(_slider[1]))
        CGMUI.add_Button(_row, 'Slider',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange, 'slider'),
                         _d_rangeAnn['slider'])
        CGMUI.add_Button(_row, 'Sel',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange, 'selected'),
                         _d_rangeAnn['selected'])
        CGMUI.add_Button(_row, 'Scene',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange, 'scene'),
                         _d_rangeAnn['scene'])
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=10)
        self.uiCB_includeStatic = mUI.MelCheckBox(_row,
                                                  label='Include static attributes',
                                                  value=self.var_animClip_includeStatic.value,
                                                  onCommand=lambda *a: self.var_animClip_includeStatic.setValue(1),
                                                  offCommand=lambda *a: self.var_animClip_includeStatic.setValue(0))
        self.uiCB_keyStartEnd = mUI.MelCheckBox(_row,
                                                label='Key start/end',
                                                ann='If Start or End is unkeyed, sample the curve there so the clip holds those values. Skips non-constant pre/post infinity regions.',
                                                value=self.var_animClip_keyStartEnd.value,
                                                onCommand=lambda *a: self.var_animClip_keyStartEnd.setValue(1),
                                                offCommand=lambda *a: self.var_animClip_keyStartEnd.setValue(0))
        _row.setStretchWidget(mUI.MelSeparator(_row))
        mUI.MelSpacer(_row, w=10)
        _row.layout()

        mc.button(parent=parent,
                  l='Capture Animation',
                  ut='cgmUITemplate',
                  h=30,
                  ann='Capture time-based curves on the selection over Start/End. Skips layers and blends.',
                  c=lambda *a: mc.evalDeferred(cgmGEN.Callback(self.uiFunc_capture)))

    def uiFunc_capture_refresh_count(self):
        if not getattr(self, 'uiLabel_captureCount', None):
            return
        n = len(self._clip_capture_nodes() or [])
        self.uiLabel_captureCount(edit=True, label='{} controls'.format(n))

    def uiFunc_updateTimeRange(self, mode='slider'):
        if not getattr(self, 'uiIF_captureStart', None):
            return
        _range = SEARCH.get_time(mode)
        if _range:
            self.uiIF_captureStart(edit=True, value=int(_range[0]))
            self.uiIF_captureEnd(edit=True, value=int(_range[1]))

    def uiFunc_capture(self):
        _str_func = 'uiFunc_capture[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        _sel = mc.ls(sl=True)
        nodes = self._clip_capture_nodes()
        if not nodes:
            return log.warning(self._clip_empty_capture_msg())
        start = self.uiIF_captureStart.getValue()
        end = self.uiIF_captureEnd.getValue()
        includeStatic = bool(self.uiCB_includeStatic.getValue())
        keyStartEnd = bool(self.uiCB_keyStartEnd.getValue())
        self.uiDat.get(start=start, end=end, includeStatic=includeStatic,
                       keyStartEnd=keyStartEnd, nodes=nodes)
        nObj = len(self.uiDat.dat.get('objects') or [])
        nCurves = _clip_curve_count(self.uiDat.dat)
        self.uiStatus_refresh()
        self.uiFunc_status('Captured {} objects | {} curves  {}-{}'.format(
            nObj, nCurves, int(start), int(end)))
        if _sel:
            mc.select(_sel)

    def uiBuild_apply(self, parent):
        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l='Paste at frame')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        _slider = SEARCH.get_time('slider') or [1, 24]
        self.uiIF_applyFrame = mUI.MelIntField(_row, width=40, value=int(_slider[0]))

        mUI.MelLabel(_row, l='Mode')
        self.uiOM_applyMode = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate',
                                                ann='Replace cuts keys in the paste window. Merge adds. Insert shifts later keys by the clip span.')
        for item in _l_applyModes:
            self.uiOM_applyMode.append(item)
        _mode = self.var_animClip_applyMode.value
        if _mode in _l_applyModes:
            self.uiOM_applyMode.setValue(_mode)
        self.uiOM_applyMode(edit=True,
                            cc=lambda *a: self.var_animClip_applyMode.setValue(
                                self.uiOM_applyMode.getValue()))

        mUI.MelLabel(_row, l='Mapping')
        self.uiOM_applyMapping = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate',
                                                   ann='Dest list is the Maya selection. If nothing is selected, names are resolved in the scene. Index: selection order. Auto: Index when counts match. Other items are PoseManager match methods.')
        for item in _l_applyMapping:
            self.uiOM_applyMapping.append(item)
        _map = self.var_animClip_applyMapping.value
        if _map == 'Auto / Pose Match':
            _map = 'Auto'
            self.var_animClip_applyMapping.setValue(_map)
        if _map in _l_applyMapping:
            self.uiOM_applyMapping.setValue(_map)
        self.uiOM_applyMapping(edit=True,
                               cc=lambda *a: self.var_animClip_applyMapping.setValue(
                                   self.uiOM_applyMapping.getValue()))

        CGMUI.add_Button(_row, 'Check Mapping',
                         cgmGEN.Callback(self.uiFunc_check_mapping),
                         'Preview clip → dest for the current Mapping. Does not paste.')
        CGMUI.add_Button(_row, 'Paste Clip',
                         cgmGEN.Callback(self.uiFunc_apply),
                         'Apply the current clip at Paste at frame onto Base or the selected Layer. Replace/Merge/Insert.')
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _rowL = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_rowL, w=5)
        mUI.MelLabel(_rowL, l='Layer')
        self.uiOM_applyLayer = mUI.MelOptionMenu(_rowL, useTemplate='cgmUITemplate',
                                                 ann='Paste onto Base, a scene Animation Layer, or New (prompt for a name). Animation Layer Editor — not Display Layers.')
        _rowL.setStretchWidget(self.uiOM_applyLayer)
        self.uiOM_applyLayerKind = mUI.MelOptionMenu(_rowL, useTemplate='cgmUITemplate',
                                                    ann='When a new animation layer is created (New, or a missing name), make it Override or Additive. Existing layers keep their mode.')
        for item in _l_applyLayerKind:
            self.uiOM_applyLayerKind.append(item)
        _kind = self.var_animClip_applyLayerKind.value
        if _kind in _l_applyLayerKind:
            self.uiOM_applyLayerKind.setValue(_kind)
        self.uiOM_applyLayerKind(edit=True,
                                 cc=lambda *a: self.var_animClip_applyLayerKind.setValue(
                                     self.uiOM_applyLayerKind.getValue()))
        CGMUI.add_Button(_rowL, 'Refresh',
                         cgmGEN.Callback(self.uiRefresh_apply_layer),
                         'Rebuild the Layer list from scene animation layers.')
        mUI.MelSpacer(_rowL, w=5)
        _rowL.layout()
        self.uiRefresh_apply_layer()
        try:
            nItem = mc.optionMenu(str(self.uiOM_applyLayer), q=True, numberOfItems=True) or 0
        except Exception:
            nItem = 0
        if nItem < 1:
            self.uiOM_applyLayer.append(_APPLY_LAYER_BASE)
        self.uiOM_applyLayer(edit=True,
                             cc=lambda *a: self.uiFunc_apply_layer_changed())

    def uiRefresh_apply_layer(self):
        """Rebuild Layer menu: Base, New, plus scene animLayers (not BaseAnimation)."""
        menu = getattr(self, 'uiOM_applyLayer', None)
        if not menu:
            return
        cur = _APPLY_LAYER_BASE
        if getattr(self, 'var_animClip_applyLayer', None):
            cur = self.var_animClip_applyLayer.value or cur
        try:
            shown = menu.getValue()
            if shown and shown != _APPLY_LAYER_NEW:
                cur = shown
        except Exception:
            pass
        if cur == _APPLY_LAYER_NEW:
            cur = _APPLY_LAYER_BASE
        items = [_APPLY_LAYER_BASE, _APPLY_LAYER_NEW]
        try:
            items.extend(SEARCH.animLayers_get(includeBase=False) or [])
        except Exception:
            pass
        log.debug(log_msg('uiRefresh_apply_layer', ' | '.join(items)))
        pick = _option_menu_replace_items(menu, items, cur)
        if getattr(self, 'var_animClip_applyLayer', None) and pick and pick != _APPLY_LAYER_NEW:
            self.var_animClip_applyLayer.setValue(pick)

    def uiFunc_apply_layer_changed(self):
        menu = getattr(self, 'uiOM_applyLayer', None)
        if not menu:
            return
        val = menu.getValue()
        if val == _APPLY_LAYER_NEW:
            self.uiFunc_new_apply_layer()
            self.uiRefresh_apply_layer()
            return
        if getattr(self, 'var_animClip_applyLayer', None) and val:
            self.var_animClip_applyLayer.setValue(val)

    def uiFunc_new_apply_layer(self):
        """Prompt for a name, create an Override or Additive animLayer, select it."""
        _str_func = 'uiFunc_new_apply_layer'
        kind = 'Override'
        if getattr(self, 'uiOM_applyLayerKind', None):
            kind = self.uiOM_applyLayerKind.getValue() or kind
        elif getattr(self, 'var_animClip_applyLayerKind', None):
            kind = self.var_animClip_applyLayerKind.value or kind
        override = (kind == 'Override')
        default = (self.uiDat.dat or {}).get('name') or 'animClip'
        default = CORESTRINGS.stripInvalidChars(default) or 'animClip'
        result = mc.promptDialog(title='New Animation Layer',
                                 message='Layer name:',
                                 text=default,
                                 button=['OK', 'Cancel'],
                                 defaultButton='OK',
                                 cancelButton='Cancel',
                                 dismissString='Cancel')
        if result != 'OK':
            return None
        name = CORESTRINGS.stripInvalidChars(
            mc.promptDialog(query=True, text=True) or '') or ''
        if not name:
            log.warning(log_msg(_str_func, 'No layer name'))
            return None
        if name.lower() in ('new', 'base', 'baseanimation'):
            log.warning(log_msg(_str_func, 'Invalid layer name | {}'.format(name)))
            return None
        existed = False
        try:
            existed = mc.objExists(name) and mc.nodeType(name) == 'animLayer'
        except Exception:
            existed = False
        layer = ANIMCLIPCURVE.ensure_anim_layer(name, override=override)
        if not layer:
            log.warning(log_msg(_str_func, 'Could not create animLayer | {}'.format(name)))
            return None
        if existed:
            log.info(log_msg(_str_func, 'Using existing animLayer | {}'.format(layer)))
        else:
            log.info(log_msg(_str_func, 'Created animLayer {} | {}'.format(layer, kind)))
        if getattr(self, 'var_animClip_applyLayer', None):
            self.var_animClip_applyLayer.setValue(layer)
        return layer

    def _apply_layer_override_flag(self):
        kind = 'Override'
        if getattr(self, 'uiOM_applyLayerKind', None):
            kind = self.uiOM_applyLayerKind.getValue() or kind
        elif getattr(self, 'var_animClip_applyLayerKind', None):
            kind = self.var_animClip_applyLayerKind.value or kind
        return kind == 'Override'

    def uiFunc_apply_frame_expand(self):
        self.var_animClip_applyFrameCollapse.setValue(0)
        self.uiRefresh_apply_layer()

    def uiFunc_apply(self):
        _str_func = 'uiFunc_apply[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        if not (self.uiDat.dat and (self.uiDat.dat.get('objects') or [])):
            return log.warning('No clip to paste')
        layer = self.uiOM_applyLayer.getValue()
        if layer == _APPLY_LAYER_NEW:
            created = self.uiFunc_new_apply_layer()
            if not created:
                return log.warning('Paste cancelled | no new layer')
            layer = created
        self.uiRefresh_apply_layer()
        at = self.uiIF_applyFrame.getValue()
        mode = self.uiOM_applyMode.getValue()
        mapping = self.uiOM_applyMapping.getValue()
        try:
            shown = self.uiOM_applyLayer.getValue()
            if shown and shown != _APPLY_LAYER_NEW:
                layer = shown
        except Exception:
            pass
        dests = self._clip_apply_dests()
        if dests is not None and not dests:
            return log.warning(self._clip_empty_apply_msg())
        n = self.uiDat.apply(atFrame=at, mode=mode, mapping=mapping, layer=layer,
                             layerOverride=self._apply_layer_override_flag(),
                             dests=dests)
        self.uiFunc_status('Pasted {} curves at {}  {} | {} | {}'.format(
            n, int(at), mode, mapping, layer))

    def uiFunc_check_mapping(self):
        _str_func = 'uiFunc_check_mapping[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        objects = (self.uiDat.dat or {}).get('objects') or []
        if not objects:
            return log.warning('No clip to map')
        self.uiRefresh_apply_layer()
        mapping = self.uiOM_applyMapping.getValue()
        ns = (self.uiDat.dat or {}).get('namespace') or ''
        dests = self._clip_apply_dests()
        if dests is not None and not dests:
            return log.warning(self._clip_empty_apply_msg())
        _sel = mc.ls(sl=True)
        pairs, nHit = _preview_mapping(objects, mapping, ns, dests=dests)
        nMiss = len(objects) - nHit
        self._mapPreview = [dst for _src, dst in pairs]
        log.info(log_msg(_str_func, '{} | {}/{} matched | {} missed'.format(
            mapping, nHit, len(objects), nMiss)))
        for src, dst in pairs:
            log.info(log_msg(_str_func, '{}  →  {}'.format(src, dst or '--')))
        self.uiUpdate_clip()
        self.uiFunc_status('{}  {}/{} matched  |  {} missed'.format(
            mapping, nHit, len(objects), nMiss))
        if _sel:
            mc.select(_sel)

    def uiFunc_set_slider_to_clip(self):
        _str_func = 'uiFunc_set_slider_to_clip[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        d = (self.uiDat.dat if self.uiDat else None) or {}
        if not (d and self.uiDat.checkState()):
            return log.warning('No clip')
        paste = 1
        if getattr(self, 'uiIF_applyFrame', None):
            paste = int(self.uiIF_applyFrame.getValue())
        dur = _clip_duration(d)
        start = float(paste)
        end = float(paste + dur) if dur else float(paste)
        td = SEARCH.get_timeline_dict()
        kw = {'minTime': start, 'maxTime': end}
        if start < td['sceneStart']:
            kw['animationStartTime'] = start
        if end > td['sceneEnd']:
            kw['animationEndTime'] = end
        mc.playbackOptions(**kw)
        self.uiFunc_status('Slider {}-{}'.format(int(start), int(end)))

    def uiFunc_status(self, msg=''):
        if getattr(self, 'uiLabel_status', None):
            self.uiLabel_status(edit=True, label=msg or '')

    def uiUpdate_clip(self):
        _str_func = 'uiUpdate_clip[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        if not getattr(self, 'uiClip_header', None):
            return

        self.uiClip_header.clear()
        if getattr(self, 'uiFrame_data', None):
            try:
                mc.deleteUI(self.uiFrame_data)
            except Exception:
                try:
                    self.uiFrame_data.clear()
                except Exception:
                    pass
        _parent = getattr(self, 'uiFrame_contents', None) or self.uiSection_clip
        self.uiFrame_data = mUI.MelColumnLayout(_parent, useTemplate='cgmUIHeaderTemplate', adj=True)
        d = (self.uiDat.dat if self.uiDat else None) or {}
        objects = d.get('objects') or []
        hasClip = bool(d) and self.uiDat.checkState()
        if getattr(self, 'uiFrame_contents', None):
            try:
                self.uiFrame_contents(edit=True,
                                      label='CLIP CONTENTS  ({})'.format(len(objects)))
            except Exception:
                pass

        _row = mUI.MelHSingleStretchLayout(self.uiClip_header, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        if hasClip:
            nFrames = _clip_frame_count(d)
            frames = '{} frames'.format(nFrames) if nFrames is not None else '-- frames'
            _ns = d.get('namespace') or ''
            if _ns:
                _sum = '{}  |  {}  |  ns {}  |  {} controls  |  {} curves'.format(
                    _clip_name(self.uiDat, self._loadedFile),
                    frames,
                    _ns,
                    len(objects),
                    _clip_curve_count(d))
            else:
                _sum = '{}  |  {}  |  {} controls  |  {} curves'.format(
                    _clip_name(self.uiDat, self._loadedFile),
                    frames,
                    len(objects),
                    _clip_curve_count(d))
        else:
            _sum = 'No clip'
        mUI.MelLabel(_row, label=_sum, align='left')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        if hasClip:
            mUI.MelButton(_row, label='Set Slider', ut='cgmUITemplate',
                          ann='Set the time slider to Paste at frame plus clip duration (single frame if duration is 0)',
                          c=lambda *a: self.uiFunc_set_slider_to_clip())
        mUI.MelButton(_row, label='Clear', ut='cgmUITemplate',
                      ann='Clear the current clip from the UI (does not delete the file)',
                      c=lambda *a: self.uiFunc_clip_clear())
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        if not objects:
            mUI.MelLabel(self.uiFrame_data,
                         label='None -- Capture Animation from selection',
                         h=16, align='center', ut='cgmUISubTemplate')
            return

        for i, obj in enumerate(objects):
            name = obj.get('shortName') or obj.get('longName') or '--'
            nCurves = len(obj.get('channels') or [])
            _preview = getattr(self, '_mapPreview', None)
            if _preview is not None and i < len(_preview):
                _dst = _preview[i]
                if _dst:
                    _label = '{}  →  {}          {} curves'.format(
                        name, _dst, nCurves)
                else:
                    _label = '[x] {}  →  --          {} curves'.format(
                        name, nCurves)
            else:
                _label = '{}          {} curves'.format(name, nCurves)
            if MATH.is_even(i):
                _header = CGMUI.guiButtonColor
            else:
                _header = CGMUI.guiBackgroundColor
            _bgc = CGMUI.guiBackgroundColor
            _f = mUI.MelFrameLayout(self.uiFrame_data,
                                    label=_label,
                                    collapsable=True,
                                    collapse=True,
                                    enable=True,
                                    bgc=_header)
            _col = mUI.MelColumnLayout(_f, bgc=_bgc, adj=True)
            channels = obj.get('channels') or []
            if not channels:
                mUI.MelLabel(_col, label='No curves in range',
                             h=16, align='center')
                self._ui_kv_row(_col, 'cgmName', obj.get('cgmName'))
                self._ui_kv_row(_col, 'cgmType', obj.get('cgmType'))
            else:
                for ch in channels:
                    attr = ch.get('attr') or ch.get('plug') or '--'
                    nKeys = len((ch.get('curve') or {}).get('keys') or [])
                    _r = mUI.MelHSingleStretchLayout(_col, bgc=_bgc, padding=5)
                    mUI.MelSpacer(_r, w=15)
                    mUI.MelLabel(_r, label=attr)
                    _r.setStretchWidget(mUI.MelSeparator(_r))
                    mUI.MelLabel(_r, label='{} keys'.format(nKeys))
                    mUI.MelSpacer(_r, w=10)
                    _r.layout()
            _r = mUI.MelHLayout(_col, padding=5, bgc=_bgc)
            mUI.MelButton(_r, label='Sel', ut='cgmUITemplate',
                          ann='Select this object if it exists',
                          c=cgmGEN.Callback(self.uiFunc_select_object, i))
            _r.layout()

    def uiStatus_refresh(self, string=None):
        _str_func = 'uiStatus_refresh[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        if self._loadedFile:
            string = string or CORESTRINGS.short(self._loadedFile, max=40, start=10)
            self.uiStatus_top(edit=True,
                              bgc=CORESHARE._d_gui_state_colors.get('connected'),
                              label=string)
        else:
            self.uiStatus_top(edit=True,
                              bgc=CORESHARE._d_gui_state_colors.get('help'),
                              label='No Data')
        self._mapPreview = None
        self.uiUpdate_clip()
        self.uiFunc_capture_refresh_count()
        self.uiFunc_status('')

    def uiFunc_dat_get(self):
        _str_func = 'uiFunc_dat_get[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        _sel = mc.ls(sl=True)
        start = end = includeStatic = keyStartEnd = None
        if getattr(self, 'uiIF_captureStart', None):
            start = self.uiIF_captureStart.getValue()
            end = self.uiIF_captureEnd.getValue()
            includeStatic = bool(self.uiCB_includeStatic.getValue())
            keyStartEnd = bool(self.uiCB_keyStartEnd.getValue())
        self.uiDat.get(start=start, end=end, includeStatic=includeStatic or False,
                       keyStartEnd=keyStartEnd or False)
        nObj = len(self.uiDat.dat.get('objects') or [])
        self.uiStatus_refresh()
        self.uiFunc_status('Get: {} objects'.format(nObj))
        if _sel:
            mc.select(_sel)

    def uiFunc_select_objects(self):
        names = []
        ns = (self.uiDat.dat or {}).get('namespace') or ''
        for obj in (self.uiDat.dat or {}).get('objects') or []:
            n = _scene_node_by_name(obj, ns)
            if n:
                names.append(n)
        if names:
            mc.select(names)
        else:
            log.warning('No clip objects exist in this scene')

    def uiFunc_select_object(self, idx):
        objects = (self.uiDat.dat or {}).get('objects') or []
        if idx < 0 or idx >= len(objects):
            return
        obj = objects[idx]
        n = _scene_node_by_name(obj, (self.uiDat.dat or {}).get('namespace') or '')
        if n:
            mc.select(n)
        else:
            log.warning('Object not in scene: {}'.format(
                obj.get('shortName') or obj.get('longName')))

    def uiStatus_fileClear(self):
        if self.uiDat:
            self.uiDat.dat = {}
        super().uiStatus_fileClear()
        self.uiFunc_status('')

    def uiFunc_clip_clear(self):
        self.uiStatus_fileClear()

    def uiStatus_fileExplorer(self):
        if self._loadedFile and os.path.exists(self._loadedFile):
            os.startfile(PATHS.Path(self._loadedFile).up().asFriendly())

    def build_layoutWrapper(self, parent):
        _str_func = 'build_layoutWrapper[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))

        _MainForm = mUI.MelFormLayout(parent, ut='CGMUITemplate')

        _row_status = mUI.MelHSingleStretchLayout(_MainForm)
        mUI.MelSpacer(_row_status, w=2)

        self.uiStatus_top = mUI.MelButton(_row_status,
                                         vis=True,
                                         c=lambda *a: mc.evalDeferred(cgmGEN.Callback(self.uiFunc_dat_get)),
                                         bgc=CORESHARE._d_gui_state_colors.get('help'),
                                         label='No Data',
                                         h=20)
        mUI.MelIconButton(_row_status,
                          ann='Clear the loaded file link',
                          image=os.path.join(CGMUI._path_imageFolder, 'clear.png'),
                          w=25, h=25,
                          bgc=CGMUI.guiButtonColor,
                          c=lambda *a: self.uiStatus_fileClear())
        mUI.MelIconButton(_row_status,
                          ann='Open Dir',
                          image=os.path.join(CGMUI._path_imageFolder, 'find_file.png'),
                          w=25, h=25,
                          bgc=CGMUI.guiButtonColor,
                          c=lambda *a: self.uiStatus_fileExplorer())

        _row_status.setStretchWidget(self.uiStatus_top)
        mUI.MelSpacer(_row_status, w=2)
        _row_status.layout()

        _pinned = self.uiBuild_pinned_chrome(_MainForm)

        _inside = mUI.MelScrollLayout(_MainForm, ut='CGMUITemplate')
        _scrollCol = mUI.MelColumnLayout(_inside, ut='CGMUITemplate', adj=True)

        self.uiSection_top = mUI.MelColumn(_scrollCol, useTemplate='cgmUISubTemplate', vis=True)
        _row = mUI.MelHSingleStretchLayout(self.uiSection_top, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l='Status')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        self.uiLabel_status = mUI.MelLabel(_row, label='')
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        mVar_cap = self.var_animClip_captureFrameCollapse
        _frameCap = mUI.MelFrameLayout(_scrollCol, label='Capture', vis=True,
                                       collapse=mVar_cap.value,
                                       collapsable=True,
                                       enable=True,
                                       useTemplate='cgmUIHeaderTemplate',
                                       expandCommand=lambda: mVar_cap.setValue(0),
                                       collapseCommand=lambda: mVar_cap.setValue(1))
        self.uiSection_capture = mUI.MelColumnLayout(_frameCap, useTemplate='cgmUISubTemplate')
        self.uiBuild_capture(self.uiSection_capture)

        mVar_clip = self.var_animClip_clipFrameCollapse
        _frameClip = mUI.MelFrameLayout(_scrollCol, label='Current Clip', vis=True,
                                        collapse=mVar_clip.value,
                                        collapsable=True,
                                        enable=True,
                                        useTemplate='cgmUIHeaderTemplate',
                                        expandCommand=lambda: mVar_clip.setValue(0),
                                        collapseCommand=lambda: mVar_clip.setValue(1))
        self.uiSection_clip = mUI.MelColumnLayout(_frameClip, useTemplate='cgmUISubTemplate', adj=True)
        self.uiClip_header = mUI.MelColumnLayout(self.uiSection_clip, useTemplate='cgmUISubTemplate', adj=True)
        mVar_contents = self.var_animClip_contentsFrameCollapse
        _contentsWrap = mUI.MelColumnLayout(self.uiSection_clip, useTemplate='cgmUIHeaderTemplate', adj=True)
        _header = CGMUI.guiHeaderColor
        self.uiFrame_contents = mUI.MelFrameLayout(
            _contentsWrap,
            label='CLIP CONTENTS  (0)',
            vis=True,
            collapse=mVar_contents.value,
            collapsable=True,
            enable=True,
            bgc=_header,
            expandCommand=lambda: mVar_contents.setValue(0),
            collapseCommand=lambda: mVar_contents.setValue(1))
        self.uiFrame_data = mUI.MelColumnLayout(self.uiFrame_contents, useTemplate='cgmUIHeaderTemplate', adj=True)
        self.uiUpdate_clip()

        mVar_apply = self.var_animClip_applyFrameCollapse
        _frameApply = mUI.MelFrameLayout(_scrollCol, label='Apply', vis=True,
                                         collapse=mVar_apply.value,
                                         collapsable=True,
                                         enable=True,
                                         useTemplate='cgmUIHeaderTemplate',
                                         expandCommand=lambda: self.uiFunc_apply_frame_expand(),
                                         collapseCommand=lambda: mVar_apply.setValue(1))
        self.uiSection_apply = mUI.MelColumnLayout(_frameApply, useTemplate='cgmUISubTemplate')
        self.uiBuild_apply(self.uiSection_apply)

        _row_cgm = CGMUI.add_cgmFooter(_MainForm)

        _af = [(_row_status, 'top', 0),
               (_row_status, 'left', 0),
               (_row_status, 'right', 0),
               (_inside, 'left', 0),
               (_inside, 'right', 0),
               (_row_cgm, 'left', 0),
               (_row_cgm, 'right', 0),
               (_row_cgm, 'bottom', 0)]
        if _pinned:
            _af.extend([(_pinned, 'left', 0),
                        (_pinned, 'right', 0)])
            _ac = [(_pinned, 'top', 0, _row_status),
                   (_inside, 'top', 2, _pinned),
                   (_inside, 'bottom', 0, _row_cgm)]
        else:
            _ac = [(_inside, 'bottom', 0, _row_cgm),
                   (_inside, 'top', 0, _row_status)]
        _MainForm(edit=True,
                  af=_af,
                  ac=_ac,
                  attachNone=[(_row_cgm, 'top')])
