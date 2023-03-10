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
    DEFAULT_SIZE = 425,350
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
        

def buildColumn_main(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    
    cgmUI.add_Header('Setup')

    #>>> Mesh Load
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Mesh:',align='right')
    self.uiTextField_baseObject = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_baseObject)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_baseObject, enforcedType = 'mesh'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select', 
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_baseObject),
                        annotationText='')               
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)            
    self.uiRow_baseLoad.layout()

    #>>> Load Projection Camera
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Projection Cam:',align='right')
    self.uiTextField_projectionCam = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_projectionCam)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_projectionCam, enforcedType = 'camera'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Make',
                        lambda *a:uiFunc_make_projection_camera(self),
                        annotationText='Make a projection camera')
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_projectionCam),
                        annotationText='')
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.layout()


    #>>> Load Projection Shader
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Projection Shader:',align='right')
    self.uiTextField_projectionShader = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_projectionShader)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_projectionShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Make', 
                        lambda *a:uiFunc_make_projection_shader(self),
                        annotationText='Make a projection shader')
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_projectionShader),
                        annotationText='')
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.layout()

    #>>> Load Alpha Shader
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Alpha Shader:',align='right')
    self.uiTextField_alphaShader = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_alphaShader)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_alphaShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Make',
                        lambda *a:uiFunc_make_alpha_shader(self),
                        annotationText='')
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_alphaShader),
                        annotationText='')
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.layout()

    #>>> Load Composite Shader
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Composite Shader:',align='right')
    self.uiTextField_compositeShader = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_compositeShader)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_compositeShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Make', lambda *a:uiFunc_make_composite_shader(self),annotationText='')
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_compositeShader),
                        annotationText='')
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.layout()

    #>>> Load Depth Shader
    self.uiRow_baseLoad = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(self.uiRow_baseLoad,w=5)
    mUI.MelLabel(self.uiRow_baseLoad,l='Depth Shader:',align='right')
    self.uiTextField_depthShader = mUI.MelTextField(self.uiRow_baseLoad,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    editable=False,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.setStretchWidget(self.uiTextField_depthShader)
    cgmUI.add_Button(self.uiRow_baseLoad,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_depthShader, enforcedType = 'surfaceShader'))
    cgmUI.add_Button(self.uiRow_baseLoad, 'Make', lambda *a:uiFunc_make_depth_shader(self),annotationText='')
    cgmUI.add_Button(self.uiRow_baseLoad, 'Select',
                        lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_depthShader),
                        annotationText='')
    mUI.MelSpacer(self.uiRow_baseLoad,w = 5)
    self.uiRow_baseLoad.layout()

    uiFunc_auto_populate_fields(self)
    return _inside

def uiFunc_auto_populate_fields(self):
    return

def uiFunc_clear_text_field(element):
    _str_func = 'uiFunc_clear_loaded'  
    element(edit=True, text='')   

def uiFunc_set_text_field(element, text):
    _str_func = 'uiFunc_load_text_field_with_selected'  
    element(edit=True, text=text)

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
    
    sg = mc.listConnections(_material, type='shadingEngine')
    if sg:
        sg = sg[0]

    rt.assignMaterial(sg, _material)  

def uiFunc_make_projection_camera(self):
    cam, shape = rt.createProjectionCamera()
    self.uiTextField_projectionCam(edit=True, text=shape)

def uiFunc_make_projection_shader(self):
    _str_func = 'uiFunc_make_projection_shader'
    _camera = self.uiTextField_projectionCam(query=True, text=True)

    if not mc.objExists(_camera):
        log.warning("|{0}| >> No camera loaded.".format(_str_func))
        return
    
    shader, sg = rt.createProjectionShader(_camera)
    self.uiTextField_projectionShader(edit=True, text=shader)

def uiFunc_make_alpha_shader(self):
    _str_func = 'uiFunc_make_alpha_shader'
    _camera = self.uiTextField_projectionCam(query=True, text=True)

    if not mc.objExists(_camera):
        log.warning("|{0}| >> No camera loaded.".format(_str_func))
        return
    
    shader, sg = rt.createProjectionShader(_camera)
    self.uiTextField_alphaShader(edit=True, text=shader)

def uiFunc_make_composite_shader(self):
    pass

def uiFunc_make_depth_shader(self):
    pass

def generate_image(prompt_field, negative_prompt_field, steps_field, seed_field, width_field, height_field, model_field, url_field, image_field, arg):
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

def open_window():
    # Create a window
    window = mc.window(title="Generate Image", widthHeight=(400, 200))
    
    # Add a row column layout to the window and store it in a variable
    col = mc.columnLayout(adjustableColumn=True)

    # Add a collapsible layout for the parameters
    params_layout = mc.frameLayout(label="Parameters", collapsable=True, collapse=False, marginHeight=5, marginWidth=5)

    # Add a row column layout to the collapsible layout for the parameters
    paramsCL = mc.columnLayout(adjustableColumn=True)
    #mc.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, 100), (2, 300)], adjustableColumn=2)
    # Add text fields for the shaders

    mc.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 100), (2, 300), (3,100)], adjustableColumn=2)

    mc.text(label="Mesh:")
    projection_camera_field = mc.textField(text="")
    mc.button(label="Set")

    mc.text(label="Projection Camera:")
    projection_camera_field = mc.textField(text="")
    mc.button(label="Set")

    mc.setParent('..')

    mc.rowColumnLayout(numberOfColumns=4, columnWidth=[(1, 100), (2, 300), (3,50), (4,50)], adjustableColumn=2)

    mc.text(label="Projection Shader:")
    projection_shader_field = mc.textField(text="")
    mc.button(label="Set")
    mc.button(label="Assign")

    mc.text(label="Depth Shader:")
    depth_shader_field = mc.textField(text="")
    mc.button(label="Set")
    mc.button(label="Assign")

    mc.text(label="Alpha Shader:")
    alpha_shader_field = mc.textField(text="")
    mc.button(label="Set")
    mc.button(label="Assign")

    mc.text(label="Composite Shader:")
    composite_shader_field = mc.textField(text="")
    mc.button(label="Set")
    mc.button(label="Assign")

    mc.setParent(col)

    layout = mc.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, 100), (2, 300)], adjustableColumn=2)
    
    # Add text fields for each parameter
    mc.text(label="Prompt:")
    prompt_field = mc.textField(text="maltese puppy")
    mc.text(label="Negative Prompt:")
    negative_prompt_field = mc.textField(text="")
    mc.text(label="Steps:")
    steps_field = mc.intSliderGrp(minValue=1, maxValue=20, value=5, field=True)
    mc.text(label="Seed:")
    seed_field = mc.intSliderGrp(minValue=-1, maxValue=100, value=-1, field=True)
    mc.setParent('..')
    mc.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 100), (2, 100), (3, 100)], adjustableColumn=1)
    mc.text(label="Size:")
    width_field = mc.intField(value=512)
    height_field = mc.intField(value=512)
    mc.setParent('..')
    mc.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 100), (2, 300)], adjustableColumn=2)
    mc.text(label="Model:")
    model_field = mc.optionMenu()
    for model in get_models_from_automatic1111():
        mc.menuItem(label=model, parent=model_field)
    mc.button(label="Refresh Models", command=partial(refresh_models, model_field))

    mc.setParent(col)

    mc.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, 100), (2, 300)], adjustableColumn=2)
    mc.text(label="URL:")
    url_field = mc.textField(text="127.0.0.1:7860")
    
    mc.setParent(col)
    # Add a button that calls the generate_image function with the input parameters
    genBtn = mc.button(label="Generate")
    
    image_field = mc.image(w=512, h=512)
    
    mc.button(genBtn, e=True, command=partial(generate_image,
        prompt_field,
        steps_field,
        seed_field,
        width_field,
        height_field,
        model_field,
        url_field,
        image_field
    ))
    
    mc.showWindow(window)

def get_models_from_automatic1111():
    # Your code to retrieve the available models goes here
    # Replace this placeholder with your actual code
    models = ['deliberate_v2', 'random_v1', 'autoencoder_v3']
    return models

def refresh_models(model_field):
    # Remove all existing menu items
    menu_items = mc.optionMenu(model_field, query=True, itemListLong=True)
    if menu_items is not None:
        for item in menu_items:
            mc.deleteUI(item)
    
    # Add the new menu items
    models = get_models_from_automatic1111()
    for model in models:
        mc.menuItem(parent=model_field, label=model)