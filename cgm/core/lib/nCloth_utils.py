"""
nCloth_utils
Apply cgm nCloth presets to a selected (or passed) nCloth node.

Usage:
    import cgm.core.lib.nCloth_utils as NCLOTH
    reload(NCLOTH)

    NCLOTH.profile_list()
    NCLOTH.profile_list(category='fabric')
    NCLOTH.profile_load('silk')                 # fabric only (base solver)
    NCLOTH.profile_load('cotton', solver='solver_quality')
    NCLOTH.profile_load('flag', solver='solver_balanced', wind='wind_flag')
"""
__MAYALOCAL = 'NCLOTH'

# From Python =============================================================
import copy
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# From Maya =============================================================
import maya.cmds as mc

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGEN
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.lib import attribute_utils as ATTR
from cgm.core.lib import search_utils as SEARCH
from cgm.core.lib import position_utils as POS
import cgm.core.presets.cgmNCloth_presets as nClothPresets

d_shortHand = {
    'nCloth': 'nc',
    'nClothShape': 'nc',
    'nucleus': 'n',
}

# UI / doc names -> actual nBase / nCloth plugs
d_attrAlias = {
    'mass': 'pointMass',
}

# Never applied from presets — leave scene collision / structural setup as-is.
l_skipPresetAttrs = frozenset([
    'isDynamic',
    'selfCollide',
    'collisionFlag',
    'selfCollisionFlag',
    'thickness',
    'selfCollideWidthScale',
    'localSpaceOutput',
    'collide',
    'ignoreSolverGravity',
    'ignoreSolverWind',
])

# Runtime / structural — omit from query → preset capture.
l_nucleus_query_ignore = frozenset([
    'currentTime',
    'startFrame',
    'lastTime',
    'enable',
    'timingOutput',
])

# Scalar presets cannot set these directly
l_skipAttrTypes = (
    'doubleArray', 'floatArray', 'intArray', 'stringArray',
    'pointArray', 'vectorArray', 'matrix', 'compound',
)


#>>> Scene axes
#=========================================================================
def scene_up_get():
    """Maya scene up axis: 'y' or 'z'."""
    return POS.scene_up_axis_get()


def gravity_direction_get():
    """Nucleus gravity direction (world down) from scene up."""
    v = [0.0, 0.0, 0.0]
    v[POS.ground_plane_up_index()] = -1.0
    return v


def ground_plane_normal_get():
    """Nucleus ground plane normal (world up) from scene up."""
    v = [0.0, 0.0, 0.0]
    v[POS.ground_plane_up_index()] = 1.0
    return v


def _remap_nucleus_scene_axes(d):
    """Rewrite gravity / ground plane vectors for current scene up."""
    if not d:
        return d

    _gravity_keys = ('gravityDirection', 'gravityDirectionX', 'gravityDirectionY', 'gravityDirectionZ')
    if any(k in d for k in _gravity_keys):
        _g = gravity_direction_get()
        d['gravityDirection'] = _g
        d['gravityDirectionX'] = _g[0]
        d['gravityDirectionY'] = _g[1]
        d['gravityDirectionZ'] = _g[2]

    if d.get('usePlane') or 'planeNormal' in d or any(
            k in d for k in ('planeNormalX', 'planeNormalY', 'planeNormalZ')):
        _n = ground_plane_normal_get()
        d['planeNormal'] = _n
        d['planeNormalX'] = _n[0]
        d['planeNormalY'] = _n[1]
        d['planeNormalZ'] = _n[2]

    return d


#>>> Resolve
#=========================================================================
def get_nCloth(node=None, noneValid=True):
    """
    Resolve an nClothShape from a node or selection.

    Accepts:
        - nClothShape
        - nCloth transform
        - mesh / poly connected to an nCloth (input or output)
    """
    _str_func = 'get_nCloth'

    if node is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            if noneValid:
                return None
            raise ValueError("|{0}| >> Nothing selected".format(_str_func))
        node = _sel[0]

    node = VALID.mNodeString(node)
    _type = VALID.get_mayaType(node)

    if _type in ('nCloth',):
        # Shape itself (Maya reports nCloth for the shape)
        if mc.objectType(node) == 'nCloth':
            return node
        shapes = mc.listRelatives(node, shapes=True, type='nCloth', fullPath=True) or []
        if shapes:
            return shapes[0]

    if SEARCH.is_shape(node) and mc.objectType(node) == 'nCloth':
        return node

    # Transform owning an nCloth shape
    shapes = mc.listRelatives(node, shapes=True, type='nCloth', fullPath=True) or []
    if shapes:
        return shapes[0]

    # Mesh connected to nCloth (inputMesh / outputMesh history)
    history = mc.listHistory(node, future=False) or []
    future = mc.listHistory(node, future=True) or []
    for n in history + future:
        if mc.objectType(n) == 'nCloth':
            return n

    connections = mc.listConnections(node, type='nCloth', shapes=True) or []
    if connections:
        return connections[0]

    if noneValid:
        log.warning("|{0}| >> No nCloth found from: {1}".format(_str_func, node))
        return None
    raise ValueError("|{0}| >> No nCloth found from: {1}".format(_str_func, node))


def get_nCloths(nodes=None, noneValid=True):
    """Resolve unique nClothShapes from nodes or selection."""
    if nodes is None:
        nodes = mc.ls(sl=True, long=True) or []
    else:
        nodes = VALID.listArg(nodes)

    found = []
    for n in nodes:
        nc = get_nCloth(n, noneValid=True)
        if nc and nc not in found:
            found.append(nc)

    if not found and not noneValid:
        raise ValueError("|get_nCloths| >> No nCloth nodes resolved")
    return found


def get_out_mesh_shape(nCloth=None, noneValid=True):
    """Return the sim output mesh shape driven by an nClothShape."""
    _str_func = 'get_out_mesh_shape'
    nc = get_nCloth(nCloth, noneValid=noneValid)
    if not nc:
        return None

    con = mc.listConnections('{0}.outputMesh'.format(nc), type='mesh', shapes=True) or []
    if con:
        return con[0]

    con = mc.listConnections('{0}.outputMesh'.format(nc)) or []
    for n in con:
        if SEARCH.is_shape(n) and VALID.get_mayaType(n) == 'mesh':
            return n
        shapes = mc.listRelatives(n, shapes=True, type='mesh', fullPath=True) or []
        if shapes:
            return shapes[0]

    if noneValid:
        log.warning("|{0}| >> No output mesh for nCloth: {1}".format(_str_func, nc))
        return None
    raise ValueError("|{0}| >> No output mesh for nCloth: {1}".format(_str_func, nc))


def get_out_mesh_transform(nCloth=None, noneValid=True):
    """Return the transform of the nCloth sim output mesh."""
    shape = get_out_mesh_shape(nCloth, noneValid=noneValid)
    if not shape:
        return None
    parents = mc.listRelatives(shape, parent=True, fullPath=True) or []
    return parents[0] if parents else shape


def get_nucleus(nCloth=None, noneValid=True):
    """Return the nucleus connected to an nClothShape (currentState link)."""
    _str_func = 'get_nucleus'
    nc = get_nCloth(nCloth, noneValid=noneValid)
    if not nc:
        return None

    for plug in ('currentState', 'startState', 'nextState'):
        con = mc.listConnections('{0}.{1}'.format(nc, plug), type='nucleus') or []
        if con:
            return con[0]

    con = mc.listConnections(nc, type='nucleus') or []
    if con:
        return con[0]

    if noneValid:
        log.warning("|{0}| >> No nucleus on: {1}".format(_str_func, nc))
        return None
    raise ValueError("|{0}| >> No nucleus on: {1}".format(_str_func, nc))


#>>> Profiles
#=========================================================================
d_profileAliases = {
    'preview': 'solver_preview',
}


def _is_profile_dict(v):
    return isinstance(v, dict) and ('n' in v or 'nc' in v)


def profile_resolve(name, module=nClothPresets):
    """Resolve deprecated profile names."""
    if not name:
        return name
    return d_profileAliases.get(name, name)


def profile_kind(name, module=nClothPresets):
    """Return profile kind: fabric | solver | wind | utility | base."""
    name = profile_resolve(name, module=module)
    cgmGEN._reloadMod(module)
    kind = module.__dict__.get('d_profileKind', {}).get(name)
    if kind:
        return kind
    _d = profile_get(name, module)
    if not _d:
        return None
    if _d.get('nc') and not _d.get('n'):
        return 'fabric'
    if _d.get('n') and not _d.get('nc'):
        if name.startswith('wind_'):
            return 'wind'
        if name.startswith('solver_'):
            return 'solver'
    return 'utility'


def profile_list(module=nClothPresets, key=None, category=None):
    """
    Sorted profile names.

    :param key: Optional 'nc' / 'n' — profile must define that section.
    :param category: Optional kind filter: fabric | solver | wind | utility
    """
    cgmGEN._reloadMod(module)
    names = []
    for k, v in list(module.__dict__.items()):
        if k.startswith('_') or k == 'd_profileKind':
            continue
        if k in d_profileAliases:
            continue
        if not _is_profile_dict(v):
            continue
        if key is not None and v.get(key) is None:
            continue
        if category and profile_kind(k, module) != category:
            continue
        names.append(k)
    return sorted(names)


def _merge_profile_dicts(module=nClothPresets, fabric=None, solver=None, wind=None,
                         clean=True, apply_base=False):
    """
    Layer profiles into nc/n dicts with section isolation.

    - fabric: seeds base.nc when clean, never writes n unless solver/wind also passed
    - solver / wind: write n only (never seed full base.n)
    - utility: seeds both sections when clean, then overlays
    - apply_base: full base.nc + base.n reset
    """
    _base = profile_get('base', module) or {}
    _d_nc = {}
    _d_n = {}

    _fabric = profile_resolve(fabric, module) if fabric else None
    _solver = profile_resolve(solver, module) if solver else None
    _wind = profile_resolve(wind, module) if wind else None
    _utility = None

    if _fabric:
        _kind = profile_kind(_fabric, module)
        if _kind == 'utility':
            _utility = _fabric
            _fabric = None
        elif _kind == 'solver':
            _solver = _solver or _fabric
            _fabric = None
        elif _kind == 'wind':
            _wind = _wind or _fabric
            _fabric = None
        elif _kind == 'base':
            apply_base = True
            _fabric = None

    if apply_base:
        _d_nc = copy.deepcopy(_base.get('nc') or {})
        _d_n = copy.deepcopy(_base.get('n') or {})
        return _d_nc, _d_n

    if _utility:
        if clean:
            _d_nc = copy.deepcopy(_base.get('nc') or {})
            _d_n = copy.deepcopy(_base.get('n') or {})
        _p = profile_get(_utility, module) or {}
        _d_nc.update(copy.deepcopy(_p.get('nc') or {}))
        _d_n.update(copy.deepcopy(_p.get('n') or {}))
        return _d_nc, _d_n

    if _fabric:
        if clean:
            _d_nc = copy.deepcopy(_base.get('nc') or {})
        _p = profile_get(_fabric, module) or {}
        _d_nc.update(copy.deepcopy(_p.get('nc') or {}))

    if _wind:
        _p = profile_get(_wind, module) or {}
        _d_n.update(copy.deepcopy(_p.get('n') or {}))

    if _solver:
        _p = profile_get(_solver, module) or {}
        _d_n.update(copy.deepcopy(_p.get('n') or {}))

    return _d_nc, _d_n


def _resolve_nuclei(targets=None):
    """Resolve nucleus nodes from targets or selection (no nCloth required)."""
    if targets is None:
        nodes = mc.ls(sl=True, long=True) or []
    else:
        nodes = VALID.listArg(targets)

    found = []
    for n in nodes:
        if not n or not mc.objExists(n):
            continue
        node = VALID.mNodeString(n)
        if mc.objectType(node) == 'nucleus':
            if node not in found:
                found.append(node)
            continue
        # nCloth → connected nucleus
        nc = get_nCloth(node, noneValid=True)
        if nc:
            nucleus = get_nucleus(nc, noneValid=True)
            if nucleus and nucleus not in found:
                found.append(nucleus)
    return found


def profile_get(arg=None, module=nClothPresets):
    cgmGEN._reloadMod(module)
    arg = profile_resolve(arg, module)
    _d = module.__dict__.get(arg)
    if _is_profile_dict(_d):
        return _d
    return None


def _resolve_attr(node, attr):
    """Map aliases and skip compound parents that are not directly settable."""
    candidates = [attr]
    if attr in d_attrAlias:
        candidates.append(d_attrAlias[attr])

    for a in candidates:
        if not mc.attributeQuery(a, node=node, exists=True):
            continue
        if mc.attributeQuery(a, node=node, multi=True):
            continue

        plug = '{0}.{1}'.format(node, a)
        try:
            atype = mc.getAttr(plug, type=True)
        except Exception:
            continue

        if atype in l_skipAttrTypes:
            continue

        children = mc.attributeQuery(a, node=node, listChildren=True) or []
        if children and atype not in ('double3', 'float3', 'short3', 'long3'):
            continue

        return a

    return None


def _filter_preset_dict(d):
    """Drop runtime / collision attrs presets should not touch."""
    if not d:
        return d
    return {k: v for k, v in list(d.items()) if k not in l_skipPresetAttrs}


def _apply_attr_dict(node, d):
    """Set attrs on node; skip missing / failed quietly with warnings."""
    if not node or not d:
        return 0
    _count = 0
    for a, v in list(d.items()):
        if a in l_skipPresetAttrs:
            continue
        attr = _resolve_attr(node, a)
        if not attr:
            log.debug("Skip attr: {0}.{1}".format(node, a))
            continue
        try:
            ATTR.set(node, attr, v)
            _count += 1
        except Exception as err:
            log.warning("Failed to set {0}.{1} = {2} | {3}".format(node, attr, v, err))
    return _count


def profile_load(arg='cotton',
                 targets=None,
                 module=nClothPresets,
                 clean=True,
                 applyNucleus=True,
                 solver=None,
                 wind=None):
    """
    Apply layered nCloth profiles to targets (or selection).

    Cloth (fabric) writes ``nc`` only. Simulation layers (solver / wind) write ``n``
    only. Utility / base may write both. ``clean`` seeds fabric from ``base.nc``
    (or both sections for utility); solver/wind never dump full ``base.n``.

    :param arg: Fabric profile (default), or solver/wind/utility/base.
    :param solver: Optional solver profile (solver_preview, solver_quality, …).
    :param wind: Optional wind profile (wind_calm, wind_flag, …).
    :param clean: Seed from ``base`` for fabric/utility paths (see merge contract).
    :param applyNucleus: Apply merged ``n`` section to connected (or target) nucleus.
    """
    _str_func = 'profile_load'

    arg = profile_resolve(arg, module)
    _kind = profile_kind(arg, module)

    _fabric = arg
    _solver = solver
    _wind = wind
    _apply_base = False

    if _kind == 'solver' and not _solver:
        _solver = arg
        _fabric = None
    elif _kind == 'wind' and not _wind:
        _wind = arg
        _fabric = None
    elif _kind == 'utility':
        _fabric = arg
        _solver = None
        _wind = None
    elif _kind == 'base':
        _fabric = None
        _solver = None
        _wind = None
        _apply_base = True

    if _fabric == 'base':
        _fabric = None
        _apply_base = True

    if _fabric and not profile_get(_fabric, module) and not (_solver or _wind or _apply_base):
        return log.error(cgmGEN.logString_msg(
            _str_func, "Invalid profile: {0} | have: {1}".format(
                arg, profile_list(module))))

    if _solver and not profile_get(_solver, module):
        return log.error(cgmGEN.logString_msg(
            _str_func, "Invalid solver profile: {0}".format(_solver)))

    if _wind and not profile_get(_wind, module):
        return log.error(cgmGEN.logString_msg(
            _str_func, "Invalid wind profile: {0}".format(_wind)))

    _d_nc, _d_n = _merge_profile_dicts(
        module=module, fabric=_fabric, solver=_solver, wind=_wind,
        clean=clean, apply_base=_apply_base)

    _label = _fabric or arg or 'base'
    if _solver:
        _label = '{0}+{1}'.format(_label, _solver)
    if _wind:
        _label = '{0}+{1}'.format(_label, _wind)

    if applyNucleus and _d_n:
        _remap_nucleus_scene_axes(_d_n)
        log.info(cgmGEN.logString_msg(
            _str_func, "Scene up: {0} | gravityDirection: {1}".format(
                scene_up_get(), _d_n.get('gravityDirection'))))

    _d_nc = _filter_preset_dict(_d_nc)
    _d_n = _filter_preset_dict(_d_n) if _d_n else _d_n

    ml = get_nCloths(targets, noneValid=True)

    # Simulation-only (solver/wind): allow nucleus targets without nCloth.
    if not ml and not _d_nc and _d_n and applyNucleus:
        nuclei = _resolve_nuclei(targets)
        if not nuclei:
            return log.error(cgmGEN.logString_msg(
                _str_func, "Select an nCloth or nucleus for simulation preset: {0}".format(_label)))
        for nucleus in nuclei:
            log.info(cgmGEN.logString_msg(
                _str_func, "nucleus: {0} | profile: {1}".format(nucleus, _label)))
            _apply_attr_dict(nucleus, _d_n)
        return nuclei

    if not ml:
        return log.error(cgmGEN.logString_msg(
            _str_func, "Select an nCloth, its transform, or a meshed cloth object"))

    _nucleus_done = set()
    for nc in ml:
        log.info(cgmGEN.logString_msg(_str_func, "nCloth: {0} | profile: {1}".format(nc, _label)))
        if _d_nc:
            _apply_attr_dict(nc, _d_nc)

        if applyNucleus and _d_n:
            nucleus = get_nucleus(nc, noneValid=True)
            if nucleus and nucleus not in _nucleus_done:
                log.info(cgmGEN.logString_msg(_str_func, "nucleus: {0}".format(nucleus)))
                _apply_attr_dict(nucleus, _d_n)
                _nucleus_done.add(nucleus)

    return ml


#>>> Query (selection → preset-shaped dict)
#=========================================================================
def _query_node_attrs(node, attr_names, skip=None):
    """Read preset-relevant attrs from a node; skip missing / unsettable."""
    if not node or not attr_names:
        return {}

    _skip = skip or frozenset()
    _d = {}
    for a in attr_names:
        if a in _skip:
            continue
        _attr = _resolve_attr(node, a)
        if not _attr:
            continue
        try:
            _v = ATTR.get(node, _attr)
        except Exception as err:
            log.debug("Skip query {0}.{1} | {2}".format(node, _attr, err))
            continue
        if _v is not None:
            _d[_attr] = _v
    return _d


def profile_diff_from_base(profile, module=nClothPresets):
    """Return profile sections with only attrs that differ from ``base``."""
    if not profile:
        return {}

    _base = profile_get('base', module) or {}
    _out = {}
    for section in ('nc', 'n', 'hs'):
        _sec = profile.get(section)
        if not _sec:
            continue
        _base_sec = _base.get(section) or {}
        _diff = {}
        for k, v in list(_sec.items()):
            if _base_sec.get(k) != v:
                _diff[k] = v
        if _diff:
            _out[section] = _diff
    return _out


def profile_format_paste(name, profile):
    """Format a profile dict as paste-ready Python for cgmNCloth_presets."""
    if not profile:
        return ''

    lines = ["{0} = {{".format(name)]
    for section in ('nc', 'n', 'hs'):
        if section not in profile or not profile[section]:
            continue
        lines.append("    '{0}': {{".format(section))
        for k in sorted(profile[section].keys()):
            lines.append("        '{0}': {1},".format(k, repr(profile[section][k])))
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("# Add to d_profileKind in cgmNCloth_presets.py:")
    if profile.get('nc') and not profile.get('n'):
        lines.append("# '{0}': 'fabric',".format(name))
    elif profile.get('n') and not profile.get('nc'):
        if name.startswith('wind_'):
            lines.append("# '{0}': 'wind',".format(name))
        else:
            lines.append("# '{0}': 'solver',  # or 'wind'".format(name))
    else:
        lines.append("# '{0}': 'utility',  # or 'fabric'".format(name))
    return '\n'.join(lines)


def query_nucleus_settings(nucleus=None, differential=True, module=nClothPresets):
    """Query nucleus attrs in preset ``n`` section shape."""
    _str_func = 'query_nucleus_settings'
    nucleus = VALID.mNodeString(nucleus, noneValid=False, calledFrom=_str_func)

    _base = profile_get('base', module) or {}
    _profile = {
        'n': _query_node_attrs(
            nucleus,
            list((_base.get('n') or {}).keys()),
            skip=l_nucleus_query_ignore,
        ),
    }
    _profile_use = profile_diff_from_base(_profile, module=module) if differential else _profile

    return {
        'sourceType': 'nucleus',
        'source': {'nucleus': nucleus},
        'profile': _profile_use,
        'paste': profile_format_paste('my_solver', _profile_use),
        'notes': [
            'gravityDirection is remapped to scene up when presets are applied',
        ],
    }


def query_settings(nCloth=None, differential=True, module=nClothPresets):
    """
    Query nCloth + connected nucleus as a preset-shaped dict (diff from ``base`` by default).

    :returns: dict with sourceType, source, profile, paste, notes
    """
    _str_func = 'query_settings'
    nc = get_nCloth(nCloth, noneValid=False)
    nucleus = get_nucleus(nc, noneValid=True)

    _base = profile_get('base', module) or {}
    _profile = {}
    _nc_attrs = list((_base.get('nc') or {}).keys())
    if _nc_attrs:
        _profile['nc'] = _query_node_attrs(nc, _nc_attrs, skip=l_skipPresetAttrs)

    if nucleus:
        _n_attrs = list((_base.get('n') or {}).keys())
        if _n_attrs:
            _profile['n'] = _query_node_attrs(nucleus, _n_attrs, skip=l_nucleus_query_ignore)

    _profile_use = profile_diff_from_base(_profile, module=module) if differential else _profile
    _xform = (mc.listRelatives(nc, parent=True, fullPath=True) or [nc])[0]
    _suggested = _xform.split('|')[-1].split(':')[-1]

    return {
        'sourceType': 'nCloth',
        'source': {
            'nClothShape': nc,
            'nClothTransform': _xform,
            'nucleus': nucleus,
        },
        'suggestedPresetName': _suggested,
        'profile': _profile_use,
        'paste': profile_format_paste(_suggested, _profile_use),
        'notes': [
            'profile contains only attrs that differ from cgmNCloth_presets.base',
            'gravityDirection is remapped to scene up when presets are applied',
            'cloth vs simulation: fabric writes nc; solver/wind write n; base.n env is query + explicit base/utility reset',
            'excluded from presets: isDynamic, collision attrs, localSpaceOutput, collide, ignoreSolverGravity/Wind',
        ],
    }


def query_settings_selection(nodes=None, differential=True):
    """
    Resolve selection to nCloth, nucleus, cgmDynFK mapped cloth, or hair/nucleus (dynFK presets).

    :returns: query result dict or None
    """
    _str_func = 'query_settings_selection'
    nodes = VALID.listArg(nodes) if nodes else (mc.ls(sl=True, long=True) or [])

    if not nodes:
        log.warning("|{0}| >> Nothing selected".format(_str_func))
        return None

    for n in nodes:
        nc = get_nCloth(n, noneValid=True)
        if nc:
            return query_settings(nc, differential=differential)

    for n in nodes:
        if mc.objectType(n) == 'nucleus':
            return query_nucleus_settings(n, differential=differential)

    import cgm.core.cgm_Meta as cgmMeta
    import cgm.core.rig.dynamic_utils as RIGDYN

    for n in nodes:
        mObj = cgmMeta.validateObjArg(n, noneValid=True)
        if not mObj:
            continue
        if getattr(mObj, 'mClass', None) == 'cgmDynFK':
            mCloth = RIGDYN.get_mapped_cloth(mObj)
            if mCloth:
                _dat = query_settings(mCloth.mNode, differential=differential)
                _dat['source']['cgmDynFK'] = mObj.mNode
                return _dat
            mNuc = mObj.getMessageAsMeta('mNucleus')
            if mNuc:
                _dat = query_nucleus_settings(mNuc.mNode, differential=differential)
                _dat['source']['cgmDynFK'] = mObj.mNode
                return _dat

    for n in nodes:
        try:
            _prof = RIGDYN.get_dat(n, differential=True)
        except Exception:
            _prof = None
        if not _prof:
            continue
        mTar = cgmMeta.validateObjArg(n, noneValid=True)
        _type = mTar.getMayaType() if mTar else mc.objectType(n)
        _key = RIGDYN.d_shortHand.get(_type, _type)
        _profile = _prof if (_key in _prof) else {_key: _prof}
        _short = (mTar.p_nameBase if mTar else n.split('|')[-1].split(':')[-1])
        return {
            'sourceType': _key,
            'source': {'node': VALID.mNodeString(n)},
            'suggestedPresetName': _short,
            'profile': _profile,
            'paste': profile_format_paste(_short, _profile),
            'notes': ['dynFK preset shape (cgmDynFK_presets)'],
        }

    log.warning("|{0}| >> No queryable sim node in selection".format(_str_func))
    return None


def apply(arg='cotton', **kws):
    """Alias for profile_load — handy from the script editor."""
    return profile_load(arg, **kws)
