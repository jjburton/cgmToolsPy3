"""
------------------------------------------
locinator: cgm.core
Author: Josh Burton
email: cgmonks.info@gmail.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
2.0 rewrite
================================================================
"""


# From Python =============================================================
import copy
import re
import sys
import pprint
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

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
import cgm.core.lib.shared_data as CORESHARE
import cgm.core.lib.string_utils as CORESTRINGS
from cgm.core.lib import search_utils as SEARCH
import cgm.core.classes.GuiFactory as cgmUI
from cgm.core.tools.markingMenus.lib import contextual_utils as MMCONTEXT

__version__ = cgmGEN.__RELEASESTRING

import cgm.core.classes.GuiFactory as CGMUI
#reload(cgmUI)
CGMUI.initializeTemplates()
mUI = CGMUI.mUI

from cgm.lib import lists

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

class fOverTimeBAK:
    def __init__(self, start_frame = None, end_frame=None, interval=None):
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.interval = interval
        self.frames = []
        self.errors = []
        self.func = None
        self._args = None
        self._kws = None

    def set_func(self, func, *args, **kws):
        self.func = func
        self._args = args
        self._kws = kws

    def get_func(self,func = None,*args,**kwargs):
        if self.func:
            return self.func, self._args, self._kws
        if func == None:
            raise ValueError("{} | Need a function".format(self.__class__))

        return func,args,kwargs

    def run(self, function = None, *args, **kwargs):
        current_time = mc.currentTime(query=True)
        current_frame = self.start_frame
        while current_frame <= self.end_frame:
            mc.currentTime(current_frame)            
            try:
                if self.func:
                    self.func()
                else:                
                    function(*args, **kwargs)
            except Exception as e:
                self.errors.append((current_frame, e, args, kwargs))
            current_frame += self.interval
        mc.currentTime(current_time)

    def run_frames(self, function = None, *args, **kwargs):
        if not self.frames:
            raise ValueError("{} | No frames set".format(self.__class__))

        current_time = mc.currentTime(query=True)
        for f in self.frames:
            mc.currentTime(f)
            try:
                if self.func:
                    self.func()
                else:                
                    function(*args, **kwargs)
            except Exception as e:
                self.errors.append((f, e, args, kwargs))
        mc.currentTime(current_time)
        
    @cgmGEN.Wrap_exception
    def run_on_current_frame(self, function=None, *args, **kwargs):
        current_frame = mc.currentTime(query=True)
        try:
            if self.func:
                self.func()
            else:
                function(current_frame, *args, **kwargs)
        except Exception as e:
            self.errors.append((current_frame, e, args, kwargs))

    def pre_run(self):
        pass
    def post_run(self):
        pass

    def set_start(self,start_frame):
        self.start_frame = start_frame
    def set_end(self,end_frame):
        self.end_frame = end_frame
    def set_interval(self,interval):
        self.interval = interval

    def print_errors(self):
        if self.errors:
            print("{} | Errors occurred during processing:".__class__)
            for error in self.errors:
                print(f"Frame {error[0]}: {error[1]} with args={error[2]} and kwargs={error[3]}")

class overload_call:
    def __init__(self, start_frame = None, end_frame=None, interval=None):
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.interval = interval
        self.frames = []
        self.errors = []

    @cgmGEN.Wrap_exception
    def call(self):
        pass
        
    def run(self):
        current_time = mc.currentTime(query=True)
        current_frame = self.start_frame
        
        self.pre_run()        
        while current_frame <= self.end_frame:
            mc.currentTime(current_frame)            
            try:
                self.call()
            except Exception as e:
                self.errors.append((current_frame, e, args, kwargs))
            current_frame += self.interval
        mc.currentTime(current_time)
        self.post_run()

    def run_frames(self, function = None, *args, **kwargs):
        if not self.frames:
            raise ValueError("{} | No frames set".format(self.__class__))
        
        self.pre_run()
        current_time = mc.currentTime(query=True)
        for f in self.frames:
            mc.currentTime(f)
            try:
                self.call()
            except Exception as e:
                self.errors.append((f, e, args, kwargs))
        mc.currentTime(current_time)
        self.post_run()
        
    @cgmGEN.Wrap_exception
    def run_on_current_frame(self, function=None, *args, **kwargs):
        self.pre_run()
        try:
            self.call()
        except Exception as e:
            self.errors.append((current_frame, e, args, kwargs))
        self.post_run()
        
    @cgmGEN.Wrap_exception
    def pre_run(self):
        pass
    
    @cgmGEN.Wrap_exception    
    def post_run(self):
        pass

    def set_start(self,start_frame):
        self.start_frame = start_frame
    def set_end(self,end_frame):
        self.end_frame = end_frame
    def set_interval(self,interval):
        self.interval = interval

    def print_errors(self):
        if self.errors:
            print("{} | Errors occurred during processing:".__class__)
            for error in self.errors:
                print(f"Frame {error[0]}: {error[1]} with args={error[2]} and kwargs={error[3]}")


class ui(CGMUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    _toolname = 'FuncOverTime'
    TOOLNAME = 'ui_FuncOverTime'
    WINDOW_NAME = "{}UI".format(TOOLNAME)
    WINDOW_TITLE = 'FOT | {0}'.format(__version__)
    DEFAULT_SIZE = 200, 275
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = False
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created

 
    def insert_init(self, *args, **kws):
        self.mFOT = overload_call()
        self.mFOT.call = self.uiFunc
        
        self.create_guiOptionVar('keysMode', defaultValue='loc')
        
        self.WINDOW_TITLE = ui.WINDOW_TITLE
        self.DEFAULT_SIZE = ui.DEFAULT_SIZE
        
        
    def build_menus(self):
        pass
        #self.uiMenu_FileMenu = mUI.MelMenu(l='File', pmc = cgmGEN.Callback(self.buildMenu_file))
        #self.uiMenu_SetupMenu = mUI.MelMenu(l='Dev', pmc = cgmGEN.Callback(self.buildMenu_dev))
        
    def uiFunc(self):
        print('{} | Hello'.format(mc.currentTime(q=True)))
        
    def buildMenu_file(self):
        self.uiMenu_FileMenu.clear()
        mUI.MelMenuItemDiv(self.uiMenu_FileMenu, l="Options")
        
        _menu = self.uiMenu_FileMenu
        #Context ...---------------------------------------------------------------------------------
        _starDir = mUI.MelMenuItem(_menu, l="StartDir",tearOff=True,
                                   subMenu = True)
        
        uiRC = mc.radioMenuItemCollection()

        
        _on = self.var_startDirMode.value
        for i,item in enumerate(self._l_startDirModes):
            if i == _on:_rb = True
            else:_rb = False
            mUI.MelMenuItem(_starDir,label=item,
                            collection = uiRC,
                            ann = _d_ann.get(item),
                            c = cgmGEN.Callback(self.uiFunc_setDirMode,i),                                  
                            rb = _rb)        
        
        mUI.MelMenuItemDiv(self.uiMenu_FileMenu, l="Utils")

        mUI.MelMenuItem( self.uiMenu_FileMenu, l="Save",
                         c = lambda *a:mc.evalDeferred(cgmGEN.Callback(self.uiFunc_dat_save)))
                         
                        # c = lambda *a:mc.evalDeferred(cgmGEN.Callback(uiFunc_save_actions,self)))

        mUI.MelMenuItem( self.uiMenu_FileMenu, l="Save As",
                         c = lambda *a:mc.evalDeferred(cgmGEN.Callback(self.uiFunc_dat_saveAs)))
        
        mUI.MelMenuItem( self.uiMenu_FileMenu, l="Load",
                          c = lambda *a:mc.evalDeferred(cgmGEN.Callback(self.uiFunc_dat_load)))
                        # c = lambda *a:mc.evalDeferred(cgmGEN.Callback(uiFunc_load_actions,self)))
                        
    def uiFunc_setDirMode(self,v):
        _str_func = 'uiFunc_setDirMode[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        
        _path = startDir_getBase(self._l_startDirModes[v])
        if _path:
            self.var_startDirMode.setValue(v)
            print(_path)
        
    
    def buildMenu_dev(self):
        self.uiMenu_SetupMenu.clear()
        _menu = self.uiMenu_SetupMenu
        mUI.MelMenuItem( _menu, l="Ui | ...",
                         c=lambda *a: self.log_self())               
        mUI.MelMenuItem( _menu, l="Dat | class",
                         c=lambda *a: self.uiDat.log_self())        
        mUI.MelMenuItem( _menu, l="Dat | stored",
                         c=lambda *a: self.uiDat.log_dat())            
    def log_self(self):
        _str_func = 'log_self[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        pprint.pprint(self.__dict__)
        
            

    def uiData_checkState(self):
        return self.uiDat.checkState()                
        
    def uiUpdate_top(self):
        _str_func = 'uiUpdate_top[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        self.uiSection_top.clear()
        CGMUI.add_Header('Put stuff here')
        mUI.MelLabel(self.uiSection_top, label = "No really, put some \n content here")
            
    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))
        
        #Declare form frames...------------------------------------------------------
        _MainForm = mUI.MelFormLayout(parent,ut='CGMUITemplate')#mUI.MelColumnLayout(ui_tabs)

        _inside = mUI.MelColumn(_MainForm,ut='CGMUITemplate')
        
        #Top Section -----------
        self.uiSection_top = mUI.MelColumn(_inside ,useTemplate = 'cgmUISubTemplate',vis=True)         
        self.uiUpdate_top()
        
        _current = mUI.MelButton(_inside, label = 'Current',ut='cgmUITemplate',
                                 c = cgmGEN.Callback(self.mFOT.run_on_current_frame,self.mFOT),                                 
                                 )
  
        #Bake frame...------------------------------------------------------
        self.create_guiOptionVar('bake',defaultValue = 0)
        mVar_frame = self.var_bake
        
        _frame = mUI.MelFrameLayout(_inside,label = 'Bake',vis=True,
                                    collapse=mVar_frame.value,
                                    collapsable=True,
                                    enable=True,
                                    w=180,
                                    #ann='Contextual MRS functionality',
                                    useTemplate = 'cgmUIHeaderTemplate',
                                    expandCommand = lambda:mVar_frame.setValue(0),
                                    collapseCommand = lambda:mVar_frame.setValue(1)
                                    )	
        self.uiFrame_bake = mUI.MelColumnLayout(_frame,useTemplate = 'cgmUISubTemplate') 


        

        #Progress bar... ----------------------------------------------------------------------------
        self.uiPB_test=None
        self.uiPB_test = mc.progressBar(vis=False)

        _row_cgm = CGMUI.add_cgmFooter(_MainForm)            

        #Form Layout--------------------------------------------------------------------
        _MainForm(edit = True,
                  af = [(_inside,"top",0),
                        (_inside,"left",0),
                        (_inside,"right",0),
                        (_row_cgm,"left",0),
                        (_row_cgm,"right",0),
                        (_row_cgm,"bottom",0),
                        ],
                  ac = [(_inside,"bottom",0,_row_cgm),
                        ],
                  attachNone = [(_row_cgm,"top")])
        
        self.uiFrame_buildBake()
        
    def uiFrame_buildBake(self):
        self.uiFrame_bake.clear()
        
        _frame_inside = self.uiFrame_bake
        #>>>Update Row ---------------------------------------------------------------------------------------
        mc.setParent(_frame_inside)
        _row_timeSet = mUI.MelHLayout(_frame_inside,ut='cgmUISubTemplate',padding = 1)
    
        CGMUI.add_Button(_row_timeSet,'Slider',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange,'slider'),                         
                         #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                         _d_annotations.get('sliderRange','fix sliderRange'))
        CGMUI.add_Button(_row_timeSet,'Sel',
                                 cgmGEN.Callback(self.uiFunc_updateTimeRange,'selected'),                         
                                 #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                                 _d_annotations.get('selectedRange','fix selectedRange'))        
    
        CGMUI.add_Button(_row_timeSet,'Scene',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange,'scene'),                         
                         _d_annotations.get('sceneRange','fix sceneRange'))
  
        
        _row_timeSet.layout()          
        
        # TimeInput Row ----------------------------------------------------------------------------------
        _row_time = mUI.MelHRowLayout(_frame_inside,ut='cgmUISubTemplate')
        mUI.MelSpacer(_row_time)
        mUI.MelLabel(_row_time,l='start')
    
        self.uiFieldInt_start = mUI.MelIntField(_row_time,
                                                width = 40)
        #_row_time.setStretchWidget( mUI.MelSpacer(_row_time) )
        mUI.MelLabel(_row_time,l='end')
    
        self.uiFieldInt_end = mUI.MelIntField(_row_time,
                                              width = 40)
        
        mUI.MelLabel(_row_time,l='int')        
        self.uiFF_interval = mUI.MelFloatField(_row_time,value=1, precision = 1,
                                                  width = 40, min=0.1)        
        
        self.uiFunc_updateTimeRange()
    
        mUI.MelSpacer(_row_time)
        _row_time.layout()   
        
        
        

        #>>>Update Row ---------------------------------------------------------------------------------------
        
        mc.setParent(_frame_inside)
        CGMUI.add_LineSubBreak()
        
        _row_bake = mUI.MelHLayout(_frame_inside,ut='cgmUISubTemplate',padding = 1)
    
        CGMUI.add_Button(_row_bake,' <<<',
                         cgmGEN.Callback(self.uiFunc_bake,'back'),                         
                         #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                         _d_annotations.get('<<<','fix'))
    
        CGMUI.add_Button(_row_bake,'Range',
                         cgmGEN.Callback(self.uiFunc_bake,'range'),                         
                         _d_annotations.get('All','fix'))
        
        
        CGMUI.add_Button(_row_bake,'>>>',
                         cgmGEN.Callback(self.uiFunc_bake,'forward'),                         
                         _d_annotations.get('>>>','fix'))    
        
        _row_bake.layout()
        
        mUI.MelButton(_frame_inside,label = 'Selected Time',
                      ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_bake,'selected'),                         
                      ann=_d_annotations.get('Selected','fix'))        

    def uiFunc_updateTimeRange(self,mode = 'slider'):
        _range = SEARCH.get_time(mode)
        if _range:
            self.uiFieldInt_start(edit = True, value = _range[0])
            self.uiFieldInt_end(edit = True, value = _range[1])            

    def uiFunc_bake(self,mode='all'):
        if mode == 'range':
            _range = [self.uiFieldInt_start.getValue(),self.uiFieldInt_end.getValue()]
        else:
            _range = SEARCH.get_time(mode)
        pprint.pprint(_range)
        
        if not _range:
            return log.warning("No frames in range")
        
        self.mFOT.start_frame = _range[0]
        self.mFOT.end_frame = _range[1]
        self.mFOT.interval = self.uiFF_interval.getValue()
        
        self.mFOT.run()
        
        return
        
        
        if mode == 'selectedRange':
            _kws = {'boundingBox':False,'keysMode':self.var_keysMode.value,'keysDirection':mode,
                    'timeMode':'selected'}
        else:
            _kws = {'boundingBox':False,'keysMode':self.var_keysMode.value,'keysDirection':mode,
                    'timeMode':'custom','timeRange':[self.uiFieldInt_start(q=True, value = True),self.uiFieldInt_end(q=True, value = True)]}
        
        
        pprint.pprint(_kws)    
        #MMCONTEXT.func_process(bake_match, _targets,'all','Bake',False,**_kws)       
















        
def bake_match(targets = None, move = True, rotate = True, boundingBox = False, pivot = 'rp',
               timeMode = 'slider',timeRange = None, keysMode = 'loc', keysDirection = 'all',
               matchMode = 'self',dynMode=None):
    """
    Updates an tagged loc or matches a tagged object
    
    :parameters:
        obj(str): Object to modify
        target(str): Target to match
        
        timeMode(str):
            :slider/range
            :scene
            :selected
            :custom
        keysMode(str)
            :loc
            :source
            :combine
            :frames -- bake every frame
            :twos
            :threes
        keysDirection(str):
            :all
            :forward
            :back
        timeRange(list) -- [0,111] for example
        matchMode - mode for update_obj call
            self
            source
    :returns
        success(bool)
    """     
    _str_func = 'bake_match'
    
    #log.info("|{0}| >> Not updatable: {1}".format(_str_func,NAMES.get_short(_obj)))  
    _targets = VALID.objStringList(l_args=targets,isTransform=True,noneValid=False,calledFrom=_str_func)
        
    if not _targets:raise ValueError("|{0}| >> no targets.".format(_str_func))
    if not move and not rotate:raise ValueError("|{0}| >> Move and rotate both False".format(_str_func))
    
    if dynMode is None:
        try:dynMode = cgmMeta.cgmOptionVar('cgmVar_dynMode').getValue()
        except:pass
        
    log.info("|{0}| >> Targets: {1}".format(_str_func,_targets))
    log.info("|{0}| >> move: {1} | rotate: {2} | boundingBox: {3}".format(_str_func,move,rotate,boundingBox))    
    log.info("|{0}| >> timeMode: {1} | keysMode: {2} | keysDirection: {3} | dynMode: {4}".format(_str_func,timeMode,keysMode,keysDirection,dynMode))
    
    _l_toDo = []
    _d_toDo = {}
    _d_keyDat = {}
    
    #>>>Validate ==============================================================================================  
    for o in _targets:
        _d = {}
        if matchMode == 'source':
            source = ATTR.get_message(o,'cgmLocSource')
            if not source:
                raise ValueError("No source found: {0}.cgmLocSource".format(o))            
            _l_toDo.append(o)
            _d['loc'] = o
            _d['source'] = source[0]
            _d_toDo[o] = _d
        else:
            _d = get_objDat(o)
            if _d and _d.get('updateType'):
                _l_toDo.append(o)
                _d_toDo[o] = _d
            
    if not _l_toDo:
        log.error("|{0}| >> No updatable targets found in: {1}".format(_str_func,_targets))        
        return False
    
    #>>>Key data ==============================================================================================    
    _d_keyDat['currentTime'] = mc.currentTime(q=True)
    
    if timeMode in ['slider','range']:
        _d_keyDat['frameStart'] = mc.playbackOptions(q=True,min=True)
        _d_keyDat['frameEnd'] = mc.playbackOptions(q=True,max=True)
    elif timeMode == 'scene':
        _d_keyDat['frameStart'] = mc.playbackOptions(q=True,animationStartTime=True)
        _d_keyDat['frameEnd'] = mc.playbackOptions(q=True,animationEndTime=True)
    elif timeMode == 'selected':
        _tRes = SEARCH.get_time('selected')
        if not _tRes:
            log.error("|{0}| >> No time range selected".format(_str_func))                    
            return False
        _d_keyDat['frameStart'] = _tRes[0]
        _d_keyDat['frameEnd'] = _tRes[1]          
    elif timeMode == 'custom':
        _d_keyDat['frameStart'] = timeRange[0]
        _d_keyDat['frameEnd'] = timeRange[1]       
    else:
        raise ValueError("|{0}| >> Unknown timeMode: {1}".format(_str_func,timeMode))
    
    _attrs = []
    if move:
        _attrs.extend(['translateX','translateY','translateZ']) 
    if rotate:
        _attrs.extend(['rotateX','rotateY','rotateZ']) 
    
    _d_keyDat['attrs'] = _attrs

    cgmGEN.print_dict(_d_toDo,"bake_match to do...",__name__)
    cgmGEN.print_dict(_d_keyDat,"Key data..",__name__)
    
    #>>>Process ==============================================================================================    
    _d_keysOfTarget = {}
    _keysToProcess = []

    _start = int(_d_keyDat['frameStart'])
    _end = int(_d_keyDat['frameEnd'])  
    
    _keysAll = None
    if keysMode == 'frames':
        _keysAll = list(range(_start,_end +1))
    elif keysMode == 'twos':
        _keysAll = []
        i = _start
        while i <= _end:
            _keysAll.append(i)
            i += 2
    elif keysMode == 'threes':
        _keysAll = []
        i = _start
        while i <= _end:
            _keysAll.append(i)
            i += 3   
            
    if keysDirection in ['forward','back'] and _keysAll:
        _keysDirection = []
        if keysDirection == 'forward':
            for k in _keysAll:
                if k > _d_keyDat['currentTime']:
                    _keysDirection.append(k)                     
        else:
            for k in _keysAll:
                if k < _d_keyDat['currentTime']:
                    _keysDirection.append(k)
        _keysAll = _keysDirection
        
        _start = _keysAll[0]
        _end = _keysAll[-1]

    if _keysAll:
        _keysToProcess = _keysAll
    

    #First for loop, gathers key data per object...
    for o in _l_toDo:
        log.info("|{0}| >> Processing: '{1}' | keysMode: {2}".format(_str_func,o,keysMode))
        _d = _d_toDo[o]
        
        #Gather target key data...
        if not _keysAll:
            if keysMode == 'loc':
                _keys = SEARCH.get_key_indices_from( SEARCH.get_transform( _d['loc']),mode = keysDirection)
            elif keysMode == 'source':
                _keys = SEARCH.get_key_indices_from( SEARCH.get_transform( _d['source']),mode = keysDirection)
            elif keysMode in ['combine','both']:
                _source = SEARCH.get_key_indices_from( SEARCH.get_transform( _d['loc']),mode = keysDirection)
                _loc = SEARCH.get_key_indices_from( SEARCH.get_transform( _d['source']),mode= keysDirection)
                
                _keys = _source + _loc
                _keys = lists.returnListNoDuplicates(_keys)
            elif keysMode == 'frames':
                _keys = list(range(_start,_end +1))
            else:raise ValueError("|{0}| >> Unknown keysMode: {1}".format(_str_func,keysMode))
        
            _l_cull = []
            for k in _keys:
                if k < _d_keyDat['frameStart'] or k > _d_keyDat['frameEnd']:
                    log.info("|{0}| >> Removing key from list: {1}".format(_str_func,k))                
                else:
                    _l_cull.append(k)
                    
                if timeRange is not None:
                    if k < timeRange[0] or k > timeRange[1]:
                        log.info("|{0}| >> Key not in time range({2}). Removing: {1}".format(_str_func,k,timeRange))                
                    else:
                        _l_cull.append(k)
                        
            keys = _l_cull
                    
            if not _keys:
                log.error("|{0}| >> No keys found for: '{1}'".format(_str_func,o))
                break            
            
            _d_keysOfTarget[o] = _keys
            _keysToProcess.extend(_keys)  
            log.info("|{0}| >> Keys: {1}".format(_str_func,_keys))            
        else: _d_keysOfTarget[o] = _keysAll
        
        
        #Clear keys in range
        if matchMode in ['source']:
            mc.cutKey(_d['source'],animation = 'objects', time=(_start,_end+ 1),at= _attrs)
        else:
            mc.cutKey(o,animation = 'objects', time=(_start,_end+ 1),at= _attrs)
            
    #pprint.pprint(_d)
    #return 
    #Second for loop processes our keys so we can do it in one go...
    _keysToProcess = lists.returnListNoDuplicates(_keysToProcess)
    #log.info(_keysToProcess)
    
    if not _keysToProcess:
        log.error("|{0}| >> No keys to process. Check settings.".format(_str_func))
        return False
    #return #...keys test...

    #Process 
    _progressBar = CGMUI.doStartMayaProgressBar(len(_keysToProcess),"Processing...")
    _autoKey = mc.autoKeyframe(q=True,state=True)
    if _autoKey:mc.autoKeyframe(state=False)
    if not dynMode:
        mc.refresh(su=1)
    else:
        _start = mc.playbackOptions(q=True,min=True)
        _keysToProcessFull = list(range(int(_start), int(max(_keysToProcess))+1))
        #for k in _keysToProcess:
        #    if k not in _keysToProcessFull:
        #        _keysToProcessFull.append(k)
        #_keysToProcessFull.sort()
        
        _keysToProcess = _keysToProcessFull
        
    _len = len(_keysToProcess)
    try:
        for i,f in enumerate(_keysToProcess):
            mc.currentTime(f)
            for o in _l_toDo:
                _keys = _d_keysOfTarget.get(o,[])
                if f in _keys:
                    log.debug("|{0}| >> Baking: {1} | {2} | {3}".format(_str_func,f,o,_attrs))
                    if _progressBar:
                        
                        if mc.progressBar(_progressBar, query=True, isCancelled=True ):
                            log.warning('Bake cancelled!')
                            return False
                        
                        mc.progressBar(_progressBar, edit=True, status = ("{0} On frame {1} for '{2}'".format(_str_func,f,o)), step=1, maxValue = _len)                    
                
                    if matchMode == 'source':
                        try:update_obj(o,move,rotate,mode=matchMode)
                        except Exception as err:log.error(err)
                        mc.setKeyframe(_d_toDo[o]['source'],time = f, at = _attrs)
                    else:
                        try:update_obj(o,move,rotate)
                        except Exception as err:log.error(err)
                        mc.setKeyframe(o,time = f, at = _attrs)
    except Exception as err:
        log.error(err)
    finally:
        if not dynMode:mc.refresh(su=0)
        CGMUI.doEndMayaProgressBar(_progressBar)
    mc.currentTime(_d_keyDat['currentTime'])
    if _autoKey:mc.autoKeyframe(state=True)
    mc.select(_targets)
    return True
        
        
def uiRadial_create(self,parent,direction = None):
    #>>>Loc ==============================================================================================    
        _l = mc.menuItem(parent=parent,subMenu=True,
                     l = 'Loc',
                     rp = direction)
    
        mc.menuItem(parent=_l,
                    l = 'World Center',
                    c = cgmGEN.Callback(LOC.create),
                    rp = "S")          
        mc.menuItem(parent=_l,
                    l = 'Me',
                    en = self._b_sel,
                    c = cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, self._l_sel,'each'),
                    rp = "N")           
        mc.menuItem(parent=_l,
                    l = 'Mid point',
                    en = self._b_sel,                    
                    c = cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, self._l_sel,'all','midPointLoc',False,**{'mode':'midPoint'}),                                                                      
                    rp = "SW")   
        mc.menuItem(parent=_l,
                    l = 'Attach Point',
                    en = self._b_sel,
                    c = cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, self._l_sel,'each','attachPoint',False,**{'mode':'attachPoint'}),
                    rp = "E")         
        mc.menuItem(parent=_l,
                    l = 'closest Point',
                    en = self._b_sel_pair,                    
                    c = cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, self._l_sel,'all','closestPoint',False,**{'mode':'closestPoint'}),                                                                      
                    rp = "NW") 
        mc.menuItem(parent=_l,
                    l = 'closest Target',
                    en = self._b_sel_few,                    
                    c = cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, self._l_sel,'all','closestTarget',False,**{'mode':'closestTarget'}),                                                                      
                    rp = "W")   
        mc.menuItem(parent=_l,
                    l = 'rayCast',
                    c = lambda *a:LOC.create(mode = 'rayCast'),
                    #c = lambda *a:self.rayCast_create('locator',False),
                    rp = "SE")       

def uiSetupOptionVars(self):
    self.var_matchModeMove = cgmMeta.cgmOptionVar('cgmVar_matchModeMove', defaultValue = 1)
    self.var_matchModeRotate = cgmMeta.cgmOptionVar('cgmVar_matchModeRotate', defaultValue = 1)
    self.var_dynMode = cgmMeta.cgmOptionVar('cgmVar_dynMode', defaultValue = 0)
    
    #self.var_matchModePivot = cgmMeta.cgmOptionVar('cgmVar_matchModePivot', defaultValue = 0)
    self.var_matchMode = cgmMeta.cgmOptionVar('cgmVar_matchMode', defaultValue = 2)
    self.var_locinatorTargetsBuffer = cgmMeta.cgmOptionVar('cgmVar_locinatorTargetsBuffer',defaultValue = [''])
    self.var_keysMode = cgmMeta.cgmOptionVar('cgmVar_locinatorKeysMode',defaultValue = 'loc') 
    
def uiFunc_change_matchMode(self,arg):
    self.var_matchMode.value = arg    
    if arg == 0:
        self.var_matchModeMove.value = 1
        self.var_matchModeRotate.value = 0
    elif arg == 1:
        self.var_matchModeMove.value = 0
        self.var_matchModeRotate.value = 1
    elif arg == 2:
        self.var_matchModeMove.value = 1
        self.var_matchModeRotate.value = 1
    else:
        self.var_matchMode.value = 2        
        raise ValueError("|{0}| >> Unknown matchMode: {1}".format(sys._getframe().f_code.co_name,arg))
    
        
def uiOptionMenu_matchMode(self, parent):
    try:#>>> KeyMode ================================================================================
        _str_section = 'match mode'
        uiMatch = mc.menuItem(p=parent, l='Match Mode ', subMenu=True)
        
        #uiMenu = mc.menuItem(p=uiMatch, l='Mode ', subMenu=True)    
        uiRC = mc.radioMenuItemCollection()
        _v = self.var_matchMode.value
        
        for i,item in enumerate(['point','orient','point/orient']):
            if i == _v:
                _rb = True
            else:_rb = False
            mc.menuItem(p=uiMatch,collection = uiRC,
                        label=item,
                        c = cgmGEN.Callback(uiFunc_change_matchMode,self,i),
                        rb = _rb)
            
        #Dyn mode...
        uiDyn = mc.menuItem(p=parent, l='Dyn Mode ', subMenu=True)        
        uiRC = mc.radioMenuItemCollection()
        _v = self.var_dynMode.value
        
        for i in range(2):
            if i == _v:
                _rb = True
            else:_rb = False
            mc.menuItem(p=uiDyn,collection = uiRC,
                        label=bool(i),
                        c = cgmGEN.Callback(self.var_dynMode.setValue,i),
                        rb = _rb)
            
        #self.var_dynMode = cgmMeta.cgmOptionVar('cgmVar_dynMode', defaultValue = 0)
        """    
        #>>> Match pivot ================================================================================    
        uiMenu = mc.menuItem(p=uiMatch, l='Pivot', subMenu=True)    
        uiRC = mc.radioMenuItemCollection() 
        _v = self.var_matchModePivot.value
        
        for i,item in enumerate(['rp','sp','boundingbox']):
            if i == _v:
                _rb = True
            else:_rb = False
            mc.menuItem(p=uiMenu,collection = uiRC,
                        label=item,
                        c = cgmGEN.Callback(self.var_matchModePivot.setValue,i),
                        rb = _rb)         """
    except Exception as err:
        log.error("|{0}| failed to load. err: {1}".format(_str_section,err)) 

    
class uiLOC(CGMUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = 'FuncOverTime'    
    WINDOW_TITLE = 'cgmLocinator - {0}'.format(__version__)
    DEFAULT_SIZE = 180, 275
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = False
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True  #always resets the size of the window when its re-created

    _checkBoxKeys = ['shared','default','user','others']
    
    def insert_init(self,*args,**kws):
            if kws:log.debug("kws: %s"%str(kws))
            if args:log.debug("args: %s"%str(args))
            log.info(self.__call__(q=True, title=True))
    
            self.__version__ = __version__
            self.__toolName__ = 'cgmLocinator'		
            #self.l_allowedDockAreas = []
            self.WINDOW_TITLE = ui.WINDOW_TITLE
            self.DEFAULT_SIZE = ui.DEFAULT_SIZE
            
            self.currentFrameOnly = True
            self.startFrame = ''
            self.endFrame = ''
            self.startFrameField = ''
            self.endFrameField = ''
            self.forceBoundingBoxState = False
            self.forceEveryFrame = False
            self.showHelp = False
            self.helpBlurbs = []
            self.oldGenBlurbs = []
        
            self.showTimeSubMenu = False
            self.timeSubMenu = []            
            

            uiSetupOptionVars(self)
            self.create_guiOptionVar('bakeFrameCollapse',defaultValue = 0) 
            
    def build_layoutWrapper(self,parent):
        _str_func = 'build_layoutWrapper'
        
        _MainForm = mUI.MelFormLayout(self,ut='cgmUITemplate')            
        ui_tabs = mUI.MelTabLayout( _MainForm,w=180,ut='cgmUITemplate' )
        uiTab_update = mUI.MelColumnLayout(ui_tabs)
        uiTab_create = mUI.MelColumnLayout( ui_tabs )
        
        for i,tab in enumerate(['Update','Create']):
            ui_tabs.setLabel(i,tab)
            
        self.buildTab_create(uiTab_create)
        self.buildTab_update(uiTab_update)
        
        _row_cgm = CGMUI.add_cgmFooter(_MainForm)            
        _MainForm(edit = True,
                  af = [(ui_tabs,"top",0),
                        (ui_tabs,"left",0),
                        (ui_tabs,"right",0),                        
                        (_row_cgm,"left",0),
                        (_row_cgm,"right",0),                        
                        (_row_cgm,"bottom",0),
    
                        ],
                  ac = [(ui_tabs,"bottom",2,_row_cgm),
                        ],
                  attachNone = [(_row_cgm,"top")])          
    def build_menus(self):
        #pmc
        self.uiMenu_options = mUI.MelMenu( l='Options', pmc = cgmGEN.Callback(self.buildMenu_options) )
        self.uiMenu_Buffer = mUI.MelMenu( l='Buffer', pmc = cgmGEN.Callback(self.buildMenu_buffer))
        self.uiMenu_help = mUI.MelMenu( l='Help', pmc = cgmGEN.Callback(self.buildMenu_help))        
        #pass#...don't want em  
    #def setup_Variables(self):pas
    
    
    def buildMenu_buffer(self):
        self.uiMenu_Buffer.clear()  
        
        uiMenu = self.uiMenu_Buffer   
        mc.menuItem(p=uiMenu, l="Define",
                    c= lambda *a: CGMUI.varBuffer_define(self,self.var_locinatorTargetsBuffer))
    
        mc.menuItem(p=uiMenu, l="Add Selected",
                         c= lambda *a: CGMUI.varBuffer_add(self,self.var_locinatorTargetsBuffer))
    
        mc.menuItem(p=uiMenu, l="Remove Selected",
                         c= lambda *a: CGMUI.varBuffer_remove(self,self.var_locinatorTargetsBuffer))
    
        mc.menuItem(p=uiMenu,l='----------------',en=False)
        mc.menuItem(p=uiMenu, l="Report",
                    c= lambda *a: self.var_locinatorTargetsBuffer.report())        
        mc.menuItem(p=uiMenu, l="Select Members",
                    c= lambda *a: self.var_locinatorTargetsBuffer.select())
        mc.menuItem(p=uiMenu, l="Clear",
                    c= lambda *a: self.var_locinatorTargetsBuffer.clear())       
      
    def buildMenu_help( self, *args):
        self.uiMenu_help.clear()

        mc.menuItem(parent=self.uiMenu_help,
                    l = 'Report Loc Data',
                    c = cgmGEN.Callback(MMCONTEXT.func_process, get_objDat, None,'each','Report',True,**{'report':True}),                                                                                      
                    rp = 'E')  
      
        mc.menuItem(p=self.uiMenu_help,l='----------------',en=False)
        mc.menuItem(parent=self.uiMenu_help,
                    l = 'Get Help',
                    c='import webbrowser;webbrowser.open("http://docs.cgmonks.com/locinator.html");',                        
                    rp = 'N')    
        mUI.MelMenuItem( self.uiMenu_help, l="Log Self",
                         c=lambda *a: CGMUI.log_selfReport(self) )        
    

        
    def buildMenu_options( self, *args):
        self.uiMenu_options.clear()   
        _menu = self.uiMenu_options
        
        uiOptionMenu_matchMode(self, _menu)
        
        
        #>>> 
        uiMenu_keysModes = mc.menuItem(parent = _menu,subMenu = True,
                                       l='Bake Keys')
        
        uiRC = mc.radioMenuItemCollection(parent = uiMenu_keysModes)
        _v = self.var_keysMode.value
    
        _d_annos = {'loc':'Use keys of the loc',
                    'source':'Use keys of the source',
                    'combine':'Combine keys of the loc and source',
                    'frames':'Within specified range, every frame',
                    'twos':'Within specified range, on twos',
                    'threes':'Within specified range, on threes'}
        
        """
        timeMode(str):
            :slider/range
            :scene
            :custom
        keysMode(str)
            :loc
            :source
            :combine
            :frames -- bake every frame
            :twos
            :threes
        """
    
        for i,item in enumerate(['loc','source','combine','frames','twos','threes']):
            if item == _v:
                _rb = True
            else:_rb = False
            mc.menuItem(parent=uiMenu_keysModes,collection = uiRC,
                        label=item,
                        ann=_d_annos.get(item,'Fill out the dict!'),                        
                        c = cgmGEN.Callback(self.var_keysMode.setValue,item),                                  
                        rb = _rb) 
    

        mc.menuItem(p=_menu,l='----------------',en=False)
        
        mc.menuItem(parent=_menu,
                    l = 'Tag Selected',
                    ann = 'Tag to last as cgmMatchTarget',
                    c = cgmGEN.Callback(MMCONTEXT.func_process, SNAP.matchTarget_set, None,'eachToLast','Tag cgmMatchTarget',False),                                                                                      
                    rp = 'SE') 
        mc.menuItem(parent=_menu,
                    l = 'Clear Selected',
                    ann = 'Clear match Target data from selected objects',
                    c = cgmGEN.Callback(MMCONTEXT.func_process, SNAP.matchTarget_clear, None,'each','Clear cgmMatch data',True),                                                                                                      
                    rp = 'S')          
            
   
        
    def uiFunc_updateTimeRange(self,mode = 'slider'):
        _range = SEARCH.get_time(mode)
        if _range:
            self.uiFieldInt_start(edit = True, value = _range[0])
            self.uiFieldInt_end(edit = True, value = _range[1])            
             
        
        
        
    def buildTab_update(self,parent):
        _column = mUI.MelColumnLayout(parent,useTemplate = 'cgmUITemplate')
        
        self.buildRow_update(_column)

        mc.setParent(_column)    
        
        CGMUI.add_LineBreak()
        
        _bake_frame = mUI.MelFrameLayout(_column,label = 'Bake',vis=True,
                                         collapse=self.var_bakeFrameCollapse.value,
                                         collapsable=True,
                                         enable=True,
                                         useTemplate = 'cgmUIHeaderTemplate',
                                         expandCommand = lambda:self.var_bakeFrameCollapse.setValue(0),
                                         collapseCommand = lambda:self.var_bakeFrameCollapse.setValue(1)
                                         )	
        _frame_inside = mUI.MelColumnLayout(_bake_frame,useTemplate = 'cgmUISubTemplate')
        
        
        #>>>Update Row ---------------------------------------------------------------------------------------
        mc.setParent(_frame_inside)
        _row_timeSet = mUI.MelHLayout(_frame_inside,ut='cgmUISubTemplate',padding = 1)
    
        CGMUI.add_Button(_row_timeSet,'Slider',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange,'slider'),                         
                         #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                         _d_annotations.get('sliderRange','fix sliderRange'))
        CGMUI.add_Button(_row_timeSet,'Sel',
                                 cgmGEN.Callback(self.uiFunc_updateTimeRange,'selected'),                         
                                 #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                                 _d_annotations.get('selectedRange','fix selectedRange'))        
    
        CGMUI.add_Button(_row_timeSet,'Scene',
                         cgmGEN.Callback(self.uiFunc_updateTimeRange,'scene'),                         
                         _d_annotations.get('sceneRange','fix sceneRange'))
  
        
        _row_timeSet.layout()          
        
        # TimeInput Row ----------------------------------------------------------------------------------
        _row_time = mUI.MelHSingleStretchLayout(_frame_inside,ut='cgmUISubTemplate')
        self.timeSubMenu.append( _row_time )
        mUI.MelSpacer(_row_time)
        mUI.MelLabel(_row_time,l='start')
    
        self.uiFieldInt_start = mUI.MelIntField(_row_time,'cgmLocWinStartFrameField',
                                                width = 40)
        _row_time.setStretchWidget( mUI.MelSpacer(_row_time) )
        mUI.MelLabel(_row_time,l='end')
    
        self.uiFieldInt_end = mUI.MelIntField(_row_time,'cgmLocWinEndFrameField',
                                              width = 40)
        
        self.uiFunc_updateTimeRange()
    
        mUI.MelSpacer(_row_time)
        _row_time.layout()   
        
        
        #>>>Bake Mode ----------------------------------------------------------------------------------        
        self.create_guiOptionVar('bakeMode',defaultValue = 0)       
        mc.setParent(_frame_inside)
    
        _rc_keyMode = mUI.MelRadioCollection()
        
        _l_bakeModes = ['sel','buffer']
        
        #build our sub section options
        _row_bakeModes = mUI.MelHSingleStretchLayout(_frame_inside,ut='cgmUISubTemplate',padding = 5)
        mUI.MelSpacer(_row_bakeModes,w=2)        
        mUI.MelLabel(_row_bakeModes,l = 'Mode:')
        _row_bakeModes.setStretchWidget( mUI.MelSeparator(_row_bakeModes) )
    
        _on = self.var_bakeMode.value
    
        for i,item in enumerate(_l_bakeModes):
            if i == _on:_rb = True
            else:_rb = False
            _rc_keyMode.createButton(_row_bakeModes,label=_l_bakeModes[i],sl=_rb,
                                     onCommand = cgmGEN.Callback(self.var_bakeMode.setValue,i))
            mUI.MelSpacer(_row_bakeModes,w=2)

        _row_bakeModes.layout()         
        

        #>>>Update Row ---------------------------------------------------------------------------------------
        
        mc.setParent(_frame_inside)
        CGMUI.add_LineSubBreak()
        
        _row_bake = mUI.MelHLayout(_frame_inside,ut='cgmUISubTemplate',padding = 1)
    
        CGMUI.add_Button(_row_bake,' <<<',
                         cgmGEN.Callback(self.uiFunc_bake,'back'),                         
                         #lambda *a: attrToolsLib.doAddAttributesToSelected(self),
                         _d_annotations.get('<<<','fix'))
    
        CGMUI.add_Button(_row_bake,'Range',
                         cgmGEN.Callback(self.uiFunc_bake,'all'),                         
                         _d_annotations.get('All','fix'))
        
        
        CGMUI.add_Button(_row_bake,'>>>',
                         cgmGEN.Callback(self.uiFunc_bake,'forward'),                         
                         _d_annotations.get('>>>','fix'))    
        
        _row_bake.layout()
        
        mUI.MelButton(_frame_inside,label = 'Selected Time',
                      ut='cgmUITemplate',
                      c = cgmGEN.Callback(self.uiFunc_bake,'selectedRange'),                         
                      ann=_d_annotations.get('Selected','fix'))        
        
        
    def uiFunc_bake(self,mode='all'):
        _bakeMode = self.var_bakeMode.value
        if _bakeMode == 0:
            _targets = None
        else:
            _targets = self.var_locinatorTargetsBuffer.value
            if not _targets:
                log.error("Buffer is empty")
                return False
            
        if mode == 'selectedRange':
            _kws = {'move':self.var_matchModeMove.value,'rotate':self.var_matchModeRotate.value,
                    'boundingBox':False,'keysMode':self.var_keysMode.value,'keysDirection':mode,
                    'timeMode':'selected'}
        else:
            _kws = {'move':self.var_matchModeMove.value,'rotate':self.var_matchModeRotate.value,
                    'boundingBox':False,'keysMode':self.var_keysMode.value,'keysDirection':mode,
                    'timeMode':'custom','timeRange':[self.uiFieldInt_start(q=True, value = True),self.uiFieldInt_end(q=True, value = True)]}
            
        MMCONTEXT.func_process(bake_match, _targets,'all','Bake',False,**_kws)       
                                                                    

        
    def buildTab_create(self,parent):
        _column = mUI.MelColumnLayout(parent,useTemplate = 'cgmUITemplate')
            
        #>>>  Center Section
        CGMUI.add_Header('Create')        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Loc Me',
                        cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, None,'each'),
                        _d_annotations['me'])
        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Mid point',
                         cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, None,'all','midPointLoc',False,**{'mode':'midPoint'}),                                                                      
                         _d_annotations['mid'])          
        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Attach point',
                         cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, None,'all','attachPoint',False,**{'mode':'attachPoint'}),                                                                      
                         _d_annotations['attach'])
        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Closest point',
                         cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, None,'all','closestPoint',False,**{'mode':'closestPoint'}),                                                                      
                         _d_annotations['closestPoint'])
        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Closest target',
                         cgmGEN.Callback(MMCONTEXT.func_process, LOC.create, None,'all','closestTarget',False,**{'mode':'closestTarget'}),                                                                      
                         _d_annotations['closestTarget'])        
        
        
        CGMUI.add_LineSubBreak()
        CGMUI.add_Button(_column,'Raycast',
                         lambda *a:LOC.create(mode = 'rayCast'),                                                                      
                         _d_annotations['rayCast'])  
        
        
        CGMUI.add_LineBreak()
        
        self.buildRow_update(_column)
        
    def buildRow_update(self,parent):
        #>>>Update Row ---------------------------------------------------------------------------------------
        mc.setParent(parent)
        CGMUI.add_Header('Update')
        _row_update = mUI.MelHLayout(parent,ut='cgmUISubTemplate',padding = 1)
    
        CGMUI.add_Button(_row_update,' Self',
                         lambda *a:update_uiCall('self'),
                         #cgmGEN.Callback(MMCONTEXT.func_process, update_obj, None,'each','Match',False,**{'move':self.var_matchModeMove.value,'rotate':self.var_matchModeRotate.value,'mode':'self'}),                         
                         _d_annotations.get('updateSelf','fix'))
    
        CGMUI.add_Button(_row_update,'Target',
                         lambda *a:update_uiCall('target'),
                         #cgmGEN.Callback(MMCONTEXT.func_process, update_obj, None,'each','Match',False,**{'move':self.var_matchModeMove.value,'rotate':self.var_matchModeRotate.value,'mode':'target'}),                                                  
                         _d_annotations.get('updateTarget','fix'))
        
        
        CGMUI.add_Button(_row_update,'Buffer',
                         lambda *a:update_uiCall('buffer'),                         
                         #cgmGEN.Callback(MMCONTEXT.func_process, update_obj, None,'each','Match',False,**{'move':self.var_matchModeMove.value,'rotate':self.var_matchModeRotate.value,'mode':'buffer'}),                                                                           
                         _d_annotations.get('updateBuffer','fix'))    
        
        _row_update.layout()        
        
        
        





