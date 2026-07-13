"""
nCloth_utils
Apply cgm nCloth presets to a selected (or passed) nCloth node.

Usage:
    import cgm.core.lib.nCloth_utils as NCLOTH
    reload(NCLOTH)

    NCLOTH.profile_list()
    NCLOTH.profile_load('silk')                 # from selection
    NCLOTH.profile_load('stable', applyNucleus=True)
    NCLOTH.profile_load('cotton', targets=['nClothShape1'])
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

# Never applied from presets — leave scene collision setup as-is.
l_skipPresetAttrs = frozenset([
    'selfCollide',
    'collisionFlag',
    'selfCollisionFlag',
    'thickness',
    'selfCollideWidthScale',
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

    if 'gravityDirection' in d:
        d['gravityDirection'] = gravity_direction_get()

    if d.get('usePlane'):
        if 'planeNormal' in d:
            d['planeNormal'] = ground_plane_normal_get()

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
def _is_profile_dict(v):
    return isinstance(v, dict) and ('n' in v or 'nc' in v)


def profile_list(module=nClothPresets, key=None):
    """Sorted profile names. Optional key ('nc'/'n') filters sections."""
    cgmGEN._reloadMod(module)
    names = []
    for k, v in list(module.__dict__.items()):
        if k.startswith('_'):
            continue
        if _is_profile_dict(v):
            if key is None or v.get(key) is not None:
                names.append(k)
    return sorted(names)


def profile_get(arg=None, module=nClothPresets):
    cgmGEN._reloadMod(module)
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
    """Drop collision attrs presets should not touch."""
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
                 applyNucleus=True):
    """
    Apply a named nCloth profile to targets (or selection).

    :param arg: Profile name in cgmNCloth_presets (silk, cotton, denim, ...)
    :param targets: Node(s) or None = selection
    :param clean: If True, merge profile onto ``base`` first
    :param applyNucleus: Also apply profile['n'] to each connected nucleus
    """
    _str_func = 'profile_load'

    _d_profile = profile_get(arg, module)
    if not _d_profile:
        return log.error(cgmGEN.logString_msg(
            _str_func, "Invalid profile: {0} | have: {1}".format(arg, profile_list(module))))

    ml = get_nCloths(targets, noneValid=True)
    if not ml:
        return log.error(cgmGEN.logString_msg(
            _str_func, "Select an nCloth, its transform, or a meshed cloth object"))

    if clean:
        _base = profile_get('base', module) or {}
        _d_nc = copy.deepcopy(_base.get('nc') or {})
        _d_n = copy.deepcopy(_base.get('n') or {})
        _d_nc.update(copy.deepcopy(_d_profile.get('nc') or {}))
        _d_n.update(copy.deepcopy(_d_profile.get('n') or {}))
    else:
        _d_nc = copy.deepcopy(_d_profile.get('nc') or {})
        _d_n = copy.deepcopy(_d_profile.get('n') or {})

    if applyNucleus and _d_n:
        _remap_nucleus_scene_axes(_d_n)
        log.info(cgmGEN.logString_msg(
            _str_func, "Scene up: {0} | gravityDirection: {1}".format(
                scene_up_get(), _d_n.get('gravityDirection'))))

    _d_nc = _filter_preset_dict(_d_nc)

    _nucleus_done = set()
    for nc in ml:
        log.info(cgmGEN.logString_msg(_str_func, "nCloth: {0} | profile: {1}".format(nc, arg)))
        _apply_attr_dict(nc, _d_nc)

        if applyNucleus and _d_n:
            nucleus = get_nucleus(nc, noneValid=True)
            if nucleus and nucleus not in _nucleus_done:
                log.info(cgmGEN.logString_msg(_str_func, "nucleus: {0}".format(nucleus)))
                _apply_attr_dict(nucleus, _d_n)
                _nucleus_done.add(nucleus)

    return ml


def apply(arg='cotton', **kws):
    """Alias for profile_load — handy from the script editor."""
    return profile_load(arg, **kws)
