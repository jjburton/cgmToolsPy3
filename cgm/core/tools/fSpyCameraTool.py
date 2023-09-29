"""
------------------------------------------
fSpyCameraTool: cgm.core.tools
Author: David Bokser
email: cgmonks.info@gmail.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
Tool to convert fSpy camera data to a camera in maya.

Original function made by JustinPedersen under the MIT license
and refactored to use maya.cmds instead of pymel
================================================================
"""
# From Python =============================================================
import json
import os
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
mUI = cgmUI.mUI

from cgm.core import cgm_General as cgmGEN

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='fSpy Camera Importer'

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__.replace(" ", ""))    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE = 425,190
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
        

    def buildColumn_main(self,parent, asScroll = False):
        if asScroll:
            _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
        else:
            _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
        
        # >>> JSON Data
        self.json_row = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(self.json_row, w=5)
        mUI.MelLabel(self.json_row, l="JSON File:", align="right")
        self.uiTextField_json = mUI.MelTextField(
            self.json_row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(self.json_row, w=5)
        self.json_row.setStretchWidget(self.uiTextField_json)
        cgmUI.add_Button(
            self.json_row, "Load", cgmGEN.Callback(self.load_file, self.uiTextField_json, 'Select JSON File')
        )
        mUI.MelSpacer(self.json_row, w=5)
        self.json_row.layout()

        # >>> Image
        self.image_row = mUI.MelHSingleStretchLayout(
            _inside, expand=True, ut="cgmUISubTemplate"
        )
        mUI.MelSpacer(self.image_row, w=5)
        mUI.MelLabel(self.image_row, l="Image:", align="right")
        self.uiTextField_image = mUI.MelTextField(
            self.image_row,
            backgroundColor=[1, 1, 1],
            h=20,
            ut="cgmUITemplate",
            w=50,
            editable=True,
            # ec = lambda *a:self._UTILS.puppet_doChangeName(self),
            annotation="Our base object from which we process things in this tab...",
        )
        mUI.MelSpacer(self.image_row, w=5)
        self.image_row.setStretchWidget(self.uiTextField_image)
        cgmUI.add_Button(
            self.image_row, "Load",cgmGEN.Callback(self.load_file, self.uiTextField_image, 'Select Image File')
        )
        mUI.MelSpacer(self.image_row, w=5)
        self.image_row.layout()

        mUI.MelSpacer(_inside, w=5, h=10)

        # Generate Button
        #
        _row = mUI.MelHLayout(_inside, ut="cgmUISubTemplate", padding=10)

        self.loadBtn = cgmUI.add_Button(
            _row,
            "Import Camera",
            cgmGEN.Callback(self.create_camera_and_plane_ui, self),
            "Import Camera",
            h=50,
        )

        _row.layout()

        mUI.MelSpacer(_inside, w=5, h=10)

        return _inside
 
    def load_file(self, field, caption=""):
        filepath = mc.fileDialog2(fileMode=1, caption=caption)
        if filepath:
            field(edit=True, text=filepath[0])
        
    def create_camera_and_plane_ui(self, *args):
        json_path = self.uiTextField_json.getValue()
        image_path = self.uiTextField_image.getValue()
        
        if not os.path.exists(json_path) or not os.path.exists(image_path):
            mc.warning('Invalid paths provided for JSON or Image.')
            return
            
        create_camera_and_plane(json_path, image_path)

def create_camera_and_plane(json_path, image_path):
    """
    Create a camera and image plane given a json with data generated from fSpy.
    :param str json_path: full path to the json.
    :param str image_path: full or relative path to the image to use.
    :return: A dictionary containing the newly created nodes in the following format:
            {'camera': (camera_transform, camera_shape),
            'image_plane': (image_transform, image_shape),
            'root': group}
    :rtype: dict
    """
    with open(json_path) as json_file:
        data = json.load(json_file)
    
    group = mc.group(em=True, n='projected_camera_grp_001')
    
    camera_transform, camera_shape = mc.camera()
    mc.parent(camera_transform, group)
    
    matrix = mc.createNode('fourByFourMatrix', n='cameraTransform_fourByFourMatrix')
    decompose_matrix = mc.createNode('decomposeMatrix', n='cameraTransform_decomposeMatrix')
    mc.connectAttr(matrix + '.output', decompose_matrix + '.inputMatrix')
    mc.connectAttr(decompose_matrix + '.outputTranslate', camera_transform + '.translate')
    mc.connectAttr(decompose_matrix + '.outputRotate', camera_transform + '.rotate')
    
    matrix_rows = [['in00', 'in10', 'in20', 'in30'],
                   ['in01', 'in11', 'in21', 'in31'],
                   ['in02', 'in12', 'in22', 'in32'],
                   ['in03', 'in13', 'in23', 'in33']]
    
    for i, matrix_list in enumerate(data['cameraTransform']['rows']):
        for value, attr in zip(matrix_list, matrix_rows[i]):
            mc.setAttr(matrix + '.' + attr, value)
            
    image_transform, image_shape = mc.imagePlane(camera=camera_transform)
    mc.setAttr(image_shape + '.imageName', image_path, type='string')
    
    mc.delete([matrix, decompose_matrix])
    
    attrs = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ', 'scaleX', 'scaleY', 'scaleZ']
    for attr in attrs:
        mc.setAttr(camera_transform + '.' + attr, lock=True)
        mc.setAttr(image_transform + '.' + attr, lock=True)
        
    return {'camera': (camera_transform, camera_shape),
            'image_plane': (image_transform, image_shape),
            'root': group}
