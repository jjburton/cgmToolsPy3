"""
------------------------------------------
baseTool: cgm.core.tools
Author: Josh Burton and David Bokser
email: dbokser@cgmonks.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
mocapBakeTools
================================================================
"""
# From Python =============================================================
import copy
import time
import pprint
import os
import sys
from functools import partial
import math
import json

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
mUI = cgmUI.mUI

from cgm.core import cgm_RigMeta as cgmRigMeta
from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
from cgm.core.lib import shared_data as SHARED
from cgm.core.lib import transform_utils as TRANS
from cgm.core.lib import position_utils as POS
from cgm.core.lib import math_utils as MATH
from cgm.core.lib import string_utils as STRING
from cgm.core.lib import search_utils as SEARCH
from cgm.core.lib import snap_utils as SNAP
from cgm.core.lib import distance_utils as DIST
from cgm.core.lib import name_utils as NAMES
from cgm.core.lib import euclid
import cgm.core.lib.mocap_align_utils as MOCAPALIGN
import cgm.core.lib.path_utils as COREPATHS
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.cgmPy import path_Utils as CGMPATH
from cgm.lib import lists


#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASE
__toolname__ ='mocapBakeTool'

_subLineBGC = [.75,.75,.75]
_buttonBGC = [.3,.3,.3]


def reload_dependencies():
    """Reload mocap align backend modules (tool open / Reload menu)."""
    import cgm.core.lib.mocap_align_utils as _mocap_align_utils
    cgmGEN._reloadMod(_mocap_align_utils)
    global MOCAPALIGN
    MOCAPALIGN = _mocap_align_utils
    return MOCAPALIGN


class cgmListItem(object):
    """Parallel list row: .item = canonical CCL pattern or DAG string; .alias = display-only."""
    item = None
    alias = None
    data = None
    #mobj = None

    def __init__(self, init_item, init_alias, init_data = {}):
        self.item = init_item
        self.alias = init_alias
        self.data = init_data
        #self.mobj = init_mobj

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE = 480,520
    TOOLNAME = '{0}.ui'.format(__toolname__)
    
    parent_source_items = []
    parent_target_items = []
    # orient_source_items = []
    # orient_target_items = []

    parent_links = []
    # orient_links = []

    connection_data = []

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

        self.create_guiOptionVar('mocap_allow_multiple_targets',defaultValue = 0)
        self.create_guiOptionVar('mocap_set_connection_at_bake',defaultValue = 1)
        self.create_guiOptionVar('mocap_show_short_names', defaultValue = 0)
        self.create_guiOptionVar('mocap_rig_namespace', defaultValue = '')
        self.create_guiOptionVar('mocap_skel_roots', defaultValue = '')
        self.create_guiOptionVar('mocap_last_ccl', defaultValue = '')
        self.var_mocap_last_ccl.setType('string')

        self.mPathList_recent = cgmMeta.pathList('{}_CCLRecent'.format(__toolname__))
        self._loaded_ccl = ''

        self.uiPopUpMenu_target = None
        self.uiPopUpMenu_source = None

    def post_init(self, *args, **kws):
        _path = self.var_mocap_last_ccl.value
        if _path and os.path.exists(_path):
            self.uiFunc_load_data(filepath=_path)

    def uiStatus_refresh(self, string=None):
        if not string:
            if self._loaded_ccl:
                string = STRING.short(self._loaded_ccl, max=40, start=10)
            else:
                string = 'No CCL loaded'
        if self._loaded_ccl:
            self.uiStatus_top(edit=True,
                              bgc=SHARED._d_gui_state_colors.get('connected'),
                              label=string)
        else:
            self.uiStatus_top(edit=True,
                              bgc=SHARED._d_gui_state_colors.get('help'),
                              label=string)

    def uiStatus_fileExplorer(self):
        if self._loaded_ccl and os.path.exists(self._loaded_ccl):
            os.startfile(CGMPATH.Path(self._loaded_ccl).up().asFriendly())

    def uiStatus_fileClear(self):
        self._loaded_ccl = ''
        self.var_mocap_last_ccl.setValue('')
        self.uiStatus_refresh()

    def reload(self):
        reload_dependencies()
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()
 
    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc = cgmGEN.Callback(self.buildMenu_first))
        self.uiMenu_tools = mUI.MelMenu( l='Tools', pmc = cgmGEN.Callback(self.buildMenu_tools))
        self.uiMenu_help = mUI.MelMenu( l='Help', pmc = cgmGEN.Callback(self.buildMenu_help))

    def buildMenu_help( self, *args):
        self.uiMenu_help.clear()
        mUI.MelMenuItem( self.uiMenu_help, l="Log Self",
                                 c=lambda *a: cgmUI.log_selfReport(self) )

    def buildMenu_tools( self, *args):
        self.uiMenu_tools.clear()
        mUI.MelMenuItem( self.uiMenu_tools, l="Make Constraints",
                                 c=lambda *a: self.uiFunc_make_constraints(self) )
        mUI.MelMenuItemDiv( self.uiMenu_tools )
        mUI.MelMenuItem( self.uiMenu_tools, l="Create Align Debug Locs",
                                 c=lambda *a: self.uiFunc_create_align_locs())
        mUI.MelMenuItem( self.uiMenu_tools, l="Delete Align Debug Locs",
                                 c=lambda *a: self.uiFunc_delete_align_locs())
        mUI.MelMenuItemDiv( self.uiMenu_tools )
        mUI.MelMenuItem( self.uiMenu_tools, l="Mapping Report...",
                                 c=lambda *a: self.uiFunc_show_mapping_report())


    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        #>>> Reset Options                           

        #mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )
        self.uiMenu_buildDock(self.uiMenu_FirstMenu)

        mUI.MelMenuItem( self.uiMenu_FirstMenu, checkBox=self.var_mocap_allow_multiple_targets.value, l="Allow multiple targets",
                 c=lambda *a: self.uiFunc_toggle_multiple_targets(self) )#not mc.optionVar(q='cgm_mocap_allow_multiple_targets')))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, checkBox=self.var_mocap_show_short_names.value, l="Show short names",
                 c=lambda *a: self.uiFunc_toggle_show_short_names(self) )

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )

        self.mPathList_recent.verify()
        _recent = mUI.MelMenuItem(self.uiMenu_FirstMenu, l="Recent",
                                  ann='Open a recent CCL file', subMenu=True)
        for p in self.mPathList_recent.l_paths:
            if '.' in p:
                _split = p.split('.')
                _l = STRING.short(str(_split[0]), 20)
            else:
                _l = STRING.short(str(p), 20)
            mUI.MelMenuItem(_recent, l=_l,
                            c=cgmGEN.Callback(self.uiFunc_load_data, filepath=p))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save",
                 c=lambda *a: self.uiFunc_save_data() )
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save As...",
                 c=lambda *a: self.uiFunc_save_as_data() )


        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Load Data",
                 c=lambda *a: self.uiFunc_load_data() )

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reload",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))
        
    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper'

        _MainForm = mUI.MelFormLayout(self,ut='cgmUITemplate')

        _status_row = mUI.MelHSingleStretchLayout(_MainForm, ut='cgmUITemplate')
        mUI.MelSpacer(_status_row, w=5)
        self.uiStatus_top = mUI.MelLabel(_status_row,
                                         vis=True,
                                         bgc=SHARED._d_gui_state_colors.get('help'),
                                         label='No CCL loaded',
                                         h=20)
        mUI.MelIconButton(_status_row,
                          ann='Clear the loaded CCL link',
                          image=os.path.join(cgmUI._path_imageFolder, 'clear.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=partial(self.uiStatus_fileClear))
        mUI.MelIconButton(_status_row,
                          ann='Open CCL folder',
                          image=os.path.join(cgmUI._path_imageFolder, 'find_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.uiStatus_fileExplorer())
        _status_row.setStretchWidget(self.uiStatus_top)
        mUI.MelSpacer(_status_row, w=5)
        _status_row.layout()

        _item_form = mUI.MelFormLayout(_MainForm,ut='cgmUITemplate')
        
        _parent_source = self.buildScrollForm(_item_form, hasHeader=True, buttonArgs = [{'label':'Add Selected', 'command':self.uiFunc_add_to_parent_source, 'annotation':_d_annotations.get('addSource','fix')}, {'label':'Remove Item', 'command':self.uiFunc_remove_from_parent_source, 'annotation':_d_annotations.get('removeSource','fix')}], headerText = 'source', allowMultiSelection=False, selectCommand=self.uiFunc_on_select_parent_source_item, doubleClickCommand=self.uiFunc_toggle_link_parent_targets)
        _parent_target = self.buildScrollForm(_item_form, hasHeader=True, buttonArgs = [
            {'label':'Add Selected', 'command':self.uiFunc_add_to_parent_target, 'annotation':_d_annotations.get('addTarget','fix')},
            {'label':'Remove Item', 'command':self.uiFunc_remove_from_parent_target, 'annotation':_d_annotations.get('removeTarget','fix')},
        ], headerText = 'target', allowMultiSelection=True, selectCommand=self.uiFunc_select_parent_target_link, doubleClickCommand=self.uiFunc_toggle_link_parent_targets)
        
        self.parent_source_scroll = _parent_source[1]
        self.parent_target_scroll = _parent_target[1]
        self._patch_target_scroll_item_as_str()


        self.uiPopUpMenu_source = mUI.MelPopupMenu(self.parent_source_scroll,button = 3)

        mUI.MelMenuItem(self.uiPopUpMenu_source,
            ann = 'Select',
            c = cgmGEN.Callback( self.uiFunc_select_from_ui, 0),
            label = "Select")
        mUI.MelMenuItem(self.uiPopUpMenu_source,
            ann = 'Select Link',
            c = cgmGEN.Callback( self.uiFunc_select_from_ui, 2),
            label = "Select Link")
        mUI.MelMenuItem(self.uiPopUpMenu_source,
            ann = 'Clear List',
            c = cgmGEN.Callback( self.uiFunc_clear_list, 0),
            label = "Clear List")
        mUI.MelMenuItem(self.uiPopUpMenu_source,
            ann = 'Select All',
            c = cgmGEN.Callback( self.uiFunc_select_all_in_list, 0),
            label = "Select All")

        self.uiPopUpMenu_target = mUI.MelPopupMenu(self.parent_target_scroll,button = 3)

        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = 'Select',
            c = cgmGEN.Callback( self.uiFunc_select_from_ui, 1),
            label = "Select")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = 'Select Link',
            c = cgmGEN.Callback( self.uiFunc_select_from_ui, 3),
            label = "Select Link")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = 'Clear List',
            c = cgmGEN.Callback( self.uiFunc_clear_list, 1),
            label = "Clear List")
        mUI.MelMenuItemDiv(self.uiPopUpMenu_target)
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = _d_annotations.get('moveTargetUp', 'Move selected targets up'),
            c = cgmGEN.Callback( self.uiFunc_reorder_parent_target, 0),
            label = "Move Up")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = _d_annotations.get('moveTargetDn', 'Move selected targets down'),
            c = cgmGEN.Callback( self.uiFunc_reorder_parent_target, 1),
            label = "Move Dn")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = _d_annotations.get('moveTargetTop', 'Move selected targets to top of list'),
            c = cgmGEN.Callback( self.uiFunc_reorder_parent_target_to_top),
            label = "Move to Top")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = _d_annotations.get('moveTargetBottom', 'Move selected targets to bottom of list'),
            c = cgmGEN.Callback( self.uiFunc_reorder_parent_target_to_bottom),
            label = "Move to Bottom")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = _d_annotations.get('moveTargetSetIndex', 'Move selected targets to a list index'),
            c = cgmGEN.Callback( self.uiFunc_reorder_parent_target_set_index),
            label = "Set Index...")
        mUI.MelMenuItem(self.uiPopUpMenu_target,
            ann = 'Select All',
            c = cgmGEN.Callback( self.uiFunc_select_all_in_list, 1),
            label = "Select All")

        self.parent_target_scroll(e=True, allowMultiSelection=self.var_mocap_allow_multiple_targets.value)

        self.splitFormHorizontal(_item_form, _parent_source[0], _parent_target[0])

        _options_column = self.buildOptions(_MainForm,False)
        _footer = cgmUI.add_cgmFooter(_options_column)        

        _MainForm(edit = True,
                  af = [(_status_row, "top", 0),
                        (_status_row, "left", 0),
                        (_status_row, "right", 0),
                        (_item_form, "left", 0),
                        (_item_form, "right", 0),
                        (_options_column, "left", 0),
                        (_options_column, "right", 0),
                        (_options_column, "bottom", 0)],
                  ac = [(_item_form, "top", 2, _status_row),
                        (_item_form, "bottom", 2, _options_column)],
                  attachNone = [(_options_column, "top")])
    
    def buildScrollForm(self, parent, hasHeader = False, buttonArgs = [], headerText = 'Header', allowMultiSelection=True, buttonCommand=None, doubleClickCommand=None, selectCommand=None):
        main_form = mUI.MelFormLayout(parent,ut='cgmUITemplate')

        header = None
        if(hasHeader):
            header = cgmUI.add_Header(headerText, overrideUpper = True)
        
        scroll_list = mUI.MelObjectScrollList( main_form, ut='cgmUITemplate',
                                                  allowMultiSelection=allowMultiSelection, doubleClickCommand=cgmGEN.Callback(doubleClickCommand,self), selectCommand=cgmGEN.Callback(selectCommand,self) )

        buttonLayout = None
        buttons = []
        hasButton = len(buttonArgs) > 0
        if(hasButton):
            #buttonLayout = mUI.MelColumnLayout(main_form,useTemplate = 'cgmUISubTemplate')
            buttonLayout = mUI.MelHLayout(main_form,ut='cgmUISubTemplate',padding = 1,bgc=_subLineBGC)
            for btn in buttonArgs:
                button = cgmUI.add_Button(buttonLayout,btn['label'],
                             cgmGEN.Callback(btn['command'],self),
                             btn['annotation'], bgc=_buttonBGC)
                buttons.append(button)
            buttonLayout.layout()


        af = [(scroll_list,"left",0), (scroll_list,"right",0)]
        ac = []
        attachNone = []

        if(hasHeader):
            af += [ (header,"top",0),
                    (header,"left",0),
                    (header,"right",0) ]
            ac += [(scroll_list,"top",0,header)]
            attachNone += [(header,"bottom")]
        else:
            af += [ (scroll_list,"top",0) ]

        if(hasButton):
            af += [ (buttonLayout,"bottom",0),
                    (buttonLayout,"left",0),
                    (buttonLayout,"right",0)]
            ac += [(scroll_list,"bottom",0,buttonLayout)]
            attachNone += [(buttonLayout,"top")]
        else:
            af += [ (scroll_list,"bottom",0) ]

        main_form(edit=True, af = af,
                                ac = ac,
                                attachNone = attachNone)
        
        return [main_form, scroll_list, header, buttons]

    def fullForm(self, form_layout, element, padding=0):
        form_layout(edit = True,
          af = [(element,"top",padding),
                (element,"bottom",padding),
                (element, "left", padding),
                (element,"right",padding)])
        return form_layout

    def splitFormHorizontal(self, form_layout, element1, element2, division = 50, padding = 0):
        form_layout(edit = True,
          af = [(element1,"top",padding),
                (element1,"bottom",padding),
                (element1, "left", padding),
                (element2,"top",padding),
                (element2,"bottom",padding),
                (element2,"right",padding)],
          ac = [(element2,"left",padding,element1)],
          ap = [(element1, 'right', padding, division)])
        return form_layout

    def splitFormVertical(self, form_layout, element1, element2, division = 50, padding = 0):
        form_layout(edit = True,
          af = [(element1,"left",padding),
                (element1,"right",padding),
                (element1, "top", padding),
                (element2,"left",padding),
                (element2,"right",padding),
                (element2,"bottom",padding)],
          ac = [(element2,"top",padding,element1)],
          ap = [(element1, 'bottom', padding, division)])
        return form_layout

    def buildOptions(self,parent, asScroll = False):
 
        if asScroll:
            _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
        else:
            _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        
        #>>>Objects Load Row ---------------------------------------------------------------------------------------
        
        mc.setParent(_inside)
        cgmUI.add_LineSubBreak()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Auto Link by')
        _row.setStretchWidget( mUI.MelSeparator(_row) )
    
        cgmUI.add_Button(_row,'Name',
                 cgmGEN.Callback(self.uiFunc_link_by_name,self),
                 _d_annotations.get('linkName','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'Distance',
                 cgmGEN.Callback(self.uiFunc_link_by_distance,self),
                 _d_annotations.get('linkDistance','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'Index',
                 cgmGEN.Callback(self.uiFunc_link_by_index,self),
                 _d_annotations.get('linkIndex','fix'), bgc=_buttonBGC) 
        mUI.MelSpacer(_row,w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 1,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=9)
        mUI.MelLabel(_row,l='Set Target Constraint to')
        _row.setStretchWidget( mUI.MelSeparator(_row) )

        cgmUI.add_Button(_row,'Point/Orient',
                 cgmGEN.Callback(self.uiFunc_set_constraint_type,1,True,self),
                 _d_annotations.get('setPointOrient','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'A',
                 cgmGEN.Callback(self.uiFunc_set_constraint_type,1,False,self),
                 _d_annotations.get('setPointOrientAll','fix'), bgc=_buttonBGC) 
        mUI.MelSpacer(_row,w=4)
        cgmUI.add_Button(_row,'Orient',
                 cgmGEN.Callback(self.uiFunc_set_constraint_type,0,True,self),
                 _d_annotations.get('setOrient','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'A',
                 cgmGEN.Callback(self.uiFunc_set_constraint_type,1,False,self),
                 _d_annotations.get('setOrientAll','fix'), bgc=_buttonBGC) 
        mUI.MelSpacer(_row,w=9)

        _row.layout()

        # Align resolution (local-TR path)
        mc.setParent(_inside)
        cgmUI.add_Header("Align (local offsets)", overrideUpper = True)
        cgmUI.add_LineSubBreak()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Rig NS')
        self.tf_rig_namespace = mUI.MelTextField(_row,
                                                 text=self.var_mocap_rig_namespace.value or '',
                                                 ann='Anim rig namespace (e.g. Hondo:)')
        _row.setStretchWidget(self.tf_rig_namespace)
        cgmUI.add_Button(_row,'From Sel',
                 cgmGEN.Callback(self.uiFunc_rig_ns_from_selection),
                 _d_annotations.get('rigNsFromSel','Get namespace from selection'), bgc=_buttonBGC)
        mUI.MelSpacer(_row,w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Skel Roots')
        self.tf_skel_roots = mUI.MelTextField(_row,
                                              text=self.var_mocap_skel_roots.value or '',
                                              ann='Semicolon-separated skeleton root long paths')
        _row.setStretchWidget(self.tf_skel_roots)
        cgmUI.add_Button(_row,'Set',
                 cgmGEN.Callback(self.uiFunc_skel_roots_from_selection),
                 _d_annotations.get('skelRootsFromSel','Set skeleton roots from selection'), bgc=_buttonBGC)
        mUI.MelSpacer(_row,w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Local Offsets')
        _row.setStretchWidget( mUI.MelSeparator(_row) )
        cgmUI.add_Button(_row,'Capture',
                 cgmGEN.Callback(self.uiFunc_capture_offsets),
                 _d_annotations.get('captureOffsets','Capture localTranslate/localRotate at bind pose'), bgc=[.2,.4,.2])
        cgmUI.add_Button(_row,'Snap All',
                 cgmGEN.Callback(self.uiFunc_snap_connections, False),
                 _d_annotations.get('snapAll','Snap all links with local offsets (no keys)'), bgc=_buttonBGC)
        cgmUI.add_Button(_row,'Snap Sel',
                 cgmGEN.Callback(self.uiFunc_snap_connections, True),
                 _d_annotations.get('snapSel','Snap selected target links with local offsets'), bgc=_buttonBGC)
        mUI.MelSpacer(_row,w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Set Connection Pose')
        _row.setStretchWidget( mUI.MelSeparator(_row) )
        self.cb_set_connection_at_bake = mUI.MelCheckBox(_row,
                           v = self.var_mocap_set_connection_at_bake.value,
                           onCommand = lambda *a: self.var_mocap_set_connection_at_bake.setValue(1),
                           offCommand = lambda *a: self.var_mocap_set_connection_at_bake.setValue(0),
                           label="Set On Bake")
        cgmUI.add_Button(_row,'Manual Set',
                 cgmGEN.Callback(self.uiFunc_set_connection_pose,1,self),
                 _d_annotations.get('setConnectionPose','Set connection offset based off these source/target positions'), bgc = [.5,.2,0.2]) 
        mUI.MelSpacer(_row,w=5)

        _row.layout()

        # Bake Options

        timelineInfo = SEARCH.get_time('slider')

        mc.setParent(_inside)
        cgmUI.add_Header("Bake Options", overrideUpper = True)

        cgmUI.add_LineSubBreak()


        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate',padding = 5,bgc=_subLineBGC)
        #self.timeSubMenu.append( _row )
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Set Timeline Range')
        _row.setStretchWidget( mUI.MelSeparator(_row) )

        cgmUI.add_Button(_row,'Slider',
                 cgmGEN.Callback(self.uiFunc_updateTimeRange,'slider'),
                 _d_annotations.get('sliderRange','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'Sel',
                 cgmGEN.Callback(self.uiFunc_updateTimeRange,'selected'),
                 _d_annotations.get('selectedRange','fix'), bgc=_buttonBGC) 
        cgmUI.add_Button(_row,'Scene',
                 cgmGEN.Callback(self.uiFunc_updateTimeRange,'scene'),
                 _d_annotations.get('sceneRange','fix'), bgc=_buttonBGC) 
        mUI.MelSpacer(_row,w=5)
        _row.layout()


        _row = mUI.MelHSingleStretchLayout(_inside,ut='cgmUISubTemplate', padding=5,bgc=_subLineBGC)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Bake Range')
        _row.setStretchWidget( mUI.MelSeparator(_row) )

        mUI.MelLabel(_row,l='start')

        self.startFrameField = mUI.MelIntField(_row,'cgmLocWinStartFrameField',
                                           width = 40,
                                           value= timelineInfo[0])

        mUI.MelLabel(_row,l='end')

        self.endFrameField = mUI.MelIntField(_row,'cgmLocWinEndFrameField',
                                         width = 40,
                                         value= timelineInfo[1])

        cgmUI.add_Button(_row,' <<',
                         cgmGEN.Callback(self.uiFunc_bake,'back'),                         
                         #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                         _d_annotations.get('<<<','fix'), bgc=_buttonBGC)
    
        cgmUI.add_Button(_row,'Bake',
                         cgmGEN.Callback(self.uiFunc_bake,'all'),                         
                         _d_annotations.get('All','fix'), bgc=_buttonBGC)
        
        
        cgmUI.add_Button(_row,'>>',
                         cgmGEN.Callback(self.uiFunc_bake,'forward'),                         
                         _d_annotations.get('>>>','fix'), bgc=_buttonBGC)

        mUI.MelSpacer(_row,w=5)
        _row.layout()

        mc.setParent(_inside)
        cgmUI.add_LineSubBreak()

        return _inside

    def uiFunc_toggle_multiple_targets(self, *args):
        self.var_mocap_allow_multiple_targets.toggle()
        self.parent_target_scroll(e=True, allowMultiSelection=self.var_mocap_allow_multiple_targets.value)

    def uiFunc_toggle_show_short_names(self, *args):
        self.var_mocap_show_short_names.toggle()
        self.refresh_aliases()

    def uiFunc_updateTimeRange(self,mode = 'slider'):
        _range = SEARCH.get_time(mode)
        if _range:
            self.startFrameField(edit = True, value = _range[0])
            self.endFrameField(edit = True, value = _range[1])  

    def uiFunc_bake(self, *args):
        mode = args[0]

        bake_range = [self.startFrameField(q=True, value=True), self.endFrameField(q=True, value=True)]
        current_frame = SEARCH.get_time('current')
        if mode == 'back':
            bake_range[1] = min(current_frame, bake_range[0], bake_range[1])
            bake_range[0] = current_frame
        if mode == 'forward':
            bake_range[1] = max(current_frame, bake_range[0], bake_range[1])
            bake_range[0] = current_frame

        mc.currentTime(bake_range[0])
        
        self._reresolve_connection_data()

        if self.var_mocap_set_connection_at_bake.value:
            self.uiFunc_set_connection_pose()

        bake(self.connection_data, bake_range[0], bake_range[1]) 

    def uiFunc_set_constraint_type(self, *args):
        
        mode = args[0]
        onlySelected = args[1]

        idxs = []
        if onlySelected:
            idxs = self.parent_target_scroll.getSelectedIdxs()
        else:
            idxs = list(range( len(self.parent_target_scroll.getAllItems())))

        # point/orient
        if mode == 0:
            for idx in idxs:
                self.parent_target_items[idx].data["constraintType"] = "o"
            log.debug("orient")
        # orient
        elif mode == 1:
            for idx in idxs:
                self.parent_target_items[idx].data["constraintType"] = "po"

            log.debug("point/orient")

        self.refresh_aliases()

        for idx in idxs:
            self.parent_target_scroll.selectByIdx(idx)
            for link in self.parent_links:
                if link[1] == idx:
                    self.parent_source_scroll.selectByIdx(link[0])

    def uiFunc_clear_list(self, mode):
        if mode == 0:
            self.parent_source_scroll.clear()
        else:
            self.parent_target_scroll.clear()

    def uiFunc_select_all_in_list(self, mode):
        pass
        
    def uiFunc_select_from_ui(self, mode):
      mc.select(cl=True)

      if mode == 0:
        idxs = self.parent_source_scroll.getSelectedIdxs()
        for idx in idxs:
          mc.select(self.parent_source_items[idx].item, add=True)
      if mode == 1:
        idxs = self.parent_target_scroll.getSelectedIdxs()
        for idx in idxs:
          mc.select(self.parent_target_items[idx].item, add=True)
      if mode == 2:
        idxs = self.parent_source_scroll.getSelectedIdxs()
        for idx in idxs:
          mc.select(self.parent_source_items[idx].item, add=True)
          for link in self.parent_links:
            if link[0] == idx:
              mc.select(self.parent_target_items[link[1]].item, add=True)      
      if mode == 3:
        idxs = self.parent_target_scroll.getSelectedIdxs()
        for idx in idxs:
          mc.select(self.parent_target_items[idx].item, add=True)
          for link in self.parent_links:
            if link[1] == idx:
              mc.select(self.parent_source_items[link[0]].item, add=True)

    def uiFunc_link_by_name(self, *args):
        self.parent_links = []

        for i, trg in enumerate(self.parent_target_items):
            wantedLink = []
            closest = sys.maxsize
            for j, src in enumerate(self.parent_source_items):
                closeness = STRING.levenshtein(trg.item, src.item)
                if closeness < closest:
                    wantedLink = [j, i]
                    closest = closeness
            
            if not self.has_link(wantedLink, self.parent_links):
                make_link = True
                if not self.var_mocap_allow_multiple_targets.value:
                    current_closest = sys.maxsize
                    for link in self.parent_links:
                        if link[0] == wantedLink[0]:
                            closeness = STRING.levenshtein(self.parent_target_items[link[1]].item, self.parent_source_items[link[0]].item)
                            if closeness < current_closest:
                                current_closest = closeness
                    if current_closest < closest:
                        make_link = False

                    # remove current links if we're making a new link
                    remove_indexes = []
                    if make_link:
                        for i, link in enumerate(self.parent_links):
                            if link[0] == wantedLink[0]:
                                remove_indexes.append(i)
                        remove_indexes.reverse()
                        for idx in remove_indexes:
                            del self.parent_links[idx]
                if make_link:
                    self.parent_links.append(wantedLink)

        self.refresh_aliases()


    def uiFunc_link_by_distance(self, *args):
        self.parent_links = []

        for i, trg in enumerate(self.parent_target_items):
            wantedLink = []
            closest = sys.float_info.max
            for j, src in enumerate(self.parent_source_items):
                closeness = DIST.get_distance_between_targets([src.item, trg.item])
                if closeness < closest:
                    wantedLink = [j, i]
                    closest = closeness
            
            if not self.has_link(wantedLink, self.parent_links):
                make_link = True
                if not self.var_mocap_allow_multiple_targets.value:
                    current_closest = sys.float_info.max
                    for link in self.parent_links:
                        if link[0] == wantedLink[0]:
                            closeness = DIST.get_distance_between_targets( [self.parent_target_items[link[1]].item, self.parent_source_items[link[0]].item] )
                            if closeness < current_closest:
                                current_closest = closeness
                    if current_closest < closest:
                        make_link = False

                    # remove current links if we're making a new link
                    remove_indexes = []
                    if make_link:
                        for i, link in enumerate(self.parent_links):
                            if link[0] == wantedLink[0]:
                                remove_indexes.append(i)
                        remove_indexes.reverse()
                        for idx in remove_indexes:
                            del self.parent_links[idx]
                if make_link:
                    self.parent_links.append(wantedLink)

        self.refresh_aliases()

    def uiFunc_link_by_index(self, *args):
        self.parent_links = []

        for i, trg in enumerate(self.parent_target_items):
            wantedLink = [min(i, len(self.parent_source_items)-1), i]
            self.parent_links.append(wantedLink)

        self.refresh_aliases()

    def uiFunc_add_selected_to_list(self, *args):
        print("Button1")

    # add items to scroll lists
    def uiFunc_add_to_parent_source(self, *args):
        for item in mc.ls(sl=True):
            if not item in [x.item for x in self.parent_source_items]:
                self.parent_source_items.append( cgmListItem(item, item) )
        
        self.refresh_aliases()
        self.print_data()

    def uiFunc_add_to_parent_target(self, *args):
        for item in mc.ls(sl=True):
            if not item in [x.item for x in self.parent_target_items]:
                self.parent_target_items.append( cgmListItem(item, item, {"constraintType":"o"}) )

        self.refresh_aliases()
        self.print_data()

    def uiFunc_set_connection_pose(self, *args):
        """Legacy vector offsets. Does not overwrite links that already have local TR."""
        self.connection_data = self._sync_connection_data_from_ui()
        legacy = []
        skipped = []
        for conn in self.connection_data:
            if MOCAPALIGN.has_local_offsets(conn):
                skipped.append(conn.get('target') or conn.get('source'))
            else:
                legacy.append(conn)
        if legacy:
            set_connection_offsets(legacy)
            legacy_by_pair = {(c.get('source'), c.get('target')): c for c in legacy}
            for i, conn in enumerate(self.connection_data):
                key = (conn.get('source'), conn.get('target'))
                if key in legacy_by_pair:
                    self.connection_data[i] = legacy_by_pair[key]
        if skipped:
            log.info("Manual Set skipped {0} link(s) with local offsets (left unchanged)".format(len(skipped)))

    def uiFunc_rig_ns_from_selection(self, *args):
        sel = mc.ls(sl=True) or []
        if not sel:
            log.warning("Select a namespaced rig control")
            return
        leaf = sel[0].split('|')[-1]
        if ':' not in leaf:
            log.warning("Selection has no namespace: {0}".format(sel[0]))
            return
        ns = leaf.rsplit(':', 1)[0] + ':'
        self.tf_rig_namespace(edit=True, text=ns)
        self.var_mocap_rig_namespace.setValue(ns)

    def uiFunc_skel_roots_from_selection(self, *args):
        sel = mc.ls(sl=True, long=True) or []
        if not sel:
            log.warning("Select skeleton root transform(s)")
            return
        text = ';'.join(sel)
        self.tf_skel_roots(edit=True, text=text)
        self.var_mocap_skel_roots.setValue(text)
        log.info("Skeleton roots set ({0})".format(len(sel)))

    def _get_rig_ns(self):
        try:
            text = self.tf_rig_namespace(q=True, text=True) or ''
        except Exception:
            text = self.var_mocap_rig_namespace.value or ''
        self.var_mocap_rig_namespace.setValue(text)
        return text

    def _get_skel_roots(self):
        try:
            text = self.tf_skel_roots(q=True, text=True) or ''
        except Exception:
            text = self.var_mocap_skel_roots.value or ''
        self.var_mocap_skel_roots.setValue(text)
        return [p.strip() for p in text.replace(',', ';').split(';') if p.strip()]

    def _align_roots_ok_for_capture(self):
        """Block capture/snap when patterns need skeleton roots and none are set."""
        roots = self._get_skel_roots()
        if roots:
            return True
        if MOCAPALIGN.count_ambiguous_skel_contexts() <= 1:
            return True
        self._sync_connection_data_from_ui()
        for conn in self.connection_data or []:
            pat = (conn.get('sourcePattern') or conn.get('source_pattern') or conn.get('source'))
            if MOCAPALIGN.source_pattern_needs_skel_roots(pat):
                log.error("Multiple MetaHuman-style skeletons in scene. Set Skel Roots from selection before Capture/Snap.")
                print("=== mocap align ===\nMultiple skeleton roots detected — set Skel Roots, then retry.\n")
                return False
        return True

    def _patch_target_scroll_item_as_str(self):
        """
        Target scroll shows cgmListItem.alias strings only (Feature_CgmToolUI).
        Default MelObjectScrollList.itemAsStr strips after the last ':' which
        removes [n] indices when link suffixes or Hondo:[n] base rows are present.
        """
        self.parent_target_scroll.itemAsStr = lambda item: str(item)

    def refresh_parent_scrolls(self, *args):
        self._patch_target_scroll_item_as_str()
        self.parent_source_scroll.setItems( [x.alias for x in self.parent_source_items] )
        self.parent_target_scroll.setItems( [x.alias for x in self.parent_target_items] )

    def _sync_connection_data_from_ui(self):
        """Rebuild connection list from UI links, preserving existing offset keys."""
        ui_data = self.get_ui_connection_data()
        old_list = list(self.connection_data or [])
        old_by_pattern = {}
        for conn in old_list:
            old_by_pattern[MOCAPALIGN.connection_pattern_key(conn)] = conn

        keep_keys = ('localTranslate', 'localRotate', 'positionOffset',
                     'offsetForward', 'offsetUp', 'sourcePattern', 'targetPattern',
                     'source_pattern', 'target_pattern',
                     'sourceResolved', 'targetResolved', 'alignLocator')
        merged = []
        for li, data in enumerate(ui_data):
            key = MOCAPALIGN.connection_pattern_key(data)
            prev = old_by_pattern.get(key)
            if not prev and li < len(old_list):
                prev = old_list[li]
            if prev:
                for k in keep_keys:
                    if k in prev:
                        data[k] = prev[k]
            merged.append(data)
        self.connection_data = merged
        return merged

    def _reresolve_connection_data(self):
        """Sync UI links then resolve patterns to scene nodes."""
        self._sync_connection_data_from_ui()
        MOCAPALIGN.resolve_connections(
            self.connection_data,
            rig_ns=self._get_rig_ns(),
            skel_roots=self._get_skel_roots(),
        )
        return self.connection_data

    def uiFunc_capture_offsets(self, *args):
        if not self._align_roots_ok_for_capture():
            return
        self._reresolve_connection_data()
        if not self.connection_data:
            log.warning("No links to capture")
            return
        MOCAPALIGN.capture_alignment_offsets(self.connection_data)

    def uiFunc_snap_connections(self, selected_only=False, *args):
        if not self._align_roots_ok_for_capture():
            return
        self._reresolve_connection_data()
        indices = None
        if selected_only:
            idxs = self.parent_target_scroll.getSelectedIdxs()
            if not idxs:
                log.warning("Select target list items to snap")
                return
            indices = []
            for li, link in enumerate(self.parent_links):
                if link[1] in idxs:
                    indices.append(li)
        MOCAPALIGN.snap_connections(
            self.connection_data,
            indices=indices,
            rig_ns=self._get_rig_ns(),
            skel_roots=self._get_skel_roots(),
        )

    def uiFunc_show_mapping_report(self, *args):
        """Open scrollable mapping resolution report (Tools menu)."""
        win_name = '{0}_mappingReportWin'.format(self.__class__.WINDOW_NAME)
        self._reresolve_connection_data()
        text = MOCAPALIGN.format_mapping_report(
            self.connection_data,
            rig_ns=self._get_rig_ns(),
            skel_roots=self._get_skel_roots(),
        )
        if mc.window(win_name, exists=True):
            mc.deleteUI(win_name)
        mc.window(win_name, title='Mocap Align Mapping Report', sizeable=True, widthHeight=(720, 520))
        mc.columnLayout(adjustableColumn=True, rowSpacing=4, columnAttach=('both', 6))
        mc.scrollField(editable=False, wordWrap=False, font='smallFixedWidthFont', text=text, height=460)
        mc.button(label='Close', command=lambda *_a: mc.deleteUI(win_name))
        mc.showWindow(win_name)
        print("\n=== mocap align mapping report ===\n{0}\n=== end mapping report ===\n".format(text))

    def uiFunc_create_align_locs(self, *args):
        self._reresolve_connection_data()
        MOCAPALIGN.create_debug_locs(self.connection_data)

    def uiFunc_delete_align_locs(self, *args):
        MOCAPALIGN.delete_debug_locs(self.connection_data)

    # helper functions
    def save_options(self, *args):
        log.debug("Saving Options")

    def add_link(self, link, link_list):
        if self.has_link(link, link_list):
            return

        trg_index = link[1]

        if( trg_index in [x[1] for x in link_list] ):
            link_list[[x[1] for x in link_list].index(trg_index)] = link
        else:
            link_list.append(link)

    def has_link(self, link, link_list):
        for list_link in link_list:
            if list_link[0] == link[0] and list_link[1] == link[1]:
                return True
        return False

    def remove_link(self, link, link_list):
        for i, list_link in enumerate(link_list):
            if list_link[0] == link[0] and list_link[1] == link[1]:
                del link_list[i]
                break

        self.refresh_aliases()

    def print_data(self, *args):
        log.debug( "==  DATA  ==")
        log.debug( "parent source >> %s" % ','.join([x.item for x in self.parent_source_items]))
        log.debug( "parent target >> %s" % ','.join([x.item for x in self.parent_target_items]))
        for i,link in enumerate(self.parent_links):
            log.debug("link[%i] >> [%i]%s -> [%i]%s" % (i, link[0], self.parent_source_items[link[0]].item, link[1], self.parent_target_items[link[1]].item)) 

    # refresh UI displays
    def _short_name_display(self, name):
        """Short name for list display — rig namespace kept, reference namespace stripped."""
        if not name:
            return name
        if not mc.objExists(name):
            return str(name).split('|')[-1].split(':')[-1]
        long_name = mc.ls(name, long=True)[0]
        short = NAMES.get_short(long_name)
        try:
            if mc.referenceQuery(long_name, isNodeReferenced=True):
                ref_ns = mc.referenceQuery(long_name, namespace=True)
                ref_token = str(ref_ns).strip(':')
                if ref_token and short.startswith(ref_token + ':'):
                    short = short[len(ref_token) + 1:]
        except Exception:
            pass
        return short

    def parse_alias(self, name):
        if not name:
            return name
        if self.var_mocap_show_short_names.value:
            return self._short_name_display(name)

        split_name = str(name).split('|')
        for i, new_name in enumerate(split_name):
            if ':' in new_name:
                split_name[i] = '(' + new_name.replace(':', ')')

        return '/'.join(split_name)

    def _format_target_list_alias(self, index, item_path):
        """
        Target scroll list display. Index prefix is display-only (never in .item / CCL).
        Always leading [n] — namespace lives in the name segment after the index.
        """
        name = self.parse_alias(item_path)
        if not name:
            return '[%i]' % index
        return '[%i] %s' % (index, name)

    def refresh_aliases(self, *args):
        # refresh parent aliases
        for i, item in enumerate(self.parent_source_items):
            target_idxs = sorted([link[1] for link in self.parent_links if link[0] == i])
            base = self.parse_alias(self.parent_source_items[i].item)
            if target_idxs:
                idx_str = ','.join('[%i]' % x for x in target_idxs)
                self.parent_source_items[i].alias = '%s -> %s' % (base, idx_str)
            else:
                self.parent_source_items[i].alias = base
        for i, item in enumerate(self.parent_target_items):
            self.parent_target_items[i].alias = self._format_target_list_alias(i, self.parent_target_items[i].item)

            for link in self.parent_links:
                if link[1] == i:
                    self.parent_target_items[i].alias += " <- %s  [%s]" % (self.parse_alias(self.parent_source_items[link[0]].item), self.parent_target_items[link[1]].data["constraintType"])
                    break

            #self.parent_target_items[i].alias = self.parent_target_items[i].alias.replace('|', '/')

        self.refresh_parent_scrolls()

    # create live constraints between source and targets
    def uiFunc_make_constraints(self, *args):
        ui_data = self.get_ui_connection_data()
        for conn in ui_data:
            if conn['setPosition']:
                mc.pointConstraint( conn['source'], conn['target'], mo=True )
            if conn['setRotation']:
                mc.orientConstraint( conn['source'], conn['target'], mo=True )

    def _uiFunc_write_ccl(self, file):
        """Validate, build CCL payload, and write to disk. Returns True on success."""
        skel_roots = self._get_skel_roots()
        if not skel_roots:
            log.error("Set Skel Roots before saving CCL")
            print("=== mocap align ===\nCannot save CCL without Skel Roots set.\n")
            return False

        try:
            COREPATHS.prepare_paths_for_write(
                [file],
                mDat=COREPATHS.get_project_mDat(),
                confirm_p4=True,
                _str_func='mocapBakeTools._uiFunc_write_ccl',
            )
        except COREPATHS.PathWritePrepareError as err:
            if getattr(err, 'reason', None) == 'Save cancelled':
                log.info('CCL save cancelled')
            else:
                log.error(str(err))
                print("=== mocap align ===\n{0}\n".format(err))
            return False

        self._reresolve_connection_data()
        validation = MOCAPALIGN.validate_connections_for_save(
            self.connection_data,
            skel_roots=skel_roots,
            rig_ns=self._get_rig_ns(),
        )
        if not validation.get('ok'):
            log.error("CCL save blocked — fix unresolved/ambiguous sources")
            print("=== mocap align save blocked ===")
            for err in validation.get('errors') or []:
                print(err)
                log.warning(err)
            print("=== end ===\n")
            return False

        stored_data = MOCAPALIGN.connections_to_ccl(
            self.connection_data,
            rig_ns=self._get_rig_ns(),
            skel_roots=skel_roots,
            source_items=[x.item for x in self.parent_source_items],
            source_data=[x.data for x in self.parent_source_items],
            target_items=[x.item for x in self.parent_target_items],
            target_data=[x.data for x in self.parent_target_items],
            links=self.parent_links,
        )
        MOCAPALIGN.save_ccl(file, stored_data, skip_prepare=True)

        if validation.get('details'):
            print("=== mocap align save patterns ===")
            for line in validation['details']:
                print(line)
            print("Saved: {0}".format(file))
            print("=== end ===\n")

        self._loaded_ccl = file
        self.var_mocap_last_ccl.setValue(file)
        self.mPathList_recent.append_recent(file)
        self.uiStatus_refresh()
        return True

    # saves link data to current CCL path (or Save As when none loaded)
    def uiFunc_save_data(self, *args):
        _path = self._loaded_ccl or self.var_mocap_last_ccl.value
        if _path and os.path.exists(_path):
            self._uiFunc_write_ccl(_path)
        else:
            self.uiFunc_save_as_data()

    def uiFunc_save_as_data(self, *args):
        basicFilter = "*.ccl"
        result = mc.fileDialog2(fileFilter=basicFilter, dialogStyle=2, fileMode=0)
        if not result:
            return
        self._uiFunc_write_ccl(result[0])

    # loads link data
    def uiFunc_load_data(self, filepath=None, *args):
        if filepath:
            if not os.path.exists(filepath):
                log.warning("CCL not found: {0}".format(filepath))
                return
            file = filepath
        else:
            basicFilter = "*.ccl"
            result = mc.fileDialog2(fileFilter=basicFilter, fileMode=1, dialogStyle=2)
            if not result:
                return
            file = result[0]

        loaded_data = MOCAPALIGN.load_ccl(file)
        rig_ns = self._get_rig_ns()
        skel_roots = self._get_skel_roots()

        if not skel_roots:
            candidates = MOCAPALIGN.find_candidate_skel_roots()
            if len(candidates) == 1:
                skel_roots = candidates
                text = candidates[0]
                try:
                    self.tf_skel_roots(edit=True, text=text)
                except Exception:
                    pass
                self.var_mocap_skel_roots.setValue(text)
                log.info("Auto-set skeleton root: {0}".format(text))
            elif len(candidates) > 1:
                log.warning("Multiple skeleton roots in scene — set Skel Roots before relying on short-name resolve")

        parsed = MOCAPALIGN.ccl_to_connections(loaded_data, rig_ns=rig_ns, skel_roots=skel_roots)

        self.parent_source_items = []
        self.parent_target_items = []

        src_patterns = parsed['source_items']
        tgt_patterns = parsed['target_items']
        src_data = parsed['source_data'] or [{} for _ in src_patterns]
        tgt_data = parsed['target_data'] or [{} for _ in tgt_patterns]

        for i, pat in enumerate(src_patterns):
            data = dict(src_data[i] if i < len(src_data) else {})
            self.parent_source_items.append(cgmListItem(pat, pat, data))

        for i, pat in enumerate(tgt_patterns):
            data = tgt_data[i] if i < len(tgt_data) else {"constraintType": "o"}
            if not data:
                data = {"constraintType": "o"}
            if "constraintType" not in data:
                data = dict(data)
                data["constraintType"] = "o"
            else:
                data = dict(data)
            self.parent_target_items.append(cgmListItem(pat, pat, data))

        self.parent_links = parsed['links'] or []
        self.connection_data = parsed['connections'] or loaded_data[5]

        self.refresh_aliases()
        self.print_data()

        self._loaded_ccl = file
        self.var_mocap_last_ccl.setValue(file)
        self.mPathList_recent.append_recent(file)
        self.uiStatus_refresh()

    # remove items from scroll lists
    def uiFunc_remove_from_parent_source(self, *args):
        idx = self.parent_source_scroll.getSelectedIdxs()[0]

        # remove links
        remove_indexes = []
        for i, link in enumerate(self.parent_links):
            if link[0] == idx:
                remove_indexes.append(i)

        #for ridx in remove_indexes:
        for i, link in enumerate(self.parent_links):
            if link[0] > idx:
                link[0] = link[0]-1
                self.parent_links[i] = link

        remove_indexes.reverse()

        for ridx in remove_indexes:
            del self.parent_links[ridx]

        del self.parent_source_items[idx]

        self.print_data()

        self.refresh_aliases()
        #self.refresh_parent_scrolls()

    def uiFunc_remove_from_parent_target(self, *args):
        idxs = self.parent_target_scroll.getSelectedIdxs()

        remove_indexes = []
        for idx in idxs:
            # remove links
            for i, link in enumerate(self.parent_links):
                if link[1] == idx:
                    remove_indexes.append(i)
                if link[1] > idx:
                    link[1] = link[1]-1
                    self.parent_links[i] = link

            del self.parent_target_items[idx]

        remove_indexes.reverse()

        for ridx in remove_indexes:
            del self.parent_links[ridx]

        self.print_data()

        self.refresh_aliases()

    def _get_parent_target_selected_idxs(self):
        idxs = self.parent_target_scroll.getSelectedIdxs()
        if not idxs:
            log.warning("Select target list items to reorder")
            return None
        if not self.parent_target_items:
            return None
        return idxs

    def _apply_parent_target_list_order(self, new_items, selected_old_idxs):
        """Replace target list, remap link indices, refresh UI selection."""
        old_items = [x.item for x in self.parent_target_items]
        self.parent_target_items = list(new_items)

        new_item_names = [x.item for x in self.parent_target_items]
        idx_map = {old_i: new_item_names.index(old_items[old_i]) for old_i in range(len(old_items))}
        for link in self.parent_links:
            link[1] = idx_map[link[1]]

        self.refresh_aliases()

        new_sel = sorted([idx_map[i] for i in selected_old_idxs])
        self.parent_target_scroll.clearSelection()
        for idx in new_sel:
            self.parent_target_scroll.selectByIdx(idx)

        self.print_data()
        return True

    def uiFunc_reorder_parent_target(self, direction=0, *args):
        """
        Reorder selected target list items. direction 0 = up, 1 = down (lists.reorderListInPlace).
        """
        idxs = self._get_parent_target_selected_idxs()
        if idxs is None:
            return False

        to_move = [self.parent_target_items[i] for i in idxs]
        new_items = list(self.parent_target_items)

        lists.reorderListInPlace(new_items, to_move, direction)
        return self._apply_parent_target_list_order(new_items, idxs)

    def uiFunc_reorder_parent_target_to_top(self, *args):
        idxs = self._get_parent_target_selected_idxs()
        if idxs is None:
            return False

        idxs = sorted(idxs)
        to_move = [self.parent_target_items[i] for i in idxs]
        remaining = [self.parent_target_items[i] for i in range(len(self.parent_target_items)) if i not in idxs]
        return self._apply_parent_target_list_order(to_move + remaining, idxs)

    def uiFunc_reorder_parent_target_to_bottom(self, *args):
        idxs = self._get_parent_target_selected_idxs()
        if idxs is None:
            return False

        idxs = sorted(idxs)
        to_move = [self.parent_target_items[i] for i in idxs]
        remaining = [self.parent_target_items[i] for i in range(len(self.parent_target_items)) if i not in idxs]
        return self._apply_parent_target_list_order(remaining + to_move, idxs)

    def uiFunc_reorder_parent_target_set_index(self, *args):
        idxs = self._get_parent_target_selected_idxs()
        if idxs is None:
            return False

        count = len(self.parent_target_items)
        max_idx = max(0, count - len(idxs))
        default = str(min(sorted(idxs)[0], max_idx))

        result = mc.promptDialog(
            title='Target list index',
            message='Move selected to index (0 = top, max {0}):'.format(max_idx),
            button=['OK', 'Cancel'],
            defaultButton='OK',
            cancelButton='Cancel',
            dismissString='Cancel',
            text=default,
        )
        if result != 'OK':
            return False

        try:
            target_idx = int(mc.promptDialog(query=True, text=True))
        except (TypeError, ValueError):
            log.warning("Target index must be an integer")
            return False

        if target_idx < 0 or target_idx > max_idx:
            log.warning("Target index must be between 0 and {0}".format(max_idx))
            return False

        idxs = sorted(idxs)
        to_move = [self.parent_target_items[i] for i in idxs]
        remaining = [self.parent_target_items[i] for i in range(len(self.parent_target_items)) if i not in idxs]
        new_items = remaining[:target_idx] + to_move + remaining[target_idx:]
        return self._apply_parent_target_list_order(new_items, idxs)

    # establish links upon double click
    def uiFunc_toggle_link_parent_targets(self, *args):
        src_index = self.parent_source_scroll.getSelectedIdxs()[0]
        trg_indexes = self.parent_target_scroll.getSelectedIdxs()
        
        # remove existing links from trg if only 1 is allowed
        if not self.var_mocap_allow_multiple_targets.value:
            remove_indexes = []
            for i, link in enumerate(self.parent_links):
                if link[0] == src_index and link[1] != trg_indexes[0]:
                    remove_indexes.append(i)

            remove_indexes.reverse()

            for idx in remove_indexes:
                del self.parent_links[idx]

        links = [[ src_index, x ] for x in trg_indexes]
        for link in links:
            if self.has_link(link, self.parent_links):
                self.remove_link(link, self.parent_links)
            else:
                self.add_link(link, self.parent_links)

        self.refresh_aliases()
        #self.refresh_parent_scrolls()

        for x in trg_indexes:
            self.parent_target_scroll.selectByIdx(x)
        self.parent_source_scroll.selectByIdx(src_index)

        self.print_data()

    # def uiFunc_toggle_link_orient_targets(self, *args):
    #     src_index = self.orient_source_scroll.getSelectedIdxs()[0]
    #     trg_indexes = self.orient_target_scroll.getSelectedIdxs()
        
    #     links = [[ src_index, x ] for x in trg_indexes]
    #     for link in links:
    #         if self.has_link(link, self.orient_links):
    #             self.remove_link(link, self.orient_links)
    #         else:
    #             self.add_link(link, self.orient_links)

    #     self.refresh_aliases()
    #     # self.refresh_orient_scrolls()

    #     for x in trg_indexes:
    #         self.orient_target_scroll.selectByIdx(x)
    #     self.orient_source_scroll.selectByIdx(src_index) 

    #     self.print_data()

    # on select item in scroll list
    def uiFunc_on_select_parent_source_item(self, *args):
        pass

    def uiFunc_on_select_parent_target_item(self, *args):
        pass

    # select associated link items
    def uiFunc_select_parent_source_link(self, *args):
        idx = self.parent_source_scroll.getSelectedIdxs()[0]
        if idx in [x[0] for x in self.parent_links]:
            self.parent_target_scroll.clearSelection()
            for link in self.parent_links:
                if link[0] == idx:
                    self.parent_target_scroll.selectByIdx(link[1])

    def uiFunc_select_parent_target_link(self, *args):
        if len(self.parent_target_scroll.getSelectedIdxs()) > 1:
            return

        idx = self.parent_target_scroll.getSelectedIdxs()[-1]

        if idx in [x[1] for x in self.parent_links]:
            self.parent_target_scroll.clearSelection()
            self.parent_target_scroll.selectByIdx(idx)

            link = self.parent_links[[x[1] for x in self.parent_links].index(idx)]
            self.parent_source_scroll.clearSelection()
            self.parent_source_scroll.selectByIdx(link[0])

    def update_connection_data(self, *args):
        ui_data = self.get_ui_connection_data()

        # cull old links
        old_link_indexes = []
        for i, conn in enumerate(self.connection_data):
            connection_exists = False
            for data in ui_data:
                if data['source'] == conn['source'] and data['target'] == conn['target']:
                    connection_exists = True
            if connection_exists:
                old_link_indexes.append(i)

        old_link_indexes.reverse()

        for i in old_link_indexes:
            del self.connection_data[i]

        # populate with new links
        for data in ui_data:
            connection_exists = False
            for conn in self.connection_data:
                if data['source'] == conn['source'] and data['target'] == conn['target']:
                    connection_exists = True

            if not connection_exists:
                self.connection_data.append(data)

    def get_ui_connection_data(self, *args):
        connection_data = []
        for link in self.parent_links:
            src_pat = self.parent_source_items[link[0]].item
            tgt_pat = self.parent_target_items[link[1]].item
            ctype = self.parent_target_items[link[1]].data.get("constraintType", "o")
            connection_data.append({
                'source': src_pat,
                'target': tgt_pat,
                'sourcePattern': src_pat,
                'targetPattern': tgt_pat,
                'source_pattern': src_pat,
                'target_pattern': tgt_pat,
                'setPosition': 'p' in str(ctype),
                'setRotation': True,
            })

        return connection_data

def set_connection_offsets(connection_data):
    '''applies offset positions to the input dictionary
    input >
    [{'source':string, 'target':string, 'setPosition':bool, 'setRotation':bool}...]
    output > 
    [{'source':string, 'target':string, 'setPosition':bool, 'setRotation':bool, 'offsetPosition':(3), 'offsetForward':(3), 'offsetUp':(3)}...]'''
    
    for i, connection in enumerate(connection_data):
        source_pos = POS.get(connection['source'], asEuclid=True)
        target_pos = POS.get(connection['target'], asEuclid=True)

        v = target_pos - source_pos
        connection['positionOffset'] = [v.x, v.y, v.z]

        v = TRANS.transformInverseDirection(connection['source'], TRANS.transformDirection(connection['target'], euclid.Vector3(0,0,1)))
        connection['offsetForward'] = [v.x, v.y, v.z]

        v = TRANS.transformInverseDirection(connection['source'], TRANS.transformDirection(connection['target'], euclid.Vector3(0,1,0)))
        connection['offsetUp'] = [v.x, v.y, v.z]


def bake(connection_data, start, end):
    """
    Dual-path bake: local-TR snap for links with localTranslate/localRotate;
    legacy POS.set + aim_atPoint for the rest (unchanged behavior).
    """
    cgmGEN.playback_stop()

    local_idxs = []
    legacy = []
    for i, conn in enumerate(connection_data or []):
        if MOCAPALIGN.has_local_offsets(conn):
            local_idxs.append(i)
        else:
            legacy.append(conn)

    if local_idxs:
        MOCAPALIGN.bake_connections(connection_data, start, end, indices=local_idxs)

    if not legacy:
        return

    bake_range = list(range( int(math.floor(start)), int(math.floor(end+1))))
    if end < start:
        bake_range = list(range(int(math.floor(end)),int(math.floor(start+1))))
        bake_range.reverse()

    mc.undoInfo(openChunk=True)
    try:
        for i in bake_range:
            mc.currentTime(i)
            for conn in legacy:
                source_pos = POS.get(conn['source'])
                
                if conn['setPosition']:
                    positionOffset = euclid.Vector3(0,0,0)
                    if 'positionOffset' in conn:
                        pos = conn['positionOffset']
                        positionOffset = euclid.Vector3(pos[0], pos[1], pos[2])
                    wanted_position = source_pos + positionOffset
                    POS.set(conn['target'], [wanted_position.x, wanted_position.y, wanted_position.z])
                    mc.setKeyframe('%s.translate' % conn['target'])
                
                target_pos = POS.get(conn['target'])
                if conn['setRotation']:
                    offsetForward = euclid.Vector3(0,0,1)
                    if 'offsetForward' in conn:
                        fwd = conn['offsetForward']
                        offsetForward = euclid.Vector3(fwd[0], fwd[1], fwd[2])
                    offsetUp = euclid.Vector3(0,1,0)
                    if 'offsetUp' in conn:
                        up = conn['offsetUp']
                        offsetUp = euclid.Vector3(up[0], up[1], up[2])
                    fwd = TRANS.transformDirection(conn['source'], offsetForward)
                    up = TRANS.transformDirection(conn['source'], offsetUp)
                    SNAP.aim_atPoint(conn['target'], target_pos + fwd, vectorUp=up, mode='matrix')
                    mc.setKeyframe('%s.rotate' % conn['target'])
    finally:
        mc.undoInfo(closeChunk=True)


_d_annotations = {'addSource':'Adds the selected objects to the source list.',
                  'removeSource':'Removed the selected object from the source list.',
                  'addTarget':'Adds the selected object to the target list.',
                  'removeTarget':'Removed the selected object from the target list.',
                  'moveTargetUp':'Move selected target list items up (order is saved in CCL)',
                  'moveTargetDn':'Move selected target list items down (order is saved in CCL)',
                  'moveTargetTop':'Move selected target list items to top of list',
                  'moveTargetBottom':'Move selected target list items to bottom of list',
                  'moveTargetSetIndex':'Prompt for list index and move selected targets there (0 = top)',
                  'linkName':'Link source and target by closest name between target and source.',
                  'linkDistance':'Link source and target by shortest distance between target and source.',
                  'setPointOrient':'Set source/target constraints to point/orient',
                  'setPointOrientAll':'Set source/target constraints to point/orient on all targets',
                  'setOrient':'Set source/target constraints to orient',
                  'setOrientAll':'Set source/target constraints to orient on all targets',
                  'setConnectionPose':'Set connection offset based off these source/target positions',
                  'captureOffsets':'Capture localTranslate/localRotate at bind pose (doLoc parented to source)',
                  'snapAll':'Snap all links that have local offsets; report missing data for the rest',
                  'snapSel':'Snap selected target links that have local offsets',
                  'rigNsFromSel':'Set rig namespace from selected control',
                  'skelRootsFromSel':'Set skeleton roots from selection (semicolon-separated)',
                  'linkIndex':'Link source and target by list index',
                  'sliderRange':' Push the slider range values to the int fields',
                  'selectedRange': 'Push the selected timeline range (if active)',
                  'sceneRange':'Push scene range values to the int fields',
                  '<<<':'Bake within a context of keys in range prior to the current time',
                  'All':'Bake within a context of the entire range of keys ',
                  '>>>':'Bake within a context of keys in range after the current time',
                  'attach':'Create a loc of the selected object AND start a clickMesh instance to setup an attach point on a mesh in scene'}