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
import base64
import logging
import json
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
import cgm.core.tools.Project as PROJECT

from functools import partial
from cgm.tools import stableDiffusionTools as sd
from cgm.tools import renderTools as rt
from cgm.tools import imageViewer as iv

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='projectDiffusionTool'

_defaultOptions = {
        'automatic_url':'127.0.0.1:7860',
        'prompt':'',
        'negative_prompt':'',
        'seed':-1,
        'width':512,
        'height':512,
        'sampling_steps':5,
        'depth_distance':30.0,
        'control_net_enabled':True,
        'control_net_low_v_ram':False,
        'control_net_preprocessor':'none',
        'control_net_weight':1.0,
        'control_net_guidance_start':0.0,
        'control_net_guidance_end':1.0,
        'sampling_method':'Euler',
        'denoising_strength':.35,
        'use_composite_pass':False,
        'use_alpha_pass':False,
        'mask_blur':4,
}

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE = 650,800
    TOOLNAME = '{0}.ui'.format(__toolname__)
    
    _initialized = False

    def insert_init(self,*args,**kws):
        _str_func = '__init__[{0}]'.format(self.__class__.TOOLNAME)            
        log.info("|{0}| >>...".format(_str_func))        

        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))
        log.info(self.__call__(q=True, title=True))

        self.__version__ = __version__
        self.__toolName__ = self.__class__.WINDOW_NAME	

        self.config = cgmMeta.cgmOptionVar("cgmVar_sdui_config", varType = "string")
        self.lastConfig = cgmMeta.cgmOptionVar("cgmVar_sdui_last_config", varType = "string")
        self.lastInfo = {}

        #self.l_allowedDockAreas = []
        self.WINDOW_TITLE = self.__class__.WINDOW_TITLE
        self.DEFAULT_SIZE = self.__class__.DEFAULT_SIZE
 
    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc = cgmGEN.Callback(self.buildMenu_first))

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        #>>> Reset Options		                     

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Load From Image Node",
                         c = lambda *a:mc.evalDeferred(self.uiFunc_load_settings_from_image,lp=True))

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu )

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reload",
                         c = lambda *a:mc.evalDeferred(self.handleReload,lp=True))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         c = lambda *a:mc.evalDeferred(self.handleReset,lp=True))
    
    def handleReload(self):
        self._initialized = False
        self.reload()

    def handleReset(self):
        self.config.setValue({})
        self.loadOptions()

    def uiFunc_load_settings_from_image(self):
        fileNodes = mc.ls(sl=True, type='file')
        if(len(fileNodes) == 0):
            return
        
        fileNode = fileNodes[0]

        data = sd.load_settings_from_image(fileNode)

        if(data is None):
            return
        
        _options = self.getOptions()

        _options['prompt'] = data['prompt']
        _options['negative_prompt'] = data['negative_prompt']
        _options['seed'] = data['seed']
        _options['width'] = data['width']
        _options['height'] = data['height']
        _options['sampling_steps'] = data['steps']
        _options['control_net_enabled'] = data['extra_generation_params']['ControlNet Enabled'] if 'ControlNet Enabled' in data['extra_generation_params'] else False
        _options['control_net_low_v_ram'] = False
        _options['control_net_preprocessor'] = data['extra_generation_params']['ControlNet Module'] if 'ControlNet Module' in data['extra_generation_params'] else 'none'
        _options['control_net_weight'] = data['extra_generation_params']['ControlNet Weight'] if 'ControlNet Weight' in data['extra_generation_params'] else 1
        _options['control_net_guidance_start'] = data['extra_generation_params']['ControlNet Guidance Start'] if 'ControlNet Guidance Start' in data['extra_generation_params'] else 0
        _options['control_net_guidance_end'] = data['extra_generation_params']['ControlNet Guidance End'] if 'ControlNet Guidance End' in data['extra_generation_params'] else 1
        _options['sampling_method'] = data['sampler_name']

        self.config.setValue(json.dumps(_options))

        self.loadOptions(_options)


    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper'
        #self._d_uiCheckBoxes = {}
    
        #_MainForm = mUI.MelFormLayout(parent,ut='cgmUISubTemplate')
        _MainForm = mUI.MelFormLayout(self,ut='cgmUITemplate')
        _column = self.buildColumn_main(_MainForm,True)

    
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
        
        self._initialized = True

        self.loadOptions()      

    def buildColumn_main(self, parent, asScroll=False):
        _tabs = mc.tabLayout()

        _setup = self.buildColumn_settings(_tabs, asScroll = True)
        _project = self.buildColumn_project(_tabs, asScroll = True)
        _edit = self.buildColumn_edit(_tabs, asScroll = False)

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
                            lambda *a:self.uiFunc_make_projection_camera(),
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
                            lambda *a:self.uiFunc_make_projection_shader(),
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
                            lambda *a:self.uiFunc_make_alpha_shader(),
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
        cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_composite_shader(),annotationText='')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_compositeShader),
                            annotationText='')
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>> Load Composite Shader
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Alpha Matte Shader:',align='right')
        self.uiTextField_alphaMatteShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_alphaMatteShader)
        cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_alphaMatteShader, enforcedType = 'surfaceShader'))
        cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_alpha_matte_shader(),annotationText='')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_alphaMatteShader),
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
        cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_depth_shader(),annotationText='')
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

        self.uiFunc_auto_populate_fields()
        return _inside

    def buildColumn_project(self,parent, asScroll = False):
        """
        Trying to put all this in here so it's insertable in other uis
        
        """   
        if asScroll:
            _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
        else:
            _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        
        #>>> Mode

        mc.setParent(_inside)

        cgmUI.add_Header('Project') 

        #>>> Prompt
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate', height=60)
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Prompt:',align='right')
        self.uiTextField_prompt = mUI.MelScrollField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        wordWrap = True,
                                                        changeCommand = lambda *a:self.saveOptions(),
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
                                                        changeCommand = lambda *a:self.saveOptions(),
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        _row.setStretchWidget(self.uiTextField_negativePrompt)
        mUI.MelSpacer(_row,w = 5)

        _row.layout()

        #>>> Properties
        #_row = mUI.MelHLayout(_inside,expand = False,ut = 'cgmUISubTemplate', padding=5)
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w = 5)
        mUI.MelLabel(_row,l='Seed:',align='right')
        self.uiIF_Seed = mUI.MelIntField(_row,
                                                    minValue = -1,
                                                    value = -1,
                                                    changeCommand = lambda *a:self.saveOptions(),
                                                    annotation = 'Degree of curve to create')	 	    
        
        cgmUI.add_Button(_row,'Last', lambda *a:self.uiFunc_getLastSeed())

        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        mUI.MelLabel(_row,l='Size:',align='right')

        self.uiIF_Width = mUI.MelIntField(_row,
                                                    minValue = 32,
                                                    value = 512,
                                                    changeCommand = lambda *a:self.saveOptions(),
                                                    annotation = 'Degree of curve to create')	 	    

        self.uiIF_Height = mUI.MelIntField(_row,
                                                    minValue = 32,
                                                    value = 512,
                                                    changeCommand = lambda *a:self.saveOptions(),
                                                    annotation = 'Degree of curve to create')	 	    

        _sizeOptions = ['512x512','1024x1024','2048x2048', '640x360', '1280x720','1920x1080']
        self.uiOM_SizeMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
        for option in _sizeOptions:
            self.uiOM_SizeMenu.append(option)

        self.uiOM_SizeMenu(edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_setSize))

        #_row.setStretchWidget( self.sizeMenu )
        mUI.MelSpacer(_row,w = 5)

        _row.layout()

        #>>> Model
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Model:',align='right')
        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        self.uiOM_modelMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate', changeCommand = lambda *a:self.setModelFromUI())
        
        self.uiFunc_updateModelsFromAutomatic()

        cgmUI.add_Button(_row,'Refresh', lambda *a:self.uiFunc_updateModelsFromAutomatic())
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>> Sampling
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Sampling Method:',align='right')
        self.uiOM_samplingMethodMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate', changeCommand = lambda *a:self.saveOptions())

        self.uiFunc_updateSamplersFromAutomatic()

        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Steps:',align='right')
        self.uiIF_samplingSteps = mUI.MelIntField(_row,
                                                    minValue = 1,
                                                    value = 20,
                                                    annotation = 'Sampling Steps', changeCommand=cgmGEN.Callback(self.uiFunc_setSamples,'field'))  
        self.uiSlider_samplingSteps = mUI.MelIntSlider(_row,1,100,20,step = 1)
        self.uiSlider_samplingSteps.setChangeCB(cgmGEN.Callback(self.uiFunc_setSamples,'slider'))

        _row.setStretchWidget( self.uiSlider_samplingSteps )
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        self.uiFunc_setSamples('field')

        #>>> Img2Img

        mc.setParent(_inside)
        cgmUI.add_Header('Img2Img Settings')

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Passes:',align='right')

        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )
        mUI.MelLabel(_row,l='Composite:',align='right')
        self.uiCompositeCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=False, changeCommand = self.uiFunc_setCompositeCB)      

        mUI.MelLabel(_row,l='Alpha Matte:',align='right')
        self.uiAlphaMatteCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=False, en=False, changeCommand = self.uiFunc_setAlphaMatteCB)      

        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        self.compositeLayout = mUI.MelColumnLayout(_inside,useTemplate = 'cgmUISubTemplate', vis=self.uiCompositeCB(q=True, v=True))
        
        #>>>Denoise Slider...
        denoise = .35
        _row = mUI.MelHSingleStretchLayout(self.compositeLayout,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Denoising Strength:',align='right')
        self.uiFF_denoiseStrength = mUI.MelFloatField(_row,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = denoise, changeCommand=cgmGEN.Callback(self.uiFunc_setDenoise, 'field'))  
                
        self.uiSlider_denoiseStrength = mUI.MelFloatSlider(_row,0.0,1.0,denoise,step = .01)
        self.uiSlider_denoiseStrength.setChangeCB(cgmGEN.Callback(self.uiFunc_setDenoise, 'slider'))
        mUI.MelSpacer(_row,w=5)	            
        _row.setStretchWidget(self.uiSlider_denoiseStrength)#Set stretch    

        self.uiFunc_setDenoise('field')
        _row.layout()

        self.alphaMatteLayout = mUI.MelHLayout(self.compositeLayout,expand = True,ut = 'cgmUISubTemplate', vis=self.uiAlphaMatteCB(q=True, v=True))
        
        #>>>Mask Blur Slider...
        maskBlur = 4
        _row = mUI.MelHSingleStretchLayout(self.alphaMatteLayout,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Mask Blur:',align='right')
        self.uiIF_maskBlur = mUI.MelIntField(_row,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                value = maskBlur, changeCommand=cgmGEN.Callback(self.uiFunc_setMaskBlur, 'field'))  
                
        self.uiSlider_maskBlur = mUI.MelIntSlider(_row,0,100,maskBlur,step = 1)
        self.uiSlider_maskBlur.setChangeCB(cgmGEN.Callback(self.uiFunc_setMaskBlur, 'slider'))
        mUI.MelSpacer(_row,w=5)	            
        _row.setStretchWidget(self.uiSlider_maskBlur)#Set stretch    

        self.uiFunc_setMaskBlur('field')
        _row.layout()

        self.alphaMatteLayout.layout()


        #>>> Control Net
        mc.setParent(_inside)
        cgmUI.add_Header('Control Net')

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Options',align='right')

        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )
        mUI.MelLabel(_row,l='Enable:',align='right')
        self.uiControlNetEnabledCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=True, changeCommand = lambda *a:self.saveOptions())      

        mUI.MelLabel(_row,l='Low VRAM:',align='right')
        self.uiControlNetLowVRamCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=True, changeCommand = lambda *a:self.saveOptions())      

        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate')

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Preprocessor:',align='right')

        self.uiOM_ControlNetPreprocessorMenu = mUI.MelOptionMenu(_subRow,useTemplate = 'cgmUITemplate', cc=self.uiFunc_changeControlNetPreProcessor)

        self.uiFunc_updateControlNetPreprocessorsMenu()

        _subRow.setStretchWidget( self.uiOM_ControlNetPreprocessorMenu )

        mUI.MelSpacer(_subRow,w = 5)

        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w = 5)
        mUI.MelLabel(_subRow,l='Model:',align='right')
        self.uiOM_ControlNetModelMenu = mUI.MelOptionMenu(_subRow,useTemplate = 'cgmUITemplate', changeCommand = lambda *a:self.saveOptions())
        
        self.uiFunc_updateControlNetModelsFromAutomatic()
        
        _subRow.setStretchWidget( self.uiOM_ControlNetModelMenu )

        mUI.MelSpacer(_subRow,w = 5)
        _subRow.layout()

        _row.layout()

        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        
        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Weight:',align='right')
        self.uiFF_controlNetWeight = mUI.MelFloatField(_subRow,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = 1.0)  
                
        self.uiSlider_controlNetWeight = mUI.MelFloatSlider(_subRow,0.0,1.0,1.0,step = .1)

        self.uiSlider_controlNetWeight(e=True, dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetWeight, 'slider'))
        self.uiFF_controlNetWeight.setChangeCB(cgmGEN.Callback(self.uiFunc_setControlNetWeight, 'field'))
        self.uiFunc_setControlNetWeight('field')

        mUI.MelSpacer(_subRow,w = 5)

        _subRow.setStretchWidget( self.uiSlider_controlNetWeight )
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Guidance Start (T):',align='right')
        self.uiFF_controlNetGuidanceStart = mUI.MelFloatField(_subRow,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = 0.0)  
      
        self.uiSlider_controlNetGuidanceStart = mUI.MelFloatSlider(_subRow,0.0,1.0,1.0,step = .1)

        self.uiSlider_controlNetGuidanceStart(e=True, dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetGuidanceStart, 'slider'))
        self.uiFF_controlNetGuidanceStart.setChangeCB(cgmGEN.Callback(self.uiFunc_setControlNetGuidanceStart, 'field'))
        self.uiFunc_setControlNetGuidanceStart('field')

        mUI.MelSpacer(_subRow,w = 5)
        _subRow.setStretchWidget( self.uiSlider_controlNetGuidanceStart )
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Guidance End (T):',align='right')
        self.uiFF_controlNetGuidanceEnd = mUI.MelFloatField(_subRow,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = 1.0)  
                
        self.uiSlider_controlNetGuidanceEnd = mUI.MelFloatSlider(_subRow,0.0,1.0,1.0,step = .1)

        self.uiSlider_controlNetGuidanceEnd(e=True, dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetGuidanceEnd, 'slider'))
        self.uiFF_controlNetGuidanceEnd.setChangeCB(cgmGEN.Callback(self.uiFunc_setControlNetGuidanceEnd, 'field'))
        self.uiFunc_setControlNetGuidanceEnd('field')

        mUI.MelSpacer(_subRow,w = 5)

        _subRow.setStretchWidget( self.uiSlider_controlNetGuidanceEnd )
        _subRow.layout()

        _row.layout()

        #>>> Materials
        mc.setParent(_inside)
        cgmUI.add_Header('Materials')
        
        #>>> Shader Assignment
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Assign Material:',align='right')
        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )
        cgmUI.add_Button(_row,'Depth', lambda *a:self.uiFunc_assign_material(self.uiTextField_depthShader))
        cgmUI.add_Button(_row,'Projection', lambda *a:self.uiFunc_assign_material(self.uiTextField_projectionShader))
        cgmUI.add_Button(_row,'Alpha', lambda *a:self.uiFunc_assign_material(self.uiTextField_alphaShader))
        cgmUI.add_Button(_row,'Composite', lambda *a:self.uiFunc_assign_material(self.uiTextField_compositeShader))
        cgmUI.add_Button(_row,'Alpha Matte', lambda *a:self.uiFunc_assign_material(self.uiTextField_alphaMatteShader))
        cgmUI.add_Button(_row,'Merged', lambda *a:self.uiFunc_assign_material(self.uiTextField_compositeShader))
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>>Depth Slider...
        depth = 50.0
        depthShader = self.getDepthShader()
        if(depthShader):
            depth = mc.getAttr('%s.distance' % depthShader)

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Depth Distance:',align='right')
        self.uiFF_depthDistance = mUI.MelFloatField(_row,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = depth, changeCommand=cgmGEN.Callback(self.uiFunc_setDepth, 'field'))  
                
        self.uiSlider_depthDistance = mUI.MelFloatSlider(_row,1.0,100.0,depth,step = 1)
        self.uiSlider_depthDistance.setChangeCB(cgmGEN.Callback(self.uiFunc_setDepth, 'slider'))
        mUI.MelSpacer(_row,w=5)	            
        _row.setStretchWidget(self.uiSlider_depthDistance)#Set stretch    

        self.uiFunc_setDepth('field')
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Tools:',align='right')
        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        self.renderBtn = cgmUI.add_Button(_row,'Test Render',
        cgmGEN.Callback(self.uiFunc_renderImage),                         
        'Render')
        self.viewImageBtn = cgmUI.add_Button(_row,'View Image',
        cgmGEN.Callback(self.uiFunc_viewImage),                         
        'View Image')
        mUI.MelSpacer(_row,w=5)	            
        _row.layout()



        # Generate Button
        #
        _row = mUI.MelHLayout(_inside,ut='cgmUISubTemplate',padding = 10)
        
        self.generateBtn = cgmUI.add_Button(_row,'Generate',
            cgmGEN.Callback(self.uiFunc_generateImage),                         
            'Generate',h=50)

        self.bakeProjectionBtn = cgmUI.add_Button(_row,'Bake Projection',
            cgmGEN.Callback(self.uiFunc_bakeProjection),                         
            'Bake Projection',h=50)

        _row.layout()    
        #
        # End Generate Button

        return _inside

    def uiFunc_setCompositeCB(self, *a):
        _str_func = 'uiFunc_setCompositeCB'
        print(_str_func, a)

        val = a[0]

        self.compositeLayout(e=True, vis=val)
        self.uiAlphaMatteCB(e=True, en=val)

        self.saveOptions()

    def uiFunc_setAlphaMatteCB(self, *a):
        _str_func = 'uiFunc_setAlphaMatteCB'
        print(_str_func, a)

        val = a[0]

        self.alphaMatteLayout(e=True, vis=val)

        self.saveOptions()

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
            if(mc.getAttr(shader) == 'sd_alphaMatte'):
                self.uiTextField_alphaMatteShader(edit=True, text=shader.split('.')[0])
                continue
        return

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
        
        print("Assigning {0} to {1}".format(_material, _mesh))
        rt.assignMaterial(_mesh, _sg)

    def uiFunc_setSize(self):
        _str_func = 'uiFunc_setSize'
        size = self.uiOM_SizeMenu(query=True, value=True)
        width, height = [int(x) for x in size.split('x')]
        self.uiIF_Width(edit=True, value=width)
        self.uiIF_Height(edit=True, value=height)
        self.saveOptions()

    def uiFunc_renderImage(self):
        outputImage = rt.renderMaterialPass(None, self.uiTextField_baseObject(query=True, text=True), asJpg = False, camera = self.uiTextField_projectionCam(q=True, text=True)  )
        iv.ui([outputImage], {'outputImage':outputImage})

    def uiFunc_viewImage(self):
        _str_func = 'uiFunc_viewImage'

        files = mc.ls(sl=True, type='file')
        imagePaths = []
        data = {}
        for file in files:
            path =mc.getAttr(file+'.fileTextureName')
            imagePaths.append(path)
            data[file] = path
        
        if imagePaths:
            iv.ui(imagePaths, data)
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))

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

        depthShader = self.uiTextField_depthShader(query=True, text=True)
        if mc.objExists(depthShader):
            ramp = mc.listConnections(depthShader + '.outColor', type='ramp')
            if(ramp):
                mc.connectAttr(ramp[0] + '.outColorG', shader + '.outColorG', force=True)

        self.uiTextField_alphaShader(edit=True, text=shader)

    def uiFunc_make_composite_shader(self):
        _str_func = 'uiFunc_make_composite_shader'

        shader, sg = sd.makeCompositeShader()
        self.uiTextField_compositeShader(edit=True, text=shader)

    def uiFunc_make_alpha_matte_shader(self):
        _str_func = 'uiFunc_make_alpha_matte_shader'

        shader, sg = sd.makeAlphaMatteShader()

        self.uiTextField_alphaMatteShader(edit=True, text=shader)

    def uiFunc_make_depth_shader(self):
        _str_func = 'uiFunc_make_depth_shader'

        shader, sg = sd.makeDepthShader()
        self.uiTextField_depthShader(edit=True, text=shader)

        alphaShader = self.uiTextField_alphaShader(query=True, text=True)
        if mc.objExists(alphaShader):
            ramp = mc.listConnections(shader + '.outColor', type='ramp')
            if(ramp):
                mc.connectAttr(ramp[0] + '.outColorG', alphaShader + '.outColorG', force=True)

        mc.setAttr(shader + '.distance', self.uiFF_depthDistance(query=True, value=True))

    def uiFunc_generateImage(self):
        _str_func = 'uiFunc_generateImage'

        depthMat = self.uiTextField_depthShader(q=True, text=True)
        mesh = self.uiTextField_baseObject(q=True, text=True)
        camera = self.uiTextField_projectionCam(q=True, text=True)

        if(not mc.objExists(depthMat)):
            log.warning("|{0}| >> No depth shader loaded.".format(_str_func))
            
        if(not mc.objExists(mesh)):
            log.warning("|{0}| >> No mesh loaded.".format(_str_func))
            

        bgColor = self.generateBtn(q=True, bgc=True)
        origText = self.generateBtn(q=True, label=True)
        self.generateBtn(edit=True, enable=False)
        self.generateBtn(edit=True, label='Generating...')
        self.generateBtn(edit=True, bgc=(1, 0.5, 0.5))

        mc.refresh()

        _options = self.getOptions()

        output_path = getImagePath()

        if mc.objExists(depthMat) and mc.objExists(mesh):
            depth_path = rt.renderMaterialPass(depthMat, mesh, asJpg=True, camera=camera)
            
            with open(depth_path, "rb") as f:
                # Read the image data
                image_data = f.read()
                
                # Encode the image data as base64
                image_base64 = base64.b64encode(image_data)
                
                # Convert the base64 bytes to string
                depth_string = image_base64.decode("utf-8")

                f.close()

            _options['control_net_image'] = depth_string
        
        if(_options['use_composite_pass']):
            composite_path = rt.renderMaterialPass(self.uiTextField_compositeShader(q=True, text=True), mesh, asJpg=False, camera=camera)

            with open(composite_path, "rb") as f:
                # Read the image data
                image_data = f.read()
                
                # Encode the image data as base64
                image_base64 = base64.b64encode(image_data)
                
                # Convert the base64 bytes to string
                composite_string = image_base64.decode("utf-8")

                _options['init_images'] = [composite_string]

                f.close()
            
            if(_options['use_alpha_pass']):
                alpha_path = rt.renderMaterialPass(self.uiTextField_alphaMatteShader(q=True, text=True), mesh, asJpg=True, camera=camera)

                with open(alpha_path, "rb") as f:
                    # Read the image data
                    image_data = f.read()
                    
                    # Encode the image data as base64
                    image_base64 = base64.b64encode(image_data)
                    
                    # Convert the base64 bytes to string
                    alpha_string = image_base64.decode("utf-8")

                    _options['mask'] = alpha_string
                    _options['mask_blur'] = self.uiIF_maskBlur(query=True, value=True)
                    _options['inpainting_mask_invert'] = 1

                    f.close()

        # standardize the output path
        _options['output_path'] = output_path

        imagePaths, info = sd.getImageFromAutomatic1111(_options)

        camera = self.uiTextField_projectionCam(query=True, text=True)
        cameraTransform = mc.listRelatives(camera, parent=True)[0]
        info['camera_info'] = {'position':mc.xform(cameraTransform, q=True, ws=True, t=True),
            'rotation' : mc.xform(cameraTransform, q=True, ws=True, ro=True),
            'fov' : mc.getAttr(camera + '.focalLength')}

        print("Generated: ", imagePaths, info)

        if(imagePaths):
            displayImage(imagePaths, info, [{'function':self.assignImageToProjection, 'label':'Assign To Projection'}])
        self.lastInfo = info

        self.generateBtn(edit=True, enable=True)
        self.generateBtn(edit=True, label=origText)
        self.generateBtn(edit=True, bgc=bgColor)


    def assignImageToProjection(self, imagePath, info):
        # assign projection shader
        
        self.uiFunc_assign_material(self.uiTextField_projectionShader)
        projectionShader = self.uiTextField_projectionShader(query=True, text=True)
        mesh = self.uiTextField_baseObject(query=True, text=True)
        rt.assignImageToProjectionShader(projectionShader, imagePath, info)        

    def uiFunc_bakeProjection(self):
        #self.assignImageToProjection(imagePath, info)
        mesh = self.uiTextField_baseObject(query=True, text=True)
        projectionShader = self.uiTextField_projectionShader(query=True, text=True)
        alphaShader = self.uiTextField_alphaShader(query=True, text=True)

        bakedImage = rt.bakeProjection(projectionShader, mesh)
        bakedAlpha = rt.bakeProjection(alphaShader, mesh)

        compositeShader = self.uiTextField_compositeShader(query=True, text=True)
        alphaMatteShader = self.uiTextField_alphaMatteShader(query=True, text=True)

        rt.addImageToCompositeShader(compositeShader, bakedImage, bakedAlpha)
        rt.updateAlphaMatteShader(alphaMatteShader, compositeShader)

        # assign composite shader
        self.uiFunc_assign_material(self.uiTextField_compositeShader)

    def uiFunc_setDepth(self, source):
        shader = self.getDepthShader()

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
        
        self.saveOptions()

    def uiFunc_setSamples(self, source):

        uiFunc_setFieldSlider(self.uiIF_samplingSteps, self.uiSlider_samplingSteps, source, 100)
        
        self.saveOptions()

    def uiFunc_setDenoise(self, source):
        uiFunc_setFieldSlider(self.uiFF_denoiseStrength, self.uiSlider_denoiseStrength, source, 1.0, .01)
        
        self.saveOptions()

    def uiFunc_setMaskBlur(self, source):
        uiFunc_setFieldSlider(self.uiIF_maskBlur, self.uiSlider_maskBlur, source, 100, 1)
        
        self.saveOptions()

    def uiFunc_updateModelsFromAutomatic(self):
        _str_func = 'uiFunc_updateModelsFromAutomatic'

        url = self.uiTextField_automaticURL(query=True, text=True)
        
        self.models = sd.getModelsFromAutomatic(url)

        self.uiOM_modelMenu.clear()
        for model in self.models:
            # if model is a string, continue
            self.uiOM_modelMenu.append(model['model_name'])

        return self.models

    def getModelFromName(self, name):
        _str_func = 'uiFunc_getModelFromName'

        for model in self.models:
            if model['model_name'] == name:
                return model

        return None
    
    def getModelFromUI(self):
        _str_func = 'uiFunc_getModelFromUI'

        name = self.uiOM_modelMenu(query=True, value=True)
        return self.getModelFromName(name)

    def setModelFromUI(self):
        _str_func = 'uiFunc_setModelFromUI'
        newModel = self.getModelFromUI()

        bgColor = self.generateBtn(q=True, bgc=True)
        origText = self.generateBtn(q=True, label=True)
        self.generateBtn(edit=True, enable=False)
        self.generateBtn(edit=True, label='Setting New Model...')
        self.generateBtn(edit=True, bgc=(1, 0.5, 0.5))

        mc.refresh()

        sd.setModel(newModel)

        self.generateBtn(edit=True, enable=True)
        self.generateBtn(edit=True, label=origText)
        self.generateBtn(edit=True, bgc=bgColor)
    
    def uiFunc_updateSamplersFromAutomatic(self):
        _str_func = 'uiFunc_updateSamplersFromAutomatic'

        url = self.uiTextField_automaticURL(query=True, text=True)
        
        _samplers = sd.getSamplersFromAutomatic1111()

        self.uiOM_samplingMethodMenu.clear()
        for sampler in _samplers:
            # if model is a string, continue
            self.uiOM_samplingMethodMenu.append(sampler['name'])

        return _samplers

    def uiFunc_updateControlNetPreprocessorsMenu(self):
        _str_func = 'uiFunc_updateControlNetPreprocessorsMenu'

        _preprocessors = sd.getControlNetPreprocessorsFromAutomatic1111()

        self.uiOM_ControlNetPreprocessorMenu.clear()
        for _preprocessor in _preprocessors:
            # if model is a string, continue
            self.uiOM_ControlNetPreprocessorMenu.append(_preprocessor)

        return _preprocessors

    def uiFunc_changeControlNetPreProcessor(self, arg):
        self.uiFunc_updateControlNetModelsFromAutomatic()

        self.saveOptions()

    def uiFunc_updateControlNetModelsFromAutomatic(self):
        _str_func = 'uiFunc_updateControlNetModelsFromAutomatic'

        preprocessor = self.uiOM_ControlNetPreprocessorMenu(query=True, value=True)

        filter = preprocessor
        if(preprocessor == 'none'):
            filter = ''
        if(preprocessor == 'segmentation'):
            filter = 'seg'
        
        url = self.uiTextField_automaticURL(query=True, text=True)

        _models = sd.getControlNetModelsFromAutomatic1111(url)
        #print(_models)
        self.uiOM_ControlNetModelMenu.clear()
        for _model in _models['model_list']:
            # if model is a string, continue
            if(filter not in _model):
                continue
            self.uiOM_ControlNetModelMenu.append(_model)

        return _models['model_list']

    def uiFunc_setControlNetWeight(self, source):
        uiFunc_setFieldSlider(self.uiFF_controlNetWeight,self.uiSlider_controlNetWeight, source, 1.0, .1)
        self.saveOptions()

    def uiFunc_setControlNetGuidanceStart(self, source):
        uiFunc_setFieldSlider(self.uiFF_controlNetGuidanceStart,self.uiSlider_controlNetGuidanceStart, source, 1.0, .1)
        self.saveOptions()

    def uiFunc_setControlNetGuidanceEnd(self, source):
        uiFunc_setFieldSlider(self.uiFF_controlNetGuidanceEnd,self.uiSlider_controlNetGuidanceEnd, source, 1.0, .1)
        self.saveOptions()

    def uiFunc_getLastSeed(self):
        lastSeed = -1
        if('seed' in self.lastInfo.keys()):
            lastSeed = self.lastInfo['seed']
        
        #set seed ui element to last seed
        self.uiIF_Seed.setValue(lastSeed)
        
        return lastSeed

    def getDepthShader(self):
        _str_func = 'getDepthShader'
        return self.uiTextField_depthShader(q=True, tx=True)

    def getAlphaShader(self):
        _str_func = 'getAlphaShader'
        return self.uiTextField_alphaShader(q=True, tx=True)

    def getProjectionShader(self):
        _str_func = 'getProjectionShader'
        return self.uiTextField_projectionShader(q=True, tx=True)
    
    def getOptions(self):
        _str_func = 'saveOptions'
        
        _options = {}
        _options['automatic_url'] = self.uiTextField_automaticURL(query=True, text=True)
        _options['prompt'] = self.uiTextField_prompt(query=True, text=True)
        _options['negative_prompt'] = self.uiTextField_negativePrompt(query=True, text=True)
        _options['seed'] = self.uiIF_Seed(query=True, value=True)
        _options['width'] = self.uiIF_Width(query=True, v=True)
        _options['height'] = self.uiIF_Height(query=True, v=True)
        _options['sampling_method'] = self.uiOM_samplingMethodMenu(query=True, value=True)
        _options['sampling_steps'] = self.uiIF_samplingSteps.getValue()
        _options['depth_distance'] = self.uiFF_depthDistance.getValue()
        _options['control_net_enabled'] = self.uiControlNetEnabledCB.getValue()
        _options['control_net_low_v_ram'] = self.uiControlNetLowVRamCB.getValue()
        _options['control_net_preprocessor'] = self.uiOM_ControlNetPreprocessorMenu(query=True, value=True)
        _options['control_net_model'] = self.uiOM_ControlNetModelMenu(query=True, value=True)
        _options['control_net_weight'] = self.uiFF_controlNetWeight.getValue()
        _options['control_net_guidance_start'] = self.uiFF_controlNetGuidanceStart.getValue()
        _options['control_net_guidance_end'] = self.uiFF_controlNetGuidanceEnd.getValue()
        _options['denoising_strength'] = self.uiFF_denoiseStrength.getValue()
        _options['use_composite_pass'] = self.uiCompositeCB.getValue()
        _options['use_alpha_pass'] = self.uiAlphaMatteCB.getValue()
        _options['mask_blur'] = self.uiIF_maskBlur.getValue()

        return _options

    def saveOptions(self):
        _str_func = 'saveOptions'
        
        if not self._initialized:
            return

        _options = {}

        try:
            _options = self.getOptions()
        except:
            log.error("|{0}| >> Error: Failed to save options".format(_str_func))
            return
        
        self.config.setValue(json.dumps(_options))

        #print("saving", _options)
    
    def loadOptions(self, options=None):
        _str_func = 'loadOptions'

        if not self._initialized:
            return

        _options = {}
        if(options):
            _options = options
        else:           
            _options = json.loads(self.config.getValue()) if self.config.getValue() else _defaultOptions

        # load model from automatic
        sdModels = sd.getModelsFromAutomatic1111(_options['automatic_url'])
        sdOptions = sd.getOptionsFromAutomatic(_options['automatic_url'])

        for model in sdModels:
            if(model['title'] == sdOptions['sd_model_checkpoint']):
                self.uiOM_modelMenu(edit=True, value=model['model_name'])
                break

        # iterate through options dict and set default from self._defaultOptions if not found
        for key in _defaultOptions:
            if key not in _options:
                _options[key] = _defaultOptions[key]

        self.uiTextField_automaticURL(edit=True, text=_options['automatic_url'])
        self.uiTextField_prompt(edit=True, text=_options['prompt'])
        self.uiTextField_negativePrompt(edit=True, text=_options['negative_prompt'])
        self.uiIF_Seed(edit=True, value=_options['seed'])
        self.uiIF_Width(edit=True, v=_options['width'])
        self.uiIF_Height(edit=True, v=_options['height'])           
        if 'sampling_method' in _options:
            self.uiOM_samplingMethodMenu(edit=True, value=_options['sampling_method'])
        self.uiIF_samplingSteps.setValue(_options['sampling_steps'])
        self.uiFF_depthDistance.setValue(_options['depth_distance'])
        self.uiControlNetEnabledCB.setValue(_options['control_net_enabled'])
        self.uiControlNetLowVRamCB.setValue(_options['control_net_low_v_ram'])
        self.uiOM_ControlNetPreprocessorMenu(edit=True, value=_options['control_net_preprocessor'])
        if 'control_net_model' in _options:
            self.uiOM_ControlNetModelMenu(edit=True, value=_options['control_net_model'])
        self.uiFF_controlNetWeight.setValue(_options['control_net_weight'])
        self.uiFF_controlNetGuidanceStart.setValue(_options['control_net_guidance_start'])
        self.uiFF_controlNetGuidanceEnd.setValue(_options['control_net_guidance_end'])
        self.uiFF_denoiseStrength.setValue(_options['denoising_strength'])
        self.uiCompositeCB.setValue(_options['use_composite_pass'])
        self.uiAlphaMatteCB.setValue(_options['use_alpha_pass'])

        self.uiIF_maskBlur.setValue(_options['mask_blur'])
        self.uiFunc_setCompositeCB(_options['use_composite_pass'])
        self.uiFunc_setAlphaMatteCB(_options['use_alpha_pass'])

        #print("loading", _options)
    
    def setProjectionImage(self, image):
        _str_func = 'setProjectionImage'
        self.uiImageField_projectionImage(edit=True, image=image)

def getImagePath():
    var_lastProject = cgmMeta.cgmOptionVar("cgmVar_projectCurrent", varType = "string")
    var_categoryStore = cgmMeta.cgmOptionVar("cgmVar_sceneUI_category", defaultValue = 0)
    var_lastAsset = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_asset", varType = "string")

    mDat = PROJECT.data(filepath=var_lastProject.getValue())
    d_userPaths = mDat.userPaths_get()
    l_categoriesBase = mDat.assetTypes_get() if mDat.assetTypes_get() else mDat.d_structure.get('assetTypes', [])

    s_imagePath = os.path.join(d_userPaths['content'],l_categoriesBase[var_categoryStore.getValue()], var_lastAsset.getValue(), 'images') 
    s_imagePath = os.path.normpath(s_imagePath)

    return s_imagePath

def uiFunc_setFieldSlider(field, slider, source, maxVal=100, step=1):

    _value = 0

    if source == 'slider':
        _value = slider(query=True, value=True)
        field.setValue(_value)
    elif source == 'field':
        _value = field.getValue()
        slider(edit=True, max=max(maxVal, _value))
        slider(edit=True, value=_value, step=step)


def displayImage(imagePaths, data = {}, callbackData = []):
    print("Displaying images: ", imagePaths)
    iv.ui( imagePaths, data, callbackData )

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