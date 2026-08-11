"""
mocap_align_utils
-----------------
Orchestration for mocapBakeTools local-TR align / snap / bake.
Reuses doLoc, movePointSnap/moveOrientSnap, TRANS, NAMES — does not reimplement snap math.

Design contract: cgmToolsDev Features/Feature_MocapAlignSnap.md
"""
__MAYALOCAL = 'MOCAPALIGN'

import copy
import json
import logging
import math
import os

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
from cgm.core.lib import name_utils as NAMES
from cgm.core.lib import transform_utils as TRANS
from cgm.lib import position as POSITION

log_start = cgmGEN.logString_start
log_msg = cgmGEN.logString_msg
log_sub = cgmGEN.logString_sub

_DEBUG_LOC_ATTR = 'cgmMocapAlignLoc'
SKEL_ROOT_SEP = ';'


# ---------------------------------------------------------------------------
# CCL IO
# ---------------------------------------------------------------------------
def load_ccl(path):
    """Load six-element CCL JSON. Returns list or raises."""
    _str_func = 'load_ccl'
    if not path or not os.path.isfile(path):
        raise IOError(log_msg(_str_func, "File not found: {0}".format(path)))
    with open(path, 'r') as f:
        data = json.load(f)
    if not isinstance(data, (list, tuple)) or len(data) < 6:
        raise ValueError(log_msg(_str_func, "Invalid CCL (need 6-element list): {0}".format(path)))
    return list(data)


def save_ccl(path, data):
    """Write six-element CCL JSON."""
    _str_func = 'save_ccl'
    if not path:
        raise ValueError(log_msg(_str_func, "No path"))
    if not isinstance(data, (list, tuple)) or len(data) < 6:
        raise ValueError(log_msg(_str_func, "Invalid CCL data"))
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, 'w') as f:
        json.dump(list(data), f, indent=2)
    log.info(log_msg(_str_func, "Saved: {0}".format(path)))
    return path


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------
def strip_short_name(node):
    """Return short DAG name without namespace or path."""
    return str(node).split('|')[-1].split(':')[-1]


def _strip_ns(name):
    return strip_short_name(name)


def normalize_namespace(namespace):
    """Normalize namespace to trailing-colon form or ':' for root."""
    if not namespace:
        return ':'
    ns = str(namespace).strip()
    if not ns or ns == ':':
        return ':'
    if not ns.endswith(':'):
        ns += ':'
    return ns


def _ensure_ns(name, rig_ns):
    """Join short control name with rig namespace. Accepts already-namespaced names."""
    if not name:
        return name
    name = str(name)
    if not rig_ns:
        return name
    ns = normalize_namespace(rig_ns)
    leaf = name.split('|')[-1]
    if ':' in leaf:
        return leaf
    return ns + leaf


def _conn_source_pattern(conn):
    return (conn.get('sourcePattern') or conn.get('source_pattern') or conn.get('source'))


def _conn_target_pattern(conn):
    return (conn.get('targetPattern') or conn.get('target_pattern') or conn.get('target'))


def _joints_matching_leaf(joint_list, leaf):
    """Joints in joint_list whose short name equals leaf."""
    return [j for j in (joint_list or []) if strip_short_name(j) == leaf]


def _joints_matching_chain_suffix(joint_list, segments):
    """Joints whose long path ends with the pipe-segment suffix."""
    if not segments or not joint_list:
        return []
    suffix = '|' + '|'.join(segments)
    matches = []
    seen = set()
    for joint in joint_list:
        if joint in seen:
            continue
        if joint.endswith(suffix):
            seen.add(joint)
            matches.append(joint)
        elif len(segments) == 1 and strip_short_name(joint) == segments[0]:
            seen.add(joint)
            matches.append(joint)
    return matches


def _pattern_segments_from_long_path(long_path, skel_roots=None):
    """
    Segment list for CCL compaction. Prefer Body| / Face| anchor when present.
    """
    long_names = mc.ls(long_path, long=True) or []
    if not long_names:
        return [strip_short_name(long_path)]
    long_path = long_names[0]

    for root_tag in ('Face', 'Body'):
        needle = '|{0}|'.format(root_tag)
        if needle in long_path:
            return [p for p in long_path[long_path.index(needle) + 1:].split('|') if p]

    for root in _parse_skel_roots(skel_roots):
        if long_path == root:
            return [strip_short_name(long_path)]
        prefix = root + '|'
        if long_path.startswith(prefix):
            rel = long_path[len(prefix):]
            if rel:
                return [p for p in rel.split('|') if p]

    return [strip_short_name(p) for p in long_path.split('|') if p]


def _minimal_unique_source_pattern(source_long, skel_roots):
    """
    Shortest pipe pattern unique under skel roots that resolves to source_long.
    Raises ValueError when no unique suffix exists.
    """
    if not source_long or not mc.objExists(source_long):
        raise ValueError('Source joint not in scene: {0}'.format(source_long))

    source_long = mc.ls(source_long, long=True)[0]
    joint_list = _joints_under_roots(skel_roots)
    if not joint_list:
        raise ValueError('No joints under skeleton roots')

    segments = _pattern_segments_from_long_path(source_long, skel_roots)
    if not segments:
        segments = [strip_short_name(source_long)]

    for length in range(1, len(segments) + 1):
        candidate_segments = segments[-length:]
        candidate = '|'.join(candidate_segments)
        matches = _joints_matching_chain_suffix(joint_list, candidate_segments)
        if len(matches) == 1 and matches[0] == source_long:
            return candidate

    raise ValueError(
        'Cannot build unique source pattern for {0} under skeleton roots'.format(
            strip_short_name(source_long)))


def _align_ccl_source_pattern(source_pattern=None, source=None, skel_roots=None):
    """
    Compact skeleton joint pattern for CCL storage (save-only).

    When skel_roots are set and source resolves to a scene joint, emit the
    shortest unique pattern under those roots (leaf or pipe chain).

    When skel_roots are absent, or input is already a non-scene pattern string,
    return the pattern unchanged (load / backward compatibility).
    """
    pat = source_pattern or source or ''
    if not pat:
        return ''

    roots = _parse_skel_roots(skel_roots)

    if roots:
        scene_src = None
        if source and mc.objExists(source):
            scene_src = mc.ls(source, long=True)[0]
        elif mc.objExists(pat):
            scene_src = mc.ls(pat, long=True)[0]
        if scene_src:
            return _minimal_unique_source_pattern(scene_src, skel_roots)

    # Pass-through: saved CCL literals and unresolved patterns (load path)
    if not mc.objExists(pat):
        return pat

    # Fallback when compaction not requested (legacy callers)
    return NAMES.get_base(pat) if mc.objExists(pat) else _strip_ns(pat)


def validate_connections_for_save(connections, skel_roots, rig_ns=None, skel_ns=None):
    """
    Pre-save validation: roots required; each source compacts to a unique pattern
    that resolves back to the same joint long path.
    """
    result = {'ok': True, 'errors': [], 'warnings': [], 'details': []}
    roots = _parse_skel_roots(skel_roots)
    if not roots:
        result['ok'] = False
        result['errors'].append('Skeleton roots required to save CCL')
        return result

    skel_ns = normalize_namespace(skel_ns or ':')
    for i, conn in enumerate(connections or []):
        src_long = conn.get('sourceResolved') or conn.get('source')
        if not src_long or not mc.objExists(src_long):
            result['ok'] = False
            result['errors'].append(
                '[{0}] source not resolved in scene: {1}'.format(i, src_long))
            continue

        src_long = mc.ls(src_long, long=True)[0]
        try:
            pattern = _minimal_unique_source_pattern(src_long, skel_roots)
        except ValueError as err:
            result['ok'] = False
            result['errors'].append('[{0}] {1}'.format(i, err))
            continue

        resolved = resolve_skeleton_joint(pattern, skel_roots=skel_roots, skel_ns=skel_ns)
        if resolved != src_long:
            result['ok'] = False
            result['errors'].append(
                '[{0}] pattern "{1}" resolves to {2}, expected {3}'.format(
                    i, pattern, resolved, src_long))
        else:
            result['details'].append('[{0}] {1} -> {2}'.format(
                i, strip_short_name(src_long), pattern))

    return result


def _align_ccl_target_pattern(target_pattern=None, target=None, rig_ns=None):
    """Compact rig control pattern: namespaced short name (no DAG path)."""
    pat = target_pattern or target or ''
    if not pat:
        return ''

    last = str(pat).split('|')[-1]
    if not str(pat).startswith('|') and ':' in last:
        return last

    if mc.objExists(pat):
        short = NAMES.get_short(pat)
        leaf = short.split('|')[-1]
        if ':' in leaf:
            return leaf
        return _ensure_ns(NAMES.get_base(pat), rig_ns)

    ns = normalize_namespace(rig_ns)
    short = strip_short_name(pat)
    if ':' in last:
        return last
    return '{0}{1}'.format(ns, short)


def has_local_offsets(conn):
    """True when connection dict has usable localTranslate + localRotate."""
    if not isinstance(conn, dict):
        return False
    lt = conn.get('localTranslate')
    lr = conn.get('localRotate')
    if lt is None or lr is None:
        return False
    try:
        return len(lt) >= 3 and len(lr) >= 3
    except TypeError:
        return False


def connection_missing_local_offset_reasons(conn):
    """List of human-readable missing fields for snap reporting."""
    reasons = []
    if not isinstance(conn, dict):
        return ['invalid connection dict']
    src = conn.get('sourceResolved') or conn.get('source')
    tgt = conn.get('targetResolved') or conn.get('target')
    if not src or (isinstance(src, str) and not mc.objExists(src)):
        reasons.append('source unresolved / missing')
    if not tgt or (isinstance(tgt, str) and not mc.objExists(tgt)):
        reasons.append('target unresolved / missing')
    if conn.get('localTranslate') is None:
        reasons.append('localTranslate')
    if conn.get('localRotate') is None:
        reasons.append('localRotate')
    elif not has_local_offsets(conn):
        reasons.append('localTranslate/localRotate incomplete')
    return reasons


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _split_pattern_segments(pattern):
    """Return pipe-separated path segments from a CCL source pattern."""
    if not pattern:
        return []
    if '|' in str(pattern):
        return [p for p in str(pattern).split('|') if p]
    short = str(pattern).split(':')[-1]
    return [short] if short else []


def _normalize_root_list(skel_roots):
    if not skel_roots:
        return []
    if isinstance(skel_roots, str):
        parts = [p.strip() for p in skel_roots.replace(',', SKEL_ROOT_SEP).split(SKEL_ROOT_SEP) if p.strip()]
        return parts
    return [str(r).strip() for r in skel_roots if r]


def _parse_skel_roots(skel_roots):
    """Parse skeleton root field into long DAG paths."""
    if not skel_roots:
        return []
    if isinstance(skel_roots, (list, tuple)):
        roots = []
        for part in skel_roots:
            if not part or not mc.objExists(part):
                continue
            long_name = (mc.ls(part, long=True) or [part])[0]
            if long_name not in roots:
                roots.append(long_name)
        return roots

    raw = str(skel_roots).strip()
    if not raw:
        return []
    if SKEL_ROOT_SEP in raw:
        parts = [p.strip() for p in raw.split(SKEL_ROOT_SEP) if p.strip()]
    else:
        parts = [p.strip() for p in raw.split(',') if p.strip()]
    roots = []
    for part in parts:
        if not mc.objExists(part):
            continue
        long_name = (mc.ls(part, long=True) or [part])[0]
        if long_name not in roots:
            roots.append(long_name)
    return roots


def _joints_under_roots(skel_roots):
    """Collect joint long names under the given root transforms (scoped search)."""
    roots = _parse_skel_roots(skel_roots)
    joints = []
    seen = set()

    def _add_joint(node):
        long_names = mc.ls(node, long=True) or []
        if not long_names:
            return
        long_name = long_names[0]
        if long_name not in seen:
            seen.add(long_name)
            joints.append(long_name)

    if not roots:
        for joint in mc.ls(type='joint', long=True) or []:
            _add_joint(joint)
        return joints

    for long_root in roots:
        if not mc.objExists(long_root):
            continue
        if mc.nodeType(long_root) == 'joint':
            _add_joint(long_root)
        for desc in mc.listRelatives(
                long_root, allDescendents=True, type='joint', fullPath=True) or []:
            _add_joint(desc)
    return joints


def _nodes_under_roots(skel_roots, node_types=('joint', 'transform')):
    """Collect joint + transform long names under skeleton roots (scoped driver search)."""
    roots = _parse_skel_roots(skel_roots)
    nodes = []
    seen = set()

    def _add_node(node):
        long_names = mc.ls(node, long=True) or []
        if not long_names:
            return
        long_name = long_names[0]
        if long_name not in seen:
            seen.add(long_name)
            nodes.append(long_name)

    if not roots:
        for ntype in node_types:
            for node in mc.ls(type=ntype, long=True) or []:
                _add_node(node)
        return nodes

    for long_root in roots:
        if not mc.objExists(long_root):
            continue
        root_type = mc.nodeType(long_root)
        if root_type in node_types:
            _add_node(long_root)
        for ntype in node_types:
            for desc in mc.listRelatives(
                    long_root, allDescendents=True, type=ntype, fullPath=True) or []:
                _add_node(desc)
    return nodes


def _pattern_leaf_key(pattern):
    """Normalized short leaf for connection merge / lookup keys."""
    if not pattern:
        return ''
    pat = str(pattern)
    if '|' in pat and not pat.startswith('|'):
        return strip_short_name(pat.split('|')[-1])
    return strip_short_name(pat)


def connection_pattern_key(conn):
    """Stable (source, target) key for merging UI links with stored connection data."""
    src = _conn_source_pattern(conn)
    tgt = _conn_target_pattern(conn)
    return (_pattern_leaf_key(src), _pattern_leaf_key(tgt))


def _ls_by_short_name(short):
    """Return long DAG paths for nodes whose leaf short name matches."""
    if not short:
        return []
    matches = []
    seen = set()
    for node in (mc.ls('*:{0}'.format(short), long=True) or []):
        if strip_short_name(node) == short and node not in seen:
            seen.add(node)
            matches.append(node)
    for node in (mc.ls(short, long=True) or []):
        if strip_short_name(node) == short and node not in seen:
            seen.add(node)
            matches.append(node)
    return matches


def _resolve_node_by_name(pattern, skel_ns=':'):
    """
    Resolve by exact path or unique short-name match.

    Returns (long_name, ambiguous_matches).
    """
    if not pattern:
        return None, []

    if mc.objExists(pattern):
        return (mc.ls(pattern, long=True) or [pattern])[0], []

    skel_ns = normalize_namespace(skel_ns)
    segments = _split_pattern_segments(pattern)
    if not segments:
        return None, []

    leaf = segments[-1]
    leaf_short = strip_short_name(leaf)

    for candidate in (pattern, leaf, '{0}{1}'.format(skel_ns, leaf_short)):
        if candidate and mc.objExists(candidate):
            return (mc.ls(candidate, long=True) or [candidate])[0], []

    matches = _ls_by_short_name(leaf_short)
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _is_skeleton_hierarchy_pattern(pattern):
    """True when pattern uses Body| / Face| pipe chains (MH skeleton paths)."""
    if not pattern or '|' not in str(pattern) or str(pattern).startswith('|'):
        return False
    if str(pattern).startswith('Body|') or str(pattern).startswith('Face|'):
        return True
    return len(_split_pattern_segments(pattern)) > 1


def _resolve_hierarchy_pattern(pattern, joint_list, skel_ns=':'):
    """Best joint match for a pipe-segment skeleton pattern within joint_list."""
    segments = _split_pattern_segments(pattern)
    if not segments or not joint_list:
        return None

    suffix = '|' + '|'.join(segments)
    leaf = segments[-1]
    leaf_short = strip_short_name(leaf)
    leaf_suffix = '|' + leaf
    ranked = []

    for joint in joint_list:
        if joint.endswith(suffix):
            ranked.append((0, -len(joint), joint))
        elif joint.endswith(leaf_suffix):
            ranked.append((1, -len(joint), joint))
        elif strip_short_name(joint) == leaf_short:
            ranked.append((2, -len(joint), joint))

    skel_ns = normalize_namespace(skel_ns)
    if skel_ns != ':':
        for joint in joint_list:
            if strip_short_name(joint) == leaf_short:
                if joint.endswith(suffix) or joint.endswith(leaf_suffix):
                    continue
                ranked.append((3, -len(joint), joint))

    if not ranked:
        return None
    ranked.sort()
    return ranked[0][2]


def source_pattern_needs_skel_roots(pattern, skel_ns=None):
    """True when pattern needs skeleton-root scoping to disambiguate."""
    if not pattern:
        return False
    direct, ambiguous = _resolve_node_by_name(pattern, skel_ns=skel_ns or ':')
    if direct:
        return False
    if len(ambiguous) > 1:
        return True
    if _is_skeleton_hierarchy_pattern(pattern):
        leaf_short = strip_short_name(_split_pattern_segments(pattern)[-1])
        return len(_ls_by_short_name(leaf_short)) > 1
    return False


def resolve_skeleton_joint(pattern, skel_roots=None, skel_ns=None):
    """
    Resolve a CCL source pattern to a scene driver long name (joint or transform).

    Direct paths and unique short-name matches resolve immediately. Skeleton
    hierarchy scoping via skel roots is used when multiple nodes share a name.
    Mocap driver controls (e.g. ArtSpine) under skel roots resolve via scoped
    transform search when they are not joints.
    """
    if not pattern:
        return None

    skel_ns = normalize_namespace(skel_ns or ':')
    direct, short_matches = _resolve_node_by_name(pattern, skel_ns=skel_ns)
    if direct:
        return direct

    root_longs = _parse_skel_roots(skel_roots)
    joint_list = _joints_under_roots(skel_roots) if root_longs else _joints_under_roots(None)
    node_list = _nodes_under_roots(skel_roots) if root_longs else _nodes_under_roots(None)

    if _is_skeleton_hierarchy_pattern(pattern):
        hierarchy_hit = _resolve_hierarchy_pattern(pattern, joint_list, skel_ns=skel_ns)
        if hierarchy_hit:
            return hierarchy_hit
        hierarchy_hit = _resolve_hierarchy_pattern(pattern, node_list, skel_ns=skel_ns)
        if hierarchy_hit:
            return hierarchy_hit

    if len(short_matches) == 1:
        return short_matches[0]

    if len(short_matches) > 1:
        if root_longs:
            scoped = set(node_list)
            in_scope = [m for m in short_matches if m in scoped]
            if len(in_scope) == 1:
                return in_scope[0]
        log.warning(log_msg('resolve_skeleton_joint',
                            "Ambiguous '{0}' ({1} hits). Set skeleton roots.".format(
                                pattern, len(short_matches))))
        return None

    if root_longs:
        segments = _split_pattern_segments(pattern)
        leaf_short = strip_short_name(segments[-1]) if segments else strip_short_name(pattern)
        scoped_matches = [n for n in node_list if strip_short_name(n) == leaf_short]
        if len(scoped_matches) == 1:
            return scoped_matches[0]
        if len(scoped_matches) > 1:
            log.warning(log_msg('resolve_skeleton_joint',
                                "Ambiguous '{0}' ({1} hits under skel roots).".format(
                                    pattern, len(scoped_matches))))
            return None

    return None


def resolve_rig_control(pattern, rig_ns=None):
    """Resolve a CCL rig control pattern to a namespaced scene transform."""
    if not pattern:
        return None

    pattern = str(pattern)
    if mc.objExists(pattern):
        return (mc.ls(pattern, long=True) or [pattern])[0]

    rig_ns = normalize_namespace(rig_ns)
    short = pattern.split('|')[-1]
    if ':' in short:
        short = short.split(':', 1)[1]

    namespaced = '{0}{1}'.format(rig_ns, short)
    if mc.objExists(namespaced):
        return (mc.ls(namespaced, long=True) or [namespaced])[0]
    return None


def _pattern_for_resolve(conn, side='source'):
    """
    Pattern string for resolve_* (load / reresolve). Never compacts — preserves CCL literals.
    """
    if side == 'source':
        stored = conn.get('sourcePattern') or conn.get('source_pattern')
        if stored:
            return str(stored)
        return str(_conn_source_pattern(conn) or conn.get('source') or '')
    stored = conn.get('targetPattern') or conn.get('target_pattern')
    if stored:
        return str(stored)
    return str(_conn_target_pattern(conn) or conn.get('target') or '')


def resolve_connections(connections, rig_ns=None, skel_roots=None, skel_ns=None):
    """Resolve source/target scene nodes for each connection dict (in place)."""
    rig_ns = normalize_namespace(rig_ns or ':')
    skel_ns = normalize_namespace(skel_ns or ':')
    for conn in connections or []:
        src_pat = _pattern_for_resolve(conn, 'source')
        tgt_pat = _align_ccl_target_pattern(
            _conn_target_pattern(conn), conn.get('target'), rig_ns=rig_ns)
        prev_source = conn.get('sourceResolved') or conn.get('source')
        src = resolve_skeleton_joint(src_pat, skel_roots=skel_roots, skel_ns=skel_ns)
        tgt = resolve_rig_control(tgt_pat, rig_ns=rig_ns)
        conn['sourcePattern'] = src_pat
        conn['source_pattern'] = src_pat
        conn['targetPattern'] = tgt_pat
        conn['target_pattern'] = tgt_pat
        conn['sourceResolved'] = src
        conn['targetResolved'] = tgt
        conn['source'] = src or src_pat
        conn['target'] = tgt or tgt_pat
        conn['resolved'] = bool(
            src and tgt and mc.objExists(src) and mc.objExists(tgt)
        )
        if prev_source and src and prev_source != src:
            _clear_locator_ref(conn)
    return connections


def connection_resolve_diagnostics(conn, rig_ns=None, skel_roots=None, skel_ns=None):
    """
    Structured resolve status for one connection (mapping report / debug).

    Returns dict: source_pattern, target_pattern, source_resolved, target_resolved,
    resolved, source_reason, target_reason, has_local_offsets.
    """
    rig_ns = normalize_namespace(rig_ns or ':')
    skel_ns = normalize_namespace(skel_ns or ':')
    src_pat = _pattern_for_resolve(conn, 'source')
    tgt_pat = _align_ccl_target_pattern(
        _conn_target_pattern(conn), conn.get('target'), rig_ns=rig_ns)
    src = resolve_skeleton_joint(src_pat, skel_roots=skel_roots, skel_ns=skel_ns)
    tgt = resolve_rig_control(tgt_pat, rig_ns=rig_ns)

    def _source_reason():
        if src:
            return ''
        if not src_pat:
            return 'empty source pattern'
        if mc.objExists(src_pat):
            return 'exists but resolve returned None'
        _direct, short_matches = _resolve_node_by_name(src_pat, skel_ns=skel_ns)
        if _direct:
            return ''
        root_longs = _parse_skel_roots(skel_roots)
        if root_longs:
            node_list = _nodes_under_roots(skel_roots)
            segments = _split_pattern_segments(src_pat)
            leaf_short = strip_short_name(segments[-1]) if segments else strip_short_name(src_pat)
            scoped = [n for n in node_list if strip_short_name(n) == leaf_short]
            if not scoped:
                if len(short_matches) > 1:
                    return '{0} ambiguous globally — set Skel Roots'.format(len(short_matches))
                return '0 hits globally, 0 under skel root'
            if len(scoped) > 1:
                return '0 hits globally, {0} ambiguous under skel root'.format(len(scoped))
        elif len(short_matches) > 1:
            return '{0} ambiguous globally — set Skel Roots'.format(len(short_matches))
        return '0 hits globally, 0 under skel root'

    def _target_reason():
        if tgt:
            return ''
        if not tgt_pat:
            return 'empty target pattern'
        if mc.objExists(tgt_pat):
            return 'exists but resolve returned None'
        rig_ns_norm = normalize_namespace(rig_ns)
        short = tgt_pat.split('|')[-1]
        if ':' in short:
            short = short.split(':', 1)[1]
        namespaced = '{0}{1}'.format(rig_ns_norm, short)
        return 'not found (tried {0}, {1})'.format(tgt_pat, namespaced)

    return {
        'source_pattern': src_pat,
        'target_pattern': tgt_pat,
        'source_resolved': src,
        'target_resolved': tgt,
        'resolved': bool(src and tgt and mc.objExists(src) and mc.objExists(tgt)),
        'source_reason': _source_reason(),
        'target_reason': _target_reason(),
        'has_local_offsets': has_local_offsets(conn),
    }


def format_mapping_line(conn, index):
    """Single-line summary for mapping report rows."""
    tgt_pat = _conn_target_pattern(conn) or '?'
    src_pat = _conn_source_pattern(conn) or '?'
    tgt_short = strip_short_name(tgt_pat)
    if '|' in str(src_pat) and not str(src_pat).startswith('|'):
        src_short = str(src_pat).split('|')[-1]
    else:
        src_short = strip_short_name(src_pat)
    follow = 'po' if conn.get('setPosition', True) else 'o'
    status = 'OK' if conn.get('resolved') else 'MISSING'
    loc_ref = conn.get('alignLocator')
    if loc_ref and mc.objExists(loc_ref):
        loc_note = ' LOC'
    elif loc_ref:
        loc_note = ' loc?'
    else:
        loc_note = ''
    offset_note = ' TR' if has_local_offsets(conn) else ''
    return '{0:3d}  {1}  <-  {2}  [{3}]  {4}{5}{6}'.format(
        index, tgt_short, src_short, follow, status, loc_note, offset_note)


def format_mapping_report(connections, rig_ns=None, skel_roots=None, skel_ns=None):
    """Build full text mapping report with resolve diagnostics."""
    lines = ['Mocap Align Mapping ({0} pairs)'.format(len(connections or [])), '']
    resolved = sum(1 for c in (connections or []) if c.get('resolved'))
    lines.append('Resolved: {0}/{1}'.format(resolved, len(connections or [])))
    with_offsets = sum(1 for c in (connections or []) if has_local_offsets(c))
    lines.append('Local offsets: {0}/{1}'.format(with_offsets, len(connections or [])))
    lines.append('')
    for i, conn in enumerate(connections or []):
        lines.append(format_mapping_line(conn, i))
        if not conn.get('resolved'):
            diag = connection_resolve_diagnostics(
                conn, rig_ns=rig_ns, skel_roots=skel_roots, skel_ns=skel_ns)
            if not diag['source_resolved']:
                lines.append('      source: {0}  ({1})'.format(
                    diag['source_pattern'], diag['source_reason'] or 'unresolved'))
            if not diag['target_resolved']:
                lines.append('      target: {0}  ({1})'.format(
                    diag['target_pattern'], diag['target_reason'] or 'unresolved'))
    return '\n'.join(lines)


def find_candidate_skel_roots():
    """
    Detect MetaHuman-style skeleton roots (joint named root with foot_l or hand_r under it).
    Returns list of long DAG paths.
    """
    candidates = []
    for j in mc.ls(type='joint', long=True) or []:
        if NAMES.get_base(j).lower() != 'root':
            continue
        desc = mc.listRelatives(j, allDescendents=True, type='joint', fullPath=True) or []
        bases = {NAMES.get_base(d).lower() for d in desc}
        if 'foot_l' in bases or 'hand_r' in bases or 'ball_l' in bases:
            candidates.append(j)
    return candidates


def count_ambiguous_skel_contexts():
    """How many MH-style roots are in the scene (for UI gating)."""
    return len(find_candidate_skel_roots())


# ---------------------------------------------------------------------------
# CCL <-> connections
# ---------------------------------------------------------------------------
def ccl_to_connections(data, rig_ns=None, skel_roots=None, skel_ns=None):
    """
    Normalize six-element CCL into connection dicts with resolved nodes when possible.

    Returns:
        dict with keys: source_items, source_data, target_items, target_data,
        links, connections (list of dicts), unresolved (list of report strings)
    """
    _str_func = 'ccl_to_connections'
    source_items = list(data[0]) if data[0] else []
    source_data = list(data[1]) if data[1] else []
    target_items = list(data[2]) if data[2] else []
    target_data = list(data[3]) if data[3] else []
    links = [list(x) for x in (data[4] or [])]
    raw_conn = list(data[5]) if data[5] else []

    connections = []

    if raw_conn:
        for conn in raw_conn:
            c = copy.deepcopy(conn) if isinstance(conn, dict) else {}
            c['source'] = c.get('source')
            c['target'] = c.get('target')
            c['sourcePattern'] = c.get('source')
            c['targetPattern'] = c.get('target')
            c['source_pattern'] = c['sourcePattern']
            c['target_pattern'] = c['targetPattern']
            if 'setPosition' not in c:
                c['setPosition'] = True
            if 'setRotation' not in c:
                c['setRotation'] = True
            connections.append(c)
    else:
        for link in links:
            try:
                si, ti = int(link[0]), int(link[1])
            except Exception:
                continue
            src_pat = source_items[si] if si < len(source_items) else None
            tgt_pat = target_items[ti] if ti < len(target_items) else None
            tdata = target_data[ti] if ti < len(target_data) else {}
            ctype = (tdata or {}).get('constraintType', 'po')
            connections.append({
                'source': src_pat,
                'target': tgt_pat,
                'sourcePattern': src_pat,
                'targetPattern': tgt_pat,
                'source_pattern': src_pat,
                'target_pattern': tgt_pat,
                'setPosition': 'p' in str(ctype),
                'setRotation': True,
            })

    resolve_connections(connections, rig_ns=rig_ns, skel_roots=skel_roots, skel_ns=skel_ns)
    _strip_locator_refs(connections)

    unresolved = []
    for i, c in enumerate(connections):
        if not c.get('resolved'):
            unresolved.append(
                "[{0}] source='{1}' target='{2}'".format(
                    i, _conn_source_pattern(c), _conn_target_pattern(c)))

    if unresolved:
        log.warning(log_sub(_str_func, "Unresolved ({0})".format(len(unresolved))))
        for line in unresolved:
            log.warning("  " + line)

    return {
        'source_items': source_items,
        'source_data': source_data,
        'target_items': target_items,
        'target_data': target_data,
        'links': links,
        'connections': connections,
        'unresolved': unresolved,
    }


def connections_to_ccl(connections, rig_ns=None, skel_roots=None,
                       source_items=None, source_data=None,
                       target_items=None, target_data=None, links=None):
    """
    Build six-element CCL from connection dicts. Emits short patterns on save.
    Preserves list/link structure when provided; otherwise rebuilds from connections.

    skel_roots: required for source pattern compaction on save (caller validates).
    """
    conn_out = []
    for c in connections or []:
        entry = {
            'source': _align_ccl_source_pattern(
                _conn_source_pattern(c), c.get('source'), skel_roots=skel_roots),
            'target': _align_ccl_target_pattern(_conn_target_pattern(c), c.get('target'), rig_ns),
            'setPosition': bool(c.get('setPosition', True)),
            'setRotation': bool(c.get('setRotation', True)),
        }
        if has_local_offsets(c):
            entry['localTranslate'] = list(c['localTranslate'])
            entry['localRotate'] = list(c['localRotate'])
        else:
            for k in ('positionOffset', 'offsetForward', 'offsetUp'):
                if k in c:
                    entry[k] = c[k]
        conn_out.append(entry)

    if source_items is None:
        source_items = [e['source'] for e in conn_out]
        source_data = [{} for _ in source_items]
        target_items = [e['target'] for e in conn_out]
        target_data = []
        for e in conn_out:
            ctype = 'po' if e.get('setPosition') else 'o'
            target_data.append({'constraintType': ctype})
        links = [[i, i] for i in range(len(conn_out))]

    src_short = [
        _align_ccl_source_pattern(x, skel_roots=skel_roots) for x in (source_items or [])]
    tgt_short = [_align_ccl_target_pattern(x, rig_ns=rig_ns) for x in (target_items or [])]

    return [
        src_short,
        list(source_data or []),
        tgt_short,
        list(target_data or []),
        [list(x) for x in (links or [])],
        conn_out,
    ]


def _strip_locator_refs(connections):
    """Drop scene locator refs from connections (e.g. after loading a CCL file)."""
    for conn in connections or []:
        _clear_locator_ref(conn)


# ---------------------------------------------------------------------------
# Offset locator create / capture / snap
# ---------------------------------------------------------------------------
def _resolved_pair(conn):
    src = conn.get('sourceResolved') or conn.get('source')
    tgt = conn.get('targetResolved') or conn.get('target')
    if src and mc.objExists(src):
        src = mc.ls(src, long=True)[0]
    else:
        src = None
    if tgt and mc.objExists(tgt):
        tgt = mc.ls(tgt, long=True)[0]
    else:
        tgt = None
    return src, tgt


def _align_cgm_object(node):
    """Wrap a scene node as cgmObject (no setClass on production controls)."""
    long_name = (mc.ls(node, long=True) or [node])[0]
    if not mc.objExists(long_name):
        raise ValueError('Node not found: {0}'.format(node))
    return cgmMeta.cgmObject(long_name)


def _as_float3(value):
    """Normalize meta translate/rotate to three floats."""
    try:
        return [float(value.x), float(value.y), float(value.z)]
    except AttributeError:
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        return [float(v) for v in value[:3]]


def _local_tr_get(m_loc):
    """Read local TR from locator meta translate/rotate properties."""
    return _as_float3(m_loc.translate), _as_float3(m_loc.rotate)


def _local_tr_set(m_loc, local_t, local_r):
    """Apply saved local TR via locator meta translate/rotate properties."""
    m_loc.translate = [float(v) for v in local_t]
    m_loc.rotate = [float(v) for v in local_r]


def _clear_locator_ref(conn):
    conn.pop('alignLocator', None)


def _sync_locator_to_conn(m_loc, m_source, conn):
    """Reparent to source joint and apply saved local offset TR."""
    m_loc.doParent(m_source)
    _local_tr_set(m_loc, conn['localTranslate'], conn['localRotate'])


def _ensure_loc_parent(m_loc, m_source):
    """Parent locator to source joint if it is not already (preserves local TR)."""
    parent = m_loc.getParent()
    source_long = m_source.p_nameLong
    if parent != source_long:
        m_loc.doParent(m_source)


def _build_parented_offset_locator(conn, source, target, name=None, visible=False):
    """
    Build a doLoc-matched locator parented to source with saved local offsets.

    Must use doLoc so rotateOrder / rotateAxis match capture-time locator shape.
    """
    if not has_local_offsets(conn):
        raise ValueError('missing local offset — run Capture Offsets')

    m_target = _align_cgm_object(target)
    m_source = _align_cgm_object(source)
    m_loc = m_target.doLoc()
    if not m_loc:
        raise RuntimeError('doLoc failed on {0}'.format(target))
    if name:
        renamed = mc.rename(m_loc.p_nameLong, name)
        m_loc = _align_cgm_object(renamed)
    mc.setAttr('{0}.v'.format(m_loc.p_nameLong), 1 if visible else 0)
    m_loc.doParent(m_source)
    _local_tr_set(m_loc, conn['localTranslate'], conn['localRotate'])
    try:
        mc.addAttr(m_loc.mNode, ln=_DEBUG_LOC_ATTR, at='bool', dv=True)
    except Exception:
        pass
    return m_loc


def _get_or_build_snap_locator(conn, source, target, index=None, visible=None, refresh_offset=True):
    """
    Return a parented offset locator for snapping.

    Reuses conn['alignLocator'] when it exists; otherwise builds a temporary locator.
    Returns (m_loc, keep_loc).
    """
    if not has_local_offsets(conn):
        raise ValueError('missing local offset — run Capture Offsets')

    m_source = _align_cgm_object(source)
    existing = conn.get('alignLocator')
    if existing and mc.objExists(existing):
        m_loc = _align_cgm_object(existing)
        if refresh_offset:
            _sync_locator_to_conn(m_loc, m_source, conn)
        else:
            _ensure_loc_parent(m_loc, m_source)
        if visible is not None:
            mc.setAttr('{0}.v'.format(m_loc.p_nameLong), 1 if visible else 0)
        return m_loc, True

    if existing:
        _clear_locator_ref(conn)

    loc_name = 'mocapAlign_{0}_loc'.format(NAMES.get_base(source))
    if index is not None:
        loc_name = 'mocapAlign_{0:03d}_{1}_loc'.format(
            index, strip_short_name(_conn_target_pattern(conn) or target))
    m_loc = _build_parented_offset_locator(
        conn, source, target, name=loc_name,
        visible=bool(visible) if visible is not None else False)
    return m_loc, False


def capture_alignment_offsets(connections, indices=None, keep_locs=False):
    """
    Bind-pose capture: doLoc on target (rp), parent to source, store local TR.

    Mutates connections in place. Returns result dict.
    """
    _str_func = 'capture_alignment_offsets'
    log.info(log_start(_str_func))
    result = {'captured': [], 'failed': [], 'details': []}

    idxs = indices if indices is not None else list(range(len(connections)))
    for i in idxs:
        if i < 0 or i >= len(connections):
            continue
        conn = connections[i]
        src, tgt = _resolved_pair(conn)
        if not src or not tgt:
            msg = "[{0}] cannot capture — source={1} target={2}".format(i, src, tgt)
            result['failed'].append(i)
            result['details'].append(msg)
            log.warning(log_msg(_str_func, msg))
            continue
        try:
            m_tgt = _align_cgm_object(tgt)
            m_source = _align_cgm_object(src)
            m_loc = m_tgt.doLoc()
            if not m_loc:
                raise RuntimeError("doLoc failed on {0}".format(tgt))
            m_loc.doParent(m_source)
            lt, lr = _local_tr_get(m_loc)
            conn['localTranslate'] = lt
            conn['localRotate'] = lr
            conn['sourceResolved'] = src
            conn['targetResolved'] = tgt
            conn['source'] = src
            conn['target'] = tgt
            conn['resolved'] = True
            for k in ('positionOffset', 'offsetForward', 'offsetUp', 'offsetPosition'):
                if k in conn:
                    del conn[k]
            if keep_locs:
                conn['alignLocator'] = m_loc.p_nameLong
                try:
                    mc.addAttr(m_loc.mNode, ln=_DEBUG_LOC_ATTR, at='bool', dv=True)
                except Exception:
                    pass
            else:
                mc.delete(m_loc.p_nameLong)
            result['captured'].append(i)
            result['details'].append("[{0}] {1} -> {2}  lt={3} lr={4}".format(
                i, NAMES.get_base(src), NAMES.get_base(tgt), lt, lr))
        except Exception as err:
            msg = "[{0}] capture failed {1} -> {2}: {3}".format(i, src, tgt, err)
            result['failed'].append(i)
            result['details'].append(msg)
            log.error(log_msg(_str_func, msg))

    _print_report(_str_func, result, verb='captured')
    return result


def _world_position(node):
    """World-space rotate-pivot position (matches movePointSnap query)."""
    return mc.xform(node, query=True, ws=True, rp=True)


def _world_rotation(node):
    """World-space rotation as a 3-float list."""
    return mc.xform(node, query=True, ws=True, ro=True)


def _vector_distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _snap_connection_pair(conn, index=None, delete_loc=True):
    """
    Single-pair snap using local TR. Returns (ok, detail_string, unchanged_bool).
    """
    src, tgt = _resolved_pair(conn)
    missing = connection_missing_local_offset_reasons(conn)
    if missing and not has_local_offsets(conn):
        return False, "skip {0} -> {1}: missing {2}".format(
            src or conn.get('source'), tgt or conn.get('target'), ', '.join(missing)), False
    if not src or not tgt:
        return False, "skip unresolved: source={0} target={1}".format(src, tgt), False

    m_loc = None
    keep_loc = False
    unchanged = False
    try:
        has_persistent_loc = bool(
            conn.get('alignLocator') and mc.objExists(conn['alignLocator']))
        m_loc, keep_loc = _get_or_build_snap_locator(
            conn, src, tgt, index=index,
            refresh_offset=not has_persistent_loc,
        )
        if keep_loc:
            conn['alignLocator'] = m_loc.p_nameLong

        before_pos = _world_position(tgt)
        before_rot = _world_rotation(tgt)

        if conn.get('setPosition', True):
            POSITION.movePointSnap(tgt, m_loc.p_nameLong)
        if conn.get('setRotation', True):
            POSITION.moveOrientSnap(tgt, m_loc.p_nameLong)

        after_pos = _world_position(tgt)
        after_rot = _world_rotation(tgt)
        pos_delta = _vector_distance(before_pos, after_pos)
        rot_delta = _vector_distance(before_rot, after_rot)
        unchanged = pos_delta < 0.001 and rot_delta < 0.01

        if unchanged:
            detail = "unchanged {0} -> {1} (pos d={2:.4f}, rot d={3:.4f})".format(
                NAMES.get_base(src), NAMES.get_base(tgt), pos_delta, rot_delta)
        else:
            detail = "ok {0} -> {1}".format(NAMES.get_base(src), NAMES.get_base(tgt))
        ok = True
    except Exception as err:
        detail = "fail {0} -> {1}: {2}".format(src, tgt, err)
        ok = False
    finally:
        if m_loc and not keep_loc and delete_loc and mc.objExists(m_loc.p_nameLong):
            mc.delete(m_loc.p_nameLong)
    return ok, detail, unchanged


def snap_connections(connections, indices=None, keep_locs=False, rig_ns=None, skel_roots=None):
    """
    Single-frame snap for links with local offsets.
    Skips missing local TR and prints a full Script Editor report.
    """
    _str_func = 'snap_connections'
    log.info(log_start(_str_func))
    result = {
        'snapped': [],
        'skipped': [],
        'failed': [],
        'unchanged': [],
        'details': [],
        'missing_report': [],
        'unchanged_details': [],
    }

    idxs = indices if indices is not None else list(range(len(connections)))
    for i in idxs:
        if i < 0 or i >= len(connections):
            continue
        conn = connections[i]
        src, tgt = _resolved_pair(conn)

        if not src or not tgt:
            src_pat = _conn_source_pattern(conn)
            tgt_pat = _conn_target_pattern(conn)
            diag = connection_resolve_diagnostics(
                conn, rig_ns=rig_ns, skel_roots=skel_roots)
            reason_bits = []
            if not src:
                reason_bits.append('source: {0}'.format(diag.get('source_reason') or 'unresolved'))
            if not tgt:
                reason_bits.append('target: {0}'.format(diag.get('target_reason') or 'unresolved'))
            reason_str = '; '.join(reason_bits)
            line = "[{0}] SKIP  unresolved  source={1}  target={2}  ({3})".format(
                i, src_pat, tgt_pat, reason_str)
            result['skipped'].append(i)
            result['missing_report'].append(line)
            result['details'].append(line)
            continue

        if not has_local_offsets(conn):
            reasons = connection_missing_local_offset_reasons(conn)
            line = "[{0}] SKIP  source={1}  target={2}  missing=[{3}]".format(
                i, src or conn.get('source'), tgt or conn.get('target'), ', '.join(reasons) or 'local offsets')
            result['skipped'].append(i)
            result['missing_report'].append(line)
            result['details'].append(line)
            continue

        ok, detail, unchanged = _snap_connection_pair(conn, index=i, delete_loc=not keep_locs)
        line = "[{0}] {1}".format(i, detail)
        result['details'].append(line)
        if ok:
            if unchanged:
                result['unchanged'].append(i)
                result['unchanged_details'].append(line)
            else:
                result['snapped'].append(i)
        else:
            result['failed'].append(i)

    log.warning(log_sub(_str_func, "Snap report"))
    print("\n=== mocap align snap report ===")
    print("snapped: {0}  unchanged: {1}  skipped: {2}  failed: {3}".format(
        len(result['snapped']), len(result['unchanged']),
        len(result['skipped']), len(result['failed'])))
    if result['missing_report']:
        print("--- missing / unresolved ---")
        for line in result['missing_report']:
            print(line)
            log.warning(line)
    if result['unchanged_details']:
        print("--- unchanged (constraints / reference locks?) ---")
        for line in result['unchanged_details']:
            print(line)
            log.warning(line)
    for line in result['details']:
        if line not in result['missing_report'] and line not in result['unchanged_details']:
            print(line)
            log.info(line)
    print("=== end snap report ===\n")
    return result


def create_debug_locs(connections, indices=None):
    """Create persistent offset locators for links that have local TR."""
    _str_func = 'create_debug_locs'
    created = []
    idxs = indices if indices is not None else list(range(len(connections)))
    for i in idxs:
        conn = connections[i]
        if not has_local_offsets(conn):
            continue
        src, tgt = _resolved_pair(conn)
        if not src or not tgt:
            continue
        if conn.get('alignLocator') and mc.objExists(conn['alignLocator']):
            mc.delete(conn['alignLocator'])
        m_loc, _ = _get_or_build_snap_locator(
            conn, src, tgt, index=i, visible=True, refresh_offset=True)
        conn['alignLocator'] = m_loc.p_nameLong
        created.append(m_loc.p_nameLong)
    log.info(log_msg(_str_func, "Created {0} locators".format(len(created))))
    return created


def delete_debug_locs(connections=None):
    """Delete session align locators (tagged or listed on connections)."""
    deleted = []
    if connections:
        for conn in connections:
            loc = conn.get('alignLocator')
            if loc and mc.objExists(loc):
                mc.delete(loc)
                deleted.append(loc)
            if 'alignLocator' in conn:
                del conn['alignLocator']
    for node in mc.ls('*.' + _DEBUG_LOC_ATTR, objectsOnly=True, long=True) or []:
        if mc.objExists(node):
            mc.delete(node)
            deleted.append(node)
    return deleted


# ---------------------------------------------------------------------------
# Bake
# ---------------------------------------------------------------------------
def bake_connections(connections, start, end, indices=None):
    """
    Timeline bake using local-TR snap for links that have offsets.
    Creates offset locs once before the frame loop.
    """
    _str_func = 'bake_connections'
    log.info(log_start(_str_func))
    cgmGEN.playback_stop()

    idxs = indices if indices is not None else list(range(len(connections)))
    active = []
    for i in idxs:
        conn = connections[i]
        if has_local_offsets(conn):
            src, tgt = _resolved_pair(conn)
            if src and tgt:
                active.append((i, conn, src, tgt))
            else:
                log.warning(log_msg(_str_func, "[{0}] skip bake — unresolved".format(i)))
        else:
            log.warning(log_msg(_str_func, "[{0}] skip local bake — no local offsets".format(i)))

    if not active:
        log.warning(log_msg(_str_func, "No local-offset links to bake"))
        return {'baked': [], 'skipped': list(idxs)}

    loc_map = {}
    preexisting = {}
    for i, conn, src, tgt in active:
        had_loc = bool(conn.get('alignLocator') and mc.objExists(conn['alignLocator']))
        preexisting[i] = conn.get('alignLocator') if had_loc else None
        m_loc, _ = _get_or_build_snap_locator(
            conn, src, tgt, index=i, refresh_offset=not had_loc)
        loc_map[i] = m_loc.p_nameLong
        if had_loc:
            conn['alignLocator'] = m_loc.p_nameLong

    bake_range = list(range(int(math.floor(start)), int(math.floor(end + 1))))
    if end < start:
        bake_range = list(range(int(math.floor(end)), int(math.floor(start + 1))))
        bake_range.reverse()

    mc.undoInfo(openChunk=True)
    try:
        for frame in bake_range:
            mc.currentTime(frame)
            for i, conn, src, tgt in active:
                loc = loc_map.get(i)
                if not loc or not mc.objExists(loc):
                    continue
                if conn.get('setPosition', True):
                    POSITION.movePointSnap(tgt, loc)
                    mc.setKeyframe(tgt + '.translate')
                if conn.get('setRotation', True):
                    POSITION.moveOrientSnap(tgt, loc)
                    mc.setKeyframe(tgt + '.rotate')
    finally:
        mc.undoInfo(closeChunk=True)
        for i, conn, src, tgt in active:
            loc = loc_map.get(i)
            if loc and mc.objExists(loc) and loc != preexisting.get(i):
                mc.delete(loc)

    log.info(log_msg(_str_func, "Baked {0} links  frames {1}-{2}".format(
        len(active), start, end)))
    return {'baked': [a[0] for a in active], 'skipped': []}


def _print_report(func_name, result, verb='done'):
    print("\n=== {0} ===".format(func_name))
    print("{0}: {1}  failed: {2}".format(
        verb, len(result.get('captured') or result.get('snapped') or []),
        len(result.get('failed') or [])))
    for line in result.get('details') or []:
        print(line)
    print("=== end ===\n")
