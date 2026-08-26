"""
AnimClip Dat — Phase 0 UI stub + JSON Dat shell.

Curve snapshot/rebuild is Phase 1. Capture range / apply / matching are later.
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

mUI = CGMUI.mUI
__version__ = cgmGEN.__RELEASESTRING

log_msg = cgmGEN.logString_msg
log_start = cgmGEN.logString_start

_CLIP_VERSION = 1


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


def _clip_curve_count(d):
    n = 0
    for obj in d.get('objects') or []:
        n += len(obj.get('channels') or [])
    return n

_l_applyModes = ('Replace', 'Merge', 'Insert')
_l_applyMapping = ('Auto', 'Name', 'Index')
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
        'objects': [],
    }


def _object_identity(node):
    """Phase 0 identity stubs. No matching, no channels."""
    short = mc.ls(node, shortNames=True)[0]
    longName = mc.ls(node, long=True)[0]
    ns = ''
    if ':' in short:
        ns = ':'.join(short.split(':')[:-1])
    uuid = ''
    try:
        uuid = mc.ls(node, uuid=True)[0]
    except Exception:
        pass
    cgmName = ''
    cgmType = ''
    if mc.attributeQuery('cgmName', node=node, exists=True):
        cgmName = mc.getAttr('{}.cgmName'.format(node)) or ''
    if mc.attributeQuery('cgmType', node=node, exists=True):
        cgmType = mc.getAttr('{}.cgmType'.format(node)) or ''
    rotateOrder = None
    if mc.attributeQuery('rotateOrder', node=node, exists=True):
        rotateOrder = mc.getAttr('{}.rotateOrder'.format(node))
    return {
        'shortName': short,
        'longName': longName,
        'namespace': ns,
        'cgmName': cgmName,
        'cgmType': cgmType,
        'uuid': uuid,
        'rotateOrder': rotateOrder,
        'channels': [],
    }


class AnimClip(CGMDAT.data):
    _ext = 'cgmAnimClip'
    _dataFormat = 'json'
    _startDir = ['cgmDat', 'anim']

    def __init__(self, filepath=None, dat=None, **kws):
        kws.setdefault('dataFormat', self._dataFormat)
        super(AnimClip, self).__init__(filepath, **kws)
        self.structureMode = 'workspace'
        if dat:
            self.dat = dat

    def get(self, start=None, end=None, includeStatic=False):
        _str_func = 'AnimClip.get'
        log.debug(log_start(_str_func))
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
        sel = ordered
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
        clip['objects'] = [_object_identity(n) for n in sel]
        self.dat = clip
        log.info(log_msg(_str_func, '{} objects | {}-{} (identity stubs, no curves)'.format(
            len(sel), start, end)))
        return self.dat


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
        self.create_guiOptionVar('animClip_captureFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_clipFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_applyFrameCollapse', defaultValue=0)
        self.create_guiOptionVar('animClip_applyMode', defaultValue='Replace')
        self.var_animClip_applyMode.setType('string')
        self.create_guiOptionVar('animClip_applyMapping', defaultValue='Auto')
        self.var_animClip_applyMapping.setType('string')

    def post_init(self, *args, **kws):
        CGMDAT.ui.post_init(self, *args, **kws)
        self.uiFunc_capture_refresh_count()

    def _ui_kv_row(self, parent, label, value):
        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
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
        _row.setStretchWidget(mUI.MelSeparator(_row))
        mUI.MelSpacer(_row, w=10)
        _row.layout()

        mc.button(parent=parent,
                  l='Capture Animation',
                  ut='cgmUITemplate',
                  h=30,
                  ann='Store identity stubs and range from the current selection. Curves are Phase 1.',
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
        self.uiDat.get(start=start, end=end, includeStatic=includeStatic)
        nObj = len(self.uiDat.dat.get('objects') or [])
        self.uiStatus_refresh()
        self.uiFunc_status('Captured {} objects  {}-{}'.format(nObj, int(start), int(end)))
        if _sel:
            mc.select(_sel)

    def uiBuild_apply(self, parent):
        _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l='Paste at frame')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        _now = int(mc.currentTime(q=True))
        self.uiIF_applyFrame = mUI.MelIntField(_row, width=40, value=_now)

        mUI.MelLabel(_row, l='Mode')
        self.uiOM_applyMode = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate',
                                                ann='Phase 3 - how incoming keys land on existing curves')
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
                                                   ann='Phase 4 - how clip objects match scene objects')
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

        CGMUI.add_Button(_row, 'Paste Clip',
                         cgmGEN.Callback(self.uiFunc_apply_stub),
                         'Phase 3 - apply the current clip at Paste at frame')
        mUI.MelSpacer(_row, w=5)
        _row.layout()

    def uiFunc_apply_stub(self):
        log.warning('Paste Clip: not implemented (Phase 3). Mode={} Mapping={} frame={}'.format(
            self.var_animClip_applyMode.value,
            self.var_animClip_applyMapping.value,
            self.uiIF_applyFrame.getValue() if getattr(self, 'uiIF_applyFrame', None) else '--'))
        self.uiFunc_status('Paste Clip is Phase 3.')

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
        self.uiFrame_data = mUI.MelColumnLayout(self.uiSection_clip, useTemplate='cgmUISubTemplate')
        d = (self.uiDat.dat if self.uiDat else None) or {}
        objects = d.get('objects') or []
        hasClip = bool(d) and self.uiDat.checkState()

        _row = mUI.MelHSingleStretchLayout(self.uiClip_header, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=5)
        if hasClip:
            nFrames = _clip_frame_count(d)
            frames = '{} frames'.format(nFrames) if nFrames is not None else '-- frames'
            _sum = '{}  |  {}  |  {} controls  |  {} curves'.format(
                _clip_name(self.uiDat, self._loadedFile),
                frames,
                len(objects),
                _clip_curve_count(d))
        else:
            _sum = 'No clip'
        mUI.MelLabel(_row, label=_sum, align='left')
        _row.setStretchWidget(mUI.MelSeparator(_row))
        mUI.MelButton(_row, label='Clear', ut='cgmUITemplate',
                      ann='Clear the current clip from the UI (does not delete the file)',
                      c=lambda *a: self.uiFunc_clip_clear())
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        mUI.MelLabel(self.uiFrame_data, label='CLIP CONTENTS  ({})'.format(len(objects)), h=13,
                     ut='cgmUIHeaderTemplate', align='center')

        if not objects:
            mUI.MelLabel(self.uiFrame_data,
                         label='None -- Capture Animation from selection',
                         h=16, align='center', ut='cgmUISubTemplate')
            return

        for i, obj in enumerate(objects):
            name = obj.get('shortName') or obj.get('longName') or '--'
            nCurves = len(obj.get('channels') or [])
            _f = mUI.MelFrameLayout(self.uiFrame_data,
                                    label='{}          {} curves'.format(name, nCurves),
                                    collapsable=True,
                                    collapse=True,
                                    enable=True,
                                    useTemplate='cgmUISubTemplate')
            _col = mUI.MelColumnLayout(_f, useTemplate='cgmUISubTemplate')
            channels = obj.get('channels') or []
            if not channels:
                mUI.MelLabel(_col, label='No curves yet (Phase 1)',
                             h=16, align='center', ut='cgmUISubTemplate')
                self._ui_kv_row(_col, 'namespace', obj.get('namespace'))
                self._ui_kv_row(_col, 'cgmName', obj.get('cgmName'))
                self._ui_kv_row(_col, 'cgmType', obj.get('cgmType'))
            else:
                for ch in channels:
                    attr = ch.get('attr') or ch.get('plug') or '--'
                    nKeys = len((ch.get('curve') or {}).get('keys') or [])
                    _r = mUI.MelHSingleStretchLayout(_col, ut='cgmUISubTemplate', padding=5)
                    mUI.MelSpacer(_r, w=15)
                    mUI.MelLabel(_r, label=attr)
                    _r.setStretchWidget(mUI.MelSeparator(_r))
                    mUI.MelLabel(_r, label='{} keys'.format(nKeys))
                    mUI.MelSpacer(_r, w=10)
                    _r.layout()
            _r = mUI.MelHLayout(_col, padding=5)
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
        self.uiUpdate_clip()
        self.uiFunc_capture_refresh_count()
        self.uiFunc_status('')

    def uiFunc_dat_get(self):
        _str_func = 'uiFunc_dat_get[{0}]'.format(self.__class__.TOOLNAME)
        log.debug("|{0}| >>...".format(_str_func))
        _sel = mc.ls(sl=True)
        start = end = includeStatic = None
        if getattr(self, 'uiIF_captureStart', None):
            start = self.uiIF_captureStart.getValue()
            end = self.uiIF_captureEnd.getValue()
            includeStatic = bool(self.uiCB_includeStatic.getValue())
        self.uiDat.get(start=start, end=end, includeStatic=includeStatic)
        nObj = len(self.uiDat.dat.get('objects') or [])
        self.uiStatus_refresh()
        self.uiFunc_status('Get: {} objects'.format(nObj))
        if _sel:
            mc.select(_sel)

    def uiFunc_select_objects(self):
        names = []
        for obj in (self.uiDat.dat or {}).get('objects') or []:
            n = obj.get('longName') or obj.get('shortName')
            if n and mc.objExists(n):
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
        n = obj.get('longName') or obj.get('shortName')
        if n and mc.objExists(n):
            mc.select(n)
        else:
            log.warning('Object not in scene: {}'.format(n))

    def uiStatus_fileClear(self):
        self._loadedFile = ''
        self.var_LastLoaded.setValue('')
        self.uiDat.dat = {}
        self.uiStatus_refresh()
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
        self.uiSection_clip = mUI.MelColumnLayout(_frameClip, useTemplate='cgmUISubTemplate')
        self.uiClip_header = mUI.MelColumnLayout(self.uiSection_clip, useTemplate='cgmUISubTemplate')
        self.uiFrame_data = mUI.MelColumnLayout(self.uiSection_clip, useTemplate='cgmUISubTemplate')
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
