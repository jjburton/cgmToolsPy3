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
def _strip_ns(name):
    if not name:
        return name
    return str(name).split('|')[-1].split(':')[-1]


def _ensure_ns(name, rig_ns):
    """Join short control name with rig namespace. Accepts already-namespaced names."""
    if not name:
        return name
    name = str(name)
    if not rig_ns:
        return name
    ns = rig_ns if rig_ns.endswith(':') else (rig_ns + ':')
    leaf = name.split('|')[-1]
    if ':' in leaf:
        return leaf
    return ns + leaf


def _align_ccl_source_pattern(node_or_pattern):
    """Prefer short / portable joint pattern for CCL save."""
    if not node_or_pattern:
        return node_or_pattern
    s = str(node_or_pattern)
    if '|' in s and not mc.objExists(s):
        # already a chain pattern like Body|spine_04
        return s
    if mc.objExists(s):
        return NAMES.get_base(s)
    return _strip_ns(s)


def _align_ccl_target_pattern(node_or_pattern, rig_ns=None):
    """Namespaced short control name for CCL save."""
    if not node_or_pattern:
        return node_or_pattern
    s = str(node_or_pattern)
    if mc.objExists(s):
        short = NAMES.get_short(s)
        leaf = short.split('|')[-1]
        if ':' in leaf:
            return leaf
        return _ensure_ns(NAMES.get_base(s), rig_ns)
    leaf = s.split('|')[-1]
    if ':' in leaf:
        return leaf
    return _ensure_ns(_strip_ns(s), rig_ns)


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
def resolve_skeleton_joint(pattern, skel_roots=None, skel_ns=None):
    """
    Resolve a joint pattern under optional skeleton roots.

    Patterns: long DAG path, leaf name (foot_l), or chain token (Body|spine_04)
    where the last `|` segment is the leaf to match under roots.
    """
    _str_func = 'resolve_skeleton_joint'
    if not pattern:
        return None

    pattern = str(pattern)
    if mc.objExists(pattern):
        hits = mc.ls(pattern, long=True) or []
        if len(hits) == 1:
            return hits[0]

    leaf = pattern.split('|')[-1]
    leaf = leaf.split(':')[-1]
    if skel_ns:
        ns = skel_ns if skel_ns.endswith(':') else (skel_ns + ':')
        candidate = ns + leaf
        if mc.objExists(candidate):
            return mc.ls(candidate, long=True)[0]

    roots = _normalize_root_list(skel_roots)
    search_nodes = []
    if roots:
        for root in roots:
            if not mc.objExists(root):
                log.warning(log_msg(_str_func, "Missing skeleton root: {0}".format(root)))
                continue
            root_long = mc.ls(root, long=True)[0]
            search_nodes.append(root_long)
            search_nodes.extend(mc.listRelatives(root_long, allDescendents=True, type='joint', fullPath=True) or [])
            search_nodes.extend(mc.listRelatives(root_long, allDescendents=True, type='transform', fullPath=True) or [])
    else:
        search_nodes = (mc.ls(type='joint', long=True) or []) + (mc.ls(type='transform', long=True) or [])

    matches = []
    seen = set()
    for node in search_nodes:
        if node in seen:
            continue
        seen.add(node)
        if NAMES.get_base(node) == leaf:
            # Optional chain hint: earlier segments should appear in the long path
            chain_parts = [p for p in pattern.split('|')[:-1] if p]
            if chain_parts:
                path_l = node.lower()
                if not all(p.lower() in path_l for p in chain_parts):
                    continue
            matches.append(node)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        log.warning(log_msg(_str_func,
                            "Ambiguous '{0}' ({1} hits). Set skeleton roots. First: {2}".format(
                                pattern, len(matches), matches[0])))
        return None
    return None


def resolve_rig_control(pattern, rig_ns=None):
    """Resolve anim control by short / namespaced pattern."""
    _str_func = 'resolve_rig_control'
    if not pattern:
        return None
    pattern = str(pattern)
    if mc.objExists(pattern):
        hits = mc.ls(pattern, long=True) or []
        if len(hits) == 1:
            return hits[0]
        if hits:
            log.warning(log_msg(_str_func, "Ambiguous control '{0}': {1}".format(pattern, hits)))
            return None

    candidate = _ensure_ns(pattern, rig_ns)
    if mc.objExists(candidate):
        hits = mc.ls(candidate, long=True) or []
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            log.warning(log_msg(_str_func, "Ambiguous control '{0}': {1}".format(candidate, hits)))
            return None

    leaf = _strip_ns(pattern)
    hits = mc.ls('*:' + leaf, long=True) or []
    if rig_ns:
        ns = rig_ns.rstrip(':')
        hits = [h for h in hits if h.split('|')[-1].startswith(ns + ':')]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        log.warning(log_msg(_str_func, "Ambiguous leaf '{0}': {1}".format(leaf, hits)))
    return None


def _normalize_root_list(skel_roots):
    if not skel_roots:
        return []
    if isinstance(skel_roots, str):
        parts = [p.strip() for p in skel_roots.replace(',', ';').split(';') if p.strip()]
        return parts
    return [str(r).strip() for r in skel_roots if r]


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
    unresolved = []

    # Prefer explicit connection_data; else build from links
    if raw_conn:
        for i, conn in enumerate(raw_conn):
            c = copy.deepcopy(conn) if isinstance(conn, dict) else {}
            src_pat = c.get('source')
            tgt_pat = c.get('target')
            src_res = resolve_skeleton_joint(src_pat, skel_roots, skel_ns)
            tgt_res = resolve_rig_control(tgt_pat, rig_ns)
            c['sourcePattern'] = src_pat
            c['targetPattern'] = tgt_pat
            c['sourceResolved'] = src_res
            c['targetResolved'] = tgt_res
            if src_res:
                c['source'] = src_res
            if tgt_res:
                c['target'] = tgt_res
            if not src_res or not tgt_res:
                unresolved.append(
                    "[{0}] source='{1}' ({2}) target='{3}' ({4})".format(
                        i, src_pat, 'OK' if src_res else 'MISSING',
                        tgt_pat, 'OK' if tgt_res else 'MISSING'))
            # Normalize follow flags
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
            c = {
                'source': src_pat,
                'target': tgt_pat,
                'sourcePattern': src_pat,
                'targetPattern': tgt_pat,
                'setPosition': 'p' in str(ctype),
                'setRotation': True,
            }
            src_res = resolve_skeleton_joint(src_pat, skel_roots, skel_ns)
            tgt_res = resolve_rig_control(tgt_pat, rig_ns)
            c['sourceResolved'] = src_res
            c['targetResolved'] = tgt_res
            if src_res:
                c['source'] = src_res
            if tgt_res:
                c['target'] = tgt_res
            if not src_res or not tgt_res:
                unresolved.append(
                    "link {0}->{1} source='{2}' target='{3}'".format(si, ti, src_pat, tgt_pat))
            connections.append(c)

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


def connections_to_ccl(connections, rig_ns=None,
                       source_items=None, source_data=None,
                       target_items=None, target_data=None, links=None):
    """
    Build six-element CCL from connection dicts. Emits short patterns on save.
    Preserves list/link structure when provided; otherwise rebuilds from connections.
    """
    conn_out = []
    for c in connections or []:
        entry = {
            'source': _align_ccl_source_pattern(c.get('sourcePattern') or c.get('source')),
            'target': _align_ccl_target_pattern(c.get('targetPattern') or c.get('target'), rig_ns),
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

    # Shorten list items if they are live DAG paths
    src_short = [_align_ccl_source_pattern(x) for x in (source_items or [])]
    tgt_short = [_align_ccl_target_pattern(x, rig_ns) for x in (target_items or [])]

    return [
        src_short,
        list(source_data or []),
        tgt_short,
        list(target_data or []),
        [list(x) for x in (links or [])],
        conn_out,
    ]


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


def _create_offset_locator(source, local_translate, local_rotate, name=None):
    """Parent a locator under source with given local TR. Returns long name."""
    loc = mc.spaceLocator(name=name or 'mocapAlign_offset_loc')[0]
    loc = TRANS.parent_set(loc, source)
    if not loc:
        return None
    mc.setAttr(loc + '.translate', *list(local_translate)[:3])
    mc.setAttr(loc + '.rotate', *list(local_rotate)[:3])
    try:
        mc.addAttr(loc, ln=_DEBUG_LOC_ATTR, at='bool', dv=True)
    except Exception:
        pass
    return mc.ls(loc, long=True)[0]


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
            m_tgt = cgmMeta.cgmObject(tgt)
            m_loc = m_tgt.doLoc()
            if not m_loc:
                raise RuntimeError("doLoc failed on {0}".format(tgt))
            loc = m_loc.mNode
            loc = TRANS.parent_set(loc, src)
            lt = list(mc.getAttr(loc + '.translate')[0])
            lr = list(mc.getAttr(loc + '.rotate')[0])
            conn['localTranslate'] = lt
            conn['localRotate'] = lr
            conn['sourceResolved'] = src
            conn['targetResolved'] = tgt
            conn['source'] = src
            conn['target'] = tgt
            # Drop legacy vectors so bake prefers local path
            for k in ('positionOffset', 'offsetForward', 'offsetUp', 'offsetPosition'):
                if k in conn:
                    del conn[k]
            if keep_locs:
                conn['alignLocator'] = mc.ls(loc, long=True)[0]
                try:
                    mc.addAttr(loc, ln=_DEBUG_LOC_ATTR, at='bool', dv=True)
                except Exception:
                    pass
            else:
                mc.delete(loc)
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


def _snap_connection_pair(conn, loc=None, delete_loc=True):
    """
    Single-pair snap using local TR. Returns (ok, detail_string).
    """
    src, tgt = _resolved_pair(conn)
    missing = connection_missing_local_offset_reasons(conn)
    if missing and not has_local_offsets(conn):
        return False, "skip {0} -> {1}: missing {2}".format(
            src or conn.get('source'), tgt or conn.get('target'), ', '.join(missing))
    if not src or not tgt:
        return False, "skip unresolved: source={0} target={1}".format(src, tgt)

    owned = False
    if not loc or not mc.objExists(loc):
        loc = _create_offset_locator(src, conn['localTranslate'], conn['localRotate'],
                                     name='mocapAlign_{0}_loc'.format(NAMES.get_base(src)))
        owned = True
        if not loc:
            return False, "failed to build offset loc for {0}".format(src)

    try:
        if conn.get('setPosition', True):
            POSITION.movePointSnap(tgt, loc)
        if conn.get('setRotation', True):
            POSITION.moveOrientSnap(tgt, loc)
        detail = "ok {0} -> {1}".format(NAMES.get_base(src), NAMES.get_base(tgt))
        ok = True
    except Exception as err:
        detail = "fail {0} -> {1}: {2}".format(src, tgt, err)
        ok = False
    finally:
        if owned and delete_loc and loc and mc.objExists(loc):
            mc.delete(loc)
    return ok, detail


def snap_connections(connections, indices=None, keep_locs=False):
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
        'details': [],
        'missing_report': [],
    }

    idxs = indices if indices is not None else list(range(len(connections)))
    for i in idxs:
        if i < 0 or i >= len(connections):
            continue
        conn = connections[i]
        src, tgt = _resolved_pair(conn)
        if not has_local_offsets(conn):
            reasons = connection_missing_local_offset_reasons(conn)
            line = "[{0}] SKIP  source={1}  target={2}  missing=[{3}]".format(
                i, src or conn.get('source'), tgt or conn.get('target'), ', '.join(reasons) or 'local offsets')
            result['skipped'].append(i)
            result['missing_report'].append(line)
            result['details'].append(line)
            continue

        ok, detail = _snap_connection_pair(conn, loc=conn.get('alignLocator'),
                                           delete_loc=not keep_locs)
        line = "[{0}] {1}".format(i, detail)
        result['details'].append(line)
        if ok:
            result['snapped'].append(i)
        else:
            result['failed'].append(i)

    # Full missing-data report
    log.warning(log_sub(_str_func, "Snap report"))
    print("\n=== mocap align snap report ===")
    print("snapped: {0}  skipped: {1}  failed: {2}".format(
        len(result['snapped']), len(result['skipped']), len(result['failed'])))
    if result['missing_report']:
        print("--- missing local offset data ---")
        for line in result['missing_report']:
            print(line)
            log.warning(line)
    for line in result['details']:
        if line not in result['missing_report']:
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
        if not src:
            continue
        if conn.get('alignLocator') and mc.objExists(conn['alignLocator']):
            mc.delete(conn['alignLocator'])
        loc = _create_offset_locator(
            src, conn['localTranslate'], conn['localRotate'],
            name='mocapAlign_{0}_{1}_loc'.format(NAMES.get_base(src), NAMES.get_base(tgt or 'tgt')))
        conn['alignLocator'] = loc
        created.append(loc)
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
    # Also purge tagged leftovers
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

    # Build locators once
    loc_map = {}
    for i, conn, src, tgt in active:
        existing = conn.get('alignLocator')
        if existing and mc.objExists(existing):
            loc_map[i] = existing
        else:
            loc_map[i] = _create_offset_locator(
                src, conn['localTranslate'], conn['localRotate'],
                name='mocapBake_{0}_loc'.format(NAMES.get_base(src)))

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
        # Cleanup temp locs that were not pre-existing debug locs
        for i, conn, src, tgt in active:
            loc = loc_map.get(i)
            preexisting = conn.get('alignLocator')
            if loc and mc.objExists(loc) and loc != preexisting:
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
