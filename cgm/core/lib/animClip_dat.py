"""
AnimClip Dat — JSON Dat + Phase 0 UI + Phase 1 curve fixture wrap + Phase 2 capture.

Curve snapshot/rebuild lives in animClip_curve.py. Capture uses ATTR.get_keyed /
ATTR.get_driver, then snapshot + slice_keys + offset_keys. keyStartEnd optionally
runs ensure_boundary_keys. Apply matches the target object, then keys each channel
attr via apply_to_plug (Replace/Merge/Insert). Mapping: Auto/Name/Index plus
PoseManager match methods via r9Core.matchNodeLists.
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

mUI = CGMUI.mUI
__version__ = cgmGEN.__RELEASESTRING

log_msg = cgmGEN.logString_msg
log_start = cgmGEN.logString_start

_CLIP_VERSION = 1


def reload_dependencies():
    """Reload AnimClip backend modules (tool open / ui.reload)."""
    from cgm.core import cgm_Dat as _CGMDAT
    import cgm.core.lib.animClip_curve as _animClip_curve
    cgmGEN._reloadMod(_CGMDAT)
    cgmGEN._reloadMod(_animClip_curve)
    global ANIMCLIPCURVE
    ANIMCLIPCURVE = _animClip_curve
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
    for attr in ('cgmName', 'cgmType'):
        if not mc.attributeQuery(attr, node=node, exists=True):
            continue
        try:
            v = ATTR.get(node, attr)
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ''
            if v not in (None, False):
                if attr == 'cgmName':
                    cgmName = str(v)
                else:
                    cgmType = str(v)
        except Exception:
            pass
    rotateOrder = None
    if mc.attributeQuery('rotateOrder', node=node, exists=True):
        try:
            rotateOrder = ATTR.get(node, 'rotateOrder')
        except Exception:
            rotateOrder = None
    return {
        'shortName': short,
        'longName': longName,
        'cgmName': cgmName,
        'cgmType': cgmType,
        'uuid': uuid,
        'rotateOrder': rotateOrder,
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


def _match_pose_destinations(objects, mapping, dest_pool, clip_ns=''):
    src = [_clip_src_token(obj, mapping, clip_ns) for obj in objects]
    valid = [s for s in src if s]
    if not valid:
        log.warning(log_msg('_match_destinations',
                            '{} needs captured node names (or live nodes for {})'.format(
                                mapping, mapping)))
        return [None] * len(objects)
    try:
        pairs = r9Core.matchNodeLists(valid, dest_pool, matchMethod=mapping) or []
    except Exception as err:
        log.warning(log_msg('_match_destinations', '{} | {}'.format(mapping, err)))
        return [None] * len(objects)
    by_src = {}
    for a, b in pairs:
        by_src[a] = b
    return [by_src.get(s) if s else None for s in src]


def _match_destinations(objects, mapping='Name', namespace=''):
    mapping = mapping or 'Name'
    sel = _selected_transforms()
    dests = []
    if mapping == 'Index':
        if len(sel) < len(objects):
            log.warning(log_msg('_match_destinations',
                                'Index mapping needs {} selected, got {}'.format(
                                    len(objects), len(sel))))
        for i, obj in enumerate(objects):
            dests.append(sel[i] if i < len(sel) else None)
        return dests
    if mapping == 'Auto' and sel and len(sel) == len(objects):
        return list(sel)
    if mapping in _l_poseMapping:
        if not sel:
            log.warning(log_msg('_match_destinations',
                                'Select dest controls for {} mapping'.format(mapping)))
            return [None] * len(objects)
        return _match_pose_destinations(objects, mapping, sel, namespace)
    for obj in objects:
        dests.append(_scene_node_by_name(obj, namespace))
    return dests


def _preview_mapping(objects, mapping='Name', namespace=''):
    """Clip shortName → dest shortName (or None) for the current mapping. Does not paste."""
    dests = _match_destinations(objects, mapping, namespace) or []
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
            'uuid': '',
            'rotateOrder': None,
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

    def get(self, start=None, end=None, includeStatic=False, keyStartEnd=False):
        _str_func = 'AnimClip.get'
        log.debug(log_start(_str_func))
        sel = _selected_transforms()
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

    def apply(self, atFrame=None, mode='Replace', mapping='Name'):
        """Paste clip keys onto matched dest.attr at atFrame. Replace/Merge/Insert. Auto/Name/Index plus Pose match methods."""
        _str_func = 'AnimClip.apply'
        log.debug(log_start(_str_func))
        clip = self.dat or {}
        objects = clip.get('objects') or []
        if not objects:
            log.warning(log_msg(_str_func, 'No clip objects to paste'))
            return 0
        mode = mode or 'Replace'
        if atFrame is None:
            _slider = SEARCH.get_time('slider') or [1, 24]
            atFrame = _slider[0]
        timeOffset = float(atFrame) if clip.get('relative') else 0.0
        dests = _match_destinations(objects, mapping, clip.get('namespace') or '')
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
                        log.warning(log_msg(_str_func,
                                            'Skip {}.{} | driver is {}'.format(
                                                dest, attr, mc.nodeType(driver))))
                        continue
                    try:
                        ANIMCLIPCURVE.apply_to_plug(curveDat, dest, attr,
                                                    timeOffset=timeOffset, mode=mode)
                        nApplied += 1
                    except Exception as err:
                        log.warning(log_msg(_str_func, '{}.{} | {}'.format(dest, attr, err)))
        finally:
            _progress_end(_pb)
        log.info(log_msg(_str_func, '{} curves | {} at {} | {}'.format(
            nApplied, mode, atFrame, mapping)))
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
        self._mapPreview = None

    def post_init(self, *args, **kws):
        CGMDAT.ui.post_init(self, *args, **kws)
        self.uiFunc_capture_refresh_count()

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
        mUI.MelLabel(_row, label='From the current Maya selection.')
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
        n = len(mc.ls(sl=True) or [])
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
        if not _sel:
            return log.warning('Select controls to capture')
        start = self.uiIF_captureStart.getValue()
        end = self.uiIF_captureEnd.getValue()
        includeStatic = bool(self.uiCB_includeStatic.getValue())
        keyStartEnd = bool(self.uiCB_keyStartEnd.getValue())
        self.uiDat.get(start=start, end=end, includeStatic=includeStatic,
                       keyStartEnd=keyStartEnd)
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
                                                   ann='Name: scene. Index: selection order. Auto: Index when counts match. Other items are PoseManager match methods (select dest).')
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
                         'Apply the current clip at Paste at frame. Replace/Merge/Insert.')
        mUI.MelSpacer(_row, w=5)
        _row.layout()

    def uiFunc_apply(self):
        _str_func = 'uiFunc_apply[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        if not (self.uiDat.dat and (self.uiDat.dat.get('objects') or [])):
            return log.warning('No clip to paste')
        at = self.uiIF_applyFrame.getValue()
        mode = self.uiOM_applyMode.getValue()
        mapping = self.uiOM_applyMapping.getValue()
        n = self.uiDat.apply(atFrame=at, mode=mode, mapping=mapping)
        self.uiFunc_status('Pasted {} curves at {}  {} | {}'.format(
            n, int(at), mode, mapping))

    def uiFunc_check_mapping(self):
        _str_func = 'uiFunc_check_mapping[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        objects = (self.uiDat.dat or {}).get('objects') or []
        if not objects:
            return log.warning('No clip to map')
        mapping = self.uiOM_applyMapping.getValue()
        ns = (self.uiDat.dat or {}).get('namespace') or ''
        _sel = mc.ls(sl=True)
        pairs, nHit = _preview_mapping(objects, mapping, ns)
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
                _label = '{}  →  {}          {} curves'.format(
                    name, _preview[i] or '--', nCurves)
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
                                         expandCommand=lambda: mVar_apply.setValue(0),
                                         collapseCommand=lambda: mVar_apply.setValue(1))
        self.uiSection_apply = mUI.MelColumnLayout(_frameApply, useTemplate='cgmUISubTemplate')
        self.uiBuild_apply(self.uiSection_apply)

        _row_cgm = CGMUI.add_cgmFooter(_MainForm)

        _MainForm(edit=True,
                  af=[(_row_status, 'top', 0),
                      (_row_status, 'left', 0),
                      (_row_status, 'right', 0),
                      (_inside, 'left', 0),
                      (_inside, 'right', 0),
                      (_row_cgm, 'left', 0),
                      (_row_cgm, 'right', 0),
                      (_row_cgm, 'bottom', 0)],
                  ac=[(_inside, 'bottom', 0, _row_cgm),
                      (_inside, 'top', 0, _row_status)],
                  attachNone=[(_row_cgm, 'top')])
