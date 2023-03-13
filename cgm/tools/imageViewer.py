"""
------------------------------------------
baseTool: cgm.core.tools
Author: Josh Burton
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
import tempfile
from PIL import Image

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

#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='imageViewer'

class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)    
    WINDOW_TITLE = '{1} - {0}'.format(__version__,__toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created  
    DEFAULT_SIZE =  550,675
    TOOLNAME = '{0}.ui'.format(__toolname__)
    
    def insert_init(self,*args,**kws):
        _str_func = '__init__[{0}]'.format(self.__class__.TOOLNAME)            
        log.info("|{0}| >>...".format(_str_func))        

        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))
        log.info(self.__call__(q=True, title=True))

        self.imageData = args[1]
        self.index = 0

        self.callbackLabel, self.callback = args[2]

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
        _column = buildColumn_main(self,_MainForm,False)
        _imageColumn = buildColumn_image(self,_MainForm,True)
    
        _row_cgm = cgmUI.add_cgmFooter(_MainForm)            
        _MainForm(edit = True,
                  af = [(_column,"top",0),
                        (_column,"left",0),
                        (_column,"right",0), 
                        (_imageColumn,"left",0),
                        (_imageColumn,"right",0),
                        (_row_cgm,"left",0),
                        (_row_cgm,"right",0),                        
                        (_row_cgm,"bottom",0),
    
                        ],
                  ac = [(_imageColumn,"bottom",0,_row_cgm),
                        (_imageColumn,"top",0,_column),
                        ],
                  attachNone = [(_row_cgm,"top")])   

        updateUI(self)

def buildColumn_main(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    
    #>>> Properties
    #_row = mUI.MelHLayout(_inside,expand = False,ut = 'cgmUISubTemplate', padding=5)
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate')
    mUI.MelSpacer(_row,w = 5)
    cgmUI.add_Button(_row,'<<', lambda *a:uiFunc_prevImage(self))

    self.indexLabel = mUI.MelLabel(_row,l='Image 1/1',align='right')

    cgmUI.add_Button(_row,'>>', lambda *a:uiFunc_nextImage(self))

    _row.setStretchWidget( mUI.MelSeparator(_row, w=2) )

    mUI.MelLabel(_row,l='Scale:',align='right')

    _scaleOptions = [10, 25, 50, 75, 100]
    self.uiOM_SizeMenu = mUI.MelOptionMenu(_row,useTemplate = 'cgmUITemplate', changeCommand=cgmGEN.Callback(updateUI,self))
    for percent in _scaleOptions:
        self.uiOM_SizeMenu.append('{}%'.format(percent))

    # Open the image and get its dimensions
    with Image.open(self.imageData[self.index]['image_path']) as img:
        width = img.width

    closest_scale = 100
    min_distance = float('inf')

    for option in _scaleOptions:
        scale = width * (option/100.0)
        distance = abs(scale - 512)
        if distance < min_distance:
            min_distance = distance
            closest_scale = option
    
    self.uiOM_SizeMenu( e=True, value='{}%'.format(closest_scale))

    #_row.setStretchWidget( self.sizeMenu )
    mUI.MelSpacer(_row,w = 5)

    _row.layout()

    #>>> Data
    _row = mUI.MelHSingleStretchLayout(_inside,expand = True,ut = 'cgmUISubTemplate', height=60)
    mUI.MelSpacer(_row,w=5)
    self.dataSF = mUI.MelScrollField(_row,backgroundColor = [1,1,1],h=20,
                                                    ut = 'cgmUITemplate',
                                                    w = 50,
                                                    wordWrap = True,
                                                    #ec = lambda *a:self._UTILS.puppet_doChangeName(self),
                                                    annotation = "Our base object from which we process things in this tab...")
    mUI.MelSpacer(_row,w = 5)
    _row.setStretchWidget(self.dataSF)
    _row.layout()

    if self.callback:
        # Generate Button
        #
        _row = mUI.MelHLayout(_inside,ut='cgmUISubTemplate',padding = 10)
        
        self.animDrawBtn = cgmUI.add_Button(_row,self.callbackLabel,
            cgmGEN.Callback(self.callback,self.imageData[self.index]['image_path'], self.imageData[self.index]['data'],),                         
            '')

        _row.layout()    

    return _inside

def buildColumn_image(self,parent, asScroll = False):
    """
    Trying to put all this in here so it's insertable in other uis
    
    """   
    if asScroll:
        _inside = mUI.MelScrollLayout(parent,useTemplate = 'cgmUISubTemplate') 
    else:
        _inside = mUI.MelColumnLayout(parent,useTemplate = 'cgmUISubTemplate') 
    
    self.imageRow = mUI.MelSingleLayout(_inside,ut = 'cgmUISubTemplate')
    self.image = mUI.MelImage(self.imageRow)
    self.imageRow.layout()

    return _inside
# Create the regenerate function
def updateUI(self):
    # Get the selected percentage from the option menu
    selected_percent = float(self.uiOM_SizeMenu( q=True, value=True).replace('%', '')) / 100.0

    # Get the image data and path of the current image
    current_image_path = self.imageData[self.index]['image_path']

    # Open the image
    img = Image.open(current_image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize the image based on the selected percentage
    new_img = img.resize((int(img.width * selected_percent), int(img.height * selected_percent)), resample=Image.LANCZOS)

    width = new_img.width
    height = new_img.height

    # Save temporary image file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        new_img.save(f.name)
        new_temp_file_path = f.name

    # Update the image control with the new image
    self.image(e=True, image=new_temp_file_path, width=width, height=height)

    # Update the scroll field with the data of the current image
    self.dataSF(e=True, text=str(self.imageData[self.index]['data']))
    self.indexLabel(e=True, label='Image %d/%d' % (self.index+1, len(self.imageData)))


# Add the button functions
def uiFunc_prevImage(self):
    if self.index < 1:           
        self.index = len(self.imageData)-1
    else:
        self.index = self.index - 1
    updateUI(self)

def uiFunc_nextImage(self):
    self.index = self.index % len(self.imageData)
    updateUI(self)