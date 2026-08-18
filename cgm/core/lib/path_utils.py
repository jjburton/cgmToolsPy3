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
    _l_mask_lower = [m.lower() for m in l_mask] if l_mask else []
    for root, dirs, files in os.walk(_path.asString(), True, None):

        if hardCap and _i > hardCap:
            log.warning(cgmGEN.logString_msg(_str_func,"hit cap...{0}".format(hardCap)))
            break

        if _l_mask_lower:
            dirs[:] = [d for d in dirs if d.lower() not in _l_mask_lower]

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
        elif _l_mask_lower and _subRoot.lower() in _l_mask_lower:
            log.debug(cgmGEN.logString_msg(_str_func,"Masked...{0}".format(_subRoot)))
            continue
        
        if _l_mask_lower:
            _splitUp_lower = [p.lower() for p in _splitUp]
            _break = False
            for v in _l_mask_lower:
                if v in _splitUp_lower:
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
_export_prepare_records = []

_EXPORT_PREPARE_FAILURE_OUTCOMES = frozenset([
    'p4_not_in_client',
    'p4_out_of_date',
    'p4_locked',
    'p4_checkout_failed',
    'p4_user_cancel',
    'not_writable',
])

_EXPORT_PREPARE_SKIPPED_OUTCOMES = frozenset([
    'p4_skipped_offline',
    'p4_skipped_vc_off',
    'p4_skipped_add_disabled',
    'p4_skipped_auto_checkout_off',
])


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


def prepare_paths_for_write(paths, mDat=None, confirm_p4=True, p4_add=True, extra_roots=(),
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
            p4_add=p4_add,
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


def _export_prepare_stage(prepare_context=None, _str_func=''):
    """Resolve export prepare ledger stage from context or caller _str_func."""
    if prepare_context and prepare_context.get('stage'):
        return prepare_context['stage']
    _sf = _str_func or ''
    if 'fbx_export' in _sf or _sf == 'check_export_output_writable':
        return 'fbx_export'
    return 'export_preflight'


def _reason_to_export_p4_outcome(reason):
    """Map PathWritePrepareError / prepare reason to stable export ledger outcome."""
    if not reason:
        return 'p4_checkout_failed'
    _r = str(reason)
    _rl = _r.lower()
    if _r == 'Save cancelled':
        return 'p4_user_cancel'
    if 'not in perforce client' in _rl:
        return 'p4_not_in_client'
    if 'out of date' in _rl:
        return 'p4_out_of_date'
    if 'locked' in _rl or 'open elsewhere' in _rl:
        return 'p4_locked'
    if 'not writable' in _rl or 'read-only' in _rl:
        return 'not_writable'
    return 'p4_checkout_failed'


def _export_prepare_record_key(path, stage, outcome):
    return (
        os.path.normcase(os.path.normpath(path)) if path else '',
        stage or '',
        outcome or '',
    )


def _export_prepare_has_record(path, stage):
    _stage = stage or 'export_preflight'
    _nc = os.path.normcase(os.path.normpath(path)) if path else ''
    for _rec in _export_prepare_records:
        if os.path.normcase(os.path.normpath(_rec.get('path') or '')) == _nc and _rec.get('stage') == _stage:
            return True
    return False


def _build_export_prepare_entry(path, outcome, ok, reason=None, p4_action='none',
                                p4_attempted=False, prepare_context=None, stage=None,
                                _str_func=''):
    _stage = stage or _export_prepare_stage(prepare_context, _str_func)
    _entry = {
        'path': os.path.normpath(path) if path else path,
        'stage': _stage,
        'outcome': outcome,
        'p4_action': p4_action or 'none',
        'p4_attempted': bool(p4_attempted),
        'ok': bool(ok),
        'reason': reason,
    }
    if prepare_context:
        if prepare_context.get('sceneFile'):
            _entry['sceneFile'] = prepare_context['sceneFile']
        if prepare_context.get('batchIndex') is not None:
            _entry['batchIndex'] = prepare_context['batchIndex']
    return _entry


def record_export_prepare(entry):
    """Append one export P4-prepare ledger entry; dedupe by path+stage+outcome."""
    global _export_prepare_records
    if not entry or not entry.get('path'):
        return
    _key = _export_prepare_record_key(
        entry.get('path'), entry.get('stage'), entry.get('outcome'))
    for _existing in _export_prepare_records:
        if _export_prepare_record_key(
                _existing.get('path'), _existing.get('stage'), _existing.get('outcome')) == _key:
            return
    _export_prepare_records.append(dict(entry))
    if not entry.get('ok') and entry.get('outcome') in _EXPORT_PREPARE_FAILURE_OUTCOMES:
        global _non_writable_export_paths
        _norm = os.path.normpath(entry.get('path')) if entry.get('path') else entry.get('path')
        if _norm and _norm not in _non_writable_export_paths:
            _non_writable_export_paths.append(_norm)


def get_export_prepare_records():
    """Return copy of export P4-prepare ledger entries for this session."""
    return [dict(_rec) for _rec in _export_prepare_records]


def get_last_export_prepare_failure(path=None):
    """Most recent failed export prepare record, optionally filtered by path."""
    for _rec in reversed(_export_prepare_records):
        if _rec.get('ok'):
            continue
        if path:
            _want = os.path.normcase(os.path.normpath(path))
            _got = os.path.normcase(os.path.normpath(_rec.get('path') or ''))
            if _want != _got:
                continue
        return dict(_rec)
    return None


def clear_export_prepare_records():
    """Reset export P4-prepare ledger and legacy non-writable path list (batch start)."""
    global _export_prepare_records
    _export_prepare_records = []
    clear_non_writable_export_paths()


def log_export_prepare_summary(_str_func, title='Batch P4 prepare summary'):
    """Log grouped export P4-prepare rollup for batch end."""
    _records = get_export_prepare_records()
    if not _records:
        return
    _counts = {}
    for _rec in _records:
        _outcome = _rec.get('outcome') or 'unknown'
        _counts[_outcome] = _counts.get(_outcome, 0) + 1
    _skipped = sum(_counts.get(_k, 0) for _k in _EXPORT_PREPARE_SKIPPED_OUTCOMES)
    _failed = sum(_counts.get(_k, 0) for _k in _EXPORT_PREPARE_FAILURE_OUTCOMES)
    log.warning(cgmGEN._str_hardBreak)
    log.info('{0} | {1} | paths={2} | p4_edit={3} | p4_add={4} | p4_already_open={5} | skipped={6} | failed={7}'.format(
        _str_func,
        title,
        len(_records),
        _counts.get('p4_edit', 0),
        _counts.get('p4_add', 0),
        _counts.get('p4_already_open', 0),
        _skipped,
        _failed,
    ))
    for _rec in _records:
        _parts = ['[{0}] {1}'.format(_rec.get('outcome'), _rec.get('path'))]
        if _rec.get('reason'):
            _parts.append(_rec.get('reason'))
        if _rec.get('sceneFile'):
            _parts.append('scene={0}'.format(_rec.get('sceneFile')))
        log.info('{0} |   {1}'.format(_str_func, '  |  '.join(_parts)))
    log.warning(cgmGEN._str_hardBreak)


def _record_export_prepare_path(path, outcome, ok, reason=None, p4_action='none',
                                p4_attempted=False, prepare_context=None, stage=None,
                                _str_func=''):
    record_export_prepare(_build_export_prepare_entry(
        path,
        outcome,
        ok,
        reason=reason,
        p4_action=p4_action,
        p4_attempted=p4_attempted,
        prepare_context=prepare_context,
        stage=stage,
        _str_func=_str_func,
    ))


def _prepare_p4_for_write(path, p4_user, p4_client, confirm=True, p4_add=True,
                          prepare_context=None, _str_func='prepare_output_for_write'):
    """
    Query fstat, block out-of-date depot files, confirm before edit/add.
    When p4_add=False, checkout depot files only — skip p4 add for not-on-depot paths.
    Raises PathWritePrepareError on failure or user cancel.
    """
    import cgm.core.lib.perforce as P4UTIL

    _record = prepare_context is not None
    _stage = _export_prepare_stage(prepare_context, _str_func) if _record else None

    def _log_p4(outcome, ok, reason=None, p4_action='none', p4_attempted=True):
        if not _record:
            return
        _record_export_prepare_path(
            path,
            outcome,
            ok,
            reason=reason,
            p4_action=p4_action,
            p4_attempted=p4_attempted,
            prepare_context=prepare_context,
            stage=_stage,
            _str_func=_str_func,
        )

    _stat = P4UTIL.query_file_status(path, p4_user=p4_user, p4_client=p4_client)
    if _stat.get('error') and not _stat.get('notInClient') and not _stat.get('notOnDepot'):
        _reason = _stat.get('error')
        _log_p4('p4_checkout_failed', False, reason=_reason)
        raise PathWritePrepareError(path, reason=_reason)

    if _stat.get('notInClient'):
        _reason = 'Path not in Perforce client view'
        _log_p4('p4_not_in_client', False, reason=_reason)
        raise PathWritePrepareError(path, reason=_reason)

    if _stat.get('lockedByOther'):
        _detail = _stat.get('otherLock') or _stat.get('otherOpen') or 'another user'
        _reason = 'File locked or open elsewhere ({0})'.format(_detail)
        _log_p4('p4_locked', False, reason=_reason)
        raise PathWritePrepareError(path, reason=_reason)

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
        _reason = 'File out of date ({0}) — sync before save'.format(_rev_msg)
        _log_p4('p4_out_of_date', False, reason=_reason)
        raise PathWritePrepareError(path, reason=_reason)

    if _stat.get('checkedOut'):
        _log_p4('p4_already_open', True, p4_action='edit', p4_attempted=True)
        return

    _needs_add = bool(_stat.get('notOnDepot') and _stat.get('inClient'))
    _needs_edit = bool(_stat.get('onDepot') and not _stat.get('checkedOut'))

    if not _needs_add and not _needs_edit:
        return

    if _needs_add and not p4_add:
        log.debug('{0} || P4 add skipped (edit-only) — local write: {1}'.format(_str_func, path))
        _log_p4('p4_skipped_add_disabled', True, p4_attempted=False)
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
            _log_p4('p4_user_cancel', False, reason='Save cancelled')
            raise PathWritePrepareError(path, reason='Save cancelled')

    _res = P4UTIL.edit_or_add(path, p4_user=p4_user, p4_client=p4_client)
    if not _res.get('ok'):
        _reason = _res.get('stderr') or 'Perforce checkout failed'
        _log_p4('p4_checkout_failed', False, reason=_reason, p4_action=_res.get('action') or 'none')
        raise PathWritePrepareError(path, reason=_reason)
    _action = _res.get('action') or 'edit'
    _outcome = 'p4_add' if _action == 'add' else 'p4_edit'
    _log_p4(_outcome, True, p4_action=_action, p4_attempted=True)
    log.info('{0} || P4 {1}: {2}'.format(
        _str_func, _action, path))


def prepare_output_for_write(path, mDat=None, use_p4=None, p4_user=None, p4_client=None,
                             confirm_p4=True, p4_checkout=True, p4_add=True, prepare_context=None,
                             _str_func='prepare_output_for_write'):
    """
    Global prepare before writing a cgm output file (project .cfg, BaseDat, export targets).

    When use_p4 is None and mDat is provided, uses project versionControl (perforce gate).
    When P4 is connected: fstat first (block if out of date), confirm before edit/add.
    When p4_checkout is False, skip edit/add (writability check only) — export batch with
    Auto Check Out Export Files off.
    When P4 is unavailable, skips P4 silently (optional layer — no behavior change).
    Returns normalized path string.

    Callers should invoke this (or prepare_paths_for_write) before expensive save work.
    """
    _stage = _export_prepare_stage(prepare_context, _str_func) if prepare_context is not None else None
    if not path:
        _err = PathWritePrepareError(path, reason='Path is empty')
        if prepare_context is not None:
            _record_export_prepare_path(
                path,
                'not_writable',
                False,
                reason=_err.reason,
                prepare_context=prepare_context,
                stage=_stage,
                _str_func=_str_func,
            )
        raise _err

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
    _p4_checkout_skipped = False

    if _p4_mode:
        import cgm.core.lib.perforce as P4UTIL
        _user, _client = P4UTIL.resolve_connection(p4_user, p4_client)
        if _user and _client and P4UTIL.is_available(p4_user=_user, p4_client=_client):
            if p4_checkout:
                _prepare_p4_for_write(
                    _norm,
                    _user,
                    _client,
                    confirm=confirm_p4,
                    p4_add=p4_add,
                    prepare_context=prepare_context,
                    _str_func=_str_func,
                )
                _p4_ran = True
            else:
                _p4_checkout_skipped = True
                log.debug('{0} || P4 checkout skipped (p4_checkout=False) — writability check only'.format(
                    _str_func))
        else:
            _p4_disconnected = True
            log.debug('{0} || P4 skipped (not connected) — writability check only'.format(_str_func))

    def _record_writability_failure(reason):
        if prepare_context is None:
            return
        _record_export_prepare_path(
            _norm,
            'not_writable',
            False,
            reason=reason,
            prepare_context=prepare_context,
            stage=_stage,
            _str_func=_str_func,
        )

    if os.path.exists(_norm):
        if not os.path.isfile(_norm):
            _reason = 'Path exists but is not a file'
            if prepare_context is not None:
                _record_export_prepare_path(
                    _norm,
                    'not_writable',
                    False,
                    reason=_reason,
                    prepare_context=prepare_context,
                    stage=_stage,
                    _str_func=_str_func,
                )
            raise PathWritePrepareError(_norm, reason=_reason)
        if not os.access(_norm, os.W_OK):
            if not _p4_ran:
                _maybe_warn_p4_writability_hint(
                    _norm, mDat=mDat, reason='File is not writable',
                    p4_mode=_p4_mode, p4_disconnected=_p4_disconnected)
            _record_writability_failure('File is not writable')
            raise PathWritePrepareError(_norm, reason='File is not writable')
    elif _parent and not os.access(_parent, os.W_OK):
        if not _p4_ran:
            _maybe_warn_p4_writability_hint(
                _norm, mDat=mDat, reason='Directory is not writable',
                p4_mode=_p4_mode, p4_disconnected=_p4_disconnected)
        _record_writability_failure('Directory is not writable')
        raise PathWritePrepareError(_norm, reason='Directory is not writable')

    if prepare_context is not None and not _export_prepare_has_record(_norm, _stage):
        if _p4_checkout_skipped:
            _record_export_prepare_path(
                _norm,
                'p4_skipped_auto_checkout_off',
                True,
                reason='Auto Check Out Export Files off — writability-only',
                prepare_context=prepare_context,
                stage=_stage,
                _str_func=_str_func,
            )
        elif not _p4_mode:
            _record_export_prepare_path(
                _norm,
                'p4_skipped_vc_off',
                True,
                reason='Project versionControl is not perforce',
                prepare_context=prepare_context,
                stage=_stage,
                _str_func=_str_func,
            )
        elif _p4_disconnected:
            _record_export_prepare_path(
                _norm,
                'p4_skipped_offline',
                True,
                reason='P4 not connected — writability-only',
                prepare_context=prepare_context,
                stage=_stage,
                _str_func=_str_func,
            )
        else:
            _record_export_prepare_path(
                _norm,
                'writable_no_p4',
                True,
                reason='No P4 checkout required',
                prepare_context=prepare_context,
                stage=_stage,
                _str_func=_str_func,
            )

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


class ExportPreflightFailedError(Exception):
    """Raised when one or more export paths fail preflight (all paths are checked first)."""

    def __init__(self, failures):
        self.failures = list(failures or [])
        _count = len(self.failures)
        if _count == 1:
            _f = self.failures[0]
            _msg = 'Export preflight failed: {0} — {1}'.format(
                _f.get('path'), _f.get('reason') or 'unknown')
        else:
            _msg = 'Export preflight failed for {0} path(s)'.format(_count)
        super(ExportPreflightFailedError, self).__init__(_msg)


def _preflight_failure_entry(path, reason):
    """Build one preflight failure dict with optional P4 ledger outcome."""
    _entry = {
        'path': os.path.normpath(path) if path else path,
        'reason': reason,
    }
    _p4 = get_last_export_prepare_failure(_entry.get('path'))
    if _p4:
        _entry['p4Outcome'] = _p4.get('outcome')
        if _p4.get('reason'):
            _entry['p4Reason'] = _p4.get('reason')
    return _entry


def clear_non_writable_export_paths():
    """Reset session list of non-writable export paths (call at batch start)."""
    global _non_writable_export_paths
    _non_writable_export_paths = []


def record_non_writable_export_path(path, reason=None, prepare_context=None, stage='fbx_export'):
    """Track a non-writable export path for batch summary reporting."""
    _record_export_prepare_path(
        path,
        'not_writable',
        False,
        reason=reason or 'Export output is not writable',
        prepare_context=prepare_context,
        stage=stage,
        _str_func='check_export_output_writable',
    )


def get_non_writable_export_paths():
    """Return copy of non-writable export paths recorded this session."""
    _paths = []
    for _rec in _export_prepare_records:
        if not _rec.get('ok') and _rec.get('outcome') in _EXPORT_PREPARE_FAILURE_OUTCOMES:
            _p = _rec.get('path')
            if _p and _p not in _paths:
                _paths.append(_p)
    for _p in _non_writable_export_paths:
        if _p and _p not in _paths:
            _paths.append(_p)
    return _paths


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


def check_export_output_writable(finalPath, prepare_context=None, _str_func='check_export_output_writable'):
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
            record_non_writable_export_path(
                _norm,
                reason='Existing export file is read-only',
                prepare_context=prepare_context,
                stage='fbx_export',
            )
            raise ExportOutputNotWritableError(_norm, reason='Existing export file is read-only')
    else:
        if _parent and not os.access(_parent, os.W_OK):
            record_non_writable_export_path(
                _norm,
                reason='Export directory is not writable',
                prepare_context=prepare_context,
                stage='fbx_export',
            )
            raise ExportOutputNotWritableError(
                _norm,
                reason='Export directory is not writable')

    return _norm.replace('\\', '/')


def prepare_export_output_for_write(path, mDat=None, confirm_p4=True, p4_checkout=True,
                                    prepare_context=None, _str_func='prepare_export_output_for_write'):
    """
    FBX export prepare — sidecar cleanup + global prepare (writability + optional P4).

    P4 subprocess/dialogs only when project versionControl=perforce, path in scope, and connected.
    """
    if not path:
        raise ExportOutputNotWritableError(path, reason='Export path is empty')
    if prepare_context is None:
        prepare_context = {}
    cleanup_fbx_export_sidecars(path, _str_func=_str_func)
    try:
        _norm = prepare_output_for_write(
            path,
            mDat=mDat,
            confirm_p4=confirm_p4,
            p4_checkout=p4_checkout,
            prepare_context=prepare_context,
            _str_func=_str_func,
        )
    except PathWritePrepareError as err:
        _reason = getattr(err, 'reason', None) or str(err)
        if _reason == 'Save cancelled':
            raise
        raise ExportOutputNotWritableError(
            getattr(err, 'path', None) or path,
            reason=_reason)
    return _norm.replace('\\', '/')


def preflight_export_output_paths(paths, mDat=None, confirm_p4=True, p4_checkout=True,
                                  prepare_context=None, _str_func='preflight_export_output_paths'):
    """Prepare each unique FBX export path before bake/prep; checks all paths, then raises."""
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
    _failures = []
    for _p in _unique:
        try:
            _out.append(prepare_export_output_for_write(
                _p,
                mDat=mDat,
                confirm_p4=confirm_p4,
                p4_checkout=p4_checkout,
                prepare_context=prepare_context,
                _str_func=_str_func,
            ))
        except PathWritePrepareError as err:
            _reason = getattr(err, 'reason', None) or str(err)
            if _reason == 'Save cancelled':
                raise
            _failures.append(_preflight_failure_entry(
                getattr(err, 'path', None) or _p,
                _reason,
            ))
        except ExportOutputNotWritableError as err:
            _failures.append(_preflight_failure_entry(
                err.path,
                getattr(err, 'reason', None) or str(err),
            ))
    if _failures:
        raise ExportPreflightFailedError(_failures)
    return _out[0] if len(_out) == 1 else _out

