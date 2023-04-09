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
from cgm.lib import dictionary

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
        self.projectColumn = None
        self.connected = True

        self.samplingMethods = []
        self.sdModels = []
        self.controlNetModels = []

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

        self.uiFunc_tryAutomatic1111Connect()
        #self.loadOptions()  

    def buildColumn_main(self, parent, asScroll=False):
        self.uiTabLayout = mc.tabLayout()

        self.setupColumn = self.buildColumn_settings(self.uiTabLayout, asScroll = True)
        self.projectColumn = self.buildColumn_project(self.uiTabLayout, asScroll = True)
        self.editColumn = self.buildColumn_edit(self.uiTabLayout, asScroll = True)

        mc.tabLayout(self.uiTabLayout, edit=True, tabLabel=((self.setupColumn, 'Setup'), (self.projectColumn, 'Project'), (self.editColumn, 'Edit')), cc=lambda *a: self.uiFunc_handleTabChange(*a))

        return self.uiTabLayout

    #=============================================================================================================
    #>> Settings Column
    #=============================================================================================================
    def buildColumn_settings(self,parent, asScroll = False):
        """
        Trying to put all this in here so it's insertable in other uis
        
        """   
        if asScroll:
            _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
        else:
            _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        
        cgmUI.add_Header('Setup')
        
        _help = mUI.MelLabel(_inside,
                             bgc = dictionary.returnStateColor('help'),
                             align = 'center',
                             label = 'Set up the required materials for your projections',
                             h=20,
                             vis = False)	

        self.l_helpElements.append(_help)

        mUI.MelSpacer(_inside,w=5, h=7)

        mUI.MelLabel(_inside,
                             align = 'center',
                             label = 'Projection Meshes',
                             h=20)	

        self.uiList_projectionMeshes = mUI.MelObjectScrollList(_inside, ut='cgmUITemplate',
                                                      allowMultiSelection=True, h=100, dcc=self.uiFunc_selectMeshes )

        try:
            _str_section = 'Projection Mesh Targets Row'
            _uiRow_meshSplitterTargets = mUI.MelHLayout(_inside,padding = 1)
            cgmUI.add_Button(_uiRow_meshSplitterTargets, 'Load Selected', 
                             lambda *a:self.uiFunc_loadSelectedMeshes(),
                             annotationText='Load materials from selected objects')
            cgmUI.add_Button(_uiRow_meshSplitterTargets, 'Load All', 
                             lambda *a:self.uiFunc_loadAllMeshes(),
                             annotationText='Load all materials from scene')
            cgmUI.add_Button(_uiRow_meshSplitterTargets, 'Remove Selected', 
                             lambda *a:self.uiFunc_removeSelectedMeshes(),
                             annotationText='Remove all materials from list')
            cgmUI.add_Button(_uiRow_meshSplitterTargets, 'Clear All', 
                             lambda *a:self.uiFunc_clearAllMeshes(),
                             annotationText='Remove all materials from list')
            _uiRow_meshSplitterTargets.layout()      
        except Exception as err:
            log.error("{0} {1} failed to load. err: {2}".format(self._str_reportStart,_str_section,err))


        #>>> Mesh Load
        # _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        # mUI.MelSpacer(_row,w=5)
        # mUI.MelLabel(_row,l='Mesh:',align='right')
        # self.uiTextField_baseObject = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
        #                                                 ut = 'cgmUITemplate',
        #                                                 w = 50,
        #                                                 editable=False,
        #                                                 #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
        #                                                 annotation = "Our base object from which we process things in this tab...")
        # mUI.MelSpacer(_row,w = 5)
        # _row.setStretchWidget(self.uiTextField_baseObject)
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_shape(self.uiTextField_baseObject, enforcedType='mesh'))
        # cgmUI.add_Button(_row, 'Select', 
        #                     lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_baseObject),
        #                     annotationText='')               
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

        #>>> Load Projection Camera
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Projection Cam:',align='right')
        self.uiTextField_projectionCamera = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_projectionCamera)
        cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_shape(self.uiTextField_projectionCamera, enforcedType = 'camera'))
        cgmUI.add_Button(_row, 'Make',
                            lambda *a:self.uiFunc_make_projection_camera(),
                            annotationText='Make a projection camera')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_projectionCamera),
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

        #>>> Load Alpha Projection Shader
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Alpha Projection Shader:',align='right')
        self.uiTextField_alphaProjectionShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
                                                        ut = 'cgmUITemplate',
                                                        w = 50,
                                                        editable=False,
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Our base object from which we process things in this tab...")
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_alphaProjectionShader)
        cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_alphaProjectionShader, enforcedType = 'surfaceShader'))
        cgmUI.add_Button(_row, 'Make',
                            lambda *a:self.uiFunc_make_alpha_projection_shader(),
                            annotationText='')
        cgmUI.add_Button(_row, 'Select',
                            lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_alphaProjectionShader),
                            annotationText='')
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #########
        # Storing shader information on the mesh itself now, so don't need these
        # extra text fields
        #
        # #>>> Load Composite Shader
        # _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        # mUI.MelSpacer(_row,w=5)
        # mUI.MelLabel(_row,l='Composite Shader:',align='right')
        # self.uiTextField_compositeShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
        #                                                 ut = 'cgmUITemplate',
        #                                                 w = 50,
        #                                                 editable=False,
        #                                                 #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
        #                                                 annotation = "Our base object from which we process things in this tab...")
        # mUI.MelSpacer(_row,w = 5)
        # _row.setStretchWidget(self.uiTextField_compositeShader)
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_compositeShader, enforcedType = 'surfaceShader'))
        # cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_composite_shader(),annotationText='')
        # cgmUI.add_Button(_row, 'Select',
        #                     lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_compositeShader),
        #                     annotationText='')
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

        #>>> Load Alpha Matte Shader
        # _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        # mUI.MelSpacer(_row,w=5)
        # mUI.MelLabel(_row,l='Alpha Matte Shader:',align='right')
        # self.uiTextField_alphaMatteShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
        #                                                 ut = 'cgmUITemplate',
        #                                                 w = 50,
        #                                                 editable=False,
        #                                                 #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
        #                                                 annotation = "Our base object from which we process things in this tab...")
        # mUI.MelSpacer(_row,w = 5)
        # _row.setStretchWidget(self.uiTextField_alphaMatteShader)
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_alphaMatteShader, enforcedType = 'surfaceShader'))
        # cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_alpha_matte_shader(),annotationText='')
        # cgmUI.add_Button(_row, 'Select',
        #                     lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_alphaMatteShader),
        #                     annotationText='')
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

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

        #########
        # Storing shader information on the mesh itself now, so don't need these
        # extra text fields but keeping them around to be safe
        #
        #>>> Load XYZ Shader
        # _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        # mUI.MelSpacer(_row,w=5)
        # mUI.MelLabel(_row,l='XYZ Shader:',align='right')
        # self.uiTextField_xyzShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
        #                                                 ut = 'cgmUITemplate',
        #                                                 w = 50,
        #                                                 editable=False,
        #                                                 #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
        #                                                 annotation = "Our base object from which we process things in this tab...")
        # mUI.MelSpacer(_row,w = 5)
        # _row.setStretchWidget(self.uiTextField_xyzShader)
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_xyzShader, enforcedType = 'surfaceShader'))
        # cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_xyz_shader(),annotationText='')
        # cgmUI.add_Button(_row, 'Select',
        #                     lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_xyzShader),
        #                     annotationText='')
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

        #>>> Load Merged Shader
        # _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        # mUI.MelSpacer(_row,w=5)
        # mUI.MelLabel(_row,l='Merged Shader:',align='right')
        # self.uiTextField_mergedShader = mUI.MelTextField(_row,backgroundColor = [1,1,1],h=20,
        #                                                 ut = 'cgmUITemplate',
        #                                                 w = 50,
        #                                                 editable=False,
        #                                                 #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
        #                                                 annotation = "Our base object from which we process things in this tab...")
        # mUI.MelSpacer(_row,w = 5)
        # _row.setStretchWidget(self.uiTextField_mergedShader)
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_load_text_field_with_selected(self.uiTextField_mergedShader, enforcedType = 'surfaceShader'))
        # cgmUI.add_Button(_row, 'Make', lambda *a:self.uiFunc_make_merged_shader(),annotationText='')
        # cgmUI.add_Button(_row, 'Select',
        #                     lambda *a:uiFunc_select_item_from_text_field(self.uiTextField_mergedShader),
        #                     annotationText='')
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

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
        self.urlBtn = cgmUI.add_Button(_row, 'Retry Connection', lambda *a:self.uiFunc_tryAutomatic1111Connect(),annotationText='', bgc=[1,.5,.5])
        mUI.MelSpacer(_row,w = 5)
        _row.setStretchWidget(self.uiTextField_automaticURL)
        _row.layout()

        self.uiFunc_auto_populate_fields()
        return _inside

    #=============================================================================================================
    #>> Project Column
    #=============================================================================================================
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
                                                        #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                        annotation = "Prompt")
        self.uiTextField_prompt(edit=True, cc=lambda *a:self.saveOptionFromUI('prompt', self.uiTextField_prompt))
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
                                                        annotation = "Negative prompt")
        self.uiTextField_negativePrompt(edit=True, cc=lambda *a:self.saveOptionFromUI('negative_prompt', self.uiTextField_negativePrompt))
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
                                        annotation = 'Random seed to use for this project')	 	    
        self.uiIF_Seed(edit=True, cc=lambda *a:self.saveOptionFromUI('seed', self.uiIF_Seed))

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
        
        #self.uiFunc_updateModelsFromAutomatic()

        cgmUI.add_Button(_row,'Refresh', lambda *a:self.uiFunc_updateModelsFromAutomatic())
        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        #>>> Sampling
        _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_row,w=5)
        mUI.MelLabel(_row,l='Sampling Method:',align='right')
        self.uiOM_samplingMethodMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate')
        #self.uiFunc_updateSamplersFromAutomatic()
        self.uiOM_samplingMethodMenu(edit=True, changeCommand = lambda *a:self.saveOptionFromUI('sampling_method', self.uiOM_samplingMethodMenu))
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
        self.uiControlNetEnabledCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=True)
        self.uiControlNetEnabledCB(edit=True, changeCommand = lambda *a:self.saveOptionFromUI('control_net_enabled', self.uiControlNetEnabledCB))

        mUI.MelLabel(_row,l='Low VRAM:',align='right')
        self.uiControlNetLowVRamCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=True)      
        self.uiControlNetLowVRamCB(edit=True, changeCommand = lambda *a:self.saveOptionFromUI('control_net_low_v_ram', self.uiControlNetLowVRamCB))

        mUI.MelSpacer(_row,w = 5)
        _row.layout()

        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate')

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w=5)
        mUI.MelLabel(_subRow,l='Preprocessor:',align='right')

        self.uiOM_ControlNetPreprocessorMenu = mUI.MelOptionMenu(_subRow,useTemplate = 'cgmUITemplate', cc=self.uiFunc_changeControlNetPreProcessor)
        
        #self.uiFunc_updateControlNetPreprocessorsMenu()

        _subRow.setStretchWidget( self.uiOM_ControlNetPreprocessorMenu )

        mUI.MelSpacer(_subRow,w = 5)

        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row,expand = True,ut = 'cgmUISubTemplate')
        mUI.MelSpacer(_subRow,w = 5)
        mUI.MelLabel(_subRow,l='Model:',align='right')
        self.uiOM_ControlNetModelMenu = mUI.MelOptionMenu(_subRow,useTemplate = 'cgmUITemplate')
        self.uiOM_ControlNetModelMenu(edit=True, changeCommand = lambda *a:self.saveOption('control_net_model', self.uiOM_ControlNetModelMenu))
        
        #self.uiFunc_updateControlNetModelsFromAutomatic()
        
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
        cgmUI.add_Button(_row,'Depth', lambda *a:self.uiFunc_assignMaterial("depth"))
        cgmUI.add_Button(_row,'XYZ', lambda *a:self.uiFunc_assignMaterial("xyz"))
        cgmUI.add_Button(_row,'Projection', lambda *a:self.uiFunc_assignMaterial("projection"))
        cgmUI.add_Button(_row,'Alpha', lambda *a:self.uiFunc_assignMaterial("alphaProjection"))
        cgmUI.add_Button(_row,'Composite', lambda *a:self.uiFunc_assignMaterial("composite"))
        cgmUI.add_Button(_row,'Alpha Matte', lambda *a:self.uiFunc_assignMaterial("alphaMatte"))

        cgmUI.add_Button(_row,'Merged', lambda *a:self.uiFunc_assignMaterial("merged"))
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


    #=============================================================================================================
    #>> Edit Column
    #=============================================================================================================
    def buildColumn_edit(self,parent, asScroll = True, inside = None):

        if(inside):
            _inside = inside
        else:
            if asScroll:
                _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
            else:
                _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
                
        compositeShader = None #self.uiTextField_compositeShader.getValue()
        if not compositeShader:
            return _inside

        #self.editTabContent = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        _row = mUI.MelHLayout(_inside,expand = True,ut = 'cgmUISubTemplate', padding = 10)

        cgmUI.add_Button(_row, 'Refresh', 
                cgmGEN.Callback( self.uiFunc_refreshEditTab ),
                annotationText='')
        
        cgmUI.add_Button(_row,'Set Composite', lambda *a:self.uiFunc_assignMaterial('composite'))
        
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
                    _grad = mc.gradientControl( at='%s.%s'%(remap_color, channel), dropCallback = lambda *a: log.debug('dropCallback executed') )
            
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
    
    #=============================================================================================================
    #>> UI Properties
    #=============================================================================================================
    @property
    def currentTab(self):
        if( not self.uiTabLayout ):
            return None
        tabIndex = mc.tabLayout(self.uiTabLayout, q=True, sti=True)
        return mc.tabLayout(self.uiTabLayout, q=True, tl=True)[tabIndex-1]

    #=============================================================================================================
    #>> UI Funcs
    #=============================================================================================================
    def uiFunc_tryAutomatic1111Connect(self):
        _str_func = 'uiFunc_tryAutomatic1111Connect'

        self.urlBtn(e=True, bgc=(1,.8,0.4), label="Connecting...")
        mc.refresh()

        url = self.uiTextField_automaticURL(q=True, text=True)
        sdModels = sd.getModelsFromAutomatic1111(url)

        self.uiFunc_setConnected(sdModels)

    def uiFunc_setConnected(self, val):
        _str_func = 'uiFunc_setConnected'

        if not val:
            self.urlBtn(e=True, bgc=(1, .5, .5), label="Try Connection")
            self.connected = False
        else:
            self.urlBtn(e=True, bgc=(.5, 1, .5), label="Connected")
            if not self.connected:
                self.handleReload()
                return

    def uiFunc_restoreComposite(self, layeredTexture):
        _str_func = 'uiFunc_restoreComposite'

        compositeShader = self.uiTextField_compositeShader.getValue()

        if not compositeShader:
            return
        
        mc.connectAttr(layeredTexture + '.outColor', compositeShader + '.outColor', f=True)

        self.uiFunc_refreshEditTab()

    def uiFunc_handleTabChange(self):
        if not self.currentTab:
            return
        if(self.currentTab.lower() == 'edit'):
            self.uiFunc_refreshEditTab()
        elif(self.currentTab.lower() == 'project'):
            self.projectColumn(e=True, en=self.connected)
            if(self.connected):
                self.uiFunc_updateModelsFromAutomatic()
                self.uiFunc_updateSamplersFromAutomatic()
                self.uiFunc_updateControlNetPreprocessorsMenu()
                self.uiFunc_updateControlNetModelsFromAutomatic()
                self.loadOptions()

    def uiFunc_addPositionMatte(self, alphaConnection):
        _str_func = 'uiFunc_addPositionMatte'
        baseObj = self.uiTextField_baseObject(query=True, text=True)
        xyzFile = self.getXYZFile(baseObj)

        log.debug ("operating on {}, xyz = {}, connection = {}".format(baseObj, xyzFile, alphaConnection))

        if not xyzFile:
            return
        
        remap, mult = rt.remapAndMultiplyColorChannels(xyzFile, labels=['X', 'Y', 'Z'])
        connections = mc.listConnections(alphaConnection, p=True)
        if connections:
            log.debug("connections = {}".format(connections))
            finalMult = mc.shadingNode('multiplyDivide', asUtility=True)
            log.debug("finalMult = {}".format(finalMult))
            mc.connectAttr(connections[0], finalMult + '.input1X', f=True)
            mc.connectAttr(mult + '.outputX', finalMult + '.input2X', f=True)
            mc.connectAttr(finalMult + '.outputX', alphaConnection, f=True)
        else:
            mc.connectAttr(mult + '.outputX', alphaConnection, f=True)
        
        self.uiFunc_refreshEditTab()

    #=============================================================================================================
    #>> XYZ File
    #=============================================================================================================
    def getXYZFile(self, mesh):
        if not mc.objExists(mesh + '.cgmXYZFile'):
            return None
        
        xyzFile = mc.listConnections(mesh + '.cgmXYZFile', type='file')
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

    #=============================================================================================================
    #>> UI Funcs -- Edit Tab
    #=============================================================================================================
    def uiFunc_refreshEditTab(self):
        _str_func = 'uiFunc_refreshEditTab'

        self.editColumn.clear()
        self.editColumn = self.buildColumn_edit(None, inside=self.editColumn)
    
    def uiFunc_updateChannelGradient(self, dragControl, dropControl, messages, x, y, dragType):
        log.debug("updateChannelGradient", dragControl, dropControl, messages, x, y, dragType)
    
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

    #=============================================================================================================
    #>> UI Funcs -- Project Tab
    #=============================================================================================================
    def uiFunc_changeAutomatic1111Url(self):
        _str_func = 'uiFunc_changeAutomatic1111Url'
        
        log.debug(_str_func, 'start')
        self.saveOption('automatic_url', self.uiTextField_automaticURL(query=True, text=True))

        self.handleReset()

    def uiFunc_setImg2ImgPass(self, *a):
        _str_func = 'uiFunc_setImg2ImgPass'
        log.debug("%s %s", _str_func, a)

        option = a[0].lower()
        val = option != 'none'

        self.img2imgLayout(e=True, vis=val)

        self.customImage_row(e=True, vis=option == 'custom')
        self.renderLayer_row(e=True, vis=option == 'render layer')
        self.uiAlphaMatteCB(e=True, en=val)

        self.saveOption('img2imgPass', a[0])

    def uiFunc_setAlphaMatteCB(self, *a):
        _str_func = 'uiFunc_setAlphaMatteCB'
        log.debug("%s %s", _str_func, a)

        val = a[0]

        self.alphaMatteLayout(e=True, vis=val)

        self.saveOption('use_alpha_pass', val)

    def uiFunc_auto_populate_fields(self):
        _str_func = 'uiFunc_auto_populate_fields'

        self.uiFunc_loadAllMeshes()

        for cam in mc.ls("*.cgmCamera"):
            if(mc.getAttr(cam) == 'projection'):
                self.uiTextField_projectionCamera(edit=True, text=cam.split('.')[0])
                break

        for shader in mc.ls("*.cgmShader"):
            if(mc.getAttr(shader) == 'sd_projection'):
                self.uiTextField_projectionShader(edit=True, text=shader.split('.')[0])
                continue
            if(mc.getAttr(shader) == 'sd_alpha'):
                self.uiTextField_alphaProjectionShader(edit=True, text=shader.split('.')[0])
                continue
            if(mc.getAttr(shader) == 'sd_depth'):
                self.uiTextField_depthShader(edit=True, text=shader.split('.')[0])
                continue

    def uiFunc_getMaterial(self, materialType, mesh=None):
        _str_func = 'uiFunc_getMaterial'

        if materialType == 'projection':
            return self.uiTextField_projectionShader(query=True, text=True)
        if materialType == 'alphaProjection':
            return self.uiTextField_alphaProjectionShader(query=True, text=True)
        if materialType == 'depth':
            return self.uiTextField_depthShader(query=True, text=True)
        
        if not mesh or not mc.objExists(mesh):
            log.error("|{0}| >> No mesh specified.".format(_str_func))
            return None
        
        attrs = {'composite':'cgmCompositeMaterial', 'alphaMatte':'cgmAlphaMatteMaterial', 'merged':'cgmMergedMaterial', 'xyz':'cgmXYZMaterial'}
        if materialType not in attrs:
            log.error("|{0}| >> Invalid material type {1}.".format(_str_func, materialType))
            return None
        
        attr = attrs[materialType]
        if not mc.objExists(mesh + '.' + attr):
            log.error("|{0}| >> Mesh doesn't have attribute {1}.".format(_str_func, attr))
            return None
        
        return mc.listConnections(mesh + '.' + attr)[0]
        
    def uiFunc_assignMaterial(self, materialType, meshes=None):
        _str_func = 'uiFunc_assignMaterial'  

        for _mesh in meshes or self.uiList_projectionMeshes(query=True, allItems=True) or []:
            if not mc.objExists(_mesh):
                log.warning("|{0}| >> Mesh doesn't exist {1}.".format(_str_func, _mesh))
                continue
            
            _material = self.uiFunc_getMaterial(materialType)
            
            if not _material or not mc.objExists(_material):
                log.warning("|{0}| >> No material loaded - {1}.".format(_str_func, _mesh))
                continue
            
            _sg = mc.listConnections(_material, type='shadingEngine')
            if _sg:
                _sg = _sg[0]
            
            log.debug("Assigning {0} to {1}".format(_material, _mesh))
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

        projectionCam = self.uiTextField_projectionCamera(q=True, text=True)
        if projectionCam:
            mc.setAttr( '%s.horizontalFilmAperture' % projectionCam, aspectRatio )
            mc.setAttr( '%s.verticalFilmAperture' % projectionCam, 1.0 )

        self.saveOption('width', width)
        self.saveOption('height', height)

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

        outputImage = rt.renderMaterialPass(camera = self.uiTextField_projectionCamera(q=True, text=True), resolution = self.resolution  )
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
        log.debug(_str_func, path)

        if os.path.exists(path):
            iv.ui([path], {'outputImage':path})
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))
            return

    def uiFunc_snapCameraFromData(self, cameraData):
        _str_func = 'uiFunc_snapCameraFromData'

        camera = self.uiTextField_projectionCamera(query=True, text=True)
        if not mc.objExists(camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            return

        if not cameraData:
            log.error("|{0}| >> No camera data loaded.".format(_str_func))
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
        self.uiTextField_projectionCamera(edit=True, text=shape)

        return shape

    def uiFunc_make_projection_shader(self):
        _str_func = 'uiFunc_make_projection_shader'
        _camera = self.uiTextField_projectionCamera(query=True, text=True)

        if not mc.objExists(_camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            return
        
        shader, sg = rt.makeProjectionShader(_camera)
        self.uiTextField_projectionShader(edit=True, text=shader)

        return shader, sg

    def uiFunc_make_alpha_projection_shader(self):
        _str_func = 'uiFunc_make_alpha_projection_shader'
        _camera = self.uiTextField_projectionCamera(query=True, text=True)

        if not mc.objExists(_camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            return
        
        shader, sg = rt.makeAlphaProjectionShader(_camera)

        depthShader = self.uiTextField_depthShader(query=True, text=True)
        if mc.objExists(depthShader):
            ramp = mc.listConnections(depthShader + '.outColor', type='ramp')
            if(ramp):
                mult = mc.listConnections(shader + '.outColorG', type='multiplyDivide')
                if(mult):
                    mc.connectAttr(ramp[0] + '.outColorG', mult[0] + '.input2Y', force=True)
                else:
                    mc.connectAttr(ramp[0] + '.outColorG', shader + '.outColorG', force=True)

        self.uiTextField_alphaProjectionShader(edit=True, text=shader)

        return shader, sg

    def uiFunc_make_depth_shader(self):
        _str_func = 'uiFunc_make_depth_shader'

        shader, sg = rt.makeDepthShader()
        self.uiTextField_depthShader(edit=True, text=shader)

        alphaShader = self.uiTextField_alphaProjectionShader(query=True, text=True)
        if mc.objExists(alphaShader):
            ramp = mc.listConnections(shader + '.outColor', type='ramp')
            if(ramp):
                mult = mc.listConnections(alphaShader + '.outColorG', type='multiplyDivide')
                if(mult):
                    mc.connectAttr(ramp[0] + '.outColorG', mult[0] + '.input2Y', force=True)
                else:
                    mc.connectAttr(ramp[0] + '.outColorG', alphaShader + '.outColorG', force=True)

        mc.setAttr(shader + '.maxDistance', self.uiFF_maxDepthDistance(query=True, value=True))

        return shader, sg

    def uiFunc_generateImage(self):
        _str_func = 'uiFunc_generateImage'

        #alphaMat = self.uiTextField_alphaMatteShader(q=True, text=True)
        #

        meshes = self.uiList_projectionMeshes(q=True, allItems=True)
        camera = self.uiTextField_projectionCamera(q=True, text=True)

        if not camera:
            log.warning("|{0}| >> No camera loaded.".format(_str_func))


            
        if meshes is None or len(meshes) == 0:
            log.warning("|{0}| >> No meshes loaded.".format(_str_func))

        bgColor = self.generateBtn(q=True, bgc=True)
        origText = self.generateBtn(q=True, label=True)
        self.generateBtn(edit=True, enable=False)
        self.generateBtn(edit=True, label='Generating...')
        self.generateBtn(edit=True, bgc=(1, 0.5, 0.5))

        mc.refresh()

        _options = self.getOptions()

        output_path = os.path.normpath(os.path.join(PROJECT.getImagePath(), 'sd_output'))

        composite_path = None
        composite_string = None

        option = _options['img2img_pass'].lower()
        log.debug("img2img_pass", option)

        if option != "none":
            if (option == "composite" or option == "merged"):
                for mesh in meshes or []:
                    wantedMat = None
                    if option == "merged":
                        wantedMat = self.uiFunc_getMaterial("merged", mesh)
                    elif option == "composite":
                        wantedMat = self.uiFunc_getMaterial("composite", mesh)
                    if wantedMat:
                        rt.assignMaterial(wantedMat, mesh)

                composite_path = rt.renderMaterialPass(camera=camera, resolution=self.resolution)

                log.debug("composite path: ", composite_path)
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
                log.debug("custom image: ", custom_image)

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
                log.debug("render layer: ", outputImage)

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

            depthMat = self.uiFunc_getMaterial("depth")

            if not mc.objExists(depthMat):
                log.warning("|{0}| >> No depth shader loaded.".format(_str_func))
                # prompt to create one
                result = mc.confirmDialog(title='No depth shader loaded', message='No depth shader loaded. Would you like to create one?', button=['Yes', 'No'], defaultButton='Yes', cancelButton='No', dismissString='No')
                if result == 'Yes':
                    depthMat, sg = self.uiFunc_make_depth_shader()

            if mc.objExists(depthMat) and meshes:
                format = 'png'
                for mesh in meshes or []:
                    wantedMat = self.uiFunc_getMaterial("depth", mesh)
                    if wantedMat:
                        rt.assignMaterial(wantedMat, mesh)

                depth_path = rt.renderMaterialPass(fileName = "DepthPass", camera=camera, resolution=self.resolution)

                log.debug( "depth_path: {0}".format(depth_path) )
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
                log.warning("|{0}| >> No depth shader loaded. Disabling Control Net".format(_str_func))
                _options['control_net_enabled'] = False
        else:
            if not composite_string:
                for mesh in meshes or []:
                    wantedMat = None
                    if option == "merged":
                        wantedMat = self.uiFunc_getMaterial("merged", mesh)
                    elif option == "composite":
                        wantedMat = self.uiFunc_getMaterial("composite", mesh)
                    if wantedMat:
                        rt.assignMaterial(wantedMat, mesh)

                composite_path = rt.renderMaterialPass(fileName = "CompositePass", camera=camera, resolution=self.resolution)

                with open(composite_path, "rb") as c:
                    # Read the image data
                    composite_data = c.read()
                    
                    # Encode the image data as base64
                    composite_base64 = base64.b64encode(composite_data)
                    
                    # Convert the base64 bytes to string
                    composite_string = composite_base64.decode("utf-8")
            
            _options['control_net_image'] = composite_string
        
        if _options['use_alpha_pass'] and _options['img2img_pass'] != 'none' and meshes:
            for mesh in meshes or []:
                wantedMat = self.uiFunc_getMaterial("alphaMatte", mesh)
                if wantedMat:
                    rt.assignMaterial(wantedMat, mesh)

            alpha_path = rt.renderMaterialPass(fileName = "AlphaPass", camera=camera, resolution=self.resolution)

            log.debug ("alpha_path: {0}".format(alpha_path))

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

        if camera:
            cameraTransform = mc.listRelatives(camera, parent=True)[0]
            info['camera_info'] = {'position':mc.xform(cameraTransform, q=True, ws=True, t=True),
                'rotation' : mc.xform(cameraTransform, q=True, ws=True, ro=True),
                'fov' : mc.getAttr(camera + '.focalLength')}

        log.debug("Generated: ", imagePaths, info)

        if(imagePaths):
            callbacks = []
            callbacks.append(
                {'label':'Make Plane', 
                 'function':rt.makeImagePlane})
            callbacks.append(
                {'label':'Set As Projection', 
                 'function':self.assignImageToProjection})

            displayImage(imagePaths, info, callbacks)
        
        self.lastInfo = info

        self.generateBtn(edit=True, enable=True)
        self.generateBtn(edit=True, label=origText)
        self.generateBtn(edit=True, bgc=bgColor)
     
    def uiFunc_loadSelectedMeshes(self):
        _str_func = 'uiFunc_loadSelectedMeshes'
        log.debug("|{0}| >> ...".format(_str_func))

        sel = mc.ls(sl=True)

        unvalidatedMeshes = []
        validatedMeshes = []

        for obj in mc.ls(sl=True):
            shape = mc.listRelatives(obj, shapes=True, type='mesh')
            if shape:
                if not sd.validateProjectionMesh(shape[0]):
                    unvalidatedMeshes.append(shape[0])
                else:
                    validatedMeshes.append(shape[0])
            else:
                log.warning("|{0}| >> No shape found for {1}".format(_str_func, obj))
        
        if unvalidatedMeshes:
            log.debug(unvalidatedMeshes)
            # make a confirm dialog prompt that asks if the user wants to validate the meshes
            result = mc.confirmDialog(title='Validate Meshes', message='The following meshes are not valid for projection. Would you like to validate them?\n\n{0}'.format('\n'.join(unvalidatedMeshes)), button=['Yes', 'No'], defaultButton='Yes', cancelButton='No', dismissString='No')
            if result == 'Yes':
                sd.initializeProjectionMeshes(unvalidatedMeshes)
                # append the newly validated meshes to the validatedMeshes list
                validatedMeshes.extend(unvalidatedMeshes)
        
        if validatedMeshes:
            self.uiList_projectionMeshes(edit=True, append=validatedMeshes)
        
    def uiFunc_loadAllMeshes(self):
        _str_func = 'uiFunc_loadAllMeshes'
        log.debug("|{0}| >> ...".format(_str_func))

        self.uiList_projectionMeshes.clear()

        # find all instances of objects with the relevant attributes
        unvalidatedMeshes = []
        validatedMeshes = []

        for shape in [x.split('.')[0] for x in mc.ls('*.cgmCompositeMaterial')]:
            if shape in unvalidatedMeshes or shape in validatedMeshes:
                continue

            if not sd.validateProjectionMesh(shape):
                unvalidatedMeshes.append(shape)
            else:
                validatedMeshes.append(shape)  
        
        if validatedMeshes:
            self.uiList_projectionMeshes(edit=True, append=validatedMeshes)

    def uiFunc_clearAllMeshes(self):
        _str_func = 'uiFunc_clearAllMeshes'
        log.debug("|{0}| >> ...".format(_str_func))
        self.uiList_projectionMeshes.clear()

    def uiFunc_removeSelectedMeshes(self):
        _str_func = 'uiFunc_removeSelectedMeshes'
        log.debug("|{0}| >> ...".format(_str_func))

        sel = self.uiList_projectionMeshes(query=True, selectItem=True)
        self.uiList_projectionMeshes(edit=True, removeItem=sel)

    def uiFunc_selectMeshes(self):
        _str_func = 'uiFunc_selectMeshes'
        log.debug("|{0}| >> ...".format(_str_func))

        sel = self.uiList_projectionMeshes(query=True, selectItem=True)
        mc.select(sel)

    #===========================================================================
    # Image Viewer Callbacks
    #===========================================================================
    def assignImageToProjection(self, imagePath, info):
        _str_func = 'assignImageToProjection'

        projectionShader = self.uiTextField_projectionShader(query=True, text=True)
        projectionCamera = self.uiTextField_projectionCamera(query=True, text=True)

        if not mc.objExists(projectionShader) or not mc.objExists(projectionCamera):
            _str = "Some items have not been set up. Missing:\n"
            if not mc.objExists(projectionCamera):
                _str += "Projection Camera\n"
            if not mc.objExists(projectionShader):
                _str += "Projection Shader\n"
            _str += "Would you like to create them?"

            # create a confirm dialog prompt that asks if the user wants to create the shader
            result = mc.confirmDialog(title='Missing Items', message=_str, button=['Yes', 'No'], defaultButton='Yes', cancelButton='No', dismissString='No')
            if result == 'Yes':
                if not mc.objExists(projectionCamera):
                    projectionCamera = self.uiFunc_make_projection_camera()
                if not mc.objExists(projectionShader):
                    projectionShader, sg = self.uiFunc_make_projection_shader()
            else:
                log.error("|{0}| >> No projection shader to assign image to".format(_str_func))
                return

        # assign projection shader
        self.uiFunc_assignMaterial("projection")
        rt.assignImageToProjectionShader(projectionShader, imagePath, info)        

    def uiFunc_bakeProjection(self):
        #self.assignImageToProjection(imagePath, info)
        mesh = self.uiTextField_baseObject(query=True, text=True)
        projectionShader = self.uiTextField_projectionShader(query=True, text=True)
        alphaShader = self.uiTextField_alphaProjectionShader(query=True, text=True)

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
        self.uiFunc_assignMaterial("composite")

    def uiFunc_mergeComposite(self):
        compositeShader = self.uiTextField_compositeShader(query=True, text=True)
        mergedShader = self.uiTextField_mergedShader(query=True, text=True)
      
        sd.mergeCompositeShaderToImage(compositeShader, mergedShader)

        # assign merged shader
        self.uiFunc_assignMaterial("composite")
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
        
        self.saveOption('min_depth_distance', _minDepth)
        self.saveOption('max_depth_distance', _maxDepth)

    def uiFunc_setSamples(self, source):

        val = uiFunc_setFieldSlider(self.uiIF_samplingSteps, self.uiSlider_samplingSteps, source, 100)
        
        self.saveOption('sampling_steps', val)

    def uiFunc_load_custom_image(self):
        _str_func = 'uiFunc_load_custom_image'

        _file = mc.fileDialog2(fileMode=1, caption='Select Image File', fileFilter='*.jpg *.jpeg *.png')
        if _file:
            _file = _file[0]
            if not os.path.exists(_file):
                log.error("|{0}| >> File not found: {1}".format(_str_func, _file))
                return False

            self.uiTextField_customImage(edit=True, text=_file)
            self.saveOption('img2img_custom_image', _file)

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
        val = uiFunc_setFieldSlider(self.uiFF_denoiseStrength, self.uiSlider_denoiseStrength, source, 1.0, .01)
        
        self.saveOption('denoising_strength', val)

    def uiFunc_setBatchCount(self, source):
        val = uiFunc_setFieldSlider(self.uiIF_batchCount, self.uiSlider_batchCount, source, 10)
        
        self.saveOption('batch_count', val)

    def uiFunc_setBatchSize(self, source):
        val = uiFunc_setFieldSlider(self.uiIF_batchSize, self.uiSlider_batchSize, source, 8)
        
        self.saveOption('batch_size', val)
        
    def uiFunc_setCFGScale(self, source):
        val = uiFunc_setFieldSlider(self.uiIF_CFGScale, self.uiSlider_CFGScale, source, 30)
        
        self.saveOption('cfg_scale', val)

    def uiFunc_setMaskBlur(self, source):
        val = uiFunc_setFieldSlider(self.uiIF_maskBlur, self.uiSlider_maskBlur, source, 100, 1)
        
        self.saveOption('mask_blur', val)

    def uiFunc_updateModelsFromAutomatic(self):
        _str_func = 'uiFunc_updateModelsFromAutomatic'

        if not self.connected:
            return []

        url = self.uiTextField_automaticURL(query=True, text=True)
        
        self.models = sd.getModelsFromAutomatic(url)
        if not self.models:
            self.uiFunc_setConnected(False)
            return []
        
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

        if not self.connected:
            return []

        url = self.uiTextField_automaticURL(query=True, text=True)
        
        _samplers = sd.getSamplersFromAutomatic1111()

        if not _samplers:
            self.uiFunc_setConnected(False)
            return []

        self.uiOM_samplingMethodMenu.clear()
        for sampler in _samplers:
            # if model is a string, continue
            self.uiOM_samplingMethodMenu.append(sampler['name'])

        return _samplers

    def uiFunc_updateControlNetPreprocessorsMenu(self):
        _str_func = 'uiFunc_updateControlNetPreprocessorsMenu'
        
        _preprocessors = sd.getControlNetPreprocessorsFromAutomatic1111()

        if not _preprocessors:
            self.uiFunc_setConnected(False)
            return []

        self.uiOM_ControlNetPreprocessorMenu.clear()
        for _preprocessor in _preprocessors:
            self.uiOM_ControlNetPreprocessorMenu.append(_preprocessor)

        return _preprocessors

    def uiFunc_changeControlNetPreProcessor(self, arg):
        _str_func = 'uiFunc_changeControlNetPreProcessor'

        self.uiFunc_updateControlNetModelsFromAutomatic()

        log.debug("|{0}| >> arg: {1}".format(_str_func, arg))
        self.saveOption('control_net_preprocessor', arg)
        self.saveOptionFromUI('control_net_model', self.uiOM_ControlNetModelMenu)

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
        val = uiFunc_setFieldSlider(self.uiFF_controlNetWeight,self.uiSlider_controlNetWeight, source, 1.0, .1)
        
        self.saveOption('control_net_weight', val)

    def uiFunc_setControlNetGuidanceStart(self, source):
        val = uiFunc_setFieldSlider(self.uiFF_controlNetGuidanceStart,self.uiSlider_controlNetGuidanceStart, source, 1.0, .1)
        
        self.saveOption('control_net_guidance_start', val)

    def uiFunc_setControlNetGuidanceEnd(self, source):
        val = uiFunc_setFieldSlider(self.uiFF_controlNetGuidanceEnd,self.uiSlider_controlNetGuidanceEnd, source, 1.0, .1)
        self.saveOption('control_net_guidance_end', val)

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
        return self.uiTextField_alphaProjectionShader(q=True, tx=True)

    def getProjectionShader(self):
        _str_func = 'getProjectionShader'
        return self.uiTextField_projectionShader(q=True, tx=True)
    
    def getOptions(self):
        _str_func = 'getOptions'
        
        _options = {}
        _options['automatic_url'] = self.uiTextField_automaticURL.getValue()
        _options['prompt'] = self.uiTextField_prompt.getValue()
        _options['negative_prompt'] = self.uiTextField_negativePrompt.getValue()
        _options['seed'] = self.uiIF_Seed.getValue()
        _options['width'] = self.uiIF_Width.getValue()
        _options['height'] = self.uiIF_Height.getValue()
        _options['sampling_method'] = self.uiOM_samplingMethodMenu.getValue()
        _options['sampling_steps'] = self.uiIF_samplingSteps.getValue()
        _options['min_depth_distance'] = self.uiFF_minDepthDistance.getValue()
        _options['max_depth_distance'] = self.uiFF_maxDepthDistance.getValue()
        _options['control_net_enabled'] = self.uiControlNetEnabledCB.getValue()
        _options['control_net_low_v_ram'] = self.uiControlNetLowVRamCB.getValue()
        _options['control_net_preprocessor'] = self.uiOM_ControlNetPreprocessorMenu.getValue()
        _options['control_net_model'] = self.uiOM_ControlNetModelMenu.getValue()
        _options['control_net_weight'] = self.uiFF_controlNetWeight.getValue()
        _options['control_net_guidance_start'] = self.uiFF_controlNetGuidanceStart.getValue()
        _options['control_net_guidance_end'] = self.uiFF_controlNetGuidanceEnd.getValue()
        _options['denoising_strength'] = self.uiFF_denoiseStrength.getValue()
        _options['img2img_pass'] = self.uiOM_passMenu.getValue()
        _options['img2img_custom_image'] = self.uiTextField_customImage.getValue()
        _options['use_alpha_pass'] = self.uiAlphaMatteCB.getValue()
        _options['mask_blur'] = self.uiIF_maskBlur.getValue()
        _options['batch_count'] = self.uiIF_batchCount.getValue()
        _options['batch_size'] = self.uiIF_batchSize.getValue()
        _options['cfg_scale'] = self.uiIF_CFGScale.getValue()

        return _options

    def saveOptionFromUI(self, option, element):
        _str_func = 'saveOptionFromUI'

        log.debug("|{0}| >> option: {1} | element: {2} | value: {3}".format(_str_func, option, element, element.getValue()))

        if not self._initialized:
            return

        _options = json.loads(self.config.getValue())
        _options[option] = element.getValue()
        self.config.setValue(json.dumps(_options))

    def saveOption(self, option, value):
        _str_func = 'saveOption'

        if not self._initialized:
            return

        log.debug("|{0}| >> option: {1} | value: {2}".format(_str_func, option, value))

        _options = json.loads(self.config.getValue())
        _options[option] = value
        self.config.setValue(json.dumps(_options))

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

        log.debug("saving", _options)
    
    def loadOptions(self, options=None):
        _str_func = 'loadOptions'

        log.debug("|{0}| >> ...".format(_str_func))

        mc.refresh()

        if not self._initialized:
            return

        _options = {}
        if(options):
            _options = options
        else:           
            _options = json.loads(self.config.getValue()) if self.config.getValue() else _defaultOptions

        log.debug("|{0}| >> loaded _options: {1}".format(_str_func,_options))

        # go through options and set default if not found
        for key in _defaultOptions:
            if key not in _options:
                _options[key] = _defaultOptions[key]
                log.debug("|{0}| >> key not found: {1} setting to default: {2}".format(_str_func,key,_defaultOptions[key]))

        # load model from automatic
        sdModels = sd.getModelsFromAutomatic1111(_options['automatic_url'])
        sdOptions = sd.getOptionsFromAutomatic(_options['automatic_url'])

        if self.uiOM_modelMenu and sdModels and sdOptions:
            for model in sdModels:
                if(model['title'] == sdOptions['sd_model_checkpoint']):
                    self.uiOM_modelMenu(edit=True, value=model['model_name'])
                    break

        # iterate through options dict and set default from self._defaultOptions if not found
        for key in _defaultOptions:
            if key not in _options:
                log.warning("|{0}| >> key not found: {1} setting to default: {2}".format(_str_func,key,_defaultOptions[key]))
                _options[key] = _defaultOptions[key]

        self.uiTextField_automaticURL(edit=True, text=_options['automatic_url'])
        self.uiTextField_prompt(edit=True, text=_options['prompt'])
        self.uiTextField_negativePrompt(edit=True, text=_options['negative_prompt'])
        self.uiIF_Seed.setValue(int(_options['seed']))
        log.debug("Seed is: %s", str(_options['seed']) if 'seed' in _options else "No Seed Option")
        self.uiIF_Width(edit=True, v=_options['width'])
        self.uiIF_Height(edit=True, v=_options['height'])           
        if 'sampling_method' in _options:
            # get options from menu
            _samplingMethodMenu = self.uiOM_samplingMethodMenu(query=True, itemListLong=True) or []
            for item in _samplingMethodMenu:
                if mc.menuItem(item, q=True, label=True) == _options['sampling_method']:
                    self.uiOM_samplingMethodMenu(edit=True, value=_options['sampling_method'])
                    break
        else:
            log.warning("|{0}| >> Failed to find sampling method in options".format(_str_func))

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
        
        if 'control_net_preprocessor' in _options:
            _controlNetPreprocessors = self.uiOM_ControlNetPreprocessorMenu(query=True, itemListLong=True) or []
            for item in _controlNetPreprocessors:
                if mc.menuItem(item, q=True, label=True) == _options['control_net_preprocessor']:
                    self.uiOM_ControlNetPreprocessorMenu(edit=True, value=_options['control_net_preprocessor'])
                    break

        if 'control_net_model' in _options:
            _controlNetModels = self.uiOM_ControlNetModelMenu(query=True, itemListLong=True) or []
            for item in _controlNetModels:
                if mc.menuItem(item, q=True, label=True) == _options['control_net_model']:
                    self.uiOM_ControlNetModelMenu(edit=True, value=_options['control_net_model'])
                    break
        else:
            log.warning("|{0}| >> Failed to find control net model in options".format(_str_func))

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

        if not sdModels:
            self.projectColumn(edit=True, enable=False)
    
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
    
    return _value

def displayImage(imagePaths, data = {}, callbackData = []):
    log.debug("Displaying images: ", imagePaths)
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
    log.debug( "uiFunc_updateChannelGradient", dragControl, dropControl, messages, x, y, dragType)