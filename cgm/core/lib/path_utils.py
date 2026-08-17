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
# Save flow contract (paths first):
#   Once the output path is known, call prepare_* BEFORE expensive work
#   (scene queries, pose capture, skin gather, CCL build, etc.) so P4
#   checkout / writability dialogs appear immediately. Low-level writers
#   may accept skip_prepare=True when the caller already prepared.
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


def get_project_mDat():
    """Loaded cgm Project dat from cgmVar_projectCurrent (None if no project cfg open)."""
    try:
        import cgm.core.cgm_Meta as cgmMeta
        _path = cgmMeta.cgmOptionVar('cgmVar_projectCurrent', defaultValue='').getValue()
        if not _path or not os.path.exists(_path):
            return None
        import cgm.core.tools.Project as PROJECT
        return PROJECT.data(filepath=_path)
    except Exception:
        return None


def path_under_root(path, root):
    """True when path is under root (Windows-safe commonpath)."""
    if not path or not root:
        return False
    try:
        _norm = os.path.normpath(path)
        _root = os.path.normpath(root)
        return os.path.commonpath([_norm, _root]) == _root
    except ValueError:
        return False


def path_in_p4_scope(path, mDat, extra_roots=()):
    """
    True when path should get P4 prepare within a perforce-enabled project.
    Call only after project_uses_perforce(mDat) is confirmed.
    """
    if not path:
        return False

    for _root in extra_roots or ():
        if path_under_root(path, _root):
            return True

    if mDat:
        try:
            _paths = mDat.userPaths_get() or {}
            for _key in ('content', 'root'):
                if path_under_root(path, _paths.get(_key)):
                    return True
        except Exception:
            pass

    try:
        import cgm.core.lib.perforce as P4UTIL
        _user, _client = P4UTIL.resolve_connection()
        if _user and _client and P4UTIL.is_available(p4_user=_user, p4_client=_client):
            return P4UTIL.is_under_client(path, p4_user=_user, p4_client=_client)
    except Exception:
        pass

    return False


def _path_looks_depot_related(path, mDat=None):
    """Heuristic for non-P4-mode read-only hint (fstat only, no checkout)."""
    if not path:
        return False

    if mDat:
        try:
            _paths = mDat.userPaths_get() or {}
            for _key in ('content', 'root'):
                if path_under_root(path, _paths.get(_key)):
                    return True
        except Exception:
            pass

    try:
        import cgm.core.lib.perforce as P4UTIL
        if not P4UTIL.is_available():
            return False
        _user, _client = P4UTIL.resolve_connection()
        if _user and _client:
            return P4UTIL.is_under_client(path, p4_user=_user, p4_client=_client)
    except Exception:
        pass

    return False


def _maybe_warn_p4_writability_hint(path, mDat=None, reason=None, p4_mode=False, p4_disconnected=False):
    """
    One-button warning when save failed on read-only file that may be Perforce-related.
    Never runs checkout — hint only.
    """
    if not path or not os.path.exists(path):
        return
    if os.access(path, os.W_OK):
        return
    if not _path_looks_depot_related(path, mDat=mDat):
        return

    if p4_mode and p4_disconnected:
        _body = (
            'File is not writable:\n\n{0}\n\n'
            'Project versionControl is Perforce but cgmP4 is not connected.\n'
            'Connect in cgmP4, check out the file manually, or clear read-only.'
        ).format(path)
    elif p4_mode:
        _body = (
            'File is not writable:\n\n{0}\n\n'
            'Check out in cgmP4 or P4V (p4 edit), or clear read-only.'
        ).format(path)
    else:
        _body = (
            'File is not writable:\n\n{0}\n\n'
            'It may be read-only from Perforce. Check out in P4V / cgmP4, or set '
            'Project General → versionControl to Perforce for checkout prompts on save.'
        ).format(path)

    if reason:
        _body = '{0}\n\n({1})'.format(_body, reason)

    mc.confirmDialog(
        title='Cannot save — file not writable',
        message=_body,
        button=['OK'],
        defaultButton='OK',
    )


def _resolve_use_p4_for_path(path, mDat=None, extra_roots=(), assume_in_scope=False):
    """Explicit use_p4 for a path: True only when project P4 mode and path in scope."""
    if not mDat:
        return False
    try:
        import cgm.core.tools.lib.project_utils as PU
        if not PU.project_uses_perforce(mDat):
            return False
    except Exception:
        return False
    if assume_in_scope:
        return True
    return path_in_p4_scope(path, mDat, extra_roots=extra_roots)


def prepare_paths_for_write(paths, mDat=None, confirm_p4=True, extra_roots=(),
                            assume_in_scope=False, _str_func='prepare_paths_for_write'):
    """
    Prepare one or more output paths; P4 only when project perforce mode and path in scope.

    Call as soon as the path(s) are known — before heavy save work — so checkout /
    writability prompts are not delayed by scene queries or data gathering.
    """
    _out = []
    for _p in paths or []:
        if not _p:
            continue
        _use_p4 = _resolve_use_p4_for_path(
            _p, mDat, extra_roots=extra_roots, assume_in_scope=assume_in_scope)
        _out.append(prepare_output_for_write(
            _p,
            mDat=mDat,
            use_p4=_use_p4,
            confirm_p4=confirm_p4,
            _str_func=_str_func,
        ))
    if not _out and paths:
        raise PathWritePrepareError(paths[0] if paths else None, reason='Path is empty')
    return _out[0] if len(_out) == 1 else _out


def prepare_pose_files_for_write(path, store_thumbnail=False, mDat=None, extra_roots=(),
                                 assume_in_scope=False, confirm_p4=True,
                                 _str_func='prepare_pose_files_for_write'):
    """Prepare .pose path and optional .bmp thumbnail before Red9 write."""
    if not path:
        raise PathWritePrepareError(path, reason='Path is empty')
    if mDat is None:
        mDat = get_project_mDat()
    _paths = [path]
    if store_thumbnail:
        _paths.append('{0}.bmp'.format(os.path.splitext(path)[0]))
    return prepare_paths_for_write(
        _paths,
        mDat=mDat,
        confirm_p4=confirm_p4,
        extra_roots=extra_roots,
        assume_in_scope=assume_in_scope,
        _str_func=_str_func,
    )


def prepare_meta_files_for_write(meta_dat_path, store_thumbnail=False,
                                 include_existing_thumbnail=False,
                                 mDat=None, confirm_p4=True,
                                 _str_func='prepare_meta_files_for_write'):
    """Prepare Scene version meta `.dat` and optional sibling `.bmp` in meta/."""
    if not meta_dat_path:
        raise PathWritePrepareError(meta_dat_path, reason='Path is empty')
    if mDat is None:
        mDat = get_project_mDat()
    _thumb = '{0}.bmp'.format(os.path.splitext(meta_dat_path)[0])
    _paths = [meta_dat_path]
    if store_thumbnail or (include_existing_thumbnail and os.path.exists(_thumb)):
        _paths.append(_thumb)
    return prepare_paths_for_write(
        _paths,
        mDat=mDat,
        confirm_p4=confirm_p4,
        _str_func=_str_func,
    )


def prepare_maya_scene_for_save(path, mDat=None, confirm_p4=True, extra_roots=(),
                                assume_in_scope=False, _str_func='prepare_maya_scene_for_save'):
    """Prepare Maya scene path before mc.file(rename=…) + save."""
    return prepare_output_for_write(
        path,
        mDat=mDat,
        use_p4=_resolve_use_p4_for_path(
            path, mDat, extra_roots=extra_roots, assume_in_scope=assume_in_scope),
        confirm_p4=confirm_p4,
        _str_func=_str_func,
    )


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

    Callers should invoke this (or prepare_paths_for_write) before expensive save work.
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

    _p4_mode = _resolve_use_p4_for_write(mDat, use_p4)
    _p4_ran = False
    _p4_disconnected = False

    if _p4_mode:
        import cgm.core.lib.perforce as P4UTIL
        _user, _client = P4UTIL.resolve_connection(p4_user, p4_client)
        if _user and _client and P4UTIL.is_available(p4_user=_user, p4_client=_client):
            _prepare_p4_for_write(
                _norm, _user, _client, confirm=confirm_p4, _str_func=_str_func)
            _p4_ran = True
        else:
            _p4_disconnected = True
            log.debug('{0} || P4 skipped (not connected) — writability check only'.format(_str_func))

    if os.path.exists(_norm):
        if not os.path.isfile(_norm):
            raise PathWritePrepareError(_norm, reason='Path exists but is not a file')
        if not os.access(_norm, os.W_OK):
            if not _p4_ran:
                _maybe_warn_p4_writability_hint(
                    _norm, mDat=mDat, reason='File is not writable',
                    p4_mode=_p4_mode, p4_disconnected=_p4_disconnected)
            raise PathWritePrepareError(_norm, reason='File is not writable')
    elif _parent and not os.access(_parent, os.W_OK):
        if not _p4_ran:
            _maybe_warn_p4_writability_hint(
                _norm, mDat=mDat, reason='Directory is not writable',
                p4_mode=_p4_mode, p4_disconnected=_p4_disconnected)
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


def prepare_export_output_for_write(path, mDat=None, confirm_p4=True, _str_func='prepare_export_output_for_write'):
    """
    FBX export prepare — sidecar cleanup + global prepare (writability + optional P4).

    P4 subprocess/dialogs only when project versionControl=perforce, path in scope, and connected.
    """
    if not path:
        raise ExportOutputNotWritableError(path, reason='Export path is empty')
    cleanup_fbx_export_sidecars(path, _str_func=_str_func)
    try:
        _norm = prepare_output_for_write(
            path,
            mDat=mDat,
            confirm_p4=confirm_p4,
            _str_func=_str_func,
        )
    except PathWritePrepareError as err:
        if getattr(err, 'reason', None) == 'Save cancelled':
            raise
        record_non_writable_export_path(getattr(err, 'path', None) or path)
        raise ExportOutputNotWritableError(
            getattr(err, 'path', None) or path,
            reason=getattr(err, 'reason', None) or str(err))
    return _norm.replace('\\', '/')


def preflight_export_output_paths(paths, mDat=None, confirm_p4=True, _str_func='preflight_export_output_paths'):
    """Prepare each unique FBX export path before bake/prep; first failure aborts."""
    _unique = []
    _seen = set()
    for _p in paths or []:
        if not _p:
            continue
        _key = os.path.normcase(os.path.normpath(_p))
        if _key in _seen:
            continue
        _seen.add(_key)
        _unique.append(_p)
    _out = []
    for _p in _unique:
        _out.append(prepare_export_output_for_write(
            _p,
            mDat=mDat,
            confirm_p4=confirm_p4,
            _str_func=_str_func,
        ))
    return _out[0] if len(_out) == 1 else _out

