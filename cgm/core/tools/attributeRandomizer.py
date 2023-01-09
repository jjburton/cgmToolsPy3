"""
------------------------------------------
attributeRandomizer: cgm.core.tools
Author: Josh Burton
email: cgmonks.info@gmail.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
================================================================
"""


# From Python =============================================================
import pprint
import logging
import random

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# From Maya =============================================================
import maya.cmds as mc
import maya.mel as mel

from cgm.core import cgm_Meta as cgmMeta
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core import cgm_General as cgmGEN
from cgm.core.lib import snap_utils as SNAP
from cgm.core.lib import locator_utils as LOC
from cgm.core.lib import attribute_utils as ATTR
from cgm.core.lib import name_utils as NAMES
#import cgm.core.lib.shared_data as CORESHARE
#import cgm.core.lib.string_utils as CORESTRINGS
from cgm.core.lib import search_utils as SEARCH
import cgm.core.classes.GuiFactory as cgmUI
from cgm.core.lib import math_utils as MATH

#import cgm.core.mrs.lib.animate_utils as MRSANIMUTILS
import cgm.core.lib.list_utils as CORELIST

__version__ = cgmGEN.__RELEASESTRING


import cgm.core.classes.GuiFactory as CGMUI
mUI = CGMUI.mUI

from . import funcOverTime as FOT

log_msg = cgmGEN.logString_msg
log_sub = cgmGEN.logString_sub
log_start = cgmGEN.logString_start

_d_annotations = {'me':'Create a loc from selected objects',
                  'mid':'Create a loc at the bb midpoint of a single target or the mid point of multiple targets',
                  'closestPoint':'Create a loc at the closest point on the targets specified - curve, mesh, nurbs',
                  'closestTarget':'Create a loc at the closest target',
                  'rayCast':'Begin a clickMesh instance to cast a single locator in scene',
                  'updateSelf':'Update the selected objects',
                  'updateTarget':'Update the selected targets if possible',
                  'updateBuffer':'Update objects loaded to the buffer',
                  'sliderRange':' Push the slider range values to the int fields',
                  'selectedRange': 'Push the selected timeline range (if active)',
                  'sceneRange':'Push scene range values to the int fields',
                  '<<<':'Bake within a context of keys in range prior to the current time',
                  'All':'Bake within a context of the entire range of keys ',
                  '>>>':'Bake within a context of keys in range after the current time',
                  'attach':'Create a loc of the selected object AND start a clickMesh instance to setup an attach point on a mesh in scene'}
_l_toolModes  = ['absolute',
                 'nudge']

_d_shorts = {'absolute':'abs',
             'relative':'rel'}
d_attrNames = {'tx':'translateX',
               'ty':'translateY',
               'tz':'translateZ',
               'rx':'rotateX',
               'ry':'rotateY',
               'rz':'rotateZ',
               'sx':'scaleX',
               'sy':'scaleY',
               'sz':'scaleZ',               
               }



class ui(FOT.ui):
    USE_Template = 'cgmUITemplate'
    _toolname = 'RandomAttr'
    TOOLNAME = 'ui_RandomAttr'
    WINDOW_NAME = "{}UI".format(TOOLNAME)
    WINDOW_TITLE = 'RandomAttr| {0}'.format(__version__)
    DEFAULT_SIZE = 300, 350
    #DEFAULT_MENU = None
    #RETAIN = True
    #MIN_BUTTON = False
    #MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created

 
    def insert_init(self, *args, **kws):
        FOT.ui.insert_init(self,*args,**kws)
        #super(FOT.ui, self).insert_init(*args, **kws)
        self.create_guiOptionVar('random_mode', defaultValue='absolute')
        self.l_attrs = []
        self.ml_targets = []
        self.d_activeAttrs = []
        
        #self.create_guiOptionVar('keysMode', defaultValue='loc')
        #self.create_guiOptionVar('interval', defaultValue=1.0)
        #self.create_guiOptionVar('showBake', defaultValue=0)
        #self.create_guiOptionVar('context_keys', defaultValue='each')
        #self.create_guiOptionVar('context_time', defaultValue='current')

    def post_init(self,*args,**kws):
        self.mFOT.set_func(self.uiFunc_call,[],{})
        self.mFOT.set_pre(self.uiFunc_pre,[],{})
        
        
        pass#...clearing parent call here
    
    def log_dat(self):
        _str_func = 'log_self[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        pprint.pprint(self.mFOT.__dict__)        
                
    def uiFunc_attrs_add(self):
        _str_func = 'uiFunc_attrs_add[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        
        l_attrs = SEARCH.get_selectedFromChannelBox(attributesOnly = 1)
        if not l_attrs:
            return mc.warning( cgmGEN.logString_msg(_str_func,"No attributes Selected"))
        
        for a in l_attrs:
            if a not in self.l_attrs:
                self.l_attrs.append(a)
                
        self.uiFunc_refreshAttrList()

    def uiFunc_pre(self,*args,**kws):
        _str_func = 'uiFunc_pre[{0}]'.format(self.__class__.TOOLNAME)                    
        #print('{} | do something here...'.format(mc.currentTime(q=True)))
        ml = cgmMeta.validateObjListArg(mc.ls(sl=1),default_mType='cgmObject')
        pprint.pprint(ml)
        
        if not ml:
            mc.warning( log_msg(_str_func,"Nothing selected"))
            return False
        
        self.ml_targets = ml
        self.d_activeAttrs = {}
        
        for i,a in enumerate(self.l_attrs):
            if self._dCB_attrs[i].getValue():
                self.d_activeAttrs[a] = {'min':self._dMin_attrs[i].getValue(),
                                         'max':self._dMax_attrs[i].getValue()}
                
        if not self.d_activeAttrs:
            return mc.warning( cgmGEN.logString_msg(_str_func,"No active Attrs"))        
        pprint.pprint([self.ml_targets,self.d_activeAttrs, self.var_random_mode.getValue()])
        return True
    
    def uiFunc_call(self,*args,**kws):
        #print('{} | do something here...'.format(mc.currentTime(q=True)))
        _targets =  self.ml_targets
        _attrs = self.d_activeAttrs
        _mode = self.var_random_mode.getValue()

        pprint.pprint(vars())
        
        for a,d in self.d_activeAttrs.items():
            for mObj in _targets:
                _node = mObj.mNode
                _value = random.uniform(d['min'],d['max'])
                print("{} | min: {} | max: {}".format(_value, d['min'], d['max']))
                if _mode == 'absolute':
                    ATTR.set(_node, a, _value)
                else:
                    _base = ATTR.get(_node, a)
                    ATTR.set(_node, a, _value + _base)
                
                mc.setKeyframe(_node, at=a)
        
    def uiFunc_attrs_clear(self):
        _str_func = 'uiFunc_attrs_clear[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        
        self.l_attrs = []
        self.uiFunc_refreshAttrList()
        
    def uiFunc_removeData(self,idx=None):
        _str_func = 'uiFunc_removeData[{0}]'.format(self.__class__.TOOLNAME)
        log.debug(log_start(_str_func))
        
        try:
            _a = self.l_attrs[idx]
        except:
            raise ValueError("{} | invalid idx: {}".format(_str_func,idx))
            
        result = mc.confirmDialog(title="Removing a| Dat {}".format(_a),
                                  message= "Remove: {}".format(_a),
                                  button=['OK','Cancel'],
                                  defaultButton='OK',
                                  cancelButton='Cancel',
                                  dismissString='Cancel')
        
        if result != 'OK':
            log.error("|{}| >> Cancelled.".format(_str_func))
            return False        
        
        if idx is not None:
            self.l_attrs.remove(_a)
            self.uiFunc_refreshAttrList()            
            return
        
        
    #@cgmGEN.Wrap_exception
    def uiFunc_refreshAttrList(self):
        _str_func = 'uiFunc_refreshAttrList[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        self._dCB_attrs = {}
        self._dMin_attrs = {}
        self._dMax_attrs = {}
        
        self.uiFrame_attrs.clear()
        
        if not self.l_attrs:
            mc.warning( cgmGEN.logString_msg(_str_func,"No attributes registered"))
            return
        
        self.l_attrs = sorted(self.l_attrs)
        
        for i,a in enumerate(self.l_attrs):
            try:
                #Row...
                _label = d_attrNames.get(a,a)
                
                _row = mUI.MelHSingleStretchLayout(self.uiFrame_attrs,)            
                
                mUI.MelSpacer(_row,w=5)

                _cb = mUI.MelCheckBox(_row,l=_label,
                                      #w=30,
                                     #annotation = d_dat.get('ann',k),
                                     value = 1)
                self._dCB_attrs[i] = _cb
                _row.setStretchWidget(_cb)
                
                
                self._dMin_attrs[i]  = mUI.MelFloatField(_row,precision = 1,
                                                         value = -1,
                                                         width = 40)
                self._dMax_attrs[i]  = mUI.MelFloatField(_row,precision = 1,
                                                         value = 1,
                                                         width = 40)
                
                
                mUI.MelButton(_row, label = '-',
                              ann= _d_annotations.get("Remove Attrs",'fix'),
                              c = cgmGEN.Callback(self.uiFunc_removeData,i))
                
                mUI.MelSpacer(_row,w=5)                
                _row.layout()
                
                mUI.MelSeparator(self.uiFrame_attrs,h=1)
            except Exception as err:
                log.error(err)
        #self.uiFrame_attrs.layout()
        
    def uiFunc_setToggles(self,arg):
        for i,mCB in list(self._dCB_attrs.items()):
            mCB.setValue(arg)
            
    def uiBuild_top(self):
        _str_func = 'uiUpdate_top[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        self.uiSection_top.clear()
        
        _inside = self.uiSection_top
        
        #>>>Mode  Options -------------------------------------------------------------------------------
        _rowRandomMode = mUI.MelHSingleStretchLayout(_inside,ut='cgmUIHeaderTemplate',padding = 5)
    
        
        mUI.MelSpacer(_rowRandomMode,w=5)                          
        mUI.MelLabel(_rowRandomMode,l='Mode: ')
        _rowRandomMode.setStretchWidget( mUI.MelSeparator(_rowRandomMode) )
    
        uiRC = mUI.MelRadioCollection()
    
        mVar = self.var_random_mode
        _on = mVar.value
    
        for i,item in enumerate(_l_toolModes):
            if item == _on:
                _rb = True
            else:_rb = False
            _label = str(_d_shorts.get(item,item))
            uiRC.createButton(_rowRandomMode,label=_label,sl=_rb,
                              ann = "Set keys context to: {0}".format(item),                          
                              onCommand = cgmGEN.Callback(mVar.setValue,item))

        mUI.MelSpacer(_rowRandomMode,w=2)                          
        
        _rowRandomMode.layout()
        mUI.MelSpacer(_inside,h=2)
        
        #--------------------------------------------------------------
        _row = mUI.MelHLayout(_inside, h=30, padding=5 )
        mUI.MelButton(_row, label = 'All',ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_setToggles,1))
        mUI.MelButton(_row, label = 'None',ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_setToggles,0))
        mUI.MelSeparator(_row,w=10)
        mUI.MelButton(_row, label = 'Clear',ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_attrs_clear))
        mUI.MelButton(_row, label = 'Add',ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_attrs_add))                         
        #mUI.MelButton(_row, label = 'Remove',ut='cgmUITemplate',
        #              c = cgmGEN.Callback(self.uiFunc_removeData))
        _row.layout()        
        
        """
        mUI.MelButton(_inside,l='Get Attrs',
                      ut='cgmUITemplate',
                      #w=150,
                      c = cgmGEN.Callback(self.uiFunc_attrs_add),                         
                      ann=_d_annotations.get('Get Attrs','fix'))
                      """
        self.uiFrame_attrs = mUI.MelColumnLayout(_inside,useTemplate = 'cgmUISubTemplate') 
        
        
        mc.setParent(_inside)
        cgmUI.add_HeaderBreak()
    