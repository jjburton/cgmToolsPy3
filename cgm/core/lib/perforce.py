"""
------------------------------------------
perforce: cgm.core.lib.perforce
Read-only Perforce connectivity queries for cgmTools.

Server calls use explicit p4 -u USER -c CLIENT (-ztag), not registry/cwd discovery.
Optional layer — does not alter export/save unless explicitly wired later.
Reference only: cgm.lib.zoo.zooPy.perforce (never import from cgm core).
------------------------------------------
"""
# From Python =============================================================
import logging
import os
import re
import subprocess
import sys

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Windows: p4.exe is a console app — hide subprocess windows in Maya
_P4_SUBPROCESS_KW = {}
if sys.platform == 'win32':
    _P4_SUBPROCESS_KW['creationflags'] = subprocess.CREATE_NO_WINDOW

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGEN

# Session cache ===========================================================
_cache = {
    'p4_user': None,
    'p4_client': None,
    'available': None,
    'info': None,
}

_INFO_PREFIX_RE = re.compile(r'^info\d*:\s*', re.IGNORECASE)

# Maya optionVars — shared prefs for all cgm P4 tools
OPT_P4_USER = 'cgmVar_p4_user'
OPT_P4_CLIENT = 'cgmVar_p4_client'

# p4 changes (text): Change 12345 on YYYY/MM/DD by user@client *pending*
_CHANGE_LINE_RE = re.compile(
    r'^Change\s+(?P<change>\d+)\s+on\s+\S+\s+by\s+\S+@\S+\s+\*(?P<status>\w+)\*'
)


#>>> Internal helpers
#===================================================================
def _strip_info_prefix(line):
    return _INFO_PREFIX_RE.sub('', line.rstrip('\r\n'))


def resolve_connection(p4_user=None, p4_client=None):
    """
    Resolve Perforce user and client workspace.

    Priority: explicit args, cgm optionVars, CGM_P4* env, P4* env.
    """
    if p4_user is None or p4_client is None:
        _ov_user, _ov_client = get_connection_prefs()
        if p4_user is None:
            p4_user = _ov_user
        if p4_client is None:
            p4_client = _ov_client

    _user = p4_user or os.environ.get('CGM_P4USER') or os.environ.get('P4USER')
    _client = p4_client or os.environ.get('CGM_P4CLIENT') or os.environ.get('P4CLIENT')
    return _user, _client


def get_connection_prefs():
    """Read p4 user/client from Maya optionVars."""
    try:
        import cgm.core.cgm_Meta as cgmMeta
        _u = cgmMeta.cgmOptionVar(OPT_P4_USER, varType='string', defaultValue='')
        _c = cgmMeta.cgmOptionVar(OPT_P4_CLIENT, varType='string', defaultValue='')
        _user = (_u.getValue() or '').strip() or None
        _client = (_c.getValue() or '').strip() or None
        return _user, _client
    except Exception:
        return None, None


def save_connection_prefs(p4_user=None, p4_client=None):
    """Persist p4 user/client to Maya optionVars."""
    import cgm.core.cgm_Meta as cgmMeta
    if p4_user is not None:
        cgmMeta.cgmOptionVar(OPT_P4_USER, varType='string', defaultValue='').setValue(
            str(p4_user).strip())
    if p4_client is not None:
        cgmMeta.cgmOptionVar(OPT_P4_CLIENT, varType='string', defaultValue='').setValue(
            str(p4_client).strip())
    _clear_cache()


def _clear_cache():
    _cache['available'] = None
    _cache['info'] = None


def _parse_tag_block(lines):
    """Parse one -ztag record (... key value lines) into a dict."""
    _out = {}
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).strip()
        if not _line.startswith('...'):
            continue
        _rest = _line[3:].strip()
        if not _rest:
            continue
        _sp = _rest.split(None, 1)
        if len(_sp) == 1:
            _out[_sp[0]] = True
        else:
            _out[_sp[0]] = _sp[1]
    return _out


def _parse_tag_records(lines):
    """Parse -ztag output with multiple records separated by blank lines."""
    _records = []
    _block = []
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).rstrip('\r\n')
        if not _line.strip() or _line.strip().startswith('exit:'):
            if _block:
                _rec = _parse_tag_block(_block)
                if _rec:
                    _records.append(_rec)
                _block = []
            continue
        if _line.strip().lower().startswith('error:'):
            continue
        _block.append(_line)
    if _block:
        _rec = _parse_tag_block(_block)
        if _rec:
            _records.append(_rec)
    return _records


def _parse_colon_dict(lines):
    """Parse p4 info -s colon output (fallback)."""
    _out = {}
    for _raw in lines or []:
        _line = _strip_info_prefix(_raw).strip()
        if not _line or _line.startswith('exit:') or _line.lower().startswith('error:'):
            continue
        if ':' not in _line:
            continue
        _key, _val = _line.split(':', 1)
        _key = _key.strip()
        _val = _val.strip()
        _parts = _key.split()
        _camel = _parts[0].lower() + ''.join(_p.capitalize() for _p in _parts[1:])
        _out[_camel] = _val
    return _out


def _normalize_error(msg):
    if not msg:
        return msg
    _m = str(msg).strip()
    if _m.lower().startswith('error:'):
        return _m[6:].strip()
    return _m


def _p4run(*args, **kwargs):
    """
    Run p4 subprocess with explicit -u / -c (required for server commands).

    :keyword p4_user: Perforce username
    :keyword p4_client: Perforce client workspace name
    :keyword ztag: Pass -ztag (default True for server queries)
    :keyword use_s: Pass -s instead of -ztag (e.g. p4 set)
    :returns: dict ok, lines, stderr, exitCode, tagRecords, tag
    """
    _p4_user = kwargs.pop('p4_user', None)
    _p4_client = kwargs.pop('p4_client', None)
    _ztag = kwargs.pop('ztag', True)
    _use_s = kwargs.pop('use_s', False)
    _cwd = kwargs.pop('cwd', None)

    _cmd = ['p4']
    if _p4_user:
        _cmd.extend(['-u', str(_p4_user)])
    if _p4_client:
        _cmd.extend(['-c', str(_p4_client)])
    if _use_s:
        _cmd.append('-s')
    elif _ztag:
        _cmd.append('-ztag')
    _cmd.extend([str(a) for a in args])

    try:
        _proc = subprocess.Popen(
            _cmd,
            cwd=_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **_P4_SUBPROCESS_KW,
        )
    except FileNotFoundError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': 'p4 executable not found',
            'exitCode': -1,
            'tag': {},
            'tagRecords': [],
            'error': str(err),
        }
    except OSError as err:
        return {
            'ok': False,
            'lines': [],
            'stderr': str(err),
            'exitCode': -1,
            'tag': {},
            'tagRecords': [],
            'error': str(err),
        }

    _stdout, _stderr = _proc.communicate()
    _exit = _proc.returncode

    try:
        _text = _stdout.decode('utf-8', errors='replace')
    except Exception:
        _text = _stdout.decode('latin-1', errors='replace')

    _lines = [_strip_info_prefix(l) for l in _text.splitlines()]
    _err = _stderr.decode('utf-8', errors='replace').strip()
    if not _err:
        _err_lines = [l for l in _lines if l.lower().startswith('error:')]
        if _err_lines:
            _err = _err_lines[0]

    _tag = _parse_tag_block(_lines)
    _tag_records = _parse_tag_records(_lines)
    _errors = [l for l in _lines if l.lower().startswith('error:')]
    _ok = _exit == 0 and not _errors

    return {
        'ok': _ok,
        'lines': _lines,
        'stderr': _normalize_error(_err),
        'exitCode': _exit,
        'tag': _tag,
        'tagRecords': _tag_records,
    }


def _require_connection(p4_user=None, p4_client=None):
    _user, _client = resolve_connection(p4_user, p4_client)
    if not _user or not _client:
        return None, None, 'p4_user and p4_client required (pass args or set CGM_P4USER/CGM_P4CLIENT)'
    return _user, _client, None


def _scene_path_get(scene_path=None):
    if scene_path:
        return os.path.normpath(scene_path)
    try:
        import maya.cmds as mc
        _scene = mc.file(q=True, sn=True)
        if _scene:
            return os.path.normpath(_scene)
    except Exception:
        pass
    return None


#>>> Public API — connectivity
#===================================================================
def is_available(force=False, p4_user=None, p4_client=None):
    """Return True when p4 info succeeds with explicit user and client."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _cache['available'] = False
        _cache['info'] = None
        return False

    if not force and _cache.get('available') is not None:
        if _cache.get('p4_user') == _user and _cache.get('p4_client') == _client:
            return _cache['available']

    _res = _p4run('info', p4_user=_user, p4_client=_client, ztag=True)
    _cache['p4_user'] = _user
    _cache['p4_client'] = _client
    _cache['available'] = bool(_res['ok'])
    if _res['ok']:
        _info = dict(_res['tag'])
        if not _info:
            _info = _parse_colon_dict(_res['lines'])
        _cache['info'] = _info
    else:
        _cache['info'] = None
    return _cache['available']


def connection_info(force=False, p4_user=None, p4_client=None):
    """Parsed p4 info for explicit user/client (-u / -c / -ztag info)."""
    if force:
        _clear_cache()

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {
            'connected': False,
            'reason': _err,
            'p4User': _user,
            'p4Client': _client,
        }

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        _res = _p4run('info', p4_user=_user, p4_client=_client, ztag=True)
        return {
            'connected': False,
            'reason': _res.get('stderr') or 'p4 info failed',
            'p4User': _user,
            'p4Client': _client,
        }

    _info = dict(_cache.get('info') or {})
    _info['connected'] = True
    _info['p4User'] = _user
    _info['p4Client'] = _client
    return _info


def query_opened(p4_user=None, p4_client=None, force=False):
    """
    Opened files grouped by changelist (p4 -u -c -ztag opened).
    """
    _empty = {'default': [], 'changes': {}, 'total': 0, 'rawCount': 0}
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return dict(_empty, error=_err)

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return dict(_empty, error='p4 info failed')

    _res = _p4run('opened', p4_user=_user, p4_client=_client, ztag=True)
    if not _res['ok']:
        return dict(_empty, error=_res.get('stderr') or 'p4 opened failed')

    _default = []
    _changes = {}
    _count = 0

    for _rec in _res.get('tagRecords') or []:
        if not _rec.get('depotFile'):
            continue
        _count += 1
        _change_raw = str(_rec.get('change', 'default'))
        _rev = _rec.get('rev')
        try:
            _rev = int(_rev)
        except (TypeError, ValueError):
            pass
        _entry = {
            'depotFile': _rec.get('depotFile'),
            'clientFile': _rec.get('clientFile'),
            'rev': _rev,
            'action': _rec.get('action'),
            'change': _change_raw,
            'type': _rec.get('type'),
        }
        if _change_raw.lower() == 'default':
            _default.append(_entry)
        else:
            try:
                _cl = int(_change_raw)
            except ValueError:
                _cl = _change_raw
            _changes.setdefault(_cl, []).append(_entry)

    return {
        'default': _default,
        'changes': _changes,
        'total': _count,
        'rawCount': _count,
    }


def query_pending_changes(p4_user=None, p4_client=None, force=False):
    """Pending changelists for user/client."""
    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        return {'error': _err, 'changes': []}

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        return {'error': 'p4 info failed', 'changes': []}

    _res = _p4run(
        'changes', '-s', 'pending', '-u', _user, '-c', _client,
        p4_user=_user, p4_client=_client, ztag=False, use_s=True,
    )
    if not _res['ok']:
        return {'error': _res.get('stderr') or 'p4 changes failed', 'changes': []}

    _changes = []
    for _line in _res['lines']:
        _line = _line.strip()
        if not _line or _line.lower().startswith('error:'):
            continue
        _m = _CHANGE_LINE_RE.match(_line)
        if not _m:
            continue
        _changes.append({
            'change': int(_m.group('change')),
            'status': _m.group('status'),
            'line': _line,
        })

    return {'changes': _changes}


def query_file_status(disk_path, p4_user=None, p4_client=None, force=False):
    """Depot status for a disk path (p4 -u -c -ztag fstat)."""
    _norm = os.path.normpath(disk_path) if disk_path else disk_path
    _out = {
        'path': _norm,
        'onDepot': False,
        'notInClient': False,
        'notOnDepot': False,
        'openAction': None,
        'change': None,
        'headRev': None,
        'haveRev': None,
        'otherOpen': None,
        'headAction': None,
        'depotFile': None,
        'clientFile': None,
    }

    if not _norm:
        _out['error'] = 'path is empty'
        return _out

    _user, _client, _err = _require_connection(p4_user, p4_client)
    if _err:
        _out['error'] = _err
        return _out

    if not is_available(force=force, p4_user=_user, p4_client=_client):
        _out['error'] = 'p4 info failed'
        return _out

    _res = _p4run('fstat', _norm, p4_user=_user, p4_client=_client, ztag=True)
    _tag = _res.get('tag') or {}

    if _tag:
        _out['onDepot'] = True
        _out['depotFile'] = _tag.get('depotFile')
        _out['clientFile'] = _tag.get('clientFile')
        _out['headRev'] = _tag.get('headRev')
        _out['haveRev'] = _tag.get('haveRev')
        _out['headAction'] = _tag.get('headAction')
        _out['openAction'] = _tag.get('action')
        _out['change'] = _tag.get('change')
        _out['otherOpen'] = _tag.get('otherOpen')
        if _tag.get('headAction') == 'delete':
            _out['onDepot'] = False
            _out['notOnDepot'] = True
        return _out

    _err_text = ' '.join(_res['lines'] + [_res.get('stderr') or '']).lower()
    if 'not in client view' in _err_text or 'not under' in _err_text:
        _out['notInClient'] = True
        return _out
    if 'no such file' in _err_text or 'not on depot' in _err_text or 'not in depot' in _err_text:
        _out['notOnDepot'] = True
        return _out

    if not _res['ok']:
        _out['error'] = _res.get('stderr') or 'p4 fstat failed'
    return _out


def query_connection(scene_path=None, force=False, p4_user=None, p4_client=None, expected_user=None):
    """
    Compose connectivity, opened files, pending changelists, and scene fstat.

    expected_user: deprecated alias for p4_user when p4_user omitted.
    """
    if p4_user is None and expected_user:
        p4_user = expected_user

    _scene = _scene_path_get(scene_path)
    _user, _client, _err = _require_connection(p4_user, p4_client)
    _info = connection_info(force=force, p4_user=_user, p4_client=_client)

    _report = {
        'connected': bool(_info.get('connected')),
        'connection': _info,
        'p4User': _user,
        'p4Client': _client,
        'opened': None,
        'pendingChanges': None,
        'scene': None,
    }

    if _err:
        _report['reason'] = _err
        return _report

    if not _report['connected']:
        _report['reason'] = _info.get('reason')
        return _report

    _report['opened'] = query_opened(p4_user=_user, p4_client=_client, force=force)
    _report['pendingChanges'] = query_pending_changes(p4_user=_user, p4_client=_client, force=force)

    if _scene:
        _report['scene'] = query_file_status(_scene, p4_user=_user, p4_client=_client, force=force)
    else:
        _report['scene'] = {'skipped': True, 'reason': 'scene not saved'}

    return _report


def _format_scene_status(scene_dat):
    if not scene_dat:
        return 'scene: (none)'
    if scene_dat.get('skipped'):
        return 'scene: {0}'.format(scene_dat.get('reason', 'skipped'))
    if scene_dat.get('error'):
        return '{0} | error: {1}'.format(scene_dat.get('path'), scene_dat['error'])
    if scene_dat.get('notInClient'):
        return '{0} | not in client view'.format(scene_dat.get('path'))
    if scene_dat.get('notOnDepot'):
        return '{0} | not on depot'.format(scene_dat.get('path'))

    _parts = [scene_dat.get('path', '?')]
    if scene_dat.get('onDepot'):
        _parts.append('onDepot')
    if scene_dat.get('headRev') is not None:
        _parts.append('headRev {0}'.format(scene_dat.get('headRev')))
    if scene_dat.get('haveRev') is not None:
        _parts.append('haveRev {0}'.format(scene_dat.get('haveRev')))
    if scene_dat.get('openAction'):
        _parts.append('open {0} change {1}'.format(scene_dat.get('openAction'), scene_dat.get('change')))
    else:
        _parts.append('not opened')
    if scene_dat.get('otherOpen'):
        _parts.append('otherOpen {0}'.format(scene_dat.get('otherOpen')))
    return ' | '.join(_parts)


def query_status_report(
    p4_user=None,
    p4_client=None,
    scene_path=None,
    force=False,
    expected_user=None,
):
    """
    Log a human-readable P4 connectivity report and return the structured dict.

    Script Editor:
        import cgm.core.lib.perforce as P4UTIL
        P4UTIL.query_status_report(
            p4_user='josh.burton',
            p4_client='josh.burton_WX-MXL6062Q6F_5734_SourceArt-DDE',
        )
    """
    _str_func = 'query_status_report'
    if p4_user is None and expected_user:
        p4_user = expected_user

    _dat = query_connection(
        scene_path=scene_path,
        force=force,
        p4_user=p4_user,
        p4_client=p4_client,
    )
    _conn = _dat.get('connection') or {}

    log.info(cgmGEN.logString_sub(_str_func, 'P4 Connection'))
    log.info('p4_user: {0}'.format(_dat.get('p4User') or '(not set)'))
    log.info('p4_client: {0}'.format(_dat.get('p4Client') or '(not set)'))
    log.info('connected: {0}'.format(_dat.get('connected')))

    if not _dat.get('connected'):
        log.info('reason: {0}'.format(_dat.get('reason') or _conn.get('reason')))
        return _dat

    log.info('user (p4 info): {0}'.format(_conn.get('userName')))
    log.info('client: {0}'.format(_conn.get('clientName')))
    log.info('clientRoot: {0}'.format(_conn.get('clientRoot')))
    log.info('server: {0}'.format(_conn.get('serverAddress')))
    log.info('serverVersion: {0}'.format(_conn.get('serverVersion')))
    if _conn.get('stream'):
        log.info('stream: {0}'.format(_conn.get('stream')))
    elif _conn.get('clientStream'):
        log.info('stream: {0}'.format(_conn.get('clientStream')))

    _opened = _dat.get('opened') or {}
    if _opened.get('error'):
        log.info(cgmGEN.logString_sub(_str_func, 'Opened files'))
        log.info(_opened['error'])
    else:
        _total = _opened.get('total', 0)
        log.info(cgmGEN.logString_sub(_str_func, 'Opened files ({0})'.format(_total)))
        _default = _opened.get('default') or []
        if _default:
            log.info('[default] {0} file(s)'.format(len(_default)))
            for _rec in _default:
                log.info('  {0} {1}#{2}'.format(_rec['action'], _rec['depotFile'], _rec['rev']))
        for _cl in sorted((_opened.get('changes') or {}).keys(), key=lambda x: int(x) if str(x).isdigit() else x):
            _files = _opened['changes'][_cl]
            log.info('[change {0}] {1} file(s)'.format(_cl, len(_files)))
            for _rec in _files:
                log.info('  {0} {1}#{2}'.format(_rec['action'], _rec['depotFile'], _rec['rev']))

    _pending = _dat.get('pendingChanges') or {}
    log.info(cgmGEN.logString_sub(_str_func, 'Pending changelists'))
    if _pending.get('error'):
        log.info(_pending['error'])
    elif not (_pending.get('changes') or []):
        log.info('(none)')
    else:
        for _ch in _pending['changes']:
            log.info('{0} *{1}*'.format(_ch.get('change'), _ch.get('status')))

    log.info(cgmGEN.logString_sub(_str_func, 'Scene file'))
    log.info(_format_scene_status(_dat.get('scene')))

    return _dat
