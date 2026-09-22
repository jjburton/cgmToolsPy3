"""
------------------------------------------
dynFKTool : cgm.core.tools
Author: David Bokser
email: dbokser@cgmonks.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
cgmDynSimTool (dynamic chains / cgmDynFK)
================================================================
"""
# From Python =============================================================
import copy
import re
import time
import pprint
import os
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
from cgm.core import cgm_RigMeta as cgmRigMeta
mUI = cgmUI.mUI

from cgm.core.lib import shared_data as SHARED
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
import cgm.core.lib.transform_utils as TRANS
from cgm.core.cgmPy import path_Utils as CGMPATH
import cgm.core.lib.math_utils as MATH
from cgm.core.lib import search_utils as SEARCH

import cgm.core.rig.dynamic_utils as RIGDYN
import cgm.core.presets.cgmDynFK_presets as dynFKPresets
import cgm.core.lib.nCloth_utils as NCLOTH
import cgm.core.lib.simChain_dat as SIMDAT
import cgm.core.cgm_Dat as CGMDAT

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ = 'cgmDynSimTool'

_padding = 5
_LIBRARY_SAVE_DIR_OV = 'cgmDynSimTool_libraryDirMode'
_LIBRARY_SAVE_DIR_OV_LEGACY = (
    'cgmDynamicsTool_libraryDirMode',
    'cgmSimChain_libraryDirMode',
)
_LIBRARY_SEARCH_DEV_OV = 'cgmDynSimTool_librarySearch_dev'
_LIBRARY_SEARCH_WS_OV = 'cgmDynSimTool_librarySearch_workspace'


def _library_save_mode_get():
    if mc.optionVar(exists=_LIBRARY_SAVE_DIR_OV):
        _v = mc.optionVar(q=_LIBRARY_SAVE_DIR_OV)
        if _v in CGMDAT._l_libraryDirModes:
            return _v
    for _legacy in _LIBRARY_SAVE_DIR_OV_LEGACY:
        if mc.optionVar(exists=_legacy):
            _v = mc.optionVar(q=_legacy)
            if _v in CGMDAT._l_libraryDirModes:
                return _v
    return 'dev'


def _library_save_mode_set(mode):
    if mode not in CGMDAT._l_libraryDirModes:
        mode = 'dev'
    mc.optionVar(sv=(_LIBRARY_SAVE_DIR_OV, mode))


def _library_search_modes_get():
    """Enabled SearchDir roots; default both on."""
    _modes = []
    for _mode, _ov in (
        ('dev', _LIBRARY_SEARCH_DEV_OV),
        ('workspace', _LIBRARY_SEARCH_WS_OV),
    ):
        if mc.optionVar(exists=_ov):
            if int(mc.optionVar(q=_ov)):
                _modes.append(_mode)
        else:
            _modes.append(_mode)
    return CGMDAT.library_modes_normalize(_modes) or ['dev']


def _library_search_mode_set(mode, enabled):
    _ov = _LIBRARY_SEARCH_DEV_OV if mode == 'dev' else _LIBRARY_SEARCH_WS_OV
    mc.optionVar(iv=(_ov, 1 if enabled else 0))


def _library_search_mode_toggle(mode):
    _modes = list(_library_search_modes_get())
    if mode in _modes:
        if len(_modes) <= 1:
            log.warning("Keep at least one SearchDir enabled")
            return list(_modes)
        _modes.remove(mode)
        _library_search_mode_set(mode, False)
    else:
        _modes.append(mode)
        _library_search_mode_set(mode, True)
    return CGMDAT.library_modes_normalize(_modes) or ['dev']


_STATUS_ROW_HELP_BGC = SHARED._d_gui_state_colors.get('help')


def _dynfk_progress_begin(status, step_max=1):
    try:
        return cgmUI.doStartMayaProgressBar(
            stepMaxValue=max(int(step_max), 1),
            statusMessage=status,
            interruptableState=True,
        )
    except Exception:
        return None


def _dynfk_progress_step(progress_bar, status=None, step=1):
    if not progress_bar:
        return False
    try:
        if mc.progressBar(progress_bar, q=True, isCancelled=True):
            return True
        _kw = {'step': step}
        if status:
            _kw['status'] = status
        mc.progressBar(progress_bar, e=True, **_kw)
        mc.refresh()
    except Exception:
        pass
    return False


def _dynfk_progress_end(progress_bar):
    if progress_bar:
        try:
            cgmUI.doEndMayaProgressBar(progress_bar)
        except Exception:
            pass


def _dynfk_build_details_empty_message(parent, message):
    """Full-width centered placeholder inside Details frame (p4 / animClip status pattern)."""
    _form = mUI.MelFormLayout(parent, ut='cgmUITemplate')
    _status = mUI.MelButton(
        _form,
        label=message,
        h=20,
        align='center',
        bgc=_STATUS_ROW_HELP_BGC,
        ann='Use the header set icon to load a cgmDynFK setup.',
        en=False,
    )
    _form(
        edit=True,
        af=(
            (_status, 'top', 2),
            (_status, 'bottom', 2),
            (_status, 'left', 2),
            (_status, 'right', 2),
        ),
    )
    return _form


def _dynfk_icon_btn_kw(image_name, w=25, h=25):
    """Match animClip_dat / Scene icon rows (cgmUITemplate, 25×25, guiButtonColor)."""
    return {
        'ut': 'cgmUITemplate',
        'style': 'iconOnly',
        'l': '',
        'image': os.path.join(cgmUI._path_imageFolder, image_name),
        'w': w,
        'h': h,
        'bgc': cgmUI.guiButtonColor,
    }


def uiBuild_setup_status_row(self, parent):
    """Pinned status row — same layout/colors as animClip_dat ``_row_status``."""
    _row = mUI.MelHSingleStretchLayout(parent)
    mUI.MelSpacer(_row, w=2)

    self.uiBtn_newSystem = mUI.MelIconButton(
        _row,
        ann='New cgmDynFK + nucleus (Init Sim Setup).',
        c=cgmGEN.Callback(uiFunc_init_sim_setup, self),
        **_dynfk_icon_btn_kw('new_set.png'),
    )
    mUI.MelLabel(_row, l='Dynamic Chain System:', h=20)

    self.uiTF_objLoad = mUI.MelButton(
        _row,
        vis=True,
        label='No setup',
        h=20,
        bgc=_STATUS_ROW_HELP_BGC,
        ann='Loaded cgmDynFK setup (click to refresh from scene).',
        c=cgmGEN.Callback(uiFunc_refresh_loaded_setup, self),
    )
    self.uiBtn_loadSelected = mUI.MelIconButton(
        _row,
        ann='Load first selected cgmDynFK setup.',
        c=cgmGEN.Callback(uiFunc_load_selected, self),
        **_dynfk_icon_btn_kw('set_25.png'),
    )
    self.uiBtn_refreshLoaded = mUI.MelIconButton(
        _row,
        ann='Refresh loaded cgmDynFK from scene (re-read messages and Details).',
        c=cgmGEN.Callback(uiFunc_refresh_loaded_setup, self),
        **_dynfk_icon_btn_kw('refresh.png'),
    )
    self.uiBtn_selectLoaded = mUI.MelIconButton(
        _row,
        ann='Select loaded cgmDynFK setup in the scene.',
        c=cgmGEN.Callback(uiFunc_select_loaded_setup, self),
        **_dynfk_icon_btn_kw('select_25.png'),
    )
    self.uiBtn_clearLoaded = mUI.MelIconButton(
        _row,
        ann='Clear loaded setup from the tool (does not delete scene nodes).',
        c=cgmGEN.Callback(uiFunc_clear_loaded, self),
        **_dynfk_icon_btn_kw('clear.png'),
    )

    _row.setStretchWidget(self.uiTF_objLoad)
    mUI.MelSpacer(_row, w=2)
    _row.layout()
    return _row


def reload_dependencies():
    """
    Reload cgmDynSimTool backend modules via cgmGEN._reloadMod.

    Leaf lib modules first, then ik/constraint rig libs, then dynamic_utils last so
    re-imported helpers are not stale. Does **not** reload Red9 / ``cgm_Meta`` / mClass
    registry — after **``cgmDynFK``** or other subclass edits, run **cgm core reload**
    (``import cgm.core as CGM; CGM._reload()``) so meta classes initialize in order.
    """
    import cgm.core.lib.attribute_utils as ATTR
    import cgm.core.lib.distance_utils as DIST
    import cgm.core.lib.name_utils as NAMES
    import cgm.core.lib.math_utils as MATHUTILS
    import cgm.core.lib.node_utils as NODES
    import cgm.core.lib.transform_utils as TRANSUTIL
    import cgm.core.lib.snap_utils as SNAP
    import cgm.core.lib.curve_Utils as CURVES
    import cgm.core.lib.locator_utils as LOC
    import cgm.core.lib.constraint_utils as CONSTRAINTS
    import cgm.core.lib.rigging_utils as CORERIG
    import cgm.core.classes.NodeFactory as NODEFACTORY
    import cgm.core.rig.constraint_utils as RIGCONSTRAINTS
    import cgm.core.rig.ik_utils as IKUTIL
    import cgm.core.lib.nCloth_utils as NCLOTHMOD
    import cgm.core.lib.simChain_dat as SIMDATMOD
    import cgm.core.presets.cgmDynFK_presets as DYNFKPRESETS
    import cgm.core.presets.cgmNCloth_presets as nClothPresets
    import cgm.core.rig.dynamic_utils as RIGDYNMOD

    _lib_mods = (
        ATTR, DIST, NAMES, MATHUTILS, NODES, TRANSUTIL, SNAP, CURVES, LOC,
        CONSTRAINTS, CORERIG, NODEFACTORY,
    )
    _rig_mods = (RIGCONSTRAINTS, IKUTIL)
    _dat_mods = (NCLOTHMOD, SIMDATMOD, DYNFKPRESETS, nClothPresets)
    _reload_mods = _lib_mods + _rig_mods + _dat_mods + (RIGDYNMOD,)

    log.info(cgmGEN.logString_msg('reload_dependencies', 'reloading cgmDynSimTool backend...'))
    for _mod in _reload_mods:
        log.info(cgmGEN.logString_msg('reload_dependencies', getattr(_mod, '__name__', repr(_mod))))
        cgmGEN._reloadMod(_mod)

    global RIGDYN, NCLOTH, SIMDAT, dynFKPresets, MATH, TRANS
    RIGDYN = RIGDYNMOD
    NCLOTH = NCLOTHMOD
    SIMDAT = SIMDATMOD
    dynFKPresets = DYNFKPRESETS
    MATH = MATHUTILS
    TRANS = TRANSUTIL

    log.info(cgmGEN.logString_msg('reload_dependencies', 'cgmDynSimTool backend done'))
    log.info(cgmGEN.logString_msg(
        'reload_dependencies',
        'mClass / meta subclass edits need cgm core reload (CGM._reload) — not done here.'))
    log.info(cgmGEN._str_subLine)


_RELAUNCH_TOOL_ANN = (
    'Reload cgmDynSimTool backend libs + dynFKTool UI (same as shelf). Rebinds loaded setup meta. '
    'Use after editing dynamic_utils, dynFKTool, simChain_dat, or presets. '
    'If you changed cgmDynFK / cgm_Meta / mClass subclasses, run cgm core reload '
    '(import cgm.core as CGM; CGM._reload()) before relaunching.')


def _reload_dynfk_backend(self):
    """Backend module reload + rebind loaded cgmDynFK; does not reload dynFKTool UI code."""
    reload_dependencies()
    _dynfk_rebind_loaded_mDynFK(self)
    if getattr(self, '_mDynFK', None):
        try:
            uiFunc_update_details(self)
        except Exception:
            pass
    log.info(cgmGEN.logString_msg(
        '_reload_dynfk_backend',
        'Backend reloaded + setup meta rebound.'))
    log.info(cgmGEN._str_subLine)


def uiFunc_relaunch_tool(self):
    """Reload backend + dynFKTool module and open cgmDynSimTool (same as shelf entry)."""
    reload_dependencies()
    import cgm.core.tools.dynFKTool as DYNFKTOOL
    log.info(cgmGEN.logString_msg('uiFunc_relaunch_tool', getattr(DYNFKTOOL, '__name__', 'dynFKTool')))
    cgmGEN._reloadMod(DYNFKTOOL)
    DYNFKTOOL.ui()
    log.info(cgmGEN._str_subLine)


def uiFunc_refresh_loaded_setup(self):
    """Re-read the loaded cgmDynFK setup from the scene without changing selection."""
    _str_func = 'uiFunc_refresh_loaded_setup'
    m = getattr(self, '_mDynFK', None)
    if not m:
        return
    try:
        _node = m.mNode
    except Exception:
        return
    if not _node or not mc.objExists(_node):
        log.warning(cgmGEN.logString_msg(_str_func, 'Loaded setup no longer exists'))
        uiFunc_clear_loaded(self)
        return
    try:
        cgmMeta.reinitializeMetaClass(m)
    except Exception:
        pass
    self._mDynFK = RIGDYN.cgmDynFK(_node)
    log.info(cgmGEN.logString_msg(_str_func, 'refreshed: {0}'.format(self._mDynFK.p_nameBase)))
    uiFunc_updateTargetDisplay(self)
    uiFunc_refresh_hair_system_create_menu(self)


def uiFunc_on_scene_change(self):
    """scriptJob SceneOpened — defer until the new scene DAG is ready."""
    log.info(cgmGEN.logString_msg(
        'uiFunc_on_scene_change', 'Scene opened — scheduling chain load refresh'))
    mc.evalDeferred(cgmGEN.Callback(uiFunc_refresh_chain_after_scene_open, self), lp=True)


def uiFunc_refresh_chain_after_scene_open(self):
    """Re-load LastDynFK (or clear) and rebuild Details — file open and tool post_init."""
    _str_func = 'uiFunc_refresh_chain_after_scene_open'
    _node = uiFunc_last_dynfk_resolve(self)
    if _node:
        uiFunc_load_dyn_chain(self, _node, with_progress=True)
        if hasattr(self, 'itemList'):
            try:
                self.itemList.rebuild()
            except Exception:
                pass
        uiFunc_update_create_panel_state(self)
        log.info(cgmGEN.logString_msg(_str_func, 'Loaded {0}'.format(_node)))
        return
    uiFunc_clear_loaded(self)
    log.info(cgmGEN.logString_msg(_str_func, 'No cgmDynFK in scene for LastDynFK'))


def _dynfk_rebind_loaded_mDynFK(self, rigdyn_module=None):
    """After backend reload, drop stale meta cache and re-wrap loaded setup with fresh cgmDynFK class."""
    m = getattr(self, '_mDynFK', None)
    if not m:
        return
    try:
        _node = m.mNode
    except Exception:
        return
    if not _node or not mc.objExists(_node):
        return
    _rigdyn = rigdyn_module or RIGDYN
    try:
        cgmMeta.reinitializeMetaClass(m)
    except Exception:
        pass
    self._mDynFK = _rigdyn.cgmDynFK(_node)
    log.info(cgmGEN.logString_msg(
        '_dynfk_rebind_loaded_mDynFK',
        'rebound loaded cgmDynFK: {0}'.format(_node)))


class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = False
    DEFAULT_SIZE = 550, 420
    TOOLNAME = '{0}.ui'.format(__toolname__)

    def __new__(cls, *a, **kw):
        """Keep last window size when relaunching from shelf (BaseMelWindow deletes/recreates)."""
        _size = cls.DEFAULT_SIZE
        if mc.window(cls.WINDOW_NAME, ex=True):
            try:
                _size = (
                    mc.window(cls.WINDOW_NAME, q=True, width=True),
                    mc.window(cls.WINDOW_NAME, q=True, height=True),
                )
            except Exception:
                _size = cls.DEFAULT_SIZE
            mc.window(cls.WINDOW_NAME, edit=True, closeCommand=mUI.doNothing)
            mc.deleteUI(cls.WINDOW_NAME)
        kw.setdefault('title', cls.WINDOW_TITLE)
        kw.setdefault('widthHeight', _size)
        kw.setdefault('menuBar', True)
        kw.setdefault('retain', cls.RETAIN)
        kw.setdefault('useTemplate', cls.USE_Template)
        kw.setdefault('minimizeButton', cls.MIN_BUTTON)
        kw.setdefault('maximizeButton', cls.MAX_BUTTON)
        kw.setdefault('closeCommand', cls.Close)
        _win = str.__new__(cls, mc.window(cls.WINDOW_NAME, **kw))
        mc.window(_win, e=True, docTag=cls.__name__)
        if cls.DEFAULT_MENU is not None:
            mUI.MelMenu(l=cls.DEFAULT_MENU, helpMenu=cls.DEFAULT_MENU_IS_HELP)
        return _win
    
    _mDynFK = False
    _simDatInst = None
    _simDatPath = None

    def insert_init(self,*args,**kws):
        _str_func = '__init__[{0}]'.format(self.__class__.TOOLNAME)            
        log.info("|{0}| >>...".format(_str_func))        

        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))
        log.info(self.__call__(q=True, title=True))

        self.__version__ = __version__
        self.__toolName__ = self.__class__.WINDOW_NAME	

        self.create_guiOptionVar('LastDynFK', defaultValue='')
        self.var_LastDynFK.setType('string')
        self.create_guiOptionVar('SimChainInCurveDegree', defaultValue='1')
        self.var_SimChainInCurveDegree.setType('string')
        self.create_guiOptionVar('SimChainOutCurveDegree', defaultValue='2')
        self.var_SimChainOutCurveDegree.setType('string')
        self.create_guiOptionVar('SimChainHairFollowMode', defaultValue='Spline IK')
        self.var_SimChainHairFollowMode.setType('string')
        self.create_guiOptionVar('SimChainAddEndJointDistance', defaultValue='2.0')
        self.var_SimChainAddEndJointDistance.setType('string')
        self.create_guiOptionVar('SimChainAddEndJointEnabled', defaultValue='0')
        self.var_SimChainAddEndJointEnabled.setType('string')
        self.create_guiOptionVar('SimChainExtendEndDistance', defaultValue='1.0')
        self.var_SimChainExtendEndDistance.setType('string')
        self.create_guiOptionVar('SimChainExtendEndEnabled', defaultValue='0')
        self.var_SimChainExtendEndEnabled.setType('string')
        self.create_guiOptionVar('SimChainAdvancedTwistEnabled', defaultValue='0')
        self.var_SimChainAdvancedTwistEnabled.setType('string')
        self.create_guiOptionVar('SimChainFollicleSampleDensity', defaultValue='1.0')
        self.var_SimChainFollicleSampleDensity.setType('string')
        self.create_guiOptionVar('SimChainHairSystemMode', defaultValue='New')
        self.var_SimChainHairSystemMode.setType('string')
        self._d_chainHairBuildMenus = {}

        #self.l_allowedDockAreas = []
        self.WINDOW_TITLE = self.__class__.WINDOW_TITLE
        self.DEFAULT_SIZE = self.__class__.DEFAULT_SIZE

        self.setSceneChangeCB(cgmGEN.Callback(uiFunc_on_scene_change, self))

    def reload(self):
        _reload_dynfk_backend(self)
 
    def build_menus(self):
        self.uiMenu_Setup = mUI.MelMenu(l='Setup', pmc=cgmGEN.Callback(self.buildMenu_file))
        self.uiMenu_PresetsMenu = mUI.MelMenu(l='Presets', pmc = cgmGEN.Callback(self.buildMenu_presets))
        self.uiMenu_ToolsMenu = mUI.MelMenu(l='Tools', pmc = cgmGEN.Callback(self.buildMenu_tools))

    def buildMenu_file(self):
        self.uiMenu_Setup.clear()
        mUI.MelMenuItem(
            self.uiMenu_Setup, l='Load Dat…',
            ann='Load cgmSim*Dat or cgmSimChainSetup and apply to the scene / setup',
            c=cgmGEN.Callback(uiFunc_sim_dat_load, self),
        )
        mUI.MelMenuItem(
            self.uiMenu_Setup, l='Save Dat',
            ann='Capture setup from loaded cgmDynFK or save in-memory dat to its path',
            c=cgmGEN.Callback(uiFunc_sim_dat_save, self, False),
        )
        mUI.MelMenuItem(
            self.uiMenu_Setup, l='Save Dat As…',
            ann='Capture setup or save in-memory dat to a new path',
            c=cgmGEN.Callback(uiFunc_sim_dat_save, self, True),
        )
        mUI.MelMenuItemDiv(self.uiMenu_Setup, l='Tool')
        self.uiMenu_buildDock(self.uiMenu_Setup)
        mUI.MelMenuItem(
            self.uiMenu_Setup, l='Relaunch Tool',
            ann=_RELAUNCH_TOOL_ANN,
            c=cgmGEN.Callback(uiFunc_relaunch_tool, self))

    def buildMenu_tools(self):
        self.uiMenu_ToolsMenu.clear()
        mUI.MelMenuItem(
            self.uiMenu_ToolsMenu,
            l='Init Sim Setup',
            ann='Create cgmDynFK + nucleus (no dynamic chain). Required before mapping cloth.',
            c=cgmGEN.Callback(uiFunc_init_sim_setup, self),
        )
        mUI.MelMenuItemDiv(self.uiMenu_ToolsMenu)
        mUI.MelMenuItem(
            self.uiMenu_ToolsMenu,
            l='Query Settings',
            ann='Print preset-shaped dict from selected nCloth, nucleus, hair system, or cgmDynFK setup.',
            c=cgmGEN.Callback(uiFunc_query_settings, self),
        )

    def buildMenu_presets(self):
        """Hair / Cloth / Nucleus dat presets + setup library."""
        self.uiMenu_PresetsMenu.clear()
        uiFunc_build_presets_menu(self, self.uiMenu_PresetsMenu)
        mUI.MelMenuItemDiv(self.uiMenu_PresetsMenu)
        _setups = mUI.MelMenuItem(
            self.uiMenu_PresetsMenu, l='Setups', subMenu=True, tearOff=True,
            ann='cgmSimChainSetup files — full setup re-wire when scene nodes exist.',
        )
        uiFunc_build_setup_library_menu(self, _setups)

    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper'
        #self._d_uiCheckBoxes = {}
    
        #_MainForm = mUI.MelFormLayout(parent,ut='cgmUISubTemplate')
        _MainForm = mUI.MelFormLayout(self, ut='cgmUITemplate')
        _row_status = uiBuild_setup_status_row(self, _MainForm)
        _column = buildColumn_main(self, _MainForm, True)

        _row_cgm = cgmUI.add_cgmFooter(_MainForm)
        _MainForm(
            edit=True,
            af=[
                (_row_status, 'top', 0),
                (_row_status, 'left', 0),
                (_row_status, 'right', 0),
                (_column, 'left', 0),
                (_column, 'right', 0),
                (_row_cgm, 'left', 0),
                (_row_cgm, 'right', 0),
                (_row_cgm, 'bottom', 0),
            ],
            ac=[
                (_column, 'bottom', 0, _row_cgm),
                (_column, 'top', 2, _row_status),
            ],
            attachNone=[(_row_cgm, 'top')],
        )
    
    def post_init(self, *args, **kws):
        _node = uiFunc_last_dynfk_resolve(self)
        if _node:
            mc.evalDeferred(
                cgmGEN.Callback(uiFunc_refresh_chain_after_scene_open, self), lp=True)
    
    def do_dock( self):
        _str_func = 'do_dock'
        #log.info("dockCnt: {0}".format(self.dockCnt))
        #log.debug("uiDock: {0}".format(self.uiDock))                
        #log.debug("area: {0}".format(self.l_allowedDockAreas[self.var_DockSide.value]))
        #log.debug("label: {0}".format(self.WINDOW_TITLE))
        #log.debug("self: {0}".format(self.Get()))                
        #log.debug("content: {0}".format(self.WINDOW_NAME))
        #log.debug("floating: {0}".format(not self.var_Dock.value))
        #log.debug("allowedArea: {0}".format(self.l_allowedDockAreas))
        #log.debug("width: {0}".format(self.DEFAULT_SIZE[0])) 
        try:
            self.uiDock
        except:
            log.debug("|{0}| >> making uiDock attr".format(_str_func)) 
            self.uiDock = False
            
        _dock = '{0}Dock'.format(self.__toolName__)   
        _l_allowed = self.__class__.l_allowedDockAreas
        
  
        _content = self.Get()
            
        if mc.dockControl(_dock,q=True, exists = True):
            log.debug('linking...')
            self.uiDock = _dock
            mc.dockControl(_dock , edit = True, area=_l_allowed[self.var_DockSide.value],
                           label=self.WINDOW_TITLE, content=_content,
                           allowedArea=_l_allowed,
                           width=self.DEFAULT_SIZE[0], height = self.DEFAULT_SIZE[1])                    
        #else:
        else:
            log.debug('creating...')       
            mc.dockControl(_dock , area=_l_allowed[self.var_DockSide.value],
                           label=self.WINDOW_TITLE, content=_content,
                           allowedArea=_l_allowed,
                           width=self.DEFAULT_SIZE[0], height = self.DEFAULT_SIZE[1]) 
            self.uiDock = _dock
        
        
        """log.info("floating: {0}".format(mc.dockControl(_dock, q = True, floating = True)))
        log.info("var_Doc: {0}".format(self.var_Dock.value))
        _floating = mc.dockControl(_dock, q = True, floating = True)
        if _floating and self.var_Dock == 1:
            log.info('mismatch')
            self.var_Dock = 0
        if not _floating and self.var_Dock == 0:
            log.info("mismatch2")
            self.var_Dock = 1"""
        
        mc.dockControl(_dock, edit = True, floating = self.var_Dock.value, width=self.DEFAULT_SIZE[0], height = self.DEFAULT_SIZE[1])
        self.uiDock = _dock   
        _floating = mc.dockControl(_dock, q = True, floating = True)            
        if _floating:
            #log.info("Not visible, resetting position.")
            #mc.dockControl(self.uiDock, e=True, visible = False)
            mc.window(_dock, edit = True, tlc = [200, 200])
        self.var_Dock.toggle()


def buildColumn_main(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    _scroll = None
    if asScroll:
        _scroll = mUI.MelScrollLayout(parent, useTemplate='cgmUITemplate')
        _inside = mUI.MelColumnLayout(_scroll, useTemplate='cgmUITemplate', adj=True)
    else:
        _inside = mUI.MelColumnLayout(parent, useTemplate='cgmUITemplate', adj=True)

    self.detailsFrame = mUI.MelFrameLayout(
        _inside,
        label='Details',
        collapsable=True,
        collapse=True,
        useTemplate='cgmUIHeaderTemplate',
    )

    uiFunc_update_details(self)

    # Create Frame

    self.createFrame = mUI.MelFrameLayout(
        _inside,
        label='Create',
        collapsable=True,
        collapse=False,
        useTemplate='cgmUIHeaderTemplate',
    )

    _create = mUI.MelColumnLayout(self.createFrame, useTemplate='cgmUIHeaderTemplate')

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_create,ut='cgmUISubTemplate',padding = _padding)

    mUI.MelSpacer(_row,w=_padding)
    
    _subRow = mUI.MelColumnLayout(_row,useTemplate = 'cgmUIHeaderTemplate') 
    self.itemList = cgmUI.cgmScrollList(_subRow, numberOfRows = 8, height=100)
    self.itemList(edit=True, allowMultiSelection=True)

    mUI.MelSpacer(_row,w=_padding)

    _row.setStretchWidget( _subRow )

    _row.layout()

    mUI.MelSeparator(_create,ut='cgmUISubTemplate',h=5)

    _row = mUI.MelHSingleStretchLayout(_create,ut='cgmUISubTemplate',padding = 5)

    mUI.MelSpacer(_row,w=_padding)

    addBtn = cgmUI.add_Button(_row,'Add Selected',
                     cgmGEN.Callback(uiFunc_list_function,self.itemList, 'add selected'),
                     "Load selected objects.")

    cgmUI.add_Button(_row,'Remove Selected',
                     cgmGEN.Callback(uiFunc_list_function,self.itemList, 'remove selected'),
                     "Remove selected objects.")

    cgmUI.add_Button(_row,'Clear',
                     cgmGEN.Callback(uiFunc_list_function,self.itemList, 'clear'),
                     "Clear all objects.")

    _row.setStretchWidget( addBtn )

    mUI.MelSpacer(_row,w=_padding)

    _row.layout()

    mc.setParent(_create)
    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_create, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Name: ')
    self.options_name = mUI.MelTextField(_row, ann='Per-chain name prefix.', text='')
    _row.setStretchWidget(self.options_name)
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _row = mUI.MelHSingleStretchLayout(_create, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Direction:')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    directions = ['x+', 'x-', 'y+', 'y-', 'z+', 'z-']
    mUI.MelLabel(_row, l='Fwd:')
    self.fwdMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for dir in directions:
        self.fwdMenu.append(dir)
    self.fwdMenu.setValue('z+')
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Up:')
    self.upMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for dir in directions:
        self.upMenu.append(dir)
    self.upMenu.setValue('y+')
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    mc.setParent(_create)
    cgmUI.add_LineSubBreak()

    self.hairCreateFrame = mUI.MelFrameLayout(
        _create, label='Hair', collapsable=True, collapse=False,
        useTemplate='cgmUIHeaderTemplate')
    _hair = mUI.MelColumnLayout(
        self.hairCreateFrame,
        useTemplate='cgmUIHeaderTemplate',
        bgc=cgmUI.guiBackgroundColor,
        adj=True,
        rowSpacing=0,
    )

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Build:')
    self.options_hairFollowMode = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate',
        ann='Follow mode for new chains.')
    for _label in ('Spline IK', 'Legacy'):
        self.options_hairFollowMode.append(_label)
    self.options_hairFollowMode.setValue('Spline IK')
    self.options_hairFollowMode(
        edit=True, changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='In deg:')
    self.options_inCurveDegree = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for _d in ('1', '2', '3'):
        self.options_inCurveDegree.append(_d)
    self.options_inCurveDegree.setValue('1')
    self.options_inCurveDegree(
        edit=True, changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Out deg:')
    self.options_outCurveDegree = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for _d in ('1', '2', '3'):
        self.options_outCurveDegree.append(_d)
    self.options_outCurveDegree.setValue('2')
    self.options_outCurveDegree(
        edit=True, changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _extRow = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_extRow, w=_padding)
    mUI.MelLabel(_extRow, l='Advanced twist:')
    self.options_advancedTwistCB = mUI.MelCheckBox(
        _extRow, v=False, label='',
        ann='Spline IK: Object Rotation Up (Start/End) on out-curve handle; sim joints at chain ends. Rebuild Chain to update existing chains.',
        changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    _extRow.setStretchWidget(mUI.MelSeparator(_extRow))
    mUI.MelLabel(_extRow, l='Add end joint:')
    self.options_addEndJointCB = mUI.MelCheckBox(
        _extRow, v=False, label='',
        ann='Extra sim joint past the last target so the last segment can bend (not an inCurve CV).',
        changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    self.options_addEndJointDistance = mUI.MelTextField(
        _extRow, w=50, text='2.0', editable=False,
        bgc=SHARED._d_gui_state_colors.get('help'),
        ann='Offset distance (scene units) along last segment when Add end joint is on.',
        changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    mUI.MelSpacer(_extRow, w=_padding)
    mUI.MelLabel(_extRow, l='Extend end:')
    self.options_curveExtendEndCB = mUI.MelCheckBox(
        _extRow, v=False, label='',
        ann='Extra inCurve CV past chain end (after add-end sim joint when that is on). Ponytail overshoot.',
        changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    self.options_curveExtendEndDistance = mUI.MelTextField(
        _extRow, w=50, text='1.0', editable=False,
        bgc=SHARED._d_gui_state_colors.get('help'),
        ann='Curve extension distance (scene units) along last segment when Extend end is on.',
        changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    mUI.MelSpacer(_extRow, w=_padding)
    _extRow.layout()
    uiFunc_sync_add_end_joint_options(self)
    uiFunc_sync_curve_extend_end_options(self)

    mc.setParent(_hair)
    cgmUI.add_SectionBreak()
    mUI.MelLabel(_hair, l='Follicle', ut='cgmUITemplate', align='center')
    mUI.MelSeparator(_hair, ut='cgmUISubTemplate', h=2)

    _row = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Fixed segment length:')
    self.options_fixedSegmentLengthCB = mUI.MelCheckBox(
        _row, v=False, label='',
        ann='Off (default): sampleDensity=1 — one sim/collision segment per inCurve CV/joint span. '
            'On: fixedSegmentLength + Segment Length (Maya uniform world-length sampling).',
        changeCommand=cgmGEN.Callback(uiFunc_sync_follicle_segment_options, self))
    self.options_follicleSegmentLength = mUI.MelTextField(
        _row, w=50, text='1.0', editable=False,
        bgc=SHARED._d_gui_state_colors.get('help'),
        ann='Scene linear units (typically cm) when Fixed segment length is enabled.')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _row = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Sample density:')
    self.options_follicleSampleDensity = mUI.MelTextField(
        _row, w=50, text='1.0', editable=True,
        ann='Default follicle sampleDensity for new chains (applied on Make Dynamic Chain only; per-chain live edit in Details).')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()
    uiFunc_sync_follicle_segment_options(self)

    cgmUI.add_SectionBreak()
    mUI.MelLabel(_hair, l='Hair system', ut='cgmUITemplate', align='center')
    mUI.MelSeparator(_hair, ut='cgmUISubTemplate', h=2)

    _row = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Mode:')
    self.options_hairSystemMode = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    self.options_hairSystemMode(
        edit=True, changeCommand=cgmGEN.Callback(uiFunc_persist_simchain_create_optionvars, self))
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    uiFunc_restore_simchain_create_optionvars(self)
    uiFunc_refresh_hair_system_create_menu(self)

    mc.setParent(_hair)
    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_hair, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Chain')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    self.btnMakeDynamicChain = cgmUI.add_Button(
        _row, 'Make Dynamic Chain',
        cgmGEN.Callback(uiFunc_make_dynamic_chain, self),
        'Make dynamic hair/curve chain (makeCurvesDynamic).')
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    mc.setParent(_create)
    cgmUI.add_LineSubBreak()

    self.clothCreateFrame = mUI.MelFrameLayout(
        _create, label='Cloth', collapsable=True, collapse=False,
        useTemplate='cgmUIHeaderTemplate')
    _cloth = mUI.MelColumnLayout(self.clothCreateFrame, useTemplate='cgmUISubTemplate')

    mUI.MelSeparator(_cloth, ut='cgmUISubTemplate', h=5)

    _row = mUI.MelHSingleStretchLayout(_cloth, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Cloth:')
    self.uiClothStatusLabel = mUI.MelLabel(_row, ut='cgmUIInstructionsTemplate', l='Not linked')
    _row.setStretchWidget(self.uiClothStatusLabel)
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _row = mUI.MelHSingleStretchLayout(_cloth, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Mesh track:')
    self.clothSurfaceTrackMenu = mUI.MelOptionMenu(
        _row, useTemplate='cgmUITemplate',
        ann='Mesh tracker on simmed nCloth outMesh (follicle, rivet, or uvPin).')
    for _track in ('follicle', 'rivet', 'uvPin'):
        self.clothSurfaceTrackMenu.append(_track)
    self.clothSurfaceTrackMenu.setValue('uvPin')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_cloth, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    self.btnAttachToCloth = cgmUI.add_Button(
        _row, 'Attach to Cloth',
        cgmGEN.Callback(uiFunc_attach_to_cloth, self),
        'Attach joint chain to mapped nCloth. Locators under mesh track drive Connect Targets.')
    self.btnAttachToCloth(e=True, en=False)
    _row.setStretchWidget(self.btnAttachToCloth)
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    uiFunc_update_create_panel_state(self)

    """
    _row.layout()

    #>>>Report ---------------------------------------------------------------------------------------
    _row_report = mUI.MelHLayout(_inside ,ut='cgmUIInstructionsTemplate',h=20)
    self.uiField_report = mUI.MelLabel(_row_report,
                                       bgc = SHARED._d_gui_state_colors.get('help'),
                                       label = '...',
                                       h=20)
    _row_report.layout() """

    return _scroll if _scroll else _inside

def uiFunc_is_profile_dict(v):
    return isinstance(v, dict) and ('n' in v or 'hs' in v)

def uiFunc_profile_list(key=None, category=None):
    """List cgmDynFK_presets names. Reloads presets only (not dynamic_utils/meta)."""
    if hasattr(RIGDYN, 'profile_list'):
        try:
            return RIGDYN.profile_list(key=key, category=category)
        except TypeError:
            # Older signature without category
            names = RIGDYN.profile_list(key=key)
            if not category or not hasattr(RIGDYN, 'profile_kind'):
                return names
            return [n for n in names if RIGDYN.profile_kind(n) == category]
        except Exception:
            pass

    cgmGEN._reloadMod(dynFKPresets)
    names = set()
    for k, v in list(dynFKPresets.__dict__.items()):
        if k.startswith('_') or k in ('d_chain', 'd_profileKind'):
            continue
        if uiFunc_is_profile_dict(v):
            names.add(k)
    d_chain = getattr(dynFKPresets, 'd_chain', None) or {}
    if isinstance(d_chain, dict):
        for k, v in list(d_chain.items()):
            if uiFunc_is_profile_dict(v):
                names.add(k)

    filtered = []
    for name in names:
        _d = dynFKPresets.__dict__.get(name)
        if not uiFunc_is_profile_dict(_d):
            _d = d_chain.get(name)
        if not _d:
            continue
        if key is not None and _d.get(key) is None:
            continue
        if category:
            _kind = None
            if hasattr(RIGDYN, 'profile_kind'):
                _kind = RIGDYN.profile_kind(name)
            else:
                _kind = (getattr(dynFKPresets, 'd_profileKind', None) or {}).get(name)
            if _kind != category:
                continue
        filtered.append(name)
    return sorted(filtered)

def uiFunc_get_profile_key_for_obj(obj):
    """Map nucleus/hairSystem targets to cgmDynFK_presets section keys."""
    try:
        mObj = cgmMeta.asMeta(obj, noneValid=True)
        if not mObj:
            return None
        return RIGDYN.d_shortHand.get(mObj.getMayaType())
    except Exception:
        return None

def uiFunc_ncloth_profile_list(category=None):
    return NCLOTH.profile_list(category=category)


def uiFunc_setup_sim_targets(self):
    """Return (mCloth, mNucleus, mHair) for the loaded cgmDynFK setup."""
    if not self._mDynFK:
        return None, None, None
    mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
    mNucleus = self._mDynFK.getMessageAsMeta('mNucleus')
    dat = self._mDynFK.get_dat() or {}
    if not mNucleus:
        mNucleus = dat.get('mNucleus')
    mHair = dat.get('mHairSysShape')
    return mCloth, mNucleus, mHair


_SIM_DAT_KINDS = (
    ('hair', 'Hair', 'cgmSimHairDat'),
    ('hairShape', 'HairShape', 'cgmSimHairShapeDat'),
    ('cloth', 'Cloth', 'cgmSimClothDat'),
    ('nucleus', 'Nucleus', 'cgmSimNucleusDat'),
)
_SIM_MENU_HAIR_PREFIX = 'Hair: '
_SIM_MENU_SHAPE_PREFIX = 'Shape: '


def uiFunc_get_library_mode(self=None):
    """SaveDir mode (legacy name kept for callers)."""
    return _library_save_mode_get()


def uiFunc_get_library_search_modes(self=None):
    return _library_search_modes_get()


def uiFunc_library_register_preset_path(self, label, filepath):
    if self is None or not label or not filepath:
        return
    if not getattr(self, '_md_libraryPresetPaths', None):
        self._md_libraryPresetPaths = {}
    self._md_libraryPresetPaths[label] = filepath


def uiFunc_library_path_for_label(self, label):
    if self is None or not label:
        return None
    return (getattr(self, '_md_libraryPresetPaths', None) or {}).get(label)


def uiFunc_library_items_for_kind(kind, ext, modes=None):
    """Return sorted (displayName, filepath) pairs for one dat kind (SearchDir collective)."""
    modes = modes or _library_search_modes_get()
    _rows = SIMDAT.get_library_rows(kind_ext=ext, modes=modes)
    return [(_r['display'], _r['filepath']) for _r in _rows]


def uiFunc_library_preset_names(kind, modes=None):
    _ext = {k: e for k, _l, e in _SIM_DAT_KINDS}.get(kind)
    if not _ext:
        return []
    return [n for n, _ in uiFunc_library_items_for_kind(kind, _ext, modes=modes)]


def uiFunc_library_dat_kind_for_name(name, modes=None):
    """Match bare or ``name [mode]`` display to a dat kind."""
    modes = modes or _library_search_modes_get()
    _bare = name
    if ' [' in name and name.endswith(']'):
        _bare = name.rsplit(' [', 1)[0]
    for kind, _label, ext in _SIM_DAT_KINDS:
        for _disp, _fpath in uiFunc_library_items_for_kind(kind, ext, modes=modes):
            if _disp == name or _disp == _bare or _disp.split(' [')[0] == _bare:
                return kind
    return None


def uiFunc_library_apply_by_path(self, filepath):
    _str_func = 'uiFunc_library_apply_by_path'
    if not filepath or not os.path.isfile(filepath):
        return log.warning("|{0}| >> Preset not found: {1}".format(_str_func, filepath))
    uiFunc_library_load_apply(self, filepath)


def uiFunc_library_apply_by_name(self, datKind, name):
    _str_func = 'uiFunc_library_apply_by_name'
    _modes = _library_search_modes_get()
    _path = None
    _ext = {k: e for k, _l, e in _SIM_DAT_KINDS}.get(datKind)
    if _ext:
        for _disp, _fpath in uiFunc_library_items_for_kind(datKind, _ext, modes=_modes):
            if _disp == name or _disp.split(' [')[0] == name:
                _path = _fpath
                break
    if not _path:
        _path = SIMDAT.resolve_library_filepath(
            '{0}.{1}'.format(datKind, name.split(' [')[0]), modes=_modes)
    if not _path:
        _path = SIMDAT.resolve_library_filepath(name.split(' [')[0], modes=_modes)
    if not _path or not os.path.isfile(_path):
        return log.warning("|{0}| >> Preset not found: {1}.{2}".format(_str_func, datKind, name))
    uiFunc_library_load_apply(self, _path)


def uiFunc_library_apply_hair_to_target(self, presetName, hairTarget, mGrp=None):
    """Apply a dynamic hair (`.cgmSimHairDat`) preset to a hairSystem shape."""
    _str_func = 'uiFunc_library_apply_hair_to_target'
    _modes = _library_search_modes_get()
    _path = uiFunc_library_path_for_label(self, _SIM_MENU_HAIR_PREFIX + presetName)
    if not _path:
        for _disp, _fpath in uiFunc_library_items_for_kind('hair', 'cgmSimHairDat', modes=_modes):
            if _disp == presetName or _disp.split(' [')[0] == presetName:
                _path = _fpath
                break
    if not _path:
        _path = SIMDAT.resolve_library_filepath(
            'hair.{0}'.format(presetName.split(' [')[0]), modes=_modes)
    if not _path or not os.path.isfile(_path):
        return log.warning("|{0}| >> Preset not found: hair.{1}".format(_str_func, presetName))
    inst, _dat = SIMDAT.read_dat(_path)
    if not inst or getattr(inst, 'datKind', None) != 'hair':
        return log.warning("|{0}| >> Not a hair dat: {1}".format(_str_func, _path))
    _hs = RIGDYN._resolve_hair_system_shape(hairTarget)
    if not _hs:
        return log.warning("|{0}| >> Invalid hairSystem target".format(_str_func))
    _count = inst.apply(target=_hs, mDynFK=self._mDynFK, mGrp=mGrp)
    log.info("|{0}| >> Applied hair {1} to {2} ({3} attrs)".format(
        _str_func, presetName, _hs, _count))


def uiFunc_library_apply_hair_shape_to_target(self, presetName, hairTarget, mGrp=None):
    """Apply a HairShape (`.cgmSimHairShapeDat`) preset to a hairSystem and/or chain follicle."""
    _str_func = 'uiFunc_library_apply_hair_shape_to_target'
    _modes = _library_search_modes_get()
    _path = uiFunc_library_path_for_label(self, _SIM_MENU_SHAPE_PREFIX + presetName)
    if not _path:
        for _disp, _fpath in uiFunc_library_items_for_kind(
                'hairShape', 'cgmSimHairShapeDat', modes=_modes):
            if _disp == presetName or _disp.split(' [')[0] == presetName:
                _path = _fpath
                break
    if not _path:
        _path = SIMDAT.resolve_library_filepath(
            'hairShape.{0}'.format(presetName.split(' [')[0]), modes=_modes)
    if not _path or not os.path.isfile(_path):
        return log.warning("|{0}| >> Preset not found: hairShape.{1}".format(_str_func, presetName))
    inst, _dat = SIMDAT.read_dat(_path)
    if not inst or getattr(inst, 'datKind', None) != 'hairShape':
        return log.warning("|{0}| >> Not a HairShape dat: {1}".format(_str_func, _path))
    if mGrp:
        _count = inst.apply(mDynFK=self._mDynFK, mGrp=mGrp)
        log.info("|{0}| >> Applied HairShape {1} on chain ({2} attrs)".format(
            _str_func, presetName, _count))
        return
    _hs = RIGDYN._resolve_hair_system_shape(hairTarget)
    if not _hs:
        return log.warning("|{0}| >> Invalid hairSystem target".format(_str_func))
    _count = inst.apply(target=_hs, mDynFK=self._mDynFK)
    log.info("|{0}| >> Applied HairShape {1} to {2} ({3} attrs)".format(
        _str_func, presetName, _hs, _count))


def uiFunc_build_presets_menu(self, parentMenu):
    """Presets → Hair / Cloth / Nucleus from cgmDat/sim library."""
    _saveMode = _library_save_mode_get()
    _searchModes = _library_search_modes_get()
    if getattr(self, '_md_libraryPresetPaths', None) is None:
        self._md_libraryPresetPaths = {}
    else:
        self._md_libraryPresetPaths.clear()

    CGMDAT.uiMenu_addLibrarySaveSearchDirs(
        parentMenu, _saveMode, _searchModes,
        lambda mode: uiFunc_library_save_dir_mode(self, mode),
        lambda mode: uiFunc_library_search_dir_toggle(self, mode),
    )

    mUI.MelMenuItemDiv(parentMenu, l='Load + Apply')
    for _kind, _label, _ext in _SIM_DAT_KINDS:
        _sub = mUI.MelMenuItem(
            parentMenu, l=_label, subMenu=True, tearOff=True,
            ann='Apply {0} preset from cgmDat/sim/{1}/'.format(_label.lower(), _kind),
        )
        _items = uiFunc_library_items_for_kind(_kind, _ext, modes=_searchModes)
        if not _items:
            mUI.MelMenuItem(_sub, l='(none)', en=False)
            continue
        for _name, _fpath in _items:
            uiFunc_library_register_preset_path(self, _name, _fpath)
            mUI.MelMenuItem(
                _sub, l=_name, ann='{0}.{1} | {2}'.format(_kind, _name, _fpath),
                c=cgmGEN.Callback(uiFunc_library_apply_by_path, self, _fpath),
            )

    mUI.MelMenuItemDiv(parentMenu, l='Capture')
    for _kind, _label, _cls in (
        ('hair', 'Hair', SIMDAT.SimHairDat),
        ('hairShape', 'HairShape', SIMDAT.SimHairShapeDat),
        ('cloth', 'Cloth', SIMDAT.SimClothDat),
        ('nucleus', 'Nucleus', SIMDAT.SimNucleusDat),
    ):
        mUI.MelMenuItem(
            parentMenu, l='Save {0} Dat…'.format(_label),
            ann='Capture from selection or loaded cgmDynFK setup and save under cgmDat/sim/{0}/'.format(_kind),
            c=cgmGEN.Callback(uiFunc_sim_dat_capture_save, self, _cls),
        )

    mUI.MelMenuItemDiv(parentMenu, l='Reset')
    mUI.MelMenuItem(
        parentMenu, l='Base (nucleus + hair)',
        ann='Reset nucleus and hairSystem to shipped base profile (not a library dat).',
        c=cgmGEN.Callback(uiFunc_presets_reset_base, self),
    )


def uiFunc_presets_reset_base(self):
    """Reset mapped nucleus / hair to cgmDynFK_presets base (setup helper)."""
    _str_func = 'uiFunc_presets_reset_base'
    if not self._mDynFK:
        return log.warning("|{0}| >> Load a cgmDynFK setup first".format(_str_func))
    _, mNucleus, _ = uiFunc_setup_sim_targets(self)
    ml_hair = RIGDYN.hair_system_list_registered(self._mDynFK)
    if mNucleus:
        RIGDYN.profile_load(mNucleus.mNode, 'base')
    for mHair in ml_hair:
        RIGDYN.profile_load(mHair.mNode, 'base')
    if not mNucleus and not ml_hair:
        return log.warning("|{0}| >> Map nucleus or hair on setup first".format(_str_func))
    log.info("|{0}| >> Applied base reset (nucleus / all hair systems)".format(_str_func))


def uiFunc_build_library_menu(self, parentMenu):
    """Deprecated alias — presets menu is library-first."""
    uiFunc_build_presets_menu(self, parentMenu)


def uiFunc_build_setup_library_menu(self, parentMenu):
    """Presets → Setups — scan cgmDat/sim/setups for cgmSimChainSetup files."""
    _modes = _library_search_modes_get()

    mUI.MelMenuItemDiv(parentMenu, l='Load + Apply')
    _rows = SIMDAT.get_library_rows(modes=_modes, setup=True)
    if not _rows:
        mUI.MelMenuItem(parentMenu, l='(none)', en=False)
    else:
        for _r in _rows:
            mUI.MelMenuItem(
                parentMenu, l=_r['display'],
                ann='{0} | {1}'.format(_r['key'], _r['filepath']),
                c=cgmGEN.Callback(uiFunc_setup_library_load_apply, self, _r['filepath']),
            )


def uiFunc_setup_library_load_apply(self, filepath):
    _str_func = 'uiFunc_setup_library_load_apply'
    inst = SIMDAT.SimChainSetup()
    if not inst.read(filepath):
        return log.warning("|{0}| >> Failed to read: {1}".format(_str_func, filepath))
    self._simDatInst = inst
    self._simDatPath = filepath
    uiFunc_sim_setup_apply_loaded(self, inst=inst)


def uiFunc_sim_setup_capture_save(self):
    """Capture loaded setup and save (File → Save Dat when no prior dat)."""
    _str_func = 'uiFunc_sim_setup_capture_save'
    if not _sim_dat_capture_setup_inst(self, keep_filepath=None):
        return log.warning("|{0}| >> Load a cgmDynFK setup first".format(_str_func))
    uiFunc_sim_dat_save(self, forceAs=True)


def uiFunc_sim_setup_apply_loaded(self, inst=None):
    _str_func = 'uiFunc_sim_setup_apply_loaded'
    inst = inst or self._simDatInst
    if not inst or not isinstance(inst, SIMDAT.SimChainSetup):
        return log.warning("|{0}| >> No cgmSimChainSetup loaded".format(_str_func))
    mSetup = inst.apply(mDynFK=self._mDynFK or None)
    if not mSetup:
        return log.warning("|{0}| >> Setup apply failed".format(_str_func))
    uiFunc_load_dyn_chain(self, mSetup.mNode)
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    log.info("|{0}| >> Setup applied: {1}".format(_str_func, mSetup.p_nameBase))


def uiFunc_library_save_dir_mode(self, mode):
    _library_save_mode_set(mode)
    self.buildMenu_presets()


def uiFunc_library_search_dir_toggle(self, mode):
    _library_search_mode_toggle(mode)
    self.buildMenu_presets()


def uiFunc_library_dir_mode(self, mode):
    """Legacy alias — sets SaveDir."""
    uiFunc_library_save_dir_mode(self, mode)


def uiFunc_library_load_apply(self, filepath):
    _str_func = 'uiFunc_library_load_apply'
    inst, _dat = SIMDAT.read_dat(filepath)
    if not inst:
        return log.warning("|{0}| >> Failed to read: {1}".format(_str_func, filepath))
    self._simDatInst = inst
    self._simDatPath = filepath
    log.info("|{0}| >> Loaded: {1}".format(_str_func, filepath))
    uiFunc_sim_dat_apply_loaded(self, inst=inst)


def uiFunc_sim_dat_load(self):
    _str_func = 'uiFunc_sim_dat_load'
    _modes = _library_search_modes_get()
    _start = SIMDAT.get_library_path(_modes[0] if _modes else 'dev')
    _result = mc.fileDialog2(
        dialogStyle=2, fileMode=1, startingDirectory=_start,
        fileFilter=(
            'Sim dat (*.cgmSimHairDat *.cgmSimHairShapeDat *.cgmSimClothDat '
            '*.cgmSimNucleusDat *.cgmSimChainSetup)'),
    )
    if not _result:
        return
    inst, _dat = SIMDAT.read_dat(_result[0])
    if not inst:
        return log.warning("|{0}| >> Failed to read".format(_str_func))
    self._simDatInst = inst
    self._simDatPath = _result[0]
    log.info("|{0}| >> Loaded: {1}".format(_str_func, self._simDatPath))
    uiFunc_sim_dat_apply_loaded(self, inst=inst)


def _sim_dat_capture_setup_inst(self, keep_filepath=None):
    """Capture loaded cgmDynFK into SimChainSetup; optional keep_filepath for Save."""
    _str_func = '_sim_dat_capture_setup_inst'
    if not self._mDynFK:
        return None
    inst = SIMDAT.SimChainSetup()
    if not inst.capture(mDynFK=self._mDynFK):
        log.warning("|{0}| >> Capture failed".format(_str_func))
        return None
    if keep_filepath:
        inst.str_filepath = keep_filepath
    self._simDatInst = inst
    return inst


def uiFunc_sim_dat_save(self, forceAs=False):
    _str_func = 'uiFunc_sim_dat_save'
    _saveMode = _library_save_mode_get()
    inst = self._simDatInst
    if isinstance(inst, SIMDAT.SimChainSetup):
        _path = inst.str_filepath if not forceAs else None
        inst = _sim_dat_capture_setup_inst(self, keep_filepath=_path)
        if not inst:
            return log.warning("|{0}| >> Setup capture failed — load a cgmDynFK setup first".format(_str_func))
    elif not inst and self._mDynFK:
        inst = _sim_dat_capture_setup_inst(self)
        if not inst:
            return log.warning("|{0}| >> Setup capture failed".format(_str_func))
        forceAs = True
    elif not inst:
        return log.warning("|{0}| >> No sim dat loaded — load a dat or a cgmDynFK setup first".format(_str_func))
    if forceAs or not inst.str_filepath:
        if not inst.write(forcePrompt=True, startDirMode=_saveMode):
            return log.warning("|{0}| >> Save cancelled".format(_str_func))
    elif not inst.write(update=True, startDirMode=_saveMode):
        return log.warning("|{0}| >> Save failed".format(_str_func))
    self._simDatPath = inst.str_filepath
    log.info("|{0}| >> Saved: {1}".format(_str_func, self._simDatPath))


def uiFunc_sim_dat_capture_save(self, datClass):
    _str_func = 'uiFunc_sim_dat_capture_save'
    _saveMode = _library_save_mode_get()
    inst = datClass()
    _mDynFK = self._mDynFK or None
    if not inst.capture(mDynFK=_mDynFK):
        if datClass is SIMDAT.SimClothDat and _mDynFK:
            if not RIGDYN.get_mapped_cloth(_mDynFK):
                return log.warning(
                    "|{0}| >> Cloth capture failed — map cloth on setup (Details → Cloth <<)".format(
                        _str_func))
        return log.warning("|{0}| >> Capture failed for {1}".format(_str_func, datClass.__name__))
    self._simDatInst = inst
    if not inst.write(forcePrompt=True, startDirMode=_saveMode):
        return log.warning("|{0}| >> Save cancelled".format(_str_func))
    self._simDatPath = inst.str_filepath
    log.info("|{0}| >> Captured + saved: {1}".format(_str_func, self._simDatPath))


def uiFunc_sim_dat_capture_save_for_target(self, datClass, targetNode):
    """Capture from a specific scene node and save via dat dialog (Presets menu parity)."""
    _str_func = 'uiFunc_sim_dat_capture_save_for_target'
    _saveMode = _library_save_mode_get()
    inst = datClass()
    _mDynFK = self._mDynFK or None
    _node = VALID.mNodeString(targetNode)
    if not _node:
        return log.warning("|{0}| >> Invalid capture target".format(_str_func))
    if not inst.capture(nodes=_node, mDynFK=_mDynFK):
        return log.warning("|{0}| >> Capture failed for {1}".format(_str_func, datClass.__name__))
    self._simDatInst = inst
    if not inst.write(forcePrompt=True, startDirMode=_saveMode):
        return log.warning("|{0}| >> Save cancelled".format(_str_func))
    self._simDatPath = inst.str_filepath
    log.info("|{0}| >> Captured + saved: {1}".format(_str_func, self._simDatPath))
    return True


_SIM_PROFILE_DAT_CLASS = {
    'hs': SIMDAT.SimHairDat,
    'nc': SIMDAT.SimClothDat,
    'n': SIMDAT.SimNucleusDat,
}

_DEFAULT_DYNFK_BASE_NAME = 'DynamicChain'

_SIM_DAT_MENU_LOAD = 'Load Dat'
_SIM_DAT_MENU_SAVE_HAIR = 'Save Hair Dat…'
_SIM_DAT_MENU_SAVE_HAIR_SHAPE = 'Save HairShape Dat…'
_SIM_DAT_MENU_SAVE_CLOTH = 'Save Cloth Dat…'
_SIM_DAT_MENU_SAVE_NUCLEUS = 'Save Nucleus Dat…'


def uiFunc_sim_dat_apply_loaded(self, inst=None):
    _str_func = 'uiFunc_sim_dat_apply_loaded'
    inst = inst or self._simDatInst
    if not inst:
        return log.warning("|{0}| >> No sim dat loaded".format(_str_func))
    if isinstance(inst, SIMDAT.SimChainSetup):
        return uiFunc_sim_setup_apply_loaded(self, inst=inst)
    _kind = inst.dat.get('datKind') or getattr(inst, 'datKind', None)
    if _kind == 'cloth' and self._mDynFK:
        mCloth, _, _ = uiFunc_setup_sim_targets(self)
        if not mCloth:
            return log.warning("|{0}| >> Map cloth first for cloth dat apply".format(_str_func))
    if _kind in ('hair', 'hairShape') and self._mDynFK:
        _, _, mHair = uiFunc_setup_sim_targets(self)
        if not mHair:
            return log.warning("|{0}| >> {1} dat apply needs hair on setup or hairSystem selection".format(
                _str_func, _kind))
    if _kind == 'nucleus' and self._mDynFK:
        _, mNucleus, _ = uiFunc_setup_sim_targets(self)
        if not mNucleus:
            return log.warning("|{0}| >> Nucleus dat apply needs nucleus on setup or selection".format(
                _str_func))
    _count = inst.apply(mDynFK=self._mDynFK or None)
    log.info("|{0}| >> Applied {1} ({2} attrs)".format(
        _str_func, inst.dat.get('name'), _count))



def uiFunc_presets_load_cloth(self, presetName):
    """Apply cloth dat preset by library name."""
    uiFunc_library_apply_by_name(self, 'cloth', presetName)


def uiFunc_presets_load_hair(self, presetName):
    """Apply hair dat preset by library name."""
    uiFunc_library_apply_by_name(self, 'hair', presetName)


def uiFunc_presets_load_nucleus(self, presetName, source='ncloth'):
    """Apply nucleus dat preset by library name (source arg ignored — library only)."""
    uiFunc_library_apply_by_name(self, 'nucleus', presetName)


def uiFunc_chain_section_label(chain_idx, chain):
    """Details chain frame title: ``[index] - name | targets: n``."""
    _n_targets = len(chain.msgList_get('mTargets') or [])
    return '[{0}] - {1} | targets: {2}'.format(
        chain_idx, RIGDYN.chain_cgm_name(chain), _n_targets)


def uiFunc_rebuild_hair_system_preset_menu(optionMenu, mHairShape=None, selfRef=None):
    """Hair system row — dynamic Hair + HairShape libraries (separate dat kinds)."""
    _modes = _library_search_modes_get()
    optionMenu.clear()
    optionMenu.append(_SIM_DAT_MENU_LOAD)
    for _name, _fpath in uiFunc_library_items_for_kind('hair', 'cgmSimHairDat', modes=_modes):
        _label = _SIM_MENU_HAIR_PREFIX + _name
        uiFunc_library_register_preset_path(selfRef, _label, _fpath)
        optionMenu.append(_label)
    optionMenu.append('---')
    for _name, _fpath in uiFunc_library_items_for_kind(
            'hairShape', 'cgmSimHairShapeDat', modes=_modes):
        _label = _SIM_MENU_SHAPE_PREFIX + _name
        uiFunc_library_register_preset_path(selfRef, _label, _fpath)
        optionMenu.append(_label)
    optionMenu.append('---')
    optionMenu.append(_SIM_DAT_MENU_SAVE_HAIR)
    optionMenu.append(_SIM_DAT_MENU_SAVE_HAIR_SHAPE)
    optionMenu.setValue(_SIM_DAT_MENU_LOAD)


def uiFunc_process_hair_system_preset_change(self, mHairShape, optionMenu):
    """Apply hair or HairShape dat to one hairSystem shape, or capture + save."""
    val = optionMenu.getValue()
    _mHair = cgmMeta.asMeta(mHairShape, noneValid=True)
    _presetNode = _mHair.mNode if _mHair else VALID.mNodeString(mHairShape)
    if val in (_SIM_DAT_MENU_LOAD, '---'):
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    if val == _SIM_DAT_MENU_SAVE_HAIR:
        uiFunc_sim_dat_capture_save_for_target(self, SIMDAT.SimHairDat, _presetNode)
        uiFunc_rebuild_hair_system_preset_menu(optionMenu, _presetNode, selfRef=self)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    if val == _SIM_DAT_MENU_SAVE_HAIR_SHAPE:
        uiFunc_sim_dat_capture_save_for_target(self, SIMDAT.SimHairShapeDat, _presetNode)
        uiFunc_rebuild_hair_system_preset_menu(optionMenu, _presetNode, selfRef=self)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    if val.startswith(_SIM_MENU_HAIR_PREFIX):
        uiFunc_library_apply_hair_to_target(
            self, val[len(_SIM_MENU_HAIR_PREFIX):], _presetNode, mGrp=None)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    if val.startswith(_SIM_MENU_SHAPE_PREFIX):
        uiFunc_library_apply_hair_shape_to_target(
            self, val[len(_SIM_MENU_SHAPE_PREFIX):], _presetNode, mGrp=None)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    optionMenu.setValue(_SIM_DAT_MENU_LOAD)


def uiFunc_set_setup_default_hair_system(self):
    """Details Default menu — set setup ``mHairSysShape`` from registered list."""
    _str_func = 'uiFunc_set_setup_default_hair_system'
    if not self._mDynFK or not hasattr(self, 'details_defaultHairSystemMenu'):
        return
    _val = (self.details_defaultHairSystemMenu.getValue() or '').strip()
    _match = re.match(r'^Hair system (\d+)$', _val)
    if not _match:
        return
    _hi = int(_match.group(1))
    _ml = RIGDYN.hair_system_list_registered(self._mDynFK) or []
    if _hi < 1 or _hi > len(_ml):
        return log.warning(cgmGEN.logString_msg(_str_func, 'Invalid hair system index: {0}'.format(_hi)))
    mHair = _ml[_hi - 1]
    if not mHair:
        return
    RIGDYN.hair_system_set_default(self._mDynFK, mHair)
    log.info(cgmGEN.logString_msg(_str_func, mHair.p_nameShort))
    uiFunc_refresh_hair_system_create_menu(self)
    mc.evalDeferred(cgmGEN.Callback(uiFunc_update_details, self), lp=True)


def uiFunc_apply_hair_system_name(self, mHairShape, *args):
    """Rename hairSystem DAG from Details Hair systems row (Enter)."""
    _str_func = 'uiFunc_apply_hair_system_name'
    if not self._mDynFK:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No setup loaded'))
    _mHair = cgmMeta.asMeta(mHairShape, noneValid=True)
    if not _mHair:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Invalid hairSystem'))
    _hs = RIGDYN._resolve_hair_system_shape(_mHair.mNode)
    if not _hs:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hairSystem'))
    _key = _hs
    _field = (getattr(self, '_md_hairSystemNameFields', None) or {}).get(_key)
    if not _field:
        return
    try:
        _val = (_field.getValue() or '').strip()
    except Exception:
        _val = ''
    _current = RIGDYN.hair_system_name_token(_hs)
    if not _val:
        try:
            _field.setValue(_current)
        except Exception:
            pass
        return log.warning(cgmGEN.logString_msg(_str_func, 'Empty name'))
    if _val == _current or _val == '{0}_hairSys'.format(_current):
        return
    if not RIGDYN.hair_system_set_name(self._mDynFK, _hs, _val):
        try:
            _field.setValue(_current)
        except Exception:
            pass
        return
    uiFunc_refresh_hair_system_create_menu(self)
    mc.evalDeferred(cgmGEN.Callback(uiFunc_update_details, self), lp=True)


def uiFunc_make_hair_system_preset_row(self, parent, hair_idx, mHair, mDefault=None):
    """Details row: registered hairSystem name field + Hair / HairShape preset menu."""
    _mHair = cgmMeta.asMeta(mHair, noneValid=True)
    if not _mHair:
        return None
    _hs = RIGDYN._resolve_hair_system_shape(_mHair.mNode) or _mHair.mNode
    _mHair = cgmMeta.asMeta(_hs, noneValid=True) or _mHair
    if not getattr(self, '_md_hairSystemNameFields', None):
        self._md_hairSystemNameFields = {}

    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=5)
    _label = 'Hair system {0}:'.format(hair_idx)
    if mDefault and mDefault.mNode == _mHair.mNode:
        _label = '{0} (default)'.format(_label)
    mUI.MelLabel(_row, l=_label)
    _nameIF = mUI.MelTextField(
        _row,
        ann='HairSystem basename — renames to {name}_hairSys. Enter to apply.',
        text=RIGDYN.hair_system_name_token(_mHair),
        enterCommand=cgmGEN.Callback(uiFunc_apply_hair_system_name, self, _hs),
    )
    self._md_hairSystemNameFields[_hs] = _nameIF
    mUI.MelIconButton(
        _row,
        ann='Select hairSystem transform.',
        c=cgmGEN.Callback(uiFunc_select_item, _mHair.getTransform(asMeta=True)),
        **_dynfk_icon_btn_kw('select_25.png'),
    )
    _row.setStretchWidget(_nameIF)
    _presetMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    uiFunc_rebuild_hair_system_preset_menu(_presetMenu, _mHair.mNode, selfRef=self)
    _presetMenu(
        edit=True,
        ann='Hair: dynamic feel. Shape: width/clump/simulationMethod on this hairSystem.',
        cc=cgmGEN.Callback(uiFunc_process_hair_system_preset_change, self, _mHair.mNode, _presetMenu))
    mUI.MelSpacer(_row, w=5)
    _row.layout()
    return _nameIF


def uiFunc_select_details_map_target(self, kind):
    """Details map row — select nucleus, cloth, or default hair from live setup."""
    _str_func = 'uiFunc_select_details_map_target'
    if not self._mDynFK:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No setup loaded'))
    mCloth, mNucleus, mHair = uiFunc_setup_sim_targets(self)
    _kind = (kind or '').strip().lower()
    if _kind == 'nucleus':
        mObj = mNucleus
    elif _kind == 'cloth':
        mObj = mCloth
    elif _kind == 'hair':
        mObj = mHair
        if not mObj:
            mObj = RIGDYN.hair_system_get_default(self._mDynFK)
        if mObj and hasattr(mObj, 'getTransform'):
            mObj = mObj.getTransform(asMeta=True)
    else:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Unknown kind: {0}'.format(kind)))
    if not mObj:
        return log.warning(cgmGEN.logString_msg(_str_func, '{0} not mapped on setup'.format(_kind)))
    uiFunc_select_item(mObj)


def uiFunc_apply_setup_base_name(self, *args):
    """Rename ``{baseName}_dynFK`` from Details base name field (Apply or Enter)."""
    _str_func = 'uiFunc_apply_setup_base_name'
    if not self._mDynFK:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No setup loaded'))
    _field = getattr(self, 'details_baseNameField', None)
    if not _field:
        return
    try:
        _val = (_field.getValue() or '').strip()
    except Exception:
        _val = ''
    if not _val:
        try:
            _field.setValue(self._mDynFK.baseName or '')
        except Exception:
            pass
        return log.warning(cgmGEN.logString_msg(_str_func, 'Empty base name'))
    if _val == self._mDynFK.baseName:
        return
    if not self._mDynFK.set_base_name(_val):
        return
    uiFunc_updateTargetDisplay(self)
    uiFunc_update_details(self)


def uiFunc_make_load_row(
        parent, label, text, loadCommand, loadAnn,
        selfRef=None, statusAttr=None, selectCommand=None, leading_separator=True):
    """Label + status button + set / select — Project ``buildFrame_paths`` row."""
    if leading_separator:
        mUI.MelSeparator(parent, ut='cgmUISubTemplate', h=3)
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=5)
    mUI.MelLabel(_row, l=label)
    uiTF = mUI.MelLabel(
        _row,
        ut='cgmUIInstructionsTemplate',
        l=text,
        # h=20,
        bgc=_STATUS_ROW_HELP_BGC,
        ann=loadAnn,
        en=False,
    )
    if loadCommand:
        mUI.MelIconButton(
            parent=_row,
            ut='cgmUITemplate',
            style='iconOnly',
            image=os.path.join(cgmUI._path_imageFolder, 'set_25.png'),
            ann=loadAnn,
            bgc=cgmUI.guiButtonColor,
            c=loadCommand,
        )
    if selectCommand is not None:
        mUI.MelIconButton(
            _row,
            ann='Select mapped node.',
            c=selectCommand,
            **_dynfk_icon_btn_kw('select_25.png'),
        )
        
    _row.setStretchWidget(uiTF)
    mUI.MelSpacer(_row, w=5)
    _row.layout()
    if selfRef is not None and statusAttr:
        setattr(selfRef, statusAttr, uiTF)
    return uiTF


def uiFunc_update_create_panel_state(self):
    if not hasattr(self, 'btnAttachToCloth'):
        return

    if not self._mDynFK:
        self.btnAttachToCloth(e=True, en=False)
        if hasattr(self, 'clothSurfaceTrackMenu'):
            self.clothSurfaceTrackMenu(e=True, en=False)
        uiFunc_set_cloth_status_labels(self, False)
        return

    mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
    _hasCloth = bool(mCloth)
    self.btnAttachToCloth(e=True, en=_hasCloth)
    if hasattr(self, 'clothSurfaceTrackMenu'):
        self.clothSurfaceTrackMenu(e=True, en=_hasCloth)
    uiFunc_set_cloth_status_labels(self, mCloth)


def uiFunc_set_cloth_status_labels(self, mCloth=None):
    """Update Create + Details cloth status text."""
    _text = 'Not linked'
    if mCloth:
        _text = 'Linked: {0}'.format(mCloth.p_nameBase)
    if hasattr(self, 'uiClothStatusLabel'):
        self.uiClothStatusLabel(edit=True, l=_text)
    if hasattr(self, 'uiClothDetailsLabel'):
        self.uiClothDetailsLabel(
            edit=True,
            label=mCloth.p_nameBase if mCloth else 'Not mapped')


def uiFunc_init_sim_setup(self):
    """Create or complete cgmDynFK nucleus setup without Make Dynamic Chain."""
    _start = mc.playbackOptions(q=True, min=True)
    if self._mDynFK:
        self._mDynFK.setup_sim(startFrame=_start, applyPreset=True)
    else:
        mDynFK = RIGDYN.setup_sim_dynFK(
            baseName=_DEFAULT_DYNFK_BASE_NAME,
            startFrame=_start,
            applyPreset=True,
        )
        uiFunc_load_dyn_chain(self, mDynFK.p_nameBase)
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)


def uiFunc_map_cloth(self):
    if not self._mDynFK:
        return log.warning("Tools → Init Sim Setup or load a cgmDynFK setup first")
    result = RIGDYN.map_cloth_surface(self._mDynFK)
    if not result:
        result = RIGDYN.get_mapped_cloth(self._mDynFK)
    uiFunc_set_cloth_status_labels(self, result)
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    if not result:
        return


def uiFunc_map_nucleus(self):
    if not self._mDynFK:
        return log.warning("Tools → Init Sim Setup or load a cgmDynFK setup first")
    result = RIGDYN.map_nucleus(self._mDynFK)
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    if not result:
        return


_HAIR_SYSTEM_MENU_DEFAULT_SUFFIX = ' (default)'


def uiFunc_hair_system_default_menu_label(mHair=None):
    """Menu label for setup default hairSystem (always includes `` (default)``)."""
    if mHair:
        return '{0}{1}'.format(mHair.p_nameShort, _HAIR_SYSTEM_MENU_DEFAULT_SUFFIX)
    return 'Default{0}'.format(_HAIR_SYSTEM_MENU_DEFAULT_SUFFIX)


def uiFunc_hair_system_menu_value_to_mode(menu_val):
    """Map Create panel menu label → ``chain_create_hair`` hairSystemMode string."""
    _val = (menu_val or '').strip()
    if _val == 'New':
        return 'new'
    if _val.endswith(_HAIR_SYSTEM_MENU_DEFAULT_SUFFIX):
        return 'default'
    if _val == 'Default':
        return 'default'
    return _val


def uiFunc_refresh_hair_system_create_menu(self):
    """Rebuild Create → Hair system menu: New, then default (+ suffix), then other registered systems."""
    if not hasattr(self, 'options_hairSystemMode'):
        return
    _menu = self.options_hairSystemMode
    _current = (_menu.getValue() or '').strip()
    if _current == 'Default':
        _current = uiFunc_hair_system_default_menu_label(
            RIGDYN.hair_system_get_default(self._mDynFK) if self._mDynFK else None)

    _menu.clear()
    _menu.append('New')

    mDefault = RIGDYN.hair_system_get_default(self._mDynFK) if self._mDynFK else None
    _default_label = uiFunc_hair_system_default_menu_label(mDefault)
    _menu.append(_default_label)

    if self._mDynFK:
        for mHair in RIGDYN.hair_system_list_registered(self._mDynFK):
            if mDefault and mHair.mNode == mDefault.mNode:
                continue
            _menu.append(mHair.p_nameShort)

    try:
        _items = _menu.getItems()
    except Exception:
        _items = ['New', _default_label]

    _pick = None
    if _current in _items:
        _pick = _current
    else:
        _saved = (self.var_SimChainHairSystemMode.value or 'New').strip()
        if _saved == 'Default':
            _saved = _default_label
        if _saved in _items:
            _pick = _saved
        elif uiFunc_hair_system_menu_value_to_mode(_saved) == 'default':
            _pick = _default_label
    _menu.setValue(_pick if _pick else 'New')


def uiFunc_hair_system_create_mode(self):
    """Create panel hairSystemMode kw for chain_create_hair."""
    if not hasattr(self, 'options_hairSystemMode'):
        return 'default'
    return uiFunc_hair_system_menu_value_to_mode(self.options_hairSystemMode.getValue())


def uiFunc_hair_system_create_menu_label_for_chain(mSetup, mGrp):
    """Create panel Hair system menu label for a chain's mapped hairSystem."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    if not mSetup or not mGrp:
        return 'New'
    mHair = RIGDYN.hair_system_resolve_for_chain(mGrp, mSetup, backfill=True)
    if not mHair:
        return 'New'
    mDefault = RIGDYN.hair_system_get_default(mSetup)
    if mDefault and mHair.mNode == mDefault.mNode:
        return uiFunc_hair_system_default_menu_label(mDefault)
    return mHair.p_nameShort


def uiFunc_set_hair_system_create_menu_from_chain(self, mGrp):
    """Sync Create → Hair system enum to match a chain grp's hairSystem wiring."""
    if not hasattr(self, 'options_hairSystemMode'):
        return False
    uiFunc_refresh_hair_system_create_menu(self)
    _label = uiFunc_hair_system_create_menu_label_for_chain(self._mDynFK, mGrp)
    try:
        _items = self.options_hairSystemMode.getItems()
    except Exception:
        _items = []
    if _label not in _items:
        log.warning(cgmGEN.logString_msg(
            'uiFunc_set_hair_system_create_menu_from_chain',
            'Hair system menu missing {0!r} — refresh setup hair registry'.format(_label)))
        return False
    self.options_hairSystemMode.setValue(_label)
    return True


def uiFunc_map_chain_hair(self, chain):
    """Map selected hairSystem onto a hair chain (rewire follicle)."""
    if not self._mDynFK:
        return log.warning('Load a cgmDynFK setup first')
    mGrp = cgmMeta.asMeta(chain, noneValid=True)
    if not mGrp:
        return log.warning('Invalid chain')
    RIGDYN.chain_map_hair_system(mGrp, self._mDynFK)
    uiFunc_refresh_hair_system_create_menu(self)
    uiFunc_update_details(self)


def uiFunc_map_hair(self):
    if not self._mDynFK:
        return log.warning("Tools → Init Sim Setup or load a cgmDynFK setup first")
    result = RIGDYN.map_hair_system(self._mDynFK)
    uiFunc_refresh_hair_system_create_menu(self)
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    if not result:
        return


def uiFunc_attach_to_cloth(self):
    if not self._mDynFK:
        return log.warning("Tools → Init Sim Setup or load a cgmDynFK setup first")
    if not RIGDYN.get_mapped_cloth(self._mDynFK):
        return log.warning("Map cloth surface first (Details → Cloth <<)")
    RIGDYN.attach_to_cloth_dynFK(
        self._mDynFK,
        name=self.options_name.getValue(),
        objs=uiFunc_create_chain_target_metas(self),
    surfaceTrack=self.clothSurfaceTrackMenu.getValue() if hasattr(self, 'clothSurfaceTrackMenu') else 'follicle',
    )
    uiFunc_update_details(self)
    self.itemList.rebuild()


def _uiFunc_sim_dat_save_label_for_profile(profileKey):
    if profileKey == 'hs':
        return _SIM_DAT_MENU_SAVE_HAIR
    if profileKey == 'nc':
        return _SIM_DAT_MENU_SAVE_CLOTH
    if profileKey == 'n':
        return _SIM_DAT_MENU_SAVE_NUCLEUS
    return None


def uiFunc_rebuild_preset_menu(optionMenu, presetObj, selfRef=None):
    """Details dat menu — cgmDat/sim library for nucleus / hair / cloth targets."""
    _modes = _library_search_modes_get()
    optionMenu.clear()
    optionMenu.append(_SIM_DAT_MENU_LOAD)

    profileKey = uiFunc_get_profile_key_for_obj(presetObj)
    if not profileKey and selfRef is not None:
        profileKey = 'hs'

    if profileKey == 'hs':
        for _name, _fpath in uiFunc_library_items_for_kind('hair', 'cgmSimHairDat', modes=_modes):
            _label = _SIM_MENU_HAIR_PREFIX + _name
            uiFunc_library_register_preset_path(selfRef, _label, _fpath)
            optionMenu.append(_label)
        optionMenu.append('---')
        for _name, _fpath in uiFunc_library_items_for_kind(
                'hairShape', 'cgmSimHairShapeDat', modes=_modes):
            _label = _SIM_MENU_SHAPE_PREFIX + _name
            uiFunc_library_register_preset_path(selfRef, _label, _fpath)
            optionMenu.append(_label)
        optionMenu.append('---')
        optionMenu.append(_SIM_DAT_MENU_SAVE_HAIR)
        optionMenu.append(_SIM_DAT_MENU_SAVE_HAIR_SHAPE)
    elif profileKey == 'n':
        for _name, _fpath in uiFunc_library_items_for_kind(
                'nucleus', 'cgmSimNucleusDat', modes=_modes):
            uiFunc_library_register_preset_path(selfRef, _name, _fpath)
            optionMenu.append(_name)
        optionMenu.append('---')
        optionMenu.append(_SIM_DAT_MENU_SAVE_NUCLEUS)
    elif profileKey == 'nc':
        for _name, _fpath in uiFunc_library_items_for_kind(
                'cloth', 'cgmSimClothDat', modes=_modes):
            uiFunc_library_register_preset_path(selfRef, _name, _fpath)
            optionMenu.append(_name)
        optionMenu.append('---')
        optionMenu.append(_SIM_DAT_MENU_SAVE_CLOTH)
    optionMenu.setValue(_SIM_DAT_MENU_LOAD)


def uiFunc_process_preset_change(self, obj, optionMenu, presetChain=None):
    val = optionMenu.getValue()
    _mObj = cgmMeta.asMeta(obj, noneValid=True)
    _presetNode = _mObj.mNode if _mObj else obj
    mChain = cgmMeta.asMeta(presetChain, noneValid=True) if presetChain else None
    profileKey = uiFunc_get_profile_key_for_obj(obj)

    if val in (_SIM_DAT_MENU_LOAD, '---'):
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return

    if val == _SIM_DAT_MENU_SAVE_HAIR and profileKey == 'hs':
        uiFunc_sim_dat_capture_save_for_target(self, SIMDAT.SimHairDat, _presetNode)
        uiFunc_rebuild_preset_menu(optionMenu, obj, selfRef=self)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    if val == _SIM_DAT_MENU_SAVE_HAIR_SHAPE and profileKey == 'hs':
        if mChain:
            inst = SIMDAT.SimHairShapeDat()
            if inst.capture(mDynFK=self._mDynFK, mGrp=mChain):
                if inst.write(forcePrompt=True, startDirMode=_library_save_mode_get()):
                    log.info('Saved HairShape dat: {0}'.format(inst.str_filepath))
        else:
            uiFunc_sim_dat_capture_save_for_target(self, SIMDAT.SimHairShapeDat, _presetNode)
        uiFunc_rebuild_preset_menu(optionMenu, obj, selfRef=self)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return
    _saveLabel = _uiFunc_sim_dat_save_label_for_profile(profileKey)
    if _saveLabel and val == _saveLabel:
        _datClass = _SIM_PROFILE_DAT_CLASS.get(profileKey)
        if _datClass:
            uiFunc_sim_dat_capture_save_for_target(self, _datClass, _presetNode)
            uiFunc_rebuild_preset_menu(optionMenu, obj, selfRef=self)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return

    if profileKey == 'hs' and mChain and self._mDynFK:
        mHair = RIGDYN.hair_system_resolve_for_chain(mChain, self._mDynFK)
        if val.startswith(_SIM_MENU_HAIR_PREFIX) and mHair:
            uiFunc_library_apply_hair_to_target(
                self, val[len(_SIM_MENU_HAIR_PREFIX):], mHair.mNode, mGrp=None)
            optionMenu.setValue(_SIM_DAT_MENU_LOAD)
            return
        if val.startswith(_SIM_MENU_SHAPE_PREFIX):
            uiFunc_library_apply_hair_shape_to_target(
                self, val[len(_SIM_MENU_SHAPE_PREFIX):], mHair.mNode if mHair else None, mGrp=mChain)
            optionMenu.setValue(_SIM_DAT_MENU_LOAD)
            return

    _path = uiFunc_library_path_for_label(self, val)
    if _path:
        uiFunc_library_apply_by_path(self, _path)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return

    _datKind = uiFunc_library_dat_kind_for_name(val)
    if _datKind:
        if _datKind == 'hair' and mChain and self._mDynFK:
            mHair = RIGDYN.hair_system_resolve_for_chain(mChain, self._mDynFK)
            if mHair:
                uiFunc_library_apply_hair_to_target(self, val, mHair.mNode, mGrp=mChain)
            else:
                uiFunc_library_apply_by_name(self, _datKind, val)
        elif _datKind == 'hairShape' and mChain:
            uiFunc_library_apply_hair_shape_to_target(self, val, None, mGrp=mChain)
        else:
            uiFunc_library_apply_by_name(self, _datKind, val)
        optionMenu.setValue(_SIM_DAT_MENU_LOAD)
        return

    optionMenu.setValue(_SIM_DAT_MENU_LOAD)


def uiFunc_make_display_line(
        parent, label="", text="", button=False, buttonCommand=None, buttonInfo="",
        presetOptions=False, presetObj=None, selfRef=None, presetChain=None):
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)

    mUI.MelSpacer(_row, w=5)
    mUI.MelLabel(_row, l=label)

    uiTF = mUI.MelLabel(_row, ut='cgmUIInstructionsTemplate', l=text, en=True)

    if button and buttonCommand:
        mUI.MelIconButton(
            _row,
            ann=buttonInfo or 'Select.',
            c=buttonCommand,
            **_dynfk_icon_btn_kw('select_25.png'),
        )
    
    _row.setStretchWidget(uiTF)

    if presetOptions:
        presetMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
        uiFunc_rebuild_preset_menu(presetMenu, presetObj, selfRef=selfRef)
        presetMenu(edit=True,
            cc=cgmGEN.Callback(uiFunc_process_preset_change, selfRef, presetObj, presetMenu, presetChain))
        
    mUI.MelSpacer(_row, w=5)

    _row.layout()

    return uiTF

def uiFunc_reset_ui_no_setup(self):
    """Rebuild Details / Create panel state when nothing is loaded."""
    self._d_chainHairBuildMenus = {}
    if hasattr(self, 'itemList'):
        try:
            self.itemList.setItems([])
        except Exception:
            pass
    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    uiFunc_refresh_hair_system_create_menu(self)


def uiFunc_update_details(self, with_progress=False):
    if not getattr(self, 'detailsFrame', None):
        return
    if not self._mDynFK:
        self.detailsFrame.clear()
        _dynfk_build_details_empty_message(self.detailsFrame, 'No setup loaded...')
        mc.setParent(self.detailsFrame)
        self.detailsFrame(edit=True, collapse=True)
        uiFunc_set_cloth_status_labels(self, False)
        return

    ml_chains = self._mDynFK.msgList_get('chain') or []
    _progress_bar = None
    _cancelled = False

    def _details_progress(status, step=1):
        nonlocal _cancelled
        if _cancelled:
            return True
        if _dynfk_progress_step(_progress_bar, status, step):
            _cancelled = True
            return True
        return False

    if with_progress:
        _progress_bar = _dynfk_progress_begin(
            'cgmDynSimTool | loading setup…',
            max(3 + len(ml_chains), 1),
        )

    if _details_progress('Syncing chains…'):
        _dynfk_progress_end(_progress_bar)
        return

    RIGDYN.chain_fixup_duplicate_names(self._mDynFK)
    RIGDYN.chain_sync_chain_index_attrs(self._mDynFK)
    uiFunc_refresh_hair_system_create_menu(self)

    if _details_progress('Reading setup data…'):
        _dynfk_progress_end(_progress_bar)
        return

    self.detailsFrame.clear()

    dat = self._mDynFK.get_dat()

    if _details_progress('Building Details…'):
        _dynfk_progress_end(_progress_bar)
        return

    self.detailsFrame(edit=True, collapse=False)

    # Header column: subsection frames need this parent for white frame labels.
    _details = mUI.MelColumnLayout(
        self.detailsFrame, useTemplate='cgmUIHeaderTemplate', adj=True, rowSpacing=0)

    mNucleus = dat.get('mNucleus')

    _row = mUI.MelHSingleStretchLayout(_details, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Name: ', h=20)
    self.details_baseNameField = mUI.MelTextField(
        _row,
        ann='Setup base name — renames {name}_dynFK. Apply or Enter.',
        text=self._mDynFK.baseName or '',
        enterCommand=cgmGEN.Callback(uiFunc_apply_setup_base_name, self),
    )
    cgmUI.add_Button(
        _row,
        'Apply',
        cgmGEN.Callback(uiFunc_apply_setup_base_name, self),
        'Rename cgmDynFK setup transform to this base name.',
    )
    mUI.MelLabel(_row, l='Enabled:')
    _nucleus_on = True
    if mNucleus and mc.objExists(mNucleus.mNode) and mc.attributeQuery(
            'enable', node=mNucleus.mNode, exists=True):
        try:
            _nucleus_on = bool(mc.getAttr('{0}.enable'.format(mNucleus.mNode)))
        except Exception:
            pass
    self.nucleusEnabledCB = mUI.MelCheckBox(
        _row, en=True, v=_nucleus_on, label='',
        ann='Enable Nucleus')
    self.nucleusEnabledCB(
        edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_nucleus_enabled, self))
    _row.setStretchWidget(self.details_baseNameField)
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    mUI.MelSeparator(_details, ut='cgmUISubTemplate', h=3)

    # Nucleus / Cloth — map rows (tight pair, like chain hair + follicle)
    uiFunc_make_load_row(
        _details, 'Nucleus:',
        mNucleus.p_nameBase if mNucleus else 'Not mapped',
        cgmGEN.Callback(uiFunc_map_nucleus, self),
        "Map selected nucleus to this setup. Apply nucleus presets via Presets → Nucleus.",
        selectCommand=cgmGEN.Callback(uiFunc_select_details_map_target, self, 'nucleus'),
        leading_separator=False,
    )

    mCloth = dat.get('mCloth') or RIGDYN.get_mapped_cloth(self._mDynFK)
    uiFunc_make_load_row(
        _details, 'Cloth:',
        mCloth.p_nameBase if mCloth else 'Not mapped',
        cgmGEN.Callback(uiFunc_map_cloth, self),
        "Map selected nCloth to this setup. Apply cloth presets via Presets → Cloth.",
        selfRef=self, statusAttr='uiClothDetailsLabel',
        selectCommand=cgmGEN.Callback(uiFunc_select_details_map_target, self, 'cloth'),
        leading_separator=False,
    )

    _hairSystemsFrame = mUI.MelFrameLayout(
        _details, label='Hair systems', collapsable=True, collapse=False,
        useTemplate='cgmUIHeaderTemplate')
    _hairSystemsColumn = mUI.MelColumnLayout(
        _hairSystemsFrame, useTemplate='cgmUISubTemplate', adj=True, rowSpacing=0)
    mc.setParent(_hairSystemsColumn)
    self._md_hairSystemNameFields = {}

    mDefaultHair = dat.get('mHairSysShape')
    _ml_hs = dat.get('mHairSystems') or RIGDYN.hair_system_list_registered(self._mDynFK)
    if _ml_hs:
        for _hi, mHair in enumerate(_ml_hs, start=1):
            if mHair:
                uiFunc_make_hair_system_preset_row(self, _hairSystemsColumn, _hi, mHair, mDefaultHair)
        _defRow = mUI.MelHSingleStretchLayout(_hairSystemsColumn, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_defRow, w=_padding)
        mUI.MelLabel(_defRow, l='Default:')
        self.details_defaultHairSystemMenu = mUI.MelOptionMenu(_defRow, useTemplate='cgmUITemplate')
        _def_pick = 'Hair system 1'
        for _hi, mHair in enumerate(_ml_hs, start=1):
            if not mHair:
                continue
            _label = 'Hair system {0}'.format(_hi)
            self.details_defaultHairSystemMenu.append(_label)
            if mDefaultHair and mHair.mNode == mDefaultHair.mNode:
                _def_pick = _label
        self.details_defaultHairSystemMenu.setValue(_def_pick)
        self.details_defaultHairSystemMenu(
            edit=True,
            changeCommand=cgmGEN.Callback(uiFunc_set_setup_default_hair_system, self),
            ann='Setup default hairSystem (Presets → Hair and Create menu default).')
        _defRow.setStretchWidget(mUI.MelSeparator(_defRow))
        mUI.MelSpacer(_defRow, w=_padding)
        _defRow.layout()
        uiFunc_make_load_row(
            _hairSystemsColumn, 'Register:',
            'Selection → setup',
            cgmGEN.Callback(uiFunc_map_hair, self),
            'Map selected hairSystem onto setup (register + set default).',
            selectCommand=cgmGEN.Callback(uiFunc_select_details_map_target, self, 'hair'),
        )
    else:
        uiFunc_make_load_row(
            _hairSystemsColumn, 'Hair:',
            'None registered',
            cgmGEN.Callback(uiFunc_map_hair, self),
            'Map selected hairSystem on setup (registers + default).',
            selectCommand=cgmGEN.Callback(uiFunc_select_details_map_target, self, 'hair'),
        )

    # Baking -----------------------------------------------------------------
    _bakingFrame = mUI.MelFrameLayout(
        _details, label='Baking', collapsable=True, collapse=True, useTemplate='cgmUIHeaderTemplate')
    _bakingColumn = mUI.MelColumnLayout(
        _bakingFrame, useTemplate='cgmUIHeaderTemplate', adj=True, rowSpacing=0)
    mc.setParent(_bakingColumn)
    cgmUI.add_LineSubBreak()

    # Start Times

    _row = mUI.MelHSingleStretchLayout(_bakingColumn, ut='cgmUISubTemplate', padding=5)        

    mUI.MelSpacer(_row,w=_padding)

    mUI.MelLabel(_row, 
                 l='Start Time:')

    _row.setStretchWidget( mUI.MelSeparator(_row) )

    _nStart = dat['mNucleus'].startFrame if dat.get('mNucleus') else mc.playbackOptions(q=True, min=True)
    self.startTimeIF = mUI.MelIntField(_row, v=_nStart )
    self.startTimeIF(edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_start_time,self, mode='refresh'))
    
    cgmUI.add_Button(_row,'<<',
                     cgmGEN.Callback(uiFunc_set_start_time,self, mode='beginning'),
                     "Set Start To Beginning of Slider.")  

    mUI.MelSpacer(_row,w=_padding)
    
    _row.layout()


    # TimeInput Row ----------------------------------------------------------------------------------
    _row = mUI.MelHSingleStretchLayout(_bakingColumn, ut='cgmUISubTemplate')
    mUI.MelSpacer(_row, w=_padding)

    mUI.MelLabel(_row,l='Bake Time:')

    _row.setStretchWidget( mUI.MelSeparator(_row) )

    mUI.MelLabel(_row,l='Start:')

    self.uiFieldInt_start = mUI.MelIntField(_row,'cgmLocWinStartFrameField',
                                            width = 40)
    
    mUI.MelLabel(_row,l='End:')

    self.uiFieldInt_end = mUI.MelIntField(_row,'cgmLocWinEndFrameField',
                                          width = 40)
    
    cgmUI.add_Button(_row,'<<',
                     cgmGEN.Callback(uiFunc_updateTimeRange,self, 'min'),
                     "Set Start To Beginning of Slider.")  
    cgmUI.add_Button(_row,'[   ]',
                     cgmGEN.Callback(uiFunc_updateTimeRange,self, 'slider'),
                     "Set Time to Slider.")  
    cgmUI.add_Button(_row,'>>',
                     cgmGEN.Callback(uiFunc_updateTimeRange,self, 'max'),
                     "Set End To End of Slider.")  

    uiFunc_updateTimeRange(self, mode='slider')

    mUI.MelSpacer(_row, w=_padding)

    _row.layout()   

    mc.setParent(_bakingColumn)
    cgmUI.add_LineSubBreak()

    allTargets = []
    for idx in dat['chains']:
        allTargets += dat['chains'][idx]['mTargets']

    _row = mUI.MelHSingleStretchLayout(_bakingColumn, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Bake')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    cgmUI.add_Button(
        _row, 'All Inputs',
        cgmGEN.Callback(uiFunc_bake_input, self, None),
        'Animate targets, then bake to input joints (inCurve drivers). '
        'Loc→target connect is cleared automatically if needed. Then run sim. '
        'After sim, Connect + Bake Targets.')
    cgmUI.add_Button(
        _row, 'All Targets',
        cgmGEN.Callback(uiFunc_bake, self, 'target', allTargets),
        'Bake all target joints on every chain.')
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _row = mUI.MelHSingleStretchLayout(_bakingColumn, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Connect')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    cgmUI.add_Button(
        _row, 'Connect All',
        cgmGEN.Callback(uiFunc_connect_targets, self),
        'Connect all target joints on every chain.')
    cgmUI.add_Button(
        _row, 'Disconnect All',
        cgmGEN.Callback(uiFunc_disconnect_targets, self),
        'Disconnect all target joints on every chain.')
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    mc.setParent(_details)
    cgmUI.add_LineSubBreak()

    # Chains
    self._d_chainHairBuildMenus = {}
    self._d_chainNameFields = {}
    _chainsFrame = mUI.MelFrameLayout(
        _details, label='Chains', collapsable=True, collapse=False, useTemplate='cgmUIHeaderTemplate')
    _chainsColumn = mUI.MelColumnLayout(
        _chainsFrame, useTemplate='cgmUIHeaderTemplate', adj=True, rowSpacing=0)
    for i, chain in enumerate(ml_chains):
        if _details_progress(
                'Chain {0}: {1}'.format(i, RIGDYN.chain_cgm_name(chain) or chain.p_nameShort)):
            _dynfk_progress_end(_progress_bar)
            return
        _chainLabel = uiFunc_chain_section_label(i, chain)
        _chainHeaderBgc = cgmUI.guiButtonColor if MATH.is_even(i) else cgmUI.guiBackgroundColor
        chainFrame = mUI.MelFrameLayout(
            _chainsColumn, label=_chainLabel, collapsable=True, collapse=True,
            useTemplate='cgmUIHeaderTemplate', bgc=_chainHeaderBgc)
        
        _chainColumn = mUI.MelColumnLayout(
            chainFrame, useTemplate='cgmUIHeaderTemplate', bgc=cgmUI.guiBackgroundColor)

        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        _chainMode = getattr(chain, 'chainMode', None) or 'hair'
        _missing_integrity = RIGDYN._hair_chain_integrity_missing(chain)
        _b_broken = bool(_missing_integrity)
        if _b_broken:
            log.warning(cgmGEN.logString_msg(
                'uiFunc_update_details',
                'Broken chain {0} — missing {1}'.format(
                    chain.p_nameBase, ', '.join(_missing_integrity))))
            chainFrame(edit=True, label='{0}  [BROKEN — incomplete build]'.format(_chainLabel),
                       collapse=False)

        mc.setParent(_chainColumn)
        if _b_broken:
            _warnRow = mUI.MelHSingleStretchLayout(
                _chainColumn, ut='cgmUISubTemplate', padding=_padding, bgc=(0.45, 0.2, 0.2))
            mUI.MelSpacer(_warnRow, w=_padding)
            mUI.MelLabel(
                _warnRow, l='Incomplete chain — missing: {0}'.format(', '.join(_missing_integrity)),
                ut='cgmUISubTemplate', align='left')
            _warnRow.setStretchWidget(mUI.MelSeparator(_warnRow))
            cgmUI.add_Button(
                _warnRow, 'Delete broken chain',
                cgmGEN.Callback(uiFunc_delete_chain, self, i, True),
                'Remove this chain grp from the setup (failed or partial create).')
            mUI.MelSpacer(_warnRow, w=_padding)
            _warnRow.layout()
            cgmUI.add_LineSubBreak()

        cgmUI.add_LineSubBreak()

        if _chainMode == 'clothAttach':
            mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
            clothLabel = mCloth.p_nameBase if mCloth else '—'
            uiFunc_make_display_line(
                _chainColumn, label='Driver Cloth:', text=clothLabel, button=bool(mCloth),
                buttonCommand=cgmGEN.Callback(uiFunc_select_item, mCloth.p_nameBase) if mCloth else None,
                buttonInfo="Mapped setup cloth.")
            _surfaceTrack = getattr(chain, 'surfaceTrack', None) or 'follicle'
            uiFunc_make_display_line(
                _chainColumn, label='Surface track:', text=_surfaceTrack, button=False)
            uiFunc_make_display_line(
                _chainColumn, label='Mode:', text='clothAttach', button=False)
        else:
            mHairChain = RIGDYN.hair_system_resolve_for_chain(chain, self._mDynFK)
            _hs_label = mHairChain.p_nameShort if mHairChain else '—'
            uiFunc_make_load_row(
                _chainColumn, 'Hair system:',
                _hs_label,
                cgmGEN.Callback(uiFunc_map_chain_hair, self, chain),
                'Map selected hairSystem to this chain (rewire follicle).',
            )
            mFollicle = chain.getMessageAsMeta('mFollicle')
            if mFollicle:
                uiFunc_make_load_row(
                    _chainColumn,
                    'Follicle:',
                    mFollicle.p_nameShort,
                    None,
                    'Follicle for this chain.',
                    selectCommand=cgmGEN.Callback(uiFunc_select_item, mFollicle),
                    leading_separator=False,
                )
        
        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        _row = mUI.MelHSingleStretchLayout(_chainColumn, ut='cgmUISubTemplate', padding=5)
        mUI.MelSpacer(_row, w=_padding)
        mUI.MelLabel(_row, l='Name:')
        _nameIF = mUI.MelTextField(
            _row,
            ann='Per-chain name token. Edit then click Apply (does not rename on every keystroke).',
            text=RIGDYN.chain_cgm_name(chain))
        self._d_chainNameFields[i] = _nameIF
        cgmUI.add_Button(
            _row, 'Apply',
            cgmGEN.Callback(uiFunc_set_chain_name, self, i),
            'Rename chain group and hair infrastructure to this name.')
        mUI.MelIconButton(
            _row,
            ann='Select chain group transform.',
            c=cgmGEN.Callback(uiFunc_select_item, chain.p_nameBase),
            **_dynfk_icon_btn_kw('select_25.png'),
        )
        _row.setStretchWidget(_nameIF)
        mUI.MelSpacer(_row, w=_padding)
        _row.layout()

        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        if _chainMode != 'clothAttach' and not _b_broken:
            _row = mUI.MelHSingleStretchLayout(_chainColumn,ut='cgmUISubTemplate',padding = 5)

            mUI.MelSpacer(_row,w=_padding)                          
            mUI.MelLabel(_row,l='Orient Up:')  

            _row.setStretchWidget( mUI.MelSeparator(_row) )

            chainDirections = []
            _chain_fwd = getattr(chain, 'fwd', None) or 'z+'
            for dir in ['x+', 'x-', 'y+', 'y-', 'z+', 'z-']:
                if _chain_fwd[0] != dir[0]:
                    chainDirections.append(dir)
            chainDirections.append('None')
           
            upMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
            for dir in chainDirections:
                upMenu.append(dir)

            upMenu.setValue(getattr(chain, 'up', None) or 'y+')

            upMenu(edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_chain_up,self,i,upMenu))

            mUI.MelSpacer(_row,w=_padding)

            _row.layout()

        if _chainMode != 'clothAttach' and not _b_broken:
            _menus = uiFunc_chain_hair_build_opts_row(self, _chainColumn, chain, chainIdx=i)
            self._d_chainHairBuildMenus[i] = _menus
            mc.setParent(_chainColumn)
            cgmUI.add_LineSubBreak()

        if not _b_broken:
            if _chainMode != 'clothAttach':
                _row = mUI.MelHSingleStretchLayout(_chainColumn, ut='cgmUISubTemplate', padding=5)
                mUI.MelSpacer(_row, w=_padding)
                mUI.MelLabel(_row, l='Input')
                _row.setStretchWidget(mUI.MelSeparator(_row))
                cgmUI.add_Button(
                    _row, 'Bake',
                    cgmGEN.Callback(uiFunc_bake_input, self, i),
                    'Bake target animation onto input joints (inCurve). '
                    'Clears loc→target connect if needed; use Connect for output.')
                mUI.MelSpacer(_row, w=_padding)
                _row.layout()

            _row = mUI.MelHSingleStretchLayout(_chainColumn, ut='cgmUISubTemplate', padding=5)
            mUI.MelSpacer(_row, w=_padding)
            mUI.MelLabel(_row, l='Targets')
            _row.setStretchWidget(mUI.MelSeparator(_row))
            cgmUI.add_Button(
                _row, 'Bake',
                cgmGEN.Callback(uiFunc_bake, self, 'target', chain.msgList_get('mTargets')),
                'Bake target joints on this chain.')
            cgmUI.add_Button(
                _row, 'Connect',
                cgmGEN.Callback(uiFunc_connect_targets, self, i),
                'Connect target joints on this chain.')
            cgmUI.add_Button(
                _row, 'Disconnect',
                cgmGEN.Callback(uiFunc_disconnect_targets, self, i),
                'Disconnect target joints on this chain.')
            mUI.MelSpacer(_row, w=_padding)
            _row.layout()

            _row = mUI.MelHSingleStretchLayout(_chainColumn, ut='cgmUISubTemplate', padding=5)
            mUI.MelSpacer(_row, w=_padding)
            mUI.MelLabel(_row, l='Chain')
            _row.setStretchWidget(mUI.MelSeparator(_row))
            if _chainMode != 'clothAttach':
                _followMode = RIGDYN._get_chain_hair_follow_mode(chain)
                if _followMode == RIGDYN.HAIR_FOLLOW_MODE_SPLINE:
                    _rebuildAnn = (
                        'At frame before sim start: rebuild inCurve, follicle outCurve, '
                        'driven joints, spline IK, and locators.')
                else:
                    _rebuildAnn = (
                        'Re-sync outCurve rest at startFrame and rebuild POC/aim locators on current outCurve.')
                cgmUI.add_Button(
                    _row, 'Rebuild',
                    cgmGEN.Callback(uiFunc_rebuild_chain_follow, self, i),
                    _rebuildAnn)
            cgmUI.add_Button(
                _row, 'Delete',
                cgmGEN.Callback(uiFunc_delete_chain, self, i, _b_broken),
                'Remove this chain from the setup.')
            mUI.MelSpacer(_row, w=_padding)
            _row.layout()

        if _b_broken:
            continue

        if _chainMode == 'clothAttach':
            _surfaceTrack = getattr(chain, 'surfaceTrack', None) or 'follicle'
            frameDat = [['Targets', 'mTargets'],
                        ['Locators', 'mLocs']]
            if _surfaceTrack == 'rivet':
                frameDat.append(['Rivets', 'mRivets'])
            elif _surfaceTrack == 'uvPin':
                frameDat.append(['UV Pins', 'mUvPins'])
            else:
                frameDat.append(['Mesh Follicles', 'mMeshFollicles'])
        else:
            _followMode = RIGDYN._get_chain_hair_follow_mode(chain)
            frameDat = [['Targets', 'mTargets'],
                        ['Locators','mLocs'],
                        ['Joint Chain', 'mObjJointChain']]
            if _followMode == RIGDYN.HAIR_FOLLOW_MODE_SPLINE:
                frameDat.append(['Driven Joints', 'mDrivenJointChain'])
            else:
                frameDat.extend([['Aims', 'mAims'],
                                 ['Parents', 'mParents']])

        mc.setParent(_chainColumn)
        _listColumn = mUI.MelColumnLayout(_chainColumn, useTemplate='cgmUIHeaderTemplate', adj=True)
        _listBgc = cgmUI.guiBackgroundColor
        for _fi, dat in enumerate(frameDat):
            _headerBgc = cgmUI.guiButtonColor if MATH.is_even(_fi) else cgmUI.guiBackgroundColor
            frame = mUI.MelFrameLayout(
                _listColumn, label=dat[0], collapsable=True, collapse=True,
                enable=True, bgc=_headerBgc)
            column = mUI.MelColumnLayout(frame, bgc=_listBgc, adj=True, height=75)
            row = mUI.MelHSingleStretchLayout(column, ut='cgmUITemplate', padding=_padding)

            mUI.MelSpacer(row, w=_padding)

            itemList = uiFunc_create_selection_list(
                row, [x.p_nameShort for x in chain.msgList_get(dat[1])])

            mUI.MelSpacer(row, w=_padding)

            row.setStretchWidget(itemList)

            row.layout()

    # End Chains

    mc.setParent(_details)
    cgmUI.add_LineSubBreak()
    _dynfk_progress_end(_progress_bar)

def uiFunc_delete_chain(self, idx, confirmIfBroken=False):
    if not self._mDynFK:
        return
    ml = self._mDynFK.msgList_get('chain') or []
    if idx >= len(ml):
        return
    mGrp = ml[idx]
    _missing = RIGDYN._hair_chain_integrity_missing(mGrp)
    if _missing and confirmIfBroken:
        _confirm = mc.confirmDialog(
            title='Delete broken chain?',
            message=(
                'Chain "{0}" is incomplete (missing: {1}).\n\n'
                'Delete the chain group and remove it from this setup?').format(
                mGrp.p_nameBase, ', '.join(_missing)),
            button=['Delete', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel')
        if _confirm != 'Delete':
            return
    elif _missing:
        log.warning(cgmGEN.logString_msg(
            'uiFunc_delete_chain',
            'Removing incomplete chain {0} — missing {1}'.format(
                mGrp.p_nameBase, ', '.join(_missing))))
    self._mDynFK.chain_deleteByIdx(idx)
    uiFunc_update_details(self)

def uiFunc_connect_targets(self, idx=None):
    self._mDynFK.targets_connect(idx)

def uiFunc_disconnect_targets(self, idx=None):
    self._mDynFK.targets_disconnect(idx)

def uiFunc_query_settings(self):
    """Query selected sim nodes and print a profile diff for cgmSim*Dat capture."""
    _str_func = 'uiFunc_query_settings'

    _dat = NCLOTH.query_settings_selection()
    if not _dat and self._mDynFK:
        mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
        if mCloth:
            _dat = NCLOTH.query_settings(mCloth.mNode)
            _dat.setdefault('source', {})['cgmDynFK'] = self._mDynFK.mNode

    if not _dat:
        log.warning("|{0}| >> Select nCloth, nucleus, hair system, or cgmDynFK setup".format(_str_func))
        return

    log.info(cgmGEN.logString_sub(_str_func, 'Query Settings'))
    log.info("|{0}| >> sourceType: {1}".format(_str_func, _dat.get('sourceType')))
    if _dat.get('suggestedPresetName'):
        log.info("|{0}| >> suggestedPresetName: {1}".format(_str_func, _dat.get('suggestedPresetName')))

    cgmGEN.print_dict(_dat.get('source') or {}, 'source', __name__)
    cgmGEN.print_dict(_dat.get('profile') or {}, 'profile (diff from base)', __name__)

    for _note in _dat.get('notes') or []:
        log.info("|{0}| >> note: {1}".format(_str_func, _note))

    print('\n# --- Paste-ready preset block (capture via Presets → Save * Dat…) ---\n')
    print(_dat.get('paste') or '')
    print('\n# --- profile dict (paste to agent / preset work) ---\n')
    pprint.pprint(_dat.get('profile') or {}, width=120, sort_dicts=True)


def uiFunc_set_chain_name(self, idx, *args):
    if not self._mDynFK:
        return
    _field = (getattr(self, '_d_chainNameFields', None) or {}).get(idx)
    _val = ''
    if _field:
        try:
            _val = _field.getValue()
        except Exception:
            pass
    _val = (_val or '').strip()
    ml = self._mDynFK.msgList_get('chain') or []
    if idx >= len(ml):
        return
    mGrp = ml[idx]
    _current = RIGDYN.chain_cgm_name(mGrp)
    if not _val:
        if _field:
            _field.setValue(_current)
        return
    if _val == _current:
        return
    if not RIGDYN.chain_set_name(self._mDynFK, idx, _val):
        if _field:
            _field.setValue(_current)
        return
    mc.evalDeferred(cgmGEN.Callback(uiFunc_update_details, self), lp=True)


def uiFunc_set_chain_up(self, idx, upMenu):
    #print "Changing up on %s to %s" % ( chain.p_nameBase, upMenu.getValue() )
    axis = upMenu.getValue()
    if axis == 'None':
        axis = None
    else:
        axis = VALID.simpleAxis(axis)
    self._mDynFK.chain_setOrientUpByIdx(idx, axis)

# mode - 'target' (Bake Targets output path)
def uiFunc_bake(self, mode, mObjs):
    if not self._mDynFK:
        return
    if mode != 'target':
        return log.warning('uiFunc_bake | Use Bake Input for input joints (uiFunc_bake_input)')
    self._mDynFK.bake_nodes(
        mObjs,
        self.uiFieldInt_start.getValue(),
        self.uiFieldInt_end.getValue(),
    )


def uiFunc_bake_input(self, idx=None):
    if not self._mDynFK:
        return
    RIGDYN.chain_bake_input_from_targets(
        self._mDynFK,
        self.uiFieldInt_start.getValue(),
        self.uiFieldInt_end.getValue(),
        idx=idx,
    )


def uiFunc_updateTimeRange(self, which='slider', mode='slider'):
    _range = SEARCH.get_time(mode)
    if _range:
        if which == "min":
            self.uiFieldInt_start(edit = True, value = _range[0])
        elif which == "max":
            self.uiFieldInt_end(edit = True, value = _range[1])
        elif which == "slider":
            self.uiFieldInt_start(edit = True, value = _range[0])
            self.uiFieldInt_end(edit = True, value = _range[1])

def uiFunc_select_item(item):
    try:
        item = item.mNode
    except AttributeError:
        pass
    if item:
        mc.select(item)

def uiFunc_select_list_item(listElement):
    mc.select( listElement.getSelectedItems() )

def uiFunc_create_selection_list(parent, items):
    itemList = cgmUI.cgmScrollList(parent, numberOfRows = 4, height=75)
    itemList.setItems(items)
    itemList(edit=True, selectCommand=cgmGEN.Callback(uiFunc_select_list_item,itemList))

    return itemList

def uiFunc_set_nucleus_enabled(self):
    mNucleus = self._mDynFK.getMessageAsMeta('mNucleus') if self._mDynFK else None
    if not mNucleus:
        return
    mc.setAttr('%s.enable' % mNucleus.mNode, self.nucleusEnabledCB.getValue())

def uiFunc_set_start_time(self,mode):
    if not self._mDynFK:
        return
    mNucleus = self._mDynFK.get_dat().get('mNucleus')
    if not mNucleus:
        return
    if mode == 'beginning':
        self.startTimeIF(e=True, v=mc.playbackOptions(q=True, min=True))
    mNucleus.startFrame = self.startTimeIF(q=True, v=True)

def uiFunc_list_function(uiElement, command):
    allItems = uiElement.getItems()
    selectedItems = uiElement.getSelectedItems()

    if command == "add selected":
        uiElement.rebuild()        
        uiElement.setItems( allItems + mc.ls(sl=True) )
    elif command == "remove selected":
        uiElement.rebuild()
        newList = []
        for item in allItems:
            if item not in selectedItems:
                newList.append( item )
        uiElement.setItems( newList )
    elif command == "clear":
        uiElement.rebuild()

def uiFunc_sync_follicle_segment_options(self):
    _en = bool(self.options_fixedSegmentLengthCB.getValue())
    if _en:
        self.options_follicleSegmentLength(
            edit=True, enable=True, editable=True,
            bgc=SHARED._d_gui_state_colors.get('normal'))
    else:
        self.options_follicleSegmentLength(
            edit=True, enable=True, editable=False,
            bgc=SHARED._d_gui_state_colors.get('help'))
    if hasattr(self, 'options_follicleSampleDensity'):
        if _en:
            self.options_follicleSampleDensity(
                edit=True, enable=True, editable=False,
                bgc=SHARED._d_gui_state_colors.get('help'))
        else:
            self.options_follicleSampleDensity(
                edit=True, enable=True, editable=True,
                bgc=SHARED._d_gui_state_colors.get('normal'))

def uiFunc_hair_create_sample_density_options(self):
    """Create Hair default sampleDensity (new chains only — not live)."""
    if hasattr(self, 'options_fixedSegmentLengthCB') and bool(self.options_fixedSegmentLengthCB.getValue()):
        return RIGDYN.FOLLICLE_DEFAULT_SAMPLE_DENSITY
    if not hasattr(self, 'options_follicleSampleDensity'):
        return RIGDYN.FOLLICLE_DEFAULT_SAMPLE_DENSITY
    try:
        return max(0.01, min(10.0, float(self.options_follicleSampleDensity.getValue() or 1.0)))
    except (TypeError, ValueError):
        try:
            return max(0.01, min(10.0, float(self.var_SimChainFollicleSampleDensity.value or 1.0)))
        except (TypeError, ValueError):
            return RIGDYN.FOLLICLE_DEFAULT_SAMPLE_DENSITY

def uiFunc_chain_sample_density_ensure_start_frame(self, mGrp):
    """Timeline at hair startFrame before live sampleDensity tweaks."""
    mDynFK = getattr(self, '_mDynFK', None)
    if not mDynFK:
        return
    _startFrame = RIGDYN._resolve_hair_start_frame(mDynFK, mGrp=cgmMeta.asMeta(mGrp))
    _cur = mc.currentTime(q=True)
    if abs(_cur - _startFrame) > 0.001:
        mc.currentTime(_startFrame, edit=True)

def uiFunc_chain_follicle_sample_density_apply(self, mGrp, sampleDensity):
    """Live follicle.sampleDensity for one hair chain grp."""
    mGrp = cgmMeta.asMeta(mGrp)
    try:
        _val = float(sampleDensity)
    except (TypeError, ValueError):
        _val = RIGDYN.FOLLICLE_DEFAULT_SAMPLE_DENSITY
    _val = max(0.01, min(10.0, _val))
    mGrp.doStore('follicleSampleDensity', _val)
    if bool(getattr(mGrp, 'fixedSegmentLength', False)):
        return _val
    mFoll = mGrp.getMessageAsMeta('mFollicle')
    if not mFoll:
        return _val
    for mShape in mFoll.getShapes(asMeta=True) or []:
        _shape = mShape.mNode
        if mc.attributeQuery('sampleDensity', node=_shape, exists=True):
            mc.setAttr('{0}.sampleDensity'.format(_shape), _val)
    return _val

def uiFunc_chain_sync_sample_density_widgets(self, densityField, densitySlider, value):
    if getattr(self, '_follicleSampleDensityUiSync', False):
        return
    try:
        _val = float(value)
    except (TypeError, ValueError):
        _val = RIGDYN.FOLLICLE_DEFAULT_SAMPLE_DENSITY
    _val = max(0.01, min(10.0, _val))
    self._follicleSampleDensityUiSync = True
    try:
        if densitySlider:
            densitySlider.setValue(_val)
        if densityField:
            densityField.setValue(_val)
    finally:
        self._follicleSampleDensityUiSync = False

def uiFunc_chain_sample_density_from_slider(self, mGrp, densityField, densitySlider, *args):
    if not densitySlider:
        return
    uiFunc_chain_sample_density_ensure_start_frame(self, mGrp)
    uiFunc_chain_sync_sample_density_widgets(
        self, densityField, densitySlider, densitySlider.getValue())
    uiFunc_chain_follicle_sample_density_apply(self, mGrp, densitySlider.getValue())

def uiFunc_chain_sample_density_from_field(self, mGrp, densityField, densitySlider, *args):
    if not densityField:
        return
    uiFunc_chain_sample_density_ensure_start_frame(self, mGrp)
    uiFunc_chain_sync_sample_density_widgets(
        self, densityField, densitySlider, densityField.getValue())
    uiFunc_chain_follicle_sample_density_apply(self, mGrp, densityField.getValue())

def uiFunc_hair_follicle_segment_options(self):
    _fixed = bool(self.options_fixedSegmentLengthCB.getValue())
    _seg = RIGDYN.FOLLICLE_FIXED_SEGMENT_LENGTH
    if _fixed:
        try:
            _seg = float(self.options_follicleSegmentLength.getValue() or _seg)
        except (TypeError, ValueError):
            pass
    return _fixed, _seg

_HAIR_FOLLOW_UI_TO_MODE = {
    'Spline IK': RIGDYN.HAIR_FOLLOW_MODE_SPLINE,
    'Legacy': RIGDYN.HAIR_FOLLOW_MODE_LEGACY,
}
_HAIR_FOLLOW_MODE_TO_UI = {
    RIGDYN.HAIR_FOLLOW_MODE_SPLINE: 'Spline IK',
    RIGDYN.HAIR_FOLLOW_MODE_LEGACY: 'Legacy',
}

def uiFunc_persist_simchain_create_optionvars(self):
    """Remember last Create Chain hair follow / degree picks."""
    if not hasattr(self, 'options_hairFollowMode'):
        return
    self.var_SimChainHairFollowMode.setValue(self.options_hairFollowMode.getValue())
    self.var_SimChainInCurveDegree.setValue(self.options_inCurveDegree.getValue())
    self.var_SimChainOutCurveDegree.setValue(self.options_outCurveDegree.getValue())
    if hasattr(self, 'options_addEndJointDistance'):
        self.var_SimChainAddEndJointDistance.setValue(self.options_addEndJointDistance.getValue())
    if hasattr(self, 'options_addEndJointCB'):
        self.var_SimChainAddEndJointEnabled.setValue(
            '1' if bool(self.options_addEndJointCB.getValue()) else '0')
    if hasattr(self, 'options_curveExtendEndDistance'):
        self.var_SimChainExtendEndDistance.setValue(self.options_curveExtendEndDistance.getValue())
    if hasattr(self, 'options_curveExtendEndCB'):
        self.var_SimChainExtendEndEnabled.setValue(
            '1' if bool(self.options_curveExtendEndCB.getValue()) else '0')
    if hasattr(self, 'options_advancedTwistCB'):
        self.var_SimChainAdvancedTwistEnabled.setValue(
            '1' if bool(self.options_advancedTwistCB.getValue()) else '0')
    if hasattr(self, 'options_follicleSampleDensity'):
        self.var_SimChainFollicleSampleDensity.setValue(self.options_follicleSampleDensity.getValue())
    if hasattr(self, 'options_hairSystemMode'):
        self.var_SimChainHairSystemMode.setValue(self.options_hairSystemMode.getValue())
    uiFunc_sync_add_end_joint_options(self)
    uiFunc_sync_curve_extend_end_options(self)

def uiFunc_restore_simchain_create_optionvars(self):
    if not hasattr(self, 'options_hairFollowMode'):
        return
    _follow = self.var_SimChainHairFollowMode.value or 'Spline IK'
    _in = self.var_SimChainInCurveDegree.value or '1'
    _out = self.var_SimChainOutCurveDegree.value or '2'
    if _follow in _HAIR_FOLLOW_UI_TO_MODE:
        self.options_hairFollowMode.setValue(_follow)
    if str(_in) in ('1', '2', '3'):
        self.options_inCurveDegree.setValue(str(_in))
    if str(_out) in ('1', '2', '3'):
        self.options_outCurveDegree.setValue(str(_out))
    if hasattr(self, 'options_addEndJointCB'):
        _ext_on = str(self.var_SimChainAddEndJointEnabled.value or '0').strip().lower() in (
            '1', 'true', 'yes', 'on')
        self.options_addEndJointCB.setValue(_ext_on)
    _ext = self.var_SimChainAddEndJointDistance.value or '2.0'
    if hasattr(self, 'options_addEndJointDistance'):
        self.options_addEndJointDistance.setValue(str(_ext))
        uiFunc_sync_add_end_joint_options(self)
    if hasattr(self, 'options_curveExtendEndCB'):
        _cvex_on = str(self.var_SimChainExtendEndEnabled.value or '0').strip().lower() in (
            '1', 'true', 'yes', 'on')
        self.options_curveExtendEndCB.setValue(_cvex_on)
    _cvex = self.var_SimChainExtendEndDistance.value or '1.0'
    if hasattr(self, 'options_curveExtendEndDistance'):
        self.options_curveExtendEndDistance.setValue(str(_cvex))
        uiFunc_sync_curve_extend_end_options(self)
    if hasattr(self, 'options_advancedTwistCB'):
        _atw = str(self.var_SimChainAdvancedTwistEnabled.value or '0').strip().lower() in (
            '1', 'true', 'yes', 'on')
        self.options_advancedTwistCB.setValue(_atw)
    if hasattr(self, 'options_follicleSampleDensity'):
        self.options_follicleSampleDensity.setValue(
            str(self.var_SimChainFollicleSampleDensity.value or '1.0'))
    if hasattr(self, 'options_hairSystemMode'):
        uiFunc_refresh_hair_system_create_menu(self)
        _hs_mode = (self.var_SimChainHairSystemMode.value or 'New').strip()
        try:
            _items = self.options_hairSystemMode.getItems()
        except Exception:
            _items = ['New']
        if _hs_mode == 'Default':
            _hs_mode = uiFunc_hair_system_default_menu_label(
                RIGDYN.hair_system_get_default(self._mDynFK) if self._mDynFK else None)
        if _hs_mode in _items:
            self.options_hairSystemMode.setValue(_hs_mode)
    uiFunc_sync_follicle_segment_options(self)

def uiFunc_sync_add_end_joint_options(self):
    if not hasattr(self, 'options_addEndJointCB'):
        return
    _on = bool(self.options_addEndJointCB.getValue())
    self.options_addEndJointDistance(edit=True, editable=_on)
    self.options_addEndJointDistance(edit=True, bgc=SHARED._d_gui_state_colors.get('normal' if _on else 'help'))

def uiFunc_hair_add_end_joint_required(self):
    """True when Create Chain UI has Add end joint checked."""
    if not hasattr(self, 'options_addEndJointCB'):
        return False
    try:
        return bool(int(self.options_addEndJointCB.getValue()))
    except (TypeError, ValueError):
        return bool(self.options_addEndJointCB.getValue())

def uiFunc_hair_add_end_joint_options(self):
    """Return addEndJoint for chain_create: False or numeric tip offset."""
    if not uiFunc_hair_add_end_joint_required(self):
        return False
    try:
        return float(self.options_addEndJointDistance.getValue())
    except (TypeError, ValueError):
        try:
            return float(self.var_SimChainAddEndJointDistance.value or 2.0)
        except (TypeError, ValueError):
            return 2.0

def uiFunc_sync_curve_extend_end_options(self):
    if not hasattr(self, 'options_curveExtendEndCB'):
        return
    _on = bool(self.options_curveExtendEndCB.getValue())
    self.options_curveExtendEndDistance(edit=True, editable=_on)
    self.options_curveExtendEndDistance(edit=True, bgc=SHARED._d_gui_state_colors.get('normal' if _on else 'help'))

def uiFunc_hair_curve_extend_end_required(self):
    if not hasattr(self, 'options_curveExtendEndCB'):
        return False
    try:
        return bool(int(self.options_curveExtendEndCB.getValue()))
    except (TypeError, ValueError):
        return bool(self.options_curveExtendEndCB.getValue())

def uiFunc_hair_advanced_twist_options(self):
    """Return advancedTwist bool for chain_create (spline IK only in backend)."""
    if hasattr(self, 'options_advancedTwistCB'):
        return bool(self.options_advancedTwistCB.getValue())
    return str(self.var_SimChainAdvancedTwistEnabled.value or '0').strip().lower() in (
        '1', 'true', 'yes', 'on')

def uiFunc_hair_curve_extend_end_options(self):
    """Return extendEnd for chain_create: False or numeric curve tip offset."""
    if not uiFunc_hair_curve_extend_end_required(self):
        return False
    try:
        return float(self.options_curveExtendEndDistance.getValue())
    except (TypeError, ValueError):
        try:
            return float(self.var_SimChainExtendEndDistance.value or 1.0)
        except (TypeError, ValueError):
            return 1.0

def uiFunc_chain_add_end_joint_from_grp(chain):
    """Read addEndJoint enabled + distance from chain grp attrs."""
    _v = RIGDYN._hair_add_end_joint_from_grp(chain)
    if not RIGDYN._hair_add_end_joint_active(_v):
        return False, 2.0
    if isinstance(_v, bool):
        return True, 2.0
    try:
        return True, float(_v)
    except (TypeError, ValueError):
        return True, 2.0

def uiFunc_chain_add_end_joint_apply(mGrp, extendCB, extendField):
    mGrp = cgmMeta.asMeta(mGrp)
    if extendCB.getValue():
        try:
            mGrp.doStore('addEndJoint', float(extendField.getValue()))
        except (TypeError, ValueError):
            mGrp.doStore('addEndJoint', 2.0)
    else:
        mGrp.doStore('addEndJoint', False)

def uiFunc_chain_curve_extend_end_from_grp(chain):
    _v = RIGDYN._hair_curve_extend_end_from_grp(chain)
    if not RIGDYN._hair_curve_extend_end_active(_v):
        return False, 1.0
    if isinstance(_v, bool):
        return True, 1.0
    try:
        return True, float(_v)
    except (TypeError, ValueError):
        return True, 1.0

def uiFunc_chain_curve_extend_end_apply(mGrp, extendCB, extendField):
    mGrp = cgmMeta.asMeta(mGrp)
    if extendCB.getValue():
        try:
            mGrp.doStore('extendEnd', float(extendField.getValue()))
        except (TypeError, ValueError):
            mGrp.doStore('extendEnd', 1.0)
    else:
        mGrp.doStore('extendEnd', False)

def uiFunc_chain_advanced_twist_row(self, parent, chain):
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Advanced twist:')
    advancedTwistCB = mUI.MelCheckBox(
        _row, v=RIGDYN._hair_advanced_twist_from_grp(chain), label='',
        ann='Spline IK advanced twist (Object Rotation Up Start/End). Rebuild Chain to apply.')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()
    return advancedTwistCB

def uiFunc_chain_advanced_twist_apply(mGrp, advancedTwistCB):
    mGrp = cgmMeta.asMeta(mGrp)
    mGrp.doStore('advancedTwist', bool(advancedTwistCB.getValue()))

def uiFunc_chain_push_build_to_create_options(self, chainIdx):
    """Copy per-chain hair build settings into Create panel + optionVars."""
    _str_func = 'uiFunc_chain_push_build_to_create_options'
    if not self._mDynFK:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No setup loaded'))
    if not hasattr(self, 'options_hairFollowMode'):
        return log.warning(cgmGEN.logString_msg(_str_func, 'Create panel not built'))
    ml = self._mDynFK.msgList_get('chain') or []
    if chainIdx >= len(ml):
        return log.warning(cgmGEN.logString_msg(_str_func, 'No chain at idx {0}'.format(chainIdx)))
    chain = ml[chainIdx]
    if getattr(chain, 'chainMode', None) == 'clothAttach':
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hair chain'))

    _menus = getattr(self, '_d_chainHairBuildMenus', {}).get(chainIdx)
    if _menus:
        followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField, densityField, densitySlider, advancedTwistCB = _menus
        uiFunc_chain_hair_build_opts_apply(
            self, chain, followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField,
            densityField, densitySlider, advancedTwistCB)
        self.options_hairFollowMode.setValue(followMenu.getValue())
        self.options_inCurveDegree.setValue(inMenu.getValue())
        self.options_outCurveDegree.setValue(outMenu.getValue())
        if extendCB is not None and extendField is not None:
            self.options_addEndJointCB.setValue(bool(extendCB.getValue()))
            self.options_addEndJointDistance.setValue(extendField.getValue())
        if curveExtCB is not None and curveExtField is not None:
            self.options_curveExtendEndCB.setValue(bool(curveExtCB.getValue()))
            self.options_curveExtendEndDistance.setValue(curveExtField.getValue())
        if advancedTwistCB is not None and hasattr(self, 'options_advancedTwistCB'):
            self.options_advancedTwistCB.setValue(bool(advancedTwistCB.getValue()))
        if densityField is not None and not bool(getattr(chain, 'fixedSegmentLength', False)):
            self.options_follicleSampleDensity.setValue(str(densityField.getValue()))
    else:
        _mode = RIGDYN._get_chain_hair_follow_mode(chain)
        self.options_hairFollowMode.setValue(_HAIR_FOLLOW_MODE_TO_UI.get(_mode, 'Spline IK'))
        if chain.hasAttr('inCurveDegree'):
            self.options_inCurveDegree.setValue(str(int(chain.inCurveDegree)))
        if chain.hasAttr('outCurveDegree'):
            self.options_outCurveDegree.setValue(str(int(chain.outCurveDegree)))
        _enabled, _dist = uiFunc_chain_add_end_joint_from_grp(chain)
        if hasattr(self, 'options_addEndJointCB'):
            self.options_addEndJointCB.setValue(_enabled)
        if hasattr(self, 'options_addEndJointDistance'):
            self.options_addEndJointDistance.setValue(str(_dist))
        _cvex_on, _cvex_dist = uiFunc_chain_curve_extend_end_from_grp(chain)
        if hasattr(self, 'options_curveExtendEndCB'):
            self.options_curveExtendEndCB.setValue(_cvex_on)
        if hasattr(self, 'options_curveExtendEndDistance'):
            self.options_curveExtendEndDistance.setValue(str(_cvex_dist))
        if hasattr(self, 'options_advancedTwistCB'):
            self.options_advancedTwistCB.setValue(RIGDYN._hair_advanced_twist_from_grp(chain))
        if hasattr(self, 'options_follicleSampleDensity'):
            _sd = RIGDYN._resolve_follicle_sample_density(chain, self._mDynFK)
            self.options_follicleSampleDensity.setValue(str(_sd))

    if hasattr(self, 'options_fixedSegmentLengthCB'):
        _fixed = bool(getattr(chain, 'fixedSegmentLength', False))
        self.options_fixedSegmentLengthCB.setValue(_fixed)
        if hasattr(self, 'options_follicleSegmentLength') and chain.hasAttr('follicleSegmentLength'):
            self.options_follicleSegmentLength.setValue(str(chain.follicleSegmentLength))
        uiFunc_sync_follicle_segment_options(self)

    uiFunc_sync_add_end_joint_options(self)
    uiFunc_sync_curve_extend_end_options(self)
    uiFunc_set_hair_system_create_menu_from_chain(self, chain)
    uiFunc_persist_simchain_create_optionvars(self)
    log.info(cgmGEN.logString_msg(
        _str_func, 'Create options updated from chain {0}'.format(chain.p_nameBase)))


def uiFunc_chain_hair_build_opts_apply(self, mGrp, followMenu, inMenu, outMenu, extendCB=None, extendField=None,
                                       curveExtCB=None, curveExtField=None,
                                       densityField=None, densitySlider=None, advancedTwistCB=None):
    """Write per-chain build menus onto chain grp attrs (used before rebuild)."""
    mGrp = cgmMeta.asMeta(mGrp)
    _mode = _HAIR_FOLLOW_UI_TO_MODE.get(followMenu.getValue(), RIGDYN.HAIR_FOLLOW_MODE_SPLINE)
    try:
        _in = int(inMenu.getValue())
    except (TypeError, ValueError):
        _in = 1
    try:
        _out = int(outMenu.getValue())
    except (TypeError, ValueError):
        _out = 2
    mGrp.doStore('hairFollowMode', _mode)
    mGrp.doStore('inCurveDegree', MATH.Clamp(_in, 1, 3))
    mGrp.doStore('outCurveDegree', MATH.Clamp(_out, 1, 3))
    if extendCB is not None and extendField is not None:
        uiFunc_chain_add_end_joint_apply(mGrp, extendCB, extendField)
    if curveExtCB is not None and curveExtField is not None:
        uiFunc_chain_curve_extend_end_apply(mGrp, curveExtCB, curveExtField)
    if advancedTwistCB is not None:
        uiFunc_chain_advanced_twist_apply(mGrp, advancedTwistCB)
    if densitySlider is not None:
        uiFunc_chain_follicle_sample_density_apply(self, mGrp, densitySlider.getValue())
    elif densityField is not None:
        uiFunc_chain_follicle_sample_density_apply(self, mGrp, densityField.getValue())

def uiFunc_chain_hair_build_opts_changed(self, mGrp, followMenu, inMenu, outMenu, extendCB=None, extendField=None,
                                         curveExtCB=None, curveExtField=None,
                                         densityField=None, densitySlider=None, advancedTwistCB=None):
    uiFunc_chain_hair_build_opts_apply(
        self, mGrp, followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField,
        densityField, densitySlider, advancedTwistCB)
    self.var_SimChainHairFollowMode.setValue(followMenu.getValue())
    self.var_SimChainInCurveDegree.setValue(inMenu.getValue())
    self.var_SimChainOutCurveDegree.setValue(outMenu.getValue())
    if hasattr(self, 'options_hairFollowMode'):
        self.options_hairFollowMode.setValue(followMenu.getValue())
        self.options_inCurveDegree.setValue(inMenu.getValue())
        self.options_outCurveDegree.setValue(outMenu.getValue())

        self.options_outCurveDegree.setValue(outMenu.getValue())
    if extendField is not None:
        self.var_SimChainAddEndJointDistance.setValue(extendField.getValue())
        if hasattr(self, 'options_addEndJointDistance'):
            self.options_addEndJointDistance.setValue(extendField.getValue())
    if curveExtField is not None:
        self.var_SimChainExtendEndDistance.setValue(curveExtField.getValue())
        if hasattr(self, 'options_curveExtendEndDistance'):
            self.options_curveExtendEndDistance.setValue(curveExtField.getValue())

def uiFunc_chain_add_end_joint_row(self, parent, chain):
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Add end joint:')
    _enabled, _dist = uiFunc_chain_add_end_joint_from_grp(chain)
    extendCB = mUI.MelCheckBox(
        _row, v=_enabled, label='',
        ann='Tip sim joint past last target along last segment (last segment bend).')
    extendField = mUI.MelTextField(_row, w=50, text=str(_dist),
        editable=_enabled,
        bgc=SHARED._d_gui_state_colors.get('normal' if _enabled else 'help'))
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()
    return extendCB, extendField

def uiFunc_chain_curve_extend_end_row(self, parent, chain):
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Extend end:')
    _enabled, _dist = uiFunc_chain_curve_extend_end_from_grp(chain)
    curveExtCB = mUI.MelCheckBox(
        _row, v=_enabled, label='',
        ann='Extra inCurve CV past chain end (after add-end joint when on).')
    curveExtField = mUI.MelTextField(_row, w=50, text=str(_dist),
        editable=_enabled,
        bgc=SHARED._d_gui_state_colors.get('normal' if _enabled else 'help'))
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()
    return curveExtCB, curveExtField

def uiFunc_chain_hair_build_opts_row(self, parent, chain, chainIdx=0):
    """Per-chain build / rebuild options (stored on chain grp)."""
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Build:')
    followMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate',
        ann='Follow mode for this chain (rebuild uses these settings).')
    for _label in ('Spline IK', 'Legacy'):
        followMenu.append(_label)
    _mode = RIGDYN._get_chain_hair_follow_mode(chain)
    followMenu.setValue(_HAIR_FOLLOW_MODE_TO_UI.get(_mode, 'Spline IK'))

    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='In deg:')
    inMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for _d in ('1', '2', '3'):
        inMenu.append(_d)
    if chain.hasAttr('inCurveDegree'):
        inMenu.setValue(str(int(chain.inCurveDegree)))
    else:
        inMenu.setValue(self.var_SimChainInCurveDegree.value or '1')

    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Out deg:')
    outMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate')
    for _d in ('1', '2', '3'):
        outMenu.append(_d)
    if chain.hasAttr('outCurveDegree'):
        outMenu.setValue(str(int(chain.outCurveDegree)))
    else:
        outMenu.setValue(self.var_SimChainOutCurveDegree.value or '2')

    _row.setStretchWidget(mUI.MelSeparator(_row))
    cgmUI.add_Button(
        _row, 'Push Settings to Build Menu',
        cgmGEN.Callback(uiFunc_chain_push_build_to_create_options, self, chainIdx),
        'Copy this chain hair build settings to Create options (use on another setup).')
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    _extRow = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_extRow, w=_padding)
    mUI.MelLabel(_extRow, l='Advanced twist:')
    advancedTwistCB = mUI.MelCheckBox(
        _extRow, v=RIGDYN._hair_advanced_twist_from_grp(chain), label='',
        ann='Spline IK advanced twist (Object Rotation Up Start/End). Rebuild Chain to apply.')
    _extRow.setStretchWidget(mUI.MelSeparator(_extRow))
    mUI.MelLabel(_extRow, l='Add end joint:')
    _enabled, _dist = uiFunc_chain_add_end_joint_from_grp(chain)
    extendCB = mUI.MelCheckBox(
        _extRow, v=_enabled, label='',
        ann='Tip sim joint past last target along last segment (last segment bend).')
    extendField = mUI.MelTextField(
        _extRow, w=50, text=str(_dist),
        editable=_enabled,
        bgc=SHARED._d_gui_state_colors.get('normal' if _enabled else 'help'))
    mUI.MelSpacer(_extRow, w=_padding)
    mUI.MelLabel(_extRow, l='Extend end:')
    _cex_on, _cex_dist = uiFunc_chain_curve_extend_end_from_grp(chain)
    curveExtCB = mUI.MelCheckBox(
        _extRow, v=_cex_on, label='',
        ann='Extra inCurve CV past chain end (after add-end joint when on).')
    curveExtField = mUI.MelTextField(
        _extRow, w=50, text=str(_cex_dist),
        editable=_cex_on,
        bgc=SHARED._d_gui_state_colors.get('normal' if _cex_on else 'help'))
    mUI.MelSpacer(_extRow, w=_padding)
    _extRow.layout()

    _sdVal = RIGDYN._resolve_follicle_sample_density(chain, getattr(self, '_mDynFK', None))
    _sdFixed = bool(getattr(chain, 'fixedSegmentLength', False))
    _sdRow = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_sdRow, w=_padding)
    mUI.MelLabel(_sdRow, l='Sample density:')
    densityField = mUI.MelFloatField(
        _sdRow, w=50, value=_sdVal, enable=not _sdFixed,
        ann='Follicle sampleDensity for this chain (live; rebuild uses stored value).')
    densitySlider = mUI.MelFloatSlider(
        _sdRow, 0.1, 10.0, defaultValue=_sdVal, value=_sdVal, step=0.1, enable=not _sdFixed)
    _sdRow.setStretchWidget(densitySlider)
    mUI.MelSpacer(_sdRow, w=_padding)
    _sdRow.layout()
    densityField(
        edit=True,
        cc=cgmGEN.Callback(
            uiFunc_chain_sample_density_from_field, self, chain, densityField, densitySlider))
    densitySlider(
        edit=True,
        cc=cgmGEN.Callback(
            uiFunc_chain_sample_density_from_slider, self, chain, densityField, densitySlider),
        dragCommand=cgmGEN.Callback(
            uiFunc_chain_sample_density_from_slider, self, chain, densityField, densitySlider))

    _cb = cgmGEN.Callback(
        uiFunc_chain_hair_build_opts_ui_changed,
        self, chain, followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField,
        densityField, densitySlider, advancedTwistCB)
    followMenu(edit=True, changeCommand=_cb)
    inMenu(edit=True, changeCommand=_cb)
    outMenu(edit=True, changeCommand=_cb)
    extendCB(edit=True, changeCommand=_cb)
    extendField(edit=True, changeCommand=_cb)
    curveExtCB(edit=True, changeCommand=_cb)
    curveExtField(edit=True, changeCommand=_cb)
    advancedTwistCB(edit=True, changeCommand=_cb)
    return followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField, densityField, densitySlider, advancedTwistCB

def uiFunc_chain_hair_build_opts_ui_changed(self, mGrp, followMenu, inMenu, outMenu, extendCB, extendField,
                                            curveExtCB=None, curveExtField=None,
                                            densityField=None, densitySlider=None, advancedTwistCB=None):
    _on = bool(extendCB.getValue())
    extendField(edit=True, editable=_on)
    extendField(edit=True, bgc=SHARED._d_gui_state_colors.get('normal' if _on else 'help'))
    if curveExtCB is not None and curveExtField is not None:
        _cex = bool(curveExtCB.getValue())
        curveExtField(edit=True, editable=_cex)
        curveExtField(edit=True, bgc=SHARED._d_gui_state_colors.get('normal' if _cex else 'help'))
    uiFunc_chain_hair_build_opts_changed(
        self, mGrp, followMenu, inMenu, outMenu, extendCB, extendField, curveExtCB, curveExtField,
        densityField, densitySlider, advancedTwistCB)

def uiFunc_hair_follow_options(self):
    """Create Options: hair follow mode and in/out curve degrees."""
    _mode = _HAIR_FOLLOW_UI_TO_MODE.get(
        self.options_hairFollowMode.getValue(), RIGDYN.HAIR_FOLLOW_MODE_SPLINE)
    try:
        _inDeg = int(self.options_inCurveDegree.getValue())
    except (TypeError, ValueError):
        _inDeg = 1
    try:
        _outDeg = int(self.options_outCurveDegree.getValue())
    except (TypeError, ValueError):
        _outDeg = 2
    return _mode, MATH.Clamp(_inDeg, 1, 3), MATH.Clamp(_outDeg, 1, 3)

def uiFunc_rebuild_chain_follow(self, chainIdx=None):
    _str_func = 'uiFunc_rebuild_chain_follow'
    if not self._mDynFK:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No setup loaded'))
    if chainIdx is not None:
        _menus = getattr(self, '_d_chainHairBuildMenus', {}).get(chainIdx)
        _ml = self._mDynFK.msgList_get('chain') or []
        if _menus and chainIdx < len(_ml):
            uiFunc_chain_hair_build_opts_apply(self, _ml[chainIdx], *_menus)
    if self._mDynFK.chain_rebuild_hair(chainIdx):
        uiFunc_update_details(self)

def uiFunc_select_nucleus(self):
    mNucleus = self._mDynFK.getMessageAsMeta('mNucleus') if self._mDynFK else None
    if not mNucleus:
        mNucleus = (self._mDynFK.get_dat() or {}).get('mNucleus') if self._mDynFK else None
    if mNucleus:
        mc.select(mNucleus.mNode)

def uiFunc_create_chain_target_metas(self):
    """Create Chain list → target metas (scroll list stores path strings only)."""
    return cgmMeta.asMeta(self.itemList.getItems(), noneValid=True) or []

def uiFunc_make_dynamic_chain(self):
    _fixedSeg, _segLen = uiFunc_hair_follicle_segment_options(self)
    _sampleDensity = uiFunc_hair_create_sample_density_options(self)
    _followMode, _inDeg, _outDeg = uiFunc_hair_follow_options(self)
    _addEndJoint = uiFunc_hair_add_end_joint_options(self)
    _extendEnd = uiFunc_hair_curve_extend_end_options(self)
    _advancedTwist = uiFunc_hair_advanced_twist_options(self)
    _requireAddEndJoint = uiFunc_hair_add_end_joint_required(self)
    _cb_raw = None
    if hasattr(self, 'options_addEndJointCB'):
        _cb_raw = self.options_addEndJointCB.getValue()
    _dist_raw = None
    if hasattr(self, 'options_addEndJointDistance'):
        _dist_raw = self.options_addEndJointDistance.getValue()
    _hair_sys_mode = uiFunc_hair_system_create_mode(self)
    log.info(cgmGEN.logString_msg(
        'uiFunc_make_dynamic_chain',
        'hairSystemMode={0!r} addEndJoint={1!r} extendEnd={2!r}'.format(
            _hair_sys_mode, _addEndJoint, _extendEnd)))
    log.info(cgmGEN.logString_msg(
        'uiFunc_make_dynamic_chain',
        'UI addEndJoint CB raw={0!r} required={1} distance raw={2!r} -> addEndJoint={3!r} extendEnd={4!r}'.format(
            _cb_raw, _requireAddEndJoint, _dist_raw, _addEndJoint, _extendEnd)))
    ml_targets = uiFunc_create_chain_target_metas(self)
    if not self._mDynFK:
        mDynFK = RIGDYN.cgmDynFK(
            baseName=_DEFAULT_DYNFK_BASE_NAME,
            name=self.options_name.getValue(),
            objs=ml_targets,
            fwd=self.fwdMenu.getValue(),
            up=self.upMenu.getValue(),
            startFrame=mc.playbackOptions(q=True, min=True),
            fixedSegmentLength=_fixedSeg,
            follicleSegmentLength=_segLen,
            follicleSampleDensity=_sampleDensity,
            hairFollowMode=_followMode,
            inCurveDegree=_inDeg,
            outCurveDegree=_outDeg,
            addEndJoint=_addEndJoint,
            extendEnd=_extendEnd,
            requireAddEndJoint=_requireAddEndJoint,
            advancedTwist=_advancedTwist,
            hairSystemMode=_hair_sys_mode)
        mDynFK.profile_load('base')
        uiFunc_load_dyn_chain(self, mDynFK.p_nameBase)
        uiFunc_refresh_hair_system_create_menu(self)
    else:
        self._mDynFK.chain_create(
            name=self.options_name.getValue(),
            objs=ml_targets,
            fwd=self.fwdMenu.getValue(),
            up=self.upMenu.getValue(),
            fixedSegmentLength=_fixedSeg,
            follicleSegmentLength=_segLen,
            follicleSampleDensity=_sampleDensity,
            hairFollowMode=_followMode,
            inCurveDegree=_inDeg,
            outCurveDegree=_outDeg,
            addEndJoint=_addEndJoint,
            extendEnd=_extendEnd,
            requireAddEndJoint=_requireAddEndJoint,
            advancedTwist=_advancedTwist,
            hairSystemMode=_hair_sys_mode)
        uiFunc_update_details(self)
        uiFunc_refresh_hair_system_create_menu(self)

    if self._mDynFK and hasattr(self, 'options_name'):
        _ml = self._mDynFK.msgList_get('chain') or []
        if _ml:
            self.options_name.setValue(RIGDYN.chain_cgm_name(_ml[-1]))

    uiFunc_persist_simchain_create_optionvars(self)
    self.itemList.rebuild()

def uiFunc_last_dynfk_resolve(self):
    """Return cgmDynFK node string from LastDynFK optionVar if it still exists."""
    _name = (self.var_LastDynFK.value or '').strip()
    if not _name or not mc.objExists(_name):
        return None
    try:
        mObj = cgmMeta.asMeta(_name)
        if mObj.mClass == 'cgmDynFK':
            return mObj.mNode
    except Exception:
        pass
    return None

def uiFunc_last_dynfk_store(self, mDynFK=None):
    """Persist last loaded cgmDynFK transform (long name) for next tool open."""
    if mDynFK and hasattr(mDynFK, 'mNode'):
        self.var_LastDynFK.setValue(mDynFK.mNode)
    else:
        self.var_LastDynFK.setValue('')

def uiFunc_load_dyn_chain(self, chain, with_progress=False):
    _str_func = 'uiFunc_load_dyn_chain'  

    self._mDynFK = False

    mDynFK = RIGDYN.cgmDynFK(chain)

    #Get our raw data
    try:
        if mDynFK.mClass == 'cgmDynFK':
            _short = mDynFK.p_nameBase            
            log.debug("|{0}| >> Target: {1}".format(_str_func, _short))
            self._mDynFK = mDynFK
    except:
        log.warning("|{0}| >> Nothing selected.".format(_str_func))            
        uiFunc_clear_loaded(self)

    if self._mDynFK:
        uiFunc_updateTargetDisplay(self, with_progress=with_progress)
        uiFunc_last_dynfk_store(self, self._mDynFK)
        uiFunc_refresh_hair_system_create_menu(self)

    #uiFunc_updateFields(self)
    #self.uiReport_do()
    #self.uiFunc_updateScrollAttrList()

def uiFunc_load_selected(self, bypassAttrCheck = False):
    _str_func = 'uiFunc_load_selected'  

    uiFunc_load_dyn_chain(self, mc.ls(sl=True)[0], with_progress=True)

def uiFunc_select_loaded_setup(self):
    _str_func = 'uiFunc_select_loaded_setup'
    if not self._mDynFK:
        return log.warning("|{0}| >> No cgmDynFK setup loaded".format(_str_func))
    mc.select(self._mDynFK.mNode, replace=True)


def uiFunc_clear_loaded(self):
    _str_func = 'uiFunc_clear_loaded'
    self._mDynFK = False
    uiFunc_last_dynfk_store(self, None)
    if getattr(self, 'uiTF_objLoad', None):
        self.uiTF_objLoad(edit=True, l='No setup', en=True)
    uiFunc_reset_ui_no_setup(self)


def uiFunc_updateTargetDisplay(self, with_progress=False):
    _str_func = 'uiFunc_updateTargetDisplay'  
    #self.uiScrollList_parents.clear()

    if not self._mDynFK:
        log.info("|{0}| >> No target.".format(_str_func))                        
        #No obj
        self.uiTF_objLoad(edit=True, l='No setup', en=True)
        self._mGroup = False

        #for o in self._l_toEnable:
            #o(e=True, en=False)

        return

    _short = self._mDynFK.p_nameBase
    _display = _short
    if len(_display) > 20:
        _display = _display[:20] + '...'
    self.uiTF_objLoad(edit=True, l=_display, ann=_short, en=True)

    uiFunc_update_details(self, with_progress=with_progress)
    uiFunc_update_create_panel_state(self)
    
    return


 