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
import traceback
from PIL import Image, ImageFilter
from io import BytesIO
import tempfile
import threading
import pprint

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI

mUI = cgmUI.mUI

from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
import cgm.core.tools.Project as PROJECT
import cgm.core.cgmPy.validateArgs as VALID

from functools import partial
from cgm.core.tools.stableDiffusion import stableDiffusionTools as sd
from cgm.core.tools.stableDiffusion import renderTools as rt
from cgm.core.tools.stableDiffusion import generateImage as gi
from cgm.core.tools import imageViewer as iv
from cgm.core.tools import imageTools as it
from cgm.lib import dictionary

# >>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ = "GrAIBox"

_defaultOptions = {
    "automatic_url": "127.0.0.1:7860",
    "prompt": "",
    "negative_prompt": "",
    "seed": -1,
    "width": 512,
    "height": 512,
    "bake_width":2048,
    "bake_height":2048,
    "sampling_steps": 5,
    "min_depth_distance": 0.0,
    "max_depth_distance": 30.0,
    "sampling_method": "Euler",
    "denoising_strength": 0.35,
    #'use_composite_pass':False,
    "img2img_scale_multiplier": 1,
    "img2img_pass": "none",
    "img2img_custom_image": "",
    "img2img_render_layer": "defaultRenderLayer",
    "use_alpha_pass": False,
    "mask_blur": 4,
    "batch_count": 1,
    "batch_size": 1,
    "batch_mode": "None",
    "cfg_scale": 7,
    "auto_depth_enabled": True,
    "control_nets":[
        {
            "control_net_enabled": True,
            "control_net_low_v_ram": False,
            "control_net_preprocessor": "none",
            "control_net_model": "none",
            "control_net_weight": 1.0,
            "control_net_guidance_start": 0.0,
            "control_net_guidance_end": 1.0,
            "control_net_noise": 0.0,
            "control_net_custom_image_path": "",
        },
        {
            "control_net_enabled": False,
            "control_net_low_v_ram": False,
            "control_net_preprocessor": "none",
            "control_net_model": "none",
            "control_net_weight": 1.0,
            "control_net_guidance_start": 0.0,
            "control_net_guidance_end": 1.0,
            "control_net_noise": 0.0,
            "control_net_custom_image_path": "",
        },
        {
            "control_net_enabled": False,
            "control_net_low_v_ram": False,
            "control_net_preprocessor": "none",
            "control_net_model": "none",
            "control_net_weight": 1.0,
            "control_net_guidance_start": 0.0,
            "control_net_guidance_end": 1.0,
            "control_net_noise": 0.0,
            "control_net_use_custom_image": False,
            "control_net_custom_image_path": "",
        },
        {
            "control_net_enabled": False,
            "control_net_low_v_ram": False,
            "control_net_preprocessor": "none",
            "control_net_model": "none",
            "control_net_weight": 1.0,
            "control_net_guidance_start": 0.0,
            "control_net_guidance_end": 1.0,
            "control_net_noise": 0.0,
            "control_net_use_custom_image": False,
            "control_net_custom_image_path": "",
        }
    ]
}

class ui(cgmUI.cgmGUI):
    USE_Template = "cgmUITemplate"
    WINDOW_NAME = "{0}_ui".format(__toolname__)
    WINDOW_TITLE = "{1} - {0}".format(__version__, __toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = (
        True  # always resets the size of the window when its re-created
    )
    DEFAULT_SIZE = 675, 825
    TOOLNAME = "{0}.ui".format(__toolname__)
    
    GREEN = (.6,.9,.6)
    RED = (.9,.3,.3)
    GRAY = (.45,.45,.45)

    _initialized = False

    @property
    def resolution(self):
        return (self.uiIF_Width.getValue(), self.uiIF_Height.getValue())

    def insert_init(self, *args, **kws):
        _str_func = "__init__[{0}]".format(self.__class__.TOOLNAME)
        log.info("|{0}| >>...".format(_str_func))

        if kws:
            log.debug("kws: %s" % str(kws))
        if args:
            log.debug("args: %s" % str(args))
        log.info(self.__call__(q=True, title=True))

        self.__version__ = __version__
        self.__toolName__ = self.__class__.WINDOW_NAME

        self.config = cgmMeta.cgmOptionVar("cgmVar_sdui_config", varType="string")
        self.lastConfig = cgmMeta.cgmOptionVar(
            "cgmVar_sdui_last_config", varType="string"
        )
        self.layerCopyData = cgmMeta.cgmOptionVar(
            "cgmVar_sdui_layerCopyData", varType="string"
        )
        self.lastInfo = {}
        self.editTabContent = None
        self.projectColumn = None
        self.connected = True

        self.samplingMethods = []
        self.sdModels = []
        self.controlNetModels = []
        self.controlNets = []

        self.activeProjectionMesh = None
        self.activePass = None

        # self.l_allowedDockAreas = []
        self.WINDOW_TITLE = self.__class__.WINDOW_TITLE
        self.DEFAULT_SIZE = self.__class__.DEFAULT_SIZE

    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(
            l="Setup", pmc=cgmGEN.Callback(self.buildMenu_first)
        )
        self.uiMenu_DebugMenu = mUI.MelMenu(
            l="Debug", pmc=cgmGEN.Callback(self.buildMenu_debug)
        )

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        # >>> Reset Options

        self.uiMenu_buildDock(self.uiMenu_FirstMenu)

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Load From Image",
            c=lambda *a: mc.evalDeferred(self.uiFunc_load_settings_from_image, lp=True),
        )

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Load From Image Node",
            c=lambda *a: mc.evalDeferred(self.uiFunc_load_settings_from_image_node, lp=True),
        )

        mUI.MelMenuItemDiv(self.uiMenu_FirstMenu)

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Reload",
            c=lambda *a: mc.evalDeferred(self.handleReload, lp=True),
        )

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Reset",
            c=lambda *a: mc.evalDeferred(self.handleReset, lp=True),
        )

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Clear Mesh Attributes",
            c=lambda *a: mc.evalDeferred(sd.clean_cgm_sd_tags, lp=True),
        )

    def buildMenu_debug(self):
        self.uiMenu_DebugMenu.clear()
        # >>> Reset Options

        mUI.MelMenuItem(
            self.uiMenu_DebugMenu,
            l="Clear Data",
            c=lambda *a: mc.evalDeferred(
                cgmGEN.Callback(uiFunc_debug_clearData, self), lp=True
            ),
        )

    def handleReload(self):
        self._initialized = False
        self.reload()

    def handleReset(self):
        self.config.setValue({})
        self.loadOptions()

    def uiFunc_load_settings_from_image(self):
        _str_func = "uiFunc_load_settings_from_image"

        # open file dialog
        _path = mc.fileDialog2(
            fileMode=1,
            caption="Select Image",
            fileFilter="Image Files (*.png)",
            dialogStyle=2,
        )
        if not _path:
            return
        
        # get metadata from image
        data = sd.parametersToDict(it.getPngMetadata(_path[0])['pngInfo']['parameters'])
        
        if data is None:
            return

        _options = self.getOptions()

        _options["prompt"] = data["Prompt"] if "Prompt" in data else ""
        _options["negative_prompt"] = data["Negative prompt"] if "Negative prompt" in data else ""
        _options["seed"] = data["Seed"] if "Seed" in data else -1
        if "Size" in data:
            _options["width"], _options["height"] = [int(x) for x in data["Size"].split("x")]

        if "Steps" in data:
            _options["sampling_steps"] = data["Steps"]
        if "Sampler" in data:
            _options["sampling_method"] = data["Sampler"]
        if "Model" in data:
            _options["cfg_scale"] = data["CFG scale"]

        for i in range(4):
            _options["control_nets"][i]["control_net_enabled"] = False
        
        for key, value in data.items():
            if key.startswith("ControlNet"):
                idx = int(key[-1])
                _options["control_nets"][idx]["control_net_enabled"] = True
                if "model" in data[key]:
                    _options["control_nets"][idx]["control_net_model"] = data[key]["model"]
                if "preprocessor" in data[key]:
                    _options["control_nets"][idx]["control_net_preprocessor"] = data[key]["preprocessor"]
                if "weight" in data[key]:
                    _options["control_nets"][idx]["control_net_weight"] = data[key]["weight"]
                if "starting/ending" in data[key]:
                    _options["control_nets"][idx]["control_net_guidance_start"] = data[key]["starting/ending"][0]
                    _options["control_nets"][idx]["control_net_guidance_end"] = data[key]["starting/ending"][1]

        self.config.setValue(json.dumps(_options))

        self.loadOptions(_options)

    def uiFunc_load_settings_from_image_node(self):
        fileNodes = mc.ls(sl=True, type="file")
        if len(fileNodes) == 0:
            return

        fileNode = fileNodes[0]

        data = sd.load_settings_from_image(fileNode)

        if data is None:
            return

        _options = self.getOptions()

        _options["prompt"] = data["prompt"]
        _options["negative_prompt"] = data["negative_prompt"]
        _options["seed"] = data["seed"]
        _options["width"] = data["width"]
        _options["height"] = data["height"]
        _options["sampling_steps"] = data["steps"]
        _options["control_net_enabled"] = (
            data["extra_generation_params"]["ControlNet Enabled"]
            if "ControlNet Enabled" in data["extra_generation_params"]
            else False
        )
        _options["control_net_low_v_ram"] = False
        _options["control_net_preprocessor"] = (
            data["extra_generation_params"]["ControlNet Module"]
            if "ControlNet Module" in data["extra_generation_params"]
            else "none"
        )
        _options["control_net_weight"] = (
            data["extra_generation_params"]["ControlNet Weight"]
            if "ControlNet Weight" in data["extra_generation_params"]
            else 1
        )
        _options["control_net_guidance_start"] = (
            data["extra_generation_params"]["ControlNet Guidance Start"]
            if "ControlNet Guidance Start" in data["extra_generation_params"]
            else 0
        )
        _options["control_net_guidance_end"] = (
            data["extra_generation_params"]["ControlNet Guidance End"]
            if "ControlNet Guidance End" in data["extra_generation_params"]
            else 1
        )
        _options["sampling_method"] = data["sampler_name"]

        self.config.setValue(json.dumps(_options))

        self.loadOptions(_options)

    def build_layoutWrapper(self, parent):
        _str_func = "build_layoutWrapper"
        # self._d_uiCheckBoxes = {}

        # _MainForm = mUI.MelFormLayout(parent,ut='cgmUISubTemplate')
        _MainForm = mUI.MelFormLayout(self, ut="cgmUITemplate")
        _column = self.buildColumn_main(_MainForm, True)

        _row_cgm = cgmUI.add_cgmFooter(_MainForm)
        _MainForm(
            edit=True,
            af=[
                (_column, "top", 0),
                (_column, "left", 0),
                (_column, "right", 0),
                (_row_cgm, "left", 0),
                (_row_cgm, "right", 0),
                (_row_cgm, "bottom", 0),
            ],
            ac=[
                (_column, "bottom", 2, _row_cgm),
            ],
            attachNone=[(_row_cgm, "top")],
        )

        self._initialized = True

        self.uiFunc_tryAutomatic1111Connect()
        # self.loadOptions()

    def buildColumn_main(self, parent, asScroll=False):
        self.uiTabLayout = mc.tabLayout()

        self.setupColumn = self.buildColumn_settings(self.uiTabLayout, asScroll=True)
        self.projectColumn = self.buildColumn_project(self.uiTabLayout, asScroll=True)
        self.editColumn = self.buildColumn_edit(self.uiTabLayout, asScroll=True)

        mc.tabLayout(
            self.uiTabLayout,
            edit=True,
            tabLabel=(
                (self.setupColumn, "Setup"),
                (self.projectColumn, "Project"),
                (self.editColumn, "Edit"),
            ),
            cc=lambda *a: mc.evalDeferred(
                cgmGEN.Callback(self.uiFunc_handleTabChange), lp=True
            ),
        )

        return self.uiTabLayout

    # =============================================================================================================
    # >> Settings Column
    # =============================================================================================================
    def buildColumn_settings(self, parent, asScroll=False):
        """
        Trying to put all this in here so it's insertable in other uis

        """
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        cgmUI.add_Header("Setup")

        _help = mUI.MelLabel(
            _inside,
            bgc=dictionary.returnStateColor("help"),
            align="center",
            label="Set up the required materials for your projections",
            h=20,
            vis=False,
        )

        self.l_helpElements.append(_help)

        mUI.MelSpacer(_inside, w=5, h=7)

        mUI.MelLabel(_inside, align="center", label="Projection Meshes", h=20)

        self.uiList_projectionMeshes = mUI.MelObjectScrollList(
            _inside,
            ut="cgmUITemplate",
            allowMultiSelection=True,
            h=100,
            dcc=self.uiFunc_selectMeshes,
        )

        try:
            _str_section = "Projection Mesh Targets Row"
            _uiRow_meshSplitterTargets = mUI.MelHLayout(_inside, padding=1)
            cgmUI.add_Button(
                _uiRow_meshSplitterTargets,
                "Load Selected",
                lambda *a: self.uiFunc_loadSelectedMeshes(),
                annotationText="Load materials from selected objects",
            )
            cgmUI.add_Button(
                _uiRow_meshSplitterTargets,
                "Load All",
                lambda *a: self.uiFunc_loadAllMeshes(),
                annotationText="Load all materials from scene",
            )
            cgmUI.add_Button(
                _uiRow_meshSplitterTargets,
                "Remove Selected",
                lambda *a: self.uiFunc_removeSelectedMeshes(),
                annotationText="Remove all materials from list",
            )
            cgmUI.add_Button(
                _uiRow_meshSplitterTargets,
                "Clear All",
                lambda *a: self.uiFunc_clearAllMeshes(),
                annotationText="Remove all materials from list",
            )
            _uiRow_meshSplitterTargets.layout()
        except Exception as err:
            log.error(
                "{0} {1} failed to load. err: {2}".format(
                    self._str_reportStart, _str_section, err
                )
            )

        # >>> Mesh Load
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
        # cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_loadTextFieldWithShape(self.uiTextField_baseObject, enforcedType='mesh'))
        # cgmUI.add_Button(_row, 'Select',
        #                     lambda *a:uiFunc_selectItemFromTextField(self.uiTextField_baseObject),
        #                     annotationText='')
        # mUI.MelSpacer(_row,w = 5)
        # _row.layout()

        # >>> Load Projection Camera
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Projection Cam:", align="right")
        self.uiTextField_projectionCamera = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=False,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_projectionCamera)
        cgmUI.add_Button(
            _row,
            "<<",
            lambda *a: uiFunc_loadTextFieldWithShape(
                self.uiTextField_projectionCamera, enforcedType="camera"
            ),
        )
        cgmUI.add_Button(
            _row,
            "Make",
            lambda *a: self.uiFunc_makeProjectionCamera(),
            annotationText="Make a projection camera",
        )
        cgmUI.add_Button(
            _row,
            "Select",
            lambda *a: uiFunc_selectItemFromTextField(
                self.uiTextField_projectionCamera
            ),
            annotationText="",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Load Projection Shader
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Projection Shader:", align="right")
        self.uiTextField_projectionShader = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=False,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_projectionShader)
        cgmUI.add_Button(
            _row,
            "<<",
            lambda *a: uiFunc_loadTextFieldWithSelected(
                self.uiTextField_projectionShader, enforcedType="surfaceShader"
            ),
        )
        cgmUI.add_Button(
            _row,
            "Make",
            lambda *a: self.uiFunc_makeProjectionShader(),
            annotationText="Make a projection shader",
        )
        cgmUI.add_Button(
            _row,
            "Select",
            lambda *a: uiFunc_selectItemFromTextField(
                self.uiTextField_projectionShader
            ),
            annotationText="",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Load Alpha Projection Shader
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Alpha Projection Shader:", align="right")
        self.uiTextField_alphaProjectionShader = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=False,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_alphaProjectionShader)
        cgmUI.add_Button(
            _row,
            "<<",
            lambda *a: uiFunc_loadTextFieldWithSelected(
                self.uiTextField_alphaProjectionShader, enforcedType="surfaceShader"
            ),
        )
        cgmUI.add_Button(
            _row,
            "Make",
            lambda *a: self.uiFunc_makeAlphaProjectionShader(),
            annotationText="",
        )
        cgmUI.add_Button(
            _row,
            "Select",
            lambda *a: uiFunc_selectItemFromTextField(
                self.uiTextField_alphaProjectionShader
            ),
            annotationText="",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Load Depth  Shader
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Depth Shader:", align="right")
        self.uiTextField_depthShader = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=False,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_depthShader)
        cgmUI.add_Button(
            _row,
            "<<",
            lambda *a: uiFunc_loadTextFieldWithSelected(
                self.uiTextField_depthShader, enforcedType="surfaceShader"
            ),
        )
        cgmUI.add_Button(
            _row, "Make", lambda *a: self.uiFunc_makeDepthShader(), annotationText=""
        )
        cgmUI.add_Button(
            _row,
            "Select",
            lambda *a: uiFunc_selectItemFromTextField(self.uiTextField_depthShader),
            annotationText="",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Load Normal Shader
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Normal Shader:", align="right")
        self.uiTextField_normalShader = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=False,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_normalShader)
        cgmUI.add_Button(
            _row,
            "<<",
            lambda *a: uiFunc_loadTextFieldWithSelected(
                self.uiTextField_normalShader, enforcedType="surfaceShader"
            ),
        )
        cgmUI.add_Button(
            _row, "Make", lambda *a: self.uiFunc_makeNormalShader(), annotationText=""
        )
        cgmUI.add_Button(
            _row,
            "Select",
            lambda *a: uiFunc_selectItemFromTextField(self.uiTextField_normalShader),
            annotationText="",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Refresh
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        _refreshButton = cgmUI.add_Button(
            _row, "Refresh From Scene", lambda *a: self.uiFunc_auto_populate_fields(), annotationText=""
        )
        _row.setStretchWidget(_refreshButton)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Automatic1111 Info
        mc.setParent(_inside)
        cgmUI.add_Header("Automatic1111 Settings")

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="URL:", align="right")

        _options = json.loads(self.config.getValue() or "{}")

        self.uiTextField_automaticURL = mUI.MelTextField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=True,
            text=_options["automatic_url"]
            if "automatic_url" in _options.keys()
            else "127.0.0.1:7860",
            cc=lambda *a: self.uiFunc_changeAutomatic1111Url(),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(_row, w=5)
        self.urlBtn = cgmUI.add_Button(
            _row,
            "Retry Connection",
            lambda *a: self.uiFunc_tryAutomatic1111Connect(),
            annotationText="",
            bgc=[1, 0.5, 0.5],
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_automaticURL)
        _row.layout()

        self.uiFunc_auto_populate_fields()
        return _inside

    # =============================================================================================================
    # >> Project Column
    # =============================================================================================================
    def buildColumn_project(self, parent, asScroll=False):
        """
        Trying to put all this in here so it's insertable in other uis

        """
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        # >>> Mode

        mc.setParent(_inside)

        cgmUI.add_Header("Project")

        # >>> Prompt
        _row = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate", height=60
        )
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Prompt:", align="right")
        self.uiTextField_prompt = mUI.MelScrollField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            wordWrap=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Prompt",
        )
        self.uiTextField_prompt(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI("prompt", self.uiTextField_prompt),
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiTextField_prompt)
        _row.layout()

        # >>> Negative Prompt
        _row = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate", height=60
        )
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Negative Prompt:", align="right")
        self.uiTextField_negativePrompt = mUI.MelScrollField(
            _row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            wordWrap=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Negative prompt",
        )
        self.uiTextField_negativePrompt(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI(
                "negative_prompt", self.uiTextField_negativePrompt
            ),
        )
        _row.setStretchWidget(self.uiTextField_negativePrompt)
        mUI.MelSpacer(_row, w=5)

        _row.layout()

        # >>> Properties
        # _row = mUI.MelHLayout(_inside,expand = False,ut = 'cgmUISubTemplate', padding=5)
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Seed:", align="right")
        self.uiIF_RandomSeed = mUI.MelIntField(
            _row,
            minValue=-1,
            value=-1,
            annotation="Random seed to use for this project",
        )

        log.debug("self._uiIF_RandomSeed: %s" % self.uiIF_RandomSeed)

        self.uiIF_RandomSeed(
            edit=True,
            changeCommand=(
                cgmGEN.Callback(self.saveOptionFromUI, "seed", self.uiIF_RandomSeed)
            ),
        )

        cgmUI.add_Button(_row, "Last", lambda *a: self.uiFunc_getLastSeed())

        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        mUI.MelLabel(_row, l="Size:", align="right")

        self.uiIF_Width = mUI.MelIntField(
            _row,
            minValue=32,
            value=512,
            changeCommand=cgmGEN.Callback(self.uiFunc_setSize, "field"),
            annotation="Width of image to create",
        )

        self.uiIF_Height = mUI.MelIntField(
            _row,
            minValue=32,
            value=512,
            changeCommand=cgmGEN.Callback(self.uiFunc_setSize, "field"),
            annotation="Height of image to create",
        )

        _sizeOptions = [
            "512x512",
            "1024x1024",
            "2048x2048",
            "768x512",
            "640x360",
            "1280x720",
            "1920x1080",
            "720x1280",
            "512x768",
            "512x1024",
        ]
        self.uiOM_SizeMenu = mUI.MelOptionMenu(_row, useTemplate="cgmUITemplate")
        for option in _sizeOptions:
            self.uiOM_SizeMenu.append(option)

        self.uiOM_SizeMenu(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_setSize, "menu")
        )

        # _row.setStretchWidget( self.sizeMenu )
        mUI.MelSpacer(_row, w=5)

        _row.layout()

        # >>> Model
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Model:", align="right")
        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.uiOM_modelMenu = mUI.MelOptionMenu(
            _row,
            useTemplate="cgmUITemplate",
            changeCommand=lambda *a: self.uiFunc_setModelFromUI(),
        )

        # self.uiFunc_updateModelsFromAutomatic()

        cgmUI.add_Button(
            _row, "Refresh", lambda *a: self.uiFunc_updateModelsFromAutomatic()
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Sampling
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Sampling Method:", align="right")
        self.uiOM_samplingMethodMenu = mUI.MelOptionMenu(
            _row, useTemplate="cgmUITemplate"
        )
        # self.uiFunc_updateSamplersFromAutomatic()
        self.uiOM_samplingMethodMenu(
            edit=True,
            changeCommand=lambda *a: self.saveOptionFromUI(
                "sampling_method", self.uiOM_samplingMethodMenu
            ),
        )
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Steps:", align="right")
        self.uiIF_samplingSteps = mUI.MelIntField(
            _row,
            minValue=1,
            value=20,
            annotation="Sampling Steps",
            changeCommand=cgmGEN.Callback(self.uiFunc_setSamples, "field"),
        )
        self.uiSlider_samplingSteps = mUI.MelIntSlider(_row, 1, 100, 20, step=1)
        self.uiSlider_samplingSteps.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setSamples, "slider")
        )

        _row.setStretchWidget(self.uiSlider_samplingSteps)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        self.uiFunc_setSamples("field")

        # >>> Batches
        _row = mUI.MelHLayout(_inside, expand=True, ut="cgmUISubTemplate")

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Batch Count:", align="right")
        self.uiIF_batchCount = mUI.MelIntField(
            _subRow,
            minValue=1,
            value=1,
            annotation="Sampling Steps",
            changeCommand=cgmGEN.Callback(self.uiFunc_setBatchCount, "field"),
        )
        self.uiSlider_batchCount = mUI.MelIntSlider(_subRow, 1, 10, 1, step=1)
        self.uiSlider_batchCount.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setBatchCount, "slider")
        )

        _subRow.setStretchWidget(self.uiSlider_batchCount)
        mUI.MelSpacer(_subRow, w=5)

        self.uiFunc_setBatchCount("field")

        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")

        mUI.MelLabel(_subRow, l="Batch Size:", align="right")
        self.uiIF_batchSize = mUI.MelIntField(
            _subRow,
            minValue=1,
            value=1,
            annotation="Sampling Steps",
            changeCommand=cgmGEN.Callback(self.uiFunc_setBatchSize, "field"),
        )
        self.uiSlider_batchSize = mUI.MelIntSlider(_subRow, 1, 100, 1, step=1)
        self.uiSlider_batchSize.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setBatchSize, "slider")
        )

        _subRow.setStretchWidget(self.uiSlider_batchSize)
        mUI.MelSpacer(_subRow, w=5)

        self.uiFunc_setBatchSize("field")

        _subRow.layout()

        _row.layout()

        # CFG Scale
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")

        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(
            _row,
            l="CFG Scale:",
            align="right",
            annotation="Value that model tries to conform to the prompt",
        )
        self.uiFF_CFGScale = mUI.MelFloatField(
            _row,
            minValue=1,
            precision=1,
            value=7,
            annotation="Value that model tries to conform to the prompt",
            changeCommand=cgmGEN.Callback(self.uiFunc_setCFGScale, "field"),
        )

        self.uiSlider_CFGScale = mUI.MelFloatSlider(_row, 1, 100, 1, step=1)
        self.uiSlider_CFGScale.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setCFGScale, "slider")
        )

        _row.setStretchWidget(self.uiSlider_CFGScale)
        mUI.MelSpacer(_row, w=5)

        self.uiFunc_setCFGScale("field")

        _row.layout()

        # >>> Img2Img

        mc.setParent(_inside)
        cgmUI.add_Header("Img2Img Settings")

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Passes:", align="right")

        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.uiOM_passMenu = mUI.MelOptionMenu(
            _row, useTemplate="cgmUITemplate", changeCommand=self.uiFunc_setImg2ImgPass
        )

        for option in ["None", "Composite", "Merged", "Custom", "Render Layer"]:
            self.uiOM_passMenu.append(option)

        # self.uiCompositeCB = mUI.MelCheckBox(_row,useTemplate = 'cgmUITemplate', v=False, changeCommand = self.uiFunc_setCompositeCB)

        mUI.MelLabel(_row, l="Alpha Matte:", align="right")
        self.uiAlphaMatteCB = mUI.MelCheckBox(
            _row,
            useTemplate="cgmUITemplate",
            v=False,
            en=False,
            changeCommand=self.uiFunc_setAlphaMatteCB,
        )

        mUI.MelSpacer(_row, w=5)
        _row.layout()

        self.img2imgLayout = mUI.MelColumnLayout(
            _inside, useTemplate="cgmUISubTemplate"
        )

        # >>> Custom Image
        self.customImage_row = mUI.MelHSingleStretchLayout(
            self.img2imgLayout, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(self.customImage_row, w=5)
        mUI.MelLabel(self.customImage_row, l="Custom Image:", align="right")
        self.uiTextField_customImage = mUI.MelTextField(
            self.customImage_row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(self.customImage_row, w=5)
        self.customImage_row.setStretchWidget(self.uiTextField_customImage)
        cgmUI.add_Button(
            self.customImage_row, "Load", lambda *a: self.uiFunc_loadCustomImage(self.uiTextField_customImage, 'img2img_custom_image')
        )
        mUI.MelSpacer(self.customImage_row, w=5)
        self.customImage_row.layout()

        # >>> Render Layer
        self.renderLayer_row = mUI.MelHSingleStretchLayout(
            self.img2imgLayout, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(self.renderLayer_row, w=5)
        mUI.MelLabel(self.renderLayer_row, l="Render Layer:", align="right")
        self.uiOM_renderLayer = mUI.MelOptionMenu(
            self.renderLayer_row,
            useTemplate="cgmUITemplate",
            bsp=cgmGEN.Callback(self.uiFunc_updateRenderLayers),
        )

        render_layers = mc.ls(type="renderLayer")

        for option in render_layers:
            self.uiOM_renderLayer.append(option)

        mUI.MelSpacer(self.renderLayer_row, w=5)
        self.renderLayer_row.setStretchWidget(self.uiOM_renderLayer)
        cgmUI.add_Button(
            self.renderLayer_row, "Render", lambda *a: self.uiFunc_renderLayer()
        )
        mUI.MelSpacer(self.renderLayer_row, w=5)

        self.renderLayer_row.layout()

        # >>>Denoise Slider...
        denoise = 0.35
        _row = mUI.MelHSingleStretchLayout(
            self.img2imgLayout, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Denoising Strength:", align="right")
        self.uiFF_denoiseStrength = mUI.MelFloatField(
            _row,
            w=40,
            ut="cgmUITemplate",
            precision=2,
            value=denoise,
            changeCommand=cgmGEN.Callback(self.uiFunc_setDenoise, "field"),
        )

        self.uiSlider_denoiseStrength = mUI.MelFloatSlider(
            _row, 0.0, 1.0, denoise, step=0.01
        )
        self.uiSlider_denoiseStrength.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setDenoise, "slider")
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiSlider_denoiseStrength)  # Set stretch

        mUI.MelLabel(_row, l="Render Scale Multiplier:", align="right")

        self.uiOM_img2imgScaleMultiplier = mUI.MelOptionMenu(
            _row, useTemplate="cgmUITemplate"
        )
        self.uiOM_img2imgScaleMultiplier(
            e=True,
            cc=cgmGEN.Callback(
                self.saveOptionFromUI,
                "img2img_scale_multiplier",
                self.uiOM_img2imgScaleMultiplier,
            ),
        )

        for option in [".25", ".5", ".75", "1", "1.5", "2"]:
            mUI.MelMenuItem(self.uiOM_img2imgScaleMultiplier, l=option)

        mUI.MelSpacer(_row, w=5)

        self.uiFunc_setDenoise("field")
        _row.layout()

        self.alphaMatteLayout = mUI.MelHLayout(
            self.img2imgLayout,
            expand=True,
            ut="cgmUISubTemplate",
            vis=self.uiAlphaMatteCB(q=True, v=True),
        )

        # >>>Mask Blur Slider...
        maskBlur = 4
        _row = mUI.MelHSingleStretchLayout(
            self.alphaMatteLayout, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Mask Blur:", align="right")
        self.uiIF_maskBlur = mUI.MelIntField(
            _row,
            w=40,
            ut="cgmUITemplate",
            value=maskBlur,
            changeCommand=cgmGEN.Callback(self.uiFunc_setMaskBlur, "field"),
        )

        self.uiSlider_maskBlur = mUI.MelIntSlider(_row, 0, 100, maskBlur, step=1)
        self.uiSlider_maskBlur.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setMaskBlur, "slider")
        )
        mUI.MelSpacer(_row, w=5)
        _row.setStretchWidget(self.uiSlider_maskBlur)  # Set stretch

        self.uiFunc_setMaskBlur("field")
        _row.layout()

        self.alphaMatteLayout.layout()

        # >>> Control Net
        mc.setParent(_inside)
        cgmUI.add_Header("Control Net")

        self.controlNets = []
        for i in range(4):
            _controlNetDict = self.build_controlNet_frame(_inside, i, "Control Net %s" % (i+1))
            self.controlNets.append(_controlNetDict)
            if i > 0:
                print(_controlNetDict)
                _controlNetDict['frame'](e=True, collapse=True)        

        # >>> Materials
        mc.setParent(_inside)
        cgmUI.add_Header("Materials")

        # >>> Shader Assignment
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Assign Material:", align="right")
        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))
        cgmUI.add_Button(_row, "Depth", lambda *a: self.uiFunc_assignMaterial("depth"))
        cgmUI.add_Button(_row, "Normal", lambda *a: self.uiFunc_assignMaterial("normal"))
        cgmUI.add_Button(_row, "XYZ", lambda *a: self.uiFunc_assignMaterial("xyz"))
        cgmUI.add_Button(
            _row, "Projection", lambda *a: self.uiFunc_assignMaterial("projection")
        )
        cgmUI.add_Button(
            _row, "Alpha", lambda *a: self.uiFunc_assignMaterial("alphaProjection")
        )
        cgmUI.add_Button(
            _row, "Composite", lambda *a: self.uiFunc_assignMaterial("composite")
        )
        cgmUI.add_Button(
            _row, "Alpha Matte", lambda *a: self.uiFunc_assignMaterial("alphaMatte")
        )

        cgmUI.add_Button(
            _row, "Merged", lambda *a: self.uiFunc_assignMaterial("merged")
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        # >>> Auto Depth
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")

        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Auto Depth Estimation:", align="right")
        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))
        self.uiAutoDepthEnabledCB = mUI.MelCheckBox(
            _row, useTemplate="cgmUITemplate", v=True
        )
        self.uiAutoDepthEnabledCB(
            edit=True,
            changeCommand=lambda *a: self.uiFunc_project_setAutoDepth(),
        )

        mUI.MelSpacer(_row, w=5)
        _row.layout()
        

        # >>>Depth Slider...
        minDepth = 0
        maxDepth = 50.0
        depthShader = self.uiFunc_getDepthShader()
        if depthShader:
            minDepth = mc.getAttr("%s.minDistance" % depthShader)
            maxDepth = mc.getAttr("%s.maxDistance" % depthShader)

        self.uiDepthRow = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")

        mUI.MelSpacer(self.uiDepthRow, w=5)
        mUI.MelLabel(self.uiDepthRow, l="Depth:", align="right")
        _layoutRow = mUI.MelHLayout(self.uiDepthRow, ut="cgmUISubTemplate", padding=10)

        _subRow = mUI.MelHSingleStretchLayout(
            _layoutRow, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelLabel(_subRow, l="Min:", align="right")
        self.uiFF_minDepthDistance = mUI.MelFloatField(
            _subRow,
            w=60,
            ut="cgmUITemplate",
            precision=2,
            value=minDepth,
            changeCommand=cgmGEN.Callback(self.uiFunc_setDepth, "field"),
        )

        self.uiSlider_minDepthDistance = mUI.MelFloatSlider(
            _subRow, 0.0, 100.0, minDepth, step=1
        )
        self.uiSlider_minDepthDistance.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setDepth, "slider")
        )
        _subRow.setStretchWidget(self.uiSlider_minDepthDistance)  # Set stretch
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(
            _layoutRow, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelLabel(_subRow, l="Max:", align="right")
        self.uiFF_maxDepthDistance = mUI.MelFloatField(
            _subRow,
            w=60,
            ut="cgmUITemplate",
            precision=2,
            value=maxDepth,
            changeCommand=cgmGEN.Callback(self.uiFunc_setDepth, "field"),
        )

        self.uiSlider_maxDepthDistance = mUI.MelFloatSlider(
            _subRow, 1.0, 100.0, maxDepth, step=1
        )
        self.uiSlider_maxDepthDistance.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setDepth, "slider")
        )
        _subRow.setStretchWidget(self.uiSlider_maxDepthDistance)  # Set stretch

        _subRow.layout()
        _layoutRow.layout()
        self.uiDepthRow.setStretchWidget(_layoutRow)
        
        cgmUI.add_Button(self.uiDepthRow,'Guess',
                         cgmGEN.Callback(self.uiFunc_guessDepth))
        mUI.MelSpacer(self.uiDepthRow, w=5)
        self.uiDepthRow.layout()

        self.uiFunc_setDepth("field")

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="XYZ:", align="right")
        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.renderBtn = cgmUI.add_Button(
            _row,
            "Set BBox From Selected",
            cgmGEN.Callback(self.uiFunc_setXYZFromSelected),
            "Set BBox From Selected",
        )
        self.viewImageBtn = cgmUI.add_Button(
            _row,
            "Bake XYZ On Selected",
            cgmGEN.Callback(self.uiFunc_bakeXYZMap),
            "Bake XYZ map",
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Tools:", align="right")
        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.renderBtn = cgmUI.add_Button(
            _row,
            "Load Projection Image",
            cgmGEN.Callback(self.uiFunc_loadProjectionImage),
            "Load Custom Projection Image",
        )

        self.renderBtn = cgmUI.add_Button(
            _row, "Test Render", cgmGEN.Callback(self.uiFunc_renderImage), "Render"
        )
        self.viewImageBtn = cgmUI.add_Button(
            _row, "View Image", cgmGEN.Callback(self.uiFunc_viewImage), "View Image"
        )
        mUI.MelSpacer(_row, w=5)
        _row.layout()


        self.uiLayout_batchMode = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate"
        )

        mUI.MelSpacer(self.uiLayout_batchMode, w=5)

        mUI.MelLabel(self.uiLayout_batchMode, l="Batch Mode:", align="right")

        self.uiOM_batchMode = mUI.MelOptionMenu(
            self.uiLayout_batchMode,
            useTemplate="cgmUITemplate"
        )
        self.uiOM_batchMode(e=True, cc=cgmGEN.Callback(self.uiFunc_project_handleBatchModeChange))

        batchModes = ["None", "Bake Projection", "Latent Space"]

        for mode in batchModes:
            self.uiOM_batchMode.append(mode)

        self.uiLayout_batchMode_bakeProjection = mUI.MelHSingleStretchLayout(
            self.uiLayout_batchMode, expand=True, ut="cgmUISubTemplate"
        )
        # mUI.MelSpacer(_subRow, w=5)
        
        # self.uiCB_batchProject = mUI.MelCheckBox(
        #     _subRow, v=False, annotation="Enable batch project"
        # )
        # self.uiCB_batchProject(
        #     edit=True,
        #     cc=lambda *a: self.saveOptionFromUI(
        #         "batch_project", self.uiCB_batchProject
        #     ),
        # )
        mUI.MelSpacer(self.uiLayout_batchMode_bakeProjection, w=5)
        mUI.MelLabel(self.uiLayout_batchMode_bakeProjection, l="Generate Every Frame:", align="right")
        self.uiCB_batchGenerate = mUI.MelCheckBox(
            self.uiLayout_batchMode_bakeProjection, v=False, annotation="Generate every frame"
        )
        self.uiCB_batchGenerate(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI(
                "batch_generate", self.uiCB_batchGenerate
            ),
        )

        self.uiLayout_batchMode_bakeProjection.setStretchWidget(mUI.MelSeparator(self.uiLayout_batchMode_bakeProjection, w=2))


        self.uiMelRow_batchTimeRange = mUI.MelRowLayout(self.uiLayout_batchMode, useTemplate="cgmUISubTemplate", numberOfColumns=6)

        mUI.MelLabel(self.uiMelRow_batchTimeRange, l="Start:", align="right")
        minTime = int(mc.playbackOptions(q=True, minTime=True))
        self.uiIF_batchProjectStart = mUI.MelIntField(
            self.uiMelRow_batchTimeRange,
            value=minTime,
            annotation="Start time for batch project",
        )
        self.uiIF_batchProjectStart(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI(
                "batch_min_time", self.uiIF_batchProjectStart
            ),
        )

        mUI.MelLabel(self.uiMelRow_batchTimeRange, l="End:", align="right")
        maxTime = int(mc.playbackOptions(q=True, maxTime=True))
        self.uiIF_batchProjectEnd = mUI.MelIntField(
            self.uiMelRow_batchTimeRange,
            value=maxTime,
            annotation="End time for batch project",
        )
        self.uiIF_batchProjectEnd(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI(
                "batch_max_time", self.uiIF_batchProjectEnd
            ),
        )

        mUI.MelLabel(self.uiMelRow_batchTimeRange, l="Step:", align="right")
        self.uiIF_batchProjectStep = mUI.MelIntField(
            self.uiMelRow_batchTimeRange, minValue=1, value=1, annotation="Frame step for batch project"
        )
        self.uiIF_batchProjectStep(
            edit=True,
            cc=lambda *a: self.saveOptionFromUI(
                "batch_step_time", self.uiIF_batchProjectStep
            ),
        )

        self.uiLayout_batchMode_bakeProjection.layout()

        self.uiLayout_batchMode.setStretchWidget(self.uiLayout_batchMode_bakeProjection)
        
        mUI.MelSpacer(self.uiLayout_batchMode, w=5)

        self.uiLayout_batchMode.layout()        

        # _row = mUI.MelHLayout(_inside,expand = False,ut = 'cgmUISubTemplate', padding=5)
        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Bake Resolution:", align="right")

        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.uiIF_BakeWidth = mUI.MelIntField(
            _row,
            minValue=32,
            value=2048,
            changeCommand=cgmGEN.Callback(self.uiFunc_setBakeSize, "field"),
            annotation="Width of baked texture image to create",
            width=50
        )

        self.uiIF_BakeHeight = mUI.MelIntField(
            _row,
            minValue=32,
            value=2048,
            changeCommand=cgmGEN.Callback(self.uiFunc_setBakeSize, "field"),
            annotation="Height of baked texture image to create",
            width=50
        )

        _bakeSizeOptions = [
            "512x512",
            "1024x1024",
            "2048x2048",
            "4096x4096",
        ]
        self.uiOM_BakeSizeMenu = mUI.MelOptionMenu(_row, useTemplate="cgmUITemplate")
        for option in _bakeSizeOptions:
            self.uiOM_BakeSizeMenu.append(option)

        self.uiOM_BakeSizeMenu(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_setBakeSize, "menu")
        )

        # _row.setStretchWidget( self.sizeMenu )
        mUI.MelSpacer(_row, w=5)

        _row.layout()


        # Generate Button
        #
        _row = mUI.MelHLayout(_inside, ut="cgmUISubTemplate", padding=10)

        self.generateBtn = cgmUI.add_Button(
            _row,
            "Generate Art",
            cgmGEN.Callback(gi.generateImageFromUI, self),
            "Generate",
            h=50,
        )

        self.bakeProjectionBtn = cgmUI.add_Button(
            _row,
            "Bake Projection on All",
            cgmGEN.Callback(self.uiFunc_bakeProjection),
            "Bake Projection on All",
            h=50,
        )

        self.bakeProjectionAllBtn = cgmUI.add_Button(
            _row,
            "Bake Projection on Selected",
            cgmGEN.Callback(self.uiFunc_bakeProjection, True),
            "Bake Projection on Selected",
            h=50,
        )

        _row.layout()

        mUI.MelSpacer(_inside, w=5, h=10)
        #
        # End Generate Button

        # mUI.MelSpacer(_inside,w = 5, h=20)

        # _frame = mUI.MelFrameLayout(_inside,label = "Batch Project",vis=True,
        #                 collapse=False,
        #                 collapsable=True,
        #                 enable=True,
        #                 useTemplate = 'cgmUITemplate',
        #                 #expandCommand = lambda *a:mVar_frame.setValue(0),
        #                 #collapseCommand = lambda *a:mVar_frame.setValue(1)
        #                 )
        # batch_layout = mUI.MelColumn(_frame,useTemplate = 'cgmUISubTemplate')
        # mUI.MelSpacer(batch_layout,w=5, h=5)

        return _inside

    def build_controlNet_frame(self, parent, index=0, label="Control Net"):
        _inside = mUI.MelFrameLayout(
            parent,
            label=label,
            collapsable=True,
            collapse=False,
            useTemplate="cgmUITemplate",
        )

        returnDict = {}

        returnDict['frame'] = _inside

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Options", align="right")

        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))
        mUI.MelLabel(_row, l="Enable:", align="right")
        uiControlNetEnabledCB = mUI.MelCheckBox(
            _row, useTemplate="cgmUITemplate", v=True
        )
        uiControlNetEnabledCB(
            edit=True,
            changeCommand=lambda *a: self.uiFunc_setControlNetEnabled(index=index),
        )

        returnDict['enabled_cb'] = uiControlNetEnabledCB

        mUI.MelLabel(_row, l="Low VRAM:", align="right")
        uiControlNetLowVRamCB = mUI.MelCheckBox(
            _row, useTemplate="cgmUITemplate", v=True
        )
        uiControlNetLowVRamCB(
            edit=True,
            changeCommand=lambda *a: self.uiFunc_saveControlNetFromUI(index=index),
        )

        returnDict['low_vram_cb'] = uiControlNetLowVRamCB

        mUI.MelLabel(_row, l="Custom Image:", align="right")
        uiControlNetCustomImageCB = mUI.MelCheckBox(
            _row, useTemplate="cgmUITemplate", v=True
        )

        uiControlNetCustomImageCB(
            edit=True,
            changeCommand=lambda *a: self.uiFunc_project_handleCustomImageCBChange(index=index),
        )

        returnDict['custom_image_cb'] = uiControlNetCustomImageCB

        mUI.MelSpacer(_row, w=5)

        _row.layout()

        _row = mUI.MelHLayout(_inside, expand=True, ut="cgmUISubTemplate")

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Preprocessor:", align="right")

        uiOM_ControlNetPreprocessorMenu = mUI.MelOptionMenu(
            _subRow,
            useTemplate="cgmUITemplate"
        )
        uiOM_ControlNetPreprocessorMenu(e=True, cc=cgmGEN.Callback(self.uiFunc_changeControlNetPreProcessor, index))

        # self.uiFunc_updateControlNetPreprocessorsMenu()

        _subRow.setStretchWidget(uiOM_ControlNetPreprocessorMenu)

        mUI.MelSpacer(_subRow, w=5)

        returnDict['preprocessor_menu'] = uiOM_ControlNetPreprocessorMenu

        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Model:", align="right")
        uiOM_ControlNetModelMenu = mUI.MelOptionMenu(
            _subRow, useTemplate="cgmUITemplate"
        )
        uiOM_ControlNetModelMenu(
            edit=True,
            changeCommand=lambda *a: self.uiFunc_saveControlNetFromUI(index),
        )

        returnDict['model_menu'] = uiOM_ControlNetModelMenu

                # self.uiFunc_updateControlNetModelsFromAutomatic()

        _subRow.setStretchWidget(uiOM_ControlNetModelMenu)

        mUI.MelSpacer(_subRow, w=5)

        _subRow.layout()

        returnDict['model_subrow'] = _subRow

        _row.layout()

        returnDict['model_row'] = _row

        # >>> Custom Image
        customImage_row = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(customImage_row, w=5)
        mUI.MelLabel(customImage_row, l="Custom Image:", align="right")
        uiTextField_customImage = mUI.MelTextField(
            customImage_row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(customImage_row, w=5)
        customImage_row.setStretchWidget(uiTextField_customImage)
        cgmUI.add_Button(
            customImage_row, "Load", lambda *a: self.uiFunc_loadCustomImage(uiTextField_customImage)
        )
        mUI.MelSpacer(customImage_row, w=5)
        customImage_row.layout()

        returnDict['custom_image_row'] = customImage_row
        returnDict['custom_image_tf'] = uiTextField_customImage

        _row = mUI.MelHLayout(_inside, expand=True, ut="cgmUISubTemplate")

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Weight:", align="right")
        uiFF_controlNetWeight = mUI.MelFloatField(
            _subRow, w=40, ut="cgmUITemplate", precision=2, value=1.0
        )
        
        uiSlider_controlNetWeight = mUI.MelFloatSlider(
            _subRow, 0.0, 1.0, 1.0, step=0.1
        )

        uiSlider_controlNetWeight(
            e=True,
            dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetWeight, "slider", index),
        )
        uiFF_controlNetWeight.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setControlNetWeight, "field", index)
        )

        returnDict['weight_slider'] = uiSlider_controlNetWeight
        returnDict['weight_field'] = uiFF_controlNetWeight

        mUI.MelSpacer(_subRow, w=5)

        _subRow.setStretchWidget(uiSlider_controlNetWeight)
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Noise:", align="right")
        uiFF_controlNetNoise = mUI.MelFloatField(
            _subRow, w=40, ut="cgmUITemplate", precision=2, value=0.0
        )

        uiSlider_controlNetNoise = mUI.MelFloatSlider(
            _subRow, 0.0, 1.0, 1.0, step=0.1
        )

        uiSlider_controlNetNoise(
            e=True,
            dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetNoise, "slider", index),
        )
        uiFF_controlNetNoise.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setControlNetNoise, "field", index)
        )

        returnDict['noise_field'] = uiFF_controlNetNoise
        returnDict['noise_slider'] = uiSlider_controlNetNoise

        mUI.MelSpacer(_subRow, w=5)
        _subRow.setStretchWidget(uiSlider_controlNetNoise)
        _subRow.layout()

        _row.layout()

        # Guidance Start and End

        _row = mUI.MelHLayout(_inside, expand=True, ut="cgmUISubTemplate")

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Guidance Start (T):", align="right")
        uiFF_controlNetGuidanceStart = mUI.MelFloatField(
            _subRow, w=40, ut="cgmUITemplate", precision=2, value=0.0
        )

        uiSlider_controlNetGuidanceStart = mUI.MelFloatSlider(
            _subRow, 0.0, 1.0, 1.0, step=0.1
        )

        uiSlider_controlNetGuidanceStart(
            e=True,
            dragCommand=cgmGEN.Callback(
                self.uiFunc_setControlNetGuidanceStart, "slider", index
            ),
        )
        uiFF_controlNetGuidanceStart.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setControlNetGuidanceStart, "field", index)
        )

        returnDict['guidance_start_field'] = uiFF_controlNetGuidanceStart
        returnDict['guidance_start_slider'] = uiSlider_controlNetGuidanceStart

        mUI.MelSpacer(_subRow, w=5)
        _subRow.setStretchWidget(uiSlider_controlNetGuidanceStart)
        _subRow.layout()

        _subRow = mUI.MelHSingleStretchLayout(_row, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_subRow, w=5)
        mUI.MelLabel(_subRow, l="Guidance End (T):", align="right")
        uiFF_controlNetGuidanceEnd = mUI.MelFloatField(
            _subRow, w=40, ut="cgmUITemplate", precision=2, value=1.0
        )

        uiSlider_controlNetGuidanceEnd = mUI.MelFloatSlider(
            _subRow, 0.0, 1.0, 1.0, step=0.1
        )

        uiSlider_controlNetGuidanceEnd(
            e=True,
            dragCommand=cgmGEN.Callback(self.uiFunc_setControlNetGuidanceEnd, "slider", index),
        )
        uiFF_controlNetGuidanceEnd.setChangeCB(
            cgmGEN.Callback(self.uiFunc_setControlNetGuidanceEnd, "field", index)
        )

        returnDict['guidance_end_field'] = uiFF_controlNetGuidanceEnd
        returnDict['guidance_end_slider'] = uiSlider_controlNetGuidanceEnd

        mUI.MelSpacer(_subRow, w=5)

        _subRow.setStretchWidget(uiSlider_controlNetGuidanceEnd)
        _subRow.layout()

        _row.layout()

        return returnDict
   
    def uiFunc_setControlNetEnabled(self, index):
        val = self.controlNets[index]['enabled_cb'].getValue()
        self.controlNets[index]['frame'](e=True, bgc=self.GREEN if val else self.GRAY)

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_getControlNets(self):
        controlNetData = []
        for i, controlNetDict in enumerate(self.controlNets):
            controlNetOptions = {
                "control_net_enabled": controlNetDict['enabled_cb'].getValue(),
                "control_net_low_v_ram": controlNetDict['low_vram_cb'].getValue(),
                "control_net_preprocessor": controlNetDict['preprocessor_menu'].getValue(),
                "control_net_model": controlNetDict['model_menu'].getValue(),
                "control_net_weight": controlNetDict['weight_field'].getValue(),
                "control_net_guidance_start": controlNetDict['guidance_start_field'].getValue(),
                "control_net_guidance_end": controlNetDict['guidance_end_field'].getValue(),
                "control_net_noise": controlNetDict['noise_field'].getValue(),
                "control_net_custom_image_path": controlNetDict['custom_image_tf'].getValue(),
                }
            controlNetData.append(controlNetOptions)

        return controlNetData

    def uiFunc_saveControlNetFromUI(self, index):
        self.saveOption("control_nets", self.uiFunc_getControlNets())

    def uiFunc_setSize(self, source):
        _str_func = "uiFunc_setSize"

        width, height = 0, 0

        if source == "menu":
            size = self.uiOM_SizeMenu(query=True, value=True)
            width, height = [int(x) for x in size.split("x")]
            self.uiIF_Width(edit=True, value=width)
            self.uiIF_Height(edit=True, value=height)
        else:
            width = self.uiIF_Width(query=True, value=True)
            height = self.uiIF_Height(query=True, value=True)

        # set render globals
        mc.setAttr("defaultResolution.width", width)
        mc.setAttr("defaultResolution.height", height)

        aspectRatio = float(width) / float(height)
        mc.setAttr("defaultResolution.deviceAspectRatio", aspectRatio)

        projectionCam = self.uiTextField_projectionCamera(q=True, text=True)
        if projectionCam:
            mc.setAttr("%s.horizontalFilmAperture" % projectionCam, aspectRatio)
            mc.setAttr("%s.verticalFilmAperture" % projectionCam, 1.0)

        self.saveOption("width", width)
        self.saveOption("height", height)

    def uiFunc_setBakeSize(self, source):
        _str_func = "uiFunc_setBakeSize"

        width, height = 0, 0

        if source == "menu":
            size = self.uiOM_BakeSizeMenu(query=True, value=True)
            width, height = [int(x) for x in size.split("x")]
            self.uiIF_BakeWidth(edit=True, value=width)
            self.uiIF_BakeHeight(edit=True, value=height)
        else:
            width = self.uiIF_BakeWidth(query=True, value=True)
            height = self.uiIF_BakeHeight(query=True, value=True)
            resolutionString = "{}x{}".format(width, height)
            log.debug(resolutionString)
            for menuItem in self.uiOM_BakeSizeMenu(query=True, itemListLong=True):
                log.debug(mc.menuItem(menuItem, query=True, label=True))
                if (mc.menuItem(menuItem, query=True, label=True) == resolutionString):
                    self.uiOM_BakeSizeMenu(edit=True, value=resolutionString)
                    break

        self.saveOption("bake_width", width)
        self.saveOption("bake_height", height)

    # =============================================================================================================
    # >> Edit Column
    # =============================================================================================================
    def buildColumn_edit(self, parent, asScroll=True, inside=None):
        if inside:
            _inside = inside
        else:
            if asScroll:
                _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
            else:
                _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        mUI.MelSpacer(_inside, w=5, h=5)
        _row = mUI.MelHSingleStretchLayout(_inside, ut="cgmUISubTemplate")

        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Active Mesh:", align="right")
        self.uiOM_edit_projectionMesh = mUI.MelOptionMenu(
            _row, useTemplate="cgmUITemplate", h=20
        )
        self.uiOM_edit_projectionMesh(
            edit=True,
            changeCommand=lambda *a: mc.evalDeferred(
                cgmGEN.Callback(self.uiFunc_edit_changeProjectionMesh, self)
            ),
        )

        for mesh in self.uiList_projectionMeshes(q=True, allItems=True) or []:
            mUI.MelMenuItem(self.uiOM_edit_projectionMesh, l=mesh)

        if not self.activeProjectionMesh:
            _row.setStretchWidget(self.uiOM_edit_projectionMesh)
            mUI.MelSpacer(_row, w=5)
            _row.layout()

            return _inside

        self.uiOM_edit_projectionMesh.setValue(self.activeProjectionMesh)
        _mesh = self.activeProjectionMesh

        compositeShader = self.uiFunc_getMaterial("composite", _mesh)
        mergedShader = self.uiFunc_getMaterial("merged", _mesh)
        alphaMatteShader = self.uiFunc_getMaterial("alphaMatte", _mesh)

        cgmUI.add_Button(
            _row,
            "<<",
            cgmGEN.Callback(self.uiFunc_edit_loadProjectionMesh, True),
            "Load Selected Mesh",
            h=20,
        )

        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Pass:", align="right")
        self.uiOM_edit_pass = mUI.MelOptionMenu(_row, useTemplate="cgmUITemplate", h=20)
        self.uiOM_edit_pass(
            edit=True,
            changeCommand=lambda *a: mc.evalDeferred(
                cgmGEN.Callback(self.uiFunc_edit_changePass, self)
            ),
        )

        for p in ["composite", "alphaMatte"]:
            mUI.MelMenuItem(self.uiOM_edit_pass, l=p)

        if not self.activePass:
            self.activePass = "composite" if compositeShader else "alphaMatte"

        self.uiOM_edit_pass.setValue(self.activePass)

        _row.setStretchWidget(self.uiOM_edit_projectionMesh)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        if not compositeShader and not alphaMatteShader:
            return _inside

        activeShader = (
            compositeShader if self.activePass == "composite" else alphaMatteShader
        )

        # Get the layered texture node
        layeredTexture = mc.listConnections(
            activeShader + ".outColor", type="layeredTexture"
        )[0]

        # self.editTabContent = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate')
        _row = mUI.MelHLayout(_inside, expand=True, ut="cgmUISubTemplate", padding=10)

        cgmUI.add_Button(
            _row,
            "Refresh",
            cgmGEN.Callback(self.uiFunc_refreshEditTab),
            annotationText="",
        )

        # cgmUI.add_Button(_row,'Set Composite', lambda *a:self.uiFunc_assignMaterial('composite'))

        cgmUI.add_Button(
            _row,
            "Merge Composite",
            cgmGEN.Callback(
                self.uiFunc_edit_mergeComposite, activeShader, mergedShader
            ),
            annotationText="",
        )

        cgmUI.add_Button(
            _row,
            "Select Layered Texture",
            cgmGEN.Callback(mc.select, layeredTexture),
            annotationText="",
        )

        _row.layout()

        # Get the number of color inputs to the layered texture
        num_inputs = mc.getAttr(layeredTexture + ".inputs", multiIndices=True)
        log.debug("{0} >> num_inputs {1}".format(layeredTexture, num_inputs))

        # Loop through each color input and create a layout for it
        self.layers = []
        for n, i in enumerate(num_inputs or []):
            log.debug("Creating layout for layer {}".format(i))

            input_color = (
                layeredTexture
                + ".inputs[{}].color".format(i)
                + ("R" if self.activePass == "alphaMatte" else "")
            )

            color_connections = rt.getAllConnectedNodesOfType(
                input_color, "file", traverseUserDefined=False
            )
            if not color_connections:
                log.debug("No color connections found for {}".format(input_color))
                continue

            color_name = color_connections[0]

            _frame = mUI.MelFrameLayout(
                _inside,
                label=color_name,
                vis=True,
                collapse=False,
                collapsable=True,
                enable=True,
                useTemplate="cgmUITemplate",
                # expandCommand = lambda *a:mVar_frame.setValue(0),
                # collapseCommand = lambda *a:mVar_frame.setValue(1)
            )
            color_layout = mUI.MelColumn(_frame, useTemplate="cgmUISubTemplate")

            # Create a new MelHSingleStretchLayout for the visibility and solo checkboxes
            # subrow_layout = mUI.MelHSingleStretchLayout(color_layout, ut="cgmUISubTemplate")
            _thumbSize = (150, 150)

            subrow_layout = mUI.MelRowLayout(
                color_layout,
                numberOfColumns=3,
                columnWidth3=(20, _thumbSize[0], 50),
                adjustableColumn=3,
                columnAlign=(1, "left"),
                columnAttach=(1, "right", 0),
                useTemplate="cgmUITemplate",
            )

            # make column layout
            _buttonColumn = mUI.MelVLayout(
                subrow_layout,
                w=20,
            )

            button_up = mUI.MelButton(
                _buttonColumn,
                l="up",
                w=20,
                ut="cgmUITemplate",
                c=cgmGEN.Callback(self.uiFunc_edit_moveLayer, layeredTexture, n, -1),
            )
            mUI.MelSpacer(_buttonColumn, h=25)
            button_dn = mUI.MelButton(
                _buttonColumn,
                l="dn",
                w=20,
                ut="cgmUITemplate",
                c=cgmGEN.Callback(self.uiFunc_edit_moveLayer, layeredTexture, n, 1),
            )
            _buttonColumn.layout()

            _thumb_row = mUI.MelColumnLayout(
                subrow_layout, useTemplate="cgmUISubTemplate"
            )

            _thumb = mUI.MelImage(_thumb_row, w=_thumbSize[0], h=_thumbSize[1])
            _thumb(e=True, vis=True)

            _uv_projection_path = mc.getAttr(color_name + ".fileTextureName")
            _orig_path = ""
            _image_path = _uv_projection_path

            if mc.objExists(color_name + ".cgmSourceProjectionImage"):
                _orig_path = mc.getAttr(color_name + ".cgmSourceProjectionImage")
                if os.path.exists(_orig_path):
                    _image_path = _orig_path

            _thumb_path = getResizedImage(
                _image_path, _thumbSize[0], _thumbSize[1], preserveAspectRatio=True
            )

            _thumb.setImage(_thumb_path)
            mc.popupMenu(parent=_thumb, button=3)
            if os.path.exists(_orig_path):
                mc.menuItem(
                    label="View Projection",
                    command=cgmGEN.Callback(self.uiFunc_viewImageFromPath, _orig_path),
                )
                mc.menuItem(
                    label="Open Orig in Explorer",
                    command=cgmGEN.Callback(self.uiFunc_openExplorerPath, os.path.split(_orig_path)[0]),
                )
            if os.path.exists(_uv_projection_path):
                mc.menuItem(
                    label="View UV Image",
                    command=cgmGEN.Callback(
                        self.uiFunc_viewImageFromPath, _uv_projection_path
                    ),
                )
                mc.menuItem(
                    label="Open UV in Explorer",
                    command=cgmGEN.Callback(self.uiFunc_openExplorerPath, os.path.split(_uv_projection_path)[0]),
                )

            info_row = mUI.MelColumn(subrow_layout, useTemplate="cgmUISubTemplate")

            info_top_column = mUI.MelHSingleStretchLayout(
                info_row, ut="cgmUISubTemplate"
            )
            visible_cb = mUI.MelCheckBox(
                info_top_column,
                useTemplate="cgmUITemplate",
                label="Vis",
                v=mc.getAttr("%s.inputs[%i].isVisible" % (layeredTexture, i)),
                changeCommand=cgmGEN.Callback(self.uiFunc_updateLayerVisibility),
            )
            solo_cb = mUI.MelCheckBox(
                info_top_column,
                useTemplate="cgmUITemplate",
                label="Solo",
                v=False,
                changeCommand=cgmGEN.Callback(self.uiFunc_updateLayerVisibility),
            )

            # set label as stretch widget
            info_top_column.setStretchWidget(mUI.MelSeparator(info_top_column, w=2))

            _layerTF = mUI.MelTextField(
                info_top_column, useTemplate="cgmUITemplate", vis=False, text=color_name
            )

            _cameraData = {}
            if mc.objExists(color_name + ".cgmImageProjectionData"):
                _data = json.loads(mc.getAttr(color_name + ".cgmImageProjectionData"))
                if "camera_info" in _data:
                    _cameraData = _data["camera_info"]
                # backwards compatibility

                if "baked_camera_info" in _data:
                    _cameraData = _data["baked_camera_info"]

            _compositeConnection = None
            _compositeSourceAttribute = color_name + ".cgmCompositeTextureSource"
            if mc.objExists(_compositeSourceAttribute):
                _compositeConnection = mc.listConnections(
                    _compositeSourceAttribute, type="layeredTexture"
                )

            cgmUI.add_Button(
                info_top_column,
                "Copy",
                cgmGEN.Callback(self.uiFunc_edit_copy, n),
                annotationText="",
            )
            cgmUI.add_Button(
                info_top_column,
                "Paste",
                cgmGEN.Callback(self.uiFunc_edit_paste, n),
                annotationText="",
            )
            cgmUI.add_Button(
                info_top_column,
                "Select",
                cgmGEN.Callback(uiFunc_selectItemFromTextField, _layerTF),
                annotationText="",
            )
            if _cameraData:
                cgmUI.add_Button(
                    info_top_column,
                    "Snap Camera",
                    cgmGEN.Callback(self.uiFunc_snapCameraFromData, _cameraData),
                    annotationText="",
                )
            if _compositeConnection:
                cgmUI.add_Button(
                    info_top_column,
                    "Restore Comp",
                    cgmGEN.Callback(
                        self.uiFunc_edit_restoreComposite,
                        activeShader,
                        _compositeConnection[0],
                    ),
                    annotationText="",
                )
            cgmUI.add_Button(
                info_top_column,
                "Delete",
                cgmGEN.Callback(self.uiFunc_edit_deleteLayer, n),
                bgc=[0.5, 0, 0],
                annotationText="",
            )

            mUI.MelSpacer(info_top_column, w=5)
            info_top_column.layout()

            # Check if the alpha input has a remapColor node and create min/max sliders if it does
            alpha_input = (
                layeredTexture + ".inputs[{}].alpha".format(i)
                if self.activePass == "composite"
                else layeredTexture + ".inputs[{}].colorR".format(i)
            )
            log.debug("alpha_input: {}".format(alpha_input))
            remapColorNodes = rt.getAllConnectedNodesOfType(alpha_input, "remapColor")
            channelSliders = {}

            _hasPositionRemap = False

            _xyzFile = self.getXYZFile(_mesh)

            for remap_color in remapColorNodes:
                # Create a new MelHSingleStretchLayout for each remapColor channel

                remap_file = mc.listConnections(remap_color + ".color", type="file")
                if remap_file:
                    remap_file = remap_file[0]
                    if remap_file == _xyzFile and _xyzFile:
                        _hasPositionRemap = True

                for channel in ["red", "green", "blue"]:
                    label = channel.capitalize()
                    if mc.objExists(
                        "%s.cgm%sLabel" % (remap_color, channel.capitalize())
                    ):
                        label = mc.getAttr(
                            "%s.cgm%sLabel" % (remap_color, channel.capitalize())
                        )

                    _alphaFrame = mUI.MelFrameLayout(
                        info_row,
                        label=label,
                        vis=True,
                        collapse=True,
                        collapsable=True,
                        enable=True,
                        useTemplate="cgmUITemplate",
                        # expandCommand = lambda *a:mVar_frame.setValue(0),
                        # collapseCommand = lambda *a:mVar_frame.setValue(1)
                    )

                    _alpha_col = mUI.MelColumnLayout(
                        _alphaFrame, useTemplate="cgmUISubTemplate"
                    )
                    mc.setParent(_alpha_col)
                    _grad = mc.gradientControl(
                        at="%s.%s" % (remap_color, channel),
                        dropCallback=lambda *a: log.debug("dropCallback executed"),
                    )

            if len(remapColorNodes) < 5:
                for n in range(5 - len(remapColorNodes)):
                    mUI.MelLabel(info_row, label="")

            if not _hasPositionRemap and _xyzFile:
                cgmUI.add_Button(
                    info_row,
                    "Add Position Matte",
                    cgmGEN.Callback(self.uiFunc_addPositionMatte, alpha_input),
                    annotationText="",
                )

            self.layers.append(
                {
                    "visible_cb": visible_cb,
                    "layeredTexture": layeredTexture,
                    "index": int(i),
                    "solo_cb": solo_cb,
                    "channelSliders": channelSliders,
                    "remapColorNodes": remapColorNodes,
                }
            )

            # subrow_layout.layout()

        log.debug("Layers: %s" % self.layers)

        return _inside

    # =============================================================================================================
    # >> UI Properties
    # =============================================================================================================
    @property
    def currentTab(self):
        if not self.uiTabLayout:
            return None
        tabIndex = mc.tabLayout(self.uiTabLayout, q=True, sti=True)
        return mc.tabLayout(self.uiTabLayout, q=True, tl=True)[tabIndex - 1]

    # =============================================================================================================
    # >> UI Funcs
    # =============================================================================================================
    def uiFunc_tryAutomatic1111Connect(self):
        _str_func = "uiFunc_tryAutomatic1111Connect"

        self.urlBtn(e=True, bgc=(1, 0.8, 0.4), label="Connecting...")
        mc.refresh()

        url = self.uiTextField_automaticURL(q=True, text=True)
        sdModels = sd.getModelsFromAutomatic1111(url)

        self.uiFunc_setConnected(sdModels)

    def uiFunc_setConnected(self, val):
        _str_func = "uiFunc_setConnected"

        if not val:
            self.urlBtn(e=True, bgc=self.RED, label="Try Connection")
            self.connected = False
        else:
            self.urlBtn(e=True, bgc=self.GREEN, label="Connected")
            if not self.connected:
                self.handleReload()
                return

    def uiFunc_handleTabChange(self):
        if not self.currentTab:
            return
        if self.currentTab.lower() == "edit":
            self.uiFunc_edit_updateActiveMesh()
            self.uiFunc_refreshEditTab()
        elif self.currentTab.lower() == "project":
            self.projectColumn(e=True, en=self.connected)
            if self.connected:
                self.uiFunc_updateModelsFromAutomatic()
                self.uiFunc_updateSamplersFromAutomatic()
                self.uiFunc_updateControlNetPreprocessorsMenu()
                self.uiFunc_updateControlNetModelsFromAutomatic()
                self.loadOptions()
        
        if self.currentTab.lower() != "edit":
            self.activeProjectionMesh = None

    def uiFunc_addPositionMatte(self, alphaConnection):
        _str_func = "uiFunc_addPositionMatte"
        baseObj = self.uiOM_edit_projectionMesh.getValue()
        xyzFile = self.getXYZFile(baseObj)

        log.debug(
            "operating on {}, xyz = {}, connection = {}".format(
                baseObj, xyzFile, alphaConnection
            )
        )

        if not xyzFile:
            return

        remap, mult = rt.remapAndMultiplyColorChannels(xyzFile, labels=["X", "Y", "Z"])
        connections = mc.listConnections(alphaConnection, p=True)
        if connections:
            log.debug("connections = {}".format(connections))
            finalMult = mc.shadingNode("multiplyDivide", asUtility=True)
            log.debug("finalMult = {}".format(finalMult))
            mc.connectAttr(connections[0], finalMult + ".input1X", f=True)
            mc.connectAttr(mult + ".outputX", finalMult + ".input2X", f=True)
            mc.connectAttr(finalMult + ".outputX", alphaConnection, f=True)
        else:
            mc.connectAttr(mult + ".outputX", alphaConnection, f=True)

        self.uiFunc_refreshEditTab()

    def uiFunc_loadProjectionImage(self):
        _str_func = "uiFunc_loadProjectionImage"

        _path = mc.fileDialog2(
            fileFilter="Image Files (*.jpg *.jpeg *.png *.exr *.tif *.tiff)",
            dialogStyle=2,
            fileMode=1,
            dir=PROJECT.getImagePath(),
        )
        if not _path:
            return

        _path = _path[0]

        # set the projection image on the projection material
        self.assignImageToProjection(_path, {})

    # =============================================================================================================
    # >> XYZ File
    # =============================================================================================================
    def getXYZFile(self, mesh):
        if not mc.objExists(mesh + ".cgmXYZFile"):
            return None

        xyzFile = mc.listConnections(mesh + ".cgmXYZFile", type="file")
        if not xyzFile:
            return None

        return xyzFile[0]

    def uiFunc_setXYZFromSelected(self):
        _str_func = "uiFunc_setXYZFromSelected"

        _sel = mc.ls(sl=True)
        if not _sel:
            return

        _meshes = []
        for obj in _sel:
            shape = mc.listRelatives(obj, s=True)[0]
            if sd.validateProjectionMesh(shape):
                _meshes.append(shape)

        _bbox = mc.exactWorldBoundingBox(_sel)

        for mesh in _meshes:
            xyzShader = self.uiFunc_getMaterial("xyz", mesh)

            if not mc.objExists(xyzShader):
                continue

            mc.setAttr(
                xyzShader + ".bboxMin", _bbox[0], _bbox[1], _bbox[2], type="double3"
            )
            mc.setAttr(
                xyzShader + ".bboxMax", _bbox[3], _bbox[4], _bbox[5], type="double3"
            )

    def uiFunc_bakeXYZMap(self):
        _str_func = "uiFunc_bakeXYZMap"
        _sel = mc.ls(sl=True)
        if not _sel:
            return

        _meshes = []
        for obj in _sel:
            shape = mc.listRelatives(obj, s=True)[0]
            if sd.validateProjectionMesh(shape):
                _meshes.append(shape)

        for mesh in _meshes:
            xyzShader = self.uiFunc_getMaterial("xyz", mesh)

            if not mc.objExists(xyzShader):
                continue

            xyzFile = rt.bakeProjection(xyzShader, mesh)

            if not xyzFile:
                return

            # create double3 attribute xyzMap
            if not mc.objExists(mesh + ".cgmXYZFile"):
                mc.addAttr(mesh, longName="cgmXYZFile", at="double3")
                mc.addAttr(
                    mesh, longName="cgmXYZFileR", at="double", parent="cgmXYZFile"
                )
                mc.addAttr(
                    mesh, longName="cgmXYZFileG", at="double", parent="cgmXYZFile"
                )
                mc.addAttr(
                    mesh, longName="cgmXYZFileB", at="double", parent="cgmXYZFile"
                )

            mc.connectAttr(xyzFile + ".outColor", mesh + ".cgmXYZFile", force=True)

    # ===========================================================================
    # Materials
    # ===========================================================================
    
    def uiFunc_getMaterial(self, materialType, mesh=None):
        _str_func = "uiFunc_getMaterial"

        if materialType == "projection":
            return self.uiFunc_getProjectionShader()
        if materialType == "alphaProjection":
            return self.uiFunc_getAlphaShader()
        if materialType == "depth":
            return self.uiFunc_getDepthShader()
        if materialType == "normal":
            return self.uiFunc_getNormalShader()
        
        if not mesh or not mc.objExists(mesh):
            log.error("|{0}| >> No mesh specified.".format(_str_func))
            return None

        return sd.getMeshMaterial(mesh, materialType)

    def uiFunc_getDepthShader(self):
        _str_func = "uiFunc_getDepthShader"
        return self.uiTextField_depthShader(q=True, tx=True)

    def uiFunc_getNormalShader(self):
        _str_func = "uiFunc_getNormalShader"
        return self.uiTextField_normalShader(q=True, tx=True)
    
    def uiFunc_getAlphaShader(self):
        _str_func = "uiFunc_getAlphaShader"
        return self.uiTextField_alphaProjectionShader(q=True, tx=True)

    def uiFunc_getProjectionShader(self):
        _str_func = "uiFunc_getProjectionShader"
        return self.uiTextField_projectionShader(q=True, tx=True)

    def uiFunc_assignMaterial(self, materialType, meshes=None):
        _str_func = "uiFunc_assignMaterial"

        if materialType == "none":
            return
        
        if not meshes:
            meshes = self.uiList_projectionMeshes(query=True, allItems=True)

        for _mesh in meshes or []:
            if not mc.objExists(_mesh):
                log.warning("|{0}| >> Mesh doesn't exist {1}.".format(_str_func, _mesh))
                continue

            _material = self.uiFunc_getMaterial(materialType, _mesh)

            if not _material or not mc.objExists(_material):
                log.warning(
                    "|{0}| >> No material loaded - {1}.".format(_str_func, _mesh)
                )
                result = mc.confirmDialog(
                    title="No Material Found",
                    message="No material found for {0}. Would you like to create one?".format(
                        materialType
                    ),
                    button=["Yes", "No"],
                    defaultButton="Yes",
                    cancelButton="No",
                    dismissString="No",
                )
                if result == "Yes":
                    self.uiFunc_makeMaterialFromType(materialType)
                    _material = self.uiFunc_getMaterial(materialType)

                    if not _material:
                        log.error(
                            "|{0}| >> Failed to create material {1}.".format(
                                _str_func, materialType
                            )
                        )
                        continue
                else:
                    continue

            _sg = mc.listConnections(_material, type="shadingEngine")
            if _sg:
                _sg = _sg[0]

            log.debug("Assigning {0} to {1}".format(_material, _mesh))
            rt.assignMaterial(_mesh, _sg)

    # ===========================================================================
    # Rendering
    # ===========================================================================

    def uiFunc_renderLayer(self, display=True):
        _str_func = "uiFunc_renderLayer"

        # get render layer
        currentLayer = mc.editRenderLayerGlobals(query=True, currentRenderLayer=True)
        mc.editRenderLayerGlobals(
            currentRenderLayer=self.uiOM_renderLayer(query=True, value=True)
        )

        # render
        outputImage = self.uiFunc_renderImage(display)

        # set render layer back
        mc.editRenderLayerGlobals(currentRenderLayer=currentLayer)

        return outputImage

    def uiFunc_renderImage(self, display=True):
        _str_func = "uiFunc_renderImage"

        outputImage = rt.renderMaterialPass(
            camera=self.uiTextField_projectionCamera(q=True, text=True),
            resolution=self.resolution,
        )
        if display:
            iv.ui([outputImage], {"outputImage": outputImage})

        return outputImage

    def uiFunc_generateImage(self, display=True):
        _str_func = "uiFunc_generateImage"

        # alphaMat = self.uiTextField_alphaMatteShader(q=True, text=True)
        #

        meshes = self.uiList_projectionMeshes(q=True, allItems=True)
        camera = self.uiTextField_projectionCamera(q=True, text=True)

        if not camera:
            log.warning("|{0}| >> No camera loaded.".format(_str_func))

        if meshes is None or len(meshes) == 0:
            log.warning("|{0}| >> No meshes loaded.".format(_str_func))

        self.uiFunc_setSize("field")

        bgColor = self.generateBtn(q=True, bgc=True)
        origText = self.generateBtn(q=True, label=True)
        self.generateBtn(edit=True, enable=False)
        self.generateBtn(edit=True, label="Generating...")
        self.generateBtn(edit=True, bgc=(1, 0.5, 0.5))

        mc.refresh()

        _options = self.getOptions()

        output_path = os.path.normpath(
            os.path.join(PROJECT.getImagePath(), "sd_output")
        )

        composite_path = None
        composite_string = None

        option = _options["img2img_pass"].lower()
        log.debug("img2img_pass {0}".format(option))

        if option != "none":
            if option == "composite" or option == "merged":
                self.uiFunc_assignMaterial(option, meshes)

                scaleMult = float(self.uiOM_img2imgScaleMultiplier.getValue())
                wantedResolution = (
                    self.resolution[0] * scaleMult,
                    self.resolution[1] * scaleMult,
                )

                log.debug(
                    "rendering composite image at resolution {0}".format(
                        wantedResolution
                    )
                )
                composite_path = rt.renderMaterialPass(
                    camera=camera, resolution=wantedResolution
                )

                log.debug("composite path: {0}".format(composite_path))
                with open(composite_path, "rb") as c:
                    # Read the image data
                    composite_data = c.read()

                    # Encode the image data as base64
                    composite_base64 = base64.b64encode(composite_data)

                    # Convert the base64 bytes to string
                    composite_string = composite_base64.decode("utf-8")

                    c.close()

                _options["init_images"] = [composite_string]
            elif option == "custom":
                custom_image = self.uiTextField_customImage(query=True, text=True)
                log.debug("custom image: {0}".format(custom_image))

                if os.path.exists(custom_image):
                    with open(custom_image, "rb") as c:
                        # Read the image data
                        composite_data = c.read()

                        # Encode the image data as base64
                        composite_base64 = base64.b64encode(composite_data)

                        # Convert the base64 bytes to string
                        composite_string = composite_base64.decode("utf-8")

                        c.close()

                    _options["init_images"] = [composite_string]
            elif option == "render layer":
                outputImage = self.uiFunc_renderLayer(display=False)
                log.debug("render layer: {0}".format(outputImage))

                if outputImage:
                    with open(outputImage, "rb") as c:
                        # Read the image data
                        composite_data = c.read()

                        # Encode the image data as base64
                        composite_base64 = base64.b64encode(composite_data)

                        # Convert the base64 bytes to string
                        composite_string = composite_base64.decode("utf-8")

                        c.close()

                    _options["init_images"] = [composite_string]

        # Get Control Nets
        for i in range(4):
            _controlNetOptions = _options['control_nets'][i]

            if not _controlNetOptions['control_net_enabled']:
                continue
            
            preprocessor = self.controlNets[i]['preprocessor_menu'](q=True, value=True)
            if preprocessor == "none":
                imgMode = None
                if 'depth' in _controlNetOptions["control_net_model"]:
                    imgMode = "depth"
                elif 'normal' in _controlNetOptions["control_net_model"]:
                    imgMode = "normal"                

                depthMat = self.uiFunc_getMaterial(imgMode)

                if not depthMat or not mc.objExists(depthMat):
                    log.warning("|{0}| >> No {1} shader loaded.".format(_str_func, imgMode))
                    # prompt to create one
                    result = mc.confirmDialog(
                        title="No {0} shader loaded".format(imgMode),
                        message="No depth shader loaded. Would you like to create one?",
                        button=["Yes", "No"],
                        defaultButton="Yes",
                        cancelButton="No",
                        dismissString="No",
                    )
                    if result == "Yes":
                        if imgMode == "depth":
                            depthMat, sg = self.uiFunc_makeDepthShader()
                            self.uiFunc_guessDepth()
                        elif imgMode == "normal":
                            depthMat, sg = self.uiFunc_makeNormalShader()

                if mc.objExists(depthMat) and meshes:
                    format = "png"
                    self.uiFunc_assignMaterial(imgMode, meshes)

                    if _options["auto_depth_enabled"] and imgMode == "depth":
                        self.uiFunc_guessDepth()

                    depth_path = rt.renderMaterialPass(
                        fileName="{0}Pass".format(imgMode.capitalize()), camera=camera, resolution=self.resolution
                    )

                    log.debug("{0}_path: {1}".format(imgMode, depth_path))
                    # Read the image data
                    depth_image = Image.open(depth_path)

                    if(imgMode == "depth"):
                        # depth_image = depth_image.filter(ImageFilter.GaussianBlur(3))
                        depth_image = it.addMonochromaticNoise(
                            depth_image, _controlNetOptions["control_net_noise"], 1
                        )

                    # Convert the image data to grayscale
                    depth_image_RGB = depth_image.convert("RGB")

                    # Encode the image data as base64
                    # depth_buffered = BytesIO()
                    with BytesIO() as depth_buffered:
                        depth_image_RGB.save(depth_buffered, format=format)

                        depth_base64 = base64.b64encode(depth_buffered.getvalue())

                        # Convert the base64 bytes to string
                        depth_string = depth_base64.decode("utf-8")

                        _controlNetOptions["control_net_image"] = depth_string
                else:
                    log.warning(
                        "|{0}| >> No depth shader loaded. Disabling Control Net".format(
                            _str_func
                        )
                    )
                    _controlNetOptions["control_net_enabled"] = False
            else:
                control_net_image_path = ""
                if self.controlNets[i]['custom_image_cb'].getValue():
                    control_net_image_path = self.controlNets[i]['custom_image_tf'].getValue()
                
                control_net_image = None

                if not os.path.exists(control_net_image_path):
                    self.uiFunc_assignMaterial("composite", meshes)

                    control_net_image_path = rt.renderMaterialPass(
                        fileName="CustomPass", camera=camera, resolution=self.resolution
                    )

                if os.path.exists(control_net_image_path):
                    with open(control_net_image_path, "rb") as c:
                        # Read the image data
                        composite_data = c.read()

                        # Encode the image data as base64
                        composite_base64 = base64.b64encode(composite_data)

                        # Convert the base64 bytes to string
                        control_net_image = composite_base64.decode("utf-8")

                        _controlNetOptions["control_net_image"] = control_net_image

            _options['control_nets'][i] = _controlNetOptions

        if _options["use_alpha_pass"] and _options["img2img_pass"] != "none" and meshes:
            self.uiFunc_assignMaterial("alphaMatte", meshes)

            alpha_path = rt.renderMaterialPass(
                fileName="AlphaPass", camera=camera, resolution=self.resolution
            )

            log.debug("alpha_path: {0}".format(alpha_path))

            if os.path.exists(alpha_path):
                # Read the image data
                alpha_image = Image.open(alpha_path)

                # Convert the image data to grayscale
                alpha_image_gray = alpha_image.convert("L")

                # Encode the image data as base64
                buffered = BytesIO()
                alpha_image_gray.save(buffered, format="PNG")

                alpha_base64 = base64.b64encode(buffered.getvalue())

                # Convert the base64 bytes to string
                alpha_string = alpha_base64.decode("utf-8")

                _options["mask"] = alpha_string
                _options["mask_blur"] = self.uiIF_maskBlur(query=True, value=True)
                _options["inpainting_mask_invert"] = 1
            else:
                log.warning("|{0}| >> No alpha matte found.".format(_str_func))

        # standardize the output path
        _options["output_path"] = output_path

        cameraInfo = {}
        if camera:
            cameraTransform = mc.listRelatives(camera, parent=True)[0]
            cameraInfo = {
                "position": mc.xform(cameraTransform, q=True, ws=True, t=True),
                "rotation": mc.xform(cameraTransform, q=True, ws=True, ro=True),
                "fov": mc.getAttr(camera + ".focalLength"),
            }

        def get_image_and_update_ui():
            try:
                imagePaths, info = sd.getImageFromAutomatic1111(_options)

                log.debug(f"Generated: {imagePaths} {info}")

                if imagePaths:
                    callbacks = []
                    callbacks.append(
                        {"label": "Make Plane", "function": rt.makeImagePlane}
                    )
                    callbacks.append(
                        {
                            "label": "Set As Custom Image",
                            "function": self.setAsCustomImage,
                        }
                    )
                    callbacks.append(
                        {
                            "label": "Set As Projection",
                            "function": self.assignImageToProjection,
                        }
                    )

                    if display:
                        displayImage(imagePaths, info, callbacks)

                info["camera_info"] = cameraInfo

                self.lastInfo = info

                self.generateBtn(edit=True, enable=True)
                self.generateBtn(edit=True, label=origText)
                self.generateBtn(edit=True, bgc=bgColor)

                return imagePaths, info
            except Exception:
                # display full error in log
                e = traceback.format_exc()
                log.error(e)

                self.generateBtn(edit=True, enable=True)
                self.generateBtn(edit=True, label=origText)
                self.generateBtn(edit=True, bgc=bgColor)

                return [], {"error": e}

        return get_image_and_update_ui()

        # Start a new thread to get the image and update the UI
        # threading.Thread(target=get_image_and_update_ui).start()

    def uiFunc_bakeProjection(self, bakeSelectedOnly=False):
        _str_func = "uiFunc_bakeProjection"
        # self.assignImageToProjection(imagePath, info)

        _batch = self.uiOM_batchMode.getValue() == "Bake Projection"
        _generate = self.uiCB_batchGenerate.getValue() and _batch

        _bakeResolution = (self.uiIF_BakeWidth.getValue(), self.uiIF_BakeHeight.getValue())

        frames = [mc.currentTime(q=True)]
        if _batch:
            frames = range(
                self.uiIF_batchProjectStart.getValue(),
                self.uiIF_batchProjectEnd.getValue()+1,
                self.uiIF_batchProjectStep.getValue(),
            )
        
        meshes = self.uiList_projectionMeshes(query=True, allItems=True)

        if bakeSelectedOnly:
            _sel = mc.ls(sl=True, type="transform")

            meshes = []
            for obj in _sel or []:
                shape = mc.listRelatives(obj, s=True)[0]
                if sd.validateProjectionMesh(shape):
                    meshes.append(shape)

        if not meshes:
            log.error("|{0}| >> No meshes to bake".format(_str_func))
            return

        projectionShader = self.uiFunc_getMaterial("projection", meshes[0])
        alphaShader = self.uiFunc_getMaterial("alphaProjection", meshes[0])

        # store current batch settings
        _batchCount = self.uiIF_batchCount.getValue()
        _batchSize = self.uiIF_batchSize.getValue()

        # set batch settings to only render 1 image since
        # we're going to be baking and just taking the first one
        # generated
        if _generate:
            self.uiIF_batchCount.setValue(1)
            self.uiFunc_setBatchCount("field")
            self.uiIF_batchSize.setValue(1)
            self.uiFunc_setBatchSize("field")

        additionalDictInfo = {}
        camera = self.uiTextField_projectionCamera(query=True, text=True)
        if camera:
            cameraTransform = mc.listRelatives(camera, parent=True)[0]
            additionalDictInfo['bakedcamera_info'] = {
                "position": mc.xform(cameraTransform, q=True, ws=True, t=True),
                "rotation": mc.xform(cameraTransform, q=True, ws=True, ro=True),
                "fov": mc.getAttr(camera + ".focalLength"),
            }

        for frame in frames:
            mc.currentTime(frame)
            mc.refresh()

            if _generate:
                imagePaths, info = self.uiFunc_generateImage(False)
                if imagePaths:
                    self.assignImageToProjection(imagePaths[0], info)

            sd.bakeProjection(meshes, projectionShader, alphaShader, additionalImageProjectionData=additionalDictInfo, resolution=_bakeResolution)

        # restore sd batch settings
        if _generate:
            self.uiIF_batchCount.setValue(_batchCount)
            self.uiFunc_setBatchCount("field")
            self.uiIF_batchSize.setValue(_batchSize)
            self.uiFunc_setBatchSize("field")

        # assign composite shader
        self.uiFunc_assignMaterial("composite")

    # =============================================================================================================
    # >> UI Funcs -- Settings Tab
    # =============================================================================================================
    def uiFunc_makeProjectionCamera(self):
        cam, shape = rt.makeProjectionCamera()
        self.uiTextField_projectionCamera(edit=True, text=shape)

        return shape

    def uiFunc_makeProjectionShader(self):
        _str_func = "uiFunc_makeProjectionShader"
        _camera = self.uiTextField_projectionCamera(query=True, text=True)

        if not mc.objExists(_camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            result = mc.confirmDialog(
                title="No Camera",
                message="No projection camera loaded.  Create one?",
                button=["Yes", "No"],
                defaultButton="Yes",
                cancelButton="No",
                dismissString="No",
            )
            if result == "Yes":
                _camera = self.uiFunc_makeProjectionCamera()
            else:
                return

        shader, sg = rt.makeProjectionShader(_camera)
        self.uiTextField_projectionShader(edit=True, text=shader)

        return shader, sg

    def uiFunc_makeAlphaProjectionShader(self):
        _str_func = "uiFunc_makeAlphaProjectionShader"
        _camera = self.uiTextField_projectionCamera(query=True, text=True)

        if not mc.objExists(_camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            result = mc.confirmDialog(
                title="No Camera",
                message="No projection camera loaded.  Create one?",
                button=["Yes", "No"],
                defaultButton="Yes",
                cancelButton="No",
                dismissString="No",
            )
            if result == "Yes":
                _camera = self.uiFunc_makeProjectionCamera()
            else:
                return

        shader, sg = rt.makeAlphaProjectionShader(_camera)

        depthShader = self.uiTextField_depthShader(query=True, text=True)
        if mc.objExists(depthShader):
            ramp = mc.listConnections(depthShader + ".outColor", type="ramp")
            if ramp:
                mult = mc.listConnections(shader + ".outColorG", type="multiplyDivide")
                if mult:
                    mc.connectAttr(
                        ramp[0] + ".outColorG", mult[0] + ".input2Y", force=True
                    )
                else:
                    mc.connectAttr(
                        ramp[0] + ".outColorG", shader + ".outColorG", force=True
                    )

        self.uiTextField_alphaProjectionShader(edit=True, text=shader)

        return shader, sg

    def uiFunc_makeDepthShader(self):
        _str_func = "uiFunc_makeDepthShader"

        shader, sg = rt.makeDepthShader()
        self.uiTextField_depthShader(edit=True, text=shader)

        alphaShader = self.uiTextField_alphaProjectionShader(query=True, text=True)
        if mc.objExists(alphaShader):
            ramp = mc.listConnections(shader + ".outColor", type="ramp")
            if ramp:
                mult = mc.listConnections(
                    alphaShader + ".outColorG", type="multiplyDivide"
                )
                if mult:
                    mc.connectAttr(
                        ramp[0] + ".outColorG", mult[0] + ".input2Y", force=True
                    )
                else:
                    mc.connectAttr(
                        ramp[0] + ".outColorG", alphaShader + ".outColorG", force=True
                    )

        mc.setAttr(
            shader + ".maxDistance", self.uiFF_maxDepthDistance(query=True, value=True)
        )

        return shader, sg

    def uiFunc_makeNormalShader(self):
        _str_func = "uiFunc_makeNormalShader"

        shader, sg = rt.makeNormalShader()
        self.uiTextField_normalShader(edit=True, text=shader)

        return shader, sg

    def uiFunc_snapCameraFromData(self, cameraData):
        _str_func = "uiFunc_snapCameraFromData"

        log.debug("|{0}| >> cameraData: {1}".format(_str_func, cameraData))

        camera = self.uiTextField_projectionCamera(query=True, text=True)
        if not mc.objExists(camera):
            log.error("|{0}| >> No camera loaded.".format(_str_func))
            return

        if not cameraData:
            log.error("|{0}| >> No camera data loaded.".format(_str_func))
            return

        cameraTransform = mc.listRelatives(camera, parent=True)[0]
        # get camera data

        position = cameraData["position"]
        rotation = cameraData["rotation"]
        fov = cameraData["fov"]

        # set camera data
        mc.setAttr(cameraTransform + ".translateX", position[0])
        mc.setAttr(cameraTransform + ".translateY", position[1])
        mc.setAttr(cameraTransform + ".translateZ", position[2])
        mc.setAttr(cameraTransform + ".rotateX", rotation[0])
        mc.setAttr(cameraTransform + ".rotateY", rotation[1])
        mc.setAttr(cameraTransform + ".rotateZ", rotation[2])

        # set fov
        mc.setAttr(camera + ".focalLength", fov)

    def uiFunc_loadSelectedMeshes(self):
        _str_func = "uiFunc_loadSelectedMeshes"
        log.debug("|{0}| >> ...".format(_str_func))

        sel = mc.ls(sl=True)

        unvalidatedMeshes = []
        validatedMeshes = []

        for obj in mc.ls(sl=True):
            shape = mc.listRelatives(obj, shapes=True, type="mesh")
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
            result = mc.confirmDialog(
                title="Validate Meshes",
                message="The following meshes are not valid for projection. Would you like to validate them?\n\n{0}".format(
                    "\n".join(unvalidatedMeshes)
                ),
                button=["Yes", "No"],
                defaultButton="Yes",
                cancelButton="No",
                dismissString="No",
            )
            if result == "Yes":
                sd.initializeProjectionMeshes(unvalidatedMeshes)
                # append the newly validated meshes to the validatedMeshes list
                validatedMeshes.extend(unvalidatedMeshes)

                itemList = {
                    "projectionCamera": self.uiTextField_projectionCamera.getValue(),
                    "projectionShader": self.uiTextField_projectionShader.getValue(),
                    "alphaProjectionShader": self.uiTextField_alphaProjectionShader.getValue(),
                    "depthShader": self.uiTextField_depthShader.getValue(),
                    "normalShader": self.uiTextField_normalShader.getValue(),
                }

                unvalidatedItems = []
                for item in itemList:
                    if not itemList[item] or not mc.objExists(itemList[item]):
                        unvalidatedItems.append(item)

                if unvalidatedItems:
                    result = mc.confirmDialog(
                        title="Validate Items",
                        message="Some items aren't found. Would you like to create them?\n\n{0}".format(
                            "\n".join(unvalidatedItems)
                        ),
                        button=["Yes", "No"],
                        defaultButton="Yes",
                        cancelButton="No",
                        dismissString="No",
                    )
                    if result == "Yes":
                        for item in unvalidatedItems:
                            if item == "projectionCamera":
                                self.uiFunc_makeProjectionCamera()
                            elif item == "projectionShader":
                                self.uiFunc_makeProjectionShader()
                            elif item == "alphaProjectionShader":
                                self.uiFunc_makeAlphaProjectionShader()
                            elif item == "depthShader":
                                self.uiFunc_makeDepthShader()
                            elif item == "normalShader":
                                self.uiFunc_makeNormalShader()

        if validatedMeshes:
            self.uiList_projectionMeshes(edit=True, append=validatedMeshes)

    def uiFunc_loadAllMeshes(self):
        _str_func = "uiFunc_loadAllMeshes"
        log.debug("|{0}| >> ...".format(_str_func))

        self.uiList_projectionMeshes.clear()

        # find all instances of objects with the relevant attributes
        unvalidatedMeshes = []
        validatedMeshes = []

        for shape in [x.split(".")[0] for x in mc.ls("*.cgmCompositeMaterial")]:
            if shape in unvalidatedMeshes or shape in validatedMeshes:
                continue

            if not sd.validateProjectionMesh(shape):
                unvalidatedMeshes.append(shape)
            else:
                validatedMeshes.append(shape)

        if validatedMeshes:
            self.uiList_projectionMeshes(edit=True, append=validatedMeshes)

    def uiFunc_clearAllMeshes(self):
        _str_func = "uiFunc_clearAllMeshes"
        log.debug("|{0}| >> ...".format(_str_func))
        self.uiList_projectionMeshes.clear()

    def uiFunc_removeSelectedMeshes(self):
        _str_func = "uiFunc_removeSelectedMeshes"
        log.debug("|{0}| >> ...".format(_str_func))

        sel = self.uiList_projectionMeshes(query=True, selectItem=True)
        self.uiList_projectionMeshes(edit=True, removeItem=sel)

    def uiFunc_selectMeshes(self):
        _str_func = "uiFunc_selectMeshes"
        log.debug("|{0}| >> ...".format(_str_func))

        sel = self.uiList_projectionMeshes(query=True, selectItem=True)
        mc.select(sel)

    # =============================================================================================================
    # >> UI Funcs -- Project Tab
    # =============================================================================================================
    def uiFunc_project_setAutoDepth(self, *a):
        _str_func = "uiFunc_project_setAutoDepth"
        self.saveOptionFromUI("auto_depth_enabled", self.uiAutoDepthEnabledCB)

        val = self.uiAutoDepthEnabledCB.getValue()
        self.uiDepthRow(e=True, vis=not val)
                
    def uiFunc_changeAutomatic1111Url(self):
        _str_func = "uiFunc_changeAutomatic1111Url"

        log.debug(_str_func + " start")
        self.saveOption(
            "automatic_url", self.uiTextField_automaticURL(query=True, text=True)
        )

        self.uiFunc_tryAutomatic1111Connect()
        # self.handleReset()

    def uiFunc_setImg2ImgPass(self, *a):
        _str_func = "uiFunc_setImg2ImgPass"
        log.debug("%s %s" % (_str_func, a))

        option = a[0].lower()
        val = option != "none"

        self.img2imgLayout(e=True, vis=val)

        self.customImage_row(e=True, vis=option == "custom")
        self.renderLayer_row(e=True, vis=option == "render layer")
        self.uiAlphaMatteCB(e=True, en=val)

        self.saveOption("img2img_pass", a[0])

    def uiFunc_setAlphaMatteCB(self, *a):
        _str_func = "uiFunc_setAlphaMatteCB"
        log.debug("%s %s" % (_str_func, a))

        val = a[0]

        self.alphaMatteLayout(e=True, vis=val)

        self.saveOption("use_alpha_pass", val)

    def uiFunc_project_handleCustomImageCBChange(self, index):
        self.controlNets[index]['custom_image_row'](e=True, vis=self.controlNets[index]['custom_image_cb'].getValue())
        self.uiFunc_saveControlNetFromUI(index=index)

    def uiFunc_project_handleBatchModeChange(self):
        _str_func = "uiFunc_project_handleBatchModeChange"

        val = self.uiOM_batchMode.getValue()
        self.saveOption("batch_mode", val)

        self.uiFunc_project_updateBatchMode()
        
    def uiFunc_project_updateBatchMode(self):
        _str_func = "uiFunc_project_updateBatchMode"

        val = self.uiOM_batchMode.getValue()

        log.debug("%s %s" % (_str_func, val ))

        self.uiLayout_batchMode_bakeProjection(e=True, vis=val.lower() == "bake projection")
        self.uiMelRow_batchTimeRange(e=True, vis=val.lower() != "none")
        self.uiLayout_batchMode.layout()

    def uiFunc_auto_populate_fields(self):
        _str_func = "uiFunc_auto_populate_fields"

        self.uiFunc_loadAllMeshes()

        for cam in mc.ls("*.cgmCamera"):
            if mc.getAttr(cam) == "projection":
                self.uiTextField_projectionCamera(edit=True, text=cam.split(".")[0])
                break

        for shader in mc.ls("*.cgmShader"):
            if mc.getAttr(shader) == "sd_projection":
                self.uiTextField_projectionShader(edit=True, text=shader.split(".")[0])
                continue
            if mc.getAttr(shader) == "sd_alpha":
                self.uiTextField_alphaProjectionShader(
                    edit=True, text=shader.split(".")[0]
                )
                continue
            if mc.getAttr(shader) == "sd_depth":
                self.uiTextField_depthShader(edit=True, text=shader.split(".")[0])
                continue
            if mc.getAttr(shader) == "sd_normal":
                self.uiTextField_normalShader(edit=True, text=shader.split(".")[0])
                continue

    def uiFunc_makeMaterialFromType(self, materialType):
        if materialType == "projection":
            return self.uiFunc_makeProjectionShader()
        if materialType == "alphaProjection":
            return self.uiFunc_makeAlphaProjectionShader()
        if materialType == "depth":
            return self.uiFunc_makeDepthShader()
        if materialType == "normal":
            return self.uiFunc_makeNormalShader()
        
        log.error("Invalid material type: %s" % materialType)
        return None

    def uiFunc_guessDepth(self):
        _str_func = "uiFunc_guessDepth"
        _camera = self.uiTextField_projectionCamera(query=True, text=True)
        
        if not _camera:
            raise ValueError("{} | No camera".format(_str_func))
        
        _camDag =  VALID.getTransform(_camera)
        
        _targets = self.uiList_projectionMeshes(query=True, allItems=True)
        if not _targets:
            _targets = mc.ls(sl=1)
            
        if not _targets:
            raise ValueError("{} | No Targets".format(_str_func))
            
        
        #print.pprint(vars())
        
        _res = sd.guess_depth_min_max2(_camDag, _targets)

        #self.uiSlider_minDepthDistance.setValue(_res[0])
        
        self.uiFF_maxDepthDistance.setValue(_res[1], False)
        self.uiFF_minDepthDistance.setValue(_res[0],False)
        
        self.uiFunc_setDepth("field")
        
        pass
        
    def uiFunc_setDepth(self, source):
        shader = self.uiFunc_getDepthShader()

        _minDepth = 0.0
        _maxDepth = 0.0

        if shader:
            _minDepth = mc.getAttr("%s.minDistance" % shader)
            _maxDepth = mc.getAttr("%s.maxDistance" % shader)

        if source == "slider":
            _minDepth = self.uiSlider_minDepthDistance(query=True, value=True)
            self.uiFF_minDepthDistance.setValue(_minDepth)

            _maxDepth = self.uiSlider_maxDepthDistance(query=True, value=True)
            self.uiFF_maxDepthDistance.setValue(_maxDepth)

        elif source == "field":
            _minDepth = self.uiFF_minDepthDistance.getValue()
            self.uiSlider_minDepthDistance(edit=True, max=max(100.0, _minDepth))
            self.uiSlider_minDepthDistance(edit=True, value=_minDepth, step=1)

            _maxDepth = self.uiFF_maxDepthDistance.getValue()
            self.uiSlider_maxDepthDistance(edit=True, max=max(100.0, _maxDepth))
            self.uiSlider_maxDepthDistance(edit=True, value=_maxDepth, step=1)

        if shader:
            mc.setAttr("%s.minDistance" % shader, _minDepth)
            mc.setAttr("%s.maxDistance" % shader, _maxDepth)

        self.saveOption("min_depth_distance", _minDepth)
        self.saveOption("max_depth_distance", _maxDepth)

    def uiFunc_setSamples(self, source):
        val = uiFunc_setFieldSlider(
            self.uiIF_samplingSteps, self.uiSlider_samplingSteps, source, 100
        )

        self.saveOption("sampling_steps", val)

    def uiFunc_loadCustomImage(self, textField, saveOption = None):
        _str_func = "uiFunc_loadCustomImage"

        _file = mc.fileDialog2(
            fileMode=1, caption="Select Image File", fileFilter="*.jpg *.jpeg *.png"
        )
        if _file:
            _file = _file[0]
            if not os.path.exists(_file):
                log.error("|{0}| >> File not found: {1}".format(_str_func, _file))
                return False

            textField(edit=True, text=_file)
            if saveOption != None:
                self.saveOption(saveOption, _file)

    def uiFunc_updateRenderLayers(self):
        _str_func = "uiFunc_updateRenderLayers"

        currentRenderLayer = self.uiOM_renderLayer.getValue()

        self.uiOM_renderLayer.clear()

        _layers = mc.ls(type="renderLayer")
        if not _layers:
            log.error("|{0}| >> No render layers found".format(_str_func))
            return False

        for _layer in _layers:
            self.uiOM_renderLayer.append(_layer)
            if _layer == currentRenderLayer:
                self.uiOM_renderLayer.setValue(_layer)

    def uiFunc_setDenoise(self, source):
        val = uiFunc_setFieldSlider(
            self.uiFF_denoiseStrength, self.uiSlider_denoiseStrength, source, 1.0, 0.01
        )

        self.saveOption("denoising_strength", val)

    def uiFunc_setBatchCount(self, source):
        val = uiFunc_setFieldSlider(
            self.uiIF_batchCount, self.uiSlider_batchCount, source, 10
        )

        self.saveOption("batch_count", val)

    def uiFunc_setBatchSize(self, source):
        val = uiFunc_setFieldSlider(
            self.uiIF_batchSize, self.uiSlider_batchSize, source, 8
        )

        self.saveOption("batch_size", val)

    def uiFunc_setCFGScale(self, source):
        val = uiFunc_setFieldSlider(
            self.uiFF_CFGScale, self.uiSlider_CFGScale, source, 30
        )

        self.saveOption("cfg_scale", val)

    def uiFunc_setMaskBlur(self, source):
        val = uiFunc_setFieldSlider(
            self.uiIF_maskBlur, self.uiSlider_maskBlur, source, 100, 1
        )

        self.saveOption("mask_blur", val)

    def uiFunc_updateModelsFromAutomatic(self):
        _str_func = "uiFunc_updateModelsFromAutomatic"

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
            self.uiOM_modelMenu.append(model.get("model_name", model.get("name")))

        return self.models

    def getModelFromName(self, name):
        _str_func = "uiFunc_getModelFromName"

        for model in self.models:
            if model.get("model_name", model.get("name")) == name:
                return model

        return None

    def getModelFromUI(self):
        _str_func = "uiFunc_getModelFromUI"

        name = self.uiOM_modelMenu(query=True, value=True)
        return self.getModelFromName(name)

    def uiFunc_setModelFromUI(self):
        _str_func = "uiFunc_setModelFromUI"
        newModel = self.getModelFromUI()

        bgColor = self.generateBtn(q=True, bgc=True)
        origText = self.generateBtn(q=True, label=True)
        self.generateBtn(edit=True, enable=False)
        self.generateBtn(edit=True, label="Setting New Model...")
        self.generateBtn(edit=True, bgc=(1, 0.5, 0.5))

        mc.refresh()

        sd.setModel(newModel)

        self.generateBtn(edit=True, enable=True)
        self.generateBtn(edit=True, label=origText)
        self.generateBtn(edit=True, bgc=bgColor)

    def uiFunc_updateSamplersFromAutomatic(self):
        _str_func = "uiFunc_updateSamplersFromAutomatic"

        if not self.connected:
            return []

        url = self.uiTextField_automaticURL(query=True, text=True)

        _samplers = sd.getSamplersFromAutomatic1111(url)

        if not _samplers:
            self.uiFunc_setConnected(False)
            return []

        self.uiOM_samplingMethodMenu.clear()
        for sampler in _samplers:
            # if model is a string, continue
            self.uiOM_samplingMethodMenu.append(sampler["name"])

        return _samplers

    def uiFunc_updateControlNetPreprocessorsMenu(self):
        _str_func = "uiFunc_updateControlNetPreprocessorsMenu"

        url = self.uiTextField_automaticURL(query=True, text=True)
        _preprocessors = sd.getControlNetPreprocessorsFromAutomatic1111(url)

        if not _preprocessors:
            self.uiFunc_setConnected(False)
            return []

        for controlNet in self.controlNets:
            controlNet['preprocessor_menu'].clear()
            for _preprocessor in _preprocessors['module_list']:
                controlNet['preprocessor_menu'].append(_preprocessor)

        return _preprocessors

    def uiFunc_changeControlNetPreProcessor(self, index):
        _str_func = "uiFunc_changeControlNetPreProcessor"

        url = self.uiTextField_automaticURL(query=True, text=True)
        self.uiFunc_updateControlNetModelsFromAutomatic(url)

        controlNet = self.controlNets[index]

        arg = controlNet['preprocessor_menu'].getValue()
        log.debug("|{0}| >> arg: {1}".format(_str_func, arg))

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_updateControlNetModelsFromAutomatic(self):
        _str_func = "uiFunc_updateControlNetModelsFromAutomatic"

        url = self.uiTextField_automaticURL(query=True, text=True)
        _models = sd.getControlNetModelsFromAutomatic1111(url)

        if not _models:
            log.error("|{0}| >> No models found".format(_str_func))
            return []

        # get current model
        for controlNet in self.controlNets:

            preprocessor = controlNet['preprocessor_menu'](query=True, value=True)

            filter = preprocessor.split('_')[0]
            if preprocessor == "none":
                filter = ""
            if preprocessor == "segmentation":
                filter = "seg"

            _currentModel = controlNet["model_menu"].getValue()

            controlNet["model_menu"].clear()
            
            controlNet['model_subrow'](e=True, vis=True)
            controlNet['model_row'].layout()
            for _model in _models["model_list"]:
                if filter not in _model:
                    controlNet['model_subrow'](e=True, vis=False)
                    controlNet['model_row'].layout()
                    continue
                
                controlNet["model_menu"].append(_model)
                if _model == _currentModel:
                    controlNet["model_menu"].setValue(_model)

            if controlNet['model_menu'].getValue():
                controlNet['model_subrow'](e=True, vis=True)
            else:
                controlNet['model_subrow'](e=True, vis=False)

        return _models["model_list"]

    def uiFunc_setControlNetWeight(self, source, index):
        uiFF_controlNetWeight = self.controlNets[index]["weight_field"]
        uiSlider_controlNetWeight = self.controlNets[index]["weight_slider"]

        val = uiFunc_setFieldSlider(
            uiFF_controlNetWeight, uiSlider_controlNetWeight, source, 2.0, 0.1
        )

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_setControlNetNoise(self, source, index):
        uiFF_controlNetNoise = self.controlNets[index]["noise_field"]
        uiSlider_controlNetNoise = self.controlNets[index]["noise_slider"]
    
        val = uiFunc_setFieldSlider(
            uiFF_controlNetNoise, uiSlider_controlNetNoise, source, 1.0, 0.1
        )

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_setControlNetGuidanceStart(self, source, index):
        uiFF_controlNetGuidanceStart = self.controlNets[index]["guidance_start_field"]
        uiSlider_controlNetGuidanceStart = self.controlNets[index]["guidance_start_slider"]
        
        val = uiFunc_setFieldSlider(
            uiFF_controlNetGuidanceStart,
            uiSlider_controlNetGuidanceStart,
            source,
            1.0,
            0.1,
        )

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_setControlNetGuidanceEnd(self, source, index):
        uiFF_controlNetGuidanceEnd = self.controlNets[index]["guidance_end_field"]
        uiSlider_controlNetGuidanceEnd = self.controlNets[index]["guidance_end_slider"]

        val = uiFunc_setFieldSlider(
            uiFF_controlNetGuidanceEnd,
            uiSlider_controlNetGuidanceEnd,
            source,
            1.0,
            0.1,
        )

        self.uiFunc_saveControlNetFromUI(index)

    def uiFunc_getLastSeed(self):
        lastSeed = -1
        if "seed" in self.lastInfo.keys():
            lastSeed = self.lastInfo["seed"]

        # set seed ui element to last seed
        self.uiIF_RandomSeed.setValue(lastSeed)

        return lastSeed

    # =============================================================================================================
    # >> UI Funcs -- Edit Tab
    # =============================================================================================================
    def uiFunc_edit_loadProjectionMesh(self, *a):
        _str_func = "uiFunc_edit_loadProjectionMesh"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)
        log.debug("{0}".format(a))

        sel = mc.ls(sl=True)
        if sel:
            shape = sel[0]
            if mc.ls(sel[0], st=True)[1] == "transform":
                shape = mc.listRelatives(sel[0], s=True)[0]
            if shape and sd.validateProjectionMesh(shape):
                self.activeProjectionMesh = shape
                self.uiOM_edit_projectionMesh.setValue(shape)

        self.uiFunc_refreshEditTab()

    def uiFunc_edit_updateActiveMesh(self, *a):
        _str_func = "uiFunc_edit_updateActiveMesh"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)
        log.debug("{0}".format(a))

        try:
            self.uiOM_edit_projectionMesh.setValue(self.activeProjectionMesh)
        except:
            log.debug("|{0}| >> No active mesh".format(_str_func))
            sel = mc.ls(sl=True)
            if sel:
                shape = sel[0]
                if mc.ls(sel[0], st=True)[1] == "transform":
                    shape = mc.listRelatives(sel[0], s=True)[0]
                if shape and sd.validateProjectionMesh(shape):
                    log.debug(
                        "|{0}| >> Using selected mesh - {1}".format(_str_func, shape)
                    )
                    self.activeProjectionMesh = shape
                    self.uiOM_edit_projectionMesh.setValue(self.activeProjectionMesh)
            else:
                self.activeProjectionMesh = self.uiOM_edit_projectionMesh.getValue()

        mc.select(self.activeProjectionMesh, r=True)

    def uiFunc_edit_changeProjectionMesh(self, *a):
        _str_func = "uiFunc_edit_changeProjectionMesh"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)
        log.debug("{0}".format(a))

        self.activeProjectionMesh = self.uiOM_edit_projectionMesh.getValue()
        log.debug(
            "|{0}| >> activeProjectionMesh: {1}".format(
                _str_func, self.activeProjectionMesh
            )
        )

        self.activePass = None
        self.uiFunc_refreshEditTab()

    def uiFunc_edit_changePass(self, *a):
        self.activePass = self.uiOM_edit_pass.getValue()
        self.uiFunc_assignMaterial(self.activePass)
        self.uiFunc_refreshEditTab()

    def uiFunc_refreshEditTab(self):
        _str_func = "uiFunc_refreshEditTab"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)

        self.editColumn.clear()
        self.editColumn = self.buildColumn_edit(None, inside=self.editColumn)

    def uiFunc_updateLayerVisibility(self):
        _str_func = "uiFunc_updateLayerVisibility"

        log.debug("{0} >> {1}".format(_str_func, self.layers))

        soloLayers = []
        for layer in self.layers:
            if layer["solo_cb"].getValue():
                soloLayers.append(layer)

        for layer in self.layers:
            visible = layer["visible_cb"].getValue()
            solo = layer["solo_cb"].getValue()
            if soloLayers:
                visible = layer in soloLayers

            visAttr = "%s.inputs[%i].isVisible" % (
                layer["layeredTexture"],
                layer["index"],
            )
            log.debug("{0} {1}".format(visAttr, visible))
            mc.setAttr(visAttr, visible)

    def uiFunc_edit_moveLayer(self, layeredTexture, index, direction):
        _str_func = "uiFunc_edit_moveLayer"

        log.debug(
            "|{0}| >> {1}, moving {2}, ltIndex : {3}".format(
                _str_func, index, direction, self.layers[index]["index"]
            )
        )

        # ensure that we are not moving the first or last layer in self.layers
        if index == 0 and direction == -1:
            log.warning("|{0}| >> Cannot move first layer".format(_str_func))
            return
        if index == len(self.layers) - 1 and direction == 1:
            log.warning("|{0}| >> Cannot move last layer".format(_str_func))
            return

        log.debug(
            "|{0}| >> reordering {1} to {2}".format(
                _str_func,
                self.layers[index]["index"],
                self.layers[index + direction]["index"],
            )
        )
        # rt.reorderLayeredTexture(layeredTexture, self.layers[index]['index'], self.layers[index + direction]['index'])
        rt.reorderLayeredTexture(layeredTexture, index, index + direction)

        # # get current layer
        # currentLayer = self.layers[index]
        # currentLayer['index'] += direction

        # # get other layer
        # otherLayer = self.layers[index + direction]
        # otherLayer['index'] -= direction

        # # swap layers
        # self.layers[index] = otherLayer
        # self.layers[index + direction] = currentLayer

        # # refresh ui
        self.uiFunc_refreshEditTab()

    def uiFunc_edit_restoreComposite(self, compositeShader, layeredTexture):
        _str_func = "uiFunc_restoreComposite"

        if not compositeShader:
            return

        mc.connectAttr(
            layeredTexture + ".outColor", compositeShader + ".outColor", f=True
        )

        self.uiFunc_refreshEditTab()

    def uiFunc_edit_deleteLayer(self, layerIndex):
        _str_func = "uiFunc_edit_deleteLayer"

        if layerIndex == None:
            return

        layeredTexture = self.layers[layerIndex]["layeredTexture"]
        if not layeredTexture:
            return

        mc.removeMultiInstance(
            layeredTexture + ".inputs[{}]".format(self.layers[layerIndex]["index"]),
            b=True,
        )

        sd.clean_and_reorder_layeredTexture(layeredTexture)

        self.uiFunc_refreshEditTab()

    def uiFunc_edit_mergeComposite(self, shader, mergedShader):
        sd.mergeCompositeShaderToImage(shader, mergedShader)

        # assign merged shader
        self.uiFunc_assignMaterial("composite")
        self.uiFunc_refreshEditTab()

    def uiFunc_edit_copy(self, index):
        _str_func = "uiFunc_edit_copy"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)

        remapColorNodeData = []
        for i in range(len(self.layers[index]["remapColorNodes"])):
            remapColorNodeData.append(
                {
                    **sd.copyRemapColorValues(self.layers[index]["remapColorNodes"][i]),
                    "type": "default",
                }
            )

        self.layerCopyData.setValue(json.dumps(remapColorNodeData))

    def uiFunc_edit_paste(self, index):
        _str_func = "uiFunc_edit_paste"
        log.debug("|{0}| >>  ".format(_str_func) + "-" * 80)

        valueDict = json.loads(self.layerCopyData.getValue() or "{}")
        if not valueDict:
            return

        for i in range(len(self.layers[index]["remapColorNodes"])):
            sd.pasteRemapColorValues(
                self.layers[index]["remapColorNodes"][i], valueDict[i]
            )

    # ===========================================================================
    # Image Viewer Callbacks
    # ===========================================================================
    def setAsCustomImage(self, imagePath, info):
        _str_func = "setAsCustomImage"

        if not imagePath:
            log.error("|{0}| >> No image path given.".format(_str_func))
            return

        # set the image path in the ui
        self.uiFunc_setImg2ImgPass('Custom')
        self.uiTextField_customImage(edit=True, text=imagePath)

    def assignImageToProjection(self, imagePath, info):
        _str_func = "assignImageToProjection"

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
            result = mc.confirmDialog(
                title="Missing Items",
                message=_str,
                button=["Yes", "No"],
                defaultButton="Yes",
                cancelButton="No",
                dismissString="No",
            )
            if result == "Yes":
                if not mc.objExists(projectionCamera):
                    projectionCamera = self.uiFunc_makeProjectionCamera()
                if not mc.objExists(projectionShader):
                    projectionShader, sg = self.uiFunc_makeProjectionShader()
            else:
                log.error(
                    "|{0}| >> No projection shader to assign image to".format(_str_func)
                )
                return

        # assign projection shader
        self.uiFunc_assignMaterial("projection")
        rt.assignImageToProjectionShader(projectionShader, imagePath, info)

    def uiFunc_viewImage(self):
        _str_func = "uiFunc_viewImage"

        files = mc.ls(sl=True, type="file")
        imagePaths = []
        data = {}
        for file in files:
            path = mc.getAttr(file + ".fileTextureName")
            imagePaths.append(path)
            data[file] = path

        if imagePaths:
            iv.ui(imagePaths, data)
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))

    def uiFunc_viewImageFromPath(self, path):
        _str_func = "uiFunc_viewImageFromPath"
        log.debug("%s %s" % (_str_func, path))

        if os.path.exists(path):
            iv.ui([path], {"outputImage": path})
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))
            return

    def uiFunc_openExplorerPath(self, path):
        _str_func = "uiFunc_openExplorerPath"
        log.debug("%s %s" % (_str_func, path))

        if os.path.exists(path):
            os.startfile(path)
        else:
            log.warning("|{0}| >> No images selected.".format(_str_func))
            return

    def uiFunc_bakeLatentSpaceImageOnSelected(self, imagePath, info):
        _str_func = "uiFunc_bakeLatentSpaceImageOnSelected"
        log.debug("|{0}| >> ...".format(_str_func))
        log.debug("|imagePath| >> ... {0}".format(imagePath))
        log.debug("|info| >> ... {0}".format(info))

        if not os.path.exists(imagePath):
            log.error("|{0}| >> Contact Sheet path not valid. No image found.".format(_str_func))
            return
        
        if not 'latent_batch' in info or not info['latent_batch']:
            log.error("|{0}| >> Latent Batch is not enabled. Proper data is not found.".format(_str_func))
            return

        _sel = mc.ls(sl=True, type="transform")

        camera = self.uiTextField_projectionCamera(query=True, text=True)

        meshes = []
        for obj in _sel or []:
            shape = mc.listRelatives(obj, s=True)[0]
            if sd.validateProjectionMesh(shape):
                meshes.append(shape)

        if not meshes:
            log.error("|{0}| >> No meshes to bake. Please select valid meshes to bake onto".format(_str_func))
            return

        projectionShader = self.uiFunc_getMaterial("projection", meshes[0])
        alphaShader = self.uiFunc_getMaterial("alphaProjection", meshes[0])

        contact_sheet = Image.open(imagePath)
        resolution = it.getResolutionFromContactSheet(contact_sheet, info['latent_batch_num_images'])

        split_images = it.splitContactSheet(contact_sheet, resolution=resolution, image_path=imagePath)

        log.debug("|meshes| >> ... {0}".format(meshes))
        log.debug("|projectionShader| >> ... {0}".format(projectionShader))
        log.debug("|alphaProjection| >> ... {0}".format(alphaShader))
        log.debug("|split_images| >> ... {0}".format(split_images))     

        width = self.uiIF_BakeWidth(query=True, value=True)
        height = self.uiIF_BakeHeight(query=True, value=True)

        for i in range(info['latent_batch_num_images']):
            mc.currentTime(info['latent_batch_camera_info'][i]['frame'])
            mc.refresh()

            self.assignImageToProjection(split_images[i], info)

            log.debug("|assigning to projection| >> ... {0}".format(split_images[i]))   

            self.uiFunc_snapCameraFromData(info['latent_batch_camera_info'][i])

            camTransform = mc.listRelatives(camera, parent=True)[0]
            mc.setAttr('{0}.sx'.format(camTransform), 1.0)
            mc.setAttr('{0}.sy'.format(camTransform), 1.0)
            mc.setAttr('{0}.sz'.format(camTransform), 1.0)

            sd.bakeProjection(meshes, projectionShader, alphaShader, resolution=(width, height))
        
        # assign composite shader
        self.uiFunc_assignMaterial("composite")

        return split_images

    def generateFromImageData(self, imagePath, info):
        pass

    # =============================================================================================================
    # >> OPTIONS
    # =============================================================================================================

    def getOptions(self):
        _str_func = "getOptions"

        _options = {}
        _options["automatic_url"] = self.uiTextField_automaticURL.getValue()
        _options["prompt"] = self.uiTextField_prompt.getValue()
        _options["negative_prompt"] = self.uiTextField_negativePrompt.getValue()
        _options["seed"] = self.uiIF_RandomSeed.getValue()
        _options["width"] = self.uiIF_Width.getValue()
        _options["height"] = self.uiIF_Height.getValue()
        _options["sampling_method"] = self.uiOM_samplingMethodMenu.getValue()
        _options["sampling_steps"] = self.uiIF_samplingSteps.getValue()
        _options["min_depth_distance"] = self.uiFF_minDepthDistance.getValue()
        _options["max_depth_distance"] = self.uiFF_maxDepthDistance.getValue()
        _options["denoising_strength"] = self.uiFF_denoiseStrength.getValue()
        _options["img2img_pass"] = self.uiOM_passMenu.getValue()
        _options["img2img_custom_image"] = self.uiTextField_customImage.getValue()
        _options["use_alpha_pass"] = self.uiAlphaMatteCB.getValue()
        _options["mask_blur"] = self.uiIF_maskBlur.getValue()
        _options["batch_count"] = self.uiIF_batchCount.getValue()
        _options["batch_size"] = self.uiIF_batchSize.getValue()
        _options["cfg_scale"] = self.uiFF_CFGScale.getValue()
        _options["auto_depth_enabled"] = self.uiAutoDepthEnabledCB.getValue()

        _options["control_nets"] = self.uiFunc_getControlNets()

        # _options["control_net_enabled"] = self.uiControlNetEnabledCB.getValue()
        # _options["control_net_low_v_ram"] = self.uiControlNetLowVRamCB.getValue()
        # _options[
        #     "control_net_preprocessor"
        # ] = self.uiOM_ControlNetPreprocessorMenu.getValue()
        # _options["control_net_model"] = self.uiOM_ControlNetModelMenu.getValue()
        # _options["control_net_weight"] = self.uiFF_controlNetWeight.getValue()
        # _options["control_net_noise"] = self.uiFF_controlNetNoise.getValue()
        # _options[
        #     "control_net_guidance_start"
        # ] = self.uiFF_controlNetGuidanceStart.getValue()
        # _options[
        #     "control_net_guidance_end"
        # ] = self.uiFF_controlNetGuidanceEnd.getValue()


        return _options

    def saveOptionFromUI(self, option, element):
        _str_func = "saveOptionFromUI"

        log.debug(
            "|{0}| >> option: {1} | element: {2} | value: {3}".format(
                _str_func, option, element, element.getValue()
            )
        )

        if not self._initialized:
            return

        _options = json.loads(self.config.getValue() or "{}")
        _options[option] = element.getValue()
        self.config.setValue(json.dumps(_options))

    def saveOption(self, option, value):
        _str_func = "saveOption"

        if not self._initialized:
            return

        log.debug("|{0}| >> option: {1} | value: {2}".format(_str_func, option, value))

        _options = json.loads(self.config.getValue() or "{}")
        _options[option] = value
        self.config.setValue(json.dumps(_options))

    def saveOptions(self):
        _str_func = "saveOptions"

        if not self._initialized:
            return

        _options = {}

        try:
            _options = self.getOptions()
        except:
            log.error("|{0}| >> Error: Failed to save options".format(_str_func))
            return

        self.config.setValue(json.dumps(_options))

        self.toolOptionsVar.setValue(json.dumps(self.toolOptions))

        log.debug("saving {0}".format(_options))

    def loadOptions(self, options=None):
        _str_func = "loadOptions"

        log.debug("|{0}| >> ...".format(_str_func))

        mc.refresh()

        if not self._initialized:
            return

        _options = {}
        if options:
            _options = options
        else:
            _options = (
                json.loads(self.config.getValue())
                if self.config.getValue()
                else _defaultOptions
            )

        log.debug("|{0}| >> loaded _options: {1}".format(_str_func, _options))

       # go through options and set default if not found
        for key in _defaultOptions:
            if key not in _options:
                _options[key] = _defaultOptions[key]
                log.debug(
                    "|{0}| >> key not found: {1} setting to default: {2}".format(
                        _str_func, key, _defaultOptions[key]
                    )
                )

        log.debug("loading options:\n%s"%(str(_options)))

        self.uiIF_BakeWidth(e=True, v=_options["bake_width"])
        self.uiIF_BakeHeight(e=True, v=_options["bake_height"])
        self.uiFunc_setBakeSize("field")

        # load model from automatic
        sdModels = sd.getModelsFromAutomatic1111(_options["automatic_url"])
        sdOptions = sd.getOptionsFromAutomatic(_options["automatic_url"])

        if self.uiOM_modelMenu and sdModels and sdOptions:
            for model in sdModels:
                if model["title"] == sdOptions.get("sd_model_checkpoint",""):
                    self.uiOM_modelMenu(edit=True, value=model.get("model_name", model.get("name")))
                    break

        # iterate through options dict and set default from self._defaultOptions if not found
        for key in _defaultOptions:
            if key not in _options:
                log.warning(
                    "|{0}| >> key not found: {1} setting to default: {2}".format(
                        _str_func, key, _defaultOptions[key]
                    )
                )
                _options[key] = _defaultOptions[key]

        self.uiTextField_automaticURL(edit=True, text=_options["automatic_url"])
        self.uiTextField_prompt(edit=True, text=_options["prompt"])
        self.uiTextField_negativePrompt(edit=True, text=_options["negative_prompt"])
        self.uiIF_RandomSeed.setValue(int(_options["seed"]))
        log.debug(
            "Seed is: %s"
            % (str(_options["seed"]) if "seed" in _options else "No Seed Option")
        )
        self.uiIF_Width(edit=True, v=_options["width"])
        self.uiIF_Height(edit=True, v=_options["height"])
        if "sampling_method" in _options:
            # get options from menu
            _samplingMethodMenu = (
                self.uiOM_samplingMethodMenu(query=True, itemListLong=True) or []
            )
            for item in _samplingMethodMenu:
                if mc.menuItem(item, q=True, label=True) == _options["sampling_method"]:
                    self.uiOM_samplingMethodMenu(
                        edit=True, value=_options["sampling_method"]
                    )
                    break
        else:
            log.warning(
                "|{0}| >> Failed to find sampling method in options".format(_str_func)
            )

        self.uiFF_CFGScale.setValue(_options["cfg_scale"])
        self.uiFunc_setCFGScale("field")

        self.uiIF_batchCount.setValue(_options["batch_count"])
        self.uiIF_batchSize.setValue(_options["batch_size"])
        self.uiFunc_setBatchSize("field")
        self.uiFunc_setBatchCount("field")

        self.uiIF_samplingSteps.setValue(_options["sampling_steps"])
        self.uiFF_minDepthDistance.setValue(_options["min_depth_distance"])
        self.uiFF_maxDepthDistance.setValue(_options["max_depth_distance"])
        self.uiFF_denoiseStrength.setValue(_options["denoising_strength"])

        self.uiOM_img2imgScaleMultiplier.setValue(
            str(_options["img2img_scale_multiplier"])
        )

        passOptions = [
            mc.menuItem(x, query=True, label=True)
            for x in self.uiOM_passMenu(query=True, itemListLong=True)
        ]
        if _options["img2img_pass"] not in passOptions:
            _options["img2img_pass"] = passOptions[0]

        self.uiOM_passMenu.setValue(_options["img2img_pass"])
        self.uiAlphaMatteCB.setValue(_options["use_alpha_pass"])
        self.uiTextField_customImage.setValue(_options["img2img_custom_image"])
        self.uiIF_maskBlur.setValue(_options["mask_blur"])

        self.uiFunc_setImg2ImgPass(_options["img2img_pass"])
        self.uiFunc_setAlphaMatteCB(_options["use_alpha_pass"])

        if not sdModels:
            self.projectColumn(edit=True, enable=False)
        
        self.uiAutoDepthEnabledCB.setValue(_options["auto_depth_enabled"])
        self.uiFunc_project_setAutoDepth()

        self.uiOM_batchMode.setValue(_options["batch_mode"])
        
        self.uiIF_batchProjectStart.setValue(_options.get("batch_min_time", 0))
        self.uiIF_batchProjectEnd.setValue(_options.get("batch_max_time", int(mc.playbackOptions(q=True, maxTime=True))))
        self.uiIF_batchProjectStep.setValue(_options.get("batch_step_time", 1))

        self.uiFunc_project_updateBatchMode()

        # Load Control Nets
        for i, _controlNetOptions in enumerate(_options["control_nets"]):
            _controlNet = self.controlNets[i]

            _controlNet['enabled_cb'].setValue(_controlNetOptions["control_net_enabled"])
            _controlNet['low_vram_cb'].setValue(_controlNetOptions["control_net_low_v_ram"])

            hasCustomImage = "control_net_custom_image_path" in _controlNetOptions.keys() and _controlNetOptions["control_net_custom_image_path"] != ""
            _controlNet['custom_image_cb'].setValue(hasCustomImage)
            
            _controlNet['frame'](e=True, bgc = self.GREEN if _controlNetOptions["control_net_enabled"] else self.GRAY)

            if "control_net_preprocessor" in _controlNetOptions:
                _controlNetPreprocessors = (
                    _controlNet['preprocessor_menu'](query=True, itemListLong=True)
                    or []
                )
                for item in _controlNetPreprocessors:
                    if (
                        mc.menuItem(item, q=True, label=True)
                        == _controlNetOptions["control_net_preprocessor"]
                    ):
                        _controlNet['preprocessor_menu'](
                            edit=True, value=_controlNetOptions["control_net_preprocessor"]
                        )
                        break
            
            if "control_net_model" in _controlNetOptions:
                _controlNetModels = (
                    _controlNet['model_menu'](query=True, itemListLong=True) or []
                )
                for item in _controlNetModels:
                    if (
                        mc.menuItem(item, q=True, label=True)
                        == _controlNetOptions["control_net_model"]
                    ):
                        _controlNet['model_menu'](
                            edit=True, value=_controlNetOptions["control_net_model"]
                        )
                        break
            else:
                log.warning(
                    "|{0}| >> Failed to find control net model in options".format(_str_func)
                )
            
            if "control_net_custom_image_path" in _controlNetOptions:
                _controlNet['custom_image_tf'].setValue(_controlNetOptions["control_net_custom_image_path"])
            _controlNet['custom_image_row'](e=True, vis=hasCustomImage)

            _controlNet['weight_field'].setValue(_controlNetOptions["control_net_weight"])
            _controlNet['noise_field'].setValue(_controlNetOptions["control_net_noise"])
            _controlNet['guidance_start_field'].setValue(
                _controlNetOptions["control_net_guidance_start"]
            )
            _controlNet['guidance_end_field'].setValue(_controlNetOptions["control_net_guidance_end"])

            self.uiFunc_setControlNetWeight("field", i)
            self.uiFunc_setControlNetNoise("field", i)
            self.uiFunc_setControlNetGuidanceEnd("field", i)
            self.uiFunc_setControlNetGuidanceStart("field", i)
            self.uiFunc_updateControlNetModelsFromAutomatic()


def uiFunc_setFieldSlider(field, slider, source, maxVal=100, step=1):
    _value = 0

    if source == "slider":
        _value = slider(query=True, value=True)
        field.setValue(_value)
    elif source == "field":
        _value = field.getValue()
        slider(edit=True, max=max(maxVal, _value))
        slider(edit=True, value=_value, step=step)

    return _value


def displayImage(imagePaths, data={}, callbackData=[]):
    log.debug(f"Displaying images: {imagePaths}")
    iv.ui(imagePaths, data, callbackData)


def uiFunc_loadTextFieldWithShape(element, enforcedType=None):
    _str_func = "uiFunc_loadTextFieldWithShape"
    _sel = mc.ls(sl=True)
    _meshes = []
    if _sel:
        _meshes = mc.listRelatives(_sel[0], shapes=True, type=enforcedType)

    if _meshes:
        element(edit=True, text=_meshes[0])
    else:
        log.warning("|{0}| >> Nothing selected.".format(_str_func))
        element(edit=True, text="")


def uiFunc_loadTextFieldWithSelected(element, enforcedType=None):
    _str_func = "uiFunc_loadTextFieldWithSelected"
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


def uiFunc_selectItemFromTextField(element):
    _str_func = "uiFunc_selectItemFromTextField"
    _item = element(query=True, text=True)
    if mc.objExists(_item):
        mc.select(_item)


def findNodeInChain(attribute, node_type):
    connected_nodes = mc.listConnections(attribute, source=True, destination=False)

    if not connected_nodes:
        return None

    for connected_node in connected_nodes:
        if mc.nodeType(connected_node) == node_type:
            return connected_node
        else:
            output_attrs = mc.listAttr(
                connected_node, output=True, multi=True, connectable=True
            )
            if output_attrs:
                for output_attr in output_attrs:
                    full_attr = connected_node + "." + output_attr
                    found_node = findNodeInChain(full_attr, node_type)
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
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        new_img.save(f.name)
        new_temp_file_path = f.name

    # Update the image control with the new image
    return new_temp_file_path


def uiFunc_updateChannelGradient(dragControl, dropControl, messages, x, y, dragType):
    log.debug(
        f"uiFunc_updateChannelGradient {dragControl} {dropControl} {messages} {x} {y} {dragType}"
    )


def uiFunc_debug_clearData(self):
    _str_func = "uiFunc_debug_clearData"
    log.debug("|{0}| >> ...".format(_str_func))

    mc.optionVar(remove="cgmVar_sdui_config")
    mc.optionVar(remove="cgmVar_sdui_last_config")
    mc.optionVar(remove="cgmVar_projectCurrent")
    mc.optionVar(remove="cgmVar_sceneUI_category")
    mc.optionVar(remove="cgmVar_sceneUI_last_asset")
