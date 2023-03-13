"""
------------------------------------------
projectDiffusionTool: cgm.core.tools
Author: David Bokser
email: cgmonks.info@gmail.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
Example ui to start from
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

from functools import partial
from cgm.tools import stableDiffusionTools as sd
from cgm.tools import renderTools as rt

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='projectDiffusionTool'

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE = 650,350
    TOOLNAME = '{0}.ui'.format(__toolname__)
    
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

 
    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc = cgmGEN.Callback(self.buildMenu_first))

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        #>>> Reset Options		                     

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )

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
        

def buildColumn_main(self, parent, asScroll=False):
    _tabs = mc.tabLayout()

    _setup = buildColumn_settings(self, _tabs, asScroll = False)
    _project = buildColumn_project(self, _tabs, asScroll = False)
    _edit = buildColumn_edit(self, _tabs, asScroll = False)

    mc.tabLayout(_tabs, edit=True, tabLabel=((_setup, 'Setup'), (_project, 'Project'), (_edit, 'Edit')))

    return _tabs

def buildColumn_settings(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    
    cgmUI.add_Header('Setup')

    #>>> Mesh Load
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Mesh:',align='right')
    self.uiTextField_baseObject = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_baseObject)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_shape(self.uiTextField_baseObject, enforcedType='mesh'))
    cgmUI.add_Button(_row, 'Select', 
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_baseObject),
                        annotationText='')               
    mUI.MelSpacer(_row,w = 5)            
    _row.layout()

    #>>> Load Projection Camera
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Projection Cam:',align='right')
    self.uiTextField_projectionCam = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_projectionCam)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_shape(self.uiTextField_projectionCam, enforcedType = 'camera'))
    cgmUI.add_Button(_row, 'Make',
                        lambda *a:uiFunc_make_projection_camera(self),
                        annotationText='Make a projection camera')
    cgmUI.add_Button(_row, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_projectionCam),
                        annotationText='')
    mUI.MelSpacer(_row,w = 5)
    _row.layout()


    #>>> Load Projection Shader
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Projection Shader:',align='right')
    self.uiTextField_projectionShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_projectionShader)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_projectionShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(_row, 'Make', 
                        lambda *a:uiFunc_make_projection_shader(self),
                        annotationText='Make a projection shader')
    cgmUI.add_Button(_row, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_projectionShader),
                        annotationText='')
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    #>>> Load Alpha Shader
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Alpha Shader:',align='right')
    self.uiTextField_alphaShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_alphaShader)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_alphaShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(_row, 'Make',
                        lambda *a:uiFunc_make_alpha_shader(self),
                        annotationText='')
    cgmUI.add_Button(_row, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_alphaShader),
                        annotationText='')
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    #>>> Load Composite Shader
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Composite Shader:',align='right')
    self.uiTextField_compositeShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_compositeShader)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_compositeShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(_row, 'Make', lambda *a:uiFunc_make_composite_shader(self),annotationText='')
    cgmUI.add_Button(_row, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_compositeShader),
                        annotationText='')
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    #>>> Load Depth Shader
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Depth Shader:',align='right')
    self.uiTextField_depthShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_depthShader)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_depthShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(_row, 'Make', lambda *a:uiFunc_make_depth_shader(self),annotationText='')
    cgmUI.add_Button(_row, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_depthShader),
                        annotationText='')
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    #>>> Automatic1111 Info
    mc.setParent(_inside)
    cgmUI.add_Header('Automatic1111 Settings')

    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='URL:',align='right')
    self.uiTextField_automaticURL = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=True,
                                                    text='127.0.0.1:7860',
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_automaticURL)
    _row.layout()

    uiFunc_auto_populate_fields(self)
    return _inside

def buildColumn_project(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    

    cgmUI.add_Header('Project')

    #>>> Prompt
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate', height=60)
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Prompt:',align='right')
    self.uiTextField_prompt = mUI.MelScrollField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    wordWrap = True,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.uiTextField_prompt)
    _row.layout()

    #>>> Negative Prompt
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate', height=60)
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Negative Prompt:',align='right')
    self.uiTextField_negativePrompt = mUI.MelScrollField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    wordWrap = True,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    _row.setStretchWidget(self.uiTextField_negativePrompt)
    mUI.MelSpacer(_row,w = 5)

    _row.layout()

    #>>> Properties
    #_row = mUI.MelHLayout(_inside,expand = False,ut = 'cgmUISubTemplate', padding=5)
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w = 5)
    mUI.MelLabel(_row,l='Steps:',align='right')
    self.uiIF_Steps = mUI.MelIntField(_row,
                                                   minValue = 1,
                                                   value = 5,
                                                   annotation = 'Degree of curve to create')	 	    
    mUI.MelLabel(_row,l='Seed:',align='right')
    self.uiIF_Seed = mUI.MelIntField(_row,
                                                   minValue = -1,
                                                   value = -1,
                                                   annotation = 'Degree of curve to create')	 	    
    
    cgmUI.add_Button(_row,'Last', lambda *a:uiFunc_getLastSeed(self))

    _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

    mUI.MelLabel(_row,l='Size:',align='right')

    self.uiIF_Width = mUI.MelIntField(_row,
                                                   minValue = 32,
                                                   value = 512,
                                                   annotation = 'Degree of curve to create')	 	    

    self.uiIF_Height = mUI.MelIntField(_row,
                                                   minValue = 32,
                                                   value = 512,
                                                   annotation = 'Degree of curve to create')	 	    

    _sizeOptions = ['512x512','1024x1024','2048x2048', '640x360', '1280x720','1920x1080']
    self.uiOM_SizeMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
    for option in _sizeOptions:
        self.uiOM_SizeMenu.append(option)

    self.uiOM_SizeMenu(edit=True, changeCommand=cgmGEN.Callback(uiFunc_setSize,self))

    #_row.setStretchWidget( self.sizeMenu )
    mUI.MelSpacer(_row,w = 5)

    _row.layout()

    #>>> Model
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Model:',align='right')
    _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

    self.modelMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
    
    uiFunc_updateModelsFromAutomatic(self)

    #self.modelMenu.setValue( self._optionDict['plane'] )

    #self.modelMenu(edit=True, changeCommand=cgmGEN.Callback(uiFunc_set_plane,self))

    cgmUI.add_Button(_row,'Refresh', lambda *a:uiFunc_updateModelsFromAutomatic(self))
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    mc.setParent(_inside)
    cgmUI.add_Header('Materials')
    
    #>>> Shader Assignment
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Assign Material:',align='right')
    _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )
    cgmUI.add_Button(_row,'Depth', lambda *a:uiFunc_assign_material(self, self.uiTextField_depthShader))
    cgmUI.add_Button(_row,'Projection', lambda *a:uiFunc_assign_material(self, self.uiTextField_projectionShader))
    cgmUI.add_Button(_row,'Alpha', lambda *a:uiFunc_assign_material(self, self.uiTextField_alphaShader))
    cgmUI.add_Button(_row,'Composite', lambda *a:uiFunc_assign_material(self, self.uiTextField_compositeShader))
    cgmUI.add_Button(_row,'Merged', lambda *a:uiFunc_assign_material(self, self.uiTextField_compositeShader))
    mUI.MelSpacer(_row,w = 5)
    _row.layout()

    #>>>Depth Slider...
    depth = 50.0
    depthShader = getDepthShader(self)
    if(depthShader):
        depth = mc.getAttr('%s.distance' % depthShader)

    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w=5)
    mUI.MelLabel(_row,l='Depth Distance:',align='right')
    self.uiFF_depthDistance = mUI.MelFloatField(_row,
                                            w = 40,
                                            ut='cgmUITemplate',
                                            precision = 2,
                                            value = depth, changeCommand=cgmGEN.Callback(uiFunc_setDepth,self, 'field'))  
              
    self.uiSlider_depthDistance = mUI.MelFloatSlider(_row,1.0,100.0,depth,step = 1)
    self.uiSlider_depthDistance.setChangeCB(cgmGEN.Callback(uiFunc_setDepth,self, 'slider'))
    mUI.MelSpacer(_row,w=5)	            
    _row.setStretchWidget(self.uiSlider_depthDistance)#Set stretch    

    uiFunc_setDepth( self, 'field' )

    # Generate Button
    #
    _row = mUI.MelHLayout(_inside,ut='cgmUISubTemplate',padding = 10)
    
    self.animDrawBtn = cgmUI.add_Button(_row,'Generate',
        cgmGEN.Callback(uiFunc_generateImage,self),                         
        #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
        'Generate',h=50)

    _row.layout()    
    #
    # End Generate Button

    return _inside

def buildColumn_edit(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    
    return _inside
    
def uiFunc_auto_populate_fields(self):
    _str_func = 'uiFunc_auto_populate_fields'

    for obj in mc.ls(sl=True):
        # list shapes
        _shapes = mc.listRelatives(obj, shapes=True, type='mesh')
        if _shapes:
            self.uiTextField_baseObject(edit=True, text=_shapes[0])
            break

    for cam in mc.ls("*.cgmCamera"):
        if(mc.getAttr(cam) == 'projection'):
            self.uiTextField_projectionCam(edit=True, text=cam.split('.')[0])
            break

    for shader in mc.ls("*.cgmShader"):
        if(mc.getAttr(shader) == 'sd_projection'):
            self.uiTextField_projectionShader(edit=True, text=shader.split('.')[0])
            continue
        if(mc.getAttr(shader) == 'sd_alpha'):
            self.uiTextField_alphaShader(edit=True, text=shader.split('.')[0])
            continue
        if(mc.getAttr(shader) == 'sd_depth'):
            self.uiTextField_depthShader(edit=True, text=shader.split('.')[0])
            continue
        if(mc.getAttr(shader) == 'sd_composite'):
            self.uiTextField_compositeShader(edit=True, text=shader.split('.')[0])
            continue
    return

def uiFunc_clear_text_field(element):
    _str_func = 'uiFunc_clear_loaded'  
    element(edit=True, text='')   

def uiFunc_set_text_field(element, text):
    _str_func = 'uiFunc_load_text_field_with_selected'  
    element(edit=True, text=text)

def uiFunc_load_text_field_with_shape(element, enforcedType = None):
    _str_func = 'uiFunc_load_text_field_with_shapes'  
    _sel = mc.ls(sl=True)
    _shapes = []
    if _sel:
        _shapes = mc.listRelatives(_sel[0], shapes=True, type=enforcedType)

    if _shapes:
        element(edit=True, text=_shapes[0])
    else:
        log.warning("|{0}| >> Nothing selected.".format(_str_func))
        element(edit=True, text="")

def uiFunc_load_text_field_with_selected(element, enforcedType = None):
    _str_func = 'uiFunc_load_text_field_with_selected'  
    _sel = mc.ls(sl=True)

    if _sel:
        if enforcedType != None:
            if enforcedType in mc.ls(_sel, st=True):
                element(edit=True, text=_sel[0])
            else:
                log.warning("|{0}| >> Not a valid {1}.".format(_str_func, enforcedType))
        else:
            element(edit=True, text=_sel[0])
    else:
        log.warning("|{0}| >> Nothing selected.".format(_str_func))
        element(edit=True, text="")

def uiFunc_select_item_from_text_field(element):
    _str_func = 'uiFunc_select_item_from_text_field'  
    _item = element(query=True, text=True)
    if mc.objExists(_item):
        mc.select(_item)

def uiFunc_assign_material(self, element):
    _str_func = 'uiFunc_assign_material'  
    _mesh = self.uiTextField_baseObject(query=True, text=True)

    if not mc.objExists(_mesh):
        log.warning("|{0}| >> No mesh loaded.".format(_str_func))
        return
    
    _material = element(query=True, text=True)
    
    if not mc.objExists(_material):
        log.warning("|{0}| >> No material loaded.".format(_str_func))
        return
    
    _sg = mc.listConnections(_material, type='shadingEngine')
    if _sg:
        _sg = _sg[0]
    
    rt.assignMaterial(_mesh, _sg)  

def uiFunc_setSize(self):
    _str_func = 'uiFunc_setSize'
    size = self.uiOM_SizeMenu(query=True, value=True)
    width, height = [int(x) for x in size.split('x')]
    self.uiIF_Width(edit=True, value=width)
    self.uiIF_Height(edit=True, value=height)

def uiFunc_make_projection_camera(self):
    cam, shape = rt.makeProjectionCamera()
    self.uiTextField_projectionCam(edit=True, text=shape)

def uiFunc_make_projection_shader(self):
    _str_func = 'uiFunc_make_projection_shader'
    _camera = self.uiTextField_projectionCam(query=True, text=True)

    if not mc.objExists(_camera):
        log.warning("|{0}| >> No camera loaded.".format(_str_func))
        return
    
    shader, sg = sd.makeProjectionShader(_camera)
    self.uiTextField_projectionShader(edit=True, text=shader)

def uiFunc_make_alpha_shader(self):
    _str_func = 'uiFunc_make_alpha_shader'
    _camera = self.uiTextField_projectionCam(query=True, text=True)

    if not mc.objExists(_camera):
        log.warning("|{0}| >> No camera loaded.".format(_str_func))
        return
    
    shader, sg = sd.makeAlphaShader(_camera)
    self.uiTextField_alphaShader(edit=True, text=shader)

def uiFunc_make_composite_shader(self):
    _str_func = 'uiFunc_make_composite_shader'

    shader, sg = sd.makeCompositeShader()
    self.uiTextField_compositeShader(edit=True, text=shader)

def uiFunc_make_depth_shader(self):
    _str_func = 'uiFunc_make_depth_shader'

    shader, sg = sd.makeDepthShader()
    self.uiTextField_depthShader(edit=True, text=shader)

def uiFunc_generateImage(self):
    _str_func = 'uiFunc_generateImage'  
    _prompt = self.uiTextField_prompt(query=True, text=True)
    _negative_prompt = self.uiTextField_negativePrompt(query=True, text=True)
    _steps = self.uiIF_Steps(query=True, value=True)
    _seed = self.uiIF_Seed(query=True, value=True)
    _width = self.uiIF_Width(query=True, v=True)
    _height = self.uiIF_Height(query=True, v=True)
    _model = self.uiOptionMenu_model(query=True, value=True)
    _url = self.uiTextField_url(query=True, text=True)

    imagePath = sd.get_image_from_automatic1111(prompt=prompt, negative_prompt=negative_prompt, steps=steps, seed=seed, size=(width, height), model=model, url=url)
    displayImage(imagePath)

def displayImage(imagePath):
    pass

def uiFunc_setDepth(self, source):
    shader = getDepthShader(self)

    _depth = 0.0

    if(shader):
        _depth = mc.getAttr('%s.distance' % shader)

    if source == 'slider':
        _depth = self.uiSlider_depthDistance(query=True, value=True)
        self.uiFF_depthDistance.setValue(_depth)
        
    elif source == 'field':
        _depth = self.uiFF_depthDistance.getValue()
        self.uiSlider_depthDistance(edit=True, max=max(100.0, _depth))
        self.uiSlider_depthDistance(edit=True, value=_depth, step=1)
    
    if shader:
        mc.setAttr('%s.distance' % shader, _depth)

    #print("depth", _depth)

def uiFunc_updateModelsFromAutomatic(self):
    _str_func = 'uiFunc_updateModelsFromAutomatic'

    url = self.uiTextField_automaticURL(query=True, text=True)
    
    models = sd.getModelsFromAutomatic(url)

    self.modelMenu.clear()
    for model in models:
        self.modelMenu.append(model['model_name'])

    return models

def uiFunc_getLastSeed(self):
    return -1

def generateImage(prompt_field, negative_prompt_field, steps_field, seed_field, width_field, height_field, model_field, url_field, image_field, arg):
    prompt = mc.textField(prompt_field, query=True, text=True)
    negative_prompt = mc.textField(negative_prompt_field, query=True, text=True)
    steps = mc.intSliderGrp(steps_field, query=True, value=True)
    seed = mc.intSliderGrp(seed_field, query=True, value=True)
    width = mc.intField(width_field, q=True, v=True)
    height = mc.intField(height_field, q=True, v=True)
    model = mc.optionMenu(model_field, query=True, value=True)
    url = mc.textField(url_field, query=True, text=True)
    print(prompt, steps, seed, width, height, model, url, arg)
    image_path = sd.get_image_from_automatic1111(prompt=prompt, negative_prompt=negative_prompt, steps=steps, seed=seed, size=(width, height), model=model, url=url)
    print(image_field, image_path)
    mc.image(image_field, e=True, image=image_path)

def getDepthShader(self):
    _str_func = 'getDepthShader'
    return self.uiTextField_depthShader(q=True, tx=True)

def getAlphaShader(self):
    _str_func = 'getAlphaShader'
    return self.uiTextField_alphaShader(q=True, tx=True)

def getProjectionShader(self):
    _str_func = 'getAlphaShader'
    return self.uiTextField_projectionShader(q=True, tx=True)