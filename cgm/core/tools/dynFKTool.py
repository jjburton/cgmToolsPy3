"""
------------------------------------------
dynFKTool : cgm.core.tools
Author: David Bokser
email: dbokser@cgmonks.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
cgmSimChain tool
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
from cgm.lib import lists
from cgm.core.lib import search_utils as SEARCH

import cgm.core.rig.dynamic_utils as RIGDYN
import cgm.core.presets.cgmDynFK_presets as dynFKPresets
import cgm.core.lib.nCloth_utils as NCLOTH

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='cgmSimChain'

_padding = 5

def reload_dependencies():
    """Reload cgmSimChain backend modules via cgmGEN._reloadMod."""
    import cgm.core.rig.constraint_utils as RIGCONSTRAINTS
    import cgm.core.lib.node_utils as NODES
    import cgm.core.presets.cgmNCloth_presets as nClothPresets
    for _mod in (RIGDYN, RIGCONSTRAINTS, NODES, NCLOTH, dynFKPresets, nClothPresets):
        cgmGEN._reloadMod(_mod)

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE = 550,350
    TOOLNAME = '{0}.ui'.format(__toolname__)
    
    _mDynFK = False

    def insert_init(self,*args,**kws):
        _str_func = '__init__[{0}]'.format(self.__class__.TOOLNAME)            
        log.info("|{0}| >>...".format(_str_func))        

        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))
        log.info(self.__call__(q=True, title=True))

        self.__version__ = __version__
        self.__toolName__ = self.__class__.WINDOW_NAME	

        #self.l_allowedDockAreas = []
        self.WINDOW_TITLE = self.__class__.WINDOW_TITLE
        self.DEFAULT_SIZE = self.__class__.DEFAULT_SIZE

    def reload(self):
        reload_dependencies()
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()
 
    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc = cgmGEN.Callback(self.buildMenu_first))
        self.uiMenu_PresetsMenu = mUI.MelMenu(l='Presets', pmc = cgmGEN.Callback(self.buildMenu_presets))
        self.uiMenu_ToolsMenu = mUI.MelMenu(l='Tools', pmc = cgmGEN.Callback(self.buildMenu_tools))

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
        """Cloth / Nucleus / Hair cascading preset loads."""
        self.uiMenu_PresetsMenu.clear()
        uiFunc_build_presets_menu(self, self.uiMenu_PresetsMenu)

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        #>>> Reset Options		                     

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )

        self.uiMenu_buildDock(self.uiMenu_FirstMenu)


        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reload",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))
        
    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper'
        #self._d_uiCheckBoxes = {}
    
        #_MainForm = mUI.MelFormLayout(parent,ut='cgmUISubTemplate')
        _MainForm = mUI.MelFormLayout(self,ut='cgmUITemplate')
        _column = buildColumn_main(self,_MainForm,True)

    
        _row_cgm = cgmUI.add_cgmFooter(_MainForm)            
        _MainForm(edit = True,
                  af = [(_column,"top",0),
                        (_column,"left",0),
                        (_column,"right",0),                        
                        (_row_cgm,"left",0),
                        (_row_cgm,"right",0),                        
                        (_row_cgm,"bottom",0),
    
                        ],
                  ac = [(_column,"bottom",2,_row_cgm),
                        ],
                  attachNone = [(_row_cgm,"top")])          
    
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
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUIHeaderTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUIHeaderTemplate') 
    

    #>>>Objects Load Row ---------------------------------------------------------------------------------------
    
    mUI.MelSeparator(_inside,ut='cgmUISubTemplate',h=3)

    _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5)        

    mUI.MelSpacer(_row,w=_padding)

    mUI.MelLabel(_row, 
                 l='Dynamic Chain System:')

    uiTF_objLoad = mUI.MelLabel(_row,ut='cgmUIInstructionsTemplate',l='',
                                en=True)

    self.uiTF_objLoad = uiTF_objLoad
    cgmUI.add_Button(_row,'<<',
                     cgmGEN.Callback(uiFunc_load_selected,self),
                     "Load first selected object.")  
    _row.setStretchWidget(uiTF_objLoad)
    mUI.MelSpacer(_row,w=_padding)

    _row.layout()

    mc.setParent(_inside)
    cgmUI.add_LineSubBreak()

    self.detailsFrame = mUI.MelFrameLayout(_inside, label="Details", collapsable=True, collapse=True,useTemplate = 'cgmUIHeaderTemplate')

    uiFunc_update_details(self)

    # Create Frame

    self.createFrame = mUI.MelFrameLayout(_inside, label="Create", collapsable=True, collapse=False,useTemplate = 'cgmUIHeaderTemplate')

    _create = mUI.MelColumnLayout(self.createFrame,useTemplate = 'cgmUIHeaderTemplate') 

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

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_create,ut='cgmUISubTemplate',padding = 5)
    mUI.MelSpacer(_row,w=_padding)
    mUI.MelLabel(_row, l='Cloth:')
    self.uiClothStatusLabel = mUI.MelLabel(_row, ut='cgmUIInstructionsTemplate', l='Not linked')
    _row.setStretchWidget(self.uiClothStatusLabel)
    mUI.MelSpacer(_row,w=_padding)
    _row.layout()

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_create, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Cloth track:')
    self.clothSurfaceTrackMenu = mUI.MelOptionMenu(_row, useTemplate='cgmUITemplate', ann='Mesh tracker for cloth attach (follicle, rivet, or uvPin).')
    for _track in ('follicle', 'rivet', 'uvPin'):
        self.clothSurfaceTrackMenu.append(_track)
    self.clothSurfaceTrackMenu.setValue('follicle')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    cgmUI.add_LineSubBreak()

    _row = mUI.MelHSingleStretchLayout(_create,ut='cgmUISubTemplate',padding = 5)

    mUI.MelSpacer(_row,w=_padding)

    self.btnMakeDynamicChain = cgmUI.add_Button(_row,'Make Dynamic Chain',
                     cgmGEN.Callback(uiFunc_make_dynamic_chain,self),
                     "Make dynamic hair/curve chain (makeCurvesDynamic).")

    mUI.MelSpacer(_row,w=_padding)

    self.btnAttachToCloth = cgmUI.add_Button(_row,'Attach to Cloth',
                     cgmGEN.Callback(uiFunc_attach_to_cloth,self),
                     "Attach joint chain to mapped nCloth. Locators under follicle/rivet/uvPin drive Connect Targets.")
    self.btnAttachToCloth(e=True, en=False)

    _row.setStretchWidget( self.btnMakeDynamicChain )

    mUI.MelSpacer(_row,w=_padding)

    _row.layout()

    uiFunc_update_create_panel_state(self)

    cgmUI.add_LineSubBreak()

    self.optionsFrame = mUI.MelFrameLayout(_create, label="Options", collapsable=True, collapse=True,useTemplate = 'cgmUIHeaderTemplate')

    _options = mUI.MelColumnLayout(self.optionsFrame,useTemplate = 'cgmUISubTemplate') 

    mUI.MelSeparator(_options,ut='cgmUISubTemplate',h=5)

    _row = mUI.MelHSingleStretchLayout(_options,ut='cgmUISubTemplate',padding = 5)

    mUI.MelSpacer(_row,w=_padding)                          
    mUI.MelLabel(_row,l='Base Name: ')        

    self.options_baseName = mUI.MelTextField(_row,
            ann='Base name for this cgmDynFK setup (e.g. DynamicChain).',
            text = 'DynamicChain',
            changeCommand=cgmGEN.Callback(uiFunc_set_base_name, self))

    _row.setStretchWidget( self.options_baseName )

    mUI.MelSpacer(_row,w=_padding)
    _row.layout()

    _row = mUI.MelHSingleStretchLayout(_options,ut='cgmUISubTemplate',padding = 5)
    mUI.MelSpacer(_row,w=_padding)                          
    mUI.MelLabel(_row,l='Name: ')        

    self.options_name = mUI.MelTextField(_row,
            ann='Name',
            text = '')

    _row.setStretchWidget( self.options_name )

    mUI.MelSpacer(_row,w=_padding)
    _row.layout()

    mUI.MelSeparator(_options,ut='cgmUISubTemplate',h=5)

    _row = mUI.MelHSingleStretchLayout(_options,ut='cgmUISubTemplate',padding = 5)

    mUI.MelSpacer(_row,w=_padding)                          
    mUI.MelLabel(_row,l='Direction:')  

    _row.setStretchWidget( mUI.MelSeparator(_row) )

    directions = ['x+', 'x-', 'y+', 'y-', 'z+', 'z-']

    mUI.MelLabel(_row,l='Fwd:') 

    self.fwdMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
    for dir in directions:
        self.fwdMenu.append(dir)
    
    self.fwdMenu.setValue('z+')

    mUI.MelSpacer(_row,w=_padding)
    
    mUI.MelLabel(_row,l='Up:')

    self.upMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
    for dir in directions:
        self.upMenu.append(dir)

    self.upMenu.setValue('y+')

    mUI.MelSpacer(_row,w=_padding)

    _row.layout()

    """
    _row.layout()

    #>>>Report ---------------------------------------------------------------------------------------
    _row_report = mUI.MelHLayout(_inside ,ut='cgmUIInstructionsTemplate',h=20)
    self.uiField_report = mUI.MelLabel(_row_report,
                                       bgc = SHARED._d_gui_state_colors.get('help'),
                                       label = '...',
                                       h=20)
    _row_report.layout() """

    return _inside

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


def uiFunc_build_presets_menu(self, parentMenu):
    """Presets → Cloth / Hair / Nucleus — feel vs shared simulation layers."""
    _cloth = mUI.MelMenuItem(parentMenu, l='Cloth', subMenu=True,
                             ann='Cloth fabric feel (nCloth). Requires mapped cloth. Does not change nucleus/hair.')
    _fabrics = uiFunc_ncloth_profile_list(category='fabric')
    if _fabrics:
        for _name in _fabrics:
            mUI.MelMenuItem(
                _cloth, l=_name,
                ann='Apply fabric profile to mapped nCloth only.',
                c=cgmGEN.Callback(uiFunc_presets_load_cloth, self, _name),
            )
    else:
        mUI.MelMenuItem(_cloth, l='(no fabric profiles)', en=False)

    _hair = mUI.MelMenuItem(parentMenu, l='Hair', subMenu=True,
                            ann='Hair feel (hairSystem). Requires hair on setup. Does not change nucleus/cloth.')
    _hairProfiles = uiFunc_profile_list(key='hs', category='hair')
    if _hairProfiles:
        for _name in _hairProfiles:
            mUI.MelMenuItem(
                _hair, l=_name,
                ann='Apply hairSystem feel profile only.',
                c=cgmGEN.Callback(uiFunc_presets_load_hair, self, _name),
            )
    else:
        mUI.MelMenuItem(_hair, l='(no hair profiles)', en=False)

    _nucleus = mUI.MelMenuItem(parentMenu, l='Nucleus', subMenu=True,
                               ann='Shared simulation layers. Cloth solvers/wind/calm + dynFK wind; skips the other system\'s feel attrs.')
    for _name in uiFunc_ncloth_profile_list(category='solver'):
        mUI.MelMenuItem(
            _nucleus, l=_name,
            ann='nCloth solver → nucleus (no fabric / hair feel).',
            c=cgmGEN.Callback(uiFunc_presets_load_nucleus, self, _name, 'ncloth'),
        )
    mUI.MelMenuItemDiv(_nucleus)
    for _name in uiFunc_ncloth_profile_list(category='wind'):
        mUI.MelMenuItem(
            _nucleus, l=_name,
            ann='nCloth wind → nucleus (no fabric / hair feel).',
            c=cgmGEN.Callback(uiFunc_presets_load_nucleus, self, _name, 'ncloth'),
        )
    for _name in uiFunc_ncloth_profile_list(category='utility'):
        mUI.MelMenuItem(
            _nucleus, l=_name,
            ann='nCloth sim utility. Needs mapped cloth when profile has nc attrs.',
            c=cgmGEN.Callback(uiFunc_presets_load_nucleus, self, _name, 'ncloth'),
        )
    mUI.MelMenuItemDiv(_nucleus)
    for _name in uiFunc_profile_list(category='wind'):
        mUI.MelMenuItem(
            _nucleus, l='dynFK_{0}'.format(_name),
            ann='dynFK wind: nucleus always; hairSystem wind attrs only if hair exists (skipped for cloth-only).',
            c=cgmGEN.Callback(uiFunc_presets_load_nucleus, self, _name, 'dynfk'),
        )
    for _name in uiFunc_profile_list(category='solver'):
        mUI.MelMenuItem(
            _nucleus, l='dynFK_{0}'.format(_name),
            ann='dynFK solver helper → nucleus; light hs only if hair exists.',
            c=cgmGEN.Callback(uiFunc_presets_load_nucleus, self, _name, 'dynfk'),
        )


def uiFunc_presets_load_cloth(self, profileName):
    """Presets → Cloth: fabric only on mapped nCloth (never nucleus / hair)."""
    _str_func = 'uiFunc_presets_load_cloth'
    if not self._mDynFK:
        return log.warning("|{0}| >> Load or Init Sim Setup first".format(_str_func))
    mCloth, _, _ = uiFunc_setup_sim_targets(self)
    if not mCloth:
        return log.warning("|{0}| >> Map cloth first (Details → Cloth <<)".format(_str_func))
    NCLOTH.profile_load(profileName, targets=mCloth.mNode, applyNucleus=False)


def uiFunc_presets_load_nucleus(self, profileName, source='ncloth'):
    """
    Presets → Nucleus: shared simulation.

    ncloth source: cgmNCloth solver/wind/utility → nucleus (via cloth when mapped).
    dynfk source: cgmDynFK wind/solver → nucleus always; hs section only when hair exists.
    Never applies cloth fabric or hair-feel profiles.
    """
    _str_func = 'uiFunc_presets_load_nucleus'
    if not self._mDynFK:
        return log.warning("|{0}| >> Load or Init Sim Setup first".format(_str_func))

    mCloth, mNucleus, mHair = uiFunc_setup_sim_targets(self)

    if source == 'dynfk':
        _d = RIGDYN.profile_get(profileName)
        if not _d:
            return log.warning("|{0}| >> Invalid dynFK profile: {1}".format(_str_func, profileName))
        if not mNucleus:
            return log.warning("|{0}| >> No nucleus on setup".format(_str_func))
        if _d.get('n'):
            RIGDYN.profile_load(mNucleus.mNode, profileName)
            log.info("|{0}| >> Applied dynFK '{1}' n → nucleus (cloth fabric untouched)".format(
                _str_func, profileName))
        # Hair-only extra: wind/solver hs attrs. Cloth-only setups skip hs.
        if mHair and _d.get('hs'):
            RIGDYN.profile_load(mHair.mNode, profileName)
            log.info("|{0}| >> Applied dynFK '{1}' hs → hair (skipped when no hair)".format(
                _str_func, profileName))
        elif _d.get('hs') and not mHair:
            log.info("|{0}| >> Skipping dynFK '{1}' hs — no hair on setup (cloth/nucleus only)".format(
                _str_func, profileName))
        return

    _kind = NCLOTH.profile_kind(profileName)
    if mCloth:
        NCLOTH.profile_load(profileName, targets=mCloth.mNode, applyNucleus=True)
        log.info("|{0}| >> nCloth '{1}' → cloth nucleus path (hair feel untouched)".format(
            _str_func, profileName))
    else:
        if not mNucleus:
            return log.warning("|{0}| >> No nucleus on setup; Init Sim or map cloth".format(_str_func))
        if _kind == 'utility':
            return log.warning(
                "|{0}| >> Utility '{1}' needs mapped cloth (has nCloth attrs). Map cloth first.".format(
                    _str_func, profileName))
        NCLOTH.profile_load(profileName, targets=mNucleus.mNode, applyNucleus=True)
        log.info("|{0}| >> nCloth '{1}' → nucleus only (no cloth; hair feel untouched)".format(
            _str_func, profileName))


def uiFunc_presets_load_hair(self, profileName):
    """Presets → Hair: hair feel only (never nucleus / cloth)."""
    _str_func = 'uiFunc_presets_load_hair'
    if not self._mDynFK:
        return log.warning("|{0}| >> Load or Init Sim Setup first".format(_str_func))
    _, _, mHair = uiFunc_setup_sim_targets(self)
    if not mHair:
        return log.warning("|{0}| >> No hair system on setup".format(_str_func))
    _kind = RIGDYN.profile_kind(profileName) if hasattr(RIGDYN, 'profile_kind') else None
    if _kind and _kind != 'hair':
        return log.warning(
            "|{0}| >> '{1}' is kind '{2}' — use Presets → Nucleus for simulation layers".format(
                _str_func, profileName, _kind))
    RIGDYN.profile_load(mHair.mNode, profileName)
    log.info("|{0}| >> Applied hair feel '{1}' (nucleus / cloth untouched)".format(
        _str_func, profileName))


def uiFunc_make_load_row(parent, label, text, loadCommand, loadAnn, selfRef=None, statusAttr=None):
    """Details row: status label + ``<<`` load-from-selection."""
    _row = mUI.MelHSingleStretchLayout(parent, ut='cgmUISubTemplate', padding=_padding)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l=label)
    uiTF = mUI.MelLabel(_row, ut='cgmUIInstructionsTemplate', l=text, en=True)
    cgmUI.add_Button(_row, '<<', loadCommand, loadAnn)
    _row.setStretchWidget(uiTF)
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()
    if selfRef is not None and statusAttr:
        setattr(selfRef, statusAttr, uiTF)
    return uiTF


def uiFunc_update_create_panel_state(self):
    if not hasattr(self, 'btnAttachToCloth'):
        return

    if not self._mDynFK:
        self.btnAttachToCloth(e=True, en=False)
        uiFunc_set_cloth_status_labels(self, False)
        return

    mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
    self.btnAttachToCloth(e=True, en=bool(mCloth))
    uiFunc_set_cloth_status_labels(self, mCloth)


def uiFunc_set_cloth_status_labels(self, mCloth=None):
    """Update Create + Details cloth status text."""
    _text = 'Not linked'
    if mCloth:
        _text = 'Linked: {0}'.format(mCloth.p_nameBase)
    if hasattr(self, 'uiClothStatusLabel'):
        self.uiClothStatusLabel(edit=True, l=_text)
    if hasattr(self, 'uiClothDetailsLabel'):
        self.uiClothDetailsLabel(edit=True, l=mCloth.p_nameBase if mCloth else 'Not mapped')


def uiFunc_init_sim_setup(self):
    """Create or complete cgmDynFK nucleus setup without Make Dynamic Chain."""
    _start = mc.playbackOptions(q=True, min=True)
    if self._mDynFK:
        self._mDynFK.setup_sim(startFrame=_start, applyPreset=True)
    else:
        mDynFK = RIGDYN.setup_sim_dynFK(
            baseName=self.options_baseName.getValue(),
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


def uiFunc_map_hair(self):
    if not self._mDynFK:
        return log.warning("Tools → Init Sim Setup or load a cgmDynFK setup first")
    result = RIGDYN.map_hair_system(self._mDynFK)
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
        objs=self.itemList.getItems(),
    surfaceTrack=self.clothSurfaceTrackMenu.getValue() if hasattr(self, 'clothSurfaceTrackMenu') else 'follicle',
    )
    uiFunc_update_details(self)
    self.itemList.rebuild()


def uiFunc_rebuild_preset_menu(optionMenu, presetObj):
    """Details Load Preset: hair → hair feel only; nucleus → dynFK sim (wind/solver/base)."""
    optionMenu.clear()
    optionMenu.append("Load Preset")

    profileKey = uiFunc_get_profile_key_for_obj(presetObj)
    l_profiles = []
    if profileKey == 'hs':
        l_profiles = uiFunc_profile_list(key='hs', category='hair')
    elif profileKey == 'n':
        l_profiles = (
            uiFunc_profile_list(key='n', category='wind')
            + uiFunc_profile_list(key='n', category='solver')
            + uiFunc_profile_list(key='n', category='base')
        )
    elif profileKey:
        l_profiles = uiFunc_profile_list(key=profileKey)

    if l_profiles:
        for a in l_profiles:
            optionMenu.append(a)
        optionMenu.append("---")

    for a in mc.nodePreset(list=presetObj) or []:
        optionMenu.append(a)
    optionMenu.append("---")
    optionMenu.append("Save Preset")
    optionMenu.setValue("Load Preset")

def uiFunc_process_preset_change(obj, optionMenu):
    val = optionMenu.getValue()

    if val in ("Load Preset", "---"):
        optionMenu.setValue("Load Preset")
        return

    if val == "Save Preset":
        result = mc.promptDialog(
                title='Save Preset',
                message='Preset Name:',
                button=['OK', 'Cancel'],
                defaultButton='OK',
                cancelButton='Cancel',
                dismissString='Cancel')

        if result == 'OK':
            text = mc.promptDialog(query=True, text=True)
            if mc.nodePreset(isValidName=text):
                mc.nodePreset( save=(obj, text) )
                uiFunc_rebuild_preset_menu(optionMenu, obj)
                optionMenu.setValue(text)
            else:
                print("Invalid name, try again")
                optionMenu.setValue("Load Preset")
        else:
            optionMenu.setValue("Load Preset")
        return

    # cgmDynFK_presets — hair feel on hairSystem; sim kinds on nucleus
    if val in uiFunc_profile_list():
        profileKey = uiFunc_get_profile_key_for_obj(obj)
        _kind = RIGDYN.profile_kind(val) if hasattr(RIGDYN, 'profile_kind') else None
        if profileKey == 'hs' and _kind and _kind != 'hair':
            log.warning("Use Nucleus / Presets → Nucleus for simulation profile '{0}' (kind={1})".format(
                val, _kind))
            optionMenu.setValue("Load Preset")
            return
        RIGDYN.profile_load(obj, val)
        optionMenu.setValue("Load Preset")
        return

    if mc.nodePreset(isValidName=val):
        if mc.nodePreset(exists=(obj, val)):
            mc.nodePreset( load=(obj, optionMenu.getValue()) )
        optionMenu.setValue("Load Preset")

def uiFunc_make_display_line(parent, label="", text="", button=False, buttonLabel = ">>", buttonCommand=None, buttonInfo="", presetOptions=False, presetObj=None):
    _row = mUI.MelHSingleStretchLayout(parent,ut='cgmUISubTemplate',padding = _padding)        

    mUI.MelSpacer(_row,w=_padding)
    mUI.MelLabel(_row, 
                 l=label)

    uiTF = mUI.MelLabel(_row,ut='cgmUIInstructionsTemplate',l=text,
                                en=True)

    if button:
        cgmUI.add_Button(_row,buttonLabel,
                         buttonCommand,
                         buttonInfo)
    
    _row.setStretchWidget(uiTF)

    if presetOptions:
        presetMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
        uiFunc_rebuild_preset_menu(presetMenu, presetObj)
        presetMenu(edit=True,
            cc = cgmGEN.Callback(uiFunc_process_preset_change, presetObj, presetMenu) )
        
    mUI.MelSpacer(_row,w=_padding)

    _row.layout()

    return uiTF

def uiFunc_update_details(self):
    if not self._mDynFK:
        return

    self.detailsFrame.clear()

    dat = self._mDynFK.get_dat()

    self.detailsFrame(edit=True, collapse=False)

    _details = mUI.MelColumnLayout(self.detailsFrame,useTemplate = 'cgmUIHeaderTemplate') 

    cgmUI.add_LineSubBreak()

    # Base Name
    _row = mUI.MelHSingleStretchLayout(_details, ut='cgmUISubTemplate', padding=5)
    mUI.MelSpacer(_row, w=_padding)
    mUI.MelLabel(_row, l='Base Name:')
    _row.setStretchWidget(mUI.MelSeparator(_row))
    _baseName = self._mDynFK.cgmName or self._mDynFK.baseName or ''
    self.details_baseNameIF = mUI.MelTextField(
        _row,
        ann='Base name for this cgmDynFK setup.',
        text=_baseName,
        changeCommand=cgmGEN.Callback(uiFunc_set_base_name, self),
    )
    mUI.MelSpacer(_row, w=_padding)
    _row.layout()

    # Direction Info
    _row = mUI.MelHSingleStretchLayout(_details,ut='cgmUISubTemplate',padding = 5)        

    mUI.MelSpacer(_row,w=_padding)

    mUI.MelLabel(_row, l="Direction:")

    _row.setStretchWidget( mUI.MelSeparator(_row) )

    mUI.MelLabel(_row, l="Fwd:")

    uiTF = mUI.MelLabel(_row,ut='cgmUISubTemplate',l=self._mDynFK.fwd,
                                en=True)

    mUI.MelLabel(_row, 
                 l="Up:")

    uiTF = mUI.MelLabel(_row,ut='cgmUISubTemplate',l=self._mDynFK.up,
                                en=True)

    mUI.MelSpacer(_row,w=10)
    _row.layout()


    # Nucleus / Cloth / Hair — ``<<`` loads from selection
    mNucleus = dat.get('mNucleus')
    uiFunc_make_load_row(
        _details, 'Nucleus:',
        mNucleus.p_nameBase if mNucleus else 'Not mapped',
        cgmGEN.Callback(uiFunc_map_nucleus, self),
        "Map selected nucleus to this setup. Apply sim presets via Presets → Nucleus.",
    )

    mCloth = dat.get('mCloth') or RIGDYN.get_mapped_cloth(self._mDynFK)
    uiFunc_make_load_row(
        _details, 'Cloth:',
        mCloth.p_nameBase if mCloth else 'Not mapped',
        cgmGEN.Callback(uiFunc_map_cloth, self),
        "Map selected nCloth to this setup. Apply cloth presets via Presets → Cloth.",
        selfRef=self, statusAttr='uiClothDetailsLabel',
    )

    mHairSysShape = dat.get('mHairSysShape')
    uiFunc_make_load_row(
        _details, 'Hair System:',
        mHairSysShape.p_nameBase if mHairSysShape else 'Not mapped',
        cgmGEN.Callback(uiFunc_map_hair, self),
        "Map selected hairSystem to this setup. Apply hair feel via Presets → Hair.",
    )

    _row = mUI.MelHSingleStretchLayout(_details,ut='cgmUISubTemplate',padding = 5)        

    mUI.MelSpacer(_row,w=_padding)

    mUI.MelLabel(_row, 
                 l='Enabled:')

    _row.setStretchWidget( mUI.MelSeparator(_row) )

    self.nucleusEnabledCB = mUI.MelCheckBox(_row,en=True,
                               v = True,
                               label = '',
                               ann='Enable Nucleus') 
    self.nucleusEnabledCB(edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_nucleus_enabled,self))
    
    mUI.MelSpacer(_row,w=_padding)
    
    _row.layout()

    # Baking -----------------------------------------------------------------
    mc.setParent(_details)
    cgmUI.add_HeaderBreak()
    cgmUI.add_Header('Baking')
    cgmUI.add_LineSubBreak()

    # Start Times

    _row = mUI.MelHSingleStretchLayout(_details,ut='cgmUISubTemplate',padding = 5)        

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
    _row = mUI.MelHSingleStretchLayout(_details,ut='cgmUISubTemplate')
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

    mc.setParent(_details)
    cgmUI.add_LineSubBreak()

    allChains = []
    for idx in dat['chains']:
        if dat['chains'][idx].get('chainMode') != 'clothAttach':
            allChains += dat['chains'][idx]['mObjJointChain']
    allTargets = []
    for idx in dat['chains']:
        allTargets += dat['chains'][idx]['mTargets']

    _row = mUI.MelHLayout(_details,ut='cgmUISubTemplate',padding = _padding*2)
    
    cgmUI.add_Button(_row,'Bake All Joints',
        cgmGEN.Callback(uiFunc_bake,self,'chain', allChains),                         
        #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
        'Bake All Joints')
    cgmUI.add_Button(_row,'Bake All Targets',
        cgmGEN.Callback(uiFunc_bake,self,'target', allTargets),                         
        'Bake All Targets') 

    _row.layout()    


    _row = mUI.MelHLayout(_details,ut='cgmUISubTemplate',padding = _padding*2)
    
    cgmUI.add_Button(_row,'Connect All Targets',
        cgmGEN.Callback(uiFunc_connect_targets, self),                         
        #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
        'Connect All Targets')
    cgmUI.add_Button(_row,'Disconnect All Targets',
        cgmGEN.Callback(uiFunc_disconnect_targets, self),                         
        'Disconnect All Targets') 

    _row.layout()   

    # Chains
    for i,chain in enumerate(self._mDynFK.msgList_get('chain')):
        _row = mUI.MelHSingleStretchLayout(_details,ut='cgmUISubTemplate',padding = _padding)        

        mUI.MelSpacer(_row,w=_padding)

        _subChainColumn = mUI.MelColumnLayout(_row,useTemplate = 'cgmUIHeaderTemplate') 

        chainFrame = mUI.MelFrameLayout(_subChainColumn, label=chain.p_nameBase, collapsable=True, collapse=True,useTemplate = 'cgmUIHeaderTemplate')
        
        _chainColumn = mUI.MelColumnLayout(chainFrame,useTemplate = 'cgmUIHeaderTemplate') 

        _row.setStretchWidget(_subChainColumn)

        #mUI.MelSpacer(_row,w=_padding)
        _row.layout()

        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        _chainMode = getattr(chain, 'chainMode', None) or 'hair'

        if _chainMode == 'clothAttach':
            mCloth = RIGDYN.get_mapped_cloth(self._mDynFK)
            clothLabel = mCloth.p_nameBase if mCloth else '—'
            uiFunc_make_display_line(_chainColumn, label='Driver Cloth:', text=clothLabel, button=bool(mCloth), buttonLabel=">>", buttonCommand=cgmGEN.Callback(uiFunc_select_item, mCloth.p_nameBase) if mCloth else None, buttonInfo="Mapped setup cloth.")
            _surfaceTrack = getattr(chain, 'surfaceTrack', None) or 'follicle'
            uiFunc_make_display_line(_chainColumn, label='Surface track:', text=_surfaceTrack, button=False)
            uiFunc_make_display_line(_chainColumn, label='Mode:', text='clothAttach', button=False)
        else:
            if chain.mFollicle:
                uiFunc_make_display_line(_chainColumn, label='Follicle:', text=cgmMeta.asMeta(chain.mFollicle[0]).p_nameBase, button=True, buttonLabel = ">>", buttonCommand=cgmGEN.Callback(uiFunc_select_item,chain.mFollicle[0]), buttonInfo="Select follicle transform.", presetOptions=True, presetObj = chain.mFollicle[0])
        
        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        uiFunc_make_display_line(_chainColumn, label='Group:', text=chain.p_nameShort, button=True, buttonLabel = ">>", buttonCommand=cgmGEN.Callback(uiFunc_select_item,chain.p_nameBase), buttonInfo="Select group transform.")

        mc.setParent(_chainColumn)
        cgmUI.add_LineSubBreak()

        if _chainMode != 'clothAttach':
            _row = mUI.MelHSingleStretchLayout(_chainColumn,ut='cgmUISubTemplate',padding = 5)

            mUI.MelSpacer(_row,w=_padding)                          
            mUI.MelLabel(_row,l='Orient Up:')  

            _row.setStretchWidget( mUI.MelSeparator(_row) )

            chainDirections = []
            for dir in ['x+', 'x-', 'y+', 'y-', 'z+', 'z-']:
                if chain.fwd[0] != dir[0]:
                    chainDirections.append(dir)
            chainDirections.append('None')
           
            upMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
            for dir in chainDirections:
                upMenu.append(dir)

            upMenu.setValue( chain.up )

            upMenu(edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_chain_up,self,i,upMenu))

            mUI.MelSpacer(_row,w=_padding)

            _row.layout()

        _row = mUI.MelHLayout(_chainColumn,ut='cgmUISubTemplate',padding = _padding*2)
        if _chainMode != 'clothAttach':
            cgmUI.add_Button(_row,'Bake Joints',
                cgmGEN.Callback(uiFunc_bake,self,'chain', chain.msgList_get('mObjJointChain')),                         
                'Bake All Joints')
        cgmUI.add_Button(_row,'Bake Targets',
            cgmGEN.Callback(uiFunc_bake,self,'target', chain.msgList_get('mTargets')),                         
            'Bake All Targets') 

        _row.layout()    

        _row = mUI.MelHLayout(_chainColumn,ut='cgmUISubTemplate',padding = _padding*2)
    
        cgmUI.add_Button(_row,'Connect Targets',
            cgmGEN.Callback(uiFunc_connect_targets, self, i),                         
            'Connect All Targets')
        cgmUI.add_Button(_row,'Disconnect Targets',
            cgmGEN.Callback(uiFunc_disconnect_targets, self, i),                         
            'Disconnect All Targets') 

        _row.layout()  

        _row = mUI.MelHLayout(_chainColumn,ut='cgmUISubTemplate',padding = _padding*2)
        cgmUI.add_Button(_row,'Delete Chain',
            cgmGEN.Callback(uiFunc_delete_chain,self, i),                         
            'Delete Chain')
        _row.layout()  

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
            frameDat = [['Targets', 'mTargets'],
                        ['Locators','mLocs'],
                        ['Joint Chain', 'mObjJointChain'],
                        ['Aims', 'mAims'],
                        ['Parents', 'mParents']]

        for dat in frameDat:
            frame = mUI.MelFrameLayout(_chainColumn, label=dat[0], collapsable=True, collapse=True,useTemplate = 'cgmUIHeaderTemplate')
            column = mUI.MelColumnLayout(frame,useTemplate = 'cgmUITemplate',height=75) 
            row = mUI.MelHSingleStretchLayout(column,ut='cgmUIHeaderTemplate',padding = _padding)

            mUI.MelSpacer(row,w=_padding)

            itemList = uiFunc_create_selection_list(row, [x.p_nameShort for x in chain.msgList_get(dat[1])] )

            mUI.MelSpacer(row,w=_padding)

            row.setStretchWidget(itemList)

            row.layout()

    # End Chains

    mc.setParent(_details)
    cgmUI.add_LineSubBreak()

def uiFunc_delete_chain(self, idx):
    self._mDynFK.chain_deleteByIdx(idx)
    uiFunc_update_details(self)

def uiFunc_connect_targets(self, idx=None):
    self._mDynFK.targets_connect(idx)

def uiFunc_disconnect_targets(self, idx=None):
    self._mDynFK.targets_disconnect(idx)

def uiFunc_query_settings(self):
    """Query selected sim nodes and print a preset dict for cgmNCloth_presets / cgmDynFK_presets."""
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

    print('\n# --- Paste-ready preset block (copy to cgmNCloth_presets.py) ---\n')
    print(_dat.get('paste') or '')
    print('\n# --- profile dict (paste to agent / preset work) ---\n')
    pprint.pprint(_dat.get('profile') or {}, width=120, sort_dicts=True)


def uiFunc_set_base_name(self, *args):
    if not self._mDynFK:
        return

    _val = None
    if getattr(self, 'details_baseNameIF', None):
        try:
            _val = self.details_baseNameIF.getValue()
        except Exception:
            pass
    if _val is None:
        _val = self.options_baseName.getValue()

    _val = (_val or '').strip()
    _current = self._mDynFK.cgmName or self._mDynFK.baseName or ''

    if not _val:
        self.options_baseName.setValue(_current)
        if getattr(self, 'details_baseNameIF', None):
            self.details_baseNameIF.setValue(_current)
        return

    if _val == _current:
        return

    self._mDynFK.set_base_name(_val)
    self.options_baseName.setValue(_val)
    if getattr(self, 'details_baseNameIF', None):
        self.details_baseNameIF.setValue(_val)

    _short = self._mDynFK.p_nameBase
    if len(_short) > 20:
        _short = _short[:20] + '...'
    self.uiTF_objLoad(edit=True, l=_short, ann=self._mDynFK.p_nameBase)


def uiFunc_set_chain_up(self, idx, upMenu):
    #print "Changing up on %s to %s" % ( chain.p_nameBase, upMenu.getValue() )
    axis = upMenu.getValue()
    if axis == 'None':
        axis = None
    else:
        axis = VALID.simpleAxis(axis)
    self._mDynFK.chain_setOrientUpByIdx(idx, axis)

# mode - 'target', 'chain'
def uiFunc_bake(self, mode, mObjs):
    if not self._mDynFK:
        return
    self._mDynFK.bake_nodes(
        mObjs,
        self.uiFieldInt_start.getValue(),
        self.uiFieldInt_end.getValue(),
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
    mc.select( item )

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

def uiFunc_select_nucleus(self):
    mc.select(self._mDynFK.get_dat()['mNucleus'].p_nameBase)

def uiFunc_make_dynamic_chain(self):
    if not self._mDynFK:
        mDynFK = RIGDYN.cgmDynFK(baseName=self.options_baseName.getValue(), name=self.options_name.getValue(),objs=self.itemList.getItems(),fwd=self.fwdMenu.getValue(), up=self.upMenu.getValue(), startFrame=mc.playbackOptions(q=True, min=True))
        mDynFK.profile_load('base')
        uiFunc_load_dyn_chain(self, mDynFK.p_nameBase)
    else:
        self._mDynFK.chain_create(name = self.options_name.getValue(),objs=self.itemList.getItems(),fwd=self.fwdMenu.getValue(), up=self.upMenu.getValue())
        uiFunc_update_details(self)

    self.itemList.rebuild()

def uiFunc_load_dyn_chain(self, chain):
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
        uiFunc_updateTargetDisplay(self)

    #uiFunc_updateFields(self)
    #self.uiReport_do()
    #self.uiFunc_updateScrollAttrList()

def uiFunc_load_selected(self, bypassAttrCheck = False):
    _str_func = 'uiFunc_load_selected'  

    uiFunc_load_dyn_chain(self, mc.ls(sl=True)[0])

def uiFunc_clear_loaded(self):
    _str_func = 'uiFunc_clear_loaded'  
    self._mDynFK = False
    #self._mGroup = False
    self.uiTF_objLoad(edit=True, l='',en=False)      
    #self.uiField_report(edit=True, l='...')
    #self.uiReport_objects()
    #self.uiScrollList_parents.clear()
    
    #for o in self._l_toEnable:
        #o(e=True, en=False)  
     
def uiFunc_updateTargetDisplay(self):
    _str_func = 'uiFunc_updateTargetDisplay'  
    #self.uiScrollList_parents.clear()

    if not self._mDynFK:
        log.info("|{0}| >> No target.".format(_str_func))                        
        #No obj
        self.uiTF_objLoad(edit=True, l='',en=False)
        self._mGroup = False

        #for o in self._l_toEnable:
            #o(e=True, en=False)

        self.options_baseName(e=True, enable=True)

        return
    
    self.options_baseName.setValue(self._mDynFK.cgmName or self._mDynFK.baseName or '')
    self.options_baseName(e=True, enable=True)

    _short = self._mDynFK.p_nameBase
    self.uiTF_objLoad(edit=True, ann=_short)
    
    if len(_short)>20:
        _short = _short[:20]+"..."
    self.uiTF_objLoad(edit=True, l=_short)   
    
    self.uiTF_objLoad(edit=True, en=True)

    uiFunc_update_details(self)
    uiFunc_update_create_panel_state(self)
    
    return


 