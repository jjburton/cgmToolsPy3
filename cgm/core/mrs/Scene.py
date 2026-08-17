from ast import mod
import maya.cmds as mc
import maya.mel as mel
import pprint
from functools import partial, reduce
import os
import time
from datetime import datetime
import json
import datetime
import copy
import sys

from shutil import copyfile
#import fnmatch
import cgm.lib.pyui as pyui
#import subprocess
import re
from cgm.core import cgm_Meta as cgmMeta
from cgm.core.lib import asset_utils as ASSET
from cgm.core.tools import Project as Project
from cgm.core.mrs.lib import batch_utils as BATCH
from cgm.core import cgm_General as cgmGEN
from cgm.core.lib import math_utils as MATH
from cgm.core.mrs.lib import scene_utils as SCENEUTILS
#reload(SCENEUTILS)
from cgm.core.lib import skinDat as SKINDAT
import cgm.core.mrs.Builder as BUILDER
import cgm.core.lib.mayaBeOdd_utils as MAYABEODD
import cgm.core.cgmPy.validateArgs as VALID
import cgm.core.tools.Project as PROJECT
import cgm.core.tools.lib.project_utils as PU
import Red9.core.Red9_General as r9General
import cgm.core.mrs.SceneDat as SCENEDAT
import cgm.core.lib.string_utils as CORESTRING
import cgm.core.lib.path_utils as PATHUTIL

import cgm.core.classes.GuiFactory as cgmUI
import importlib
#reload(cgmUI)
mUI = cgmUI.mUI

import cgm.core.cgmPy.path_Utils as PATHS
import cgm.core.cgmPy.os_Utils as CGMOS

import cgm.images as cgmImages

import cgm.images.icons as cgmIcons
_path_imageFolder = PATHS.Path(cgmIcons.__file__).up().asFriendly()


mImagesPath = PATHS.Path(cgmImages.__path__[0])

global UI
UI = None
def ui_get():
    global UI
    if UI:
        log.debug('cached...')
        UI.show()
        return UI
    return ui()

log_start = cgmGEN.logString_start
log_end = cgmGEN.logString_end
log_msg = cgmGEN.logString_msg
log_sub = cgmGEN.logString_sub

_batch_export_results = []


def clear_batch_export_results():
    """Reset export summary list (call at batch start)."""
    global _batch_export_results
    _batch_export_results = []


def extend_batch_export_results(entries):
    """Append per-scene export results for batch rollup."""
    global _batch_export_results
    if entries:
        _batch_export_results.extend(entries)


def log_export_results_summary(_str_func, results, title='Export summary', log_scene_up=True):
    """Log a readable list of exported shots/files and frame ranges."""
    if not results and not log_scene_up:
        return
    log.info(cgmGEN._str_hardBreak)
    if results:
        log.info("{0} | {1} | {2} export(s)".format(_str_func, title, len(results)))
        for i, r in enumerate(results):
            _name = r.get('name') or os.path.basename(r.get('path', ''))
            _path = r.get('path', '')
            _frames = r.get('frames')
            if _frames is not None:
                log.info("{0} |   [{1}] {2}  |  frames {3}-{4}  |  {5}".format(
                    _str_func, i + 1, _name, _frames[0], _frames[1], _path))
            else:
                log.info("{0} |   [{1}] {2}  |  {3}".format(_str_func, i + 1, _name, _path))
    if log_scene_up:
        log.info("{0} | UP axis: {1}".format(_str_func, mc.upAxis(q=True, axis=True)))
    log.info(cgmGEN._str_hardBreak)

#>>>======================================================================
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
#=========================================================================
_d_ann = SCENEUTILS.d_annotations

_EXPORT_ERROR_STAGES = (
    'path_resolve',
    'prep',
    'bake',
    'fbx_export',
    'post_cleanup',
    'batch_item',
)


def _export_ctx_to_str(ctx):
    """Stable key/value formatting for export error reporting."""
    if not ctx:
        return 'context=none'
    l_msg = []
    for k in sorted(ctx.keys()):
        l_msg.append('{0}={1}'.format(k, ctx.get(k)))
    return ' | '.join(l_msg)


def _export_transforms_after_mesh_strip(deleteMesh, exportTransforms, obj, fallback_members=None):
    """
    After deleteMesh removes mesh transforms, exportTransforms may still list deleted
    DAG nodes (from Prep). Return names that still exist, or fall back to export set
    members (*fallback_members*) and finally the export context hint *obj* if it exists.
    Returns None if deleteMesh ran and no valid target could be resolved.
    """
    if not deleteMesh:
        return exportTransforms
    if isinstance(exportTransforms, (list, tuple)):
        _alive = [n for n in exportTransforms if n and mc.objExists(n)]
        exportTransforms = _alive if _alive else None
    elif exportTransforms and mc.objExists(exportTransforms):
        exportTransforms = [exportTransforms]
    else:
        exportTransforms = None
    if not exportTransforms:
        _resolved = []
        _seen = set()
        for m in fallback_members or []:
            if not m:
                continue
            _short = m.split('|')[-1].split(':')[-1]
            _path = (mc.ls(_short, l=True) or [None])[0]
            if _path and mc.objExists(_path) and _path not in _seen:
                _seen.add(_path)
                _resolved.append(_path)
            elif mc.objExists(m) and m not in _seen:
                _seen.add(m)
                _resolved.append(m)
        if _resolved:
            exportTransforms = _resolved
        else:
            for _cand in (obj, obj.split('|')[-1] if obj else '', (obj.split('|')[-1].split(':')[-1] if obj else '')):
                if _cand and mc.objExists(_cand):
                    exportTransforms = [_cand]
                    break
            else:
                exportTransforms = None
    return exportTransforms


#>>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ ='mrsScene'

_subLineBGC = [.75,.75,.75]
_l_directoryMask = ['meta','.mayaSwatches','incrementalSave','cgmDat','mayaSwatches']

# Dependencies — reloaded on Scene open via reload_dependencies()
l_dependencies = (
    'cgm.core.tools.lib.project_utils',
)


def reload_dependencies():
    """Reload Scene backend modules (tool open / Reload menu / Reload SceneStuff)."""
    global PU
    import cgm.core.tools.lib.project_utils as _project_utils
    cgmGEN._reloadMod(_project_utils)
    PU = _project_utils
    return PU


def reloadSceneStuff():
    """Reload export pipeline modules without cgm.core._reload()."""
    import cgm.core.tools.bakeAndPrep as bakeAndPrep
    import cgm.core.mrs.Shots as SHOTS
    import cgm.core.lib.mayaSettings_utils as MAYASET

    log.info("reloading Scene Stuff...")
    reload_dependencies()
    for m in [bakeAndPrep, SHOTS, BATCH, PATHUTIL, MAYASET, SCENEUTILS]:
        print(m)
        cgmGEN._reloadMod(m)
    log.info(cgmGEN._str_subLine)


class ui(cgmUI.cgmGUI):
    '''
Scene UI class.

Loads the SceneUI.

| outputs AnimationImporter

example:
.. python::

    import cgm.core.mrs.Scene as SCENE
    x = SCENE.SceneUI()

    # returns loaded directory
    print x.directory

    # prints the names of all of the loaded assets
    print x.assetList
    '''

    WINDOW_NAME = 'cgmScene'
    DEFAULT_SIZE = 800, 400

    TOOLNAME = 'cgmScene'
    WINDOW_TITLE = '%s - %s'%(TOOLNAME,__version__)    
    reload_dependencies()
    cgmGEN._reloadMod(SCENEUTILS)

    def reload(self):
        reload_dependencies()
        cgmGEN._reloadMod(SCENEUTILS)
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()

    def insert_init(self,*args,**kws):
        self.b_loadState = False
        self.path_current = None
        self.categoryList                = ["Character", "Environment", "Props"]
        self.categoryIndex               = 0

        self.subTypes                    = ['animation']
        self.subTypeIndex                = 0
        self.l_subTypesBase = []
        self._subTypePathWarningsShown = set()
        self.b_subFile = False
        self.b_varFile = False
        self.var_lastProject       = cgmMeta.cgmOptionVar("cgmVar_projectCurrent", varType = "string")
        self.var_lastAsset     = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_asset", varType = "string")
        self.var_lastSubtype      = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_subtype", varType = "string")        
        self.var_lastSet      = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_set", varType = "string")
        self.var_lastVariation = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_variation", varType = "string")
        self.var_lastVersion   = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_version", varType = "string")
        self.var_showAllFiles           = cgmMeta.cgmOptionVar("cgmVar_sceneUI_show_all_files", defaultValue = 1)
        #self.var_removeNamespace        = cgmMeta.cgmOptionVar("cgmVar_sceneUI_remove_namespace", defaultValue = 0)
        #self.var_zeroRoot               = cgmMeta.cgmOptionVar("cgmVar_sceneUI_zero_root", defaultValue = 0)
        self.var_useMayaPy              = cgmMeta.cgmOptionVar("cgmVar_sceneUI_use_mayaPy", defaultValue = 1)
        self.var_categoryStore               = cgmMeta.cgmOptionVar("cgmVar_sceneUI_category", defaultValue = 0)
        self.var_subTypeStore                = cgmMeta.cgmOptionVar("cgmVar_sceneUI_subType", defaultValue = 0)
        self.var_alwaysSendReferenceFiles    = cgmMeta.cgmOptionVar("cgmVar_sceneUI_alwaysSendReferences", varType= 'int', defaultValue = 0)
        self.var_showDirectories        = cgmMeta.cgmOptionVar("cgmVar_sceneUI_show_directories", defaultValue = 0)
        self.var_showPathWarnings       = cgmMeta.cgmOptionVar("cgmVar_sceneUI_show_path_warnings", defaultValue = 0)
        self.var_displayDetails         = cgmMeta.cgmOptionVar("cgmVar_sceneUI_display_details", defaultValue = 1)
        self.var_displayProject         = cgmMeta.cgmOptionVar("cgmVar_sceneUI_display_project", defaultValue = 1)

        #self.var_postEuler          = cgmMeta.cgmOptionVar("cgmVar_sceneUI_postEuler", defaultValue = 1)
        #self.var_postTangent     = cgmMeta.cgmOptionVar("cgmVar_sceneUI_postTangent", varType = "string", defaultValue='auto')
        #self.var_mayaFilePref     = cgmMeta.cgmOptionVar("cgmVar_sceneUI_mayaFilePref", varType = "string", defaultValue='ma')

        self.var_posePathLocal = cgmMeta.cgmOptionVar('cgmVar_mrs_localPosePath',defaultValue = '')
        self.var_posePathProject = cgmMeta.cgmOptionVar('cgmVar_mrs_projectPosePath',defaultValue = '')        
        self.var_updateRigs               = cgmMeta.cgmOptionVar("cgmVar_sceneUI_updateRigs", defaultValue = 0)


        self.var_bakeSet                     = cgmMeta.cgmOptionVar('cgm_bake_set', varType="string",defaultValue = 'bake_tdSet')
        self.var_deleteSet                   = cgmMeta.cgmOptionVar('cgm_delete_set', varType="string",defaultValue = 'delete_tdSet')
        self.var_exportSet                   = cgmMeta.cgmOptionVar('cgm_export_set', varType="string",defaultValue = 'export_tdSet') 

        ## sizes
        self.__itemHeight                = 35
        self.__cw1                       = 125

        # UI elements
        self.assetList                   = None #pyui.SearchableList()
        self.subTypeSearchList           = None #pyui.SearchableList()
        self.variationList               = None #pyui.SearchableList()
        self.versionList                 = None #pyui.SearchableList()
        self.queueTSL                    = None #pyui.UIList()
        self.updateCB                    = None
        self.menuBarLayout               = None
        self.uiMenu_Projects             = None
        self.uiMenu_ToolsMenu            = None
        self.uiMenu_OptionsMenu          = None
        self.categoryBtn                 = None
        self.subTypeBtn                  = None
        self.exportQueueFrame            = None
        self.categoryMenu                = None
        self.categoryMenuItemList        = []
        self.subTypeMenuItemList         = []
        self.uList_sendToProject_version   = []
        self.uList_sendToProject_variant   = []
        self.d_subPops = {}
        self.assetRigMenuItemList        = []
        self.assetReferenceRigMenuItemList  = []
        self.uiPop_sendToProject_version = None
        self.uiPop_sendToProject_variant = None
        self.uiPop_sendToProject_sub = None
        self.subTypeListPUM = None
        self.variationListPUM = None
        self.versionListPUM = None
        self._d_fileListPopupPmc = {}
        self.ml_dirOptions_set = []
        self.ml_fileOptions_set = []
        self.ml_dirOptions_variant = []
        self.ml_fileOptions_variant = []
        self.ml_p4_options_set = []
        self.ml_p4_options_variant = []
        self.ml_p4_options_version = []
        self.ml_p4_options_multi = []
        self.ml_p4_options_dir_set = []
        self.ml_p4_options_dir_variant = []
        self.ml_p4_options_dir_version = []
        self.ml_p4_options_dir_asset = []
        self._version_list_refreshed = False
        self.displayProject = True
        self.mDat                     = None
        self.assetMetaData               = {}

        self.exportCommand               = ""

        self.cb_showAllFiles          = None
        #self.cb_removeNamespace       = None
        #self.cb_zeroRoot              = None
        self.cb_useMayaPy             = None
        self.cb_showDirectories       = None
        self.cb_showPathWarnings      = None

        self.showDirectories             = self.var_showDirectories.getValue()
        self.showPathWarnings            = bool(self.var_showPathWarnings.getValue())
        self.displayDetails              = self.var_displayDetails.getValue()

        self.showAllFiles                = self.var_showAllFiles.getValue()
        #self.removeNamespace             = self.var_removeNamespace.getValue()
        #self.zeroRoot                    = self.var_zeroRoot.getValue()
        self.useMayaPy                   = self.var_useMayaPy.getValue()

        self.fileListMenuItems           = []
        self.batchExportItems            = []

        self.exportDirectory             = None

        self.v_bgc                       = [.6,.3,.3]
        self.updateRigsCB = None

        #Project migration ---------------------------------------------------------------------------------------
        self.pathProject = None
        self.mDat = PROJECT.data()
        self.path_projectConfig = None
        self.var_project = cgmMeta.cgmOptionVar('cgmVar_projectCurrent',defaultValue = '')
        self.var_pathProject = cgmMeta.cgmOptionVar('cgmVar_projectPath',defaultValue = '')
        self.var_pathLastProject = cgmMeta.cgmOptionVar('cgmVar_projectLastPath',defaultValue = '')
        self.mPathList = PROJECT.pathList_project('cgmProjectPaths')
        self.mPathList_recent = cgmMeta.pathList('cgmProjectPathsRecent')
        self.d_projectPathsToNames = {}
        self.d_tf = {}
        self.d_uiTypes = {}
        self.d_buttons = {}
        self.d_labels = {}        
        self.d_userPaths = {}
        self.mExportDat = None
        self.l_dirMask = copy.copy(_l_directoryMask)
        
        global UI
        UI = self

    def post_init(self,*args,**kws):
        if self.var_lastProject.getValue():
            self.LoadProject(self.var_lastProject.getValue())
        else:
            mPathList = cgmMeta.pathList('cgmProjectPaths')
            try:self.LoadProject(mPathList.mOptionVar.value[0])
            except:pass
    @property
    def directory(self):
        return self.directoryTF.getValue() #self.d_userPaths.get('content')

    @directory.setter
    def directory(self, directory):
        self.directoryTF.setValue( directory )

    @property
    def path_dir_category(self):
        return os.path.normpath(os.path.join( self.directory, self.category ))

    def rebuild_scriptUI(self):
        _str_func = 'rebuild_scriptUI'
        log.debug(log_start(_str_func))
        self.uiMenu_projectUtils(edit=True, vis=False)

        _path = self.d_userPaths.get('scriptUI')
        if not _path:
            return log.debug(cgmGEN.logString_msg(_str_func, "No scriptUI path"))

        if not os.path.exists(_path):
            return log.debug(cgmGEN.logString_msg(_str_func, "path doesn't exist: {}".format(_path)))

        log.debug(cgmGEN.logString_msg(_str_func, _path))
        module = None
        if float(cgmGEN.__mayaVersion__) < 2022:
            import imp
            if _path.endswith('.py'):
                _pyc = _path.replace('.py','.pyc')
                if os.path.exists(_pyc):
                    os.remove(_pyc)
            module = imp.load_source('tmp',_path)
        else:
            module_name = os.path.splitext(os.path.basename(_path))[0]
            module = __import__(module_name, globals(), locals(), ['*'])
            cgmGEN._reloadMod(module) 

            # import importlib.util
            # spec = importlib.util.spec_from_file_location('tmp', _path)
            # module = importlib.util.module_from_spec(spec)
            # spec.loader.exec_module(module)
            
            # sys.modules['tmp'] = module
            # importlib.reload(module.__path__)

        if not module:
            log.warning("Unknown scriptUI module: {}".format(_path))
            return
        self.uiMenu_projectUtils(edit=True, vis=True)

        self.uiMenu_projectUtils.clear()

        if module.__dict__.get('uiMenu'):
            log.debug(log_msg(_str_func, "trying to load..."))
            module.uiMenu(self, self.uiMenu_projectUtils)

            mUI.MelMenuItemDiv(self.uiMenu_projectUtils)
            mUI.MelMenuItemDiv(self.uiMenu_projectUtils)

            mUI.MelMenuItem(self.uiMenu_projectUtils,
                    l = 'Reload Menu',
                    c = lambda *a: self.rebuild_scriptUI())
        else:
            log.warning(cgmGEN.logString_msg(_str_func, "No uiMenu function found on : {}".format(_path)))



    def report_selectedPaths(self):
        _str_func = 'report_selectedPaths'
        log.debug(log_start(_str_func))
        log.debug("Directory: {0}".format(self.directory))
        log.debug("Asset: {0}".format(self.path_asset))
        log.debug("Subtype Dir: {0}".format(self.path_subType))
        log.debug("Subtype: {0}".format(self.path_subType))
        log.debug("Variation: {0}".format(self.path_variationDirectory))
        log.debug("Version: {0}".format(self.path_versionDirectory))

    def _log_picked_file_to_script_editor(self):
        """Echo resolved file path to Script Editor when user picks a file row."""
        try:
            _path = self.versionFile
            if _path and os.path.isfile(_path):
                log.info(_path)
        except Exception:
            pass

    def report_lastSelection(self):
        _str_func = 'report_lastSelection'
        log.debug(log_start(_str_func))
        log.debug("Project: {0}".format(self.var_lastProject.value))
        log.debug("Asset: {0}".format(self.var_lastAsset.value))
        log.debug("Subtype: {0}".format(self.var_lastSubtype.value))
        log.debug("Set: {0}".format(self.var_lastSet.value))
        log.debug("Variation: {0}".format(self.var_lastVariation.value))
        log.debug("Version: {0}".format(self.var_lastVersion.value))

    def report_states(self):
        _str_func = 'report_states'
        log.debug(log_start(_str_func))
        log.debug(log_sub(_str_func,'Options...'))
        log.debug("Category: {0}".format(self.category))
        log.debug("Asset: {0}".format(self.selectedAsset))
        log.debug("Subtype: {0}".format(self.subType))
        log.debug("Set: {0}".format(self.selectedSet))
        log.debug("Variation: {0}".format(self.selectedVariation))
        log.debug("Version: {0}".format(self.selectedVersion))
        log.debug("File: {0}".format(self.versionFile))
        log.debug(log_sub(_str_func,'Paths...'))
        log.debug("Directory: {0}".format(self.directory))
        log.debug("Asset: {0}".format(self.path_asset))
        log.debug("Subtype Dir: {0}".format(self.path_subType))
        log.debug("Set: {0}".format(self.path_set))
        log.debug("Variation: {0}".format(self.path_variationDirectory))
        log.debug("Version: {0}".format(self.path_versionDirectory))
        log.debug(log_sub(_str_func,'States...'))
        log.debug("hasSub: {0}".format(self.hasSub))
        log.debug("hasVariant: {0}".format(self.hasVariant))
        log.debug("hasNested: {0}".format(self.hasNested))
        log.debug("hasSubTypes: {0}".format(self.hasSubTypes))

    @property
    def selectedAsset(self):
        return self.assetList['scrollList'].getSelectedItem()

    @property
    def path_asset(self):
        try:return os.path.normpath(os.path.join( self.path_dir_category, self.assetList['scrollList'].getSelectedItem() )) if self.assetList['scrollList'].getSelectedItem() else None
        except Exception as err:
            log.debug(err)
            return False
        
    @property
    def selectedSet(self):
        _path = self.path_set
        if PATHS.Path(_path).isDir():
            return self.subTypeSearchList['scrollList'].getSelectedItem()	
        return False
    
    @property
    def path_subType(self):
        try:
            return self._resolve_subType_container_path(self.path_asset, self.subType)
        except Exception as err:
            log.debug(err)
            return False

    @property
    def path_set(self):
        try:
            if self.hasSub:
                if self.subTypeSearchList['scrollList'].getSelectedItem():
                    _subTypePath = self.path_subType
                    if not _subTypePath:
                        return None
                    return os.path.normpath(os.path.join(_subTypePath, self.subTypeSearchList['scrollList'].getSelectedItem()))
                else:
                    return None
            else:
                return self.path_subType
        except Exception as err:
            log.debug(err)
            return False


    @property
    def selectedVariation(self):
        return self.variationList['scrollList'].getSelectedItem()

    @property
    def path_variationDirectory(self):
        try:return os.path.normpath(os.path.join( self.path_set, self.variationList['scrollList'].getSelectedItem() )) if self.variationList['scrollList'].getSelectedItem() else None
        except Exception as err:
            log.debug(err)
            return False

    def _version_files_parent_directory(self):
        """
        Folder that holds version .ma/.mb files — must match LoadVersionList searchDir
        (including projects with no subtype tabs, where versions live under path_asset).
        """
        try:
            if not self.subTypes:
                _d = self.path_asset
            elif self.hasVariant:
                _d = self.path_variationDirectory
            elif self.hasSub:
                _d = self.path_set
            else:
                _d = self.path_subType
            if not isinstance(_d, str) or not _d:
                return None
            return os.path.normpath(_d)
        except Exception as err:
            log.debug(err)
            return None

    @property
    def path_versionDirectory(self):
        return self._version_files_parent_directory()

    @property
    def selectedVersion(self):
        return self.versionList['scrollList'].getSelectedItem()

    @property
    def versionFile(self):

        _set =  self.path_set
        log.debug(_set)
        if _set and os.path.isfile(_set):
            return _set
        _var = self.path_variationDirectory
        if _var and os.path.isfile(_var):
            return _var
        """
        _version = self.selectedVersion
        log.info(_version)
        if _version and os.path.isfile(_version):
            return _version

        _variation = self.selectedVariation
        log.info(_variation)
        if _variation and os.path.isfile(_variation):
            return _variation
        """


        #return None

        #log.info("Set: {0}".format(self.selectedSet))
        #log.info("Variation: {0}".format(self.selectedVariation))        
        #log.info("Version: {0}".format(self.selectedVersion))           
        try:
            if self.hasSub:
                if self.hasVariant:
                    return os.path.normpath(os.path.join( self.path_variationDirectory, self.versionList['scrollList'].getSelectedItem() )) if self.versionList['scrollList'].getSelectedItem() else None
                else:
                    return os.path.normpath(os.path.join( self.path_set, self.versionList['scrollList'].getSelectedItem() )) if self.versionList['scrollList'].getSelectedItem() else None
            else:
                if self.hasSubTypes:
                    return os.path.normpath(os.path.join( self.path_subType, self.subTypeSearchList['scrollList'].getSelectedItem() )) if self.subTypeSearchList['scrollList'].getSelectedItem() else None                                        
                else:
                    return os.path.normpath(os.path.join( self.path_asset, self.versionList['scrollList'].getSelectedItem() )) if self.versionList['scrollList'].getSelectedItem() else None                    
                #else:
                #return os.path.normpath(os.path.join( self.path_set, self.subTypeSearchList['scrollList'].getSelectedItem() )) if self.subTypeSearchList['scrollList'].getSelectedItem() else None
        except Exception as err:log.error("Version file query fail: {}".format(err))

    @property
    def exportFileName(self):
        if self.hasSub:
            if self.hasVariant:
                return '{0}_{1}_{2}.fbx'.format(self.assetList['scrollList'].getSelectedItem(), self.subTypeSearchList['scrollList'].getSelectedItem(), self.variationList['scrollList'].getSelectedItem())
            else:
                return '{0}_{1}.fbx'.format(self.assetList['scrollList'].getSelectedItem(), self.subTypeSearchList['scrollList'].getSelectedItem())
        else:
            return '{0}_{1}.fbx'.format(self.assetList['scrollList'].getSelectedItem(), PU.subtype_file_token(self.subType))


    @property
    def category(self):
        _str_func = 'category'
        log.debug(log_start(_str_func))        
        return self.categoryList[self.categoryIndex] if len(self.categoryList) > self.categoryIndex else self.categoryList[0]

    @property
    def subType(self):
        _str_func = 'subType'
        log.debug(log_start(_str_func))
        log.debug(log_msg(_str_func, self.subTypeIndex))
        return self.subTypes[min(self.subTypeIndex, len(self.subTypes)-1)] if self.subTypes else None

    @property
    def hasSub(self):
        _str_func = 'hasSub'

        _res = False
        _path  = self.path_subType
        if not _path:
            return False

        if not os.path.isdir(_path):
            return False

        log.debug(log_start(_str_func))    
        log.debug(log_msg(_str_func, self.category))
        log.debug(log_msg(_str_func, _path))

        #path_set= os.path.normpath(os.path.join( self.path_dir_category, self.category ))
        _dirs = CGMOS.get_lsFromPath(_path,'dir')
        _dirsUse = []      
        for d in _dirs:
            if d.lower() not in self.l_dirMask:
                _dirsUse.append(d)

        if _dirsUse:
            _res = True

        #log.debug(log_start(_str_func))    
        #pprint.pprint(_dirs)
        log.debug(log_msg(_str_func,_res))
        return _res


        """
        try:
            r = self.mDat.assetType_get(self.category)['content'][self.subTypeIndex].get('hasSub', False)
            return r
        except:
            return True

        """
    @property
    def hasSubTypes(self):
        _str_func = 'hasSubTypes'

        _res = False
        _path = self.path_asset
        if not _path:
            return False

        log.debug(log_start(_str_func))    
        log.debug(log_msg(_str_func, self.subType))

        #path_set= os.path.normpath(os.path.join( self.path_dir_category, self.category ))
        _dirsRaw = CGMOS.get_lsFromPath(_path,'dir')
        _dirs = []
        for d in _dirsRaw:
            log.debug(d)
            if d.lower() not in self.l_dirMask:
                _dirs.append(d)

            #return False
        #log.info("hasSubTypes...")
        #pprint.pprint(_dirs)
        if _dirs:
            _res = True

        log.debug(log_msg(_str_func,_res))
        return _res

    @property
    def hasNested(self):
        _str_func = 'hasSub'

        _res = False
        _path = self.path_subType
        if not _path:
            return False

        log.debug(log_start(_str_func))    
        log.debug(log_msg(_str_func, self.subType))

        #path_set= os.path.normpath(os.path.join( self.path_dir_category, self.category ))
        _dirsRaw = CGMOS.get_lsFromPath(_path,'dir')
        _dirs = []
        for d in _dirsRaw:
            if d.lower() not in self.l_dirMask:
                print(log_msg(_str_func, "{} | {}".format(self.subType,d )))
                _dirs.append(d)
                
        #log.info("hasNested...")
        #pprint.pprint(_dirs)        

        if _dirs:
            _res = True

        log.debug(log_msg(_str_func,_res))
        return _res

    @property
    def hasVariant(self):
        _str_func = 'hasVariant'
        _res = False
        _dirs = []
        _dirsRaw = []
        try:
            _path_set= self.path_set
            log.debug(log_msg(_str_func, _path_set))
        except Exception as err:
            log.error(log_msg(_str_func, err))            
            return _res

        log.debug(log_start(_str_func))
        log.debug(log_msg(_str_func, "path_set | {}".format(_path_set)))        
        if _path_set and os.path.isdir(_path_set):
            _dirsRaw = CGMOS.get_lsFromPath(_path_set,'dir')

        for d in _dirsRaw:
            if d.lower() not in self.l_dirMask:
                _dirs.append(d)
                
        #log.info("hasVariant...")
        #pprint.pprint(_dirs)             

        if _dirs:
            _res = True


        log.debug(log_msg(_str_func,_res))

        return _res
        """
        try:
            r = self.mDat.assetType_get(self.category)['content'][self.subTypeIndex].get('hasVariant', False)
            return r
        except:
            return True"""

    def HasSub(self, category, subType):
        try:
            hasSub = True
            for sub in self.mDat.assetType_get(category)['content']:
                if sub['n'] == subType:
                    hasSub = sub.get('hasSub', True)
            return hasSub
        except:
            return True

    def _dir_children_dirs(self, path):
        """Immediate child directory names under *path*, filtered by dirMask."""
        if not path or not os.path.isdir(path):
            return []
        _dirs = []
        for d in CGMOS.get_lsFromPath(path, 'dir') or []:
            if not d or d[0] in ('_', '.'):
                continue
            if d.lower() in self.l_dirMask:
                continue
            _dirs.append(d)
        return _dirs

    def _dir_maya_files(self, path):
        """Immediate .ma/.mb files under *path* (loose scan for mixed-level UI)."""
        if not path or not os.path.isdir(path):
            return []
        fileExtensions = ['mb', 'ma']
        _files = []
        for f in CGMOS.get_lsFromPath(path) or []:
            if not f or f[0] in ('_', '.'):
                continue
            if os.path.isdir(os.path.join(path, f)):
                continue
            if self.showAllFiles:
                if f in ['meta']:
                    continue
                if 'MRSbatch' in f:
                    continue
                _files.append(f)
            elif os.path.splitext(f)[-1].lower()[1:] in fileExtensions:
                _files.append(f)
        return _files

    def _dir_is_mixed(self, path):
        return bool(self._dir_children_dirs(path)) and bool(self._dir_maya_files(path))

    def _subtype_level_has_content(self):
        _path = self.path_subType
        if not _path or not os.path.isdir(_path):
            return False
        return bool(self._dir_children_dirs(_path) or self._dir_maya_files(_path))

    def _level_show_dir_actions(self, path):
        if path and os.path.isdir(path) and self._dir_children_dirs(path):
            return True
        return bool(self.subTypes)

    def _level_show_file_actions(self, path, selected_is_file=False):
        if selected_is_file:
            return True
        if not path:
            return False
        if os.path.isfile(path):
            return True
        if os.path.isdir(path):
            if self._dir_maya_files(path):
                return True
            # Empty leaf dir (e.g. rig/ with no sets yet) — still allow Save / Export / Save Version
            if not self._dir_children_dirs(path):
                return True
            return False
        # Intended save root not created yet — offer file actions when asset parent exists
        _parent = os.path.dirname(os.path.normpath(path))
        return bool(_parent and os.path.isdir(_parent) and self.subTypes)

    def _sets_buttons_browse_directory(self):
        """Directory whose immediate children drive sets-row button visibility."""
        if self.b_subFile and self.file_subType:
            try:
                return os.path.dirname(os.path.normpath(self.file_subType))
            except Exception:
                pass
        if self.hasSub:
            _set = self.path_set
            if _set and os.path.isdir(_set):
                return _set
        return self.path_subType

    def _version_column_should_show(self):
        """
        Show the version column when browsing a directory that holds (or will hold)
        version files. Hide only when the *selected parent-list item* is itself a
        Maya file (b_subFile / b_varFile). Empty dirs still show so Save / Save
        Version can populate them (e.g. character/.../animation/test/cloth).
        """
        if self.b_subFile or self.b_varFile:
            return False
        if not self.subTypes:
            return True
        if not self.subTypeSearchList['scrollList'].getSelectedItem():
            return False
        if self.hasVariant:
            if not self.variationList['scrollList'].getSelectedItem():
                return False
            _varPath = self.path_variationDirectory
            return bool(_varPath and os.path.isdir(_varPath))
        _parent = self._version_files_parent_directory()
        if _parent and os.path.isdir(_parent):
            return True
        if _parent and os.path.isfile(_parent):
            return False
        _fallback = self.path_subType
        return bool(_fallback and os.path.isdir(_fallback))

    def _append_set_dir_buttons(self, row):
        if self.hasSub:
            mUI.MelIconButton(row,
                              ut='cgmUITemplate',
                              style='iconOnly',
                              l='',
                              ann="New {0}".format(self._subtypeDisplayLabel()),
                              image=os.path.join(_path_imageFolder, 'new_set.png'),
                              w=25, h=25,
                              bgc=cgmUI.guiButtonColor,
                              c=lambda *a: self.CreateSubAsset())
            if self.hasVariant == False:
                mUI.MelIconButton(row,
                                  ut='cgmUITemplate',
                                  style='iconOnly',
                                  l='',
                                  ann="Add Variation",
                                  image=os.path.join(_path_imageFolder, 'new_variation.png'),
                                  w=25, h=25,
                                  bgc=cgmUI.guiButtonColor,
                                  c=lambda *a: self.CreateVariation())
        else:
            mUI.MelIconButton(row,
                              ut='cgmUITemplate',
                              style='iconOnly',
                              l='',
                              ann="Add Set",
                              image=os.path.join(_path_imageFolder, 'new_dir.png'),
                              w=25, h=25,
                              bgc=cgmUI.guiButtonColor,
                              c=lambda *a: self.CreateSubAsset())

    def _append_set_file_buttons(self, row):
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save Maya file",
                          image=os.path.join(_path_imageFolder, 'new_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.uiPath_mayaSaveTo_sets())
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Export selected objects using Maya's Export Selection",
                          image=os.path.join(_path_imageFolder, 'export_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.ExportSelection_sets())
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save new version",
                          image=os.path.join(_path_imageFolder, 'new_version.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.SaveVersion())

    def _append_variation_dir_buttons(self, row):
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="New Variation",
                          image=os.path.join(_path_imageFolder, 'new_variation.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.CreateVariation())

    def _append_variation_file_buttons(self, row):
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save Maya file",
                          image=os.path.join(_path_imageFolder, 'new_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.uiPath_mayaSaveTo_variant())
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Export selected objects using Maya's Export Selection",
                          image=os.path.join(_path_imageFolder, 'export_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.ExportSelection(mode='variant'))
        mUI.MelIconButton(row,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save new version",
                          image=os.path.join(_path_imageFolder, 'new_version.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.SaveVersion())

    def _warn_subType_path_resolution(self, subType, msg, title='Subtype Directory Warning', assetPath=None):
        key = "{0}|{1}".format(subType, msg)
        if key in self._subTypePathWarningsShown:
            return
        self._subTypePathWarningsShown.add(key)
        if not self.showPathWarnings:
            log.debug(msg)
            return
        log.warning(msg)
        try:
            _buttons = ['OK']
            if assetPath:
                _buttons.append('Fix Now')
            _result = mc.confirmDialog(
                title=title,
                message=msg,
                button=_buttons,
                defaultButton='OK',
                cancelButton='OK',
                dismissString='OK')
            if _result == 'Fix Now' and assetPath:
                self._fix_subType_directory_discrepancy(assetPath, subType)
        except Exception as err:
            log.debug("Subtype warning dialog failed: {}".format(err))

    def _use_plural_subdirs(self):
        try:
            raw = self.mDat.d_project.get('usePluralSubDirs', False)
        except Exception:
            raw = False

        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ('true', '1', 'yes')
        return bool(raw)

    def _fix_subType_directory_discrepancy(self, assetPath, subType):
        """
        Resolve legacy/plural subtype directory discrepancies only under a single asset directory.
        """
        _str_func = '_fix_subType_directory_discrepancy'
        if not assetPath or not subType:
            return False

        _candidates = PU.subtype_dir_candidates(subType, prefer_plural=self._use_plural_subdirs())
        if len(_candidates) < 2:
            return False

        _preferred_name = _candidates[0]
        _legacy_names = _candidates[1:]
        _preferred_path = os.path.normpath(os.path.join(assetPath, _preferred_name))
        _legacy_paths = [os.path.normpath(os.path.join(assetPath, n)) for n in _legacy_names]
        _existing_legacy = [p for p in _legacy_paths if os.path.isdir(p)]
        _moved = []
        _skipped = []

        try:
            if not os.path.isdir(_preferred_path) and _existing_legacy:
                os.makedirs(_preferred_path)

            for _legacy_path in _existing_legacy:
                for _name in os.listdir(_legacy_path):
                    _src = os.path.normpath(os.path.join(_legacy_path, _name))
                    _dst = os.path.normpath(os.path.join(_preferred_path, _name))
                    if os.path.exists(_dst):
                        _skipped.append(_name)
                        continue
                    os.rename(_src, _dst)
                    _moved.append(_name)

                if not os.listdir(_legacy_path):
                    os.rmdir(_legacy_path)

            _msg = "Subtype directory fix complete for '{0}'.\nMoved: {1}\nSkipped (already exists): {2}".format(
                subType,
                len(_moved),
                len(_skipped))
            log.warning(log_msg(_str_func, _msg))
            mc.confirmDialog(title='Subtype Directory Fix', message=_msg, button=['OK'])
            return True
        except Exception as err:
            _msg = "Subtype directory fix failed for '{0}': {1}".format(subType, err)
            log.error(log_msg(_str_func, _msg))
            mc.confirmDialog(title='Subtype Directory Fix Failed', message=_msg, button=['OK'])
            return False

    def _resolve_subType_container_path(self, assetPath, subType):
        _str_func = '_resolve_subType_container_path'
        if not assetPath or not subType:
            return False

        _candidates = PU.subtype_dir_candidates(subType, prefer_plural=self._use_plural_subdirs())
        if not _candidates:
            return os.path.normpath(os.path.join(assetPath, subType))

        _paths = [os.path.normpath(os.path.join(assetPath, c)) for c in _candidates]
        _existing = [p for p in _paths if os.path.isdir(p)]
        _preferred = _paths[0]

        if len(_existing) > 1:
            if self._use_plural_subdirs():
                self._warn_subType_path_resolution(
                    subType,
                    "Both plural and legacy subtype directories found for '{0}'. Using: {1}".format(
                        subType, os.path.basename(_preferred)),
                    assetPath=assetPath,
                )
            return _preferred

        if len(_existing) == 1:
            _chosen = _existing[0]
            if _chosen != _preferred:
                if self._use_plural_subdirs():
                    self._warn_subType_path_resolution(
                        subType,
                        "Using legacy subtype directory for '{0}': {1}".format(
                            subType, os.path.basename(_chosen)),
                        assetPath=assetPath,
                    )
            return _chosen

        return _preferred

    def _refreshMetaDataFromSelection(self):
        """Refresh details panel metadata from the currently selected version file."""
        _version = self.versionFile
        if not _version or not os.path.isfile(_version):
            return False
        self.assetMetaData = self.getMetaDataFromFile()
        self.buildDetailsColumn()
        return True

    def _selectByValueIfPresent(self, scrollList, value):
        """Avoid Script Editor 'Item not found' warnings when restoring stale selections."""
        if not value:
            return False
        try:
            _items = list(getattr(scrollList, '_items', []) or [])
        except Exception:
            _items = []
        if value in _items:
            scrollList.selectByValue(value)
            return True
        return False

    def _resolveSubTypeLabelFromPathToken(self, token):
        """Map path folder tokens (plural/singular/case variants) to a subtype label in self.subTypes."""
        if not token:
            return None
        _t = token.lower()
        _candidates = []
        _candidates.extend(self.subTypes or [])
        _candidates.extend(self.l_subTypesBase or [])
        # preserve order, remove dupes
        _candidates = list(dict.fromkeys(_candidates))
        for _sub in _candidates:
            if _sub.lower() == _t:
                return _sub
            _cands = PU.subtype_dir_candidates(_sub, prefer_plural=self._use_plural_subdirs())
            if _t in [c.lower() for c in _cands]:
                return _sub
        return None

    def _canonicalize_set_token_for_filename(self, setName):
        """
        Prevent plural subtype directory tokens leaking into file basenames.
        If a set token includes subtype folder token forms (rig/rigs/templates/etc),
        force those token parts to canonical singular file token.
        """
        if not setName:
            return setName
        _canonical = PU.subtype_file_token(self.subType)
        if not _canonical:
            return setName

        _subCandidates = [c.lower() for c in PU.subtype_dir_candidates(self.subType, prefer_plural=self._use_plural_subdirs())]
        _subCandidates.append(_canonical.lower())
        _subCandidates = list(dict.fromkeys(_subCandidates))

        _parts = setName.split('_')
        _changed = False
        for i, p in enumerate(_parts):
            if p.lower() in _subCandidates:
                _parts[i] = _canonical
                _changed = True

        if _changed:
            return '_'.join(_parts)

        # Also handle whole-token cases with no underscores.
        if setName.lower() in _subCandidates:
            return _canonical

        return setName

    def _exportSubTypeDirName(self, subTypeToken=None):
        """Directory label for export paths honoring project plural-subdir policy."""
        _token = subTypeToken if subTypeToken else self.subType
        if not _token:
            return _token
        _subName = self._resolveSubTypeLabelFromPathToken(_token) or _token
        return PU.subtype_dir_preferred(_subName, prefer_plural=self._use_plural_subdirs())

    def _subtypeDisplayLabel(self):
        """UI display label for subtype actions should use canonical singular token."""
        if not self.subType:
            return "Subtype"
        _tok = PU.subtype_file_token(self.subType) or self.subType
        return _tok.capitalize()

    def LoadOptions(self, *args):
        self.showAllFiles    = bool(self.var_showAllFiles.getValue())
        self.categoryIndex   = int(self.var_categoryStore.getValue())
        self.subTypeIndex    = int(self.var_subTypeStore.getValue())
        #self.removeNamespace = bool(self.var_removeNamespace.getValue())
        #self.zeroRoot        = bool(self.var_zeroRoot.getValue())
        self.useMayaPy       = bool(self.var_useMayaPy.getValue())
        self.showDirectories = bool(self.var_showDirectories.getValue())
        self.showPathWarnings = bool(self.var_showPathWarnings.getValue())
        self.displayDetails  = bool(self.var_displayDetails.getValue())
        self.displayProject  = bool(self.var_displayProject.getValue())

        if self.cb_showAllFiles:
            self.cb_showAllFiles(e=True, checkBox = self.showAllFiles)
        if self.cb_showPathWarnings:
            self.cb_showPathWarnings(e=True, checkBox=self.showPathWarnings)
        #if self.cb_removeNamespace:
        #    self.cb_removeNamespace(e=True, checkBox = self.removeNamespace)
        #if self.cb_zeroRoot:
        #    self.cb_zeroRoot(e=True, checkBox = self.zeroRoot)

        self.SetSubType(self.subTypeIndex)
        self.buildMenu_subTypes()
        self.SetCategory(self.categoryIndex)
        #self.LoadPreviousSelection()
        self.uiFunc_showDirectories(self.showDirectories)	
        self.uiFunc_displayDetails(self.displayDetails)
        self.uiFunc_displayProject( self.displayProject )

        self.setTitle('|[ {} ]| --- {}'.format(self.mDat.d_project.get('name','No Name'),self.WINDOW_TITLE ))

    def SaveOptions(self, *args):
        log.info( "Saving options" )
        self.showAllFiles = self.cb_showAllFiles( q=True, checkBox=True ) if self.cb_showAllFiles else False
        #self.removeNamespace = self.cb_removeNamespace( q=True, checkBox=True ) if self.cb_removeNamespace else False
        #self.zeroRoot = self.cb_zeroRoot( q=True, checkBox=True ) if self.cb_zeroRoot else False

        self.useMayaPy = self.cb_useMayaPy( q=True, checkBox=True ) if self.cb_useMayaPy else False
        self.showDirectories = self.cb_showDirectories( q=True, checkBox=True ) if self.cb_showDirectories else False
        self.showPathWarnings = self.cb_showPathWarnings(q=True, checkBox=True) if self.cb_showPathWarnings else False

        self.var_showAllFiles.setValue(self.showAllFiles)
        #self.var_removeNamespace.setValue(self.removeNamespace)
        #self.var_zeroRoot.setValue(self.zeroRoot)
        self.var_useMayaPy.setValue(self.useMayaPy)
        self.var_showDirectories.setValue(self.showDirectories)
        self.var_showPathWarnings.setValue(self.showPathWarnings)
        self.var_displayDetails.setValue(self.displayDetails)
        self.var_displayProject.setValue(self.displayProject)

        # self.optionVarExportDirStore.setValue( self.exportDirectory )
        self.var_categoryStore.setValue( self.categoryIndex )
        self.var_subTypeStore.setValue( self.subTypeIndex )

        self.uiFunc_showDirectories(self.showDirectories)
        self.uiFunc_displayDetails(self.displayDetails)
        self.uiFunc_displayProject(self.displayProject)

    def UpdateToLatestRig(self, *args):
        for obj in mc.ls(sl=True):
            myAsset = ASSET.Asset(obj)
            myAsset.UpdateToLatest()

    def SetExportSets(self, *args):
        mc.window( width=150 )
        col = mc.columnLayout( adjustableColumn=True )
        #mc.button( label='Set Bake Set', command=self.SetBakeSet )
        cgmUI.add_Button(col,'Set Bake Set', lambda *a: self.SetBakeSet())

        #mc.button( label='Set Delete Set', command=self.SetDeleteSet )
        cgmUI.add_Button(col,'Set Delete Set', lambda *a: self.SetDeleteSet())

        # mc.button( label='Set Export Set', command=self.SetExportSet )
        cgmUI.add_Button(col,'Set Export Set', lambda *a: self.SetExportSet())

        mc.showWindow()

    def ResetExportSets(self, *args):
        for n in 'bake','delete','export':
            mc.optionVar(sv=('cgm_{0}_set'.format(n), '{0}_tdSet'.format(n)))
        self.QueryExportSets()

    def QueryExportSets(self, *args):
        for n in 'bake','delete','export':
            print((mc.optionVar(q='cgm_{0}_set'.format(n))))

    def SetDeleteSet(self, *args):
        sel = mc.ls(sl=True)
        deleteSet = sel[0].split(':')[-1]
        log.info( "Setting delete set to: %s" % deleteSet )
        self.var_deleteSet.setValue(deleteSet)

    def SetBakeSet(self, *args):
        sel = mc.ls(sl=True)
        bakeSet = sel[0].split(':')[-1]
        log.info( "Setting bake set to: %s" % bakeSet )
        self.var_bakeSet.setValue(bakeSet)

    def SetExportSet(self, *args):
        sel = mc.ls(sl=True)
        exportSet = sel[0].split(':')[-1]
        log.info( "Setting geo set to: %s" % exportSet )
        self.var_exportSet.setValue(exportSet)

    def uiFunc_contentDir_loadSelect(self):
        try:_dat = self.mContentListDat
        except:
            log.warning("No self.mContentListDat")
            return


        if self.mDat:#Adding the ability to load to Scene
            select_idx = self.uiScrollList_dirContent.getSelectedIdxs(False)

            for i,d in enumerate(self.mDat.assetDat):
                k = d.get('n')
                if k in _dat['split']:
                    idx_split = _dat['split'].index(k)
                    l_temp = _dat['split'][idx_split:]
                    print(('Found: {0} | {1}'.format(k,l_temp)))

                    numItemsFound = len(l_temp)   

                    if numItemsFound > 0:
                        if l_temp[0] in self.categoryList:
                            idx = self.categoryList.index(l_temp[0])
                            self.SetCategory(idx)
                        else:
                            log.warning('{0} not found in category list'.format(l_temp[0]) )
                            return

                    if numItemsFound > 1:
                        self.assetList['scrollList'].clearSelection()
                        self.assetList['scrollList'].selectByValue(l_temp[1])

                    if numItemsFound > 2:
                        _subName = self._resolveSubTypeLabelFromPathToken(l_temp[2])
                        if _subName in self.subTypes:
                            self.SetSubType(self.subTypes.index(_subName))
                        else:
                            log.warning('{0} not found in subType list'.format(l_temp[2]) )
                            return

                    if numItemsFound > 3:
                        self.subTypeSearchList['scrollList'].clearSelection()
                        self.subTypeSearchList['scrollList'].selectByValue(l_temp[3])
                        self.LoadVariationList()

                    if numItemsFound > 4:                  
                        if self.hasVariant:
                            self.variationList['scrollList'].clearSelection()
                            self.variationList['scrollList'].selectByValue(l_temp[4])
                            self.LoadVersionList()
                            if numItemsFound > 5:   
                                self.versionList['scrollList'].selectByValue(l_temp[5])
                        else:
                            self.versionList['scrollList'].selectByValue(l_temp[4])

                    #if self.mScene:
                    #self.var_categoryStore.value = i
                    #self.LoadOptions()

                    #if select_idx:
                        #self.uiScrollList_dirContent.selectByIdx(select_idx[0])
                    #return


    def uiFunc_reloadContentBrowser(self):
        self.uiScrollList_dirContent.rebuild( self.directory)

    def uiFunc_reloadExportBrowser(self):
        self.uiScrollList_dirExport.rebuild( self.exportDirectory)

    def uiFunc_exportFindSelected(self):
        _category = self.category        
        _asset = self.selectedAsset
        _subType = self.subType

        k_use = None
        for k,d in list(self.uiScrollList_dirExport._d_dir.items()):
            #print((d['split']))
            if d['split'][-3:] == [_category,_asset, _subType]:
                k_use = d['uiString']
                break
            if d['split'][-2:] == [_category,_asset]:
                k_use = d['uiString']
                break
            if d['split'][-1] == [_category]:
                k_use = d['uiString']
                break
        if k_use:
            self.uiScrollList_dirExport.selectByValue(k_use,True)


    def build_layoutWrapper(self,parent):

        _ParentForm = mUI.MelFormLayout(self,ut='cgmUISubTemplate')

        _headerColumn = mUI.MelColumnLayout(_ParentForm,useTemplate = 'cgmUISubTemplate')

        _imageFailPath = os.path.join(mImagesPath.asFriendly(),'cgm_project.png')
        imageRow = mUI.MelHRowLayout(_headerColumn,bgc=self.v_bgc)

        #mUI.MelSpacer(imageRow,w=10)
        self.uiImage_ProjectRow = imageRow
        self.uiImage_Project= mUI.MelImage(imageRow,w=1000, h=75)#350
        self.uiImage_Project.setImage(_imageFailPath)
        self.uiImageRow_project = imageRow
        #mUI.MelSpacer(imageRow,w=10)	
        imageRow.layout()

        self._detailsColumn = mUI.MelScrollLayout(_ParentForm,useTemplate = 'cgmUISubTemplate', w=294)
        self._projectForm = mUI.MelTabLayout( _ParentForm, w=400, ut='cgmUITemplate')#w180 mUI.MelFormLayout(_ParentForm,useTemplate = 'cgmUISubTemplate', w=250)

        _MainForm = mUI.MelFormLayout(_ParentForm,ut='cgmUITemplate')

        ##############################
        # Top Column Layout 
        ##############################

        self._detailsToggleBtn = mUI.MelButton(_MainForm, ut = 'cgmUITemplate', label="<", w=15, bgc=(1.0, .445, .08), c = lambda *a:mc.evalDeferred(self.uiFunc_toggleDisplayInfo,lp=True))	

        self._projectToggleBtn = mUI.MelButton(_MainForm,
                                               ut = 'cgmUITemplate',
                                               label=">", w=15, bgc=(1.0, .445, .08), c = lambda *a:mc.evalDeferred(self.uiFunc_toggleProjectColumn,lp=True))	

        _directoryColumn = mUI.MelColumnLayout(_MainForm,useTemplate = 'cgmUISubTemplate')

        self._uiRow_dir = mUI.MelHSingleStretchLayout(_directoryColumn)

        mUI.MelLabel(self._uiRow_dir,l='Content', w=100)
        self.directoryTF = mUI.MelTextField(self._uiRow_dir, editable = False, bgc=(.8,.8,.8))
        self.directoryTF.setValue( self.directory )

        #mUI.MelButton(self._uiRow_dir,l='Explorer', ut = 'cgmUITemplate',
        #              c=lambda *a:self.OpenDirectory(self.directory))

        mUI.MelIconButton(parent=self._uiRow_dir,
                          ut = 'cgmUITemplate',
                          style='iconOnly',
                          w=25,
                          h=25,
                          image= os.path.join(_path_imageFolder,'explorer_25.png'),
                          bgc = cgmUI.guiButtonColor,                                            
                          c=lambda *a:self.OpenDirectory(self.directory))


        mUI.MelSpacer(self._uiRow_dir,w=2)

        self._uiRow_dir.setStretchWidget(self.directoryTF)
        self._uiRow_dir.layout()

        self._uiRow_export = mUI.MelHSingleStretchLayout(_directoryColumn)

        mUI.MelLabel(self._uiRow_export,l='Export Dir', w=100)
        self.exportDirectoryTF = mUI.MelTextField(self._uiRow_export, editable = False, bgc=(.8,.8,.8))
        self.exportDirectoryTF.setValue( self.exportDirectory )

        """
        mUI.MelButton(self._uiRow_export,l='Explorer', ut = 'cgmUITemplate',
                      c=lambda *a:self.OpenDirectory(self.exportDirectory))"""      

        mUI.MelIconButton(parent=self._uiRow_export,
                          ut = 'cgmUITemplate',
                          w=25,
                          h=25,
                          style='iconOnly',
                          image= os.path.join(_path_imageFolder,'explorer_25.png'),
                          bgc = cgmUI.guiButtonColor,
                          c=lambda *a:self.OpenDirectory(self.exportDirectory))


        mUI.MelSpacer(self._uiRow_export,w=2)                      

        self._uiRow_export.setStretchWidget(self.exportDirectoryTF)

        self._uiRow_export.layout()

        self._uiRow_export(e=True, vis=self.showDirectories)
        self._uiRow_dir(e=True, vis=self.showDirectories)


        #======================================
        # Projects Column
        ui_tabs = self._projectForm
        #ui_tabs = mUI.MelTabLayout( self._projectForm )#w180

        uiTab_Project = mUI.MelScrollLayout(ui_tabs,ut='cgmUITemplate')#mUI.MelColumnLayout(ui_tabs)
        uiTab_Content = mUI.MelFormLayout(ui_tabs,ut='cgmUITemplate')#mUI.MelColumnLayout(ui_tabs)
        self.uiTab_Content = uiTab_Content
        uiTab_Export = mUI.MelFormLayout(ui_tabs,ut='cgmUITemplate')#mUI.MelScrollLayout( ui_tabs,ut='cgmUITemplate' )


        for i,tab in enumerate(['Project','Content','Export']):
            ui_tabs.setLabel(i,tab)

        #self.buildTab_setup(uiTab_setup)
        #self.buildTab_utilities(uiTab_utils)


        #Project Setup ========================================================================================
        #iColumn_project = mUI.MelScrollLayout(parent=uiTab_Project)
        self.ui_projectDirty = mUI.MelButton(uiTab_Project, label = 'Changes detected. Save?', vis = False, height = 15, bgc = PROJECT._colorBad,
                                             command = cgmGEN.Callback(self.uiProject_saveAndRefresh))

        PROJECT.buildFrame_baseDat(self, uiTab_Project, changeCommand=cgmGEN.Callback(self.uiFunc_projectDirtyState,True))

        PROJECT.buildFrame_assetTypes(self,uiTab_Project,changeCommand=cgmGEN.Callback(self.uiFunc_projectDirtyState,True))

        PROJECT.buildFrame_paths(self,uiTab_Project,changeCommand=cgmGEN.Callback(self.uiFunc_projectDirtyState,True))
        PROJECT.buildFrames(self,uiTab_Project,changeCommand=cgmGEN.Callback(self.uiFunc_projectDirtyState,True))





        #Content ========================================================================================================
        _projectColumnTop = mUI.MelColumn(uiTab_Content)


        #_inside = _projectColumnTop

        mUI.MelSeparator(_projectColumnTop,ut='cgmUISubTemplate',h=3)

        _textField = mUI.MelTextField(_projectColumnTop,
                                      ann='Filter',
                                      #w=50,
                                      bgc = [.3,.3,.3],
                                      en=True,
                                      text = '')    


        #Scroll list
        mScrollList = Project.cgmProjectDirList(uiTab_Content, ut='cgmUISubTemplate',
                                                allowMultiSelection=0, en=True,
                                                ebg=0,
                                                bgc = [.2,.2,.2],
                                                #w = 50,
                                                dcc = cgmGEN.Callback(self.uiFunc_contentDir_loadSelect))



        try:mScrollList(edit=True,hlc = [.5,.5,.5])
        except:pass

        mScrollList.set_filterObj(_textField)
        _textField(edit=True,
                   tcc = lambda *a: mScrollList.update_display())    

        #mScrollList.set_selCallBack(mrsPoseDirSelect,mScrollList,self)

        self.uiScrollList_dirContent = mScrollList        
        mScrollList.mScene = self


        _refresh = mUI.MelButton(uiTab_Content,l='Refresh', h=15, ut = 'cgmUITemplate',
                                 c=lambda *a:self.uiFunc_reloadContentBrowser())        


        uiTab_Content( edit=True, 
                       attachForm=[
                           (_projectColumnTop, 'top', 0), 
                           (_projectColumnTop, 'left', 0), 
                           (_projectColumnTop, 'right', 0),
                           (mScrollList, 'left', 0), 
                           (mScrollList, 'right', 0),
                           (_refresh, 'left', 0), 
                           (_refresh, 'right', 0),                           
                           (_refresh, 'bottom', 0)], 
                       attachControl=[
                           (mScrollList, 'top', 0, _projectColumnTop),
                           (mScrollList, 'bottom', 0, _refresh)] )

        #Export ========================================================================================================
        _projectColumnTop = mUI.MelColumn(uiTab_Export)


        #_inside = _projectColumnTop

        mUI.MelSeparator(_projectColumnTop,ut='cgmUISubTemplate',h=3)

        _textField = mUI.MelTextField(_projectColumnTop,
                                      ann='Filter',
                                          #w=50,
                                          bgc = [.3,.3,.3],
                                          en=True,
                                          text = '')    


        #Scroll list
        mScrollList2 = Project.cgmProjectDirList(uiTab_Export, ut='cgmUISubTemplate',
                                                 allowMultiSelection=0, en=True,
                                                ebg=0,
                                                bgc = [.2,.2,.2],)
                                                #w = 50)



        try:mScrollList2(edit=True,hlc = [.5,.5,.5])
        except:pass

        mScrollList2.set_filterObj(_textField)
        _textField(edit=True,
                   tcc = lambda *a: mScrollList2.update_display())    

        #mScrollList.set_selCallBack(mrsPoseDirSelect,mScrollList,self)

        self.uiScrollList_dirExport = mScrollList2        
        mScrollList2.mScene = self

        _findSelected = mUI.MelButton(uiTab_Export,l='Find Selected', h=25, ut = 'cgmUITemplate',
                                      c=lambda *a:self.uiFunc_exportFindSelected())        

        _refresh = mUI.MelButton(uiTab_Export,l='Refresh', h=25, ut = 'cgmUITemplate',
                                 c=lambda *a:self.uiFunc_reloadExportBrowser())        


        uiTab_Export( edit=True, 
                      attachForm=[
                               (_projectColumnTop, 'top', 0), 
                               (_projectColumnTop, 'left', 0), 
                               (_projectColumnTop, 'right', 0),
                               (mScrollList2, 'left', 0), 
                               (mScrollList2, 'right', 0),
                               (_findSelected, 'left', 0), 
                               (_findSelected, 'right', 0),                                
                               (_refresh, 'left', 0), 
                               (_refresh, 'right', 0),                           
                               (_refresh, 'bottom', 0)], 
                           attachControl=[
                               (mScrollList2, 'top', 0, _projectColumnTop),
                               (_findSelected, 'bottom', 0, _refresh),
                               (mScrollList2, 'bottom', 0, _findSelected)] )        

        #--------------------------------------

        ##############################
        # Main Asset Lists 
        ##############################
        self._assetsForm = mUI.MelFormLayout(_MainForm,ut='cgmUISubTemplate', numberOfDivisions=100) #mc.columnLayout(adjustableColumn=True)

        # Category
        _catForm = mUI.MelFormLayout(self._assetsForm,ut='cgmUISubTemplate')
        self.categoryBtn = mUI.MelButton(_catForm,
                                         label=self.category,ut='cgmUITemplate',
                                         ann='Select the asset category')

        self.categoryMenu = mUI.MelPopupMenu(self.categoryBtn, button=1 )
        # for i,category in enumerate(self.categoryList):
        # 	self.categoryMenuItemList.append( mUI.MelMenuItem(self.categoryMenu, label=category, c=partial(self.SetCategory,i)) )
        # 	if i == self.categoryIndex:
        # 		self.categoryMenuItemList[i]( e=True, enable=False)

        self.assetList = self.build_searchable_list(_catForm, sc=self.uiFunc_assetList_select)
        self.assetTSLpum = mUI.MelPopupMenu(self.assetList['scrollList'], pmc=self.UpdateAssetTSLPopup)

        mRow_asset = mUI.MelHLayout(_catForm,padding = 2)
        self.assetButton = mUI.MelButton(mRow_asset, ut='cgmUITemplate', label="New Asset", command=self.CreateAsset)
        #self.addSubTypeButton = mUI.MelButton(mRow_asset, ut='cgmUITemplate', label="Add SubType", command=self.CreateSubType)
        mRow_asset.layout()

        _catForm( edit=True, 
                  attachForm=[
                              (self.categoryBtn, 'top', 0), 
                              (self.categoryBtn, 'left', 0), 
                              (self.categoryBtn, 'right', 0), 
                                      (self.assetList['formLayout'], 'left', 0),
                                    (self.assetList['formLayout'], 'right', 0),
                                        (mRow_asset, 'bottom', 0), 
                                        (mRow_asset, 'right', 0), 
                                        (mRow_asset, 'left', 0)], 
                          attachControl=[
                              (self.assetList['formLayout'], 'top', 0, self.categoryBtn),
                              (self.assetList['formLayout'], 'bottom', 0, mRow_asset)] )


        # Sets ======================================================================================
        _setsForm = mUI.MelFormLayout(self._assetsForm,ut='cgmUISubTemplate')
        self.subTypeBtn = mUI.MelButton( _setsForm,
                                         label=self.subType,ut='cgmUITemplate',
                                         ann='Select the sub type', en=True )

        self.subTypeMenu = mUI.MelPopupMenu(self.subTypeBtn, button=1 )
        self.subTypeSearchList = self.build_searchable_list(_setsForm, sc=self.uiFunc_subTypeList_select,
                                                            refreshCommand=self._refreshSubTypeList,
                                                            allowMultiSelect=True)

        # File-list popup rebuilt on selection (Builder pattern); reduced menu when multi-select
        self._wireFileListScrollSelect(
            self.subTypeSearchList,
            'subTypeListPUM',
            self.buildSubTypeListPopup,
            self.uiFunc_subTypeList_select,
            list_key='sets',
            sendToProjectAttr='uiPop_sendToProject_sub')


        """
        mRow_sets = mUI.MelHLayout(_setsForm)
        self.subTypeButton = mUI.MelButton(mRow_sets, ut='cgmUITemplate', label="New Subtype", command=self.CreateSubAsset)
        mRow_sets.layout()"""

        mRow_sets = mUI.MelHLayout(_setsForm,padding = 2)
        self.subTypeButton = mUI.MelButton(mRow_sets, ut='cgmUITemplate', label="Save Version", command=self.SaveVersion)
        #self.addSetButton = mUI.MelButton(mRow_sets, ut='cgmUITemplate', label="Add Set", command=self.CreateSubAsset)
        mRow_sets.layout()        
        self.mRow_setButtons = mRow_sets

        _setsForm( edit=True, 
                   attachForm=[
                               (self.subTypeBtn, 'top', 0), 
                               (self.subTypeBtn, 'left', 0), 
                               (self.subTypeBtn, 'right', 0), 
                                       (self.subTypeSearchList['formLayout'], 'left', 0),
                                    (self.subTypeSearchList['formLayout'], 'right', 0),
                                        (mRow_sets, 'bottom', 0), 
                                        (mRow_sets, 'right', 0),
                                        (mRow_sets, 'left', 0)], 
                           attachControl=[
                               (self.subTypeSearchList['formLayout'], 'top', 0, self.subTypeBtn),
                               (self.subTypeSearchList['formLayout'], 'bottom', 0, mRow_sets)] )

        # Variation ======================================================================================
        _variationForm = mUI.MelFormLayout(self._assetsForm,ut='cgmUISubTemplate')
        _variationBtn = mUI.MelButton(_variationForm,
                                      label='Variation',ut='cgmUITemplate',
                                              ann='Select the asset variation', en=False)

        self.variationList = self.build_searchable_list(_variationForm, sc=self.uiFunc_variationList_select,
                                                        refreshCommand=self._refreshVariationList,
                                                        allowMultiSelect=True)



        self._wireFileListScrollSelect(
            self.variationList,
            'variationListPUM',
            self.buildVariationListPopup,
            self.uiFunc_variationList_select,
            list_key='variation',
            sendToProjectAttr='uiPop_sendToProject_variant')
        #---------------------------------------------------------------------------------------

        mRow_variationButtons = mUI.MelHLayout(_variationForm, padding=2)
        self.mRow_variationButtons = mRow_variationButtons
        mRow_variationButtons.layout()

        _variationForm( edit=True, 
                        attachForm=[
                                    (_variationBtn, 'top', 0), 
                                    (_variationBtn, 'left', 0), 
                                    (_variationBtn, 'right', 0), 
                                            (self.variationList['formLayout'], 'left', 0),
                                    (self.variationList['formLayout'], 'right', 0),
                                        (mRow_variationButtons, 'bottom', 0), 
                                        (mRow_variationButtons, 'right', 0), 
                                        (mRow_variationButtons, 'left', 0)], 
                                attachControl=[
                                    (self.variationList['formLayout'], 'top', 0, _variationBtn),
                                    (self.variationList['formLayout'], 'bottom', 0, mRow_variationButtons)] )


        # Version ======================================================================================
        _versionForm = mUI.MelFormLayout(self._assetsForm,ut='cgmUISubTemplate')
        _versionBtn = mUI.MelButton(_versionForm,
                                    label='Version',ut='cgmUITemplate',
                                            ann='Select the asset version', en=False)

        self.versionList = self.build_searchable_list(_versionForm, sc=self.uiFunc_versionList_select,
                                                      refreshCommand=self._refreshVersionList,
                                                      allowMultiSelect=True)


        self._wireFileListScrollSelect(
            self.versionList,
            'versionListPUM',
            self.buildVersionListPopup,
            self.uiFunc_versionList_select,
            list_key='version',
            sendToProjectAttr='uiPop_sendToProject_version')

        mRow_versionButtons = mUI.MelHLayout(_versionForm, padding=2)
        self.mRow_versionButtons = mRow_versionButtons
        mUI.MelIconButton(mRow_versionButtons,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save Maya file",
                          image=os.path.join(_path_imageFolder, 'new_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.uiPath_mayaSaveTo_version())
        mUI.MelIconButton(mRow_versionButtons,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Export selected objects using Maya's Export Selection",
                          image=os.path.join(_path_imageFolder, 'export_file.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.ExportSelection(mode='version'))
        mUI.MelIconButton(mRow_versionButtons,
                          ut='cgmUITemplate',
                          style='iconOnly',
                          l='',
                          ann="Save new version",
                          image=os.path.join(_path_imageFolder, 'new_version.png'),
                          w=25, h=25,
                          bgc=cgmUI.guiButtonColor,
                          c=lambda *a: self.SaveVersion())
        mRow_versionButtons.layout()

        _versionForm( edit=True, 
                      attachForm=[
                          (_versionBtn, 'top', 0), 
                          (_versionBtn, 'left', 0), 
                          (_versionBtn, 'right', 0), 
                                  (self.versionList['formLayout'], 'left', 0),
                            (self.versionList['formLayout'], 'right', 0),
                                (mRow_versionButtons, 'bottom', 0), 
                                (mRow_versionButtons, 'right', 0), 
                                (mRow_versionButtons, 'left', 0)], 
                      attachControl=[
                          (self.versionList['formLayout'], 'top', 0, _versionBtn),
                          (self.versionList['formLayout'], 'bottom', 0, mRow_versionButtons)] )


        self._subForms = [_catForm,_setsForm,_variationForm,_versionForm]

        self.buildAssetForm()


        ##############################
        # Bottom 
        ##############################
        def create_exportButton(parent,ann,image,c=None,w=30,h=30):
            return mUI.MelIconButton(parent,
                                     ann = ann,
                                     #bgc = cgmUI.guiButtonColor,
                                     image=image,
                                     w=w,
                                     h=h,
                                     c=c)


        _bottomColumn    = mUI.MelColumnLayout(_MainForm,useTemplate = 'cgmUISubTemplate', adjustableColumn=True)#mc.columnLayout(adjustableColumn = True)

        mc.setParent(_bottomColumn)
        cgmUI.add_LineSubBreak()

        _row = mUI.MelHSingleStretchLayout(_bottomColumn,ut='cgmUISubTemplate',h=40)#padding = 5)

        mUI.MelSpacer(_row,w=10)


        create_exportButton(_row,'Create a new scene with project settings', os.path.join(_path_imageFolder,'new_file.png'), partial(SCENEUTILS.uiFunc_newProjectScene,self))
        mUI.MelLabel(_row, label="  |  ", h=self.__itemHeight, align = 'center')
        create_exportButton(_row,'Select Open File', os.path.join(_path_imageFolder,'find_file.png'), partial(self.uiFunc_selectOpenFile))




        mUI.MelLabel(_row, label="Export: ", h=self.__itemHeight, align = 'right')

        #self.exportButton = mUI.MelButton(_row, label="Static", ut = 'cgmUITemplate', c=partial(self.RunExportCommand,4), h=self.__itemHeight)


        """
        self.exportButton = mUI.MelIconButton(_row,
                                              ann = 'Static...',
                                              bgc = cgmUI.guiButtonColor,
                                              image=os.path.join(_path_imageFolder,'export.png') ,
                                              h=40,
                                              #marginWidth = 10,
                                              c=partial(self.RunExportCommand,4))"""

        create_exportButton(_row,'Static...',os.path.join(_path_imageFolder,'export.png'), partial(self.RunExportCommand,4))        
        create_exportButton(_row,'Bake',os.path.join(_path_imageFolder,'bake.png'), partial(self.RunExportCommand,0))

        self.exportButton = create_exportButton(_row,'Anim',os.path.join(_path_imageFolder,'anim_2.png'), partial(self.RunExportCommand,1))        

        #self.exportButton = mUI.MelButton(_row, label="Anim", ut = 'cgmUITemplate', c=partial(self.RunExportCommand,1), h=self.__itemHeight)

        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Bake", c=partial(self.RunExportCommand,0), h=self.__itemHeight)
        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Rig", c=partial(self.RunExportCommand,3), h=self.__itemHeight)
        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Cutscene", c=partial(self.RunExportCommand,2), h=self.__itemHeight)

        create_exportButton(_row,'Cutscene',os.path.join(_path_imageFolder,'scene.png'), partial(self.RunExportCommand,2))        
        mUI.MelSeparator(_row,w=5)        
        create_exportButton(_row,'Rig',os.path.join(_path_imageFolder,'rig_export.png'), partial(self.RunExportCommand,3))

        mUI.MelLabel(_row, label="       | ", h=self.__itemHeight, align = 'center')

        mUI.MelLabel(_row, label="Add to queue as: ", h=self.__itemHeight, align = 'right')

        create_exportButton(_row,'Anim', os.path.join(_path_imageFolder,'anim_2.png'), lambda *a:(self.AddSelectedToExportQueue('export')))
        create_exportButton(_row,'Cutscene', os.path.join(_path_imageFolder,'scene.png'),  lambda *a:(self.AddSelectedToExportQueue('cutscene')))
        mUI.MelSeparator(_row,w=5)
        create_exportButton(_row,'Rig', os.path.join(_path_imageFolder,'rig_export.png'), lambda *a:(self.AddSelectedToExportQueue('rig')))

        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Rig",  c=lambda *a:(self.AddToExportQueue('rig')), h=self.__itemHeight)
        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Cutscene",  c=lambda *a:(self.AddToExportQueue('cutscene')), h=self.__itemHeight)

        #_row.setStretchWidget(_split)

        #mUI.MelSpacer(_row,w=0)
        mUI.MelLabel(_row, label="       | ", h=self.__itemHeight, align = 'center')

        self.loadBtn = mUI.MelButton(_row, ut = 'cgmUITemplate', label="Load File", c=self.LoadFile, h=self.__itemHeight)        
        _row.setStretchWidget(self.loadBtn)

        mUI.MelSpacer(_row,w=10)

        _row.layout()

        """
        mc.setParent(_bottomColumn)
        cgmUI.add_LineSubBreak()

        #_row = mUI.MelHSingleStretchLayout(_bottomColumn,ut='cgmUISubTemplate',padding = 5)
        _row = mUI.MelHSingleStretchLayout(_bottomColumn,useTemplate = 'cgmUISubTemplate') 
        #mUI.MelSpacer(_row,w=5)

        create_exportButton(_row,'Create a new scene with project settings', os.path.join(_path_imageFolder,'new_file.png'), partial(SCENEUTILS.uiFunc_newProjectScene,self))
        create_exportButton(_row,'Select Open File', os.path.join(_path_imageFolder,'find_file.png'), partial(self.uiFunc_selectOpenFile))

        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Create New Scene", c= partial(SCENEUTILS.uiFunc_newProjectScene,self), h=self.__itemHeight, w= 200,
                      #ann="Create a new scene with project settings")
        #mUI.MelButton(_row, ut = 'cgmUITemplate', label="Select Open File", c= partial(self.uiFunc_selectOpenFile), h=self.__itemHeight, w= 200)
        self.loadBtn = mUI.MelButton(_row, ut = 'cgmUITemplate', label="Load File", c=self.LoadFile, h=self.__itemHeight)
        _row.setStretchWidget(self.loadBtn)

        #_row.setStretchWidget( self.loadBtn )

        #mUI.MelSpacer(_row,w=5)

        _row.layout()
        """

        mc.setParent(_bottomColumn)
        cgmUI.add_LineSubBreak()

        self.exportQueueFrame = mUI.MelFrameLayout(_bottomColumn, label="Export Queue", collapsable=True, collapse=True)
        _rcl = mUI.MelFormLayout(self.exportQueueFrame,ut='cgmUITemplate')

        self.queueTSL = cgmUI.cgmScrollList(_rcl)
        self.queueTSL.allowMultiSelect(True)
        self.queueTSL(e=True, dcc=cgmGEN.Callback(self.ExportQueue_selectEntryInUI))

        _col = mUI.MelColumnLayout(_rcl,width=200,adjustableColumn=True,useTemplate = 'cgmUISubTemplate',rowSpacing=0)#mc.columnLayout(width=200,adjustableColumn=True)

        _row = mUI.MelHSingleStretchLayout(_col, ut='cgmUISubTemplate', padding=5, h=40)
        mUI.MelSpacer(_row, w=10)
        create_exportButton(_row, 'Save', os.path.join(_path_imageFolder, 'file_save.png'), partial(self.ExportQueue_write))
        create_exportButton(_row, 'Load', os.path.join(_path_imageFolder, 'file_open.png'), partial(self.ExportQueue_load))
        create_exportButton(_row, 'Update', os.path.join(_path_imageFolder, 'refresh.png'), partial(self.ExportQueue_update))
        create_exportButton(_row, 'Report', os.path.join(_path_imageFolder, 'report.png'), partial(self.ExportQueue_report))
        create_exportButton(_row, 'Sort', os.path.join(_path_imageFolder, 'sortBy_name.png'), partial(self.ExportQueue_sort))
        _spacer = mUI.MelSpacer(_row, w=0)
        _row.setStretchWidget(_spacer)
        _row.layout()

        mc.setParent(_col)
        cgmUI.add_LineSubBreak()
        mUI.MelButton(_col, label="Remove", ut='cgmUITemplate', command=partial(self.RemoveFromQueue, 0))
        cgmUI.add_LineSubBreak()
        mUI.MelButton(_col, label="Remove All", ut = 'cgmUITemplate', command=partial(self.RemoveFromQueue, 1))
        cgmUI.add_LineSubBreak()
        mUI.MelButton(_col, label="Batch Export", ut = 'cgmUITemplate', command=partial(self.batch_buildFile))
        cgmUI.add_LineSubBreak()

        _options_fl = mUI.MelFrameLayout(_col, label="Options", collapsable=True)

        _c2 = mUI.MelColumnLayout(_options_fl, adjustableColumn=True)
        self.updateCB = mUI.MelCheckBox(_c2, label="Update and Save Increment", v=False)
        self.updateRigsCB = mUI.MelCheckBox(_c2, label="Update and Save", v=self.var_updateRigs.getValue(), cc=cgmGEN.Callback(self.var_updateRigs.toggle))

        _rcl( edit=True, 
              attachForm=[
                          (self.queueTSL, 'top', 0), 
                          (self.queueTSL, 'left', 0), 
                          (self.queueTSL, 'bottom', 0), 
                                  (_col, 'bottom', 0), 
                                    (_col, 'top', 0), 
                                        (_col, 'right', 0)], 
                      attachControl=[
                          (self.queueTSL, 'right', 0, _col)] )

        ##############################
        # Layout form
        ##############################

        _footer = cgmUI.add_cgmFooter(_ParentForm)            

        _MainForm( edit=True, 
                   attachForm=[
                               (_directoryColumn, 'top', 0), 
                               #(_directoryColumn, 'left', 0), 
                                        (_bottomColumn, 'left', 0),
                                        (_bottomColumn, 'bottom', 0),
                                        (self._assetsForm, 'left', 0),


                                                                (self._projectToggleBtn, 'top', 0),
                                        (self._projectToggleBtn, 'bottom', 0),
                                        (self._projectToggleBtn, 'left', 0),

                                        (self._detailsToggleBtn, 'right', 0),
                                        (self._detailsToggleBtn, 'top', 0),
                                        (self._detailsToggleBtn, 'bottom', 0)], 
                           attachControl=[
                               (self._assetsForm, 'top', 0, _directoryColumn),
                               (self._assetsForm, 'bottom', 0, _bottomColumn),

                                        (self._assetsForm, 'left', 0, self._projectToggleBtn),
                                        (_bottomColumn, 'left', 0, self._projectToggleBtn),
                                        (_directoryColumn, 'left', 0, self._projectToggleBtn),                                        
                                        (self._assetsForm, 'right', 0, self._detailsToggleBtn),
                                        (_bottomColumn, 'right', 0, self._detailsToggleBtn),
                                         (_directoryColumn, 'right', 0, self._detailsToggleBtn)])

        _ParentForm( edit=True,
                     attachForm=[						 
                                 (_headerColumn, 'left', 0),
                                        (_headerColumn, 'right', 0),
                                        (_headerColumn, 'top', 0),
                                        (self._detailsColumn, 'right', 0),
                                        (self._projectForm, 'left', 0),                                        
                                        #(_MainForm, 'left', 0),
                                         (_footer, 'left', 0),
                                        (_footer, 'right', 0),
                                          (_footer, 'bottom', 0)],
                             attachControl=[(_MainForm, 'top', 0, _headerColumn),
                                                        (_MainForm, 'bottom', 0, _footer),
                                                        (_MainForm, 'left', 0, self._projectForm),
                                                        (_MainForm, 'right', 0, self._detailsColumn),
                                                         (self._projectForm, 'top', 0, _headerColumn),
                                                         (self._projectForm, 'bottom', 1, _footer),
                                                          (self._detailsColumn, 'top', 0, _headerColumn),
                                                         (self._detailsColumn, 'bottom', 1, _footer)])
    def show( self ):		
        self.setVisibility( True )
        self.buildMenu_options()
        self.buildDetailsColumn()


    #=========================================================================
    # Menu Building
    #=========================================================================
    def buildAssetForm(self):
        _str_func = 'buildAssetForm'
        log.debug("|{0}| >>...".format(_str_func))

        #pprint.pprint(self.subTypes)
        if not self.subTypes:
            log.debug(log_msg(_str_func,"no subtypes..."))

            mc.formLayout( self._subForms[1], e=True, vis=False )            
            mc.formLayout( self._subForms[3], e=True, vis=True )

        else:
            log.debug(log_msg(_str_func,"subtypes..."))            
            mc.formLayout( self._subForms[2], e=True, vis=self.hasVariant and self.hasSub )
            mc.formLayout( self._subForms[1], e=True, vis=True )            

            _hasSub = self.hasSub
            log.debug(log_msg(_str_func,"hasSub: {}".format(_hasSub)))

            if not self.subTypeSearchList['scrollList'].getSelectedItem():
                log.debug(log_msg(_str_func,"no subTypeSearchList selected"))
                mc.formLayout( self._subForms[3], e=True, vis=False)

            else:
                log.debug(log_msg(_str_func,"subTypeSearchList selected"))
                mc.formLayout( self._subForms[3], e=True, vis=self._version_column_should_show())

                if not self.hasSubTypes:
                    log.debug(log_msg(_str_func,"no subtypes 2..."))

                    mc.formLayout( self._subForms[3], e=True, vis=self._version_column_should_show())

                else:
                    log.debug(log_msg(_str_func,"subtypes 2..."))
                    mc.formLayout( self._subForms[1], e=True, vis=True )


        attachForm = []
        attachControl = []
        attachPosition = []

        attachedForms = []

        for form in self._subForms:
            vis = mc.formLayout(form, q=True, visible=True)
            if vis:
                attachedForms.append(form)

        for i,form in enumerate(attachedForms):
            if i == 0:
                attachForm.append( (form, 'left', 1) )
            else:
                attachControl.append( (form, 'left', 5, attachedForms[i-1]) )

            attachForm.append((form, 'top', 0))
            attachForm.append((form, 'bottom', 5))

            if i == len(attachedForms)-1:
                attachForm.append( (form, 'right', 1) )
            else:
                attachPosition.append( (form, 'right', 5, (100 / len(attachedForms)) * (i+1)) )

        self._assetsForm( edit=True, attachForm = attachForm, attachControl = attachControl, attachPosition = attachPosition)

    def build_menus(self):
        _str_func = 'build_menus[{0}]'.format(self.__class__.TOOLNAME)            
        log.debug("|{0}| >>...".format(_str_func))   
        self.uiMenu_FirstMenu = mUI.MelMenu(l='File', pmc = cgmGEN.Callback(self.buildMenu_first))

        self.uiMenu_Projects = mUI.MelMenu( l='Projects', pmc=self.buildMenu_project)		        

        self.uiMenu_OptionsMenu = mUI.MelMenu( l='Options', pmc=self.buildMenu_options)
        self.uiMenu_ToolsMenu = mUI.MelMenu( l='Tools', pmc=self.buildMenu_tools,pmo=True)
        self.uiMenu_Utils = mUI.MelMenu(l='Utils', pmo=1,
                                        pmc = cgmGEN.Callback(self.buildMenu_utils),
                                        tearOff=True)
        self.uiMenu_projectUtils = mUI.MelMenu(l='Project Scripts',
                                               tearOff=True)

        self.uiMenu_HelpMenu = mUI.MelMenu( l='Help', pmc=self.buildMenu_help,pmo=True)

    def uiProject_open(self):
        PROJECT.uiProject_load(self)
        self.uiProject_refreshDisplay()
        self.uiFunc_projectDirtyState(False)

    def uiProject_saveAndRefresh(self):
        self.SaveOptions()
        if not PROJECT.uiProject_save(self):
            return
        self.uiProject_refreshDisplay()
        self.uiFunc_projectDirtyState(False)

    def reload_headerImage(self, path = None):
        _str_func = 'reload_headerImage'
        log.debug("|{0}| >>...".format(_str_func))

        if path:
            _path = PATHS.Path(path)

        else:
            _path = PATHS.Path(self.d_tf['paths']['image'].getValue())

        if _path.exists():
            log.warning('Image path: {0}'.format(_path))
            _imagePath = _path
        else:
            _imagePath = os.path.join(mImagesPath.asFriendly(),
                                      'cgm_project_{0}.png'.format(self.d_tf['general']['type'].getValue()))

        _height = CGMOS.get_image_size(_imagePath)[1]
        log.debug(log_msg(_str_func,"Height: {}".format( _height )))
        self.uiImage_Project(edit=True, height = _height)
        self.uiImage_Project.setImage(_imagePath)
        #self.uiImageRow_project.layout()

    def uiProject_refreshDisplay(self):
        #self.uiFunc_displayProject(self.displayProject)
        
        #DirMask -------------------------------------------------------
        self.l_dirMask = copy.copy(_l_directoryMask)
        
        if self.mDat.d_project.get('dirMask'):
            _l_mask = CORESTRING.parseCommaString(self.mDat.d_project.get('dirMask'))
            self.l_dirMask.extend(_l_mask)
        
            if self.l_dirMask:
                self.l_dirMask = [n.lower() for n in self.l_dirMask]
        #----------------------------------------------------------------
        
        log.debug("DirMask:")
        log.debug(self.l_dirMask)

        _bgColor = self.v_bgc
        self.d_userPaths = {}
        try:
            _bgColor = self.mDat.d_colors['project']

        except Exception as err:
            log.warning("No project color stored | {0}".format(err))

        try:self.uiImage_ProjectRow(edit=True, bgc = _bgColor)
        except Exception as err:
            log.warning("Failed to set bgc: {0} | {1}".format(_bgColor,err))

        try:

            _c_secondary = self.mDat.d_colors['secondary']
            #print _c_secondary
            vTmp = _c_secondary
            vLite = [MATH.Clamp(1.7 * v, .5, 1.0) for v in vTmp]


            self._detailsToggleBtn(edit=True, bgc=vTmp)
            self._projectToggleBtn(edit=True, bgc=vTmp)
            self.uiScrollList_dirContent.v_hlc = vLite
            self.uiScrollList_dirExport.v_hlc = vLite

        except Exception as err:
            log.error("Load project color set error | {0}".format(err))

            self._detailsToggleBtn(edit=True, bgc=(1.0, .445, .08))
            self._projectToggleBtn(edit=True, bgc=(1.0, .445, .08))
            self.uiScrollList_dirContent(edit=True, hlc = (1.0, .445, .08))
            self.uiScrollList_dirExport(edit=True, hlc = (1.0, .445, .08))

        d_userPaths = self.mDat.userPaths_get()
        self.d_userPaths = d_userPaths

        if not d_userPaths.get('content'):
            log.error("No Content path found")
            self.reload_headerImage()            
            #return False

        if not d_userPaths.get('export'):
            log.error("No Export path found")
            self.exportDirectoryTF(edit=1,en=False)
        else:
            self.exportDirectory = d_userPaths['export']
            self.exportDirectoryTF(edit=1,en=True)            
            self.exportDirectoryTF.setValue( self.exportDirectory )

            self.uiScrollList_dirExport.mDat = self.mDat        
            self.uiScrollList_dirExport.rebuild( self.exportDirectory)            

        _path_content = d_userPaths.get('content')
        if _path_content and os.path.exists(_path_content):
            self.LoadCategoryList(d_userPaths['content'])

            _l = self.mDat.assetTypes_get() if self.mDat.assetTypes_get() else self.mDat.d_structure.get('assetTypes', [])
            _l = sorted(_l, key=lambda v: v.upper())

            self.l_categoriesBase = _l
            self.categoryList = [c for c in self.l_categoriesBase]

            for i,f in enumerate(os.listdir(self.directory)):
                if os.path.isfile(os.path.join(self.directory, f)):
                    continue
                if f in self.l_categoriesBase:
                    continue

                self.categoryList.append(f)

            if d_userPaths.get('image') and os.path.exists(d_userPaths.get('image')):
                self.uiImage_Project.setImage(self.reload_headerImage(d_userPaths['image']))
            else:
                _imageFailPath = os.path.join(mImagesPath.asFriendly(),
                                              'cgm_project_{0}.png'.format(self.mDat.d_project.get('type','unity')))
                self.reload_headerImage(_imageFailPath)


            self.buildMenu_category()

            mc.workspace( d_userPaths['content'], openWorkspace=True )

            self.assetMetaData = {}
            self.LoadOptions()

            self.assetList['scrollList'].clearSelection()
        else:
            log.error('error "Project content path does not exist')
            self.reload_headerImage()
            
            #HERE JOSH 

        self.uiScrollList_dirContent.mDat = self.mDat
        self.uiScrollList_dirContent.rebuild( self.directory)


        if d_userPaths.get('poses') and os.path.exists(d_userPaths.get('poses')):
            self.var_posePathProject.value = d_userPaths['poses']
            self.var_posePathLocal.value = d_userPaths['poses']

        self.rebuild_scriptUI()
        
        
        self.LoadPreviousSelection()
        
        

        """
        log.debug( "+"*100)
        log.debug(self.d_tf['general']['mayaFilePref'].getValue())        
        log.debug(self.d_tf['exportOptions']['removeNameSpace'].getValue())
        log.debug(self.d_tf['exportOptions']['zeroRoot'].getValue())        
        log.debug(self.d_tf['exportOptions']['postEuler'].getValue())        
        log.debug(self.d_tf['exportOptions']['postTangent'].getValue()) """       





    def uiProject_reset(self):
        PROJECT.uiProject_reset(self)
        self.uiProject_refreshDisplay()

    def uiProject_revert(self):
        PROJECT.uiProject_revert(self)
        self.uiProject_refreshDisplay()

    def uiProject_clear(self):
        PROJECT.uiProject_clear(self)
        self.uiProject_refreshDisplay()

    def uiProject_new(self):


        if not PROJECT.uiProject_new(self):
            return

        self.directory = ''
        self.exportDirectoryTF.setValue('')

        self.assetList['scrollList'].clear()
        self.subTypeSearchList['scrollList'].clear()
        self.variationList['scrollList'].clear()
        self.versionList['scrollList'].clear()                

        self.LoadProject(self.mDat.str_filepath)

    def uiProject_duplicate(self):
        """
        Duplicate the current project with a new name.
        Prompts user for new project name, clears current project path,
        sets new name in mDat, and triggers save as dialog.
        """
        _str_func = 'uiProject_duplicate'
        log.debug("|{0}| >>...".format(_str_func))
        
        # Get current project name
        current_name = self.mDat.d_project.get('name', 'Unnamed Project')
        
        # Prompt for new project name
        result = mc.promptDialog(
            title='Duplicate Project',
            message='Enter new project name:',
            button=['OK', 'Cancel'],
            text=current_name + '_copy',
            defaultButton='OK',
            cancelButton='Cancel',
            dismissString='Cancel'
        )
        
        if result != 'OK':
            log.info("Project duplication cancelled by user")
            return False
            
        new_name = mc.promptDialog(query=True, text=True)
        
        if not new_name or new_name.strip() == '':
            log.warning("No project name entered")
            return False
            
        new_name = new_name.strip()
        
        # If name is the same as current, don't proceed
        if new_name == current_name:
            log.warning("New project name is the same as current project name")
            return False
            
        log.info("Duplicating project '{0}' as '{1}'".format(current_name, new_name))
        
        # Clear current project path and set new name
        self.mDat.str_filepath = None
        self.mDat.d_project['name'] = new_name
        
        # Clear UI fields
        self.directory = ''
        self.exportDirectoryTF.setValue('')
        self.assetList['scrollList'].clear()
        self.subTypeSearchList['scrollList'].clear()
        self.variationList['scrollList'].clear()
        self.versionList['scrollList'].clear()
        
        # Refresh display to show new project name
        self.uiProject_refreshDisplay()
        
        # Trigger save as dialog
        PROJECT.uiProject_saveAs(self)
        
        log.info("Project duplication completed successfully")
        return True

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()

        #Recent -------------------------------------------------------------------


        mUI.MelMenuItem( self.uiMenu_FirstMenu, label='Export Selection',
        c = lambda *a:self.ExportSelection(mode='content') )
        #>>> Reset Options		                     
        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu, label='Basic' )
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="New",
                         ann='Create a new project',                         
                         c = lambda *a:mc.evalDeferred(self.uiProject_new,lp=True))


        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Open",
                         ann='Open an existing project',                         
                         c = lambda *a:mc.evalDeferred(self.uiProject_open,lp=True))

        #Recent Projects --------------------------------------------------------------------------
        self.mPathList_recent.verify()
        _recent = mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Recent",
                                   ann='Open an existing project',subMenu=True)

        for p in self.mPathList_recent.l_paths:
            if '.' in p:
                _split = p.split('.')
                _l = CORESTRING.short(str(_split[0]),20)                
            else:
                _l = CORESTRING.short(str(p),20)            

            _short = self.d_projectPathsToNames.get(os.path.normpath(p)) or _l

            mUI.MelMenuItem(_recent, l=_short,
                            c = partial(self.LoadProject,p))            
        #==========================================================================================



        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save ",
                         c = lambda *a:mc.evalDeferred(self.uiProject_saveAndRefresh,lp=True))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save As",
                         c = lambda *a:mc.evalDeferred(cgmGEN.Callback(PROJECT.uiProject_saveAs,self),lp=True))

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Clone",
                         ann='Create a duplicate of the current project with a new name',
                         c = lambda *a:mc.evalDeferred(self.uiProject_duplicate,lp=True))

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu, label='Utils' )

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         ann='Reset data to default',
                         c = lambda *a:mc.evalDeferred(cgmGEN.Callback(self.uiProject_reset),lp=True))

        #mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Fill",
        #                 ann='Refill the ui fields from the mDat',                         
        #                 c = lambda *a:mc.evalDeferred(cgmGEN.Callback(PROJECT.uiProject_fill,self),lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Revert",
                         ann='Revert to saved file data',
                         c = lambda *a:mc.evalDeferred(self.uiProject_revert,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Clear",
                         ann='Clear the fields',
                         c = lambda *a:mc.evalDeferred(self.uiProject_clear,lp=True))


        """
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Load",
                         c = lambda *a:mc.evalDeferred(self.uiProject_load,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save ",
                         c = lambda *a:mc.evalDeferred(self.uiProject_save,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Save As",
                         c = lambda *a:mc.evalDeferred(self.uiProject_saveAs,lp=True))
        #mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Duplicate",
        #                c = lambda *a:mc.evalDeferred(self.uiProject_duplicate,lp=True))

        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu, label='Utils' )
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         ann='Reset data to default',
                         c = lambda *a:mc.evalDeferred(self.reset,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Fill",
                         ann='Refill the ui fields from the mDat',                         
                         c = lambda *a:mc.evalDeferred(self.uiProject_fill,lp=True))        
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Revert",
                         ann='Revert to saved file data',
                         c = lambda *a:mc.evalDeferred(self.uiProject_revert,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Clear",
                         ann='Clear the fields',
                         c = lambda *a:mc.evalDeferred(self.uiProject_clear,lp=True))
        """




        mUI.MelMenuItemDiv( self.uiMenu_FirstMenu, label='UI' )

        #self.uiMenu_buildDock(self.uiMenu_FirstMenu)
        """
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Dock",
                         c = lambda *a:self.do_dock())"""        

        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reload",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))
        mUI.MelMenuItem( self.uiMenu_FirstMenu, l="Reset",
                         c = lambda *a:mc.evalDeferred(self.reload,lp=True))    
    def buildMenu_utils(self):
        self.uiMenu_Utils.clear()

        SCENEUTILS.buildMenu_utils(self, self.uiMenu_Utils)



    def buildMenu_help( self, *args):
        self.uiMenu_HelpMenu.clear()

        mc.menuItem(parent=self.uiMenu_HelpMenu,
                    l = 'Get Help',
                            c='import webbrowser;webbrowser.open("https://http://docs.cgmonks.com/mrs.html");',                        
                            rp = 'N')    
        mUI.MelMenuItemDiv(self.uiMenu_HelpMenu, l="Dev")

        mUI.MelMenuItem(self.uiMenu_HelpMenu, l="Reload SceneStuff",
                        c=lambda *a: reloadSceneStuff())

        mUI.MelMenuItem( self.uiMenu_HelpMenu, l="Refresh",
                         c=lambda *a:self.uiProject_refreshDisplay())
                            #c=lambda *a:self.uiProject_saveAndRefresh())

        _log = mUI.MelMenuItem( self.uiMenu_HelpMenu, l="Logs:",subMenu=True, tearOff = True)


        mUI.MelMenuItem( _log, l="Dat",
                         c=lambda *a: self.mDat.log_self())
        mUI.MelMenuItem( _log, l="Open File Dat",
                         c=lambda *a: self.uiFunc_getOpenFileDict())        
        mUI.MelMenuItem( _log, l="States",
                         c=lambda *a: self.report_states())
        mUI.MelMenuItem( _log, l="Export Batch",
                         c=lambda *a: pprint.pprint(self.batchExportItems))        
        mUI.MelMenuItem( _log, l="Last Selection",
                         c=lambda *a: self.report_lastSelection() ) 
        mUI.MelMenuItem( _log, l="Log Self",
                         c=lambda *a: cgmUI.log_selfReport(self) )

        mUI.MelMenuItem( _log, l="Rebuild scriptUI",
                         c=lambda *a: self.rebuild_scriptUI() )

        #Logger toggle
        iMenu_loggerMaster = mUI.MelMenuItem( self.uiMenu_HelpMenu, l='Logger Level', subMenu=True)
        mUI.MelMenuItem( iMenu_loggerMaster, l='Info',
                         c = lambda *a:mc.evalDeferred(self.set_loggingInfo,lp=True))                         

        mUI.MelMenuItem( iMenu_loggerMaster, l='Debug',
                         c = lambda *a:mc.evalDeferred(self.set_loggingDebug,lp=True))

    def set_loggingInfo(self):
        self.var_DebugMode.value = 0
        log.setLevel(logging.INFO)
        cgmUI.log.setLevel(logging.INFO)

    def set_loggingDebug(self):
        self.var_DebugMode.value = 1
        log.setLevel(logging.DEBUG)    
        cgmUI.log.setLevel(logging.DEBUG)

    #@cgmGEN.Timer
    def buildMenu_project( self, *args):
        self.uiMenu_Projects.clear()
        mMenu = self.uiMenu_Projects
        #>>> Reset Options			

        mPathList = cgmMeta.pathList('cgmProjectPaths')
        mPathList.verify()

        project_names = []

        d_paths = {}
        """
        project name use:{path}
        """
        d_pathToName = {}

        for i,p in enumerate(mPathList.mOptionVar.value):
            proj = Project.data(filepath=p)
            name = proj.d_project['name']
            project_names.append(name)
            nameUse = name if project_names.count(name) == 1 else '%s {%i}' % (name,project_names.count(name)-1)
            _path = proj.userPaths_get().get('content') or False
            if _path and os.path.exists(_path):
                pass
            else:
                log.warning("'{0}' Missing content path".format(name))            

            _current = False
            #print('{} | {}'.format(p,self.path_current))
            _normpath = os.path.normpath(p)
            if  _normpath == self.path_current:
                _current = True

            d_paths[nameUse] = {'path':p, 'en':True, 'current':_current}
            d_pathToName[_normpath] = nameUse
        for l in sorted(d_paths, key=lambda s: s.lower()):        
            d = d_paths[l]
            if d['current']:
                mUI.MelMenuItemDiv( self.uiMenu_Projects, label='Current')                
                _label = "[ {} ]".format(l)
            else:
                _label = l

            mUI.MelMenuItem( self.uiMenu_Projects, en=d['en'], l=_label,
                             c = partial(self.LoadProject,d['path']))
            if d['current']:
                mUI.MelMenuItemDiv( self.uiMenu_Projects )


        mUI.MelMenuItemDiv( self.uiMenu_Projects )

        mUI.MelMenuItem( self.uiMenu_Projects, l="MRSProject",
                         c = lambda *a:mc.evalDeferred(Project.ui,lp=True))                         

        self.d_projectPathsToNames = d_pathToName
        mUI.MelMenuItemDiv(mMenu)
        #mUI.MelMenuItem(mMenu,
        #                label = "Clear Recent",
        #                ann="Clear the recent projects",
        #                c=cgmGEN.Callback(self.mPathList.clear))
        mUI.MelMenuItem(mMenu,
                        label = "Edit Path List",
                        ann="Open Edit UI",
                        c=cgmGEN.Callback(self.mPathList.ui))            

    def buildMenu_options( self, *args):
        self.uiMenu_OptionsMenu.clear()
        #>>> Reset Options		

        mUI.MelMenuItemDiv( self.uiMenu_OptionsMenu, label = 'Export', )
        self.cb_useMayaPy =  mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Use Maya Standalone",
                                              ann="Use Mayapy/Maya stand alone to process",
                                                 checkBox=self.useMayaPy,
                                                 c = lambda *a:mc.evalDeferred(self.SaveOptions,lp=True))        

        """
        self.cb_removeNamespace = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Remove namespace upon export",
                                                      checkBox=self.removeNamespace,
                                                      c = lambda *a:mc.evalDeferred(self.SaveOptions,lp=True))

        self.cb_zeroRoot = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Zero root upon export",
                                               checkBox=self.zeroRoot,
                                               c = lambda *a:mc.evalDeferred(self.SaveOptions,lp=True))

        self.cb_postEuler = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Post Euler",
                                               checkBox=self.var_postEuler.getValue(),
                                               c = lambda *a:mc.evalDeferred(self.SaveOptions,lp=True))

        self.cb_tangent = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Post Tangent",subMenu=True
                                              )
        uiMenu = self.cb_tangent 

        uiRC = mc.radioMenuItemCollection()
        #self.uiOptions_menuMode = []		
        _v = self.var_postTangent.value

        for i,item in enumerate(['none','auto','linear']):
            if item == _v: _rb = True
            else:_rb = False            
            mc.menuItem(parent=uiMenu,collection = uiRC,
                        label=item,
                        c = cgmGEN.Callback(self.var_postTangent.setValue,item),                                  
                        rb = _rb)

        #...-------------------------------------------------------------------------------------------
        self.cb_mayaFilePref = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Maya File Pref",subMenu=True
                                              )
        uiMenu = self.cb_mayaFilePref 

        uiRC = mc.radioMenuItemCollection()
        #self.uiOptions_menuMode = []		
        _v = self.var_mayaFilePref.value

        for i,item in enumerate(['ma','mb']):
            if item == _v: _rb = True
            else:_rb = False            
            mc.menuItem(parent=uiMenu,collection = uiRC,
                        label=item,
                        c = cgmGEN.Callback(self.var_mayaFilePref.setValue,item),                                  
                        rb = _rb)        

        """

        mUI.MelMenuItemDiv( self.uiMenu_OptionsMenu, l = 'Other')

        self.cb_showAllFiles = mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Show all files",
                                                checkBox=self.showAllFiles,
                                                           c = lambda *a:mc.evalDeferred(self.uiFunc_showAllFiles,lp=True))


        self.cb_showDirectories =  mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Show Directories",
                                                    checkBox=self.showDirectories,
                                                               c = lambda *a:mc.evalDeferred(self.SaveOptions,lp=True))
        self.cb_showPathWarnings = mUI.MelMenuItem(self.uiMenu_OptionsMenu, l="Show path warnings",
                                                     ann="Popup warnings for subtype directory mismatches and similar path issues (TD tooling)",
                                                     checkBox=self.showPathWarnings,
                                                     c=lambda *a: mc.evalDeferred(self.SaveOptions, lp=True))
        self.cb_alwaysSendReferenceFiles =  mUI.MelMenuItem( self.uiMenu_OptionsMenu, l="Always Send References",
                                                             checkBox= int(self.var_alwaysSendReferenceFiles.getValue()),
                                                               c = lambda *a:mc.evalDeferred(self.var_alwaysSendReferenceFiles.toggle,lp=True))        



    def uiFunc_showAllFiles(self):
        self.SaveOptions()
        self.LoadSubTypeList()
        self.LoadVariationList()
        self.LoadVersionList()

    def uiFunc_assetList_select(self):
        _str_func = 'uiFunc_assetList_select'
        log.debug(log_start(_str_func))

        try:
            path_set= os.path.normpath(os.path.join( self.path_dir_category, self.assetList['scrollList'].getSelectedItem() ))
        except:
            return

        if not os.path.exists(path_set):
            self.LoadCategoryList()
            return


        self._clear_searchable_list(self.subTypeSearchList)
        self._clear_searchable_list(self.variationList)
        self._clear_searchable_list(self.versionList)



        l_newTypes = []
        l_expected = []
        for d in CGMOS.get_lsFromPath(path_set,'dir'):
            _subName = self._resolveSubTypeLabelFromPathToken(d) or d
            if _subName in self.l_subTypesBase:
                l_expected.append(_subName)
            else:
                l_newTypes.append(_subName)

        #pprint.pprint(l_expected)
        #pprint.pprint(l_newTypes)

        self.subTypes = []
        if l_expected:
            self.subTypes.extend(l_expected)
        if l_newTypes:
            self.subTypes.extend(l_newTypes)
        # De-dupe while preserving order so canonical subtype labels win.
        self.subTypes = list(dict.fromkeys(self.subTypes))


        #print self.subType
        #pprint.pprint(self.subTypes)        

        if self.subTypes:
            self.buildMenu_subTypes()
            if self.subType not in self.subTypes:
                log.debug(log_msg(_str_func, "Setting subtype because stored not in list"))
                self.subType = self.subTypes[0]
            else:
                self.SetSubType(self.subTypes.index(self.subType))

        #if self.subTypes:
            #self.buildMenu_subTypes()
            #self.LoadSubTypeList()

        self.buildAssetForm()

        if not self.subTypes:#...if 
            self.LoadVersionList()

        self.LoadPreviousSelection(skip=['asset'])

        if self.subTypes:
            self.uiUpdate_setsButtons()

        self.SaveCurrentSelection()

    def uiUpdate_setsButtons(self):
        _str_func = 'uiUpdate_setsButtons'
        log.debug(log_start(_str_func))

        browse_dir = self._sets_buttons_browse_directory()
        show_dir = self._level_show_dir_actions(browse_dir)
        show_file = self._level_show_file_actions(browse_dir, selected_is_file=self.b_subFile)

        log.debug(log_msg(_str_func, "browse_dir: {} | show_dir: {} | show_file: {}".format(
            browse_dir, show_dir, show_file)))

        self.mRow_setButtons.clear()
        if show_dir:
            self._append_set_dir_buttons(self.mRow_setButtons)
        if show_file:
            self._append_set_file_buttons(self.mRow_setButtons)
        self.mRow_setButtons.layout()

        log.debug(log_msg(_str_func,cgmGEN._str_hardBreak))

    def uiUpdate_variationButtons(self):
        _str_func = 'uiUpdate_variationButtons'
        log.debug(log_start(_str_func))

        browse_dir = self.path_set
        show_dir = bool(browse_dir and os.path.isdir(browse_dir))
        show_file = self._level_show_file_actions(browse_dir, selected_is_file=self.b_varFile)

        log.debug(log_msg(_str_func, "show_dir: {} | show_file: {}".format(show_dir, show_file)))

        self.mRow_variationButtons.clear()
        if show_dir:
            self._append_variation_dir_buttons(self.mRow_variationButtons)
        if show_file:
            self._append_variation_file_buttons(self.mRow_variationButtons)
        self.mRow_variationButtons.layout()

        log.debug(log_msg(_str_func,cgmGEN._str_hardBreak))

    def uiFunc_subTypeList_select(self):
        _str_func = 'uiFunc_subTypeList_select'
        log.debug(log_start(_str_func))

        #self.report_selectedPaths()
        self.file_subType = None

        try:
            _subRoot = self.path_subType or self._resolve_subType_container_path(self.path_asset, self.subType)
            _path = os.path.normpath(os.path.join(_subRoot,
                                                  self.subTypeSearchList['scrollList'].getSelectedItem(),
                                                  ))
        except:
            _path = None

        if _path and os.path.isfile(_path):
            self.b_subFile = True
            self.b_varFile = False
            self.file_subType = _path
            log.debug(log_msg(_str_func,"File passed"))
            self.variationList['scrollList'].clear()
            self.versionList['scrollList'].clear()

            for mUI in self.ml_fileOptions_set:
                mUI(edit=True,en=True)

            for mUI in self.ml_dirOptions_set:
                mUI(edit=True,en=False)

            self._refresh_p4_menu_items([self.ml_p4_options_set], True)
            self._refresh_p4_dir_menu_items([self.ml_p4_options_dir_set], False)

            log.debug(log_msg(_str_func,'is versionList'))            
            self.assetMetaData = self.getMetaDataFromFile()
            self.buildDetailsColumn()
            self._log_picked_file_to_script_editor()
            self.buildAssetForm()
            self.uiUpdate_setsButtons()

            return
        else:
            log.debug(log_msg(_str_func,"dir passed"))            
            self.b_subFile = False
            #for mUI in self.ml_fileOptions_set:
            #    mUI(edit=True,en=False)
            for mUI in self.ml_dirOptions_set:
                mUI(edit=True,en=True)

            self._refresh_p4_menu_items([self.ml_p4_options_set], False)
            self._refresh_p4_dir_menu_items([self.ml_p4_options_dir_set], True)

        self._version_list_refreshed = False

        if self.hasVariant:
            log.debug(log_msg(_str_func,"hasVariant"))                        
            self.b_varFile = False
            self.LoadVariationList()
        else:
            log.debug(log_msg(_str_func,"hasVariant == false"))
            if self.variationList:
                self._clear_searchable_list(self.variationList)

        if not self._version_list_refreshed:
            self.LoadVersionList()
        self._refreshMetaDataFromSelection()

        #else:
        #self.LoadSubTypeList()

        self.buildAssetForm()

        self.uiUpdate_setsButtons()
        self.SaveCurrentSelection()

        log.debug(log_end(_str_func))


    def uiFunc_variationList_select(self):
        _str_func = 'uiFunc_variationList_select'
        log.debug(log_start(_str_func))
        #self.report_selectedPaths()

        _path = self.path_variationDirectory

        if not _path:
            return

        if os.path.isfile(_path):
            log.debug(log_msg(_str_func,"file passed"))
            self.b_varFile = True
            for mUI in self.ml_fileOptions_set:
                mUI(edit=True,en=True)

            for mUI in self.ml_fileOptions_variant:
                mUI(edit=True,en=True)            
            for mUI in self.ml_dirOptions_variant:
                mUI(edit=True,en=False)

            self._refresh_p4_menu_items([self.ml_p4_options_variant], True)
            self._refresh_p4_dir_menu_items([self.ml_p4_options_dir_variant], False)

            self.versionList['scrollList'].clear()
            self.assetMetaData = self.getMetaDataFromFile()
            self.buildDetailsColumn()
            self._log_picked_file_to_script_editor()
        elif os.path.isdir(_path):
            log.debug(log_msg(_str_func,"dir passed"))
            self.b_varFile = False            
            for mUI in self.ml_fileOptions_variant:
                mUI(edit=True,en=False)            
            for mUI in self.ml_dirOptions_variant:
                mUI(edit=True,en=True)

            self._refresh_p4_menu_items([self.ml_p4_options_variant], False)
            self._refresh_p4_dir_menu_items([self.ml_p4_options_dir_variant], True)

            if not self._version_list_refreshed:
                self.LoadVersionList()
            else:
                self._version_list_refreshed = False
            self._refreshMetaDataFromSelection()

        self.buildAssetForm()
        self.uiUpdate_variationButtons()
        self.SaveCurrentSelection()

    def uiFunc_versionList_select(self, selectKey= None):
        _str_func = 'uiFunc_variationList_select'
        log.debug(log_start(_str_func))
        #if selectKey:
            #self.versionList['scrollList'].selectByValue(selectKey)

        #self.report_selectedPaths()

        self.assetMetaData = self.getMetaDataFromFile()
        self.buildDetailsColumn()
        self.SaveCurrentSelection()
        self._refresh_p4_menu_items(
            [self.ml_p4_options_version],
            bool(self._scene_p4_selected_file_path()))
        self._log_picked_file_to_script_editor()



    def buildProjectColumn(self):
        if not self._projectForm(q=True, vis=True):
            log.debug("Project column isn't visible")
            return

        log.debug("Project column...")

        self._projectForm.clear()

        #self._projectForm(e=1, vis=1)
        mc.setParent(self._projectForm)

        mUI.MelLabel(self._projectForm,l='Project', h=15, ut = 'cgmUIHeaderTemplate')

        _inside = self._projectForm
        #Utils -------------------------------------------------------------------------------------------
        _row = mUI.MelHLayout(_inside,padding=3,)
        button_refresh = mUI.MelButton(_row,
                                       label='Refresh',ut='cgmUITemplate',
                                       c=lambda *a: self.uiScrollList_dirContent.rebuild( self.directory),
                                        ann='Force the scroll list to update')

        button_add= mUI.MelButton(_row,
                                  label='Add',ut='cgmUITemplate',
                                  ann='Add a subdir to the path root')    

        button_verify = mUI.MelButton(_row,
                                      label='Verify Dir',ut='cgmUITemplate',
                                       ann='Verify the directories from the project Type')  

        mUI.MelButton(_row,
                      label='Query',ut='cgmUITemplate',
                      c=lambda *a: SCENEUTILS.find_tmpFiles( self. self.directory),
                       ann='Query trash files')    
        mUI.MelButton(_row,
                      label='Clean',ut='cgmUITemplate',
                      c=lambda *a: SCENEUTILS.find_tmpFiles( self.directory,cleanFiles=1),
                       ann='Clean trash files')
        _row.layout()
        #--------------------------------------------------------------------------------------------

        mUI.MelSeparator(_inside,ut='cgmUISubTemplate',h=3)


        _textField = mUI.MelTextField(_inside,
                                      ann='Filter',
                                      w=50,
                                      bgc = [.3,.3,.3],
                                      en=True,
                                      text = '')    



        #Scroll list
        mScrollList = Project.cgmProjectDirList(_inside, ut='cgmUISubTemplate',
                                                allowMultiSelection=0,en=True,
                                        ebg=0,
                                        h=600,
                                        bgc = [.2,.2,.2],
                                        w = 50)

        mScrollList.mDat = self.mDat

        #Connect the functions to the buttons after we add the scroll list...
        button_verify(edit=True,
                      c=lambda *a:Project.uiProject_verifyDir(self,'content',None,mScrollList),)
        button_add(edit=True,
                   c=lambda *a:Project.uiProject_addDir(self,'content',mScrollList),
                   )

        try:mScrollList(edit=True,hlc = [.5,.5,.5])
        except:pass

        mScrollList.set_filterObj(_textField)
        _textField(edit=True,
                   tcc = lambda *a: mScrollList.update_display())    

        #mScrollList.set_selCallBack(mrsPoseDirSelect,mScrollList,self)

        self.uiScrollList_dirContent = mScrollList        

        self.uiScrollList_dirContent.mDat = self.mDat




    def buildDetailsColumn(self):
        if not self._detailsColumn(q=True, vis=True):
            log.debug("details column isn't visible")
            return
        _spacer = 2
        _bgc = .8,.8,.8

        self._detailsColumn.clear()

        mc.setParent(self._detailsColumn)

        mUI.MelLabel(self._detailsColumn,l='Details', h=15, ut = 'cgmUIHeaderTemplate')

        mc.setParent(self._detailsColumn)
        cgmUI.add_LineSubBreak()		

        thumb = self.getThumbnail()

        self.uiImage_Thumb = mUI.MelImage( self._detailsColumn, w=130, h=150 )
        self.uiImage_Thumb(e=True, vis=(thumb != None))

        if thumb:
            self.uiImage_Thumb.setImage(thumb)

        pum = mUI.MelPopupMenu(self.uiImage_Thumb)
        mUI.MelMenuItem(pum, label="Remake Thumbnail", command=cgmGEN.Callback(self.makeThumbnail) )		

        self.uiButton_MakeThumb = mUI.MelButton(self._detailsColumn, ut = 'cgmUITemplate', h=150, label="Make Thumbnail", c=cgmGEN.Callback(self.makeThumbnail), vis=(thumb == None))

        mc.setParent(self._detailsColumn)
        cgmUI.add_LineSubBreak()

        _row = mUI.MelHLayout(self._detailsColumn)

        mUI.MelButton(_row, ut = 'cgmUITemplate', h=15, label="Refresh Data",
                      c=cgmGEN.Callback(self.refreshMetaData) )
        mUI.MelButton(_row, ut = 'cgmUITemplate', h=15, label="Report Data",
                      c=cgmGEN.Callback(self.metaData_print) )
        mUI.MelButton(_row, ut = 'cgmUITemplate', h=15, label="Copy ShotList",
                      c=cgmGEN.Callback(self.metaData_copyShotList) )                
        _row.layout()


        mc.setParent(self._detailsColumn)
        cgmUI.add_LineSubBreak()	

        _d = {'Asset':self.assetMetaData.get('asset', None),
              'Type':self.assetMetaData.get('type', None),
              'SubAsset':self.assetMetaData.get('subTypeAsset', None),
              'Variation':self.assetMetaData.get('variation', None),
              'User':self.assetMetaData.get('user', None)}

        for k in ['Asset','Type','SubAsset','Variation','User']:
            _dat = _d.get(k)
            if _dat is not None:
                _row = mUI.MelHSingleStretchLayout(self._detailsColumn)
                mUI.MelLabel(_row,l=k, w=70)
                _row.setStretchWidget(mUI.MelTextField(_row, text=_dat, ann=_dat,
                                                       editable = False, bgc=_bgc))	
                mUI.MelSpacer(_row,w=_spacer)

                _row.layout()	


        """
        _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

        mUI.MelLabel(_row,l='Asset', w=70)
        _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('asset', ""), editable = False, bgc=(.8,.8,.8)))	
        mUI.MelSpacer(_row,w=_spacer)

        _row.layout()

        _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

        mUI.MelLabel(_row,l='Type', w=70)
        _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('type', ""), editable = False, bgc=(.8,.8,.8)))	
        mUI.MelSpacer(_row,w=_spacer)

        _row.layout()

        _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

        mUI.MelLabel(_row,l='SubType', w=70)
        _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('subType', ""), editable = False, bgc=(.8,.8,.8)))	
        mUI.MelSpacer(_row,w=_spacer)

        _row.layout()

        if self.assetMetaData.get('subTypeAsset', None):
            _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

            mUI.MelLabel(_row,l='SubAsset', w=70)
            _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('subTypeAsset', ""), editable = False, bgc=(.8,.8,.8)))	
            mUI.MelSpacer(_row,w=_spacer)

            _row.layout()	

        if self.assetMetaData.get('variation', None):
            _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

            mUI.MelLabel(_row,l='Variation', w=70)
            _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('variation', ""), editable = False, bgc=(.8,.8,.8)))	
            mUI.MelSpacer(_row,w=_spacer)

            _row.layout()	

        _row = mUI.MelHSingleStretchLayout(self._detailsColumn)

        mUI.MelLabel(_row,l='User', w=70)
        _row.setStretchWidget(mUI.MelTextField(_row, text=self.assetMetaData.get('user', ""), editable = False, bgc=(.8,.8,.8)))	
        mUI.MelSpacer(_row,w=_spacer)

        _row.layout()	
        """
        mUI.MelLabel(self._detailsColumn,l='Notes', w=70)

        _row = mUI.MelHSingleStretchLayout(self._detailsColumn)
        mUI.MelSpacer(_row,w=_spacer)		
        noteField = mUI.MelScrollField(_row, h=150, text=self.assetMetaData.get('notes', ""), wordWrap=True, editable=True, bgc=(.8,.8,.8))
        noteField(e=True, changeCommand=cgmGEN.Callback( self.saveMetaNote,noteField ) )
        _row.setStretchWidget(noteField)
        mUI.MelSpacer(_row,w=_spacer)
        _row.layout()

        if self.assetMetaData.get('references', None):
            mUI.MelLabel(self._detailsColumn,l='References', w=50)

            for ref in self.assetMetaData.get('references', []):
                _row = mUI.MelHSingleStretchLayout(self._detailsColumn)
                path = os.path.normpath(self.directory) +  os.path.normpath(ref)
                mUI.MelSpacer(_row,w=_spacer)		
                _row.setStretchWidget(mUI.MelTextField(_row, text=ref, editable = False, bgc=(.8,.8,.8)))
                cgmUI.add_Button(_row,'Load', cgmGEN.Callback(VALID.fileOpen,path,True,True))


                mUI.MelSpacer(_row,w=_spacer)
                _row.layout()			

        if self.assetMetaData.get('shots', None):
            mUI.MelLabel(self._detailsColumn,l='Shots', w=50)

            for shot in self.assetMetaData.get('shots', []):
                _row = mUI.MelHRowLayout(self._detailsColumn, w=150)
                _ann = "{0} | start: {1} | end: {2} | length: {3}".format(shot[0],shot[1][0],shot[1][1],shot[1][2])
                mUI.MelSpacer(_row,w=_spacer)
                mUI.MelTextField(_row, text=shot[0], ann = _ann,
                                 editable = False, bgc=(.8,.8,.8), w = 120)
                mUI.MelTextField(_row, text=shot[1][0], editable = False, ann = _ann,
                                 bgc=(.8,.8,.8), w=40)
                mUI.MelTextField(_row, text=shot[1][1], editable = False, ann = _ann,
                                 bgc=(.8,.8,.8), w=40)
                mUI.MelTextField(_row, text=shot[1][2], editable = False, ann = _ann,
                                 bgc=(.8,.8,.8), w=40)
                mUI.MelSpacer(_row,w=_spacer)
                _row.layout()


        mUI.MelLabel(self._detailsColumn,l='File', w=50)
        for k in ['size','dateModified','dateAccess','file']:
            if self.assetMetaData.get(k, None) is not None:
                _row = mUI.MelHSingleStretchLayout(self._detailsColumn)
                _dat = self.assetMetaData.get(k, "")
                mUI.MelLabel(_row,l=k, w=70)
                _row.setStretchWidget(mUI.MelTextField(_row, text=_dat, ann=_dat,
                                                       editable = False, bgc=(_bgc)))	
                mUI.MelSpacer(_row,w=_spacer)

                _row.layout()                
        """
        ata['size'] = os.path.getsize(self.versionFile)
        data['dateModified'] = time.ctime(os.path.getmtime(self.versionFile))
        data['dateAccess'] = time.ctime(os.path.getctime(self.versionFile))
        data['file']
        """

    def makeThumbnail(self):
        if self.versionFile:
            path, filename = os.path.split(self.versionFile)
            basefile = os.path.splitext(filename)[0]

            metaDir = os.path.join(path, 'meta')
            if not os.path.exists(metaDir):
                os.mkdir( os.path.join(path, 'meta') )

            thumbFile = os.path.join(path, 'meta', '{0}.bmp'.format(basefile))
            r9General.thumbNailScreen(thumbFile, 256, 256)		
            self.uiButton_MakeThumb(e=True, vis=False)
            self.uiImage_Thumb.setImage(thumbFile)
            self.uiImage_Thumb(e=True, vis=True)

    def getThumbnail(self):
        thumbFile = None

        if self.versionFile:
            path, filename = os.path.split(self.versionFile)
            basefile = os.path.splitext(filename)[0]
            thumbFile = os.path.join(path, 'meta', '{0}.bmp'.format(basefile))
            if not os.path.exists(thumbFile):
                thumbFile = None

        return thumbFile

    def metaData_copyShotList(self):
        _d = self.getMetaDataFromFile() 

        _d.get('file')
        _file =  os.path.normpath(_d.get('file')).replace(os.path.normpath(self.mDat.userPaths_get()['content']), '')

        """
        {"arame_poker_cheer_left": [280, 420, 140], "arame_poker_cheer_right": [560, 700, 140], "arame_poker_cheer_lwrR": [700, 840, 140], "arame_poker_cheer_center": [0, 140, 140], "arame_poker_cheer_lwrL": [420, 560, 140], "arame_poker_cheer_down": [140, 280, 140]}
        """
        #Shots
        _d_res = {}

        if _d.get('shots'):
            _shots = _d.get('shots')
            _total = 0
            _lows = []
            _highs = []

            _l_shots = []

            for s in _shots:
                _d_res[str(s[0])] = s[1]
                _total += s[1][2]
                _l = [s[0], s[1][0], s[1][1], s[1][2]] 
                _l = [str(v) for v in _l]
                _l_shots.append( _l )
                _lows.append(s[1][0])
                _highs.append(s[1][1])

            """
            print ','.join(['clip','start','end',str(_total), "{0}".format(max(_highs) - min(_lows))])
            print ''
            for s in _l_shots:
                print ','.join(s)"""

            pprint.pprint(_d_res)

            mList = cgmMeta.validateObjArg('AnimListNode',noneValid=True)

            if mList is False:
                mList = cgmMeta.cgmObject(name="AnimListNode")#node.Transform(name="AnimListNode")
            mList.addAttr("subAnimList", attrType = 'string')


            mList.subAnimList = _d_res#json.dumps(self.animDict)            

    def metaData_print(self):

        _d = self.getMetaDataFromFile() 
        pprint.pprint(_d)

        _type = _d.get('type')
        _subType =_d.get('subType')
        _subTypeAsset = _d.get('subTypeAsset')
        _asset = _d.get('asset')

        _l = []
        for k in _type,_asset,_subType,_subTypeAsset:
            if k:
                _l.append(k)

        _name = '.'.join(_l)

        print('')
        _d.get('file')
        _file =  os.path.normpath(_d.get('file')).replace(os.path.normpath(self.mDat.userPaths_get()['content']), '')
        _l_asset = [_name,_file]
        print((','.join(_l_asset)))
        print('')

        #Shots
        if _d.get('shots'):
            _shots = _d.get('shots')
            _total = 0
            _lows = []
            _highs = []

            _l_shots = []

            for s in _shots:
                _total += s[1][2]
                _l = [s[0], s[1][0], s[1][1], s[1][2]] 
                _l = [str(v) for v in _l]
                _l_shots.append( _l )
                _lows.append(s[1][0])
                _highs.append(s[1][1])


            print((','.join(['clip','start','end',str(_total), "{0}".format(max(_highs) - min(_lows))])))
            print('')
            for s in _l_shots:
                print((','.join(s)))

        print('Notes')
        print((_d.get('notes','None')))

        #pprint.pprint( self.getMetaDataFromCurrent() )

    def getMetaDataFromCurrent(self):
        from cgm.core.mrs.Shots import AnimList
        import getpass

        #if os.path.normpath(self.versionFile) != os.path.normpath(mc.file(q=True, loc=True)):
            #mc.confirmDialog(title="No. Just no.", message="The open file doesn't match the selected file. I refuse to refresh this metaData with the wrong file. It just wouldn't feel right.", button=["Cancel", "Sorry"])
            #return

        data = {}
        data['asset'] = self.assetList['scrollList'].getSelectedItem()
        data['type'] = self.category
        data['subType'] = PU.subtype_file_token(self.subType) if self.subType else self.subType
        data['subTypeAsset'] = self.subTypeSearchList['scrollList'].getSelectedItem() if self.hasSub else ""
        data['variation'] = self.variationList['scrollList'].getSelectedItem() if self.hasVariant else ""
        data['user'] = getpass.getuser()

        data['size'] = os.path.getsize(self.versionFile)
        data['dateModified'] = time.ctime(os.path.getmtime(self.versionFile))
        data['dateAccess'] = time.ctime(os.path.getctime(self.versionFile))
        data['file'] = self.versionFile

        data['saved'] = datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        data['notes'] = ""

        data['references'] = [os.path.normpath(x).replace(os.path.normpath(self.directory), "") for x in mc.file(q=True, r=True)]

        data['startTime'] = mc.playbackOptions(q=True, min=True)
        data['endTime'] = mc.playbackOptions(q=True, max=True)

        l = AnimList()
        data['shots'] = l.SortedList(1)

        return data

    def getMetaDataFromFile(self):
        _func_str = 'Scene.getMetaDataFromFile'

        metaFile = None

        data = {}

        if self.versionFile:
            path, filename = os.path.split(self.versionFile)
            basefile = os.path.splitext(filename)[0]
            metaFile = os.path.join(path, 'meta', '{0}.dat'.format(basefile))
            if not os.path.exists(metaFile):
                log.debug("{0} | No meta file found".format(_func_str))
                metaFile = None
            else:
                f = open(metaFile, 'r')
                data = json.loads(f.read())
        else:
            log.debug("{0} | No version file found".format(_func_str))
        return data

    def refreshMetaData(self):
        currentFile = mc.file(q=True, loc=True)
        if not os.path.exists(currentFile):
            log.warning("Can't refresh unsaved files")
            return False
        if not self.versionFile:
            log.warning("No version file")            
            return
        if os.path.normpath(self.versionFile) != os.path.normpath(currentFile):
            mc.confirmDialog(title="No. Just no.", message="The open file doesn't match the selected file. I refuse to refresh this metaData with the wrong file. It just wouldn't feel right.", button=["Cancel", "Sorry"])
            return

        notes = self.assetMetaData.get('notes', "")
        self.assetMetaData = self.getMetaDataFromCurrent()
        self.assetMetaData['notes'] = notes

        self.buildDetailsColumn()
        self.saveMetaData()

    def saveMetaNote(self, field):
        self.assetMetaData['notes'] = field.getValue()
        self.saveMetaData()

    def saveMetaData(self):
        if self.versionFile:
            path, filename = os.path.split(self.versionFile)
            basefile = os.path.splitext(filename)[0]

            metaDir = os.path.join(path, 'meta')
            if not os.path.exists(metaDir):
                os.mkdir( os.path.join(path, 'meta') )

            metaFile = os.path.join(path, 'meta', '{0}.dat'.format(basefile))
            try:
                PATHUTIL.prepare_paths_for_write([metaFile], mDat=self.mDat)
            except PATHUTIL.PathWritePrepareError as err:
                log.error(str(err))
                return
            f = open(metaFile, 'w')
            f.write( json.dumps(self.assetMetaData) )
            f.close()

            log.info('wrote file: {0}'.format(metaFile))

    def uiFunc_showDirectories(self, val):
        self._uiRow_dir(e=True, vis=val)
        self._uiRow_export(e=True, vis=val)

    def uiFunc_toggleDisplayInfo(self):
        self.displayDetails = not self.displayDetails
        self.uiFunc_displayDetails(self.displayDetails)
        self.SaveOptions()

    def uiFunc_toggleProjectColumn(self):
        self.displayProject = not self.displayProject
        self.uiFunc_displayProject(self.displayProject)
        self.SaveOptions()

    def uiFunc_displayDetails(self, val):
        self._detailsColumn(e=True, vis=val)
        self._detailsToggleBtn(e=True, label='>' if val else '<')

        if val:
            self.buildDetailsColumn()

    def uiFunc_projectDirtyState(self,arg=True):
        _str_func = 'uiFunc_projectDirtyState'
        log.debug("|{}| >>...{}".format(_str_func,arg))
        if arg:
            self.b_projectDirty = True            
            self.ui_projectDirty(edit=True,vis=True)
        else:
            self.b_projectDirty = False            
            self.ui_projectDirty(edit=True,vis=False)

    def uiFunc_displayProject(self,val):
        _str_func = 'uiFunc_displayProject'
        log.debug("|{}| >>...{}".format(_str_func,val))        
        self._projectForm(e=True, vis=val)
        self._projectToggleBtn(e=True, label='<' if val else '>')

        #if val:
            #self.uiScrollList_dirContent.mDat = self.mDat
            #self.uiScrollList_dirContent.rebuild( self.directory)
            #self.buildProjectColumn()        

    def buildMenu_tools( self, *args):
        self.uiMenu_ToolsMenu.clear()
        #>>> Reset Options		

        mUI.MelMenuItemDiv( self.uiMenu_ToolsMenu, label='Asset..' )

        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l="Update Selected Rigs",
                         c = lambda *a:mc.evalDeferred(self.UpdateToLatestRig,lp=True))

        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l="Remap Unlinked Textures",
                         c = lambda *a:mc.evalDeferred(self.RemapTextures,lp=True))

        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l="Verify Asset Dirs",
                         c = cgmGEN.Callback(self.VerifyAssetDirs) )

        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l="Clean Scene",
                         c = lambda *a:mc.evalDeferred(MAYABEODD.cleanFile,lp=1) )        

        mUI_skinDat = mUI.MelMenuItem(self.uiMenu_ToolsMenu,l='SkinDat',subMenu=True)
        SKINDAT.uiBuildMenu(mUI_skinDat)

        mUI.MelMenuItemDiv( self.uiMenu_ToolsMenu, label='Baking..' )

        #Export Menu ...
        _exportMenu = mUI.MelMenuItem(self.uiMenu_ToolsMenu,l='Export Sets',subMenu=True)
        mUI.MelMenuItem( _exportMenu, l="Set",
                         c = lambda *a:mc.evalDeferred(self.SetExportSets,lp=True))
        mUI.MelMenuItem( _exportMenu, l="Reset",
                         c = lambda *a:mc.evalDeferred(self.ResetExportSets,lp=True))
        mUI.MelMenuItem( _exportMenu, l="Query",
                         c = lambda *a:mc.evalDeferred(self.QueryExportSets,lp=True))

        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l='Verify Sets',
                         c = lambda *a:mc.evalDeferred(SCENEUTILS.verify_ObjectSets,lp=True))

        mUI.MelMenuItemDiv( self.uiMenu_ToolsMenu, label='Project..' )
        mUI.MelMenuItem( self.uiMenu_ToolsMenu, l="Maya Scanner",
                         c = lambda *a:mc.evalDeferred(self.uiFunc_mayaScannerProject,lp=True))

    def uiFunc_mayaScannerProject(self):

        mc.loadPlugin("MayaScanner")
        #mPath = PATHS.Path(self.directory)
        #print mPath
        #split = mPath.split()
        #print split
        #return
        path = r"{}".format(self.directory)
        print(path)
        cgmGEN._reloadMod(MAYABEODD)
        if path and os.path.exists(path):
            MAYABEODD.mayaScanner_batch(path)


    def RemapTextures(self, *args):
        import cgm.tools.findTextures as findTextures
        findTextures.FindAndRemapTextures()

    def buildMenu_category(self, *args):
        self.categoryMenu.clear()
        self.categoryMenuItemList = []

        l_cats = []
        b_extra = False
        for i,category in enumerate(self.categoryList):
            #if category not in self.l_categoriesBase and not b_extra != True:
            #    mUI.MelMenuItemDiv( self.categoryMenu, label='Extras..' )
            #    b_extra = True


            self.categoryMenuItemList.append( mUI.MelMenuItem(self.categoryMenu, label=category, c=partial(self.SetCategory,i)) )
            if i == self.categoryIndex:
                self.categoryMenuItemList[i]( e=True, enable=False)
            l_cats.append(category)


    def buildMenu_subTypes(self, *args):
        _str_func = 'buildMenu_subTypes'
        log.debug(log_start(_str_func))

        self.subTypeMenu.clear()
        # for item in self.subTypeMenuItemList:
        # 	if mc.menuItem(item, q=True, exists=True):
        # 		mc.deleteUI(item)

        self.subTypeMenuItemList = []

        mc.setParent(self.subTypeMenu, menu=True)
        b_extra = False

        for i,subType in enumerate(self.subTypes):
            # mc.menuItem(label=subType, c=cgmGEN.Callback(self.SetSubType,i))

            if subType not in self.l_subTypesBase and not b_extra:
                mUI.MelMenuItemDiv( self.subTypeMenu, label='Extras..' )
                b_extra = True
            self.subTypeMenuItemList.append( mc.menuItem(label=subType, enable=i!=self.subTypeIndex, c=cgmGEN.Callback(self.SetSubType,i)) ) #mUI.MelMenuItem(self.subTypeMenu, label=subType, c=partial(self.SetSubType,i)) )

        mUI.MelMenuItemDiv( self.subTypeMenu, label='Utils..' )
        mUI.MelMenuItem(self.subTypeMenu, label = 'Create Subtype', c=partial(self.CreateSubType) )
        try:mUI.MelMenuItem(self.subTypeMenu, label="Rename '{}'".format(self.subTypes[self.subTypeIndex]), command= partial(self.rename_below,'subtype') )
        except:mUI.MelMenuItem(self.subTypeMenu, label="Rename subtype", command= partial(self.rename_below,'subtype') )


    #####
    ## Searchable Lists
    #####
    def build_searchable_list(self, parent = None, sc=None, refreshCommand = None, allowMultiSelect=False):
        _margin = 0

        if not parent:
            parent = self

        form = mUI.MelFormLayout(parent,ut='cgmUITemplate')

        rcl = mUI.MelHSingleStretchLayout(form)

        tx = mUI.MelTextField(rcl)
        rcl.setStretchWidget(tx)

        #b = mUI.MelButton(rcl, label='clear', ut='cgmUISubTemplate')
        b = mUI.MelIconButton(rcl,
                              ann='Clear the field',
                              image=os.path.join(_path_imageFolder,'clear.png') ,
                              w=25,h=25)        

        tsl = cgmUI.cgmScrollList(form)
        tsl.allowMultiSelect(allowMultiSelect)
        try:
            tsl(edit=True, hlc=[.5, .5, .5])
        except Exception:
            pass

        if sc != None:
            #tsl.set_selCallBack(sc)
            tsl.cmd_select = sc
            #tsl(edit = True, sc=sc)

        if refreshCommand:
            mUI.MelIconButton(rcl,
                              ann='Recheck the target directory for new data',
                              image=os.path.join(_path_imageFolder,'refresh.png') ,
                              w=25,h=25,
                              c=lambda *a: self._defer_ui(refreshCommand))
            '''
            mUI.MelButton(rcl, label='Refresh', ut='cgmUISubTemplate',
                          ann='Recheck the target directory for new data',
                          c=refreshCommand)'''

        rcl.layout()

        form( edit=True, attachForm=[(rcl, 'top', _margin), (rcl, 'left', _margin), (rcl, 'right', _margin), (tsl, 'bottom', _margin), (tsl, 'right', _margin), (tsl, 'left', _margin)], attachControl=[(tsl, 'top', _margin, rcl)] )

        searchableList = {'formLayout':form, 'scrollList':tsl, 'searchField':tx, 'searchButton':b, 'items':[], 'rows':[], 'selectCommand':sc}

        tx(edit=True, tcc=partial(self.process_search_filter, searchableList))
        b(edit=True, command=partial(self.clear_search_filter, searchableList))

        return searchableList

    def _defer_ui(self, callableObj, *args, **kwargs):
        """Next-idle UI work — avoids Maya/Qt crash when mutating scroll lists from popup menus."""
        mc.evalDeferred(cgmGEN.Callback(callableObj, *args, **kwargs), lp=True)

    def _reload_lists_after_asset_delete(self, *args):
        """Post-delete asset column refresh — must run deferred from popup menus."""
        self.buildAssetForm()
        self.LoadCategoryList()
        self.assetList['scrollList'].selectByIdx(0)
        self.uiFunc_assetList_select()
        self.LoadPreviousSelection()

    def _defer_list_reload_after_delete(self, mode):
        """Defer scroll-list rebuild after delete — avoids Qt crash during QMenu::exec."""
        _reload = {
            'asset': self._reload_lists_after_asset_delete,
            'sets': self.LoadSubTypeList,
            'variation': self.LoadVariationList,
            'version': self.LoadVersionList,
        }
        _fn = _reload.get(mode)
        if _fn:
            self._defer_ui(_fn)

    def _refresh_searchable_display(self, searchableList, progress_bar=None, progress_label=None):
        """BlockScrollList-style refresh: ra, append label, itc per display index."""
        _source = searchableList.get('rows') or []
        _search = ''
        try:
            _search = searchableList['searchField'].getValue() or ''
        except Exception:
            pass
        if _search.strip():
            _displayRows = SCENEUTILS.scene_list_filter_rows(
                _source, _search.lower().strip().split(' '))
        else:
            _displayRows = list(_source)

        sl = searchableList['scrollList']
        _selOn = sl.b_selCommandOn
        sl.b_selCommandOn = False
        _total = len(_displayRows)
        try:
            try:
                sl(e=True, deselectAll=True)
            except Exception:
                pass
            sl(e=True, ra=True)
            sl._items = []
            sl._ml_rows = []

            for i, row in enumerate(_displayRows):
                if progress_bar:
                    if i == 0 or (i + 1) % 25 == 0 or i + 1 == _total:
                        if self._scene_list_progress_update(
                                progress_bar,
                                status='{0} | Building list ({1}/{2})'.format(
                                    progress_label or 'Scene', i + 1, _total),
                                progress=i + 1,
                                max_value=_total):
                            break
                _label = row.alias if row.alias is not None else row.item
                sl.appendDisplayRow(
                    _label,
                    itc=row.itc or SCENEUTILS.SCENE_LIST_ITC_FILE,
                    displayIndex=i + 1,
                )
                sl._ml_rows.append(row)

            sl._items = [r.item for r in sl._ml_rows]
            searchableList['items'] = list(sl._items)
            sl._syncHLCFromSelection(dim=SCENEUTILS.SCENE_LIST_HLC_DIM)
        finally:
            sl.b_selCommandOn = _selOn

    def _scene_list_progress_begin(self, status, max_steps=100):
        try:
            return cgmUI.doStartMayaProgressBar(
                stepMaxValue=max(int(max_steps), 1),
                statusMessage=status,
                interruptableState=True)
        except Exception:
            return None

    def _scene_list_progress_update(self, progress_bar, status=None, progress=None, max_value=None):
        if not progress_bar:
            return False
        try:
            if mc.progressBar(progress_bar, query=True, isCancelled=True):
                return True
            _kw = {}
            if status is not None:
                _kw['status'] = status
            if progress is not None:
                _kw['progress'] = progress
            if max_value is not None:
                _kw['maxValue'] = max(int(max_value), 1)
            cgmUI.progressBar_set(progress_bar, **_kw)
        except Exception:
            pass
        return False

    def _scene_list_progress_end(self, progress_bar):
        if not progress_bar:
            return
        try:
            cgmUI.progressBar_end(progress_bar)
        except Exception:
            try:
                cgmUI.doEndMayaProgressBar(progress_bar)
            except Exception:
                pass

    def _scene_p4_multi_file_progress_begin(self, action_label, total):
        """Maya progress bar for multi-file P4 actions (2+ files)."""
        _total = int(total or 0)
        if _total <= 1:
            return None
        return self._scene_list_progress_begin(
            'P4 {0} | 0/{1}'.format(action_label, _total),
            max_steps=_total)

    def _scene_p4_multi_file_progress_tick(self, progress_bar, action_label, index, total, path):
        if not progress_bar:
            return False
        _name = os.path.basename(path) if path else ''
        _short = _name if len(_name) <= 48 else '...{0}'.format(_name[-45:])
        _idx = int(index or 0)
        _total = max(int(total or 0), 1)
        if _idx == 1 or _idx % 10 == 0 or _idx == _total:
            try:
                mc.refresh()
            except Exception:
                pass
        return self._scene_list_progress_update(
            progress_bar,
            status='P4 {0} | {1}/{2} | {3}'.format(action_label, _idx, _total, _short),
            progress=_idx,
            max_value=_total)

    def _scene_list_file_row_count(self, rows):
        return sum(1 for r in (rows or []) if getattr(r, 'kind', None) == 'file')

    def _scene_list_file_paths(self, rows, search_dir):
        if not search_dir:
            return []
        _paths = []
        for row in rows or []:
            if getattr(row, 'kind', None) != 'file':
                continue
            try:
                _paths.append(os.path.normpath(os.path.join(search_dir, row.item)))
            except Exception:
                continue
        return _paths

    def _scene_list_slow_publish_work(self, rows, search_dir):
        """
        True when list publish is worth a progress bar (uncached P4 fstat or large non-P4 UI).

        Returns (needs_progress, file_count, p4_fstat_misses).
        """
        _file_count = self._scene_list_file_row_count(rows)
        if _file_count < SCENEUTILS.SCENE_LIST_PROGRESS_FILE_THRESHOLD:
            return False, _file_count, 0

        if SCENEUTILS.scene_list_p4_enabled(self.mDat):
            try:
                import cgm.core.lib.perforce as P4UTIL
                _misses = P4UTIL.count_fstat_cache_misses(
                    self._scene_list_file_paths(rows, search_dir))
            except Exception:
                _misses = _file_count
            if _misses > 0:
                return True, _file_count, _misses
            return False, _file_count, 0

        return True, _file_count, 0

    def _publish_searchable_list_rows(self, searchableList, rows, search_dir, progress_label='Scene'):
        """Apply P4 row colors and refresh scroll display; progress bar only on slow work."""
        _needs_progress, _file_count, _p4_misses = self._scene_list_slow_publish_work(rows, search_dir)
        _progress_bar = None
        _max_steps = 100
        if _needs_progress:
            try:
                import cgm.core.lib.perforce as P4UTIL
                _p4_chunks = max(
                    1,
                    (_p4_misses + P4UTIL.FSTAT_QUERY_CHUNK - 1) // P4UTIL.FSTAT_QUERY_CHUNK,
                ) if _p4_misses else 0
            except Exception:
                _p4_chunks = 0
            _max_steps = max(_p4_chunks + _file_count, _file_count, 2)
            _progress_bar = self._scene_list_progress_begin(
                '{0} | {1} files'.format(progress_label, _file_count),
                max_steps=_max_steps)

        def _p4_progress_cb(step, total, status):
            return self._scene_list_progress_update(
                _progress_bar,
                status='{0} | {1} ({2}/{3})'.format(progress_label, status, step, total),
                progress=step,
                max_value=total)

        try:
            if _progress_bar and _p4_misses:
                self._scene_list_progress_update(
                    _progress_bar,
                    status='{0} | Perforce'.format(progress_label),
                    progress=0,
                    max_value=_max_steps)
            self._apply_p4_file_row_colors(
                rows,
                search_dir,
                progress_cb=_p4_progress_cb if _progress_bar and _p4_misses else None)
            if _progress_bar and mc.progressBar(_progress_bar, query=True, isCancelled=True):
                return
            self._push_searchable_rows(
                searchableList,
                rows,
                progress_bar=_progress_bar,
                progress_label=progress_label)
        finally:
            self._scene_list_progress_end(_progress_bar)

    def _apply_p4_file_row_colors(self, rows, search_dir, progress_cb=None):
        """P4 file-row itc when versionControl=perforce and connected."""
        if not rows or not search_dir:
            return rows
        SCENEUTILS.scene_list_apply_p4_file_itc(
            rows,
            path_by_item=lambda r: os.path.join(search_dir, r.item),
            mDat=self.mDat,
            progress_cb=progress_cb,
        )
        return rows

    def _push_searchable_rows(self, searchableList, rows, store=True, progress_bar=None, progress_label=None):
        """Store SceneListRow source list and refresh scroll display."""
        if store:
            searchableList['rows'] = list(rows or [])
        self._refresh_searchable_display(
            searchableList, progress_bar=progress_bar, progress_label=progress_label)

    def _clear_searchable_list(self, searchableList):
        self._push_searchable_rows(searchableList, [])

    def process_search_filter(self, searchableList, *args):
        self._refresh_searchable_display(searchableList)
        searchableList['selectCommand']

    def clear_search_filter(self, searchableList, *args):
        log.debug( "Clearing search filter for %s with search term %s" % (searchableList['scrollList'], searchableList['searchField'].getValue()) )
        searchableList['searchField'].setValue("")
        selected = searchableList['scrollList'].getSelectedItem()
        self._refresh_searchable_display(searchableList)
        if selected:
            searchableList['scrollList'].selectByValue(selected)

    def SetCategory(self, index, *args):
        self.categoryIndex = index

        mc.button( self.categoryBtn, e=True, label=self.category )
        for i,category in enumerate(self.categoryMenuItemList):
            if i == self.categoryIndex:
                self.categoryMenuItemList[i]( e=True, enable=False)
            else:
                self.categoryMenuItemList[i]( e=True, enable=True)

        self.LoadCategoryList(self.directory)

        self.var_categoryStore.setValue(self.categoryIndex)

        try:
            self.l_subTypesBase = [x['n'] for x in self.mDat.assetType_get(self.category).get('content', [{'n':'animation'}])]
        except:
            self.l_subTypesBase = []

        self.subTypes = [c for c in self.l_subTypesBase]        

        # Set SubType -------------------------------------------------------------------------
        try:
            self.subTypes = [x['n'] for x in self.mDat.assetType_get(self.category)['content']]
        except:
            self.subTypes = ['None']

        if self.subTypeBtn(q=True, label=True) in self.subTypes:
            self.subTypeIndex = self.subTypes.index(self.subTypeBtn(q=True, label=True))
        else:
            self.subTypeIndex = min(self.subTypeIndex, len(self.subTypes)-1)

        self.SetSubType(self.subTypeIndex)
        self.buildMenu_subTypes()

    def LoadCategoryList(self, directory="", *args):
        _str_func = 'LoadCategoryList'
        if directory:		
            self.directory = directory

        assetList = []

        categoryDirectory = os.path.join(self.directory, self.category)
        log.debug( log_msg( _str_func, categoryDirectory ) )
        if os.path.exists(categoryDirectory):
            for d in os.listdir(categoryDirectory):
                #for ext in fileExtensions:
                #	if os.path.splitext(f)[-1].lower() == ".%s" % ext :
                if d[0] == '_' or d[0] == '.':
                    continue
                if d.lower() in self.l_dirMask:
                    continue

                charDir = os.path.normpath(os.path.join(categoryDirectory, d))
                if os.path.isdir(charDir):
                    assetList.append(d)

        assetList = sorted(assetList, key=lambda v: v.upper())

        self.UpdateAssetList(assetList)

        self._clear_searchable_list(self.subTypeSearchList)
        self._clear_searchable_list(self.variationList)
        self._clear_searchable_list(self.versionList)

        #self.SaveCurrentSelection()

    def SetSubType(self, index, *args):
        _str_func = 'LoadSubTypeList'
        log.debug(log_start(_str_func))
        self.subTypeIndex = index

        self.subTypeBtn( e=True, label=self.subType )

        self.LoadSubTypeList()
        self.var_subTypeStore.setValue(self.subTypeIndex)

        if not self.b_loadState:
            try:self.var_lastSubtype.setValue(self.subTypes[self.subTypeIndex])
            except:
                log.error("Failed to load subTypes index {}".format(self.subTypeIndex))
                return

        for i,item in enumerate(self.subTypeMenuItemList):
            mc.menuItem(item, e=True, enable= i != self.subTypeIndex)

        if not self.hasSub:
            mc.formLayout( self._subForms[3], e=True, vis=self._subtype_level_has_content())
        elif not self._subtype_level_has_content():
            mc.formLayout( self._subForms[3], e=True, vis=False )
        else:
            mc.formLayout( self._subForms[3], e=True, vis=True )

        mc.formLayout( self._subForms[2], e=True, vis=self.hasVariant and self.hasSub )
        self.buildAssetForm()
        self.uiUpdate_setsButtons()

        #self.LoadPreviousSelection(skip=['asset'])


    def LoadSubTypeList(self, *args):
        _str_func = 'LoadSubTypeList'
        log.debug(log_start(_str_func))


        #if not self.hasSub:
        #    self.LoadVersionList()
            #self._referenceSubTypePUM(e=True, en=True)
        #    return

        #self._referenceSubTypePUM(e=True, en=False)

        subEntries = []
        charDir = None

        if self.path_dir_category and self.assetList['scrollList'].getSelectedItem():
            if not self.hasSub:
                self.LoadVersionList()
                self.uiUpdate_setsButtons()
                return

            charDir = self.path_subType

            if os.path.exists(charDir):
                for d in os.listdir(charDir):
                    animDir = os.path.normpath(os.path.join(charDir, d))
                    if self.showAllFiles:
                        if d.lower() in self.l_dirMask:
                            continue
                        _break = False
                        for chk in ['MRSbatch']:
                            if chk in d:
                                _break = True
                                break
                        if _break:
                            continue

                    if os.path.isdir(animDir):
                        subEntries.append((d, 'dir'))
                    else:
                        subEntries.append((d, 'file'))

        _rows = SCENEUTILS.scene_list_sort_rows(
            SCENEUTILS.scene_list_rows_from_entries(subEntries))
        self._publish_searchable_list_rows(self.subTypeSearchList, _rows, charDir, progress_label='Sets')

        self._clear_searchable_list(self.variationList)
        self._clear_searchable_list(self.versionList)

        self.uiUpdate_setsButtons()

        #self.SaveCurrentSelection()

    def LoadVariationList(self, *args):
        _str_func = 'LoadVariationList'
        log.debug(log_start(_str_func))
        self._version_list_refreshed = False
        """
        if not self.hasSub and self.hasNested:
            self.LoadVersionList()            
            return"""


        if not self.hasVariant:
            log.debug(log_msg(_str_func, "not hasVariant"))
            self._version_list_refreshed = True
            self.LoadVersionList()
            #self.buildAssetForm()
            mc.formLayout( self._subForms[2], e=True, vis=False )
            self.buildAssetForm()            
            return
        else:
            log.debug(log_msg(_str_func, "hasVariant"))            
            mc.formLayout( self._subForms[2], e=True, vis=False )                        
            self.buildAssetForm()


        variationEntries = []
        animationDir = None

        selectedVariation = self.variationList['scrollList'].getSelectedItem()

        self._clear_searchable_list(self.variationList)

        if self.path_set:#self.path_dir_category and self.assetList['scrollList'].getSelectedItem() and self.subTypeSearchList['scrollList'].getSelectedItem():
            animationDir = self.path_set
            log.debug(log_msg(_str_func, "path walk: {}".format(animationDir)))                                    
            if os.path.isfile(animationDir):
                log.debug(log_msg(_str_func, "is file..."))                                        
                return


            if os.path.exists(animationDir):
                for d in self._dir_children_dirs(animationDir):
                    variationEntries.append((d, 'dir'))

                _dirNames = {e[0] for e in variationEntries}
                for f in self._dir_maya_files(animationDir):
                    if f not in _dirNames:
                        variationEntries.append((f, 'file'))

            else:
                log.error(log_msg(_str_func, "path doesn't exist? {}".format(animationDir)))                                    

        _rows = SCENEUTILS.scene_list_sort_rows(
            SCENEUTILS.scene_list_rows_from_entries(variationEntries))
        self._publish_searchable_list_rows(self.variationList, _rows, animationDir, progress_label='Variation')

        if _rows:
            _vsl = self.variationList['scrollList']
            _selOn = _vsl.b_selCommandOn
            _vsl.b_selCommandOn = False
            try:
                _vsl.select_last(selCommand=False)
            finally:
                _vsl.b_selCommandOn = _selOn
            # Auto-select skips selCommand — keep file/dir flags and version column in sync
            _autoPath = self.path_variationDirectory
            self.b_varFile = bool(_autoPath and os.path.isfile(_autoPath))
            if _autoPath and os.path.isdir(_autoPath):
                self._version_list_refreshed = True
                self.LoadVersionList()

        self.uiUpdate_variationButtons()

        #self.variationList['scrollList'].selectByValue(selectedVariation) # if selectedVariation else variationList[0]

        #...hunting loop
        #self.versionList['items'] = []
        #self.versionList['scrollList'].clear()

        #self.LoadVersionList()


        #if len(self.versionList['items']) > 0:
        #    self.versionList['scrollList'].selectByIdx( len(self.versionList['items'])-1 )

        #self.SaveCurrentSelection()

    def LoadVersionList(self, selectValue = None, *args):
        _str_func = 'LoadVersionList'
        log.debug(log_start(_str_func))
        searchList = self.versionList

        if not self.subTypes:#...if we have 
            log.debug(log_msg(_str_func,"no subtypes"))
            searchDir = self.path_asset
        else:
            log.debug(log_msg(_str_func,"subtypes"))            
            #searchDir = os.path.join(self.path_asset if self.path_asset else self.path_dir_category, self.subType if self.subType else "")
            #searchList = self.subTypeSearchList
            #if self.hasSub:
            if self.hasVariant:
                log.debug(log_msg(_str_func,"subtypes"))                            
                searchDir = self.path_variationDirectory
            elif self.hasSub:
                log.debug(log_msg(_str_func,"has sub"))                            
                searchDir = self.path_set
            else:
                searchDir = self.path_subType                
                searchList = self.subTypeSearchList


        log.debug(log_msg(_str_func,"searchDir: {}".format(searchDir)))            
        log.debug(log_msg(_str_func,"searchList: {}".format(searchList)))            


        if not searchDir:
            self._clear_searchable_list(searchList)
            return

        anims = []

        # populate animation info list
        fileExtensions = ['mb', 'ma']

        #log.debug('{0} >> searchDir: {1}'.format(_str_func, searchDir))
        if os.path.exists(searchDir):
            # animDir = (self.path_variationDirectory if self.hasVariant else self.path_set) if self.hasSub else self.path_dir_category

            # if os.path.exists(animDir):
            if not os.path.isdir(searchDir):
                return

            for f in CGMOS.get_lsFromPath(searchDir):
                if f[0] == '_' or f[0] == '.':
                    continue

                if os.path.isdir(os.path.join(searchDir,f)):
                    continue                

                if self.showAllFiles:
                    if f in ['meta']:
                        continue
                    for chk in ['MRSbatch']:
                        _break = False
                        if chk in f:
                            _break = True
                            continue

                    if _break:
                        continue

                    anims.append(f)

                elif os.path.splitext(f)[-1].lower()[1:] in fileExtensions:
                    if self.hasSub:
                        if self.hasVariant:
                            if '{0}_{1}_{2}_'.format(self.selectedAsset, self.selectedSet, self.selectedVariation) in f:
                                anims.append(f)
                        else:
                            if '{0}_{1}_'.format(self.selectedAsset, self.selectedSet) in f:
                                anims.append(f)							
                    else:
                        if '{0}_{1}_'.format(self.selectedAsset, self.subType) in f:
                            anims.append(f)
        _rows = SCENEUTILS.scene_list_sort_rows(
            SCENEUTILS.scene_list_rows_from_entries([(f, 'file') for f in anims]))
        self._publish_searchable_list_rows(searchList, _rows, searchDir, progress_label='Version')
        if anims:
            _vsl = searchList['scrollList']
            _selOn = _vsl.b_selCommandOn
            _vsl.b_selCommandOn = False
            try:
                if selectValue:
                    _vsl.selectByValue(selectValue, selCommand=False)
                else:
                    _lastVersion = self.var_lastVersion.getValue()
                    if _lastVersion and _lastVersion in _vsl._items:
                        _vsl.selectByValue(_lastVersion, selCommand=False)
                    else:
                        _vsl.select_last(selCommand=False)
            finally:
                _vsl.b_selCommandOn = _selOn

        #if anims:
            #searchList['scrollList'].selectByValue(anims[-1])
        #    self.uiFunc_versionList_select(anims[-1])
        #else:
        #    self.SaveCurrentSelection()

    def LoadFile(self, *args):
        """
        print self.versionFile
        if not self.assetList['scrollList'].getSelectedItem():
            log.warning( "No asset selected" )
            return
        if not self.subTypeSearchList['scrollList'].getSelectedItem():
            print "No animation selected"
            return
        if not self.versionList['scrollList'].getSelectedItem() and self.hasSub:
            print "No version selected"
            return
        """
        if VALID.fileOpen(self.versionFile,True,True):
            self.refreshMetaData()

        if cgmGEN.__mayaVersionInt__ > 2021:
            if mc.objExists('sceneConfigurationScriptNode'):
                _before = mc.getAttr('sceneConfigurationScriptNode.before')
                if _before and _before.count('playbackOptions') == 1 and not _before.count(';'):
                    print("sceneConfigurationScriptNode: {}".format(_before))
                    import maya.mel as MEL
                    MEL.eval(_before)

    def uiFuncTF_update(self,tf,datDict, datKey, refreshDisplay = False):
        _str_func = 'uiFuncTF_update'
        log.debug(log_start(_str_func))
        #log.info(tf)
        #log.info(datDict)
        #log.info(datKey)
        #log.info(tf.getValue())
        datDict[datKey] = tf.getValue()
        
        if refreshDisplay:
            self.uiProject_refreshDisplay()
        
    def uiFunc_getOpenFileDict(self,*args):

        _str_func = 'uiFunc_selectOpenFile'
        log.debug(log_start(_str_func))

        _current = mc.file(q=True, sn=True)

        _content = self.directory

        if _content in _current:
            pContent = PATHS.Path(_content)
            pCurrent = PATHS.Path(_current)
            pCurrent.split()
            l_current = pCurrent.split()

            l = []

            for i,n in enumerate(pContent.split()):
                l_current.pop(0)

            #l_current[-1] = '.'.join(l_current[-1].split('.')[:-1])

            pprint.pprint(l_current)

            return
            l_fields = ['asset','sub','variation','version']
            d_fields = {'asset':self.assetList['scrollList'],
                        'sub':self.subTypeSearchList['scrollList'],
                        'variation':self.variationList['scrollList'],
                        'version':self.versionList['scrollList'],
                        }
            int_len = len(l_current)
            for i,n in enumerate(l_current):
                log.debug(cgmGEN.logString_sub(_str_func, "{} | {}".format(i,n)))
                if n == l_current[-1]:
                    self.LoadVersionList()

                if i == 0:
                    if n in self.categoryList:
                        idx = self.categoryList.index(n)
                        self.SetCategory(idx)
                        continue                        
                    else:
                        log.warning('{0} not found in category list'.format(n) )
                        return
                if i == 2:
                    _subName = self._resolveSubTypeLabelFromPathToken(n)
                    if _subName in self.subTypes:
                        self.SetSubType(self.subTypes.index(_subName))
                        continue
                    else:
                        log.warning('{0} not found in subType list'.format(n) )
                        return                    

                for f in l_fields:
                    log.debug(f)
                    if n in d_fields[f]._items:
                        d_fields[f].clearSelection()
                        d_fields[f].selectByValue(n)
                        l_fields.remove(f)
                        log.debug(l_fields)

                        if f == 'sub':
                            self.LoadVariationList()

            return

    def uiFunc_selectOpenFile(self, *args):
        _str_func = 'uiFunc_selectOpenFile'
        log.debug(log_start(_str_func))

        _current = mc.file(q=True, sn=True)

        _content = self.directory

        if _content in _current:
            pContent = PATHS.Path(_content)
            pCurrent = PATHS.Path(_current)
            pCurrent.split()
            l_current = pCurrent.split()

            l = []

            for i,n in enumerate(pContent.split()):
                l_current.pop(0)

            #l_current[-1] = '.'.join(l_current[-1].split('.')[:-1])

            pprint.pprint(l_current)

            l_fields = ['asset','sub','variation','version']
            d_fields = {'asset':self.assetList['scrollList'],
                        'sub':self.subTypeSearchList['scrollList'],
                        'variation':self.variationList['scrollList'],
                        'version':self.versionList['scrollList'],
                        }
            int_len = len(l_current)
            for i,n in enumerate(l_current):
                log.debug(cgmGEN.logString_sub(_str_func, "{} | {}".format(i,n)))
                if n == l_current[-1]:
                    self.LoadVersionList()

                if i == 0:
                    if n in self.categoryList:
                        idx = self.categoryList.index(n)
                        self.SetCategory(idx)
                        continue                        
                    else:
                        log.warning('{0} not found in category list'.format(n) )
                        return
                if i == 2:
                    _subName = self._resolveSubTypeLabelFromPathToken(n)
                    if _subName in self.subTypes:
                        self.SetSubType(self.subTypes.index(_subName))
                        continue
                    else:
                        log.warning('{0} not found in subType list'.format(n) )
                        return                    

                for f in l_fields:
                    log.debug(f)
                    if n in d_fields[f]._items:
                        d_fields[f].clearSelection()
                        d_fields[f].selectByValue(n)
                        l_fields.remove(f)
                        log.debug(l_fields)

                        if f == 'sub':
                            self.LoadVariationList()





            return
            if self.mDat:#Adding the ability to load to Scene                
                for i,d in enumerate(self.mDat.assetDat):
                    k = d.get('n')
                    if k in _dat['split']:
                        idx_split = _dat['split'].index(k)
                        l_temp = _dat['split'][idx_split:]
                        print(('Found: {0} | {1}'.format(k,l_temp)))

                        numItemsFound = len(l_temp)   

                        if numItemsFound > 0:
                            if l_temp[0] in self.categoryList:
                                idx = self.categoryList.index(l_temp[0])
                                self.SetCategory(idx)
                            else:
                                log.warning('{0} not found in category list'.format(l_temp[0]) )
                                return

                        if numItemsFound > 1:
                            self.assetList['scrollList'].clearSelection()
                            self.assetList['scrollList'].selectByValue(l_temp[1])

                        if numItemsFound > 2:
                            _subName = self._resolveSubTypeLabelFromPathToken(l_temp[2])
                            if _subName in self.subTypes:
                                self.SetSubType(self.subTypes.index(_subName))
                            else:
                                log.warning('{0} not found in subType list'.format(l_temp[2]) )
                                return

                        if numItemsFound > 3:
                            self.subTypeSearchList['scrollList'].clearSelection()
                            self.subTypeSearchList['scrollList'].selectByValue(l_temp[3])
                            self.LoadVariationList()

                        if numItemsFound > 4:                  
                            if self.hasVariant:
                                self.variationList['scrollList'].clearSelection()
                                self.variationList['scrollList'].selectByValue(l_temp[4])
                                self.LoadVersionList()
                                if numItemsFound > 5:   
                                    self.versionList['scrollList'].selectByValue(l_temp[5])
                            else:
                                self.versionList['scrollList'].selectByValue(l_temp[4])            


    def SetAnimationDirectory(self, *args):
        basicFilter = "*"
        x = mc.fileDialog2(fileFilter=basicFilter, dialogStyle=2, fm=3)
        if x:
            self.LoadCategoryList(x[0])

    def GetPreviousDirectories(self, *args):
        if type(self.optionVarDirStore.getValue()) is list:
            return self.optionVarDirStore.getValue()
        else:
            return []

    def UpdateAssetList(self, assetList):
        _rows = SCENEUTILS.scene_list_sort_rows(
            SCENEUTILS.scene_list_rows_from_entries([(n, 'dir') for n in assetList]))
        self._push_searchable_rows(self.assetList, _rows)

    # def GetPreviousDirectory(self, *args):
    # 	if self.optionVarLastDirStore.getValue():
    # 		return self.optionVarLastDirStore.getValue()
    # 	else:
    # 		return None

    def SaveCurrentSelection(self, *args):
        _str_func = 'SaveCurrentSelection'

        if self.b_loadState:
            return
        log.debug(log_start(_str_func))

        if self.assetList['scrollList'].getSelectedItem():
            self.var_lastAsset.setValue(self.assetList['scrollList'].getSelectedItem())
        #else:
        #	mc.optionVar(rm=self.var_lastAsset)

        self.var_lastSubtype.setValue(self.subType)

        if self.subTypeSearchList['scrollList'].getSelectedItem():
            self.var_lastSet.setValue(self.subTypeSearchList['scrollList'].getSelectedItem())
        #else:
        #	mc.optionVar(rm=self.var_lastSet)

        if self.variationList['scrollList'].getSelectedItem():
            self.var_lastVariation.setValue(self.variationList['scrollList'].getSelectedItem())
        #else:
        #	mc.optionVar(rm=self.var_lastVariation)

        if self.versionList['scrollList'].getSelectedItem():
            self.var_lastVersion.setValue( self.versionList['scrollList'].getSelectedItem() )
        #else:
        #	mc.optionVar(rm=self.var_lastVersion)

    def LoadPreviousSelection(self, skip = [], *args):
        _str_func = 'LoadPreviousSelection'
        log.debug(log_start(_str_func))

        if 'asset' not in skip:
            val_asset = self.var_lastAsset.getValue()
            if val_asset:
                self._selectByValueIfPresent(self.assetList['scrollList'], val_asset)

        if self.subTypes:
            _last_subType = self.var_lastSubtype.getValue()
            #print "last subType: {}".format(_last_subType)
            try:self.SetSubType(self.subTypes.index(_last_subType))
            except:
                log.warning("Failed to load subtype: {}".format(_last_subType))


            #self.LoadSubTypeList()
            _last_set = self.var_lastSet.getValue()
            #print "last set: {}".format(_last_set)
            if _last_set:
                self._selectByValueIfPresent(self.subTypeSearchList['scrollList'], _last_set)

            if not  self.subTypeSearchList['scrollList'].getSelectedItem():
                self.subTypeSearchList['scrollList'].select_last()


            #self.LoadVariationList()

            _last_variation = self.var_lastVariation.getValue()
            #print "last variation: {}".format(_last_variation)

            if _last_variation:
                self._selectByValueIfPresent(self.variationList['scrollList'], _last_variation)


        #self.LoadVersionList()
        _last_version = self.var_lastVersion.getValue()        
        #print "last version: {}".format(_last_version)
        if _last_version:
            self._selectByValueIfPresent(self.versionList['scrollList'], _last_version)

        if not  self.versionList['scrollList'].getSelectedItem():
            self.versionList['scrollList'].select_last()        

        self.assetMetaData = self.getMetaDataFromFile()	

        log.debug(log_end(_str_func))


    def ClearPreviousDirectories(self, *args):		
        self.optionVarDirStore.clear()
        self.buildMenu_project()

    def CreateAsset(self, *args):
        result = mc.promptDialog(
            title='New Asset',
                    message='Asset Name:',
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            #pprint.pprint(self.l_subTypesBase)
            charName = mc.promptDialog(query=True, text=True)
            charPath = os.path.normpath(os.path.join(self.path_dir_category, charName))
            if not os.path.exists(charPath):
                os.makedirs(charPath)
            for subType in self.l_subTypesBase:
                subTypePath = self._resolve_subType_container_path(charPath, subType)
                if subTypePath and not os.path.exists(subTypePath):
                    os.mkdir(subTypePath)

            self.LoadCategoryList(self.directory)
            self.assetList['scrollList'].selectByValue(charName)
            self.uiFunc_assetList_select()

    def DuplicateAssetStructure(self, *args):
        result = mc.promptDialog(
            title='New Asset',
                    message='Asset Name:',
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            _currentChar = self.assetList['scrollList'].getSelectedItem()
            _path1  = os.path.normpath(os.path.join(self.path_dir_category, _currentChar))


            charName = mc.promptDialog(query=True, text=True)
            _path2 = os.path.normpath(os.path.join(self.path_dir_category, charName))

            CGMOS.dup_dirsBelow(_path1,_path2)

            #if not os.path.exists(charPath):
                #os.mkdir(charPath)
                #for subType in self.l_subTypesBase:
                    #os.mkdir(os.path.normpath(os.path.join(charPath, subType)))

            self.LoadCategoryList(self.directory)
            self.assetList['scrollList'].selectByValue(charName)   
            self.uiFunc_assetList_select()

    def CreateSubType(self, *args):
        if not self.path_asset:
            log.error("No asset selected.")
            return

        result = mc.promptDialog(
            title='New Subtype category'.format(self.subType.capitalize()),
                    message='New SubType Name:'.format(self.subType.capitalize()),
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            subTypeCat = mc.promptDialog(query=True, text=True)
            subTypeDir = self.path_asset #os.path.normpath(os.path.join(self.path_asset, self.subType)) if self.hasSub else os.path.normpath(self.path_asset)
            if not os.path.exists(subTypeDir):
                os.mkdir(subTypeDir)

            subTypePath = os.path.normpath(os.path.join(subTypeDir, subTypeCat))
            if not os.path.exists(subTypePath):
                os.mkdir(subTypePath)

            self.uiFunc_assetList_select()
            self.LoadSubTypeList()

            self.subTypeSearchList['scrollList'].clearSelection()
            self.subTypeSearchList['scrollList'].selectByValue( subTypeCat )



            if not self.hasVariant:
                self.CreateStartingFile()
                self.LoadVersionList()

    def CreateSubTypeRef(self, *args):
        _str_func = 'CreateSubTypeRef'
        filePath = self.versionFile
        if not self.versionFile and not os.path.exists(self.versionFile):
            return False

            #file -import -type "mayaBinary"  -ignoreVersion -mergeNamespacesOnClash false -rpr #"wing_birdBase_03" -options "v=0;"  -pr  -importTimeRange "combine" "D:/Dropbox/mrsMakers_share/content/Demo/wing/scenes/birdBase/wing_birdBase_03.mb";




        versionList = self.versionList if self.hasSub else self.subTypeSearchList
        existingFiles = versionList['items']

        _stok = PU.subtype_file_token(self.subType) if self.subType else self.subType
        _setToken = self._canonicalize_set_token_for_filename(self.subTypeSearchList['scrollList'].getSelectedItem())
        wantedName = "%s_%s" % (self.assetList['scrollList'].getSelectedItem(), _setToken if self.hasSub else _stok)
        if self.hasVariant:
            wantedName = "%s_%s" % (wantedName, self.variationList['scrollList'].getSelectedItem())


        wantedName = "{}Ref.{}".format(wantedName, self.d_tf['general']['mayaFilePref'].getValue())

        log.debug(log_msg(_str_func,"Wanted: {0}".format(wantedName)))

        """
        if len(existingFiles) == 0:
            wantedName = "%s_%02d.mb" % (wantedName, 1)
        else:
            currentFile = mc.file(q=True, loc=True)
            if not os.path.exists(currentFile):
                currentFile = "%s_%02d.mb" % (wantedName, 1)

            baseFile = os.path.split(currentFile)[-1]
            baseName, ext = baseFile.split('.')

            wantedBasename = wantedName #"%s_%s" % (self.assetList['scrollList'].getSelectedItem(), self.subTypeSearchList['scrollList'].getSelectedItem())
            if not wantedBasename in baseName:
                baseName = "%s_%02d" % (wantedBasename, 1)

            noVersionName = '_'.join(baseName.split('_')[:-1])
            versionString = baseName.split('_')[-1]
            versionNumString = re.findall('[0-9]+', versionString)[0]
            versionPrefix = versionString[:versionString.find(versionNumString)]
            version = int(versionNumString)

            versionFiles = []
            versions = []
            for item in existingFiles:
                matchString = "^(%s_%s)[0-9]+\.m." % (noVersionName, versionPrefix)
                pattern = re.compile(matchString)
                if pattern.match(item):
                    versionFiles.append(item)
                    versions.append( int(item.split('.')[0].split('_')[-1].replace(versionPrefix, '')) )

            versions.sort()

            if len(versions) > 0:
                newVersion = versions[-1]+1
            else:
                newVersion = 1

            wantedName = "%s_%s%02d.%s" % (noVersionName, versionPrefix, newVersion, ext)"""

        #new file
        mc.file(f=True,new=True)
        mc.file(filePath, r=True, ignoreVersion=True, gl=True, mergeNamespacesOnClash=False,
                namespace=self.assetList['scrollList'].getSelectedItem())        
        SCENEUTILS.fncMayaSett_do(self,True,True)

        saveLocation = self._version_files_parent_directory()
        if not saveLocation:
            log.error(log_msg(_str_func, "No save directory resolved (match LoadVersionList paths)"))
            return

        log.info(log_msg(_str_func,"Save to: {0}".format(saveLocation)))

        saveFile = os.path.normpath(os.path.join(saveLocation,wantedName) ) 
        
        #Set our base timeline to not be huge
        mc.playbackOptions(minTime=0, maxTime=10)
        mc.playbackOptions(animationStartTime=0, animationEndTime=10)
        
        log.info( "Saving file: %s" % saveFile )
        try:
            saveFile = PATHUTIL.prepare_maya_scene_for_save(saveFile, mDat=self.mDat)
        except PATHUTIL.PathWritePrepareError as err:
            log.error(str(err))
            return
        mc.file( rename=saveFile )
        mc.file( save=True )

        self.LoadVersionList()

        versionList['scrollList'].selectByValue( wantedName )
        self.SaveCurrentSelection()
        self.refreshMetaData()














    def CreateSubAsset(self, *args):
        if not self.path_asset:
            log.error("No asset selected.")
            return

        result = mc.promptDialog(
            title='New {0}'.format(self._subtypeDisplayLabel()),
                    message='{0} Name:'.format(self._subtypeDisplayLabel()),
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            subTypeName = mc.promptDialog(query=True, text=True)
            subTypeDir = self._resolve_subType_container_path(self.path_asset, self.subType)
            if not os.path.exists(subTypeDir):
                os.mkdir(PATHS.get_dir(subTypeDir))

            subTypePath = os.path.normpath(os.path.join(subTypeDir, subTypeName))
            if not os.path.exists(subTypePath):
                os.mkdir(PATHS.get_dir(subTypePath))

            self.buildAssetForm()

            self.LoadSubTypeList()

            self.subTypeSearchList['scrollList'].clearSelection()
            self.subTypeSearchList['scrollList'].selectByValue( subTypeName )



            if not self.hasVariant:
                self.CreateStartingFile()
                self.LoadVersionList()
            else:
                self.form

    def CreateStartingFile(self):
        createPrompt = mc.confirmDialog(
            title='Create?',
                    message='Save Current File Here?',
                        button=['Yes', 'No', 'Make New File'],
                        defaultButton='No',
                                                cancelButton='No',
                                                        dismissString='No')

        if createPrompt == "Yes":
            self.SaveVersion()
        elif createPrompt == 'Make New File':
            mc.file(new=True, f=True)
            self.SaveVersion()
            SCENEUTILS.fncMayaSett_do(self,True,True)


    def CreateVariation(self, *args):
        result = mc.promptDialog(
            title='New Variation',
                    message='Variation Name:',
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            variationName = mc.promptDialog(query=True, text=True)
            variationDir = os.path.normpath( os.path.join(self.path_set, variationName) )
            if not os.path.exists(variationDir):
                os.mkdir(PATHS.get_dir(variationDir))

                self.LoadVariationList()
                self.variationList['scrollList'].clearSelection()
                self.variationList['scrollList'].selectByValue(variationName)

                self.CreateStartingFile()

                self.LoadVersionList()



    def _compute_next_version_save_basename(self):
        """
        Next save filename (with extension) using the same rules as SaveVersion.
        Used to prefill fileDialog2 via startingDirectory full path.
        """
        if not self.path_asset:
            return None
        _fileType = self.d_tf['general']['mayaFilePref'].getValue()
        versionList = self.versionList if self.hasSub else self.subTypeSearchList
        existingFiles = versionList['items']

        if self.hasSub:
            _setToken = self._canonicalize_set_token_for_filename(self.subTypeSearchList['scrollList'].getSelectedItem())
            wantedName = "%s_%s" % (self.assetList['scrollList'].getSelectedItem(), _setToken)
        else:
            wantedName = "%s" % (self.assetList['scrollList'].getSelectedItem())

        log.debug("Wanted name: {}".format(wantedName))

        if self.hasVariant:
            wantedName = "%s_%s" % (wantedName, self.variationList['scrollList'].getSelectedItem())
            log.debug("Has variant name: {}".format(wantedName))

        _fileTok = PU.subtype_file_token(self.subType) if self.subType else ''
        if _fileTok and _fileTok not in ['animation', 'anim']:
            wantedName = "%s_%s" % (wantedName, _fileTok)
            log.debug("Has subTpe name: {}".format(wantedName))

        if len(existingFiles) == 0:
            wantedName = "{0}_0{1}.{2}".format(wantedName, 1, _fileType)
        else:
            print(wantedName)

            wantedBasename = wantedName

            currentFile = mc.file(q=True, loc=True)

            if not os.path.exists(currentFile):
                log.debug("Doesn't exist: {}".format(currentFile))
                baseFile = versionList['scrollList'].getSelectedItem()
                baseName, ext = baseFile.split('.')

                if not wantedBasename in baseName:
                    baseName = "%s_%02d" % (wantedBasename, 1)

            elif 'cat' == 'dog':
                currentFile = os.path.split(currentFile)[-1]
                baseName, ext = currentFile.split('.')

            else:
                baseName = wantedBasename

            if '_BUILD' in baseName:
                baseName = baseName.replace('_BUILD', '')

            if baseName != wantedBasename:
                noVersionName = '_'.join(baseName.split('_')[:-1])
                versionString = baseName.split('_')[-1]
                try:
                    versionNumString = re.findall('[0-9]+', versionString)[0]
                except Exception:
                    versionNumString = ''
                try:
                    versionPrefix = versionString[:versionString.find(versionNumString)]
                except Exception:
                    versionPrefix = ''
            else:
                noVersionName = baseName
                versionPrefix = ''

            versionFiles = []
            versions = []
            for item in existingFiles:
                matchString = "^(%s_%s)[0-9]+\.m." % (noVersionName, versionPrefix)
                pattern = re.compile(matchString)
                if pattern.match(item):
                    versionFiles.append(item)
                    versions.append(int(item.split('.')[0].split('_')[-1].replace(versionPrefix, '')))

            versions.sort()

            if len(versions) > 0:
                newVersion = versions[-1] + 1
            else:
                newVersion = 1

            wantedName = "%s_%s%02d.%s" % (noVersionName, versionPrefix, newVersion, _fileType)

        return wantedName

    def _save_here_suggested_stub(self):
        """
        Basename for Save Maya here dialog: same logical name as the next SaveVersion file,
        but without the trailing version digits and without .ma/.mb (user picks type in dialog).
        """
        full = self._compute_next_version_save_basename()
        if not full:
            return None
        base, _ext = os.path.splitext(full)
        parts = base.split('_')
        if not parts:
            return None
        last = parts[-1]
        m = re.match(r'^([^0-9]*)(\d+)$', last)
        if not m:
            return base
        prefix_before_digits, _digits = m.groups()
        stub = '_'.join(parts[:-1])
        if prefix_before_digits:
            stub = '%s_%s' % (stub, prefix_before_digits)
        return stub or base

    def SaveVersion(self, *args):
        _str_func = 'SaveVersion'
        log.debug("|{}| >>...".format(_str_func))

        if not self.path_asset:
            log.error("No asset selected")
            return
        _saveTypeDict = {'ma':'mayaAscii', 'mb':'mayaBinary'}
        _fileType = self.d_tf['general']['mayaFilePref'].getValue()
        _saveType = _saveTypeDict[_fileType]
        wantedName = self._compute_next_version_save_basename()
        if not wantedName:
            log.error("No asset selected")
            return

        saveLocation = self._version_files_parent_directory()
        if not saveLocation:
            log.error("{0} | No save directory resolved (match LoadVersionList paths)".format(_str_func))
            return

        saveFile = os.path.normpath(os.path.join(saveLocation, wantedName) ) 
        log.info( "Saving file: %s" % saveFile )
        try:
            saveFile = PATHUTIL.prepare_maya_scene_for_save(saveFile, mDat=self.mDat)
        except PATHUTIL.PathWritePrepareError as err:
            log.error(str(err))
            return
        mc.file( rename=saveFile )
        mc.file( save=True, typ = _saveType)

        self.LoadVersionList(wantedName)
        #versionList['scrollList'].selectByValue( wantedName )
        self.SaveCurrentSelection()

        #self.uiFunc_selectOpenFile()
        self.refreshMetaData()


    def OpenDirectory(self, path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            log.warning("Path not found - {0}".format(path))

        
    def LoadProject(self, path, *args):
        if not os.path.exists(path):
            mel.eval('warning "No Project Set"')
            return

        #Clear our previous data...
        for mSet in [self.assetList,self.subTypeSearchList,self.variationList,self.versionList]:
            mSet['scrollList'].clear()
        self.pathProject = None
        self.directory = ''
        self.path_current = ''
        self.exportDirectory = ''
        #----------------------------------------------------
        
        
        mDat = Project.data(filepath=path)


        #We want to check our project version at open
        if mDat.d_project.get('mayaVersionCheck'):
            _expected = float(mDat.d_project.get('mayaVersion'))
            _current = cgmGEN.__mayaVersion__

            if _current != _expected:
                _name = mDat.d_project.get('name')            
                log.warning("Expected maya version not found. Current: {} | Expected: {}".format(_current,_expected))
                result = mc.confirmDialog(title="Open Anyway?",
                                          message= "Project '{}' Expects another maya version: {}. \n Open anyway?".format(_name, _expected),
                                          icon='warning',
                                          button=['Open',"Cancel"],
                                          defaultButton='Save',
                                          cancelButton='Cancel',
                                          dismissString='Cancel')
                if result == "Cancel":
                    return log.warning("Project load aborted: {0}".format(path))


        
        self.b_loadState = True
        self.report_lastSelection()        
    
        self.mDat = mDat
    
        #print"{}...".format('projectload')                
        PROJECT.uiProject_load(self, path=path)
        #self.report_lastSelection()
    
        self.var_lastProject.setValue( path )
        
        self.uiProject_refreshDisplay()
        
        self.uiFunc_projectDirtyState(False)
        
        
        self.b_loadState = False
        self.path_current = os.path.normpath(path)
        self.mPathList_recent.append_recent(path)
        
        self.d_tf['general']['dirMask'](edit=True, cc = cgmGEN.Callback(self.uiFuncTF_update,self.d_tf['general']['dirMask'], self.mDat.d_project, 'dirMask', refreshDisplay=True))
        
        return
    
        #Moving this stuff...
        

        #print"{}...".format('refresh')        
        self.uiProject_refreshDisplay()
        #self.report_lastSelection()

        #print"{}...".format('dirty')        
        self.uiFunc_projectDirtyState(False)
        #self.report_lastSelection()

        #print"{}...".format('previous')                
        #self.LoadPreviousSelection()
        #self.report_lastSelection()

        self.b_loadState = False
        self.path_current = os.path.normpath(path)
        self.mPathList_recent.append_recent(path)
        return




        _bgColor = self.v_bgc
        try:
            _bgColor = self.mDat.d_colors['project']
        except Exception as err:
            log.warning("No project color stored | {0}".format(err))

        try:self.uiImage_ProjectRow(edit=True, bgc = _bgColor)
        except Exception as err:
            log.warning("Failed to set bgc: {0} | {1}".format(_bgColor,err))

        try:
            vTmp = [MATH.Clamp(1.5 * v,None,2.0) for v in _bgColor]
            vLite = [MATH.Clamp(1.7 * v, .5, 1.0) for v in _bgColor]


            self._detailsToggleBtn(edit=True, bgc=vTmp)
            self._projectToggleBtn(edit=True, bgc=vTmp)
            #self.uiScrollList_dirContent(edit=True, bgc = vLite)
            self.uiScrollList_dirContent.v_hlc = vLite
            self.uiScrollList_dirExport.v_hlc = vLite

        except Exception as err:
            log.error("Load project color set error | {0}".format(err))

            self._detailsToggleBtn(edit=True, bgc=(1.0, .445, .08))
            self._projectToggleBtn(edit=True, bgc=(1.0, .445, .08))
            self.uiScrollList_dirContent(edit=True, hlc = (1.0, .445, .08))
            self.uiScrollList_dirExport(edit=True, hlc = (1.0, .445, .08))

        d_userPaths = self.mDat.userPaths_get()

        if not d_userPaths.get('content'):
            log.error("No Content path found")
            return False

        if not d_userPaths.get('export'):
            log.error("No Export path found")
            self.exportDirectoryTF(edit=1,en=False)

            #return False
        else:
            self.exportDirectory = d_userPaths['export']
            self.exportDirectoryTF(edit=1,en=True)            
            self.exportDirectoryTF.setValue( self.exportDirectory )



        if os.path.exists(d_userPaths['content']):
            self.var_lastProject.setValue( path )
            self.LoadCategoryList(d_userPaths['content'])

            # self.optionVarExportDirStore.setValue( self.exportDirectory )

            self.l_categoriesBase = self.mDat.assetTypes_get() if self.mDat.assetTypes_get() else self.mDat.d_structure.get('assetTypes', [])
            self.categoryList = [c for c in self.l_categoriesBase]
            self.categoryList  = sorted(self.categoryList , key=lambda v: v.upper())

            for i,f in enumerate(os.listdir(self.directory)):
                if os.path.isfile(os.path.join(self.directory, f)):
                    continue
                if f in self.l_categoriesBase:
                    continue

                self.categoryList.append(f)

            if d_userPaths.get('image') and os.path.exists(d_userPaths.get('image')):
                self.uiImage_Project.setImage(d_userPaths['image'])
            else:
                _imageFailPath = os.path.join(mImagesPath.asFriendly(),
                                              'cgm_project_{0}.png'.format(self.mDat.d_project.get('type','unity')))
                self.uiImage_Project.setImage(_imageFailPath)

            self.buildMenu_category()


            mc.workspace( d_userPaths['content'], openWorkspace=True )

            self.assetMetaData = {}

            self.LoadOptions()
        else:
            mel.eval('error "Project path does not exist"')


        self.uiScrollList_dirContent.mDat = self.mDat
        self.uiScrollList_dirContent.rebuild( self.directory)
        self.uiScrollList_dirExport.rebuild( self.exportDirectory)


        log.debug( "+"*100)
        log.debug(self.d_tf['exportOptions']['removeNameSpace'].getValue())

        return True

    def rename_below(self, mode = 'asset',*args):
        _str_func = 'rename_below'
        #remember, you need to pass a path up
        if mode == 'asset':
            sourceName = self.selectedAsset
            path = self.path_dir_category
        elif mode == 'set':
            sourceName = self.selectedSet
            path = self.path_subType            
        elif mode == 'subtype':
            sourceName = self.selectedSet
            path = self.path_asset
        elif mode in ['variant','variation']:
            sourceName = self.selectedVariation
            path = self.path_set
        else:
            return log.warning(log_msg(_str_func, "Unknown mode: {0}".format(mode)))        



        result = mc.promptDialog(
            title='Rename {0}'.format(mode.capitalize()),
                    text = sourceName,
                    message='Current: {0} | Enter Name:'.format(sourceName),
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')


        if result == 'OK':
            newName = mc.promptDialog(query=True, text=True)
            if not newName:
                return log.warning(log_msg(_str_func, "Must enter a new name"))
            if newName == sourceName:
                return log.warning(log_msg(_str_func, "Must have a different name"))

            #_path = r"{0}".format(path)
            #print os.path.normpath(path)
            log.info(log_msg(_str_func,"Current: {0}".format(sourceName)))
            log.info(log_msg(_str_func,"New: {0}".format(newName)))
            log.info(log_msg(_str_func,"path: {0}".format(path)))


            #Do the rename pass...
            try:
                CGMOS.rename_filesInPath(path, sourceName, newName)
            except Exception as err:
                log.error(err)
                return log.warning(log_msg(_str_func, "Error on rename. Check if you have one of the directories open as file browsers"))

            #Cat...
            self.LoadCategoryList(self.directory)
            if mode == 'asset':
                self.assetList['scrollList'].selectByValue( newName )
            else:
                self.assetList['scrollList'].selectByValue( self.var_lastAsset.getValue() )

            #Sub...
            self.LoadSubTypeList()

            if mode == 'subtype':
                self.subTypeSearchList['scrollList'].selectByValue( newName )
            else:
                self.subTypeSearchList['scrollList'].selectByValue( self.var_lastSet.getValue() )


            #Var...
            self.LoadVariationList()
            if mode in ['variant','variation']:
                self.variationList['scrollList'].selectByValue( newName )

            elif self.var_lastVariation.getValue():
                self.variationList['scrollList'].selectByValue( self.var_lastVariation.getValue() )


            #Version...
            self.LoadVersionList()

            if self.var_lastVersion.getValue():
                self.versionList['scrollList'].selectByValue( self.var_lastVersion.getValue() )            









    def RenameAsset(self, *args):
        result = mc.promptDialog(
            title='Rename Object',
                    message='Enter Name:',
                    button=['OK', 'Cancel'],
                    defaultButton='OK',
                            cancelButton='Cancel',
                                        dismissString='Cancel')

        if result == 'OK':
            newName = mc.promptDialog(query=True, text=True)
            log.info( 'Renaming %s to %s' % (self.selectedAsset, newName) )

            originalAssetName = self.selectedAsset

            # rename animations (subtype container may be Rigs/geo via path_subType)
            _subRoot = self.path_subType or os.path.normpath(os.path.join(self.path_asset, self.subType))
            for animation in os.listdir(_subRoot):
                for variation in os.listdir(os.path.join(_subRoot, animation)):
                    for version in os.listdir(os.path.join(_subRoot, animation, variation)):
                        if originalAssetName in version:
                            originalPath = os.path.join(_subRoot, animation, variation, version)
                            newPath = os.path.join(_subRoot, animation, variation, version.replace(originalAssetName, newName))
                            os.rename(originalPath, newPath)

            # rename rigs
            for baseFile in os.listdir(self.path_asset):
                if os.path.isfile(os.path.join(self.path_asset, baseFile)):
                    if originalAssetName in baseFile:
                        originalPath = os.path.join(self.path_asset, baseFile)
                        newPath = os.path.join(self.path_asset, baseFile.replace(originalAssetName, newName))
                        os.rename(originalPath, newPath)

            # rename folder
            os.rename(self.path_asset, self.path_asset.replace(originalAssetName, newName))

            self.LoadCategoryList(self.directory)
            self.assetList['scrollList'].selectByValue( newName )

            self.LoadSubTypeList()

            if self.var_lastSet.getValue():
                self.subTypeSearchList['scrollList'].selectByValue( self.var_lastSet.getValue() )

            self.LoadVariationList()

            if self.var_lastVariation.getValue():
                self.variationList['scrollList'].selectByValue( self.var_lastVariation.getValue() )

            self.LoadVersionList()

            if self.var_lastVersion.getValue():
                self.versionList['scrollList'].selectByValue( self.var_lastVersion.getValue() )



    def OpenAssetDirectory(self, *args):
        if self.selectedAsset:
            self.OpenDirectory( os.path.join(self.path_dir_category, self.selectedAsset) )
        else:
            self.OpenDirectory( self.path_dir_category )

    def uiPath_mayaOpen(self,path=None):
        _res = mc.fileDialog2(fileMode=1, dir=path)
        if _res:
            log.warning("Opening: {0}".format(_res[0]))
            mc.file(_res[0], o=True, f=True, pr=True)
            return
        log.warning("Unknown path: {0}".format(path))

    def _fileListScrollForMode(self, mode):
        if mode == 'sets':
            return self.subTypeSearchList['scrollList']
        if mode == 'variation':
            return self.variationList['scrollList']
        if mode == 'version':
            return self.versionList['scrollList']
        return None

    def _resolveFileListDeletePath(self, list_key, item_name):
        if not item_name:
            return None
        try:
            if list_key == 'sets':
                _subRoot = self.path_subType or self._resolve_subType_container_path(self.path_asset, self.subType)
                if not _subRoot:
                    return None
                return os.path.normpath(os.path.join(_subRoot, item_name))
            if list_key == 'variation':
                _path_set = self.path_set
                if not _path_set:
                    return None
                return os.path.normpath(os.path.join(_path_set, item_name))
            if list_key == 'version':
                _parent = self._version_files_parent_directory()
                if not _parent:
                    return None
                return os.path.normpath(os.path.join(_parent, item_name))
        except Exception as err:
            log.debug(log_msg('_resolveFileListDeletePath', err))
        return None

    def uiFunc_deleteSelectedInList(self,mode = None):
        _str_func = 'uiFunc_deleteSelectedInList'
        log.debug("|{}| >>...{}".format(_str_func,mode))

        _scroll = self._fileListScrollForMode(mode)
        _items = _scroll.getSelectedItems() if _scroll else []
        if len(_items) > 1:
            _paths = []
            for _item in _items:
                _path = self._resolveFileListDeletePath(mode, _item)
                if _path and (os.path.isfile(_path) or os.path.isdir(_path)):
                    _paths.append(_path)
            if not _paths:
                return log.warning(log_msg(_str_func, 'no valid paths for bulk delete'))
            _result = mc.confirmDialog(
                title='Remove Selected',
                message='Delete {0} selected item(s)?'.format(len(_paths)),
                button=['OK', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
            if _result != 'OK':
                return
            for _path in _paths:
                try:
                    if os.path.isfile(_path):
                        os.remove(_path)
                    elif os.path.isdir(_path):
                        import shutil
                        shutil.rmtree(_path)
                    log.warning("deleted: {0}".format(_path))
                except Exception as err:
                    log.error(log_msg(_str_func, 'delete failed | {0} | {1}'.format(_path, err)))
            self._defer_list_reload_after_delete(mode)
            return

        if mode == 'asset':
            _path =  self.path_asset
        elif mode == 'sets':
            _path = self.path_set
            #cgmUI.cgmScrollList(parent).getSelectedItem

            _file = self.subTypeSearchList['scrollList'].getSelectedItem()
            if _file and not _path.endswith(_file):
                _path = os.path.join(_path,_file)

        elif mode == 'variation':
            _path = self.path_variationDirectory
        elif mode == 'version':
            _path = self.versionFile

        log.debug(_path)

        #reload(cgmUI)
        if cgmUI.uiPrompt_removeDir(_path):
            self._defer_list_reload_after_delete(mode)




    def uiPath_mayaSaveTo(self, path=None, defaultFilename=None):
        _filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb);;"
        if path and defaultFilename:
            _start = os.path.normpath(os.path.join(path, defaultFilename))
        else:
            _start = path
        _fdKw = dict(fileMode=0, dialogStyle=2, fileFilter=_filter)
        if _start:
            _fdKw['startingDirectory'] = _start
        _res = mc.fileDialog2(**_fdKw)
        if _res:
            log.warning("Saving: {0}".format(_res[0]))
            try:
                _save_path = PATHUTIL.prepare_maya_scene_for_save(_res[0], mDat=self.mDat)
            except PATHUTIL.PathWritePrepareError as err:
                log.error(str(err))
                return
            mc.file(rename=_save_path)
            mc.file(save=1)        

    def uiPath_mayaOpen_subType(self):
        _path = self.path_subType or os.path.normpath(os.path.join(self.path_asset, self.subType))
        if _path and os.path.exists(_path):
            self.uiPath_mayaOpen( _path)
        else:
            log.warning("SubType path doesn't exist")

    def uiPath_mayaSaveTo_sets(self, *args):
        _path = self.path_subType or os.path.normpath(os.path.join(self.path_asset, self.subType))
        if _path:
            _suggest = self._save_here_suggested_stub()
            self.uiPath_mayaSaveTo(_path, defaultFilename=_suggest)
        else:
            log.warning("SubType path doesn't exist")

    def uiPath_mayaOpen_variant(self):

        if self.path_variationDirectory:
            self.uiPath_mayaOpen( self.path_variationDirectory )
        else:
            log.warning("Variation path doesn't exist")


    def uiPath_mayaSaveTo_variant(self):
        if self.path_variationDirectory:
            _suggest = self._save_here_suggested_stub()
            self.uiPath_mayaSaveTo(self.path_variationDirectory, defaultFilename=_suggest)
        else:
            log.warning("Variation path doesn't exist")

    def uiPath_mayaSaveTo_version(self, *args):
        if self.path_versionDirectory:
            _suggest = self._save_here_suggested_stub()
            self.uiPath_mayaSaveTo(self.path_versionDirectory, defaultFilename=_suggest)
        else:
            log.warning("Version path doesn't exist")

    def OpenSubTypeDirectory(self, *args):
        if self.path_asset:
            _p = self.path_subType or os.path.normpath(os.path.join(self.path_asset, self.subType))
            self.OpenDirectory(_p)
        else:
            log.warning("Asset path doesn't exist")

    def OpenVariationDirectory(self, *args):
        self.OpenDirectory(self.path_set)

    def OpenVersionDirectory(self, *args):
        _p = self.path_versionDirectory
        if not _p:
            log.warning("Version path doesn't exist")
            return
        self.OpenDirectory(_p)

    def ReferenceFile(self, *args):
        #if not self.assetList['scrollList'].getSelectedItem():
            #log.debug( "No asset selected" )
            #return
        #if not self.subTypeSearchList['scrollList'].getSelectedItem():
            #log.debug( "No animation selected" )
            #return
        #if not self.versionList['scrollList'].getSelectedItem():
            #log.debug( "No version selected" )
            #return

        filePath = self.versionFile
        if self.versionFile and os.path.exists(self.versionFile):
            _namespace = self.assetList['scrollList'].getSelectedItem() if self.hasSub else self.selectedAsset
            mc.file(filePath, r=True, ignoreVersion=True, namespace=CORESTRING.stripInvalidChars(_namespace))
        else:
            log.info( "Version file doesn't exist" )

    def ImportFile(self, *args):
        filePath = self.versionFile
        if self.versionFile and os.path.exists(self.versionFile):
            #file -import -type "mayaBinary"  -ignoreVersion -mergeNamespacesOnClash false -rpr #"wing_birdBase_03" -options "v=0;"  -pr  -importTimeRange "combine" "D:/Dropbox/mrsMakers_share/content/Demo/wing/scenes/birdBase/wing_birdBase_03.mb";

            mc.file(filePath, i=True, ignoreVersion=True,
                    mergeNamespacesOnClash=False,
                    importTimeRange = 'combine')
        else:
            log.info( "Version file doesn't exist" )
    def file_replace(self, *args):
        filePath = self.versionFile
        if self.versionFile and os.path.exists(self.versionFile):
            result = mc.confirmDialog(title='Confirm',
                                      message= "Replacing : {0}".format(self.versionFile),
                                      button=['OK', 'Cancel'],
                                      defaultButton='OK',
                                      cancelButton='Cancel',
                                      dismissString='Cancel')
            if result != 'OK':
                log.error(">> Replacing Cancelled | {0}".format(filePath))
                return False

            mc.file(rn=os.path.normpath(filePath))
            #mc.file(filePath)
            mc.file(s=True)
        else:
            log.info( "Version file doesn't exist" )



    def ExportSelection(self, mode='content', *args):
        """
        Export the currently selected objects using Maya's built-in Export Selection command.
        Preloads the export dialog with the appropriate directory context based on mode.
        
        Args:
            mode (str): Determines the starting directory for the export dialog
                - 'variant': Uses self.path_variationDirectory
                - 'version': Uses self.path_versionDirectory
                - 'sets': Uses subtype/set folder (same as Save Maya here on sets list)
                - 'content': Uses self.mDat.userPaths_get()['content'] (default)
        """
        if not mc.ls(sl=True):
            log.warning("Export Selection | No objects selected")
            return
        
        log.info("ExportSelection - mode: {0}".format(mode))
        
        # Determine the export directory based on mode
        if mode == 'variant':
            export_dir = self.path_variationDirectory
        elif mode == 'version':
            export_dir = self.path_versionDirectory
        elif mode == 'sets':
            export_dir = self.path_subType or os.path.normpath(os.path.join(self.path_asset, self.subType))
        else:  # mode == 'content' or any other value
            export_dir = self.mDat.userPaths_get()['content']
        
        # Temporarily change working directory for ExportSelection command
        if export_dir and os.path.exists(export_dir):
            # Check if "workspace.mel" exists in the export directory before setting the project path
            workspace_mel_path = os.path.join(export_dir, "workspace.mel")
            had_workspace_mel = os.path.isfile(workspace_mel_path)
            
            original_dir = os.getcwd()
            try:
                log.info("Changing directory to: {0}".format(export_dir))
                mel.eval('setProject "{0}";'.format(VALID.sanitize_filepath(export_dir)))
                mel.eval('ExportSelection')
            finally:
                log.info("Restoring original directory: {0}".format(self.mDat.userPaths_get()['content']))
                mel.eval('setProject "{0}";'.format(self.mDat.userPaths_get()['content']))
            
            # If we didn't have a workspace.mel at that path but now do, delete it
            if not had_workspace_mel and os.path.isfile(workspace_mel_path):
                try:
                    os.remove(workspace_mel_path)
                    log.debug("Deleted newly created workspace.mel at: {0}".format(workspace_mel_path))
                except Exception as e:
                    log.warning("Failed to delete temporary workspace.mel at {0}: {1}".format(workspace_mel_path, e))
        else:
            # Fallback to standard ExportSelection if directory doesn't exist
            mel.eval('ExportSelection')

    # Legacy method names for backward compatibility - these now call the unified method
    def ExportSelection_variant(self, *args):
        """Legacy method - now calls ExportSelection with mode='variant'"""
        self.ExportSelection(mode='variant')

    def ExportSelection_version(self, *args):
        """Legacy method - now calls ExportSelection with mode='version'"""
        self.ExportSelection(mode='version')

    def ExportSelection_sets(self, *args):
        """Export with starting directory matching sets/subtype column (no-hasSub layout)."""
        self.ExportSelection(mode='sets')

    def UpdateAssetTSLPopup(self, *args):
        ''''''
        _str_func = 'UpdateAssetTSLPopup'
        log.debug(_str_func)

        self.assetTSLpum.clear()

        renameAssetMB = mUI.MelMenuItem(self.assetTSLpum, label="Rename Asset", command= partial(self.rename_below,'asset') )
        mUI.MelMenuItem(self.assetTSLpum, label="Duplicate Structure", command=self.DuplicateAssetStructure,en=1)

        openInExplorerMB = mUI.MelMenuItem(self.assetTSLpum, label="Open In Explorer", command=self.OpenAssetDirectory )
        openMayaFileHereMB = mUI.MelMenuItem(self.assetTSLpum, label="Open In Maya", command=lambda *a:self.uiPath_mayaOpen( os.path.join(self.path_dir_category, self.selectedAsset) ))

        for item in self.assetRigMenuItemList:
            mc.deleteUI(item, menuItem=True)
        for item in self.assetReferenceRigMenuItemList:
            mc.deleteUI(item, menuItem=True)

        self.assetRigMenuItemList = []
        self.assetReferenceRigMenuItemList = []

        openMB = mUI.MelMenuItem(self.assetTSLpum, label="Open", subMenu=True )
        referenceMB = mUI.MelMenuItem(self.assetTSLpum, label="Reference", subMenu=True )

        hasItems = False

        for subType in self.subTypes:
            if self.HasSub(self.category, subType):
                continue

            try:subDir = os.path.join(self.path_asset, subType)
            except:
                continue
            if not os.path.exists(subDir):
                continue

            assetList = ASSET.AssetDirectory(subDir, self.selectedAsset, subType)
            directoryList = assetList.GetFullPaths()

            if len(assetList.versions) == 0:
                continue

            openRigMB = mUI.MelMenuItem(openMB, label=subType, subMenu=True )
            referenceRigMB = mUI.MelMenuItem(referenceMB, label=subType, subMenu=True )

            #rigPath = #os.path.normpath(os.path.join(self.path_asset, "%s_rig.mb" % self.assetList['scrollList'].getSelectedItem() ))
            #if len(assetList.versions) > 0:
                #mc.menuItem( openRigMB, e=True, enable=True )
                #mc.menuItem( referenceRigMB, e=True, enable=True )
            #else:
                #mc.menuItem( openRigMB, e=True, enable=False )
                #mc.menuItem( referenceRigMB, e=True, enable=False )

            for i,rig in enumerate(assetList.versions):
                item = mUI.MelMenuItem( openRigMB, l=rig,
                                        c = cgmGEN.Callback(self.OpenRig,directoryList[i]))
                self.assetRigMenuItemList.append(item)

                item = mUI.MelMenuItem( referenceRigMB, l=rig,
                                        c = cgmGEN.Callback(self.ReferenceRig,directoryList[i], self.selectedAsset))
                self.assetReferenceRigMenuItemList.append(item)

                hasItems = True

        if not hasItems:
            openMB(e=True, en=False)
            referenceMB(e=True, en=False)


        self.refreshAssetListMB = mUI.MelMenuItem(self.assetTSLpum, label="Refresh", command=lambda *a: self._defer_ui(self.LoadCategoryList))

        self.ml_p4_options_dir_asset = []
        if self._scene_p4_menu_active():
            mUI.MelMenuItemDiv(self.assetTSLpum, label='Perforce')
            self.ml_p4_options_dir_asset.append(mUI.MelMenuItem(
                self.assetTSLpum,
                label='Get Latest Revision',
                ann='p4 sync — update asset directory and all files below to head revision',
                c=cgmGEN.Callback(self._defer_ui, self.uiFunc_p4_sync_asset_directory),
                en=self._scene_p4_connected()))

        mUI.MelMenuItemDiv(self.assetTSLpum)
        mUI.MelMenuItem(self.assetTSLpum, label="Delete",
                         command=lambda *a: self._defer_ui(cgmGEN.Callback(self.uiFunc_deleteSelectedInList, 'asset')))


    def _scene_p4_menu_active(self):
        try:
            return bool(PU.project_uses_perforce(self.mDat))
        except Exception:
            return False

    def _scene_p4_connected(self):
        try:
            import cgm.core.lib.perforce as P4UTIL
            return bool(P4UTIL.query_project_p4_status().get('connected'))
        except Exception:
            return False

    def _scene_p4_connection(self):
        import cgm.core.lib.perforce as P4UTIL
        return P4UTIL.resolve_connection()

    def _scene_p4_selected_file_path(self):
        try:
            _path = self.versionFile
            if _path and os.path.isfile(_path):
                return os.path.normpath(_path)
        except Exception:
            pass
        return None

    def _scene_p4_file_paths_for_list(self, list_key):
        scroll = self._fileListScrollForMode(list_key)
        if not scroll:
            return []
        paths = []
        for item in scroll.getSelectedItems() or []:
            path = self._resolveFileListDeletePath(list_key, item)
            if path and os.path.isfile(path):
                paths.append(os.path.normpath(path))
        return paths

    def _scene_p4_action_paths(self, list_key=None):
        if list_key:
            return self._scene_p4_file_paths_for_list(list_key)
        _path = self._scene_p4_selected_file_path()
        return [_path] if _path else []

    def _scene_p4_selected_dir_path(self, list_key):
        scroll = self._fileListScrollForMode(list_key)
        if not scroll:
            return None
        item = scroll.getSelectedItem()
        if not item:
            return None
        path = self._resolveFileListDeletePath(list_key, item)
        if path and os.path.isdir(path):
            return os.path.normpath(path)
        return None

    def _scene_p4_project_root_path(self):
        try:
            _path = self.directory
        except Exception:
            _path = None
        if not _path:
            try:
                _path = (self.d_userPaths or {}).get('content')
            except Exception:
                _path = None
        if _path:
            _path = os.path.normpath(_path)
            if os.path.isdir(_path):
                return _path
        return None

    def _scene_p4_project_root_in_client(self):
        _path = self._scene_p4_project_root_path()
        if not _path or not self._scene_p4_connected():
            return False
        try:
            import cgm.core.lib.perforce as P4UTIL
            _user, _client = self._scene_p4_connection()
            return bool(P4UTIL.is_under_client(_path, p4_user=_user, p4_client=_client))
        except Exception:
            return False

    def _scene_p4_project_root_sync_enabled(self):
        return bool(self._scene_p4_project_root_in_client())

    def _refresh_p4_menu_items(self, item_lists, file_selected):
        _en = bool(file_selected and self._scene_p4_connected())
        for _lst in item_lists or []:
            for _item in _lst or []:
                try:
                    _item(edit=True, en=_en)
                except Exception:
                    pass

    def _refresh_p4_dir_menu_items(self, item_lists, dir_selected):
        _en = bool(dir_selected and self._scene_p4_connected())
        for _lst in item_lists or []:
            for _item in _lst or []:
                try:
                    _item(edit=True, en=_en)
                except Exception:
                    pass

    def _resolve_p4_search_dir_for_column(self, list_key):
        if list_key == 'sets':
            if self.path_dir_category and self.assetList['scrollList'].getSelectedItem():
                if not self.hasSub:
                    return self._version_files_parent_directory()
                return self.path_subType
            return None
        if list_key == 'variation':
            _path = self.path_set
            if not _path or os.path.isfile(_path):
                return None
            return _path
        if list_key == 'version':
            return self._version_files_parent_directory()
        return None

    def _invalidate_p4_directory_for_column(self, list_key):
        try:
            import cgm.core.lib.perforce as P4UTIL
            _dir = self._resolve_p4_search_dir_for_column(list_key)
            if _dir:
                P4UTIL.invalidate_fstat_directory(_dir)
        except Exception as err:
            log.debug(log_msg('_invalidate_p4_directory_for_column', err))

    def _refreshSubTypeList(self, *args):
        self._invalidate_p4_directory_for_column('sets')
        self.LoadSubTypeList()

    def _refreshVariationList(self, *args):
        self._invalidate_p4_directory_for_column('variation')
        self.LoadVariationList()

    def _refreshVersionList(self, *args):
        self._invalidate_p4_directory_for_column('version')
        self.LoadVersionList()

    def _scene_p4_active_list_key(self):
        if self.b_subFile:
            return 'sets'
        if self.b_varFile:
            return 'variation'
        return 'version'

    def _scene_p4_reload_lists(self):
        if self.b_subFile:
            self.LoadSubTypeList()
        elif self.b_varFile:
            self.LoadVariationList()
        else:
            self.LoadVersionList()

    def _scene_p4_after_write(self, list_key=None):
        if list_key is None:
            list_key = self._scene_p4_active_list_key()
        _reload = {
            'sets': self.LoadSubTypeList,
            'variation': self.LoadVariationList,
            'version': self.LoadVersionList,
        }
        _fn = _reload.get(list_key)
        if _fn:
            self._defer_ui(_fn)
        else:
            self._defer_ui(self._scene_p4_reload_lists)

    def _scene_p4_after_sync_directory(self, sync_path=None, list_key=None):
        """Refresh dir scroll lists and file-list columns after p4 directory sync."""
        def _reload():
            if getattr(self, 'uiScrollList_dirContent', None) and self.directory:
                try:
                    self.uiScrollList_dirContent.rebuild(self.directory)
                except Exception as err:
                    log.debug(log_msg('_scene_p4_after_sync_directory', 'dirContent | {0}'.format(err)))
            if getattr(self, 'uiScrollList_dirExport', None) and getattr(self, 'exportDirectory', None):
                try:
                    self.uiScrollList_dirExport.rebuild(self.exportDirectory)
                except Exception as err:
                    log.debug(log_msg('_scene_p4_after_sync_directory', 'dirExport | {0}'.format(err)))

            if list_key in ('project', 'content'):
                log.info(
                    'P4 Get Latest: content sync complete — use column Refresh for P4 file colors')
                return

            if not self.assetList['scrollList'].getSelectedItem():
                return

            if list_key == 'version':
                self._refreshVersionList()
                return

            if list_key == 'variation':
                self._refreshVariationList()
                return

            self._refreshSubTypeList()
            if self.subTypeSearchList['scrollList'].getSelectedItem() and not self.b_subFile:
                self.uiFunc_subTypeList_select()

        self._defer_ui(_reload)

    def _append_p4_file_menu(self, pum, track_list, list_key=None):
        track_list[:] = []
        if not self._scene_p4_menu_active():
            return
        mUI.MelMenuItemDiv(pum, label='Perforce')
        _paths = self._scene_p4_action_paths(list_key)
        _en = bool(self._scene_p4_connected() and _paths)
        track_list.append(mUI.MelMenuItem(
            pum,
            label='Get',
            ann='p4 sync — get latest revision for selected file(s)',
            c=cgmGEN.Callback(self.uiFunc_p4_sync_file, list_key),
            en=_en))
        track_list.append(mUI.MelMenuItem(
            pum, label='Checkout',
            ann='p4 edit — open depot file(s) for edit',
            c=cgmGEN.Callback(self.uiFunc_p4_checkout_file, list_key),
            en=_en))
        track_list.append(mUI.MelMenuItem(
            pum, label='Add',
            ann='p4 add — mark local file(s) for add to depot',
            c=cgmGEN.Callback(self.uiFunc_p4_add_file, list_key),
            en=_en))
        track_list.append(mUI.MelMenuItem(
            pum, label='Revert',
            ann='p4 revert — discard local open on selected file(s)',
            c=cgmGEN.Callback(self.uiFunc_p4_revert_file, list_key),
            en=_en))
        track_list.append(mUI.MelMenuItem(
            pum, label='Submit',
            ann='p4 submit — add/checkout if needed, then submit selected file(s)',
            c=cgmGEN.Callback(self.uiFunc_p4_submit_file, list_key),
            en=_en))
        track_list.append(mUI.MelMenuItem(
            pum, label='Shelve',
            ann='p4 shelve — add/checkout if needed, then shelf selected file(s)',
            c=cgmGEN.Callback(self.uiFunc_p4_shelve_file, list_key),
            en=_en))

    def _append_p4_get_latest_dir_item(self, pum, track_list, callback, enabled=False):
        track_list[:] = []
        if not self._scene_p4_menu_active():
            return
        track_list.append(mUI.MelMenuItem(
            pum,
            label='Get Latest Revision',
            ann='p4 sync — update directory and all files below to head revision',
            c=cgmGEN.Callback(self._defer_ui, callback),
            en=bool(enabled and self._scene_p4_connected())))

    def _p4_sync_progress_tick(self, progress_bar, count, line):
        _short = line if len(line) <= 72 else '...{0}'.format(line[-69:])
        if count == 1 or count % 100 == 0:
            try:
                mc.refresh()
            except Exception:
                pass
        return self._scene_list_progress_update(
            progress_bar,
            status='P4 Get Latest | {0} file(s) | {1}'.format(count, _short),
            progress=count,
            max_value=max(100, count + 1))

    def _uiFunc_p4_sync_directory_path(self, path, list_key=None):
        _path = os.path.normpath(path) if path else None
        if not _path or not os.path.isdir(_path):
            return log.warning('P4 Get Latest: no directory selected')
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Get Latest: set user/client in cgmP4')
        log.info('P4 Get Latest: {0}'.format(_path))
        _msg = 'Sync directory and all files below to head revision?\n\n{0}'.format(_path)
        if list_key in ('project', 'content'):
            _msg += (
                '\n\nLarge trees can take several minutes. '
                'Progress updates in the status bar; use column Refresh for P4 colors after.')
        _result = mc.confirmDialog(
            title='Get Latest Revision',
            message=_msg,
            button=['Sync', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel',
        )
        if _result != 'Sync':
            return
        self._defer_ui(self._uiFunc_p4_sync_directory_run, _path, list_key)

    def _uiFunc_p4_sync_directory_run(self, path, list_key=None):
        _path = os.path.normpath(path) if path else None
        if not _path or not os.path.isdir(_path):
            return
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Get Latest: set user/client in cgmP4')
        import cgm.core.lib.perforce as P4UTIL
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

        _progress_bar = self._scene_list_progress_begin(
            'P4 Get Latest | starting...', max_steps=100)
        try:
            mc.refresh()
        except Exception:
            pass

        def _progress_cb(count, line):
            return self._p4_sync_progress_tick(_progress_bar, count, line)

        def _cancel_cb():
            if not _progress_bar:
                return False
            try:
                return mc.progressBar(_progress_bar, query=True, isCancelled=True)
            except Exception:
                return False

        _large_tree = list_key in ('project', 'content')
        log.info('P4 Get Latest: syncing {0}...'.format(_path))
        try:
            _res = P4UTIL.sync_directory(
                _path,
                p4_user=_user,
                p4_client=_client,
                progress_cb=_progress_cb,
                cancel_cb=_cancel_cb,
                progress_every=50 if _large_tree else 25,
                fstat_cache_flush='all' if _large_tree else 'directory',
            )
        finally:
            self._scene_list_progress_end(_progress_bar)

        if _res.get('cancelled'):
            return log.warning('P4 Get Latest: cancelled — {0}'.format(_path))
        if _res.get('ok'):
            _count = _res.get('fileCount') or len(_res.get('lines') or [])
            _lines = _res.get('lines') or []
            if any('no file' in l.lower() for l in _lines):
                log.info('P4 Get Latest: no files updated — {0}'.format(_path))
            else:
                log.info('P4 synced directory: {0} ({1} file(s))'.format(_path, _count))
            self._scene_p4_after_sync_directory(_path, list_key=list_key)
        else:
            log.error('P4 sync directory failed: {0} | {1}'.format(
                _path, _res.get('stderr') or 'unknown'))

    def uiFunc_p4_checkout_file(self, list_key=None, *args):
        _paths = self._scene_p4_action_paths(list_key)
        if not _paths:
            return log.warning('P4 Checkout: no file selected')
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Checkout: set user/client in cgmP4')
        import cgm.core.lib.perforce as P4UTIL
        if len(_paths) == 1:
            _path = _paths[0]
            _stat = P4UTIL.query_file_status(_path, p4_user=_user, p4_client=_client)
            if _stat.get('checkedOut'):
                return log.warning('P4 Checkout: file already opened — {0}'.format(_path))
            if _stat.get('notInClient'):
                return log.warning('P4 Checkout: file not in client view — {0}'.format(_path))
            if not _stat.get('onDepot'):
                return log.warning('P4 Checkout: file not on depot — use Add — {0}'.format(_path))
            if _stat.get('outOfDate'):
                return log.warning('P4 Checkout: file out of date — sync first — {0}'.format(_path))
            if _stat.get('lockedByOther'):
                return log.error('P4 Checkout: locked or open elsewhere — {0}'.format(_path))
            _result = mc.confirmDialog(
                title='Checkout file',
                message='Checkout file for edit?\n\n{0}'.format(_path),
                button=['Checkout', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
            if _result != 'Checkout':
                return
            P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
            _res = P4UTIL.edit(_path, p4_user=_user, p4_client=_client)
            if _res.get('ok'):
                log.info('P4 checkout: {0}'.format(_path))
                self._scene_p4_after_write(list_key=list_key)
            else:
                log.error('P4 checkout failed: {0}'.format(_res.get('stderr') or 'unknown'))
            return
        _result = mc.confirmDialog(
            title='Checkout files',
            message='Checkout {0} files for edit?'.format(len(_paths)),
            button=['Checkout', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel',
        )
        if _result != 'Checkout':
            return
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
        _ok = 0
        _cancelled = False
        _progress_bar = self._scene_p4_multi_file_progress_begin('Checkout', len(_paths))
        try:
            for _idx, _path in enumerate(_paths, 1):
                if self._scene_p4_multi_file_progress_tick(
                        _progress_bar, 'Checkout', _idx, len(_paths), _path):
                    _cancelled = True
                    break
                _stat = P4UTIL.query_file_status(_path, p4_user=_user, p4_client=_client)
                if _stat.get('checkedOut'):
                    log.warning('P4 Checkout: skip — already opened — {0}'.format(_path))
                    continue
                if _stat.get('notInClient'):
                    log.warning('P4 Checkout: skip — not in client view — {0}'.format(_path))
                    continue
                if not _stat.get('onDepot'):
                    log.warning('P4 Checkout: skip — not on depot — {0}'.format(_path))
                    continue
                if _stat.get('outOfDate'):
                    log.warning('P4 Checkout: skip — out of date — {0}'.format(_path))
                    continue
                if _stat.get('lockedByOther'):
                    log.error('P4 Checkout: skip — locked elsewhere — {0}'.format(_path))
                    continue
                _res = P4UTIL.edit(_path, p4_user=_user, p4_client=_client)
                if _res.get('ok'):
                    _ok += 1
                    log.info('P4 checkout: {0}'.format(_path))
                else:
                    log.error('P4 checkout failed: {0} | {1}'.format(_path, _res.get('stderr') or 'unknown'))
        finally:
            self._scene_list_progress_end(_progress_bar)
        if _cancelled:
            log.warning('P4 Checkout: cancelled — {0}/{1} file(s) done'.format(_ok, len(_paths)))
        if _ok:
            self._scene_p4_after_write(list_key=list_key)
        log.info('P4 checkout complete: {0}/{1} file(s)'.format(_ok, len(_paths)))

    def uiFunc_p4_add_file(self, list_key=None, *args):
        _paths = self._scene_p4_action_paths(list_key)
        if not _paths:
            return log.warning('P4 Add: no file selected')
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Add: set user/client in cgmP4')
        import cgm.core.lib.perforce as P4UTIL
        if len(_paths) == 1:
            _path = _paths[0]
            _stat = P4UTIL.query_file_status(_path, p4_user=_user, p4_client=_client)
            if _stat.get('checkedOut'):
                return log.warning('P4 Add: file already opened — {0}'.format(_path))
            if _stat.get('notInClient'):
                return log.warning('P4 Add: file not in client view — {0}'.format(_path))
            if _stat.get('onDepot') and not _stat.get('notOnDepot'):
                return log.warning('P4 Add: file already on depot — use Checkout — {0}'.format(_path))
            if _stat.get('lockedByOther'):
                return log.error('P4 Add: locked or open elsewhere — {0}'.format(_path))
            _result = mc.confirmDialog(
                title='Add file',
                message='Mark file for add to depot?\n\n{0}'.format(_path),
                button=['Add', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
            if _result != 'Add':
                return
            P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
            _res = P4UTIL.add(_path, p4_user=_user, p4_client=_client)
            if _res.get('ok'):
                log.info('P4 add: {0}'.format(_path))
                self._scene_p4_after_write(list_key=list_key)
            else:
                log.error('P4 add failed: {0}'.format(_res.get('stderr') or 'unknown'))
            return
        _result = mc.confirmDialog(
            title='Add files',
            message='Mark {0} files for add to depot?'.format(len(_paths)),
            button=['Add', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel',
        )
        if _result != 'Add':
            return
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
        _ok = 0
        _cancelled = False
        _progress_bar = self._scene_p4_multi_file_progress_begin('Add', len(_paths))
        try:
            for _idx, _path in enumerate(_paths, 1):
                if self._scene_p4_multi_file_progress_tick(
                        _progress_bar, 'Add', _idx, len(_paths), _path):
                    _cancelled = True
                    break
                _stat = P4UTIL.query_file_status(_path, p4_user=_user, p4_client=_client)
                if _stat.get('checkedOut'):
                    log.warning('P4 Add: skip — already opened — {0}'.format(_path))
                    continue
                if _stat.get('notInClient'):
                    log.warning('P4 Add: skip — not in client view — {0}'.format(_path))
                    continue
                if _stat.get('onDepot') and not _stat.get('notOnDepot'):
                    log.warning('P4 Add: skip — already on depot — {0}'.format(_path))
                    continue
                if _stat.get('lockedByOther'):
                    log.error('P4 Add: skip — locked elsewhere — {0}'.format(_path))
                    continue
                _res = P4UTIL.add(_path, p4_user=_user, p4_client=_client)
                if _res.get('ok'):
                    _ok += 1
                    log.info('P4 add: {0}'.format(_path))
                else:
                    log.error('P4 add failed: {0} | {1}'.format(_path, _res.get('stderr') or 'unknown'))
        finally:
            self._scene_list_progress_end(_progress_bar)
        if _cancelled:
            log.warning('P4 Add: cancelled — {0}/{1} file(s) done'.format(_ok, len(_paths)))
        if _ok:
            self._scene_p4_after_write(list_key=list_key)
        log.info('P4 add complete: {0}/{1} file(s)'.format(_ok, len(_paths)))

    def uiFunc_p4_revert_file(self, list_key=None, *args):
        _paths = self._scene_p4_action_paths(list_key)
        if not _paths:
            return log.warning('P4 Revert: no file selected')
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Revert: set user/client in cgmP4')
        if len(_paths) == 1:
            _path = _paths[0]
            _result = mc.confirmDialog(
                title='Revert file',
                message='Revert opened file?\n\n{0}'.format(_path),
                button=['Revert', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
        else:
            _result = mc.confirmDialog(
                title='Revert files',
                message='Revert {0} file(s)?'.format(len(_paths)),
                button=['Revert', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
        if _result != 'Revert':
            return
        import cgm.core.lib.perforce as P4UTIL
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
        _ok = 0
        _cancelled = False
        _progress_bar = self._scene_p4_multi_file_progress_begin('Revert', len(_paths))
        try:
            for _idx, _path in enumerate(_paths, 1):
                if self._scene_p4_multi_file_progress_tick(
                        _progress_bar, 'Revert', _idx, len(_paths), _path):
                    _cancelled = True
                    break
                _res = P4UTIL.revert(_path, p4_user=_user, p4_client=_client)
                if _res.get('ok'):
                    _ok += 1
                    log.info('P4 reverted: {0}'.format(_path))
                else:
                    log.error('P4 revert failed: {0} | {1}'.format(_path, _res.get('stderr') or 'unknown'))
        finally:
            self._scene_list_progress_end(_progress_bar)
        if _cancelled:
            log.warning('P4 Revert: cancelled — {0}/{1} file(s) done'.format(_ok, len(_paths)))
        if _ok:
            self._scene_p4_after_write(list_key=list_key)
        if len(_paths) > 1:
            log.info('P4 revert complete: {0}/{1} file(s)'.format(_ok, len(_paths)))

    def uiFunc_p4_sync_file(self, list_key=None, *args):
        _paths = self._scene_p4_action_paths(list_key)
        if not _paths:
            return log.warning('P4 Sync: no file selected')
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 Sync: set user/client in cgmP4')
        if len(_paths) == 1:
            _path = _paths[0]
            _result = mc.confirmDialog(
                title='Sync file',
                message='Sync file to head revision?\n\n{0}'.format(_path),
                button=['Sync', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
        else:
            _result = mc.confirmDialog(
                title='Sync files',
                message='Sync {0} file(s) to head revision?'.format(len(_paths)),
                button=['Sync', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
        if _result != 'Sync':
            return
        import cgm.core.lib.perforce as P4UTIL
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
        _ok = 0
        _cancelled = False
        _progress_bar = self._scene_p4_multi_file_progress_begin('Sync', len(_paths))
        try:
            for _idx, _path in enumerate(_paths, 1):
                if self._scene_p4_multi_file_progress_tick(
                        _progress_bar, 'Sync', _idx, len(_paths), _path):
                    _cancelled = True
                    break
                _res = P4UTIL.sync_file(_path, p4_user=_user, p4_client=_client)
                if _res.get('ok'):
                    _ok += 1
                    log.info('P4 synced: {0}'.format(_path))
                else:
                    log.error('P4 sync failed: {0} | {1}'.format(_path, _res.get('stderr') or 'unknown'))
        finally:
            self._scene_list_progress_end(_progress_bar)
        if _cancelled:
            log.warning('P4 Sync: cancelled — {0}/{1} file(s) done'.format(_ok, len(_paths)))
        if _ok:
            self._scene_p4_after_write(list_key=list_key)
        if len(_paths) > 1:
            log.info('P4 sync complete: {0}/{1} file(s)'.format(_ok, len(_paths)))

    def uiFunc_p4_sync_directory(self, list_key=None, *args):
        if not list_key:
            return log.warning('P4 Get Latest: no list context')
        _path = self._scene_p4_selected_dir_path(list_key)
        self._uiFunc_p4_sync_directory_path(_path, list_key=list_key)

    def uiFunc_p4_sync_version_directory(self, *args):
        self._uiFunc_p4_sync_directory_path(
            self._version_files_parent_directory(),
            list_key='version')

    def uiFunc_p4_sync_asset_directory(self, *args):
        if not self.selectedAsset or not self.path_dir_category:
            return log.warning('P4 Get Latest: no asset selected')
        _path = os.path.normpath(os.path.join(self.path_dir_category, self.selectedAsset))
        self._uiFunc_p4_sync_directory_path(_path, list_key='asset')

    def uiFunc_p4_sync_project_root(self, *args):
        _path = self._scene_p4_project_root_path()
        if not _path:
            return log.warning('P4 Get: no project content path')
        if not self._scene_p4_project_root_in_client():
            return log.warning(
                'P4 Get: project path not in Perforce client view — {0}'.format(_path))
        self._uiFunc_p4_sync_directory_path(_path, list_key='project')

    def _scene_p4_classify_open_paths(self, paths, user, client):
        """Split selected paths into ready, prepare (add/checkout), and blocked."""
        import cgm.core.lib.perforce as P4UTIL
        _ready = []
        _prepare = []
        _blocked = []
        for _path in paths or []:
            _stat = P4UTIL.query_file_status(_path, p4_user=user, p4_client=client)
            _action = P4UTIL.submit_prepare_action(_stat)
            if _action is None:
                _ready.append((_path, _stat.get('change') or 'default'))
            elif _action == 'add':
                _prepare.append((_path, 'add'))
            elif _action == 'checkout':
                _prepare.append((_path, 'checkout'))
            else:
                _blocked.append((_path, _action))
        return _ready, _prepare, _blocked

    def _scene_p4_confirm_open_action_blocked(self, ready, prepare, blocked, action_label='Submit'):
        """Confirm when some selected files are blocked."""
        if not blocked:
            return True
        _lines = []
        for _path, _reason in blocked:
            _lines.append('{0}\n  — {1}'.format(_path, _reason))
        _skip_msg = '\n\n'.join(_lines)
        _actionable = len(ready) + len(prepare)
        if not _actionable:
            mc.confirmDialog(
                title='P4 {0}'.format(action_label),
                message='No selected files can be {0}d:\n\n{1}'.format(
                    action_label.lower(), _skip_msg),
                button=['OK'],
                defaultButton='OK',
            )
            log.warning('P4 {0}: no eligible files in selection'.format(action_label))
            return False
        _result = mc.confirmDialog(
            title='P4 {0}'.format(action_label),
            message=(
                'Some selected files cannot be {0}d:\n\n{1}\n\n'
                'Continue with {2} file(s)?'.format(
                    action_label.lower(), _skip_msg, _actionable)
            ),
            button=['Continue', 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel',
        )
        if _result != 'Continue':
            log.info('P4 {0}: cancelled — {1} blocked file(s)'.format(
                action_label, len(blocked)))
            return False
        for _path, _reason in blocked:
            log.warning('P4 {0}: skip — {1} — {2}'.format(action_label, _reason, _path))
        return True

    def _scene_p4_prepare_open_files(self, prepare_list, user, client, action_label='Submit'):
        """Run p4 add/edit before submit/shelve. Returns [(path, change), ...] for successes."""
        import cgm.core.lib.perforce as P4UTIL
        _prepared = []
        for _path, _action in prepare_list or []:
            if _action == 'add':
                _res = P4UTIL.add(_path, p4_user=user, p4_client=client)
            elif _action == 'checkout':
                _res = P4UTIL.edit(_path, p4_user=user, p4_client=client)
            else:
                continue
            if not _res.get('ok'):
                log.error(
                    'P4 prepare for {0} ({1}) failed: {2} — {3}'.format(
                        action_label.lower(), _action, _path, _res.get('stderr') or 'unknown'))
                continue
            _stat = P4UTIL.query_file_status(_path, p4_user=user, p4_client=client, force=True)
            if _stat.get('checkedOut'):
                _prepared.append((_path, _stat.get('change') or 'default'))
                log.info('P4 prepare for {0} ({1}): {2}'.format(
                    action_label.lower(), _action, _path))
            else:
                log.error(
                    'P4 prepare for {0}: {1} succeeded but file not opened — {2}'.format(
                        action_label.lower(), _action, _path))
        return _prepared

    def _scene_p4_open_prepare_note(self, prepare_list, action_past='submitted'):
        """One-line summary for submit/shelve description dialog."""
        _add = sum(1 for _, _a in prepare_list if _a == 'add')
        _checkout = sum(1 for _, _a in prepare_list if _a == 'checkout')
        _parts = []
        if _add:
            _parts.append('{0} will be added to depot'.format(_add))
        if _checkout:
            _parts.append('{0} will be checked out'.format(_checkout))
        if not _parts:
            return ''
        return '{0}, then {1}.'.format(' and '.join(_parts), action_past)

    def _scene_p4_open_action_prompt_message(self, action_label, ready, prepare, paths):
        """Build promptDialog message before add/checkout."""
        _parts = []
        _past = {'Submit': 'submitted', 'Shelve': 'shelved'}.get(
            action_label, '{0}ed'.format(action_label.lower()))
        _prepare_note = self._scene_p4_open_prepare_note(prepare, action_past=_past)
        if _prepare_note:
            _parts.append(_prepare_note)
        if len(paths) == 1:
            _parts.append(os.path.basename(paths[0]))
        else:
            _parts.append('{0} {1} selected file(s).'.format(action_label, len(paths)))
        return '\n\n'.join(_parts) or 'Enter {0} description.'.format(_action_lower)

    def _scene_p4_prompt_open_description(self, title, message, user, client, ready=None,
                                          action_label='Submit'):
        import cgm.core.lib.perforce as P4UTIL
        _default_text = None
        if ready:
            _changes = {str(_change).lower() for _, _change in ready}
            if len(_changes) == 1:
                _default_text = P4UTIL.query_change_description(
                    ready[0][1], p4_user=user, p4_client=client) or None
        _desc = cgmUI.uiPrompt_getValue(
            title=title,
            message=message,
            text=_default_text,
            style='text',
        )
        if _desc is None:
            return None
        _desc = _desc.strip()
        if not _desc:
            log.warning('P4 {0}: description required'.format(action_label))
            return None
        return _desc

    def _scene_p4_run_open_file_action(self, list_key, action_label, p4_paths_fn, title):
        """Shared submit/shelve orchestration for Scene file popups."""
        _paths = self._scene_p4_action_paths(list_key)
        if not _paths:
            return log.warning('P4 {0}: no file selected'.format(action_label))
        _user, _client = self._scene_p4_connection()
        if not _user or not _client:
            return log.warning('P4 {0}: set user/client in cgmP4'.format(action_label))
        import cgm.core.lib.perforce as P4UTIL
        _ready, _prepare, _blocked = self._scene_p4_classify_open_paths(_paths, _user, _client)
        if not self._scene_p4_confirm_open_action_blocked(
                _ready, _prepare, _blocked, action_label=action_label):
            return
        _actionable_paths = [_path for _path, _change in _ready] + [
            _path for _path, _action in _prepare]
        if not _actionable_paths:
            return log.warning('P4 {0}: no files to {1}'.format(
                action_label, action_label.lower()))
        _msg = self._scene_p4_open_action_prompt_message(
            action_label, _ready, _prepare, _actionable_paths)
        _desc = self._scene_p4_prompt_open_description(
            title, _msg, _user, _client, ready=_ready, action_label=action_label)
        if not _desc:
            return
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
        _prepared = self._scene_p4_prepare_open_files(
            _prepare, _user, _client, action_label=action_label)
        if _prepare and not _prepared:
            return log.error(
                'P4 {0}: prepare failed — no files opened for {1}'.format(
                    action_label, action_label.lower()))
        _opened = list(_ready) + list(_prepared)
        if not _opened:
            return log.warning('P4 {0}: no files to {1}'.format(
                action_label, action_label.lower()))
        _by_change = {}
        for _path, _change in _opened:
            _key = str(_change).lower()
            if _key not in _by_change:
                _by_change[_key] = {'change': _change, 'paths': []}
            _by_change[_key]['paths'].append(_path)
        _groups = list(_by_change.values())
        _ok = 0
        _cancelled = False
        _progress_bar = None
        _past = {'Submit': 'submitted', 'Shelve': 'shelved'}.get(
            action_label, action_label.lower())
        if len(_groups) > 1:
            _progress_bar = self._scene_p4_multi_file_progress_begin(action_label, len(_groups))
        try:
            for _idx, _grp in enumerate(_groups, 1):
                _grp_paths = _grp['paths']
                _change = _grp['change']
                if _progress_bar and self._scene_p4_multi_file_progress_tick(
                        _progress_bar, action_label, _idx, len(_groups), _grp_paths[0]):
                    _cancelled = True
                    break
                _res = p4_paths_fn(
                    _grp_paths, change=_change, description=_desc,
                    p4_user=_user, p4_client=_client)
                if _res.get('ok'):
                    _ok += len(_grp_paths)
                    for _path in _grp_paths:
                        log.info('P4 {0}: {1}'.format(_past, _path))
                else:
                    log.error('P4 {0} failed: {1}'.format(
                        action_label.lower(), _res.get('stderr') or 'unknown'))
        finally:
            if _progress_bar:
                self._scene_list_progress_end(_progress_bar)
        if _cancelled:
            log.warning('P4 {0}: cancelled — {1}/{2} file(s) done'.format(
                action_label, _ok, len(_opened)))
        if not _ok and _prepare:
            _prepared_paths = {_path for _path, _change in _prepared}
            for _path, _action in _prepare:
                if _action != 'add' or _path not in _prepared_paths:
                    continue
                _rev = P4UTIL.revert(_path, p4_user=_user, p4_client=_client)
                if _rev.get('ok'):
                    log.warning(
                        'P4 {0}: reverted add after failure — {1}'.format(
                            action_label, _path))
                else:
                    log.error(
                        'P4 {0}: revert after failure failed — {1}: {2}'.format(
                            action_label, _path, _rev.get('stderr') or 'unknown'))
        if _ok:
            self._scene_p4_after_write(list_key=list_key)
        elif _prepare:
            self._scene_p4_after_write(list_key=list_key)
        if _ok or not _cancelled:
            log.info('P4 {0} complete: {1}/{2} file(s)'.format(
                _past, _ok, len(_opened)))

    def uiFunc_p4_submit_file(self, list_key=None, *args):
        import cgm.core.lib.perforce as P4UTIL
        self._scene_p4_run_open_file_action(
            list_key, 'Submit', P4UTIL.submit_paths, 'Submit to Perforce')

    def uiFunc_p4_shelve_file(self, list_key=None, *args):
        import cgm.core.lib.perforce as P4UTIL
        self._scene_p4_run_open_file_action(
            list_key, 'Shelve', P4UTIL.shelve_paths, 'Shelve to Perforce')

    def _fileListPopupDelete(self, popupAttr, sendToProjectAttr=None):
        if sendToProjectAttr:
            _sendMenu = getattr(self, sendToProjectAttr, None)
            if _sendMenu is not None:
                self.d_subPops.pop(_sendMenu, None)
            setattr(self, sendToProjectAttr, None)
        pum = getattr(self, popupAttr, None)
        if not pum:
            return
        try:
            pum.clear()
            pum.delete()
        except Exception as err:
            log.debug(log_msg('_fileListPopupDelete', err))
        setattr(self, popupAttr, None)

    def _buildFileListPopupMulti(self, pum, list_key, scrollList):
        """Reduced RMB menu when multiple file rows are selected (Builder block-list pattern)."""
        _labels = {'sets': 'Set', 'variation': 'Variant', 'version': 'Version'}
        _count = len(scrollList.getSelectedItems() or [])
        mUI.MelMenuItem(
            pum,
            label='        {0} ({1} selected)'.format(_labels.get(list_key, 'File'), _count),
            en=False)
        mUI.MelMenuItemDiv(pum, label='Selected')

        _batch = mUI.MelMenuItem(pum, label='To Queue as:', subMenu=True)
        for t in ['export', 'rig', 'cutscene']:
            mUI.MelMenuItem(_batch, label=t.capitalize(), command=partial(self.AddSelectedToExportQueue, t))

        mUI.MelMenuItem(pum, label='Delete',
                         command=lambda *a: self._defer_ui(cgmGEN.Callback(self.uiFunc_deleteSelectedInList, list_key)))

        self.ml_p4_options_multi = []
        self._append_p4_file_menu(pum, self.ml_p4_options_multi, list_key=list_key)

        mUI.MelMenuItemDiv(pum, label='List')
        _refresh = {
            'sets': self._refreshSubTypeList,
            'variation': self._refreshVariationList,
            'version': self._refreshVersionList,
        }
        _refreshFn = _refresh.get(list_key)
        if _refreshFn:
            mUI.MelMenuItem(pum, label='Refresh', command=lambda *a: self._defer_ui(_refreshFn))

    def _rebuildFileListPopup(self, scrollList, popupAttr, buildSingleFunc, list_key, sendToProjectAttr=None):
        """Delete and recreate file-list popup from current selection (Builder pattern)."""
        self._fileListPopupDelete(popupAttr, sendToProjectAttr=sendToProjectAttr)
        _items = scrollList.getSelectedItems()
        if not _items:
            return None
        _pmc = self._d_fileListPopupPmc.get(popupAttr)
        _kw = {'button': 3}
        if _pmc:
            _kw['pmc'] = cgmGEN.Callback(_pmc)
        pum = mUI.MelPopupMenu(scrollList, **_kw)
        setattr(self, popupAttr, pum)
        if len(_items) > 1:
            self._buildFileListPopupMulti(pum, list_key, scrollList)
        else:
            buildSingleFunc(scrollList, pum)
        return pum

    def _fileListSelectCommand(self, scrollList, popupAttr, buildPopupFunc, listSelectFunc, list_key,
                               sendToProjectAttr=None, *args):
        """Selection handler — rebuild popup each change; multi-select gets reduced menu."""
        self._rebuildFileListPopup(scrollList, popupAttr, buildPopupFunc, list_key,
                                   sendToProjectAttr=sendToProjectAttr)
        _items = scrollList.getSelectedItems() or []
        if not _items:
            return False
        if len(_items) <= 1:
            listSelectFunc()
        return True

    def _wireFileListScrollSelect(self, searchableList, popupAttr, buildPopupFunc, listSelectFunc,
                                  list_key=None, sendToProjectAttr=None):
        scrollList = searchableList['scrollList']
        setattr(self, popupAttr, None)

        def _popupPmc(*a):
            pum = getattr(self, popupAttr, None)
            if not pum or len(pum) == 0:
                self._rebuildFileListPopup(scrollList, popupAttr, buildPopupFunc, list_key,
                                           sendToProjectAttr=sendToProjectAttr)
            if sendToProjectAttr and len(scrollList.getSelectedItems() or []) <= 1:
                _sendMenu = getattr(self, sendToProjectAttr, None)
                if _sendMenu and mc.objExists(_sendMenu):
                    self.UpdateVersionTSLPopup(_sendMenu)

        self._d_fileListPopupPmc[popupAttr] = _popupPmc

        scrollList.cmd_select = cgmGEN.Callback(
            self._fileListSelectCommand,
            scrollList, popupAttr, buildPopupFunc, listSelectFunc, list_key, sendToProjectAttr)

        def _selCommand(*a, **kws):
            if scrollList.cmd_select:
                return scrollList.cmd_select()
            return False

        scrollList.selCommand = _selCommand
        scrollList(e=True, sc=_selCommand)

    def buildSubTypeListPopup(self, scrollList, pum=None):
        if pum is None:
            pum = mUI.MelPopupMenu(scrollList, button=3)
            setattr(self, 'subTypeListPUM', pum)
        else:
            setattr(self, 'subTypeListPUM', pum)

        mUI.MelMenuItem(pum, label='        Subtype', en=False)
        mUI.MelMenuItemDiv(pum, label='Selected')

        self.ml_dirOptions_set = []
        self.ml_dirOptions_set.append(mUI.MelMenuItem(pum, label="Rename Set", command=partial(self.rename_below, 'set')))

        self.ml_fileOptions_set = []
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Reference",
                                                       ann=_d_ann.get('reference'),
                                                       command=self.ReferenceFile, en=1))
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Import",
                                                       ann=_d_ann.get('import'),
                                                       command=self.ImportFile, en=1))
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Replace",
                                                       ann=_d_ann.get('replace', 'Replace'),
                                                       command=self.file_replace, en=1))
        mUI.MelMenuItem(pum, label="Export Here",
                        ann="Export selected objects using Maya's Export Selection",
                        c=lambda *a: self.ExportSelection_sets())

        self.uiPop_sendToProject_sub = mUI.MelMenuItem(pum, label="Send To Project", subMenu=True, en=1)
        self.ml_fileOptions_set.append(self.uiPop_sendToProject_sub)
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Send To Build", command=self.SendToBuild, en=1))
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Send Last To Queue", command=self.AddLastToExportQueue))
        self.ml_fileOptions_set.append(mUI.MelMenuItem(pum, label="Create SubTypeRef", command=lambda *a: self.CreateSubTypeRef()))

        _batch = mUI.MelMenuItem(pum, label="To Queue as:", subMenu=True)
        self.ml_fileOptions_set.append(_batch)
        for t in ['export', 'rig', 'cutscene']:
            mUI.MelMenuItem(_batch, label=t.capitalize(), command=partial(self.AddToExportQueue, t))

        self._append_p4_file_menu(pum, self.ml_p4_options_set, list_key='sets')

        mUI.MelMenuItemDiv(pum, label='Directory')
        self._append_p4_get_latest_dir_item(
            pum, self.ml_p4_options_dir_set, partial(self.uiFunc_p4_sync_directory, 'sets'))
        mUI.MelMenuItem(pum, label="Explorer", command=self.OpenSubTypeDirectory)
        mUI.MelMenuItem(pum, ann="Open Maya file", c=lambda *a: self.uiPath_mayaOpen_subType(), label='Open Maya here')
        mUI.MelMenuItem(pum, ann="Save Maya file", c=lambda *a: self.uiPath_mayaSaveTo_sets(), label='Save Maya here')
        mUI.MelMenuItem(pum, label="Refresh", command=lambda *a: self._defer_ui(self._refreshSubTypeList))
        mUI.MelMenuItemDiv(pum)
        mUI.MelMenuItem(pum, label="Delete",
                         command=lambda *a: self._defer_ui(cgmGEN.Callback(self.uiFunc_deleteSelectedInList, 'sets')))
        self.UpdateVersionTSLPopup(self.uiPop_sendToProject_sub)

    def buildVariationListPopup(self, scrollList, pum=None):
        if pum is None:
            pum = mUI.MelPopupMenu(scrollList, button=3)
            setattr(self, 'variationListPUM', pum)
        else:
            setattr(self, 'variationListPUM', pum)

        mUI.MelMenuItem(pum, label='        Variant', en=False)
        mUI.MelMenuItemDiv(pum, label='Selected')

        self.ml_dirOptions_variant = []
        self.ml_dirOptions_variant.append(mUI.MelMenuItem(pum, label="Rename Variant", command=partial(self.rename_below, 'variant')))

        self.ml_fileOptions_variant = []
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Reference File",
                                                           ann=_d_ann.get('reference'),
                                                           command=self.ReferenceFile))
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Import",
                                                           ann=_d_ann.get('import'),
                                                           command=self.ImportFile))
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Replace",
                                                           ann=_d_ann.get('replace', 'Replace'),
                                                           command=self.file_replace))
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Export Here",
                                                           ann="Export selected objects using Maya's Export Selection",
                                                           command=lambda *a: self.ExportSelection(mode='variant')))

        self.uiPop_sendToProject_variant = mUI.MelMenuItem(pum, label="Send To Project", subMenu=True)
        self.ml_fileOptions_variant.append(self.uiPop_sendToProject_variant)
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Send To Build", command=self.SendToBuild, en=1))
        self.ml_fileOptions_variant.append(mUI.MelMenuItem(pum, label="Send Last To Queue", command=self.AddLastToExportQueue))

        self._append_p4_file_menu(pum, self.ml_p4_options_variant, list_key='variation')

        mUI.MelMenuItemDiv(pum, label='Directory')
        self._append_p4_get_latest_dir_item(
            pum, self.ml_p4_options_dir_variant, partial(self.uiFunc_p4_sync_directory, 'variation'))
        mUI.MelMenuItem(pum, label="Explorer", command=self.OpenVariationDirectory)
        mUI.MelMenuItem(pum, ann="Open Maya file", c=lambda *a: self.uiPath_mayaOpen_variant(), label='Open Maya here')
        mUI.MelMenuItem(pum, ann="Save Maya file", c=lambda *a: self.uiPath_mayaSaveTo_variant(), label='Save Maya here')
        mUI.MelMenuItem(pum, label="Refresh", command=lambda *a: self._defer_ui(self._refreshVariationList))
        mUI.MelMenuItemDiv(pum)
        mUI.MelMenuItem(pum, label="Delete",
                         command=lambda *a: self._defer_ui(cgmGEN.Callback(self.uiFunc_deleteSelectedInList, 'variation')))
        self.UpdateVersionTSLPopup(self.uiPop_sendToProject_variant)

    def buildVersionListPopup(self, scrollList, pum=None):
        if pum is None:
            pum = mUI.MelPopupMenu(scrollList, button=3)
            setattr(self, 'versionListPUM', pum)
        else:
            setattr(self, 'versionListPUM', pum)

        mUI.MelMenuItem(pum, label='        Version', en=False)
        mUI.MelMenuItemDiv(pum, label='Selected')

        mUI.MelMenuItem(pum, label="Reference File", ann=_d_ann.get('reference'), command=self.ReferenceFile)
        mUI.MelMenuItem(pum, label="Import", ann=_d_ann.get('import'), command=self.ImportFile)
        mUI.MelMenuItem(pum, label="Replace", ann=_d_ann.get('replace', 'Replace'), command=self.file_replace)
        mUI.MelMenuItem(pum, label="Export Here",
                        ann="Export selected objects using Maya's Export Selection",
                        command=lambda *a: self.ExportSelection(mode='version'))

        self.uiPop_sendToProject_version = mUI.MelMenuItem(pum, label="Send To Project", subMenu=True)
        mUI.MelMenuItem(pum, label="Send To Build", command=self.SendToBuild, en=1)

        _batch = mUI.MelMenuItem(pum, label="To Queue as:", subMenu=True)
        for t in ['export', 'rig', 'cutscene']:
            mUI.MelMenuItem(_batch, label=t.capitalize(), command=partial(self.AddToExportQueue, t))

        mUI.MelMenuItem(pum, label="Create SubTypeRef", command=lambda *a: self.CreateSubTypeRef())

        self._append_p4_file_menu(pum, self.ml_p4_options_version, list_key='version')

        mUI.MelMenuItemDiv(pum, label='Directory')
        self._append_p4_get_latest_dir_item(
            pum, self.ml_p4_options_dir_version, self.uiFunc_p4_sync_version_directory,
            enabled=True)
        mUI.MelMenuItem(pum, label="Explorer", command=self.OpenVersionDirectory)
        mUI.MelMenuItem(pum, ann="Save Maya file", c=lambda *a: self.uiPath_mayaSaveTo_version(), label='Save Maya here')
        mUI.MelMenuItem(pum, label="Refresh", command=lambda *a: self._defer_ui(self._refreshVersionList))
        mUI.MelMenuItemDiv(pum)
        mUI.MelMenuItem(pum, label="Delete",
                         command=lambda *a: self._defer_ui(cgmGEN.Callback(self.uiFunc_deleteSelectedInList, 'version')))
        self.UpdateVersionTSLPopup(self.uiPop_sendToProject_version)

    def UpdateVersionTSLPopup(self, mMenu = None,  *args):
        if not mMenu or not mc.objExists(mMenu):
            if mMenu is not None:
                self.d_subPops.pop(mMenu, None)
            return
        for item in self.d_subPops.get(mMenu, []):
            try:
                if mc.objExists(item):
                    mc.deleteUI(item, menuItem=True)
            except Exception as err:
                log.debug(log_msg('UpdateVersionTSLPopup', err))

        self.d_subPops[mMenu] = []

        asset = self.versionFile

        mPathList = cgmMeta.pathList('cgmProjectPaths')

        project_names = []
        for i,p in enumerate(mPathList.mOptionVar.value):
            mProj = Project.data(filepath=p)
            name = mProj.d_project['name']
            project_names.append(name)

            if self.mDat.userPaths_get().get('content') == mProj.userPaths_get().get('content'):
                continue

            item = mUI.MelMenuItem( mMenu, l=name if project_names.count(name) == 1 else '%s {%i}' % (name,project_names.count(name)-1),
                                    c = partial(self.SendVersionFileToProject,{'filename':asset,'project':p}))
            self.d_subPops[mMenu].append(item)
            #mMenu.append(item)

    def SendToBuild(self,*args):
        _str_func = 'Scene.SendToBuild'
        f = self.versionFile
        if not f:
            return log.error("SendToBuild: No version file found")

        log.info(log_msg(_str_func, "Opening MRS Build for file | {0}".format(f)))
        try:
            m_standalone = BUILDER.ui_toStandAlone()
        except Exception:
            log.exception(log_msg(_str_func, "Failed to open MRS Build UI"))
            return
        m_standalone.l_files = [f]
        log.info(
            log_msg(
                _str_func,
                "Queued for Build button | l_files={0} (click Build in the window)".format(
                    m_standalone.l_files
                ),
            )
        )


    def SendVersionFileToProject(self, infoDict, *args):
        _str_func = 'ui.SendVersionFileToProject'
        newProject = Project.data(filepath=infoDict['project'])
        _file = infoDict['filename']
        newFilename = os.path.normpath(_file).replace(os.path.normpath(self.mDat.userPaths_get()['content']), os.path.normpath(newProject.userPaths_get()['content']))

        log.debug( log_msg(_str_func,"Selected: {0}".format(_file)))            
        log.debug( log_msg(_str_func,"New: {0}".format(newFilename)))            

        if os.path.exists(newFilename):
            result = mc.confirmDialog(
                title='Destination file exists!',
                            message='The destination file already exists. Would you like to overwrite it?',
                            button=['Yes', 'Cancel'],
                            defaultButton='Yes',
                                        cancelButton='Cancel',
                                                    dismissString='Cancel')

            if result != 'Yes':
                return False

        if not os.path.exists(os.path.dirname(newFilename)):
            log.debug( log_msg(_str_func,"Creating path : {0}".format(newFilename)))            
            os.makedirs(os.path.dirname(newFilename))

        copyfile(_file, newFilename)

        #if os.path.exists(newFilename) and os.path.normpath(mc.file(q=True, loc=True)) == os.path.normpath(infoDict['filename']):
        result = 'Cancel'
        if not self.var_alwaysSendReferenceFiles.getValue():
            result = mc.confirmDialog(
                title='Send Missing References?',
                                message='Copy missing references as well?',
                                button=['Yes', 'Yes and Stop Asking', 'Cancel'],
                                defaultButton='Yes',
                                                cancelButton='No',
                                                            dismissString='No')

        if result == 'Yes and Stop Asking':
            self.var_alwaysSendReferenceFiles.setValue(1)

        if result == 'Yes' or self.var_alwaysSendReferenceFiles.getValue():
            log.debug( log_msg(_str_func,"Trying References..."))
            for refFile in mc.file(_file,query=True, reference=True):
                if not os.path.exists(refFile):
                    continue

                newRefFilename = os.path.normpath(refFile).replace(os.path.normpath(self.mDat.userPaths_get()['content']), os.path.normpath(newProject.userPaths_get()['content']))
                print(newRefFilename)
                if not os.path.exists(newRefFilename):
                    if not os.path.exists(os.path.dirname(newRefFilename)):
                        os.makedirs(os.path.dirname(newRefFilename))
                    copyfile(refFile, newRefFilename)

        result = mc.confirmDialog(
            title='Change Project?',
                        message='Change to the new project?',
                        button=['Yes', 'No'],
                        defaultButton='Yes',
                                    cancelButton='No',
                                                dismissString='No')

        if result == 'Yes':
            if self.LoadProject(infoDict['project']):
                self.LoadOptions()
        #else:
        #    log.debug( log_msg(_str_func,"Path mismatch, no ref possible"))


        log.debug( log_msg(_str_func,"Done"))
    def SendLatestRigToProject():
        pass

    def OpenRig(self, filename, *args):
        rigPath = filename #os.path.normpath(os.path.join(self.path_asset, "%s_rig.mb" % self.assetList['scrollList'].getSelectedItem() ))
        if os.path.exists(rigPath):
            mc.file(rigPath, o=True, f=True, ignoreVersion=True)

    def ReferenceRig(self, filename, assetName, *args):
        _str_func = 'Scene.ReferenceRig'
        rigPath = filename #os.path.normpath(os.path.join(self.path_asset, "%s_rig.mb" % self.assetList['scrollList'].getSelectedItem() ))

        log.debug( '{0} | Referencing file : {1}'.format(_str_func, rigPath) )

        if os.path.exists(rigPath):
            mc.file(rigPath, r=True, ignoreVersion=True, gl=True, mergeNamespacesOnClash=False, namespace=assetName)

    def VerifyAssetDirs(self):
        _str_func = 'Scene.VerifyAssetDirs'

        PROJECT.uiProject_verifyDir(self,'content',None)
        self.uiProject_refreshDisplay()


        return
        assetName = self.selectedAsset
        assetPath = os.path.normpath(os.path.join(self.path_dir_category, assetName))
        #subTypes = [x['n'] for x in self.mDat.assetType_get(category).get('content', [{'n':'animation'}])]

        if not os.path.exists(assetPath):
            os.mkdir(PATHS.get_dir(charPath))
            log.info('{0}>> Path not found. Appending: {1}'.format(_str_func, assetPath))		
        for subType in self.subTypes:
            subPath = os.path.normpath(os.path.join(assetPath, subType))
            if not os.path.exists(subPath):
                os.mkdir(PATHS.get_dir(subPath))
                log.info('{0}>> Path not found. Appending: {1}'.format(_str_func, subPath))

    def AddLastToExportQueue(self, *args):
        if self.variationList != None:
            self.batchExportItems.append( {"category":self.category,
                                           'subType':self.subType,                                           
                                           "asset":self.assetList['scrollList'].getSelectedItem(),
                                           "set":self.subTypeSearchList['scrollList'].getSelectedItem(),
                                           "variation":self.variationList['scrollList'].getSelectedItem(),
                                           "version":self.versionList['scrollList'].getItems()[-1]} )

        self.RefreshQueueList()

    def ExportQueue_write(self,*args):
        if not self.batchExportItems:
            return log.error("Nothing in queue")

        mDat = SCENEDAT.SceneExport({'data':self.batchExportItems})
        mDat.write()



    def ExportQueue_load(self,*args):
        mDat = SCENEDAT.SceneExport({'data':self.batchExportItems})
        mDat.read()

        if mDat.dat:
            self.batchExportItems = mDat.dat.get('data',[])

        self.RefreshQueueList()

    def ExportQueue_getEntryDirectoryAndPrefix(self, animDict):
        """Resolve directory and version filename prefix for a queue entry."""
        _str_func = 'ExportQueue_getEntryDirectoryAndPrefix'
        if not self.directory:
            log.debug(log_msg(_str_func, 'No directory set'))
            return None, None
        try:
            categoryDirectory = os.path.normpath(os.path.join(self.directory, animDict.get('category', '')))
            path_asset = os.path.normpath(os.path.join(categoryDirectory, animDict.get('asset', '')))
            path_set = self._resolve_subType_container_path(path_asset, animDict.get('subType', ''))
            if animDict.get('path'):
                searchDir = os.path.dirname(animDict['path'])
                if not os.path.isdir(searchDir):
                    log.debug(log_msg(_str_func, 'Path dir not found: {}'.format(searchDir)))
                    return None, None
            else:
                if animDict.get('variation'):
                    searchDir = os.path.normpath(os.path.join(path_set, animDict['variation']))
                else:
                    searchDir = path_set
            if not os.path.isdir(searchDir):
                log.debug(log_msg(_str_func, 'Dir not found: {}'.format(searchDir)))
                return searchDir, None
            exportMode = animDict.get('exportMode', 'export')
            if exportMode == 'rig':
                if animDict.get('set'):
                    prefix = '{0}_{1}_rig_'.format(animDict.get('asset', ''), animDict.get('set', ''))
                else:
                    prefix = '{0}_rig_'.format(animDict.get('asset', ''))
            else:
                if animDict.get('variation'):
                    prefix = '{0}_{1}_{2}_'.format(
                        animDict.get('asset', ''),
                        animDict.get('set', ''),
                        animDict.get('variation', ''))
                elif animDict.get('set'):
                    prefix = '{0}_{1}_'.format(animDict.get('asset', ''), animDict.get('set', ''))
                else:
                    baseName = (animDict.get('version') or '').split('.')[0]
                    if baseName:
                        prefix = re.sub(r'[0-9]+$', '', baseName)
                    else:
                        return searchDir, None
            return searchDir, prefix
        except Exception as err:
            log.debug(log_msg(_str_func, 'Error: {}'.format(err)))
            return None, None

    def ExportQueue_checkForUpdates(self):
        """Scan batchExportItems for entries that have newer versions available. Returns list of updatable items."""
        _str_func = 'ExportQueue_checkForUpdates'
        log.debug(log_start(_str_func))
        l_updatable = []
        fileExtensions = ['ma', 'mb']
        for idx, animDict in enumerate(self.batchExportItems):
            currentVersion = animDict.get('version')
            if not currentVersion:
                continue
            baseName = currentVersion.split('.')[0]
            if not re.search(r'[0-9]+$', baseName):
                continue
            searchDir, prefix = self.ExportQueue_getEntryDirectoryAndPrefix(animDict)
            if not searchDir or not prefix or not os.path.isdir(searchDir):
                continue
            try:
                allFiles = CGMOS.get_lsFromPath(searchDir)
            except (ValueError, TypeError):
                continue
            matched = []
            for f in allFiles:
                if f[0] in '_.':
                    continue
                if os.path.isdir(os.path.join(searchDir, f)):
                    continue
                if os.path.splitext(f)[-1].lower()[1:] not in fileExtensions:
                    continue
                if prefix in f:
                    try:
                        numPart = re.findall(r'[0-9]+', f.split('.')[0].split('_')[-1])
                        num = int(numPart[0]) if numPart else 0
                        matched.append((f, num))
                    except (IndexError, ValueError):
                        matched.append((f, 0))
            if not matched:
                continue
            matched.sort(key=lambda x: x[1])
            latestFile = matched[-1][0]
            currentBase = currentVersion.split('{')[0] if '{' in currentVersion else currentVersion
            if latestFile != currentBase:
                newPath = os.path.normpath(os.path.join(searchDir, latestFile))
                l_updatable.append({
                    'idx': idx,
                    'entry': animDict,
                    'current_version': currentVersion,
                    'new_version': latestFile,
                    'new_path': newPath,
                })
        return l_updatable

    def ExportQueue_updateDialog(self, l_updatable):
        """Show popup with checkboxes for each updatable entry. Apply updates on confirm."""
        _str_func = 'ExportQueue_updateDialog'
        winName = 'cgmSceneQueueUpdateWin'
        if mc.window(winName, exists=True):
            mc.deleteUI(winName)
        win = mc.window(winName, title='Update Queue Entries', resizeToFitChildren=True, sizeable=True)
        mainCol = mUI.MelColumnLayout(win, ut='cgmUISubTemplate')
        mUI.MelLabel(mainCol, label='Select entries to update to newer versions:', align='left')
        cgmUI.add_LineSubBreak()
        scroll = mUI.MelScrollLayout(mainCol, useTemplate='cgmUISubTemplate')
        col = mUI.MelColumnLayout(scroll, adjustableColumn=True)
        checkboxes = []
        for i, item in enumerate(l_updatable):
            lbl = '{0} -> {1}'.format(item['current_version'], item['new_version'])
            _ut = 'cgmUIInstructionsTemplate' if MATH.is_even(i) else 'cgmUISubTemplate'
            row = mUI.MelHSingleStretchLayout(col, padding=2, ut=_ut)
            cb = mUI.MelCheckBox(row, label=lbl, v=True)
            row.setStretchWidget(cb)
            checkboxes.append((item['idx'], cb, item))
            row.layout()
        cgmUI.add_LineSubBreak()
        btnRow = mUI.MelHLayout(mainCol, padding=5)
        def _checkAll(*a):
            for _, cb, _ in checkboxes:
                mc.checkBox(cb, edit=True, value=True)
        def _clearAll(*a):
            for _, cb, _ in checkboxes:
                mc.checkBox(cb, edit=True, value=False)
        def _apply(*a):
            for idx, cb, item in checkboxes:
                if mc.checkBox(cb, q=True, v=True):
                    self.batchExportItems[idx]['version'] = item['new_version']
                    self.batchExportItems[idx]['path'] = item['new_path']
            self.RefreshQueueList()
            mc.deleteUI(winName)
        mUI.MelButton(btnRow, label='Check All', ut='cgmUITemplate', c=cgmGEN.Callback(_checkAll))
        mUI.MelButton(btnRow, label='Clear', ut='cgmUITemplate', c=cgmGEN.Callback(_clearAll))
        mUI.MelButton(btnRow, label='Apply', ut='cgmUITemplate', c=cgmGEN.Callback(_apply))
        mUI.MelButton(btnRow, label='Cancel', ut='cgmUITemplate', c=cgmGEN.Callback(mc.deleteUI, winName))
        btnRow.layout()
        mc.showWindow(win)

    def ExportQueue_update(self, *args):
        """Check queue for newer versions and offer to update selected entries."""
        _str_func = 'ExportQueue_update'
        log.debug(log_start(_str_func))
        if not self.batchExportItems:
            mc.confirmDialog(title='Update Queue', message='Queue is empty.')
            return
        l_updatable = self.ExportQueue_checkForUpdates()
        if not l_updatable:
            mc.confirmDialog(title='Update Queue', message='No entries have newer versions available.')
            return
        self.ExportQueue_updateDialog(l_updatable)

    def ExportQueue_report(self, *args):
        """Show a hierarchical report of queue data by category, asset, set, variation."""
        _str_func = 'ExportQueue_report'
        if not self.batchExportItems:
            mc.confirmDialog(title='Queue Report', message='Queue is empty.')
            return
        lines = []
        lines.append('Export Queue Report ({} entries)'.format(len(self.batchExportItems)))
        lines.append('=' * 50)
        d_tree = {}
        for item in self.batchExportItems:
            cat = item.get('category') or '(none)'
            asset = item.get('asset') or '(none)'
            subType = item.get('subType') or '(none)'
            s = item.get('set') or '(none)'
            var = item.get('variation') or '(none)'
            ver = item.get('version') or '(none)'
            mode = item.get('exportMode') or 'export'
            path = item.get('path') or '(no path)'
            if cat not in d_tree:
                d_tree[cat] = {}
            if asset not in d_tree[cat]:
                d_tree[cat][asset] = {}
            if subType not in d_tree[cat][asset]:
                d_tree[cat][asset][subType] = {}
            if s not in d_tree[cat][asset][subType]:
                d_tree[cat][asset][subType][s] = {}
            if var not in d_tree[cat][asset][subType][s]:
                d_tree[cat][asset][subType][s][var] = []
            d_tree[cat][asset][subType][s][var].append({'version': ver, 'mode': mode, 'path': path})
        for cat in sorted(d_tree.keys()):
            lines.append('')
            lines.append('Category: {}'.format(cat))
            for asset in sorted(d_tree[cat].keys()):
                lines.append('  Asset: {}'.format(asset))
                for subType in sorted(d_tree[cat][asset].keys()):
                    lines.append('    SubType: {}'.format(subType))
                    for s in sorted(d_tree[cat][asset][subType].keys()):
                        lines.append('      Set: {}'.format(s))
                        for var in sorted(d_tree[cat][asset][subType][s].keys()):
                            lines.append('        Variation: {}'.format(var))
                            for ent in d_tree[cat][asset][subType][s][var]:
                                lines.append('          - {} [{}]'.format(ent['version'], ent['mode']))
        reportText = '\n'.join(lines)
        winName = 'cgmSceneQueueReportWin'
        if mc.window(winName, exists=True):
            mc.deleteUI(winName)
        win = mc.window(winName, title='Queue Report', resizeToFitChildren=True, sizeable=True)
        mainCol = mUI.MelColumnLayout(win, ut='cgmUISubTemplate')
        mUI.MelLabel(mainCol, label='Queue data breakdown by category, asset, set, variation:', align='left')
        cgmUI.add_LineSubBreak()
        scrollField = mUI.MelScrollField(mainCol, h=400, text=reportText, wordWrap=False, editable=False)
        cgmUI.add_LineSubBreak()
        mUI.MelButton(mainCol, label='Close', ut='cgmUITemplate', c=cgmGEN.Callback(mc.deleteUI, winName))
        mc.showWindow(win)

    def ExportQueue_sort(self, *args):
        """Sort batchExportItems by category, asset, subType, set, variation, version."""
        if not self.batchExportItems:
            return
        def _sortKey(item):
            return (
                (item.get('category') or '').lower(),
                (item.get('asset') or '').lower(),
                (item.get('subType') or '').lower(),
                (item.get('set') or '').lower(),
                (item.get('variation') or '').lower(),
                (item.get('version') or '').lower(),
            )
        self.batchExportItems.sort(key=_sortKey)
        self.RefreshQueueList()

    def ExportQueue_selectEntryInUI(self, *args):
        """On double-click of queue entry, navigate the top section to select that file (like Select Open File)."""
        idx = self.queueTSL.getSelectedIdx()
        if idx is None or idx < 0 or idx >= len(self.batchExportItems):
            return
        animDict = self.batchExportItems[idx]
        try:
            if animDict.get('category') and animDict['category'] in self.categoryList:
                self.SetCategory(self.categoryList.index(animDict['category']))
            if animDict.get('subType') and animDict['subType'] in self.subTypes:
                self.SetSubType(self.subTypes.index(animDict['subType']))
            if animDict.get('asset'):
                self.assetList['scrollList'].selectByValue(animDict['asset'])
            self.LoadSubTypeList()
            if animDict.get('set'):
                self.subTypeSearchList['scrollList'].selectByValue(animDict['set'])
            self.LoadVariationList()
            if animDict.get('variation'):
                self.variationList['scrollList'].selectByValue(animDict['variation'])
            self.LoadVersionList()
            if animDict.get('version'):
                self.versionList['scrollList'].selectByValue(animDict['version'])
        except Exception as err:
            log.warning("ExportQueue_selectEntryInUI: could not navigate to entry - {}".format(err))

    def _exportQueueBaseFields(self, exportMode):
        return {
            "category": self.category,
            'subType': self.subType,
            'exportMode': exportMode,
            "asset": self.assetList['scrollList'].getSelectedItem(),
        }

    def _exportQueueEntryForVersion(self, version_name, exportMode):
        _str_func = '_exportQueueEntryForVersion'
        if not version_name:
            return None
        entry = self._exportQueueBaseFields(exportMode)
        parent = self._version_files_parent_directory()
        path = os.path.normpath(os.path.join(parent, version_name)) if parent else None
        entry.update({
            "path": path,
            "set": self.subTypeSearchList['scrollList'].getSelectedItem(),
            "variation": self.variationList['scrollList'].getSelectedItem(),
            "version": version_name,
        })
        return entry

    def _exportQueueEntryForSetItem(self, item_name, exportMode):
        _str_func = '_exportQueueEntryForSetItem'
        if not item_name:
            return None
        try:
            _subRoot = self.path_subType or self._resolve_subType_container_path(self.path_asset, self.subType)
            if not _subRoot:
                return None
            full_path = os.path.normpath(os.path.join(_subRoot, item_name))
        except Exception as err:
            log.debug(log_msg(_str_func, 'Error: {}'.format(err)))
            return None
        entry = self._exportQueueBaseFields(exportMode)
        if os.path.isfile(full_path):
            entry.update({
                "path": None,
                "set": None,
                "variation": None,
                "version": item_name,
            })
        elif os.path.isdir(full_path):
            entry.update({
                "path": None,
                "set": item_name,
                "variation": None,
                "version": None,
            })
        else:
            return None
        return entry

    def _exportQueueEntryForVariationItem(self, item_name, exportMode):
        _str_func = '_exportQueueEntryForVariationItem'
        if not item_name:
            return None
        path_set = self.path_set
        if not path_set:
            return None
        full_path = os.path.normpath(os.path.join(path_set, item_name))
        entry = self._exportQueueBaseFields(exportMode)
        entry["set"] = self.subTypeSearchList['scrollList'].getSelectedItem()
        if os.path.isfile(full_path):
            entry.update({
                "path": None,
                "variation": None,
                "version": item_name,
            })
        elif os.path.isdir(full_path):
            entry.update({
                "path": None,
                "variation": item_name,
                "version": None,
            })
        else:
            return None
        return entry

    def _exportQueueActiveFileList(self):
        """Pick which file scroll list drives bulk queue; prefer a multi-selection list."""
        lists = [
            ('version', self.versionList['scrollList']),
            ('variation', self.variationList['scrollList']),
            ('sets', self.subTypeSearchList['scrollList']),
        ]
        for name, scroll in lists:
            if len(scroll.getSelectedItems() or []) > 1:
                return name, scroll
        for name, scroll in lists:
            if scroll.getSelectedItems():
                return name, scroll
        return None, None

    def _collectExportQueueEntries(self, exportMode):
        _str_func = '_collectExportQueueEntries'
        active_name, scroll = self._exportQueueActiveFileList()
        if not scroll:
            return []
        entries = []
        for item in scroll.getSelectedItems():
            if active_name == 'version':
                entry = self._exportQueueEntryForVersion(item, exportMode)
            elif active_name == 'variation':
                entry = self._exportQueueEntryForVariationItem(item, exportMode)
            else:
                entry = self._exportQueueEntryForSetItem(item, exportMode)
            if entry:
                entries.append(entry)
            else:
                log.debug(log_msg(_str_func, 'skip {} item | {}'.format(active_name, item)))
        return entries

    def AddToExportQueue(self, exportMode = 'export', *args):
        if self.versionList['scrollList'].getSelectedItem() != None:
            self.batchExportItems.append( {"category":self.category,
                                           "path":self.versionFile,
                                           'subType':self.subType,
                                           'exportMode':exportMode,
                                           "asset":self.assetList['scrollList'].getSelectedItem(),
                                           "set":self.subTypeSearchList['scrollList'].getSelectedItem(),
                                           "variation":self.variationList['scrollList'].getSelectedItem(),
                                           "version":self.versionList['scrollList'].getSelectedItem()} )
        elif self.variationList != None:
            self.batchExportItems.append( {"category":self.category,
                                           "path":None,
                                           'subType':self.subType,
                                           'exportMode':exportMode,
                                           "asset":self.assetList['scrollList'].getSelectedItem(),
                                           "set":None,#self.subTypeSearchList['scrollList'].getSelectedItem(),
                                           "variation":None, # self.variationList['scrollList'].getSelectedItem(),
                                           "version":self.subTypeSearchList['scrollList'].getSelectedItem()} )
        else:
            return log.warning("AddToExportQueue: no valid selection")
        pprint.pprint(self.batchExportItems[-1])
        self.RefreshQueueList()

    def AddSelectedToExportQueue(self, exportMode='export', *args):
        _str_func = 'AddSelectedToExportQueue'
        entries = self._collectExportQueueEntries(exportMode)
        if not entries:
            return log.warning(log_msg(_str_func, 'no valid selection'))
        self.batchExportItems.extend(entries)
        log.info(log_msg(_str_func, 'Added {} item(s) to export queue'.format(len(entries))))
        self.RefreshQueueList()

    def RemoveFromQueue(self, *args):
        if args[0] == 0:
            idxes = self.queueTSL.getSelectedIdxs()
            print(idxes)
            idxes.reverse()

            for idx in idxes:
                #del self.batchExportItems[idx-1]
                self.batchExportItems.remove( self.batchExportItems[idx] )
        elif args[0] == 1:
            self.batchExportItems = []

        self.RefreshQueueList()

    def batch_buildFile(self, *args):
        _str_func = 'batch_buildFile'
        log.info(log_start(_str_func))


        if self.useMayaPy:
            #reload(BATCH)
            log.debug('Maya Py!')

            bakeSetName = self.var_bakeSet.getValue()
            deleteSetName = self.var_deleteSet.getValue()
            exportSetName = self.var_exportSet.getValue()

            #if(mc.optionVar(exists='cgm_bake_set')):
                #bakeSetName = mc.optionVar(q='cgm_bake_set')    
            #if(mc.optionVar(exists='cgm_delete_set')):
                #deleteSetName = mc.optionVar(q='cgm_delete_set')
            #if(mc.optionVar(exists='cgm_export_set')):
                #exportSetName = mc.optionVar(q='cgm_export_set')                


            l_dat = []
            d_base = {'removeNamespace' : PU.exportOption_getValue(self, 'removeNameSpace'),
                      'bakeSetName':bakeSetName,
                      'exportSetName':exportSetName,
                      'deleteSetName':deleteSetName,
                      'zeroRoot' : PU.exportOption_getValue(self, 'zeroRoot'),
                      'euler':PU.exportOption_getValue(self, 'postEuler'),
                      'fixRotation':PU.exportOption_getValue(self, 'fixRotation'),
                      'tangent':PU.exportOption_getValue(self, 'postTangent'),
                      'sampleBy':PU.exportOption_getValue(self, 'sampleBy'),
                      'simplify':PU.exportOption_getValue(self, 'simplify'),
                      'reducer':PU.exportOption_getValue(self, 'reducer'),
                      'exportShotsToIndividualFiles':PU.exportOption_getValue(self, 'exportShotsToIndividualFiles'),
                      'noShotListExportName':PU.exportOption_getValue(self, 'noShotListExportName'),
                      'parentExportToWorld':PU.exportOption_getValue(self, 'parentExportToWorld'),
                      'deleteMesh':PU.exportOption_getValue(self, 'deleteMesh'),
                      'worldUp': (self.mDat.d_world.get('worldUp', 'y') if self.mDat else 'y'),
                      }

            for animDict in self.batchExportItems:

                categoryDirectory = os.path.normpath(os.path.join( self.directory, animDict["category"] ))
                path_asset = os.path.normpath(os.path.join( categoryDirectory, animDict["asset"] ))


                pprint.pprint(animDict)
                #path_set= os.path.normpath(os.path.join( path_asset, animDict["subType"], animDict["set"] ))

                path_set = self._resolve_subType_container_path(path_asset, animDict["subType"])

                if animDict.get('path'):
                    versionFile = animDict.get('path')
                else:
                    if animDict.get('variation'):
                        path_variationDirectory = os.path.normpath(os.path.join( path_set, animDict["variation"] ))                    
                    else:
                        path_variationDirectory = path_set

                    versionFile = os.path.normpath(os.path.join( path_variationDirectory, animDict["version"] ))

                categoryExportPath = os.path.normpath(os.path.join( self.exportDirectory, animDict["category"]))
                exportAssetPath = os.path.normpath(os.path.join( categoryExportPath, animDict["asset"]))
                _exportSubType = self._exportSubTypeDirName(animDict.get("subType"))
                exportAnimPath = os.path.normpath(os.path.join(exportAssetPath, _exportSubType))

                if animDict.get('exportMode') == 'rig':
                    if animDict.get('set'):
                        _exportFileName = [animDict["asset"], animDict["set"], 'rig']
                    else:
                        _exportFileName = [animDict["asset"], 'rig']
                elif animDict.get('asset') and animDict.get('set'):
                    _exportFileName = [animDict["asset"], animDict["set"]]
                else:
                    _exportFileName = [animDict.get('version').split('.')[0]]

                if animDict.get("variation"):
                    _exportFileName.append(animDict["variation"])

                exportFileName = "_".join(_exportFileName) + '.fbx'

                #exportFileName = '%s_%s_%s.fbx' % (animDict["asset"], animDict["set"], animDict["variation"])

                d = {
                    'file':PATHS.Path(versionFile).asString(),
                    #'objs':objs,
                    'mode':-1, #Probably needs to be able to specify this
                    'exportMode':animDict['exportMode'],
                    'exportName':exportFileName,
                    'animationName':animDict["set"],
                    'exportAssetPath' : PATHS.Path(exportAssetPath).split(),
                    'categoryExportPath' : PATHS.Path(categoryExportPath).split(),
                    'exportAnimPath' : PATHS.Path(exportAnimPath).split(),
                    'updateAndIncrement' : int(mc.checkBox(self.updateCB, q=True, v=True)),
                    'updateRigs' : int(mc.checkBox(self.updateRigsCB, q=True, v=True))

                }                

                d.update(d_base)

                l_dat.append(d)



            pprint.pprint(l_dat)


            BATCH.create_Scene_batchFile(l_dat)
            return





        for animDict in self.batchExportItems:
            self.assetList['scrollList'].selectByValue( animDict["asset"] )
            self.LoadSubTypeList()
            self.subTypeSearchList['scrollList'].selectByValue( animDict["set"])
            self.LoadVariationList()
            self.variationList['scrollList'].selectByValue( animDict["variation"])
            self.LoadVersionList()
            self.versionList['scrollList'].selectByValue( animDict["version"])

            mc.file(self.versionFile, o=True, f=True, ignoreVersion=True)

            masterNode = None
            for item in mc.ls("*:master", r=True):
                if len(item.split(":")) == 2:
                    masterNode = item

                if mc.checkBox(self.updateCB, q=True, v=True):
                    rig = ASSET.Asset(item)
                    if rig.UpdateToLatest():
                        self.SaveVersion()

            mc.select(masterNode)

            #mc.confirmDialog(message="exporting %s from %s" % (masterNode, mc.file(q=True, loc=True)))
            self.RunExportCommand(1)


    def RefreshQueueList(self, *args):
        self.queueTSL.clear()
        for i,item in enumerate(self.batchExportItems):
            self.queueTSL.append( "%i ||| asset: %s | set: %s | var: %s | version: %s | ----- Mode: [ %s ] " % (
                i,
            item["asset"],
            item["set"],
            item["variation"],
            item["version"],
            item['exportMode'],                                                                               
            ))

        if len(self.batchExportItems) > 0:
            mc.frameLayout(self.exportQueueFrame, e=True, collapse=False)
        else:
            mc.frameLayout(self.exportQueueFrame, e=True, collapse=True)



    def uiFunc_getOpenFilePathTokens(self,*args):

        _str_func = 'uiFunc_getOpenFilePathTokens'
        log.debug(log_start(_str_func))
        _current = mc.file(q=True, sn=True)
        _content = self.directory

        if _content in _current:
            pContent = PATHS.Path(_content)
            pCurrent = PATHS.Path(_current)
            pCurrent.split()
            l_current = pCurrent.split()

            l = []

            for i,n in enumerate(pContent.split()):
                l_current.pop(0)

            l_current.pop(-1)

            #l_current[-1] = '.'.join(l_current[-1].split('.')[:-1])

            pprint.pprint(l_current)
            return l_current
        return []

    # args[0]:
    # 0 is bake and prep, don't export
    # 1 is export as a regular asset
    #   - export the asset into the asset/animation directory
    # 2 is export as a cutscene 
    #   - cutscene means it adds the namespace to the 
    #   - asset and exports all of the assets into the
    #   - same directory
    # 3 is export as a rig
    #   - export into the base asset directory with
    #   - just the asset name
    def RunExportCommand(self, *args):
        _str_func = 'RunExportCommand'
        log.info(log_start(_str_func))
        mode = args[0] if args else -1
        modeLabel = {0: 'bake', 1: 'export', 2: 'cutscene', 3: 'rig', 4: 'static'}.get(mode, 'unknown')
        stage = 'path_resolve'
        _baseCtx = {'mode': mode, 'modeLabel': modeLabel}

        try:
            _l_openTokens = self.uiFunc_getOpenFilePathTokens() or []
            _pathCtx = dict(_baseCtx, stage=stage, openTokens=_l_openTokens, exportDirectory=self.exportDirectory)

            if len(_l_openTokens) < 3:
                log.error("{0} | Invalid open file path tokens. Need >=3, got {1} | {2}".format(
                    _str_func, len(_l_openTokens), _export_ctx_to_str(_pathCtx)))
                return False
            if not self.exportDirectory:
                log.error("{0} | Export directory not set | {1}".format(_str_func, _export_ctx_to_str(_pathCtx)))
                return False

            categoryExportPath = os.path.normpath(os.path.join(self.exportDirectory, _l_openTokens[0]))
            _l_openTokens.pop(0)
            exportAssetPath = os.path.normpath(os.path.join(categoryExportPath, _l_openTokens[0]))
            _l_openTokens.pop(0)
            _tmp  = self._exportSubTypeDirName(_l_openTokens[0])##os.path.join(*_l_openTokens)
            exportAnimPath = os.path.normpath(os.path.join(exportAssetPath,_tmp))

            d_userPaths = self.mDat.userPaths_get()

            postEuler = PU.exportOption_getValue(self, 'postEuler')
            fixRotation = PU.exportOption_getValue(self, 'fixRotation')
            postTangent = PU.exportOption_getValue(self, 'postTangent')
            sampleBy = PU.exportOption_getValue(self, 'sampleBy')
            reducer = PU.exportOption_getValue(self, 'reducer')
            simplify = PU.exportOption_getValue(self, 'simplify')
            exportShotsToIndividualFiles = PU.exportOption_getValue(self, 'exportShotsToIndividualFiles')
            breakTextureLinks = PU.exportOption_getValue(self, 'breakTextureLinks')
            noShotListExportName = PU.exportOption_getValue(self, 'noShotListExportName')
            parentExportToWorld = PU.exportOption_getValue(self, 'parentExportToWorld')
            deleteMesh = PU.exportOption_getValue(self, 'deleteMesh')

            pprint.pprint(vars())
            pprint.pprint(self.d_tf['exportOptions'])

            if postTangent == 'none':
                postTangent = False

            _ctx = dict(_baseCtx,
                        stage=stage,
                        categoryExportPath=categoryExportPath,
                        exportAssetPath=exportAssetPath,
                        exportAnimPath=exportAnimPath,
                        sceneFile=mc.file(q=True, sn=True))

            if self.useMayaPy:
                #reload(BATCH)
                log.debug('Maya Py!')

                bakeSetName = self.var_bakeSet.getValue()
                deleteSetName = self.var_deleteSet.getValue()
                exportSetName = self.var_exportSet.getValue()


                d = {
                    'file':mc.file(q=True, sn=True),
                    'objs':mc.ls(sl=1),
                    'mode':mode,
                    'exportName':self.exportFileName,
                    'exportAssetPath' : PATHS.Path(exportAssetPath).split(),
                    'categoryExportPath' : PATHS.Path(categoryExportPath).split(),
                    'subType' : self.subType,
                    'subSet' : self.selectedSet,
                    'exportAnimPath' : PATHS.Path(exportAnimPath).split(),
                    'removeNamespace' : PU.exportOption_getValue(self, 'removeNameSpace'),
                    'zeroRoot' : PU.exportOption_getValue(self, 'zeroRoot'),
                    'bakeSetName':bakeSetName,
                    'exportSetName':exportSetName,
                    'deleteSetName':deleteSetName,
                    'animationName':self.selectedSet,
                    'sampleBy':sampleBy,
                    'tangent':postTangent,
                    'euler':postEuler,
                    'fixRotation':fixRotation,
                    'workspace':d_userPaths['content'],
                    'simplify':simplify,
                    'reducer':reducer,
                    'exportShotsToIndividualFiles':exportShotsToIndividualFiles,
                    'breakTextureLinks':breakTextureLinks,
                    'noShotListExportName':noShotListExportName,
                    'parentExportToWorld':parentExportToWorld,
                    'deleteMesh':deleteMesh,
                    'worldUp': (self.mDat.d_world.get('worldUp', 'y') if self.mDat else 'y'),
                }
                pprint.pprint(d)

                BATCH.create_Scene_batchFile([d])
                return True
            #pprint.pprint(vars())

            # Cutscene path appends animationName under exportAnimPath (subtype dir). Must be the
            # animation/set leaf (e.g. flow), not the subtype token (Animations) — _l_openTokens[0]
            # after path parsing is still the subtype folder name.
            _animationFolderName = self.selectedSet or (_l_openTokens[-1] if _l_openTokens else None)

            result = ExportScene(mode = mode,
                                 exportObjs = None,
                                 exportName = self.exportFileName,
                                 exportAssetPath = exportAssetPath,
                                 subType = self.subType,
                                 subSet= self.selectedSet,
                                 categoryExportPath = categoryExportPath,
                                 exportAnimPath = exportAnimPath,
                                 removeNamespace = PU.exportOption_getValue(self, 'removeNameSpace'),
                                 zeroRoot = PU.exportOption_getValue(self, 'zeroRoot'),
                                 animationName=_animationFolderName,
                                 exportShotsToIndividualFiles = exportShotsToIndividualFiles,
                                 tangent=postTangent,
                                 euler=postEuler,
                                 fixRotation=fixRotation,
                                 sampleBy=sampleBy,
                                 workspace=d_userPaths['content'],
                                 simplify=simplify,
                                 reducer=reducer,
                                 breakTextureLinks=breakTextureLinks,
                                 noShotListExportName=noShotListExportName,
                                 parentExportToWorld=parentExportToWorld,
                                 deleteMesh=deleteMesh,
                                 )
            return bool(result)
        except Exception:
            _errCtx = dict(_baseCtx, stage=stage, sceneFile=mc.file(q=True, sn=True))
            log.exception("{0} | Unhandled export command error | {1}".format(_str_func, _export_ctx_to_str(_errCtx)))
            return False





def BatchExport(dataList = []):
    _str_func = 'BatchExport'
    log.info(log_start(_str_func))

    PATHUTIL.clear_non_writable_export_paths()
    clear_batch_export_results()

    t1 = time.time()

    if dataList:
        world_up = dataList[0].get('worldUp')
        if world_up:
            from cgm.core.lib import mayaSettings_utils as MAYASET
            _axis_before = MAYASET.sceneUp_get()
            if _axis_before != world_up:
                log.info('{0} | Applying batch worldUp={1} (session was {2})'.format(
                    _str_func, world_up, _axis_before))
                MAYASET.sceneUp_set(world_up)
            else:
                log.debug('{0} | worldUp already {1}'.format(_str_func, world_up))
        else:
            log.debug('{0} | No worldUp in batch payload; Maya up axis unchanged'.format(_str_func))

    _resFail = []
    _successCount = 0
    for i,fileDat in enumerate(dataList):
        _d = {}

        try:    
            _d['categoryExportPath'] = PATHS.NICE_SEPARATOR.join(fileDat.get('categoryExportPath'))
            _d['exportAnimPath'] = PATHS.NICE_SEPARATOR.join(fileDat.get('exportAnimPath'))
            _d['exportAssetPath'] = PATHS.NICE_SEPARATOR.join(fileDat.get('exportAssetPath'))
            _d['subType'] = fileDat.get('subType')
            _d['subSet'] = fileDat.get('set')            
            _d['exportName'] = fileDat.get('exportName')
            mFile = PATHS.Path(fileDat.get('file'))
            _d['mode'] = int(fileDat.get('mode'))
            _d['exportMode'] = fileDat.get('exportMode')
            _d['exportObjs'] = fileDat.get('objs')
            _removeNamespace =  fileDat.get('removeNamespace', "False")
            _d['removeNamespace'] = False if _removeNamespace == "False" else True
            _zeroRoot =  fileDat.get('zeroRoot', "False")
            _d['zeroRoot'] = False if _zeroRoot == "False" else True
            _d['deleteSetName'] = fileDat.get('deleteSetName')
            _d['exportSetName'] = fileDat.get('exportSetName')
            _d['bakeSetName'] = fileDat.get('bakeSetName')
            _d['animationName'] = fileDat.get('animationName')
            _d['workspace'] = fileDat.get('workspace')
            _d['updateAndIncrement'] = fileDat.get('updateAndIncrement')
            _d['updateRigs'] = fileDat.get('updateRigs')

            _euler =  fileDat.get('euler', "0")        
            _d['euler'] = False if _euler == '0' else True
            _fixRotation = fileDat.get('fixRotation', "False")
            _d['fixRotation'] = False if _fixRotation == "False" else True
            _d['tangent'] = fileDat.get('tangent')

            _d['reducer'] = False if fileDat.get('reducer',"False") == "False" else True
            
            _d['simplify'] = False if fileDat.get('simplify',"False") == "False" else True
            _d['exportShotsToIndividualFiles'] = False if fileDat.get('exportShotsToIndividualFiles',"False") == "False" else True
            _d['breakTextureLinks'] = False if fileDat.get('breakTextureLinks',"True") == "False" else True
            _d['noShotListExportName'] = fileDat.get('noShotListExportName', 'asset')
            _parentExportToWorld = fileDat.get('parentExportToWorld', "True")
            _d['parentExportToWorld'] = False if _parentExportToWorld == "False" else True
            _deleteMesh = fileDat.get('deleteMesh', "False")
            _d['deleteMesh'] = False if _deleteMesh == "False" else True
            _d['sampleBy'] = float(fileDat.get('sampleBy',1.0))
            _d['logExportSummary'] = False

            log.info(mFile)
            pprint.pprint(_d)

            _path = mFile.asString()
            if not mFile.exists():
                log.error("Invalid file: {0}".format(_path))
                continue

            mc.file(_path, open = 1, f = 1, iv = 1)

            _exportOk = ExportScene(**_d)
            if _exportOk is False:
                log.error("{0} | ExportScene returned False | index={1} | file={2}".format(
                    _str_func, i, fileDat.get('file')))
                _resFail.append({'index': i,
                                 'file': fileDat.get('file'),
                                 'mode': fileDat.get('mode'),
                                 'stage': 'export_scene',
                                 'error': 'ExportScene returned False (early exit, user cancel, or failure)'})
                continue
        except Exception as err:
            _ctx = {'stage': 'batch_item',
                    'index': i,
                    'file': fileDat.get('file'),
                    'mode': fileDat.get('mode'),
                    'exportName': fileDat.get('exportName')}
            log.exception("{0} | Batch item failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
            _resFail.append({'index': i,
                             'file': fileDat.get('file'),
                             'mode': fileDat.get('mode'),
                             'stage': 'batch_item',
                             'error': str(err)})
            continue
        _successCount += 1



    t2 = time.time()
    log.info("|{0}| >> Total Time >> = {1} seconds".format(_str_func, "%0.4f"%( t2-t1 )))
    print(('Completed: {}'.format(datetime.datetime.now())))                        

    log.info("{0} | Batch summary | attempted={1} | succeeded={2} | failed={3}".format(
        _str_func, len(dataList), _successCount, len(_resFail)))
    if _resFail:
        log.warning(cgmGEN._str_hardBreak)
        pprint.pprint(_resFail)
        log.warning(cgmGEN._str_hardBreak)
    _nonWritable = PATHUTIL.get_non_writable_export_paths()
    if _nonWritable:
        log.warning(cgmGEN._str_hardBreak)
        log.warning("{0} | Non-writable export paths (checkout required):".format(_str_func))
        for _p in _nonWritable:
            log.warning("{0} |   - {1}".format(_str_func, _p))
        log.warning(cgmGEN._str_hardBreak)
    if _batch_export_results:
        log_export_results_summary(_str_func, _batch_export_results, title='Batch export summary')
    return


# args[0]:
# -1 is unknown mode
# 0 is bake and prep, don't export
# 1 is export as a regular asset
#   - export the asset into the asset/animation directory
# 2 is export as a cutscene 
#   - cutscene means it adds the namespace to the 
#   - asset and exports all of the assets into the
#   - same directory
# 3 is export as a rig
#   - export into the base asset directory with
#   - just the asset name

def _resolve_no_shot_export_name(exportName, noShotListExportName, animList):
    """When shot list is empty, optionally use scene file stem instead of browser exportName."""
    if animList and animList.shotList:
        return exportName
    if noShotListExportName != 'sceneFile':
        return exportName
    _scene = mc.file(q=True, sn=True) or mc.file(q=True, loc=True) or ''
    if not _scene:
        log.warning("_resolve_no_shot_export_name | noShotListExportName=sceneFile but no scene path; using exportName")
        return exportName
    _stem = os.path.splitext(os.path.basename(_scene))[0]
    if _stem.endswith('_baked'):
        _stem = _stem[:-len('_baked')]
    _safe = CORESTRING.stripInvalidChars(_stem)
    if not _safe:
        log.warning("_resolve_no_shot_export_name | empty stem after sanitize; using exportName")
        return exportName
    return '{0}.fbx'.format(_safe)

def ExportScene(mode = -1,
                exportObjs = None,
                exportName = None,
                categoryExportPath = None,
                subType = None,
                subSet = None,
                exportAssetPath = None,
                exportAnimPath = None,
                exportMode = None,
                removeNamespace = False,
                zeroRoot = False,
                bakeSetName = 'bake_tdSet',
                exportSetName = 'export_tdSet',
                deleteSetName = 'delete_tdSet',
                animationName = None,
                workspace = None,
                updateAndIncrement = False,
                exportShotsToIndividualFiles = True,
                updateRigs = False,
                euler = False,
                fixRotation = False,
                sampleBy = 1.0,
                tangent = False,
                deleteMesh = False,
                reducer = False,
                simplify = True,
                breakTextureLinks = True,
                logExportSummary = True,
                noShotListExportName = 'asset',
                parentExportToWorld = True,
                ):

    _str_func = 'ExportScene'
    log.info(log_start(_str_func))
    _ctx_base = {'mode': mode,
                 'exportName': exportName,
                 'subType': subType,
                 'subSet': subSet,
                 'workspace': workspace,
                 'sceneFile': mc.file(q=True, sn=True)}
    _errorEvents = []

    def _finalize_failure(stage, reason, ctx=None):
        _event = {'stage': stage, 'reason': reason}
        if ctx:
            _event.update(ctx)
        _errorEvents.append(_event)
        log.error("{0} | {1} | {2}".format(_str_func, reason, _export_ctx_to_str(_event)))
        log.warning(cgmGEN._str_hardBreak)
        log.warning("{0} | Export failed. Troubleshooting summary:".format(_str_func))
        for i, e in enumerate(_errorEvents):
            log.warning("{0} | {1} | stage={2} | reason={3}".format(_str_func, i, e.get('stage'), e.get('reason')))
        log.warning(cgmGEN._str_hardBreak)
        return False

    def _finalize_fbx_export_error(err, exportFile, failure_label='FBX export failed', **extra):
        if isinstance(err, PATHUTIL.ExportOutputNotWritableError):
            PATHUTIL.record_non_writable_export_path(err.path)
            _ctx = dict(_ctx_base,
                        stage='fbx_export',
                        exportFile=exportFile or err.path,
                        exportPath=err.path,
                        reason='not_writable',
                        **extra)
            log.error("{0} | Export output not writable: {1}".format(_str_func, err.path))
            return _finalize_failure('fbx_export', 'Export output not writable', _ctx)
        _ctx = dict(_ctx_base, stage='fbx_export', exportFile=exportFile, **extra)
        log.exception("{0} | {1} | {2}".format(_str_func, failure_label, _export_ctx_to_str(_ctx)))
        return _finalize_failure('fbx_export', failure_label, _ctx)

    _export_results = []

    def _record_export_result(name, path, frames=None, exportObj=None):
        _export_results.append({
            'name': name,
            'path': os.path.normpath(path) if path else path,
            'frames': frames,
            'exportObj': exportObj,
        })

    def _finish_export_scene_success():
        if logExportSummary:
            log_export_results_summary(_str_func, _export_results)
        extend_batch_export_results(_export_results)
        return True

    #pprint.pprint(vars())

    #exec(self.exportCommand)
    import cgm.core.tools.bakeAndPrep as bakeAndPrep
    cgmGEN._reloadMod(bakeAndPrep)
    import cgm.core.mrs.Shots as SHOTS

    if workspace:
        try:
            mc.workspace(workspace, openWorkspace=True)
        except Exception:
            _ctx = dict(_ctx_base, stage='path_resolve')
            log.exception("{0} | Failed opening workspace | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
            return _finalize_failure('path_resolve', 'Failed opening workspace', _ctx)

    if updateRigs and updateRigs != '0':
        log.info(log_sub(_str_func,'Rig update'))

        masterNode = None
        for item in mc.ls("*:master", r=True):
            if len(item.split(":")) == 2:
                masterNode = item
            log.info(item)
            rig = ASSET.Asset(item)
            if rig.UpdateToLatest():
                log.info(log_sub(_str_func,'Rig update: {}'.format(item)))
                _scene_path = mc.file(q=True, loc=True)
                if _scene_path:
                    try:
                        PATHUTIL.prepare_maya_scene_for_save(
                            _scene_path, mDat=PATHUTIL.get_project_mDat())
                    except PATHUTIL.PathWritePrepareError as err:
                        log.error(str(err))
                        continue
                mc.file(save=1)    
            else:
                log.info(log_sub(_str_func,'Rig up to date: {}'.format(item)))                

    if not exportObjs:
        log.info("No exportObjs passed....")
        exportObjs = mc.ls(sl=True)
        log.info(exportObjs)

    cameras = []
    exportCams = []

    addNamespaceSuffix = False
    exportFBXFile = False
    exportAsRig = False
    exportAsCutscene = False
    exportStatic = False

    log.info("mode check...")
    d_exportModes = {'export':1,
                     'cutscene':2,
                     'rig':3,
                     'static':4}

    if exportMode is not None:
        mode = d_exportModes[exportMode]

    #...get our objects...
    if not exportObjs:
        log.info("No exportObjs passed #2....")
        exportObjs = []

        _setMatchesRaw = mc.ls('*%s' % exportSetName, r=True) or []
        _setMatches = []
        for s in _setMatchesRaw:
            if s not in _setMatches:
                _setMatches.append(s)

        log.info("Export sets found (raw): {0}".format(_setMatchesRaw))
        log.info("Export sets found (deduped): {0}".format(_setMatches))

        for s in _setMatches:
            if not mc.objExists(s):
                log.warning("Missing export set: {0}".format(s))
                continue

            _setMembers = mc.sets(s, q=True) or []
            if not _setMembers:
                log.warning("Export set empty: {0}".format(s))
                continue

            _setTokens = s.split(':')
            _setNamespace = _setTokens[0] if len(_setTokens) == 2 else None
            _rootCandidates = []
            _skippedMissingMembers = []
            _skippedNamespaceMembers = []

            for m in _setMembers:
                if not mc.objExists(m):
                    _skippedMissingMembers.append(m)
                    continue
                _longPath = (mc.ls(m, l=True) or [m])[0]
                _dagTokens = [t for t in _longPath.split('|') if t]
                if not _dagTokens:
                    continue

                if _setNamespace:
                    _nsTokens = [t for t in _dagTokens if t.startswith('{0}:'.format(_setNamespace))]
                    if not _nsTokens:
                        _skippedNamespaceMembers.append(m)
                        continue
                    _candidate = _nsTokens[0]
                else:
                    _candidate = _dagTokens[0]

                if mc.objExists(_candidate) and _candidate not in _rootCandidates:
                    _rootCandidates.append(_candidate)

            log.info("Set [{0}] members: {1}".format(s, _setMembers))
            log.info("Set [{0}] root candidates: {1}".format(s, _rootCandidates))
            if _skippedMissingMembers:
                log.warning("Set [{0}] skipped missing members: {1}".format(s, _skippedMissingMembers))
            if _skippedNamespaceMembers:
                log.warning("Set [{0}] skipped members outside namespace [{1}]: {2}".format(s, _setNamespace, _skippedNamespaceMembers))

            if _setNamespace:
                _master = '{0}:master'.format(_setNamespace)
                if mc.objExists(_master):
                    _chosen = _master
                    log.info("Set [{0}] selected namespace master: {1}".format(s, _chosen))
                elif _rootCandidates:
                    _chosen = _rootCandidates[0]
                    log.warning("Set [{0}] namespace master missing, using fallback root: {1}".format(s, _chosen))
                else:
                    _chosen = None

                if _chosen and _chosen not in exportObjs:
                    exportObjs.append(_chosen)
                    log.info("Set [{0}] chose export context hint: {1} (bake/delete correlation, not post-delete DAG root)".format(s, _chosen))
                elif not _chosen:
                    log.error("Set [{0}] has no valid export root candidates. Members: {1}".format(s, _setMembers))
                continue

            _masterCandidates = [c for c in _rootCandidates if c.split('|')[-1] == 'master']
            _chosenRoots = _masterCandidates if _masterCandidates else _rootCandidates
            if not _chosenRoots:
                log.error("Set [{0}] has no valid export roots after candidate filtering.".format(s))
                continue
            if _masterCandidates:
                log.info("Set [{0}] selected non-namespaced master context hints: {1}".format(s, _masterCandidates))
            else:
                log.warning("Set [{0}] has no 'master' hints, using fallback context roots: {1}".format(s, _chosenRoots))
            for _chosen in _chosenRoots:
                if _chosen not in exportObjs:
                    exportObjs.append(_chosen)
                    log.info("Set [{0}] chose export context hint: {1} (bake/delete correlation, not post-delete DAG root)".format(s, _chosen))

    #...cam check...
    for obj in exportObjs:
        log.info("Obj Check: {0}".format(obj))
        if mc.listRelatives(obj, shapes=True, type='camera'):
            log.info("Camera: {0}".format(obj))
            mCam = cgmMeta.asMeta(obj)
            cameras.append(obj)            
            if mCam.p_parent and mCam.getConstraintsTo():
                log.info("Creating export cam...")                
                _new = bakeAndPrep.MakeExportCam(obj)
                exportCams.append( _new )
                cameras.append(_new)
                exportObjs.remove(obj)

    exportObjs += exportCams

    if mode == -1:
        log.info("unknown mode, attempting to auto detect")


        if len(exportObjs) > 1:
            log.info("More than one export obj found, setting cutscene mode: 2")
            mode = 2
        elif len(exportObjs) == 1:
            log.info("One export obj found, setting regular asset mode: 1")
            mode = 1
        else:
            log.info("Auto detection failed. Exiting.")
            return

    if mode > 0:
        exportFBXFile = True

    log.info("Mode: {0}".format(mode))    
    pprint.pprint(exportObjs)

    # Multiple export roots: only mode 1 (anim) needs the cutscene-style confirmation.
    # Modes 2–4 (cutscene / rig / static) are designed to handle multiple roots; mode 3 rig
    # must not block on a dialog (batch/mayapy has no user to click Yes — export silently aborts).
    if len(exportObjs) > 1 and mode == 1:
        log.info("Multi check (anim mode: offer cutscene-style multi export)")
        result = mc.confirmDialog(
            title='Multiple Object Selected',
                    message='Will export in cutscene mode, is this what you intended? If not, hit Cancel, select one object and try again.',
                    button=['Yes', 'Cancel'],
                    defaultButton='Yes',
                            cancelButton='Cancel',
                            dismissString='Cancel')

        if result != 'Yes':
            return False

        addNamespaceSuffix = True
        exportAsCutscene = True

    if mode== 2:
        log.info("mode 2 | Anim...")        
        addNamespaceSuffix = True
        exportAsCutscene = True
    if mode == 3:
        log.info("mode 3 | Rig...")                
        exportAsRig = True

    if mode == 4:
        log.info("mode 4 | Static..")                
        exportStatic = True

    if mode not in (1, 2):
        deleteMesh = False

    # make the relevant directories if they dont exist
    #categoryExportPath = os.path.normpath(os.path.join( self.exportDirectory, self.category))

    #log.info("category path...")
    #if not os.path.exists(categoryExportPath):
    #    os.mkdir(categoryExportPath)
    #exportAssetPath = os.path.normpath(os.path.join( categoryExportPath, self.assetList['scrollList'].getSelectedItem()))

    #log.info("asset path...")

    #if not os.path.exists(exportAssetPath):
    #    os.mkdir(exportAssetPath)
    log.info(log_msg(_str_func,"Pathcheck..."))
    if exportAsRig:
        exportAnimPath = exportAssetPath
    elif not exportAnimPath:
        log.info("Getting path...")
        _exportSubTypeDir = subType
        exportAnimPath = os.path.normpath(os.path.join(exportAssetPath, _exportSubTypeDir))
    log.info("exportPath: {0}".format(exportAnimPath))


    #pprint.pprint(vars())
    #return

    #if not os.path.exists(exportAnimPath):
        #log.info("making export anim path...")

        #os.mkdir(exportAnimPath)
        ## create empty file so folders are checked into source control
        #f = open(os.path.join(exportAnimPath, "filler.txt"),"w")
        #f.write("filler file")
        #f.close()

    if animationName is not None and str(animationName).strip().lower() in ('none', 'null'):
        animationName = None

    if animationName:
        if '.' in animationName:
            animationName = animationName.split('.')[0]
        # Only cutscene nests animationName under subtype (e.g. Animations/flow). Regular anim
        # export stays on exportAnimPath as built (e.g. .../Animations/), not .../Animations/base/.
        if exportAsCutscene and not exportStatic and not exportAsRig:
            exportAnimPath = os.path.normpath(os.path.join(exportAnimPath, animationName))

    pprint.pprint(vars())
    if exportAsCutscene:
        log.info("export as cutscene...")

    if not exportStatic and not exportAsRig and exportAnimPath:
        CGMOS.mkdir_recursive(PATHS.get_dir(exportAnimPath))

    exportFiles = []

    log.info("bake prep...")

    # rename for safety
    loc = mc.file(q=True, loc=True)
    base, ext = os.path.splitext(loc)
    bakedLoc = "%s_baked%s" % (base, ext)

    mc.file(rn=bakedLoc)

    if not bakeSetName:
        bakeSetName = cgmMeta.cgmOptionVar('cgm_bake_set', varType="string",defaultValue = 'bake_tdSet').getValue()
    if not deleteSetName:
        deleteSetName = cgmMeta.cgmOptionVar('cgm_delete_set', varType="string",defaultValue = 'delete_tdSet').getValue()
    if not exportSetName:
        exportSetName = cgmMeta.cgmOptionVar('cgm_export_set', varType="string",defaultValue = 'export_tdSet').getValue()  

    animList = SHOTS.AnimList()
    _effectiveExportName = _resolve_no_shot_export_name(exportName, noShotListExportName, animList)
    #find our minMax
    l_min = []
    l_max = []

    for shot in animList.shotList:
        l_min.append(shot[1][0])
        l_max.append(shot[1][1])

    if l_min:
        _start = min(l_min)
    else:
        _start = None

    if l_max:
        _end = max(l_max)
    else:
        _end = None

    log.info( log_sub(_str_func,'Bake | start: {0} | end: {1}'.format(_start,_end)) )
    if _start and _end:
        mc.playbackOptions(minTime=_start, maxTime=_end)


    #Bake Check -----------------------------------------------------------------------------------------------
    #if mc.objExists(bakeSetName) and mc.sets(bakeSetName, q=True):
    #    log.info("bake...")        
    if not exportStatic:
        try:
            bakeAndPrep.Bake(exportObjs,bakeSetName,startFrame= _start, endFrame= _end,sampleBy=sampleBy,
                             euler=euler, fixRotation=fixRotation, tangent=tangent,
                             reducer=reducer, simplify=simplify)
        except Exception:
            _ctx = dict(_ctx_base,
                        stage='bake',
                        bakeSetName=bakeSetName,
                        startFrame=_start,
                        endFrame=_end,
                        exportObjCount=len(exportObjs or []))
            log.exception("{0} | Bake stage failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
            return _finalize_failure('bake', 'Bake stage failed', _ctx)
    #else:
    #    log.info("bake skip...")



    try:
        if not cgmGEN.ensure_fbx_plugin(_str_func):
            _ctx = dict(_ctx_base, stage='fbx_export', plugin='fbxmaya')
            log.error("{0} | FBX plugin not ready (FBXExportFileVersion missing) | {1}".format(
                _str_func, _export_ctx_to_str(_ctx)))
            return _finalize_failure('fbx_export', 'FBX plugin not ready', _ctx)
    except Exception:
        _ctx = dict(_ctx_base, stage='fbx_export', plugin='fbxmaya')
        log.exception("{0} | Failed loading FBX plugin | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
        return _finalize_failure('fbx_export', 'Failed loading FBX plugin', _ctx)

    def _rig_fbx_export_to_path(exportPathAbs):
        """Rig FBX only: no FBXExportSplitAnimationIntoTakes (no takes)."""
        _dir = os.path.dirname(exportPathAbs)
        if _dir and not os.path.exists(_dir):
            log.info("making export dir... {0}".format(_dir))
            os.makedirs(_dir)
        cgmGEN.fbx_export_preamble(clear_takes=False)
        cgmGEN.fbx_export_selection(exportPathAbs)

    def _export_single_anim_fbx(exportFile, exportObj, animList, cameras):
        """Write one anim FBX at *exportFile*; FBX takes from shotList when present."""
        exportDir = os.path.split(exportFile)[0]
        mel.eval('FBXExportSplitAnimationIntoTakes -c')

        if exportObj not in cameras and animList and animList.shotList:
            for shot in animList.shotList:
                log.info(log_msg(_str_func, "shot..."))
                log.info(shot)
                mel.eval('FBXExportSplitAnimationIntoTakes -v \"{}\" {} {}'.format(
                    shot[0], shot[1][0], shot[1][1]))

        if not os.path.exists(exportDir):
            log.info("making export dir... {0}".format(exportDir))
            os.makedirs(exportDir)

        log.info('Export Command: FBXExport -f \"{}\" -s'.format(exportFile))
        try:
            cgmGEN.fbx_export_selection(exportFile)
        except Exception as err:
            return _finalize_fbx_export_error(err, exportFile, failure_label='FBX export failed',
                                              exportObj=exportObj)
        if animList and animList.shotList and exportObj not in cameras:
            for shot in animList.shotList:
                _record_export_result(shot[0], exportFile,
                                      (shot[1][0], shot[1][1]), exportObj=exportObj)
        else:
            _record_export_result(os.path.basename(exportFile), exportFile, exportObj=exportObj)
        return None

    # Rig + multiple export roots: prepare each root, then one FBX containing all hierarchies.
    # (Iterating per root would overwrite the same rig filename and run destructive cleanup between passes.)
    if exportAsRig and len(exportObjs) > 1:
        exportFile = os.path.normpath(os.path.join(exportAssetPath, exportName))
        log.info("{0} | Rig multi-root -> single FBX | path={1} | roots={2}".format(
            _str_func, exportFile, exportObjs))

        l_cleanup = []

        for obj in exportObjs:
            log.info(log_sub(_str_func, 'Rig multi prepare | {0}'.format(obj)))
            cgmObj = cgmMeta.validateObjArg(obj, noneValid=True)
            cgmObj.select()

            if cgmObj.isReferenced():
                try:
                    prepResult = bakeAndPrep.Prep(removeNamespace=removeNamespace,
                                                  deleteSetName=deleteSetName,
                                                  exportSetName=exportSetName,
                                                  zeroRoot=zeroRoot,
                                                  breakTextures=breakTextureLinks,
                                                  parentExportToWorld=parentExportToWorld)
                except Exception:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.exception("{0} | Prep stage failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Prep stage failed', _ctx)
                if prepResult is False:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.error("{0} | Prep stage returned failure | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Prep stage returned failure', _ctx)
                exportTransforms = mc.ls(sl=True)
                _exportMemberFallback = list(exportTransforms) if exportTransforms else []
            else:
                try:
                    exportTransforms = bakeAndPrep.export_prep_non_referenced(
                        obj,
                        deleteSetName=deleteSetName,
                        exportSetName=exportSetName,
                        removeNamespace=removeNamespace,
                        zeroRoot=zeroRoot,
                        parentExportToWorld=parentExportToWorld,
                        _str_func='{0}|nonref_prep'.format(_str_func))
                except Exception:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.exception("{0} | Non-referenced prep failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Non-referenced prep failed', _ctx)
                if not exportTransforms:
                    _ctx = dict(_ctx_base, stage='select', exportObj=obj)
                    log.error("{0} | No export targets after non-referenced prep | {1}".format(
                        _str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('select', 'No export targets after non-referenced prep', _ctx)
                _exportMemberFallback = list(exportTransforms)

            mObjs = cgmMeta.asMeta(exportTransforms)

            if deleteMesh:
                _exportMemberProtect = bakeAndPrep.export_set_member_paths_set(exportSetName)
                bakeAndPrep.delete_mesh_under_transforms(
                    mObjs,
                    protected_paths=_exportMemberProtect,
                    _str_func='{0}|rig_multi_deleteMesh'.format(_str_func))
            exportTransforms = _export_transforms_after_mesh_strip(
                deleteMesh, exportTransforms, obj, fallback_members=_exportMemberFallback)
            if deleteMesh and not exportTransforms:
                _ctx = dict(_ctx_base, stage='select', exportObj=obj)
                log.error("{0} | No export DAG to select after mesh strip | {1}".format(
                    _str_func, _export_ctx_to_str(_ctx)))
                return _finalize_failure('select', 'No export DAG to select after mesh strip', _ctx)

            l_cleanup.append((cgmObj, exportTransforms))

        mc.select(cl=True)
        for _cgmObj, exportTransforms in l_cleanup:
            if isinstance(exportTransforms, (list, tuple)):
                for _n in exportTransforms:
                    if _n and mc.objExists(_n):
                        mc.select(_n, add=True)
            else:
                if exportTransforms and mc.objExists(exportTransforms):
                    mc.select(exportTransforms, add=True)
        _selFlat = mc.ls(sl=True)
        if _selFlat:
            mc.select(_selFlat, hi=True)

        log.info("Heirarchy (rig multi combined)...")
        for i, o in enumerate(mc.ls(sl=1)):
            log.info("{0} | {1}".format(i, o))

        if exportFBXFile:
            log.info('Export Command: FBXExport -f \"{}\" -s (rig multi, no takes)'.format(exportFile))
            try:
                _rig_fbx_export_to_path(exportFile)
            except Exception as err:
                return _finalize_fbx_export_error(err, exportFile, failure_label='FBX export failed',
                                                  exportObjs=exportObjs)
            _record_export_result(os.path.basename(exportFile), exportFile,
                                  exportObj=', '.join(exportObjs))

        if len(exportObjs) > 1 and removeNamespace:
            for _cgmObj, exportTransforms in l_cleanup:
                try:
                    mc.delete(_cgmObj.mNode)
                except Exception:
                    _ctx = dict(_ctx_base, stage='post_cleanup', exportObj=_cgmObj.mNode, exportFile=exportFile)
                    log.exception("{0} | Failed export cleanup delete (root) | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                try:
                    if isinstance(exportTransforms, (list, tuple)):
                        mc.delete(exportTransforms)
                    else:
                        mc.delete(exportTransforms)
                except Exception:
                    _ctx = dict(_ctx_base, stage='post_cleanup', exportTransforms=exportTransforms, exportFile=exportFile)
                    log.exception("{0} | Failed export cleanup delete (transforms) | {1}".format(
                        _str_func, _export_ctx_to_str(_ctx)))

        return _finish_export_scene_success()

    for obj in exportObjs:			
        log.info( log_sub(_str_func,'On: {0}'.format(obj)) )
        #print(obj)
        cgmObj = cgmMeta.validateObjArg(obj,noneValid=True)

        assetName = obj.split(':')[0].split('|')[-1]
        if exportStatic:
            exportFile = os.path.normpath(os.path.join(exportAssetPath, "{}.fbx".format(cgmObj.p_nameBase)) )
        else:
            exportFile = os.path.normpath(os.path.join(exportAnimPath, _effectiveExportName) )

        if( addNamespaceSuffix ):
            exportFile = exportFile.replace(".fbx", "_%s.fbx" % assetName )
        if( exportAsRig ):
            # {refNamespace}_rig.fbx (e.g. CrateBase_rig.fbx) — exportName stem is not the ref prefix.
            _stem, _ext = os.path.splitext(exportName)
            if not _ext:
                _ext = '.fbx'
            _rigFileName = '{0}_rig{1}'.format(assetName, _ext)
            exportFile = os.path.normpath(os.path.join(exportAssetPath, _rigFileName))

        cgmObj.select()

        log.info("Export: {}".format(exportFile))

        if exportStatic:
            # Break texture links for static export if enabled
            if breakTextureLinks:
                log.info(log_sub(_str_func, "Breaking texture links for static export"))
                try:
                    bakeAndPrep.BreakTextureLinks()
                except Exception:
                    _ctx = dict(_ctx_base, stage='prep', exportFile=exportFile, exportObj=obj, breakTextureLinks=breakTextureLinks)
                    log.exception("{0} | Failed breaking texture links for static export | {1}".format(
                        _str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Failed breaking texture links for static export', _ctx)
            
            if(exportFBXFile):
                exportDir = os.path.split(exportFile)[0]
                if not os.path.exists(exportDir):
                    log.info("making export dir... {0}".format(exportDir))
                    os.makedirs(exportDir)

                # log.info('Export Command: FBXExport -f \"{}\" -s'.format(exportFile))
                # mel.eval('FBXExport -f \"{}\" -s'.format(exportFile.replace('\\', '/')))

                if animList:
                    mel.eval('FBXExportSplitAnimationIntoTakes -c')

                    # if obj not in cameras:#...cameras we don't want in takes
                    for shot in animList.shotList:
                        log.info( log_msg(_str_func, "shot..."))
                        log.info(shot)
                        mel.eval('FBXExportSplitAnimationIntoTakes -v \"{}\" {} {}'.format(shot[0], shot[1][0], shot[1][1]))

                    exportDir = os.path.split(exportFile)[0]
                    if not os.path.exists(exportDir):
                        log.info("making export dir... {0}".format(exportDir))
                        os.makedirs(exportDir)

                log.info('Export Command: FBXExport -f \"{}\" -s'.format(exportFile))
                try:
                    cgmGEN.fbx_export_selection(exportFile)
                except Exception as err:
                    return _finalize_fbx_export_error(err, exportFile, failure_label='Static FBX export failed',
                                                      exportObj=obj)
                if animList and animList.shotList:
                    for shot in animList.shotList:
                        _record_export_result(shot[0], exportFile,
                                              (shot[1][0], shot[1][1]), exportObj=obj)
                else:
                    _record_export_result(os.path.basename(exportFile), exportFile, exportObj=obj)

        else:
            if cgmObj.isReferenced():
                try:
                    prepResult = bakeAndPrep.Prep(removeNamespace=removeNamespace,
                                                  deleteSetName=deleteSetName,
                                                  exportSetName=exportSetName,
                                                  zeroRoot=zeroRoot,
                                                  breakTextures=breakTextureLinks,
                                                  parentExportToWorld=parentExportToWorld)
                except Exception:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.exception("{0} | Prep stage failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Prep stage failed', _ctx)
                if prepResult is False:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.error("{0} | Prep stage returned failure | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Prep stage returned failure', _ctx)
                exportTransforms = mc.ls(sl=True)
                _exportMemberFallback = list(exportTransforms) if exportTransforms else []
            else:
                try:
                    exportTransforms = bakeAndPrep.export_prep_non_referenced(
                        obj,
                        deleteSetName=deleteSetName,
                        exportSetName=exportSetName,
                        removeNamespace=removeNamespace,
                        zeroRoot=zeroRoot,
                        parentExportToWorld=parentExportToWorld,
                        _str_func='{0}|nonref_prep'.format(_str_func))
                except Exception:
                    _ctx = dict(_ctx_base, stage='prep', exportObj=obj, removeNamespace=removeNamespace, zeroRoot=zeroRoot)
                    log.exception("{0} | Non-referenced prep failed | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('prep', 'Non-referenced prep failed', _ctx)
                if not exportTransforms:
                    _ctx = dict(_ctx_base, stage='select', exportObj=obj)
                    log.error("{0} | No export targets after non-referenced prep | {1}".format(
                        _str_func, _export_ctx_to_str(_ctx)))
                    return _finalize_failure('select', 'No export targets after non-referenced prep', _ctx)
                _exportMemberFallback = list(exportTransforms)

            mObjs = cgmMeta.asMeta(exportTransforms)

            if deleteMesh:
                _exportMemberProtect = bakeAndPrep.export_set_member_paths_set(exportSetName)
                bakeAndPrep.delete_mesh_under_transforms(
                    mObjs,
                    protected_paths=_exportMemberProtect,
                    _str_func='{0}|deleteMesh'.format(_str_func))
            exportTransforms = _export_transforms_after_mesh_strip(
                deleteMesh, exportTransforms, obj, fallback_members=_exportMemberFallback)
            if deleteMesh and not exportTransforms:
                _ctx = dict(_ctx_base, stage='select', exportObj=obj)
                log.error("{0} | No export DAG to select after mesh strip | {1}".format(
                    _str_func, _export_ctx_to_str(_ctx)))
                return _finalize_failure('select', 'No export DAG to select after mesh strip', _ctx)

            mc.select(exportTransforms, hi=True)		

            log.info("Heirarchy...")

            for i,o in enumerate(mc.ls(sl=1)):
                log.info("{0} | {1}".format(i,o))

            if(exportFBXFile):
                # Rig exports are always single-file exports. Even if the project option
                # is enabled, skip per-shot file splitting for rig mode.
                # Cutscene or single-root anim: per-shot FBXs sit in exportDir only (no extra stem folder).
                # Multi-root non-cutscene: nest under export stem so shot names cannot collide across assets.
                if (exportShotsToIndividualFiles or exportAsCutscene) and not exportAsRig:
                    exportDir = os.path.split(exportFile)[0]

                    baseName = os.path.splitext(os.path.basename(exportFile))[0]
                    if exportAsCutscene or len(exportObjs) == 1:
                        baseDir = exportDir
                    else:
                        baseDir = os.path.join(exportDir, baseName)
                    if not os.path.exists(baseDir):
                        log.info("making export dir... {0}".format(baseDir))
                        os.makedirs(baseDir)

                    if obj not in cameras:
                        if animList.shotList:
                            cgmGEN.fbx_export_preamble(clear_takes=True)
                            for shot in animList.shotList:
                                shotName = shot[0]
                                s, e = shot[1][0], shot[1][1]
                                log.info(log_msg(_str_func, "shot..."))
                                log.info((shotName, (s, e)))

                                safe = CORESTRING.stripInvalidChars(shotName)
                                if exportAsCutscene:
                                    # e.g. AN_CrateHarness_flow_1_resetPadCrane_Crane.fbx (shot_takeNamespace)
                                    _fbxStem = CORESTRING.stripInvalidChars('{0}_{1}'.format(safe, assetName))
                                    outFile = os.path.join(baseDir, "{}.fbx".format(_fbxStem)).replace('\\', '/')
                                else:
                                    outFile = os.path.join(baseDir, "{}.fbx".format(safe)).replace('\\', '/')

                                # Set time range for this shot and export
                                cgmGEN.fbx_export_preamble(clear_takes=True)
                                cgmGEN.fbx_export_shot_time_range(s, e)

                                log.info('Export Command: FBXExport -f \"{}\" -s'.format(outFile))
                                try:
                                    cgmGEN.fbx_export_selection(outFile)
                                except Exception as err:
                                    return _finalize_fbx_export_error(err, outFile, failure_label='Shot FBX export failed',
                                                                  exportObj=obj, shotName=shotName)
                                _record_export_result(shotName, outFile, (s, e), exportObj=obj)
                        else:
                            log.warning("{0} | No shot list; falling back to single FBX | {1}".format(
                                _str_func, exportFile))
                            _fbxErr = _export_single_anim_fbx(exportFile, obj, animList, cameras)
                            if _fbxErr is not None:
                                return _fbxErr

                else:
                    exportDir = os.path.split(exportFile)[0]
                    if exportAsRig:
                        log.info('Export Command: FBXExport -f \"{}\" -s (rig, no takes)'.format(exportFile))
                        try:
                            _rig_fbx_export_to_path(exportFile)
                        except Exception as err:
                            return _finalize_fbx_export_error(err, exportFile, failure_label='FBX export failed',
                                                              exportObj=obj)
                        _record_export_result(os.path.basename(exportFile), exportFile, exportObj=obj)
                    else:
                        _fbxErr = _export_single_anim_fbx(exportFile, obj, animList, cameras)
                        if _fbxErr is not None:
                            return _fbxErr

                if len(exportObjs) > 1 and removeNamespace:
                    # Deleting the exported transforms in case another file has duplicate export names
                    mc.delete(cgmObj.mNode)
                    try:
                        mc.delete(exportTransforms)
                    except Exception:
                        _ctx = dict(_ctx_base, stage='post_cleanup', exportObj=obj, exportFile=exportFile)
                        log.exception("{0} | Failed export cleanup delete | {1}".format(_str_func, _export_ctx_to_str(_ctx)))

    if exportFBXFile and not _export_results:
        _ctx = dict(_ctx_base, stage='fbx_export', exportObjs=exportObjs)
        log.error("{0} | No FBX files written | {1}".format(_str_func, _export_ctx_to_str(_ctx)))
        return _finalize_failure('fbx_export', 'No FBX files written', _ctx)

    return _finish_export_scene_success()



def PurgeOptionVars():

    optionVarProjectStore       = cgmMeta.cgmOptionVar("cgmVar_projectCurrent", varType = "string")
    optionVarProjectStore.purge()

    optionVarLastAssetStore     = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_asset", varType = "string")
    optionVarLastAssetStore.purge()

    optionVarLastAnimStore      = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_animation", varType = "string")
    optionVarLastAnimStore.purge()

    optionVarLastVariationStore = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_variation", varType = "string")
    optionVarLastVariationStore.purge()

    optionVarLastVersionStore   = cgmMeta.cgmOptionVar("cgmVar_sceneUI_last_version", varType = "string")
    optionVarLastVersionStore.purge()

    showAllFilesStore           = cgmMeta.cgmOptionVar("cgmVar_sceneUI_show_all_files", defaultValue = 0)
    showAllFilesStore.purge()

    removeNamespaceStore        = cgmMeta.cgmOptionVar("cgmVar_sceneUI_remove_namespace", defaultValue = 0)
    removeNamespaceStore.purge()

    categoryStore               = cgmMeta.cgmOptionVar("cgmVar_sceneUI_category", defaultValue = 0)
    categoryStore.purge()

    alwaysSendReferenceFiles    = cgmMeta.cgmOptionVar("cgmVar_sceneUI_alwaysSendReferences", defaultValue = 0)
    alwaysSendReferenceFiles.purge()