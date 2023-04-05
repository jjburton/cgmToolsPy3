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
import os
import base64
import logging
import json
from PIL import Image
from io import BytesIO
import tempfile

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
mUI = cgmUI.mUI

from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
import cgm.core.tools.Project as PROJECT

from functools import partial
from cgm.tools import stableDiffusionTools as sd
from cgm.tools import renderTools as rt
from cgm.tools import imageViewer as iv

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='GrAIBox'

_defaultOptions = {
        'automatic_url':'127.0.0.1:7860',
        'prompt':'',
        'negative_prompt':'',
        'seed':-1,
        'width':512,
        'height':512,
        'sampling_steps':5,
        'min_depth_distance':0.0,
        'max_depth_distance':30.0,
        'control_net_enabled':True,
        'control_net_low_v_ram':False,
        'control_net_preprocessor':'none',
        'control_net_weight':1.0,
        'control_net_guidance_start':0.0,
        'control_net_guidance_end':1.0,
        'sampling_method':'Euler',
        'denoising_strength':.35,
        #'use_composite_pass':False,
        'img2img_pass':'none',
        'img2img_custom_image':'',
        'img2img_render_layer':'defaultRenderLayer',
        'use_alpha_pass':False,
        'mask_blur':4,
        'batch_count':1,
        'batch_size':1,
        'cfg_scale':7
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

    @property
    def resolution(self):
        return (self.uiIF_Width.getValue(), self.uiIF_Height.getValue())

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
        self.editTabContent = None

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
        self.uiTabLayout = mc.tabLayout()

        self.setupColumn = self.buildColumn_settings(self.uiTabLayout, asScroll = True)
        self.projectColumn = self.buildColumn_project(self.uiTabLayout, asScroll = True)
        self.editColumn = self.buildColumn_edit(self.uiTabLayout, asScroll = True)

        mc.tabLayout(self.uiTabLayout, edit=True, tabLabel=((self.setupColumn, 'Setup'), (self.projectColumn, 'Project'), (self.editColumn, 'Edit')), cc=lambda *a: self.uiFunc_handleTabChange(*a))

        return self.uiTabLayout

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

        #>>> Load XYZ Shader
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='XYZ Shader:',align='right')
        self.uiTextField_xyzShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_xyzShader)
        cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_xyzShader, enforcedType = 'surfaceShader'))
        cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_xyz_shader(),annotationText='')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_xyzShader),
                            annotationText='')
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>> Load Merged Shader
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Merged Shader:',align='right')
        self.uiTextField_mergedShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_mergedShader)
        cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_mergedShader, enforcedType = 'surfaceShader'))
        cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_merged_shader(),annotationText='')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_mergedShader),
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
                                                        cc = lambda *a:self.uiFunc_changeAutomatic1111Url(),
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
                                                        annotation = "Prompt")
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
                                                        annotation = "Negative prompt")
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
                                        annotation = 'Random seed to use for this project')	 	    

        cgmUI.add_Button(_row,'Last', lambda *a:self.uiFunc_getLastSeed())

        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        mUI.MelLabel(_row,l='Size:',align='right')

        self.uiIF_Width = mUI.MelIntField(_row,
                                            minValue = 32,
                                            value = 512,
                                            changeCommand = cgmGEN.Callback(self.uiFunc_setSize, 'field'),
                                            annotation = 'Width of image to create')	 	    

        self.uiIF_Height = mUI.MelIntField(_row,
                                            minValue = 32,
                                            value = 512,
                                            changeCommand = cgmGEN.Callback(self.uiFunc_setSize, 'field'),
                                            annotation = 'Height of image to create')	 	    

        _sizeOptions = ['512x512','1024x1024','2048x2048', '768x512', '640x360', '1280x720','1920x1080', '720x1280', '512x768', '512x1024']
        self.uiOM_SizeMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
        for option in _sizeOptions:
            self.uiOM_SizeMenu.append(option)

        self.uiOM_SizeMenu(edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_setSize, 'menu'))

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


        #>>> Batches
        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate')

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Batch Count:',align='right')
        self.uiIF_batchCount = mUI.MelIntField(_subRow,
                                                    minValue = 1,
                                                    value = 1,
                                                    annotation = 'Sampling Steps', changeCommand=cgmGEN.Callback(self.uiFunc_setBatchCount,'field'))  
        self.uiSlider_batchCount = mUI.MelIntSlider(_subRow,1,10,1,step = 1)
        self.uiSlider_batchCount.setChangeCB(cgmGEN.Callback(self.uiFunc_setBatchCount,'slider'))

        _subRow.setStretchWidget( self.uiSlider_batchCount )
        mUI.MelSpacer(_subRow,w = 5)

        self.uiFunc_setBatchCount('field')

        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        
        mUI.MelLabel(_subRow,l='Batch Size:',align='right')
        self.uiIF_batchSize = mUI.MelIntField(_subRow,
                                                    minValue = 1,
                                                    value = 1,
                                                    annotation = 'Sampling Steps', changeCommand=cgmGEN.Callback(self.uiFunc_setBatchSize,'field'))  
        self.uiSlider_batchSize = mUI.MelIntSlider(_subRow,1,100,1,step = 1)
        self.uiSlider_batchSize.setChangeCB(cgmGEN.Callback(self.uiFunc_setBatchSize,'slider'))

        _subRow.setStretchWidget( self.uiSlider_batchSize )
        mUI.MelSpacer(_subRow,w = 5)

        self.uiFunc_setBatchSize('field')

        _subRow.layout()

        _row.layout()

        # CFG Scale
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='CFG Scale:',align='right', annotation = 'Value that model tries to conform to the prompt')
        self.uiIF_CFGScale = mUI.MelIntField(_row,
                                                    minValue = 1,
                                                    value = 7,
                                                    annotation = 'Value that model tries to conform to the prompt', changeCommand=cgmGEN.Callback(self.uiFunc_setCFGScale,'field'))  
        self.uiSlider_CFGScale = mUI.MelIntSlider(_row,1,100,1,step = 1)
        self.uiSlider_CFGScale.setChangeCB(cgmGEN.Callback(self.uiFunc_setCFGScale,'slider'))

        _row.setStretchWidget( self.uiSlider_CFGScale )
        mUI.MelSpacer(_row,w = 5)

        self.uiFunc_setCFGScale('field')

        _row.layout()

        #>>> Img2Img

        mc.setParent(_inside)
        cgmUI.add_Header('Img2Img Settings')

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Passes:',align='right')

        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        self.uiOM_passMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate', changeCommand = self.uiFunc_setImg2ImgPass)
        
        for option in ['None', 'Composite', 'Merged', 'Custom', 'Render Layer']:
            self.uiOM_passMenu.append(option)
        
        #self.uiCompositeCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=False, changeCommand = self.uiFunc_setCompositeCB)      

        mUI.MelLabel(_row,l='Alpha Matte:',align='right')
        self.uiAlphaMatteCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=False, en=False, changeCommand = self.uiFunc_setAlphaMatteCB)      

        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        self.img2imgLayout = mUI.MelColumnLayout(_inside,useTemplate = 'cgmUISubTemplate')

        #>>> Custom Image
        self.customImage_row = mUI.MelHSingleStretchLayout(self.img2imgLayout,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(self.customImage_row,w=5)
        mUI.MelLabel(self.customImage_row,l='Custom Image:',align='right')
        self.uiTextField_customImage = mUI.MelTextField(self.customImage_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(self.customImage_row,w = 5)
        self.customImage_row.setStretchWidget(self.uiTextField_customImage)
        cgmUI.add_Button(self.customImage_row,'Load', lambda *a:self.uiFunc_load_custom_image())
        mUI.MelSpacer(self.customImage_row,w = 5)
        self.customImage_row.layout()

        #>>> Render Layer
        self.renderLayer_row = mUI.MelHSingleStretchLayout(self.img2imgLayout,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(self.renderLayer_row,w=5)
        mUI.MelLabel(self.renderLayer_row,l='Render Layer:',align='right')
        self.uiOM_renderLayer = mUI.MelOptionMenu(self.renderLayer_row,useTemplate = 'cgmUITemplate', bsp=cgmGEN.Callback(self.uiFunc_updateRenderLayers))
        
        render_layers = mc.ls(type='renderLayer')

        for option in render_layers:
            self.uiOM_renderLayer.append(option)

        mUI.MelSpacer(self.renderLayer_row,w = 5)
        self.renderLayer_row.setStretchWidget(self.uiOM_renderLayer)
        cgmUI.add_Button(self.renderLayer_row,'Render', lambda *a:self.uiFunc_renderLayer())
        mUI.MelSpacer(self.renderLayer_row,w = 5)

        self.renderLayer_row.layout()

        #>>>Denoise Slider...
        denoise = .35
        _row = mUI.MelHSingleStretchLayout(self.img2imgLayout,expand = True,ut = 'cgmUISubTemplate')
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

        self.alphaMatteLayout = mUI.MelHLayout(self.img2imgLayout,expand = True,ut = 'cgmUISubTemplate', vis=self.uiAlphaMatteCB(q=True, v=True))
        
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
        cgmUI.add_Button(_row,'XYZ', lambda *a:self.uiFunc_assign_material(self.uiTextField_xyzShader))
        cgmUI.add_Button(_row,'Projection', lambda *a:self.uiFunc_assign_material(self.uiTextField_projectionShader))
        cgmUI.add_Button(_row,'Alpha', lambda *a:self.uiFunc_assign_material(self.uiTextField_alphaShader))
        cgmUI.add_Button(_row,'Composite', lambda *a:self.uiFunc_assign_material(self.uiTextField_compositeShader))
        cgmUI.add_Button(_row,'Alpha Matte', lambda *a:self.uiFunc_assign_material(self.uiTextField_alphaMatteShader))

        cgmUI.add_Button(_row,'Merged', lambda *a:self.uiFunc_assign_material(self.uiTextField_mergedShader))
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>>Depth Slider...
        minDepth = 0
        maxDepth = 50.0
        depthShader = self.getDepthShader()
        if(depthShader):
            minDepth = mc.getAttr('%s.minDistance' % depthShader)
            maxDepth = mc.getAttr('%s.maxDistance' % depthShader)

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Depth:',align='right')
        _layoutRow = mUI.MelHLayout(_row,ut='cgmUISubTemplate',padding = 10)

        _subRow = mUI.MelHSingleStretchLayout(_layoutRow,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelLabel(_subRow,l='Min:',align='right')
        self.uiFF_minDepthDistance = mUI.MelFloatField(_subRow,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = minDepth, changeCommand=cgmGEN.Callback(self.uiFunc_setDepth, 'field'))  
                
        self.uiSlider_minDepthDistance = mUI.MelFloatSlider(_subRow,0.0,100.0,minDepth,step = 1)
        self.uiSlider_minDepthDistance.setChangeCB(cgmGEN.Callback(self.uiFunc_setDepth, 'slider'))
        _subRow.setStretchWidget(self.uiSlider_minDepthDistance)#Set stretch    
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_layoutRow,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelLabel(_subRow,l='Max:',align='right')
        self.uiFF_maxDepthDistance = mUI.MelFloatField(_subRow,
                                                w = 40,
                                                ut='cgmUITemplate',
                                                precision = 2,
                                                value = maxDepth, changeCommand=cgmGEN.Callback(self.uiFunc_setDepth, 'field'))  
                
        self.uiSlider_maxDepthDistance = mUI.MelFloatSlider(_subRow,1.0,100.0,maxDepth,step = 1)
        self.uiSlider_maxDepthDistance.setChangeCB(cgmGEN.Callback(self.uiFunc_setDepth, 'slider'))
        _subRow.setStretchWidget(self.uiSlider_maxDepthDistance)#Set stretch    

        _subRow.layout()
        _layoutRow.layout()
        _row.setStretchWidget(_layoutRow)
        _row.layout()

        self.uiFunc_setDepth('field')

        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='XYZ:',align='right')
        _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

        self.renderBtn = cgmUI.add_Button(_row,'Set BBox From Selected',
        cgmGEN.Callback(self.uiFunc_setXYZFromSelected),                         
        'Set BBox From Selected')
        self.viewImageBtn = cgmUI.add_Button(_row,'Bake',
        cgmGEN.Callback(self.uiFunc_bakeXYZMap),                         
        'Bake XYZ map')
        mUI.MelSpacer(_row,w=5)	            
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
        
        self.generateBtn = cgmUI.add_Button(_row,'Steal Art',
            cgmGEN.Callback(self.uiFunc_generateImage),                         
            'Generate',h=50)

        self.bakeProjectionBtn = cgmUI.add_Button(_row,'Bake Projection',
            cgmGEN.Callback(self.uiFunc_bakeProjection),                         
            'Bake Projection',h=50)

        self.mergeCompositeBtn = cgmUI.add_Button(_row,'Merge Composite',
            cgmGEN.Callback(self.uiFunc_mergeComposite),                         
            'Merge Composite',h=50)

        _row.layout()    
        #
        # End Generate Button

        return _inside

    def buildColumn_edit(self,parent, asScroll = True, inside = None):

        if(inside):
            _inside = inside
        else:
            if asScroll:
                _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
            else:
                _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
                
        compositeShader = self.uiTextField_compositeShader.getValue()
        if not compositeShader:
            return _inside

        #self.editTabContent = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate', padding = 10)

        cgmUI.add_Button(_row, 'Refresh', 
                cgmGEN.Callback( self.uiFunc_refreshEditTab ),
                annotationText='')
        
        cgmUI.add_Button(_row,'Set Composite', lambda *a:self.uiFunc_assign_material(self.uiTextField_compositeShader))
        
        cgmUI.add_Button(_row, 'Merge Composite', 
                cgmGEN.Callback( self.uiFunc_mergeComposite ),
                annotationText='')
        
        _row.layout()

        # Get the layered texture node
        layeredTexture = mc.listConnections(compositeShader + ".outColor", type="layeredTexture")[0]

        # Get the number of color inputs to the layered texture
        num_inputs = mc.getAttr(layeredTexture + ".inputs", multiIndices=True)

        # Loop through each color input and create a layout for it
        self.layers = []
        for i in num_inputs:
            input_color = layeredTexture + ".inputs[{}].color".format(i)

            color_connections = mc.listConnections(input_color)
            if not color_connections:
                return _inside
            
            color_name = color_connections[0]

            _frame = mUI.MelFrameLayout(_inside,label = color_name,vis=True,
                            collapse=False,
                            collapsable=True,
                            enable=True,
                            useTemplate = 'cgmUITemplate',
                            #expandCommand = lambda *a:mVar_frame.setValue(0),
                            #collapseCommand = lambda *a:mVar_frame.setValue(1)
                            )
            color_layout = mUI.MelColumn(_frame,useTemplate = 'cgmUISubTemplate') 

            # Create a new MelHSingleStretchLayout for the visibility and solo checkboxes
            #subrow_layout = mUI.MelHSingleStretchLayout(color_layout, ut="cgmUISubTemplate")           
            _thumbSize = (150,150)
            
            subrow_layout = mUI.MelRowLayout(color_layout, numberOfColumns=3, columnWidth3=(20,_thumbSize[0], 50), adjustableColumn=3, columnAlign=(1, 'left'), columnAttach=(1, 'right', 0), useTemplate='cgmUITemplate')
            
            # make column layout
            _buttonColumn = mUI.MelVLayout(subrow_layout, w= 20,)
            
            button_up =  mUI.MelButton(_buttonColumn,l="up",w=20, ut='cgmUITemplate')
            mUI.MelSpacer(_buttonColumn,h=25)
            button_dn = mUI.MelButton(_buttonColumn,l="dn",w=20, ut='cgmUITemplate')
            _buttonColumn.layout()
            
            _thumb_row = mUI.MelColumnLayout(subrow_layout,useTemplate = 'cgmUISubTemplate')


            _thumb = mUI.MelImage( _thumb_row, w=_thumbSize[0], h=_thumbSize[1] )
            _thumb(e=True, vis=True)
            
            _uv_projection_path = mc.getAttr(color_name + '.fileTextureName')
            _orig_path = ""
            _image_path = _uv_projection_path

            if( mc.objExists(color_name + '.cgmSourceProjectionImage') ):
                _orig_path = mc.getAttr(color_name + '.cgmSourceProjectionImage')
                if( os.path.exists(_orig_path) ):
                    _image_path = _orig_path

            _thumb_path = getResizedImage(_image_path, _thumbSize[0], _thumbSize[1], preserveAspectRatio=True)

            _thumb.setImage( _thumb_path )

            info_row = mUI.MelColumn(subrow_layout,useTemplate = 'cgmUISubTemplate')
            
            info_top_column = mUI.MelHSingleStretchLayout(info_row, ut="cgmUISubTemplate")                       
            visible_cb = mUI.MelCheckBox(info_top_column, useTemplate='cgmUITemplate', label="Vis", v=mc.getAttr('%s.inputs[%i].isVisible' % (layeredTexture, i)), changeCommand=lambda *a, s=self: s.uiFunc_updateLayerVisibility(i))
            solo_cb = mUI.MelCheckBox(info_top_column, useTemplate='cgmUITemplate', label="Solo", v=False, changeCommand=lambda *a, s=self: s.uiFunc_updateLayerVisibility(i))

            # set label as stretch widget
            info_top_column.setStretchWidget( mUI.MelSeparator(info_top_column, w=2) )
            
            _layerTF = mUI.MelTextField(info_top_column,useTemplate = 'cgmUITemplate',vis=False, text = color_name)
            
            _cameraData = {}
            if( mc.objExists(color_name + '.cgmImageProjectionData') ):
                _data = json.loads(mc.getAttr(color_name + '.cgmImageProjectionData'))
                if('camera_info' in _data):
                    _cameraData = _data['camera_info']

            _compositeConnection = None
            _compositeSourceAttribute = color_name + '.cgmCompositeTextureSource'
            if( mc.objExists(_compositeSourceAttribute) ):
                _compositeConnection = mc.listConnections(_compositeSourceAttribute, type='layeredTexture')

            if os.path.exists(_orig_path):
                cgmUI.add_Button(info_top_column, 'View Orig',
                        cgmGEN.Callback( self.uiFunc_viewImageFromPath, _orig_path),
                        annotationText='')
            if os.path.exists(_uv_projection_path):
                cgmUI.add_Button(info_top_column, 'View UV',
                        cgmGEN.Callback( self.uiFunc_viewImageFromPath, _uv_projection_path),
                        annotationText='')
            cgmUI.add_Button(info_top_column, 'Select',
                    cgmGEN.Callback( uiFunc_select_item_from_text_field, _layerTF),
                    annotationText='')
            if _cameraData:
                cgmUI.add_Button( info_top_column, 'Snap Camera', 
                        cgmGEN.Callback( self.uiFunc_snapCameraFromData, _cameraData),
                        annotationText='')
            if _compositeConnection:
                cgmUI.add_Button( info_top_column, 'Restore Comp', 
                        cgmGEN.Callback( self.uiFunc_restoreComposite, _compositeConnection[0]),
                        annotationText='')
            
            mUI.MelSpacer(info_top_column,w = 5)
            info_top_column.layout()
            
            # Check if the alpha input has a remapColor node and create min/max sliders if it does
            alpha_input = layeredTexture + ".inputs[{}].alpha".format(i)
            remap_color_nodes = rt.getAllConnectedNodesOfType(alpha_input, "remapColor")
            channelSliders = {}

            _hasPositionRemap = False

            _mesh = self.uiTextField_baseObject.getValue()
            _xyzFile = self.getXYZFile(_mesh)
            

            for remap_color in remap_color_nodes:
                # Create a new MelHSingleStretchLayout for each remapColor channel
                
                remap_file = mc.listConnections(remap_color + '.color', type='file')
                if remap_file:
                    remap_file = remap_file[0]
                    if remap_file == _xyzFile and _xyzFile: 
                        _hasPositionRemap = True

                for channel in ["red", "green", "blue"]:
                    label = channel.capitalize()
                    if(mc.objExists('%s.cgm%sLabel'%(remap_color, channel.capitalize()))):
                        label = mc.getAttr('%s.cgm%sLabel'%(remap_color, channel.capitalize()))
                    
                    _alphaFrame = mUI.MelFrameLayout(info_row,label = label,vis=True,
                                    collapse=True,
                                    collapsable=True,
                                    enable=True,
                                    useTemplate = 'cgmUITemplate',
                                    #expandCommand = lambda *a:mVar_frame.setValue(0),
                                    #collapseCommand = lambda *a:mVar_frame.setValue(1)
                                    )

                    _alpha_col = mUI.MelColumnLayout(_alphaFrame,useTemplate = 'cgmUISubTemplate')
                    mc.setParent(_alpha_col)
                    _grad = mc.gradientControl( at='%s.%s'%(remap_color, channel), dropCallback = "print 'dropCallback executed'" )
            
            if len(remap_color_nodes) < 5:
                for i in range(5-len(remap_color_nodes)):
                    mUI.MelLabel(info_row,label = "")                
        
            
            if not _hasPositionRemap and _xyzFile:
                cgmUI.add_Button(info_row, 'Add Position Matte',
                        cgmGEN.Callback( self.uiFunc_addPositionMatte, alpha_input),
                        annotationText='')
            
            self.layers.append({"visible_cb": visible_cb, "layeredTexture":layeredTexture, "index": i, "solo_cb": solo_cb, "channelSliders": channelSliders})

            #subrow_layout.layout()
            
        return _inside
    
    @property
    def currentTab(self):
        tabIndex = mc.tabLayout(self.uiTabLayout, q=True, sti=True)
        return mc.tabLayout(self.uiTabLayout, q=True, tl=True)[tabIndex-1]
    
    def uiFunc_restoreComposite(self, layeredTexture):
        _str_func = 'uiFunc_restoreComposite'

        compositeShader = self.uiTextField_compositeShader.getValue()

        if not compositeShader:
            return
        
        mc.connectAttr(layeredTexture + '.outColor', compositeShader + '.outColor', f=True)

        self.uiFunc_refreshEditTab()

    def uiFunc_handleTabChange(self):
        if(self.currentTab.lower() == 'edit'):
            self.uiFunc_refreshEditTab()

    def uiFunc_addPositionMatte(self, alphaConnection):
        _str_func = 'uiFunc_addPositionMatte'
        baseObj = self.uiTextField_baseObject(query=True, text=True)
        xyzFile = self.getXYZFile(baseObj)

        print ("operating on {}, xyz = {}, connection = {}".format(baseObj, xyzFile, alphaConnection))

        if not xyzFile:
            return
        
        remap, mult = rt.remapAndMultiplyColorChannels(xyzFile, labels=['X', 'Y', 'Z'])
        connections = mc.listConnections(alphaConnection, p=True)
        if connections:
            print("connections = {}".format(connections))
            finalMult = mc.shadingNode('multiplyDivide', asUtility=True)
            print("finalMult = {}".format(finalMult))
            mc.connectAttr(connections[0], finalMult + '.input1X', f=True)
            mc.connectAttr(mult + '.outputX', finalMult + '.input2X', f=True)
            mc.connectAttr(finalMult + '.outputX', alphaConnection, f=True)
        else:
            mc.connectAttr(mult + '.outputX', alphaConnection, f=True)
        
        self.uiFunc_refreshEditTab()

    def getXYZFile(self, mesh):
        if not mc.objExists(mesh + '.xyzColor'):
            return None
        
        xyzFile = mc.listConnections(mesh + '.xyzColor', type='file')
        if not xyzFile:
            return None
        
        return xyzFile[0]

    def uiFunc_setXYZFromSelected(self):
        _str_func = 'uiFunc_setXYZFromSelected'
        _sel = mc.ls(sl=True)
        if not _sel:
            return

        xyzShader = self.uiTextField_xyzShader(query=True, text=True)
        if not mc.objExists(xyzShader):
            return
        
        _sel = _sel[0]
        _bbox = mc.exactWorldBoundingBox(_sel)
        mc.setAttr(xyzShader + '.bboxMin', _bbox[0], _bbox[1], _bbox[2], type='double3')
        mc.setAttr(xyzShader + '.bboxMax', _bbox[3], _bbox[4], _bbox[5], type='double3')

    def uiFunc_bakeXYZMap(self):
        _str_func = 'uiFunc_bakeXYZMap'
        mesh = self.uiTextField_baseObject(query=True, text=True)
        if not mc.objExists(mesh):
            return
        
        xyzShader = self.uiTextField_xyzShader(query=True, text=True)
        if not mc.objExists(xyzShader):
            return
        
        xyzFile = rt.bakeProjection(xyzShader, mesh)
        if not xyzFile:
            return
        
        # create double3 attribute xyzMap
        if not mc.objExists(mesh + '.xyzColor'):
            mc.addAttr(mesh, longName='xyzColor', at='double3')
            mc.addAttr(mesh, longName='xyzColorR', at='double', parent='xyzColor')
            mc.addAttr(mesh, longName='xyzColorG', at='double', parent='xyzColor')
            mc.addAttr(mesh, longName='xyzColorB', at='double', parent='xyzColor')

        mc.connectAttr(xyzFile + '.outColor', mesh + '.xyzColor', force=True)            

    def uiFunc_refreshEditTab(self):
        _str_func = 'uiFunc_refreshEditTab'

        self.editColumn.clear()
        self.editColumn = self.buildColumn_edit(None, inside=self.editColumn)
    
    def uiFunc_updateChannelGradient(self, dragControl, dropControl, messages, x, y, dragType):
        print("updateChannelGradient", dragControl, dropControl, messages, x, y, dragType)
    
    def uiFunc_updateLayerVisibility(self, index):
        soloLayers = []
        for layer in self.layers:
            if layer['solo_cb'].getValue():
                soloLayers.append(layer)

        for layer in self.layers:
            visible = layer['visible_cb'].getValue()
            solo = layer['solo_cb'].getValue()
            if soloLayers:
                visible = layer in soloLayers
            
            mc.setAttr('%s.inputs[%i].isVisible' % (layer['layeredTexture'], layer['index']), visible)

    def uiFunc_changeAutomatic1111Url(self):
        _str_func = 'uiFunc_changeAutomatic1111Url'

        self.saveOptions()

        self.handleReset()

    def uiFunc_setImg2ImgPass(self, *a):
        _str_func = 'uiFunc_setImg2ImgPass'
        print(_str_func, a)

        option = a[0].lower()
        val = option != 'none'

        self.img2imgLayout(e=True, vis=val)

        self.customImage_row(e=True, vis=option == 'custom')
        self.renderLayer_row(e=True, vis=option == 'render layer')
        self.uiAlphaMatteCB(e=True, en=val)

        self.saveOptions()

    def uiFunc_setAlphaMatteCB(self, *a):
        _str_func = 'uiFunc_setAlphaMatteCB'
        print(_str_func, a)

        val = a[0]

        self.alphaMatteLayout(e=True, vis=val)

        self.saveOptions()

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
            if(mc.getAttr(shader) == 'sd_merged'):
                self.uiTextField_mergedShader(edit=True, text=shader.split('.')[0])
                continue
            if(mc.getAttr(shader) == 'sd_xyz'):
                self.uiTextField_xyzShader(edit=True, text=shader.split('.')[0])
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

    def uiFunc_setSize(self, source):
        _str_func = 'uiFunc_setSize'

        width,height=0,0

        if source == 'menu':
            size = self.uiOM_SizeMenu(query=True, value=True)
            width, height = [int(x) for x in size.split('x')]
            self.uiIF_Width(edit=True, value=width)
            self.uiIF_Height(edit=True, value=height)
        else:
            width = self.uiIF_Width(query=True, value=True)
            height = self.uiIF_Height(query=True, value=True)

        # set render globals
        mc.setAttr('defaultResolution.width', width)
        mc.setAttr('defaultResolution.height', height)

        aspectRatio = float(width)/float(height)
        mc.setAttr( "defaultResolution.deviceAspectRatio", aspectRatio)

        projectionCam = self.uiTextField_projectionCam(q=True, text=True)
        mc.setAttr( '%s.horizontalFilmAperture' % projectionCam, aspectRatio )
        mc.setAttr( '%s.verticalFilmAperture' % projectionCam, 1.0 )

        self.saveOptions()

    def uiFunc_renderLayer(self, display=True):
        _str_func = 'uiFunc_renderLayer'

        # get render layer
        currentLayer = mc.editRenderLayerGlobals(query=True, currentRenderLayer=True)
        mc.editRenderLayerGlobals(currentRenderLayer=self.uiOM_renderLayer(query=True, value=True))

        # render
        outputImage = self.uiFunc_renderImage(display)

        # set render layer back
        mc.editRenderLayerGlobals(currentRenderLayer=currentLayer)

        return outputImage

    def uiFunc_renderImage(self, display=True):
        _str_func = 'uiFunc_renderImage'

        outputImage = rt.renderMaterialPass(None, self.uiTextField_baseObject(query=True, text=True), camera = self.uiTextField_projectionCam(q=True, text=True), resolution = self.resolution  )
        if display:
            iv.ui([outputImage], {'outputImage':outputImage})
        
        return outputImage

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

    def uiFunc_viewImageFromPath(self, path):
        _str_func = 'uiFunc_viewImageFromPath'
        print(_str_func, path)

        if os.path.exists(path):
            iv.ui([path], {'outputImage':path})
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))
            return

    def uiFunc_snapCameraFromData(self, cameraData):
        _str_func = 'uiFunc_snapCameraFromData'

        camera = self.uiTextField_projectionCam(query=True, text=True)
        if not mc.objExists(camera):
            log.warning("|{0}| >> No camera loaded.".format(_str_func))
            return

        if not cameraData:
            log.warning("|{0}| >> No camera data loaded.".format(_str_func))
            return

        cameraTransform = mc.listRelatives(camera, parent=True)[0]
        # get camera data
        
        position = cameraData['position']
        rotation = cameraData['rotation']
        fov = cameraData['fov']

        # set camera data
        mc.setAttr(cameraTransform+'.translateX', position[0])
        mc.setAttr(cameraTransform+'.translateY', position[1])
        mc.setAttr(cameraTransform+'.translateZ', position[2])
        mc.setAttr(cameraTransform+'.rotateX', rotation[0])
        mc.setAttr(cameraTransform+'.rotateY', rotation[1])
        mc.setAttr(cameraTransform+'.rotateZ', rotation[2])

        # set fov
        mc.setAttr(camera+'.focalLength', fov)

    def uiFunc_make_projection_camera(self):
        cam, shape = rt.makeProjectionCamera()
        self.uiTextField_projectionCam(edit=True, text=shape)

    def uiFunc_make_projection_shader(self):
        _str_func = 'uiFunc_make_projection_shader'
        _camera = self.uiTextField_projectionCam(query=True, text=True)

        if not mc.objExists(_camera):
            log.warning("|{0}| >> No camera loaded.".format(_str_func))
            return
        
        shader, sg = rt.makeProjectionShader(_camera)
        self.uiTextField_projectionShader(edit=True, text=shader)

    def uiFunc_make_alpha_shader(self):
        _str_func = 'uiFunc_make_alpha_shader'
        _camera = self.uiTextField_projectionCam(query=True, text=True)

        if not mc.objExists(_camera):
            log.warning("|{0}| >> No camera loaded.".format(_str_func))
            return
        
        shader, sg = rt.makeAlphaShader(_camera)

        depthShader = self.uiTextField_depthShader(query=True, text=True)
        if mc.objExists(depthShader):
            ramp = mc.listConnections(depthShader + '.outColor', type='ramp')
            if(ramp):
                mult = mc.listConnections(shader + '.outColorG', type='multiplyDivide')
                if(mult):
                    mc.connectAttr(ramp[0] + '.outColorG', mult[0] + '.input2Y', force=True)
                else:
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

        shader, sg = rt.makeDepthShader()
        self.uiTextField_depthShader(edit=True, text=shader)

        alphaShader = self.uiTextField_alphaShader(query=True, text=True)
        if mc.objExists(alphaShader):
            ramp = mc.listConnections(shader + '.outColor', type='ramp')
            if(ramp):
                mult = mc.listConnections(alphaShader + '.outColorG', type='multiplyDivide')
                if(mult):
                    mc.connectAttr(ramp[0] + '.outColorG', mult[0] + '.input2Y', force=True)
                else:
                    mc.connectAttr(ramp[0] + '.outColorG', alphaShader + '.outColorG', force=True)

        mc.setAttr(shader + '.maxDistance', self.uiFF_maxDepthDistance(query=True, value=True))

    def uiFunc_make_xyz_shader(self):
        _str_func = 'uiFunc_make_xyz_shader'

        shader, sg = rt.makeXYZShader()

        mesh = self.uiTextField_baseObject(query=True, text=True)
        if mc.objExists(mesh):
            bbox = mc.exactWorldBoundingBox(mesh)

            mc.setAttr(shader + '.bboxMin', bbox[0], bbox[1], bbox[2], type='double3')
            mc.setAttr(shader + '.bboxMax', bbox[3], bbox[4], bbox[5], type='double3')

        self.uiTextField_xyzShader(edit=True, text=shader)

    def uiFunc_make_merged_shader(self):
        _str_func = 'uiFunc_make_merged_shader'

        shader, sg = sd.makeMergedShader()

        self.uiTextField_mergedShader(edit=True, text=shader)

    def uiFunc_generateImage(self):
        _str_func = 'uiFunc_generateImage'

        depthMat = self.uiTextField_depthShader(q=True, text=True)
        alphaMat = self.uiTextField_alphaMatteShader(q=True, text=True)
        compositeMat = self.uiTextField_compositeShader(q=True, text=True)

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

        output_path = PROJECT.getImagePath()

        composite_path = None
        composite_string = None

        option = _options['img2img_pass'].lower()
        print("img2img_pass", option)

        if option != "none":
            if (option == "composite" or option == "merged") and mc.objExists(compositeMat) and mc.objExists(mesh):
                wantedMat = compositeMat
                if option == "merged":
                    wantedMat = self.uiTextField_mergedShader(query=True, text=True)
                composite_path = rt.renderMaterialPass(wantedMat, mesh, camera=camera, resolution=self.resolution)

                print("composite path: ", composite_path)
                with open(composite_path, "rb") as c:
                    # Read the image data
                    composite_data = c.read()
                    
                    # Encode the image data as base64
                    composite_base64 = base64.b64encode(composite_data)
                    
                    # Convert the base64 bytes to string
                    composite_string = composite_base64.decode("utf-8")

                    c.close()

                _options['init_images'] = [composite_string]
            elif option == "custom":
                custom_image = self.uiTextField_customImage(query=True, text=True)
                print("custom image: ", custom_image)

                if(os.path.exists(custom_image)):
                    with open(custom_image, "rb") as c:
                        # Read the image data
                        composite_data = c.read()
                        
                        # Encode the image data as base64
                        composite_base64 = base64.b64encode(composite_data)
                        
                        # Convert the base64 bytes to string
                        composite_string = composite_base64.decode("utf-8")

                        c.close()

                    _options['init_images'] = [composite_string]
            elif option == 'render layer':
                outputImage = self.uiFunc_renderLayer(display=False)
                print("render layer: ", outputImage)

                if outputImage:
                    with open(outputImage, "rb") as c:
                        # Read the image data
                        composite_data = c.read()
                        
                        # Encode the image data as base64
                        composite_base64 = base64.b64encode(composite_data)
                        
                        # Convert the base64 bytes to string
                        composite_string = composite_base64.decode("utf-8")

                        c.close()

                    _options['init_images'] = [composite_string]

        if self.uiOM_ControlNetPreprocessorMenu(q=True, value=True) == 'none':
            if mc.objExists(depthMat) and mc.objExists(mesh):
                format = 'png'
                depth_path = rt.renderMaterialPass(depthMat, mesh, camera=camera, resolution=(self.resolution[0]*2, self.resolution[1]*2))
                print( "depth_path: {0}".format(depth_path) )
                # Read the image data
                depth_image = Image.open(depth_path)

                # Convert the image data to grayscale
                depth_image_RGB = depth_image.convert('RGB')

                # Encode the image data as base64
                #depth_buffered = BytesIO()
                with BytesIO() as depth_buffered:
                    depth_image_RGB.save(depth_buffered, format=format)
                    
                    depth_base64 = base64.b64encode(depth_buffered.getvalue())

                    # Convert the base64 bytes to string
                    depth_string = depth_base64.decode("utf-8")

                    _options['control_net_image'] = depth_string
        else:
            if not composite_string:
                composite_path = rt.renderMaterialPass(compositeMat, mesh, camera=camera, resolution=self.resolution)

                with open(composite_path, "rb") as c:
                    # Read the image data
                    composite_data = c.read()
                    
                    # Encode the image data as base64
                    composite_base64 = base64.b64encode(composite_data)
                    
                    # Convert the base64 bytes to string
                    composite_string = composite_base64.decode("utf-8")
            
            _options['control_net_image'] = composite_string
        
        if _options['use_alpha_pass'] and _options['img2img_pass'] != 'none' and mc.objExists(alphaMat) and mc.objExists(mesh):
            alpha_path = rt.renderMaterialPass(alphaMat, mesh, camera=camera, resolution=self.resolution)

            print ("alpha_path: {0}".format(alpha_path))

            if os.path.exists(alpha_path):
                # Read the image data
                alpha_image = Image.open(alpha_path)

                # Convert the image data to grayscale
                alpha_image_gray = alpha_image.convert('L')

                # Encode the image data as base64
                buffered = BytesIO()
                alpha_image_gray.save(buffered, format="PNG")

                alpha_base64 = base64.b64encode(buffered.getvalue())

                # Convert the base64 bytes to string
                alpha_string = alpha_base64.decode("utf-8")

                _options['mask'] = alpha_string
                _options['mask_blur'] = self.uiIF_maskBlur(query=True, value=True)
                _options['inpainting_mask_invert'] = 1
            else:
                log.warning("|{0}| >> No alpha matte found.".format(_str_func))

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

        
        mFile = cgmMeta.asMeta(bakedImage)  

        projection = mc.listConnections(projectionShader, type='projection')
        if projection:
            projection = projection[0]
            projectionFile = mc.listConnections(f'{projection}.image')
            if projectionFile:
                mFile.doStore('cgmSourceProjectionImage',mc.getAttr(f'{projectionFile[0]}.fileTextureName'))  
                mFile.doStore('cgmImageProjectionData',mc.getAttr(f'{projectionFile[0]}.cgmImageProjectionData'))  
        
        compositeShader = self.uiTextField_compositeShader(query=True, text=True)
        alphaMatteShader = self.uiTextField_alphaMatteShader(query=True, text=True)

        rt.addImageToCompositeShader(compositeShader, bakedImage, bakedAlpha)
        rt.updateAlphaMatteShader(alphaMatteShader, compositeShader)

        # assign composite shader
        self.uiFunc_assign_material(self.uiTextField_compositeShader)

    def uiFunc_mergeComposite(self):
        compositeShader = self.uiTextField_compositeShader(query=True, text=True)
        mergedShader = self.uiTextField_mergedShader(query=True, text=True)
      
        sd.mergeCompositeShaderToImage(compositeShader, mergedShader)

        # assign merged shader
        self.uiFunc_assign_material(self.uiTextField_compositeShader)
        self.uiFunc_refreshEditTab()

    def uiFunc_setDepth(self, source):
        shader = self.getDepthShader()

        _minDepth = 0.0
        _maxDepth = 0.0

        if(shader):
            _minDepth = mc.getAttr('%s.minDistance' % shader)
            _maxDepth = mc.getAttr('%s.maxDistance' % shader)

        if source == 'slider':
            _minDepth = self.uiSlider_minDepthDistance(query=True, value=True)
            self.uiFF_minDepthDistance.setValue(_minDepth)

            _maxDepth = self.uiSlider_maxDepthDistance(query=True, value=True)
            self.uiFF_maxDepthDistance.setValue(_maxDepth)
            
        elif source == 'field':
            _minDepth = self.uiFF_minDepthDistance.getValue()
            self.uiSlider_minDepthDistance(edit=True, max=max(100.0, _minDepth))
            self.uiSlider_minDepthDistance(edit=True, value=_minDepth, step=1)

            _maxDepth = self.uiFF_maxDepthDistance.getValue()
            self.uiSlider_maxDepthDistance(edit=True, max=max(100.0, _maxDepth))
            self.uiSlider_maxDepthDistance(edit=True, value=_maxDepth, step=1)
        
        if shader:
            mc.setAttr('%s.minDistance' % shader, _minDepth)
            mc.setAttr('%s.maxDistance' % shader, _maxDepth)
        
        self.saveOptions()

    def uiFunc_setSamples(self, source):

        uiFunc_setFieldSlider(self.uiIF_samplingSteps, self.uiSlider_samplingSteps, source, 100)
        
        self.saveOptions()

    def uiFunc_load_custom_image(self):
        _str_func = 'uiFunc_load_custom_image'

        _file = mc.fileDialog2(fileMode=1, caption='Select Image File', fileFilter='*.jpg *.jpeg *.png')
        if _file:
            _file = _file[0]
            if not os.path.exists(_file):
                log.error("|{0}| >> File not found: {1}".format(_str_func, _file))
                return False

            self.uiTextField_customImage(edit=True, text=_file)
            self.saveOptions()

    def uiFunc_updateRenderLayers(self):
        _str_func = 'uiFunc_updateRenderLayers'

        currentRenderLayer = self.uiOM_renderLayer.getValue()

        self.uiOM_renderLayer.clear()

        _layers = mc.ls(type='renderLayer')
        if not _layers:
            log.error("|{0}| >> No render layers found".format(_str_func))
            return False
        
        for _layer in _layers:
            self.uiOM_renderLayer.append(_layer)
            if _layer == currentRenderLayer:
                self.uiOM_renderLayer.setValue(_layer)

    def uiFunc_setDenoise(self, source):
        uiFunc_setFieldSlider(self.uiFF_denoiseStrength, self.uiSlider_denoiseStrength, source, 1.0, .01)
        
        self.saveOptions()


    def uiFunc_setBatchCount(self, source):
        uiFunc_setFieldSlider(self.uiIF_batchCount, self.uiSlider_batchCount, source, 10)
        
        self.saveOptions()

    def uiFunc_setBatchSize(self, source):
        uiFunc_setFieldSlider(self.uiIF_batchSize, self.uiSlider_batchSize, source, 8)
        
        self.saveOptions()
        
    def uiFunc_setCFGScale(self, source):
        uiFunc_setFieldSlider(self.uiIF_CFGScale, self.uiSlider_CFGScale, source, 30)
        
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

        if not _models:
            log.error("|{0}| >> No models found".format(_str_func))
            return []

        # get current model
        _currentModel = self.uiOM_ControlNetModelMenu.getValue()

        self.uiOM_ControlNetModelMenu.clear()
        for _model in _models['model_list']:
            if(filter not in _model):
                continue
            self.uiOM_ControlNetModelMenu.append(_model)
            if _model == _currentModel:
                self.uiOM_ControlNetModelMenu.setValue(_model)

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
        _options['min_depth_distance'] = self.uiFF_minDepthDistance.getValue()
        _options['max_depth_distance'] = self.uiFF_maxDepthDistance.getValue()
        _options['control_net_enabled'] = self.uiControlNetEnabledCB.getValue()
        _options['control_net_low_v_ram'] = self.uiControlNetLowVRamCB.getValue()
        _options['control_net_preprocessor'] = self.uiOM_ControlNetPreprocessorMenu(query=True, value=True)
        _options['control_net_model'] = self.uiOM_ControlNetModelMenu(query=True, value=True)
        _options['control_net_weight'] = self.uiFF_controlNetWeight.getValue()
        _options['control_net_guidance_start'] = self.uiFF_controlNetGuidanceStart.getValue()
        _options['control_net_guidance_end'] = self.uiFF_controlNetGuidanceEnd.getValue()
        _options['denoising_strength'] = self.uiFF_denoiseStrength.getValue()
        _options['img2img_pass'] = self.uiOM_passMenu(query=True, value=True)
        _options['img2img_custom_image'] = self.uiTextField_customImage(query=True, text=True)
        _options['use_alpha_pass'] = self.uiAlphaMatteCB.getValue()
        _options['mask_blur'] = self.uiIF_maskBlur.getValue()
        _options['batch_count'] = self.uiIF_batchCount.getValue()
        _options['batch_size'] = self.uiIF_batchSize.getValue()
        _options['cfg_scale'] = self.uiIF_CFGScale.getValue()

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

        print(_str_func, ": loading", options)

        if not self._initialized:
            return

        _options = {}
        if(options):
            _options = options
        else:           
            _options = json.loads(self.config.getValue()) if self.config.getValue() else _defaultOptions

        # go through options and set default if not found
        for key in _defaultOptions:
            if key not in _options:
                _options[key] = _defaultOptions[key]

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
                print("key not found: ", key, " setting to default: ", _defaultOptions[key])
                _options[key] = _defaultOptions[key]

        self.uiTextField_automaticURL(edit=True, text=_options['automatic_url'])
        self.uiTextField_prompt(edit=True, text=_options['prompt'])
        self.uiTextField_negativePrompt(edit=True, text=_options['negative_prompt'])
        self.uiIF_Seed.setValue(int(_options['seed']))
        print("Seed is: ", _options['seed'])
        self.uiIF_Width(edit=True, v=_options['width'])
        self.uiIF_Height(edit=True, v=_options['height'])           
        if 'sampling_method' in _options:
            # get options from menu
            _samplingMethodMenu = self.uiOM_samplingMethodMenu(query=True, itemListLong=True) or []
            for item in _samplingMethodMenu:
                if mc.optionMenu(item, q=True, label=True) == _options['sampling_method']:
                    self.uiOM_samplingMethodMenu(edit=True, value=item)
                    break

        self.uiIF_CFGScale.setValue(_options['cfg_scale'])
        self.uiFunc_setCFGScale('field')

        self.uiIF_batchCount.setValue(_options['batch_count'])
        self.uiIF_batchSize.setValue(_options['batch_size'])
        self.uiFunc_setBatchSize('field')
        self.uiFunc_setBatchCount('field')

        self.uiIF_samplingSteps.setValue(_options['sampling_steps'])
        self.uiFF_minDepthDistance.setValue(_options['min_depth_distance'])
        self.uiFF_maxDepthDistance.setValue(_options['max_depth_distance'])
        self.uiControlNetEnabledCB.setValue(_options['control_net_enabled'])
        self.uiControlNetLowVRamCB.setValue(_options['control_net_low_v_ram'])
        self.uiOM_ControlNetPreprocessorMenu(edit=True, value=_options['control_net_preprocessor'])
        if 'control_net_model' in _options:
            _controlNetModels = self.uiOM_ControlNetModelMenu(query=True, itemListLong=True) or []
            for item in _controlNetModels:
                if mc.optionMenu(item, q=True, label=True) == _options['control_net_model']:
                    self.uiOM_ControlNetModelMenu(edit=True, value=_options['control_net_model'])
                    break

        self.uiFF_controlNetWeight.setValue(_options['control_net_weight'])
        self.uiFF_controlNetGuidanceStart.setValue(_options['control_net_guidance_start'])
        self.uiFF_controlNetGuidanceEnd.setValue(_options['control_net_guidance_end'])
        self.uiFF_denoiseStrength.setValue(_options['denoising_strength'])
        
        passOptions = [mc.menuItem(x, query=True, label=True) for x in self.uiOM_passMenu(query=True, itemListLong=True)]
        if _options['img2img_pass'] not in passOptions:
            _options['img2img_pass'] = passOptions[0]
        
        self.uiOM_passMenu(edit=True, value=_options['img2img_pass'])
        self.uiAlphaMatteCB.setValue(_options['use_alpha_pass'])
        self.uiTextField_customImage(edit=True, text=_options['img2img_custom_image'])
        self.uiIF_maskBlur.setValue(_options['mask_blur'])

        self.uiFunc_setImg2ImgPass(_options['img2img_pass'])
        self.uiFunc_setAlphaMatteCB(_options['use_alpha_pass'])
    
    def setProjectionImage(self, image):
        _str_func = 'setProjectionImage'
        self.uiImageField_projectionImage(edit=True, image=image)

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
        
def find_node_in_chain(attribute, node_type):
    connected_nodes = mc.listConnections(attribute, source=True, destination=False)

    if not connected_nodes:
        return None

    for connected_node in connected_nodes:
        if mc.nodeType(connected_node) == node_type:
            return connected_node
        else:
            output_attrs = mc.listAttr(connected_node, output=True, multi=True, connectable=True)
            if output_attrs:
                for output_attr in output_attrs:
                    full_attr = connected_node + "." + output_attr
                    found_node = find_node_in_chain(full_attr, node_type)
                    if found_node:
                        return found_node

    return None

def getResizedImage(imagePath, width, height, preserveAspectRatio=False):
    image = Image.open(imagePath)

    if preserveAspectRatio:
        # Get the aspect ratio of the image, scaling height to match the new width
        aspect_ratio = image.size[0] / image.size[1]
        height = int(width / aspect_ratio)

    new_img = image.resize((width, height), resample=Image.LANCZOS)

    # Save temporary image file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        new_img.save(f.name)
        new_temp_file_path = f.name

    # Update the image control with the new image
    return new_temp_file_path

def uiFunc_updateChannelGradient(dragControl, dropControl, messages, x, y, dragType):
    print( "uiFunc_updateChannelGradient", dragControl, dropControl, messages, x, y, dragType)