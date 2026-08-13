"""
------------------------------------------
arrange_utils: cgm.core.lib.distance_utils
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

"""
__MAYALOCAL = 'ARRANGE'

# From Python =============================================================
import copy
import re
import sys
import os
import pprint

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# From Maya =============================================================
import maya.cmds as mc
import maya.mel as mel

# From Red9 =============================================================

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGEN
from cgm.core.cgmPy import validateArgs as VALID
import cgm.core.cgmPy.path_Utils as PATHS

#>>> Utilities
#===================================================================
def walk_below_dir(arg = None, tests = None,uiStrings = True,
                   fileTest=None, fileCount = True, hardCap = 20,
                   skipRoot = True, 
                   l_mask=['.svn','pristine']):
    """
    Walk directory for pertinent info

    :parameters:

    :returns
        _d_modules, _d_categories, _l_unbuildable
        _d_modules(dict) - keys to modules
        _d_categories(dict) - categories to list of entries
        _l_unbuildable(list) - list of unbuildable modules
    """
    _str_func = 'walk_below'       
    
    _b_debug = log.isEnabledFor(logging.DEBUG)

    _path = PATHS.Path(arg)
    if not _path.exists():
        log.debug(cgmGEN.logString_msg(_str_func,"Path doesn't exists: {0}".format(arg)))
        return False
    
    _l_duplicates = []
    _l_unbuildable = []
    _base = _path.split()[-1]
    #_d_files =  {}
    #_d_modules = {}
    #_d_import = {}
    #_d_categories = {}
    _d_levels = {}
    _d_dir = {}
    _l_keys = []
    
    if uiStrings:
        log.debug("|{0}| >> uiStrings on".format(_str_func))           
        _d_uiStrings = {}
        _l_uiStrings = []
    
    log.debug("|{0}| >> Checking base: {1} | path: {2}".format(_str_func,_base,_path))   
    _i = 0
    
    _rootKey = None
    for root, dirs, files in os.walk(_path.asString(), True, None):

        if hardCap and _i > hardCap:
            log.warning(cgmGEN.logString_msg(_str_func,"hit cap...{0}".format(hardCap)))
            break

        _rootPath = PATHS.Path(root)
        _split = _rootPath.split()
        _subRoot = _split[-1]
        _splitUp = _split[_split.index(_base):]
        _depth = len(_splitUp) - 1
        
        if _path == root:
            _rootKey = _split[-1]

            if skipRoot:
                log.debug(cgmGEN.logString_msg(_str_func,"Skipping root"))
                continue

        log.debug(cgmGEN.logString_sub(_str_func,_subRoot))
        
        if _subRoot[0] in ['.']:
            log.debug(cgmGEN.logString_msg(_str_func,"Skipping...{0}".format(_subRoot)))
            continue
        elif _subRoot in l_mask:
            log.debug(cgmGEN.logString_msg(_str_func,"Masked...{0}".format(_subRoot)))
            continue
        
        if l_mask:
            _break = False
            for v in l_mask:
                if v in _splitUp:
                    log.debug(cgmGEN.logString_msg(_str_func,"Masked...{0}".format(_rootPath)))
                    _break = True
                    continue
            
            if _break:
                continue
        
        
        log.debug("|{0}| >> On subroot: {1} | path: {2}".format(_str_func,_subRoot,root))   
        #log.debug("|{0}| >> On split up: {1}".format(_str_func,_splitUp))
        #log.debug("|{0}| >> On split: {1}".format(_str_func,_split))
        
        _splitRoot = _split[_split.index(_rootKey)+1:]
        _key = '|||'.join(_splitRoot)#_rootPath.asString()
        _l_keys.append(_key)
        

            
        _d_dir[_key] = {'depth':_depth,
                        'split':_split,
                        'splitRoot':_splitRoot,
                        'token':_subRoot,
                        'pyString':_rootPath.asFriendly(),
                        'raw':root,
                        'mPath':_rootPath,
                        'dir':dirs,
                        'index':_i,
                        'key':_key,
                        'files':files}
        
        if uiStrings:
            if _depth > 1:
                _Root = _splitRoot[:-1]
                _Root.reverse()
                _uiString = '  '*(_depth) + " {0} ".format(_subRoot) + '    \\\\' + '.'.join(_Root)
                
                #_reverseRoot = _splitRoot[:-1]
                #_reverseRoot.reverse()
                #_uiString = '   '*(_depth) + '>' + '--' + '{0}'.format(_subRoot) + "      {0}".format('.'.join(_reverseRoot))
            else:
                _uiString = " || "+ _subRoot
            
            if files:
                if fileTest and fileTest.get('endsWith'):
                    _cnt = 0
                    for f in files:
                        if f.endswith(fileTest.get('endsWith')):
                            _cnt +=1
                elif fileCount:
                    _cnt = len(files)
                    
                _uiString = _uiString + ' ({0})'.format(_cnt)
                    
                
            #if files:
            #    _uiString = _uiString + ' cnt: {0}'.format(len(files))
            
            #if _uiString in _l_uiStrings:
            #    _uiString = _uiString+ "[dup | {0}]".format(_i)
                
            _l_uiStrings.append(_uiString)
            _d_uiStrings[_i] = _uiString
            
            _d_dir[_key]['uiString'] = _uiString
            
        if not _d_levels.get(_depth):
            _d_levels[_depth] = []
            
        _d_levels[_depth].append(_key)
        
        _i+=1
        
    for k,d in list(_d_dir.items()):
        if d.get('dir'):
            d['tokensSub'] = {}
            for subD in d.get('dir'):
                for k,d2 in list(_d_dir.items()):
                    if d2.get('token') == subD:
                        d['tokensSub'][k] = subD

    if _b_debug:
        print((cgmGEN.logString_sub(_str_func,"Levels")))
        pprint.pprint(_d_levels)
        print((cgmGEN.logString_sub(_str_func,"Dat")))
        pprint.pprint(_d_dir)
        
        if uiStrings:
            print((cgmGEN.logString_sub(_str_func,'Ui Strings')))
            #pprint.pprint(_d_uiStrings)
            
            for s in _l_uiStrings:
                print(s)        
        

    if _l_duplicates and _b_debug:
        log.debug(cgmGEN._str_subLine)
        log.debug("|{0}| >> DUPLICATE ....".format(_str_func))
        for m in _l_duplicates:
            print(m)
        raise Exception("Must resolve")
    
    #log.debug("|{0}| >> Found {1} modules under: {2}".format(_str_func,len(_d_files.keys()),_path))     
    return _d_dir, _d_levels, _l_keys


#>>> Global output prepare for write
#===================================================================
_non_writable_export_paths = []


class PathWritePrepareError(Exception):
    """Raised when a disk path cannot be prepared for write (P4 or local permissions)."""

    def __init__(self, path, reason=None):
        self.path = os.path.normpath(path) if path else path
        self.reason = reason or 'Path is not writable'
        _msg = '{0}: {1} — check out in Perforce (p4 edit) or clear read-only'.format(
            self.reason, self.path)
        super(PathWritePrepareError, self).__init__(_msg)


def _resolve_use_p4_for_write(mDat=None, use_p4=None):
    """Resolve P4 opt-in: explicit use_p4, else project versionControl when mDat provided."""
    if use_p4 is not None:
        return bool(use_p4)
    if mDat is None:
        return False
    try:
        import cgm.core.tools.lib.project_utils as PU
        return PU.project_uses_perforce(mDat)
    except Exception:
        return False


def _prepare_p4_for_write(path, p4_user, p4_client, confirm=True, _str_func='prepare_output_for_write'):
    """
    Query fstat, block out-of-date depot files, confirm before edit/add.
    Raises PathWritePrepareError on failure or user cancel.
    """
    import cgm.core.lib.perforce as P4UTIL

    _stat = P4UTIL.query_file_status(path, p4_user=p4_user, p4_client=p4_client)
    if _stat.get('error') and not _stat.get('notInClient') and not _stat.get('notOnDepot'):
        raise PathWritePrepareError(path, reason=_stat.get('error'))

    if _stat.get('notInClient'):
        raise PathWritePrepareError(path, reason='Path not in Perforce client view')

    if _stat.get('lockedByOther'):
        _detail = _stat.get('otherLock') or _stat.get('otherOpen') or 'another user'
        raise PathWritePrepareError(
            path, reason='File locked or open elsewhere ({0})'.format(_detail))

    if _stat.get('onDepot') and _stat.get('outOfDate'):
        _have = _stat.get('haveRev')
        _head = _stat.get('headRev')
        _rev_msg = 'have {0}, head {1}'.format(_have, _head) if _have is not None else 'not at head'
        if confirm:
            mc.confirmDialog(
                title='Perforce — file out of date',
                message=(
                    'Cannot save: workspace file is not at the latest depot revision.\n\n'
                    '{0}\n\n{1}\n\nSync the file in Perforce, then save again.'
                ).format(path, _rev_msg),
                button=['OK'],
                defaultButton='OK',
            )
        raise PathWritePrepareError(
            path, reason='File out of date ({0}) — sync before save'.format(_rev_msg))

    if _stat.get('checkedOut'):
        return

    _needs_add = bool(_stat.get('notOnDepot') and _stat.get('inClient'))
    _needs_edit = bool(_stat.get('onDepot') and not _stat.get('checkedOut'))

    if not _needs_add and not _needs_edit:
        return

    if confirm:
        _summary = P4UTIL.format_file_status(_stat)
        if _needs_add:
            _title = 'Perforce add'
            _btn = 'Add'
            _msg = 'Add this file to Perforce before saving?\n\n{0}\n\n{1}'.format(path, _summary)
        else:
            _title = 'Perforce checkout'
            _btn = 'Checkout'
            _msg = 'Check out this file for edit before saving?\n\n{0}\n\n{1}'.format(path, _summary)
        _result = mc.confirmDialog(
            title=_title,
            message=_msg,
            button=[_btn, 'Cancel'],
            defaultButton='Cancel',
            cancelButton='Cancel',
            dismissString='Cancel',
        )
        if _result != _btn:
            raise PathWritePrepareError(path, reason='Save cancelled')

    _res = P4UTIL.edit_or_add(path, p4_user=p4_user, p4_client=p4_client)
    if not _res.get('ok'):
        raise PathWritePrepareError(
            path, reason=_res.get('stderr') or 'Perforce checkout failed')
    log.info('{0} || P4 {1}: {2}'.format(
        _str_func, _res.get('action') or 'edit_or_add', path))


def prepare_output_for_write(path, mDat=None, use_p4=None, p4_user=None, p4_client=None,
                             confirm_p4=True, _str_func='prepare_output_for_write'):
    """
    Global prepare before writing a cgm output file (project .cfg, BaseDat, export targets).

    When use_p4 is None and mDat is provided, uses project versionControl (perforce gate).
    When P4 is connected: fstat first (block if out of date), confirm before edit/add.
    When P4 is unavailable, skips P4 silently (optional layer — no behavior change).
    Returns normalized path string.
    """
    if not path:
        raise PathWritePrepareError(path, reason='Path is empty')

    _norm = os.path.normpath(path)
    _parent = os.path.dirname(_norm)
    if _parent and not os.path.isdir(_parent):
        try:
            os.makedirs(_parent)
            log.info('{0} || created directory: {1}'.format(_str_func, _parent))
        except Exception as err:
            raise PathWritePrepareError(
                _norm, reason='Cannot create directory ({0})'.format(err))

    if _resolve_use_p4_for_write(mDat, use_p4):
        import cgm.core.lib.perforce as P4UTIL
        _user, _client = P4UTIL.resolve_connection(p4_user, p4_client)
        if _user and _client and P4UTIL.is_available(p4_user=_user, p4_client=_client):
            _prepare_p4_for_write(
                _norm, _user, _client, confirm=confirm_p4, _str_func=_str_func)
        else:
            log.debug('{0} || P4 skipped (not connected) — writability check only'.format(_str_func))

    if os.path.exists(_norm):
        if not os.path.isfile(_norm):
            raise PathWritePrepareError(_norm, reason='Path exists but is not a file')
        if not os.access(_norm, os.W_OK):
            raise PathWritePrepareError(_norm, reason='File is not writable')
    elif _parent and not os.access(_parent, os.W_OK):
        raise PathWritePrepareError(_norm, reason='Directory is not writable')

    return _norm


def prepare_path_for_write(path, use_p4=False, p4_user=None, p4_client=None, _str_func='prepare_path_for_write'):
    """Prepare path for write with explicit use_p4 flag. Prefer prepare_output_for_write(mDat=)."""
    return prepare_output_for_write(
        path, use_p4=use_p4, p4_user=p4_user, p4_client=p4_client, _str_func=_str_func)


#>>> Export output path helpers (FBX export)
#===================================================================


class ExportOutputNotWritableError(Exception):
    """Raised when an FBX export target path cannot be written."""

    def __init__(self, path, reason=None):
        self.path = os.path.normpath(path) if path else path
        self.reason = reason or 'Export output is not writable'
        _msg = '{0}: {1} — check out in Perforce (p4 edit) or clear read-only'.format(
            self.reason, self.path)
        super(ExportOutputNotWritableError, self).__init__(_msg)


def clear_non_writable_export_paths():
    """Reset session list of non-writable export paths (call at batch start)."""
    global _non_writable_export_paths
    _non_writable_export_paths = []


def record_non_writable_export_path(path):
    """Track a non-writable export path for batch summary reporting."""
    global _non_writable_export_paths
    _norm = os.path.normpath(path) if path else path
    if _norm and _norm not in _non_writable_export_paths:
        _non_writable_export_paths.append(_norm)


def get_non_writable_export_paths():
    """Return copy of non-writable export paths recorded this session."""
    return list(_non_writable_export_paths)


def _fbx_export_sidecar_candidates(finalPath):
    """Known FBX plugin sidecar paths left after a failed overwrite."""
    _norm = os.path.normpath(finalPath)
    _stem, _ext = os.path.splitext(_norm)
    _candidates = [
        _norm + '.bak',
        '{0}.bak'.format(_stem),
    ]
    if _ext.lower() != '.fbx':
        _candidates.append('{0}.fbx.bak'.format(_stem))
    _seen = set()
    _out = []
    for _c in _candidates:
        if _c not in _seen:
            _seen.add(_c)
            _out.append(_c)
    return _out


def cleanup_fbx_export_sidecars(finalPath, _str_func='cleanup_fbx_export_sidecars'):
    """Remove stale FBX .bak sidecars when they are deletable (best-effort)."""
    _removed = []
    for _sidecar in _fbx_export_sidecar_candidates(finalPath):
        if not os.path.isfile(_sidecar):
            continue
        if not os.access(_sidecar, os.W_OK):
            log.debug("{0} || sidecar not deletable, skipping: {1}".format(_str_func, _sidecar))
            continue
        try:
            os.remove(_sidecar)
            _removed.append(_sidecar)
            log.info("{0} || removed stale export sidecar: {1}".format(_str_func, _sidecar))
        except Exception as err:
            log.warning("{0} || failed removing sidecar {1} | err={2}".format(_str_func, _sidecar, err))
    return _removed


def check_export_output_writable(finalPath, _str_func='check_export_output_writable'):
    """
    Ensure FBX export target is writable before FBXExport runs.
    Creates parent directory, cleans editable sidecars, raises ExportOutputNotWritableError if not writable.
    Returns normalized path string with forward slashes.
    """
    if not finalPath:
        raise ExportOutputNotWritableError(finalPath, reason='Export path is empty')

    _norm = os.path.normpath(finalPath)
    _parent = os.path.dirname(_norm)
    if _parent and not os.path.isdir(_parent):
        try:
            os.makedirs(_parent)
            log.info("{0} || created export directory: {1}".format(_str_func, _parent))
        except Exception as err:
            raise ExportOutputNotWritableError(
                _norm,
                reason='Cannot create export directory ({0})'.format(err))

    cleanup_fbx_export_sidecars(_norm, _str_func=_str_func)

    if os.path.exists(_norm):
        if not os.path.isfile(_norm):
            raise ExportOutputNotWritableError(_norm, reason='Export path exists but is not a file')
        if not os.access(_norm, os.W_OK):
            record_non_writable_export_path(_norm)
            raise ExportOutputNotWritableError(_norm, reason='Existing export file is read-only')
    else:
        if _parent and not os.access(_parent, os.W_OK):
            record_non_writable_export_path(_norm)
            raise ExportOutputNotWritableError(
                _norm,
                reason='Export directory is not writable')

    return _norm.replace('\\', '/')

