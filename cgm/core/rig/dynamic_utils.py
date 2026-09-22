import maya.cmds as mc
from cgm.core import cgm_General as cgmGEN
import cgm.core.lib.distance_utils as DIST
import cgm.core.lib.attribute_utils as ATTR
import cgm.core.lib.euclid as euclid
import cgm.core.lib.rigging_utils as CORERIG
import cgm.core.lib.locator_utils as LOC
import cgm.core.lib.curve_Utils as CURVES
from cgm.core.cgmPy.validateArgs import simpleAxis
import cgm.core.lib.name_utils as NAMES
import cgm.core.cgm_Meta as cgmMeta
from cgm.core.lib import math_utils as MATHUTILS
import cgm.core.classes.NodeFactory as NODEFACTORY
import cgm.core.lib.snap_utils as SNAP
import cgm.core.lib.transform_utils as TRANS
import cgm.core.lib.constraint_utils as CONSTRAINTS
import cgm.core.rig.constraint_utils as RIGCONSTRAINTS

import pprint
import copy
import maya.mel as mel
from cgm.core.cgmPy import validateArgs as VALID
import cgm.core.lib.shared_data as SHARED
import importlib

__MAYALOCAL = 'RIGDYN'

import cgm.core.presets.cgmDynFK_presets as dynFKPresets

import logging
import time

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import cgm.core.classes.GuiFactory as CGMUI

_BAKE_INPUT_TR_ATTRS = ['translate', 'rotate']
_bake_input_run_counter = 0


def _dag_str(node):
    """Return a Maya DAG name string for mc.* (never pass meta to mc)."""
    if node is None:
        return None
    if isinstance(node, str):
        return node
    _name = getattr(node, 'mNode', None)
    if isinstance(_name, str):
        return _name
    raise TypeError(cgmGEN.logString_msg(
        '_dag_str', 'Expected str or meta with mNode str, got {0}'.format(type(node))))


class chain(object):
    hairSystem = None
    nucleus = None
    follicles = []
    ml_follicles = []
    outCurves = []
    targets = []
    baseName = None
        
    
    def __init__(self, objs = None, fwd = 'z+', up = 'y+', hairSystem=None, baseName = 'cgmDynHair', name = None):
        self.hairSystem = hairSystem
        
        _sel = mc.ls(sl=1)
        if not objs:
            if _sel:
                objs = _sel
                
        self.baseName = baseName
                
        if objs:
            self.CreateChain(objs, fwd, up, name)
            


    def CreateChain(self, objs = None, fwd = 'z+', up='y+',name = None):
        _str_func = 'CreateChain'
        
        objs = cgmMeta.asMeta( mc.ls(sl=True) )
        
        if not objs:
            return log.warning("No objects passed. Unable to createChain")
            
        if name is None:
            name = objs[-1].p_nameBase

        self.targets = self.targets + objs

        fwdAxis = simpleAxis(fwd)
        upAxis = simpleAxis(up)

        crvPositions = []

        for obj in objs:
            crvPositions.append(obj.p_position)

        crvPositions.append( DIST.get_pos_by_axis_dist(objs[-1], fwdAxis.p_string,
                                                       DIST.get_distance_between_points(crvPositions[-1],crvPositions[-2])) )

        crvPositions.insert(0, DIST.get_pos_by_axis_dist(objs[0], fwdAxis.inverse.p_string,
                                                         DIST.get_distance_between_points(crvPositions[0],crvPositions[1])*.5) )

        crv = CORERIG.create_at(create='curve',l_pos= crvPositions, baseName = name)

        # make the dynamic setup
        b_existing = False
        if self.hairSystem != None:
            log.info(cgmGEN.logString_msg(_str_func,'Using existing system: {0}'.format(self.hairSystem)))
            mc.select(self.hairSystem, add=True)
            b_existing = True
            
        mel.eval('makeCurvesDynamic 2 { "0", "0", "1", "1", "0" }')

        # get relevant nodes
        follicle = mc.listRelatives(crv,parent=True)[0]
        mFollicle = cgmMeta.asMeta(follicle)
        mFollicle.rename("{0}_foll".format(name))
        follicle = mFollicle.mNode
        self.ml_follicles.append(mFollicle)
        
        follicleShape = mc.listRelatives(mFollicle.mNode, shapes=True)[0]
        self.hairSystem = mc.listRelatives( mc.listConnections('%s.currentPosition' % follicleShape)[0], shapes=True)[0]
        if not b_existing:
            mHairSys = cgmMeta.asMeta(self.hairSystem)
            mHairSysDag = mHairSys.getTransform(asMeta=1)
            
            mHairSysDag.rename("{0}_hairSys".format(self.baseName))
            self.hairSystem = mHairSys.mNode
            
        outCurve = mc.listConnections('%s.outCurve' % follicle)[0]
        outCurveShape = mc.listRelatives(outCurve, shapes=True)[0]
        self.nucleus = mc.listConnections( '%s.currentState' % self.hairSystem )[0]
        if not b_existing:
            pass
        mc.select((mc.listRelatives(
            _dag_str(objs[0]), parent=True, type='transform', fullPath=True) or [None])[0])

        self.follicles.append(follicle)
        self.outCurves.append(outCurve)
        
        # set default properties
        mc.setAttr( '%s.pointLock' % follicleShape, 1 )
        mc.parentConstraint(
            (mc.listRelatives(
                _dag_str(objs[0]), parent=True, type='transform', fullPath=True) or [None])[0],
            follicle, mo=True)

        # create locators on objects
        locators = []
        prs = []

        for i, obj in enumerate(objs):
            loc = LOC.create(obj.getNameLong())
            locators.append(loc)
            
            aimNull = mc.group(em=True)
            aimNull = mc.rename('%s_aim' % obj.getShortName())
            
            poc = mc.createNode('pointOnCurveInfo', name='%s_pos' % loc)
            pocAim = mc.createNode('pointOnCurveInfo', name='%s_aim' % loc)
            pr = CURVES.getUParamOnCurve(loc, outCurve)
            
            mc.connectAttr( '%s.worldSpace[0]' % outCurveShape, '%s.inputCurve' % poc, f=True )
            mc.connectAttr( '%s.worldSpace[0]' % outCurveShape, '%s.inputCurve' % pocAim, f=True )

            mc.setAttr( '%s.parameter' % poc, pr )
            
            if i < len(objs)-1:
                nextpr = CURVES.getUParamOnCurve(objs[i+1], outCurve)
                mc.setAttr('%s.parameter' % pocAim, (nextpr + pr) * .5)
            else:
                mc.setAttr( '%s.parameter' % pocAim, len(objs)+1 )
            
            locParent = mc.group(em=True)
            locParent = mc.rename( '%s_pos' % obj.getShortName() )

            mc.connectAttr( '%s.position' % poc, '%s.translate' % locParent)
            mc.connectAttr( '%s.position' % pocAim, '%s.translate' % aimNull)
            
            _worldUp = (mc.listRelatives(
                _dag_str(objs[0]), parent=True, type='transform', fullPath=True) or [None])[0]
            aimConstraint = mc.aimConstraint(
                aimNull, locParent, aimVector=fwdAxis.p_vector, upVector=upAxis.p_vector,
                worldUpType='objectrotation', worldUpVector=upAxis.p_vector, worldUpObject=_worldUp)

            mc.parent(loc, locParent)

    def SelectTargets(self):
        mc.select(cl = True)
        for obj in self.targets:
            mc.select(obj, add=True)
            
            
    def report(self):
        pprint.pprint(self.__dict__)
        
    def delete(self):
        pass


def _transform_has_follicle_shape(node):
    node = VALID.mNodeString(node)
    return bool(mc.listRelatives(node, shapes=True, type='follicle') or [])


def _resolve_follicle_from_incurve(inCurve):
    """Return follicle transform for a dynamic hair inCurve after makeCurvesDynamic."""
    inCurve = VALID.mNodeString(inCurve)
    _parents = mc.listRelatives(inCurve, parent=True, fullPath=True) or []
    for _p in _parents:
        if _transform_has_follicle_shape(_p):
            return _p
    _crvShapes = mc.listRelatives(inCurve, shapes=True, type='nurbsCurve', fullPath=True) or []
    for _shape in _crvShapes:
        _follicleShapes = mc.listConnections(_shape, type='follicle', s=False, d=True) or []
        for _fs in _follicleShapes:
            _folParents = mc.listRelatives(_fs, parent=True, fullPath=True) or []
            if _folParents:
                return _folParents[0]
    return None


def _resolve_start_curve_from_follicle(follicleShape):
    """Return (transform, nurbsCurve shape) wired to follicle startPosition after MCD."""
    follicleShape = VALID.mNodeString(follicleShape)
    if not mc.attributeQuery('startPosition', node=follicleShape, exists=True):
        return None, None
    _src = mc.listConnections(
        '{0}.startPosition'.format(follicleShape),
        source=True, destination=False, plugs=False) or []
    if not _src:
        return None, None
    _node = _src[0]
    if mc.nodeType(_node) == 'nurbsCurve':
        _shape = _node
        _parents = mc.listRelatives(_shape, parent=True, fullPath=True) or []
        return (_parents[0] if _parents else None), _shape
    if mc.nodeType(_node) == 'transform':
        _shapes = mc.listRelatives(_node, shapes=True, type='nurbsCurve', fullPath=True) or []
        return _node, (_shapes[0] if _shapes else None)
    return None, None


# Default follicle sim segment length (scene linear units — typically cm in Maya).
FOLLICLE_FIXED_SEGMENT_LENGTH = 1.0
FOLLICLE_DEFAULT_SAMPLE_DENSITY = 1.0

HAIR_FOLLOW_MODE_LEGACY = 'legacy'
HAIR_FOLLOW_MODE_SPLINE = 'splineIk'


def _configure_follicle_segment_sampling(follicleShape, fixedSegmentLength=False,
                                         segmentLength=None, l_positions=None,
                                         sampleDensity=None):
    """
    Follicle sim/collision sampling for dynFK hair chains.

    Default (fixedSegmentLength=False): follicle.sampleDensity (default 1.0).
    Optional fixedSegmentLength=True: uniform world-length segments (segmentLength, default 1 unit).
    """
    _str_func = '_configure_follicle_segment_sampling'
    follicleShape = VALID.mNodeString(follicleShape)
    if sampleDensity is None:
        sampleDensity = FOLLICLE_DEFAULT_SAMPLE_DENSITY
    if fixedSegmentLength:
        _seg = segmentLength if segmentLength is not None else FOLLICLE_FIXED_SEGMENT_LENGTH
        if mc.attributeQuery('fixedSegmentLength', node=follicleShape, exists=True):
            mc.setAttr('{0}.fixedSegmentLength'.format(follicleShape), 1)
        if mc.attributeQuery('segmentLength', node=follicleShape, exists=True):
            mc.setAttr('{0}.segmentLength'.format(follicleShape), _seg)
        log.debug(cgmGEN.logString_msg(
            _str_func, 'fixedSegmentLength=on, segmentLength={0}'.format(_seg)))
    else:
        if mc.attributeQuery('fixedSegmentLength', node=follicleShape, exists=True):
            mc.setAttr('{0}.fixedSegmentLength'.format(follicleShape), 0)
        if mc.attributeQuery('sampleDensity', node=follicleShape, exists=True):
            mc.setAttr('{0}.sampleDensity'.format(follicleShape), float(sampleDensity))
        log.debug(cgmGEN.logString_msg(
            _str_func, 'sampleDensity={0}, fixedSegmentLength=off'.format(sampleDensity)))


def _warn_hair_system_extra_segments(hairSystemShape):
    """Shared hairSystem bend/subdivision attrs add collision samples beyond joint CV count."""
    hairSystemShape = VALID.mNodeString(hairSystemShape)
    _extra = 0
    _sub = 0
    if mc.attributeQuery('extraBendLinks', node=hairSystemShape, exists=True):
        _extra = mc.getAttr('{0}.extraBendLinks'.format(hairSystemShape)) or 0
    if mc.attributeQuery('subSegments', node=hairSystemShape, exists=True):
        _sub = mc.getAttr('{0}.subSegments'.format(hairSystemShape)) or 0
    if _extra or _sub:
        log.info(cgmGEN.logString_msg(
            '_warn_hair_system_extra_segments',
            'hairSystem extraBendLinks={0} subSegments={1} — collision chain has more/shorter segments than joint CV spans'.format(
                _extra, _sub)))


def _wire_follicle_start_curve(follicleShape, curveShape):
    """Connect nurbsCurve worldSpace to follicle startPosition (post-MCD input curve)."""
    follicleShape = VALID.mNodeString(follicleShape)
    curveShape = VALID.mNodeString(curveShape)
    _dest = '{0}.startPosition'.format(follicleShape)
    for _src in mc.listConnections(_dest, source=True, destination=False, plugs=True) or []:
        try:
            mc.disconnectAttr(_src, _dest)
        except Exception:
            pass
    mc.connectAttr('{0}.worldSpace[0]'.format(curveShape), _dest, f=True)


def _resolve_follicle_transform_and_shape(follicle):
    """Resolve follicle transform + shape from transform, shape, or cgmMeta."""
    follicle = VALID.mNodeString(follicle)
    if mc.nodeType(follicle) == 'follicle':
        follicle_shape = follicle
        follicle_transform = mc.listRelatives(follicle_shape, parent=True, fullPath=True)[0]
    else:
        follicle_transform = follicle
        shapes = mc.listRelatives(
            follicle_transform, shapes=True, noIntermediate=True, fullPath=True, type='follicle') or []
        if not shapes:
            raise ValueError('No follicle shape found under: {0}'.format(follicle_transform))
        follicle_shape = shapes[0]
    return follicle_transform, follicle_shape


def _resolve_nurbs_curve_transform_and_shape(curve):
    """Resolve NURBS curve transform + shape from transform, shape, or cgmMeta."""
    curve = VALID.mNodeString(curve)
    if mc.nodeType(curve) == 'nurbsCurve':
        curve_shape = curve
        curve_transform = mc.listRelatives(curve_shape, parent=True, fullPath=True)[0]
    else:
        curve_transform = curve
        shapes = mc.listRelatives(
            curve_transform, shapes=True, noIntermediate=True, fullPath=True, type='nurbsCurve') or []
        if not shapes:
            raise ValueError('No NURBS curve shape found under: {0}'.format(curve_transform))
        curve_shape = shapes[0]
    return curve_transform, curve_shape


def follicle_set_input_curve(input_curve, follicle):
    """
    Connect a start/input curve to an nHair follicle (local + startPositionMatrix).

    Args:
        input_curve: nurbsCurve transform or shape
        follicle: follicle transform or follicle shape

    Returns:
        follicle shape node name
    """
    _str_func = 'follicle_set_input_curve'
    if input_curve is None or follicle is None:
        raise ValueError('input_curve and follicle are required')

    input_curve, curve_shape = _resolve_nurbs_curve_transform_and_shape(input_curve)
    _, follicle_shape = _resolve_follicle_transform_and_shape(follicle)

    _dest = '{0}.startPosition'.format(follicle_shape)
    for _src in mc.listConnections(_dest, source=True, destination=False, plugs=True) or []:
        try:
            mc.disconnectAttr(_src, _dest)
        except Exception:
            pass
    _dest_matrix = '{0}.startPositionMatrix'.format(follicle_shape)
    for _src in mc.listConnections(_dest_matrix, source=True, destination=False, plugs=True) or []:
        try:
            mc.disconnectAttr(_src, _dest_matrix)
        except Exception:
            pass

    mc.connectAttr('{0}.local'.format(curve_shape), _dest, force=True)
    mc.connectAttr('{0}.worldMatrix[0]'.format(input_curve), _dest_matrix, force=True)
    log.info(cgmGEN.logString_msg(_str_func, '{0} -> {1}'.format(curve_shape, follicle_shape)))
    return follicle_shape


def follicle_regenerate_out_curve(follicle, base_name=None):
    """
    Create a new output curve for an existing nHair follicle via outCurve -> create.

    Returns:
        Out curve transform (short name path from mc.curve)
    """
    _str_func = 'follicle_regenerate_out_curve'
    if follicle is None:
        raise ValueError('follicle is required')

    follicle_transform, follicle_shape = _resolve_follicle_transform_and_shape(follicle)

    old_shapes = mc.listConnections(
        '{0}.outCurve'.format(follicle_shape),
        source=False, destination=True, shapes=True, type='nurbsCurve') or []
    old_transforms = []
    for shape in old_shapes:
        parents = mc.listRelatives(shape, parent=True, fullPath=True) or []
        old_transforms.extend(parents)

    _leaf = follicle_transform.split('|')[-1]
    _name = base_name if base_name else '{0}_outputCurve'.format(_leaf)
    output_curve = mc.curve(
        degree=1,
        point=[(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        name=_name)
    output_shape = mc.listRelatives(
        output_curve, shapes=True, noIntermediate=True, fullPath=True, type='nurbsCurve')[0]

    mc.connectAttr(
        '{0}.outCurve'.format(follicle_shape),
        '{0}.create'.format(output_shape),
        force=True)
    mc.setAttr('{0}.inheritsTransform'.format(output_curve), 0)

    old_transforms = list(set(old_transforms))
    for old_transform in old_transforms:
        if mc.objExists(old_transform) and old_transform != output_curve:
            try:
                mc.delete(old_transform)
            except Exception:
                pass

    log.info(cgmGEN.logString_msg(
        _str_func, 'Created {0} from {1}.outCurve'.format(output_curve, follicle_shape)))
    return output_curve


def _follicle_outcurve_meta(follicle):
    """Return cgmMeta for the transform wired to follicle.outCurve (after create / rest eval)."""
    _, follicle_shape = _resolve_follicle_transform_and_shape(follicle)
    shapes = mc.listConnections(
        '{0}.outCurve'.format(follicle_shape),
        source=False, destination=True, shapes=True, type='nurbsCurve') or []
    if not shapes:
        return None
    parents = mc.listRelatives(shapes[0], parent=True, fullPath=True) or []
    if not parents:
        return None
    return cgmMeta.asMeta(parents[0])


def _configure_follicle_outcurve_degree(follicleShape, degree=2):
    """Set follicle outCurve rebuild degree (1=linear, 2=cubic default)."""
    follicleShape = VALID.mNodeString(follicleShape)
    try:
        _degree = int(degree)
    except (TypeError, ValueError):
        _degree = 2
    _degree = MATHUTILS.Clamp(_degree, 1, 3)
    if mc.attributeQuery('degree', node=follicleShape, exists=True):
        mc.setAttr('{0}.degree'.format(follicleShape), _degree)
    return _degree


_D_HAIR_INCURVE_CREATE = {
    1: 'curveLinear',
    2: 'curveQuadratic',
    3: 'curve',
}


def _create_hair_incurve(l_pos, name, inCurveDegree=1):
    """Build hair inCurve via CORERIG.create_at (linear / quadratic / cubic) — no rebuildCurve."""
    try:
        _deg = int(inCurveDegree)
    except (TypeError, ValueError):
        _deg = 1
    _deg = MATHUTILS.Clamp(_deg, 1, 3)
    _create = _D_HAIR_INCURVE_CREATE.get(_deg, 'curveLinear')
    return CORERIG.create_at(create=_create, l_pos=l_pos, baseName=name)


def _resolve_hair_follow_mode(hairFollowMode=None, mDynFK=None, kws=None):
    if hairFollowMode:
        return hairFollowMode
    if kws and kws.get('hairFollowMode'):
        return kws.get('hairFollowMode')
    if mDynFK is not None:
        return getattr(mDynFK, 'hairFollowMode', HAIR_FOLLOW_MODE_SPLINE)
    return HAIR_FOLLOW_MODE_SPLINE


def _get_chain_hair_follow_mode(mGrp):
    mGrp = cgmMeta.asMeta(mGrp)
    if mGrp.hasAttr('hairFollowMode'):
        _mode = getattr(mGrp, 'hairFollowMode', None)
        if _mode in (HAIR_FOLLOW_MODE_LEGACY, HAIR_FOLLOW_MODE_SPLINE):
            return _mode
    return HAIR_FOLLOW_MODE_LEGACY


def _hair_chain_integrity_missing(mGrp):
    """
    Missing required hair/cloth chain wiring (empty list = OK for its mode).
    Used by Details UI and rebuild guards when create failed partway.
    """
    mGrp = cgmMeta.asMeta(mGrp)
    _chainMode = getattr(mGrp, 'chainMode', None) or 'hair'
    if _chainMode == 'clothAttach':
        _missing = []
        if not (mGrp.msgList_get('mTargets') or []):
            _missing.append('mTargets')
        return _missing
    _missing = []
    for _msg in ('mFollicle', 'mInCrv'):
        if not mGrp.getMessageAsMeta(_msg):
            _missing.append(_msg)
    for _msg in ('mTargets', 'mObjJointChain'):
        if not (mGrp.msgList_get(_msg) or []):
            _missing.append(_msg)
    if _get_chain_hair_follow_mode(mGrp) == HAIR_FOLLOW_MODE_SPLINE:
        if not mGrp.getMessageAsMeta('mOutCrv'):
            _missing.append('mOutCrv')
    return _missing


def _resolve_follicle_sample_density(mGrp, mSetup=None):
    """Sample density stored on chain grp, else setup default."""
    if mGrp and mGrp.hasAttr('follicleSampleDensity'):
        try:
            return float(mGrp.follicleSampleDensity)
        except (TypeError, ValueError):
            pass
    if mSetup is not None:
        return float(getattr(mSetup, 'follicleSampleDensity', FOLLICLE_DEFAULT_SAMPLE_DENSITY))
    return FOLLICLE_DEFAULT_SAMPLE_DENSITY


def _consolidate_hair_incurve_after_mcd(mInCrv, mFollicleShape, mGrp, name, ml_sim, l_pos, skinCluster,
                                        fixedSegmentLength=False, follicleSegmentLength=None,
                                        inCurveDegree=1, use_follicle_input_curve=False,
                                        sampleDensity=None):
    """
    After makeCurvesDynamic, rebuild the follicle input curve from sim joint positions (`l_pos`).

    MCD often leaves the cgm *_inCrv transform as an empty shell (or with a non-driving
    shape) while follicle.startPosition uses a different curve — CVs and skin diverge.
    Replace the dynamic input with a fresh curve, wire startPosition, and rebind skin.
    Caller `l_pos` is ignored; positions from `_hair_incurve_l_pos_for_chain` (sim joints + curve extendEnd).
    """
    _str_func = '_consolidate_hair_incurve_after_mcd'
    _follicleShape = mFollicleShape.mNode if hasattr(mFollicleShape, 'mNode') else mFollicleShape
    if not _hair_sim_joint_chain_ordered(ml_sim):
        raise ValueError(cgmGEN.logString_msg(_str_func, 'No sim joints for skinCluster'))

    _oldInCrv = mInCrv.mNode
    _prevStartXform, _prevStartShape = _resolve_start_curve_from_follicle(_follicleShape)

    for _node in {n for n in (_oldInCrv, _prevStartXform) if n and mc.objExists(n)}:
        if _node == _oldInCrv:
            try:
                mGrp.disconnectChildNode(_node, 'mInCrv')
            except Exception:
                pass
        try:
            mc.delete(_node)
        except Exception as err:
            log.debug(cgmGEN.logString_msg(_str_func, 'Delete {0}: {1}'.format(_node, err)))

    if skinCluster and mc.objExists(skinCluster):
        try:
            mc.delete(skinCluster)
        except Exception:
            pass

    mGrp = cgmMeta.asMeta(mGrp)
    ml_baseTargets = mGrp.msgList_get('mBaseTargets') or mGrp.msgList_get('mTargets')
    _settings = _get_hair_chain_follow_settings(mGrp)
    if mGrp.hasAttr('fwd'):
        fwdAxis = simpleAxis(mGrp.fwd)
    else:
        fwdAxis = None
    l_pos = _hair_incurve_l_pos_for_chain(
        mGrp, ml_sim, ml_baseTargets,
        extendStart=_settings.get('extendStart'),
        extendEnd=_settings.get('extendEnd'),
        upSetup=_settings.get('upSetup'),
        fwdAxis=fwdAxis,
        addEndJoint=_settings.get('addEndJoint'))
    crv = _create_hair_incurve(l_pos, name, inCurveDegree)
    mInCrv = cgmMeta.asMeta(crv)
    mInCrv.rename('{0}_inCrv'.format(name))
    mInCrv.p_parent = mGrp
    mGrp.connectChildNode(mInCrv.mNode, 'mInCrv')

    _shape = mc.listRelatives(mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
    if use_follicle_input_curve:
        follicle_set_input_curve(mInCrv.mNode, _follicleShape)
    else:
        _wire_follicle_start_curve(_follicleShape, _shape)

    mSkinCluster, ml_sim = _hair_incurve_skin_bind(
        ml_sim, mInCrv, '{0}_skinCluster'.format(name))

    _configure_follicle_segment_sampling(
        _follicleShape,
        fixedSegmentLength=fixedSegmentLength,
        segmentLength=follicleSegmentLength,
        l_positions=l_pos,
        sampleDensity=sampleDensity)

    log.info(cgmGEN.logString_msg(
        _str_func, 'Rebuilt startPosition inCurve: {0} ({1} CVs, {2} joints)'.format(
            mInCrv.mNode, len(l_pos), len(ml_sim))))
    return mInCrv


def _configure_follicle_rest_match_start(follicleShape):
    """Follicle restPose Same As Start — rest outCurve follows start curve."""
    follicleShape = VALID.mNodeString(follicleShape)
    if mc.attributeQuery('restPose', node=follicleShape, exists=True):
        mc.setAttr('{0}.restPose'.format(follicleShape), 1)


def _refresh_hair_rest_output(follicleShape, hairSystemShape):
    """Evaluate hair rest state after inCurve rebuild (outCurve may still hold pre-rebuild CVs)."""
    follicleShape = VALID.mNodeString(follicleShape)
    hairSystemShape = VALID.mNodeString(hairSystemShape)
    _time = mc.currentTime(q=True)
    _start = 1
    if mc.attributeQuery('startFrame', node=hairSystemShape, exists=True):
        _start = mc.getAttr('{0}.startFrame'.format(hairSystemShape))
    for _node in (follicleShape, hairSystemShape):
        mc.dgdirty(_node)
    mc.currentTime(_start, edit=True)
    mc.currentTime(_time, edit=True)


def _sync_hair_outcurve_to_incurve(inCurveShape, outCurveShape):
    """Copy inCurve CVs onto outCurve at build rest (MCD outCurve is stale after inCurve rebuild)."""
    _str_func = '_sync_hair_outcurve_to_incurve'
    inCurveShape = VALID.mNodeString(inCurveShape)
    outCurveShape = VALID.mNodeString(outCurveShape)
    if not mc.objExists(inCurveShape) or not mc.objExists(outCurveShape):
        return False
    try:
        CURVES.match(inCurveShape, outCurveShape, autoRebuild=True, keepOriginal=True, space='ws')
        log.info(cgmGEN.logString_msg(_str_func, 'Matched outCurve CVs to inCurve at rest'))
        return True
    except Exception as err:
        log.warning(cgmGEN.logString_msg(_str_func, 'match failed: {0}'.format(err)))
        return False


def _finalize_hair_outcurve_rest(follicleShape, hairSystemShape, inCurveShape, outCurveShape,
                                 fixedSegmentLength=None, follicleSegmentLength=None,
                                 l_positions=None, sampleDensity=None):
    """
    Configure follicle + outCurve at rest after inCurve is wired.

    Order (normative — do not reorder):
    1. restPose Same As Start
    2. follicle segment sampling (when build passes sampling args)
    3. evaluate rest at startFrame — follicle rebuilds outCurve from startPosition
    4. sync outCurve CVs to inCurve — must run **after** refresh or eval wipes CVs
    """
    _str_func = '_finalize_hair_outcurve_rest'
    _configure_follicle_rest_match_start(follicleShape)
    if fixedSegmentLength is not None:
        _configure_follicle_segment_sampling(
            follicleShape,
            fixedSegmentLength=fixedSegmentLength,
            segmentLength=follicleSegmentLength,
            l_positions=l_positions,
            sampleDensity=sampleDensity)
    _refresh_hair_rest_output(follicleShape, hairSystemShape)
    _sync_hair_outcurve_to_incurve(inCurveShape, outCurveShape)
    log.debug(cgmGEN.logString_msg(_str_func, 'Done'))


def _store_hair_chain_follow_metadata(mGrp, aimUpMode, addEndJoint, extendStart, upControl, upSetup, extendEnd=None,
                                      advancedTwist=None):
    """Persist follow-rig settings on chain grp for rebuild."""
    mGrp.doStore('aimUpMode', aimUpMode)
    if advancedTwist is not None:
        mGrp.doStore('advancedTwist', bool(advancedTwist))
    if not _hair_add_end_joint_active(addEndJoint):
        mGrp.doStore('addEndJoint', False)
    elif isinstance(addEndJoint, bool):
        mGrp.doStore('addEndJoint', True)
    else:
        try:
            mGrp.doStore('addEndJoint', float(addEndJoint))
        except (TypeError, ValueError):
            mGrp.doStore('addEndJoint', False)
    if not _hair_curve_extend_end_active(extendEnd):
        mGrp.doStore('extendEnd', False)
    elif isinstance(extendEnd, bool):
        mGrp.doStore('extendEnd', True)
    else:
        try:
            mGrp.doStore('extendEnd', float(extendEnd))
        except (TypeError, ValueError):
            mGrp.doStore('extendEnd', False)
    if extendStart is not None:
        mGrp.doStore('extendStart', extendStart)
    mGrp.doStore('upControl', bool(upControl))
    mGrp.doStore('upSetup', upSetup)


def _get_hair_chain_follow_settings(mGrp):
    """Read follow-rig settings from chain grp (safe defaults for older chains)."""
    mGrp = cgmMeta.asMeta(mGrp)
    _settings = {
        'aimUpMode': 'joint',
        'addEndJoint': _hair_add_end_joint_from_grp(mGrp),
        'extendEnd': _hair_curve_extend_end_from_grp(mGrp),
        'extendStart': None,
        'upControl': False,
        'upSetup': 'guess',
        'advancedTwist': _hair_advanced_twist_from_grp(mGrp),
    }
    for _key in ('aimUpMode', 'extendStart', 'upControl', 'upSetup', 'advancedTwist'):
        if mGrp.hasAttr(_key):
            _val = getattr(mGrp, _key, _settings[_key])
            if _val is not None and _val != '':
                _settings[_key] = _val
    return _settings


def _chain_targets_connected(mGrp):
    """Return True if any chain target has incoming constraints (Connect Targets state)."""
    for mObj in cgmMeta.asMeta(mGrp).msgList_get('mTargets') or []:
        if mObj.getConstraintsTo():
            return True
    return False


def _resolve_hair_start_frame(mDynFK, mGrp=None):
    """Resolve sim rest frame for hair chain rebuild / connect."""
    if mGrp is not None and (getattr(mGrp, 'chainMode', None) or 'hair') == 'hair':
        mHairSys = hair_system_resolve_for_chain(mGrp, mDynFK, backfill=False)
        if mHairSys and mc.attributeQuery('startFrame', node=mHairSys.mNode, exists=True):
            return mc.getAttr('{0}.startFrame'.format(mHairSys.mNode))
    mHairSys = mDynFK.getMessageAsMeta('mHairSysShape')
    if mHairSys and mc.attributeQuery('startFrame', node=mHairSys.mNode, exists=True):
        return mc.getAttr('{0}.startFrame'.format(mHairSys.mNode))
    mNucleus = mDynFK.getMessageAsMeta('mNucleus')
    if mNucleus and mc.attributeQuery('startFrame', node=mNucleus.mNode, exists=True):
        return mc.getAttr('{0}.startFrame'.format(mNucleus.mNode))
    return mc.playbackOptions(q=True, min=True)


def _tear_down_hair_chain_follow(mGrp):
    """Remove POC/aim locator follow rig from a hair chain grp (keeps sim + curves)."""
    _str_func = '_tear_down_hair_chain_follow'
    mGrp = cgmMeta.asMeta(mGrp)
    _name = chain_cgm_name(mGrp)

    _l_delete = []
    for _msg in ('mParents', 'mAims', 'mLocs'):
        for mObj in mGrp.msgList_get(_msg) or []:
            for _con in CONSTRAINTS.get_constraintsFrom(mObj.mNode) or []:
                try:
                    mc.delete(_con)
                except Exception:
                    pass
            _l_delete.append(mObj.mNode)

    mOutCrv = mGrp.getMessageAsMeta('mOutCrv')
    if mOutCrv:
        for _shape in mOutCrv.getShapes(asMeta=False) or []:
            for _node in mc.listConnections(_shape, source=False, destination=True) or []:
                if mc.nodeType(_node) == 'pointOnCurveInfo':
                    _l_delete.append(_node)

    for _node in mc.ls('*{0}*aimTanScale*'.format(_name), '*{0}*aimPos*'.format(_name),
                         '*{0}*_pma*'.format(_name),
                         type=('multiplyDivide', 'plusMinusAverage')) or []:
        if mc.objExists(_node):
            _l_delete.append(_node)

    for _child in mGrp.getChildren(asMeta=True) or []:
        if _child.p_nameBase == 'chain_{0}_up'.format(_name):
            _l_delete.append(_child.mNode)
        elif _child.p_nameBase.startswith('chain_{0}_up'.format(_name)):
            _l_delete.append(_child.mNode)

    _l_delete = list({n for n in _l_delete if n and mc.objExists(n)})
    if _l_delete:
        try:
            mc.delete(_l_delete)
        except Exception as err:
            log.warning(cgmGEN.logString_msg(_str_func, 'delete: {0}'.format(err)))

    for _msg in ('mLocs', 'mAims', 'mParents'):
        ATTR.msgList_clean(mGrp.mNode, _msg)

    log.info(cgmGEN.logString_msg(_str_func, mGrp.p_nameBase))


def chain_cgm_name(mGrp):
    """Resolved per-chain name token from grp ``cgmName`` or ``chain_{name}_grp``."""
    mGrp = cgmMeta.asMeta(mGrp)
    if mGrp.hasAttr('cgmName') and mGrp.cgmName:
        return str(mGrp.cgmName)
    _base = mGrp.p_nameBase or ''
    if _base.startswith('chain_') and _base.endswith('_grp'):
        return _base[6:-4]
    return _base


def chain_setup_index(mSetup, mGrp):
    """Index of a chain grp on the cgmDynFK setup ``chain`` msgList (None if not linked)."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    if not mSetup or not mGrp:
        return None
    try:
        _idx = mSetup.msgList_index('chain', mGrp.mNode)
        if _idx is not None:
            return _idx
    except ValueError:
        pass
    _grp_long = NAMES.get_long(mGrp.mNode)
    for _i, mChain in enumerate(mSetup.msgList_get('chain') or []):
        if not mChain:
            continue
        if mChain.mNode == mGrp.mNode:
            return _i
        try:
            if NAMES.get_long(mChain.mNode) == _grp_long:
                return _i
        except Exception:
            pass
    return None


def chain_connect_to_setup(mSetup, mGrp):
    """
    Register a chain grp on the setup via ``chain`` msgList (``chain_0``, ``chain_1``, … + ``owner``).

    Discovery is by message index, not DAG name. Stores ``chainIndex`` on the grp when possible.
    """
    _str_func = 'chain_connect_to_setup'
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    if not mSetup or not mGrp:
        return None
    _existing = chain_setup_index(mSetup, mGrp)
    if _existing is not None:
        try:
            mGrp.doStore('chainIndex', int(_existing))
        except Exception:
            pass
        return _existing
    try:
        ATTR.msgList_clean(mSetup.mNode, 'chain')
    except Exception as err:
        log.debug(cgmGEN.logString_msg(_str_func, 'msgList_clean chain: {0}'.format(err)))
    _idx = mSetup.msgList_append('chain', mGrp.mNode, connectBack='owner')
    try:
        mGrp.doStore('chainIndex', int(_idx))
    except Exception:
        pass
    log.info(cgmGEN.logString_msg(
        _str_func, 'chain[{0}] msgList -> {1}'.format(_idx, mGrp.p_nameShort)))
    return _idx


def chain_sync_chain_index_attrs(mSetup):
    """Align ``chainIndex`` on each chain grp with its setup msgList order."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return 0
    _n = 0
    for _i, mGrp in enumerate(mSetup.msgList_get('chain') or []):
        if not mGrp:
            continue
        try:
            if not mGrp.hasAttr('chainIndex') or int(mGrp.chainIndex) != _i:
                mGrp.doStore('chainIndex', _i)
                _n += 1
        except Exception:
            try:
                mGrp.doStore('chainIndex', _i)
                _n += 1
            except Exception:
                pass
    return _n


def _chain_clean_name_token(name):
    """Normalize a chain name token (same rules as ``chain_set_name``)."""
    _s = VALID.stringArg(name, noneValid=True)
    if not _s:
        return None
    _s = str(_s).strip()
    if not _s:
        return None
    _s = NAMES.clean(_s, replaceChar='_', stripTailing=True)
    return _s or None


def chain_names_in_use(mSetup, exclude_idx=None):
    """Set of ``chain_cgm_name`` tokens already on a cgmDynFK setup."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return set()
    _used = set()
    for _i, mGrp in enumerate(mSetup.msgList_get('chain') or []):
        if exclude_idx is not None and _i == exclude_idx:
            continue
        if mGrp:
            _used.add(chain_cgm_name(mGrp))
    return _used


def chain_resolve_unique_name(mSetup, name, exclude_idx=None):
    """
    Return a chain name token unique among setup chains.

    When ``name`` is taken, appends ``_02``, ``_03``, … (logs once when adjusted).
    """
    _str_func = 'chain_resolve_unique_name'
    _base = _chain_clean_name_token(name)
    if not _base:
        _base = 'chain'
    _used = chain_names_in_use(mSetup, exclude_idx=exclude_idx)
    if _base not in _used:
        return _base
    for _n in range(2, 1000):
        _candidate = '{0}_{1:02d}'.format(_base, _n)
        if _candidate not in _used:
            log.info(cgmGEN.logString_msg(
                _str_func, "Chain name '{0}' already used — using '{1}'".format(_base, _candidate)))
            return _candidate
    return '{0}_dup'.format(_base)


def chain_fixup_duplicate_names(mDynFK):
    """
    Rename later chains when multiple chains share the same ``cgmName`` / grp token.

    Uses ``chain_set_name`` so hair infrastructure renames with the chain.
    """
    _str_func = 'chain_fixup_duplicate_names'
    mSetup = cgmMeta.validateObjArg(mDynFK, noneValid=True)
    if not mSetup or getattr(mSetup, 'mClass', None) != 'cgmDynFK':
        return 0
    ml = mSetup.msgList_get('chain') or []
    _seen = set()
    _fixed = 0
    for _i, mGrp in enumerate(ml):
        if not mGrp:
            continue
        _n = chain_cgm_name(mGrp)
        if _n not in _seen:
            _seen.add(_n)
            continue
        _new = chain_resolve_unique_name(mSetup, _n)
        if chain_set_name(mSetup, _i, _new):
            _seen.add(_new)
            _fixed += 1
            log.info(cgmGEN.logString_msg(
                _str_func, 'Chain [{0}] renamed {1} -> {2}'.format(_i, _n, _new)))
    chain_sync_chain_index_attrs(mSetup)
    return _fixed


def _chain_rename_meta_short(mObj, new_short):
    if not mObj or not mc.objExists(_dag_str(mObj)):
        return
    if mObj.p_nameBase == new_short:
        return
    try:
        mObj.rename(new_short)
    except Exception as err:
        log.warning(cgmGEN.logString_msg(
            '_chain_rename_meta_short', '{0} -> {1}: {2}'.format(mObj.p_nameBase, new_short, err)))


def _chain_rename_hair_infrastructure(mGrp, old_name, new_name):
    """Rename hair chain nodes that embed the chain name token (not rig targets)."""
    if not old_name or old_name == new_name:
        return

    _suspend = False
    try:
        _suspend = mc.refresh(q=True, suspend=True)
    except Exception:
        pass

    try:
        for mJ in mGrp.msgList_get('mObjJointChain') or []:
            _base = mJ.p_nameBase
            _prefix = '{0}_sim_'.format(old_name)
            if _base.startswith(_prefix):
                _chain_rename_meta_short(mJ, '{0}_sim_{1}'.format(new_name, _base[len(_prefix):]))

        for mJ in mGrp.msgList_get('mDrivenJointChain') or []:
            _base = mJ.p_nameBase
            _prefix = '{0}_driven_'.format(old_name)
            if _base.startswith(_prefix):
                _chain_rename_meta_short(mJ, '{0}_driven_{1}'.format(new_name, _base[len(_prefix):]))

        for mChild in mGrp.getChildren(asMeta=True) or []:
            _base = mChild.p_nameBase
            if _base == 'chain_{0}_up'.format(old_name):
                _chain_rename_meta_short(mChild, 'chain_{0}_up'.format(new_name))
            elif _base == 'chain_{0}_end_loc'.format(old_name):
                _chain_rename_meta_short(mChild, 'chain_{0}_end_loc'.format(new_name))

        mInCrv = mGrp.getMessageAsMeta('mInCrv')
        mOutCrv = mGrp.getMessageAsMeta('mOutCrv')
        mFollicle = mGrp.getMessageAsMeta('mFollicle')
        if mInCrv:
            _chain_rename_meta_short(mInCrv, '{0}_inCrv'.format(new_name))
        if mOutCrv:
            _chain_rename_meta_short(mOutCrv, '{0}_outCrv'.format(new_name))
        if mFollicle:
            _chain_rename_meta_short(mFollicle, '{0}_foll'.format(new_name))

        _old_prefix = '{0}_'.format(old_name)
        for _msg in ('mLocs', 'mAims', 'mParents'):
            for mObj in mGrp.msgList_get(_msg) or []:
                _base = mObj.p_nameBase
                if _base.startswith(_old_prefix):
                    _chain_rename_meta_short(
                        mObj, '{0}{1}'.format(new_name, _base[len(old_name):]))
    finally:
        try:
            mc.refresh(suspend=_suspend)
        except Exception:
            pass


def chain_set_name(mDynFK, idx, name):
    """
    Rename a setup chain grp and hair infrastructure; updates chain grp ``cgmName`` (not rig targets).

    :param mDynFK: cgmDynFK setup meta
    :param idx: chain msgList index
    :param name: new chain name token
    """
    _str_func = 'chain_set_name'
    mSetup = cgmMeta.validateObjArg(mDynFK, noneValid=True)
    if not mSetup or getattr(mSetup, 'mClass', None) != 'cgmDynFK':
        return log.warning(cgmGEN.logString_msg(_str_func, 'Owner is not a cgmDynFK setup'))

    ml = mSetup.msgList_get('chain') or []
    if idx is None or idx >= len(ml):
        return log.warning(cgmGEN.logString_msg(_str_func, 'No chain at idx {0}'.format(idx)))

    mGrp = ml[idx]
    _new = _chain_clean_name_token(name)
    if not _new:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Empty or invalid name'))

    _old = chain_cgm_name(mGrp)
    if _new == _old:
        return True

    for _i, mOther in enumerate(ml):
        if _i == idx:
            continue
        if chain_cgm_name(mOther) == _new:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'Chain name already in use: {0}'.format(_new)))

    _chainMode = getattr(mGrp, 'chainMode', None) or 'hair'
    mc.undoInfo(openChunk=True, chunkName='cgmDynSimTool chain rename')
    try:
        try:
            mGrp.dagLock(False)
        except Exception:
            pass

        if _chainMode != 'clothAttach':
            _chain_rename_hair_infrastructure(mGrp, _old, _new)

        _chain_rename_meta_short(mGrp, 'chain_{0}_grp'.format(_new))
        mGrp.doStore('cgmName', _new)

        try:
            mGrp.dagLock()
        except Exception:
            pass
    finally:
        mc.undoInfo(closeChunk=True)

    log.info(cgmGEN.logString_msg(_str_func, '{0} -> {1} ({2})'.format(_old, _new, mGrp.p_nameBase)))
    return True


def _build_hair_chain_follow(mGrp, outCurveShape, ml, ml_baseTargets, ml_sim, name,
                             fwdAxis, upAxis, _l_paramFrac=None,
                             upSetup='guess', upControl=False, aimUpMode='joint',
                             addEndJoint=False, extendEnd=False):
    """
    Build POC + aim locator follow rig on outCurve.

    Returns (ml_locs, ml_aims, ml_prts).
    """
    _str_func = '_build_hair_chain_follow'
    mGrp = cgmMeta.asMeta(mGrp)
    mOutShape = cgmMeta.asMeta(outCurveShape, noneValid=True)
    outCurveShape = mOutShape.mNode if mOutShape else VALID.mNodeString(outCurveShape)
    ml_sim = _hair_normalize_sim_chain(ml_sim)

    if _l_paramFrac is None:
        _l_jointPos = [mObj.p_position for mObj in ml_baseTargets]
        _l_paramFrac = CURVES.polyline_length_fractions(_l_jointPos)

    ml_locs = []
    ml_aims = []
    ml_prts = []

    _upVector = None
    if upSetup == 'guess':
        log.debug(cgmGEN.logString_msg(_str_func, 'Resolving up/aim'))
        mPoci_base = cgmMeta.asMeta(CURVES.create_pointOnInfoNode(outCurveShape, 1))
        _upVector = mPoci_base.normalizedNormal
        log.debug(cgmGEN.logString_msg(_str_func, 'upVector: {0}'.format(_upVector)))

    mUp = ml[0].doCreateAt(setClass=1)
    mUp.rename('chain_{0}_up'.format(name))
    mUp.p_parent = mGrp

    if _upVector:
        SNAP.aim_atPoint(
            mUp.mNode,
            DIST.get_pos_by_vec_dist(mUp.p_position, _upVector, 10),
            aimAxis='y+', upAxis='z+')

    if upControl:
        log.debug(cgmGEN.logString_msg(_str_func, 'upControl'))
        if len(ml_baseTargets) > 1:
            sizeControl = DIST.get_distance_between_targets(
                [mObj.mNode for mObj in ml_baseTargets], True)
        else:
            sizeControl = DIST.get_bb_size(ml[0], True, 'max')
        crv = CURVES.create_controlCurve(mUp.mNode, 'arrowSingle', size=sizeControl, direction='y+')
        CORERIG.shapeParent_in_place(mUp.mNode, crv, False)
        mUpGroup = mUp.doGroup(True, True, asMeta=True, typeModifier='master', setClass='cgmObject')
        _upDriver = (mc.listRelatives(
            _dag_str(ml[0]), parent=True, type='transform', fullPath=True) or [None])[0]
        mc.parentConstraint(_upDriver, _dag_str(mUpGroup), mo=True)
    else:
        _upDriver = (mc.listRelatives(
            _dag_str(ml[0]), parent=True, type='transform', fullPath=True) or [None])[0]
        mc.parentConstraint(_upDriver, _dag_str(mUp), mo=True)

    log.debug(cgmGEN.logString_msg(_str_func, 'aimUpMode: {0}'.format(aimUpMode)))

    for i, mObj in enumerate(ml):
        mUpUse = mUp if not i else ml_locs[-1]

        mLoc = cgmMeta.asMeta(LOC.create(mObj.getNameLong()))
        loc = mLoc.mNode
        ml_locs.append(mLoc)

        mAim = mLoc.doGroup(False, False, asMeta=True, typeModifier='aim', setClass='cgmObject')
        ml_aims.append(mAim)

        _param = _l_paramFrac[i] if i < len(_l_paramFrac) else 0.0
        poc = CURVES.create_pointOnInfoNode(
            outCurveShape, parameter=_param, turnOnPercentage=True)
        mPoci_obj = cgmMeta.asMeta(poc)
        mPoci_obj.rename('{0}_pos'.format(loc))
        _aimVector = fwdAxis.p_vector
        if i < len(ml) - 1:
            _aimParam = _l_paramFrac[i + 1]
        elif addEndJoint or _hair_curve_extend_end_active(extendEnd):
            _aimParam = 1.0
        else:
            _aimParam = None
        if _aimParam is not None:
            pocAim = CURVES.create_pointOnInfoNode(
                outCurveShape, parameter=_aimParam, turnOnPercentage=True)
            mc.connectAttr('{0}.position'.format(pocAim), '{0}.translate'.format(mAim.mNode))
        else:
            _segLen = DIST.get_distance_between_points(ml[i - 1].p_position, ml[i].p_position)
            if _segLen < 0.0001:
                _segLen = 0.001
            mPoci_aim = cgmMeta.asMeta(CURVES.create_pointOnInfoNode(
                outCurveShape, parameter=_param, turnOnPercentage=True))
            mPoci_aim.rename('{0}_aimCrv'.format(loc))
            mMult = cgmMeta.cgmNode(
                name='{0}_aimTanScale'.format(mObj.p_nameBase), nodeType='multiplyDivide')
            mc.setAttr('{0}.input2X'.format(mMult.mNode), _segLen)
            mc.setAttr('{0}.input2Y'.format(mMult.mNode), _segLen)
            mc.setAttr('{0}.input2Z'.format(mMult.mNode), _segLen)
            mPoci_aim.doConnectOut('normalizedTangent', '{0}.input1'.format(mMult.mNode))
            mPma = cgmMeta.cgmNode(
                name='{0}_aimPos'.format(mObj.p_nameBase), nodeType='plusMinusAverage')
            mPma.operation = 1
            mPoci_obj.doConnectOut('position', '{0}.input3D[0]'.format(mPma.mNode))
            mc.connectAttr('{0}.output'.format(mMult.mNode), '{0}.input3D[1]'.format(mPma.mNode))
            mc.connectAttr('{0}.output3D'.format(mPma.mNode), '{0}.translate'.format(mAim.mNode))

        mLocParent = mLoc.doGroup(False, False, asMeta=True, typeModifier='pos', setClass='cgmObject')
        ml_prts.append(mLocParent)

        mc.connectAttr('{0}.position'.format(mPoci_obj.mNode), '{0}.translate'.format(mLocParent.mNode))

        if aimUpMode == 'master':
            mc.aimConstraint(
                mAim.mNode, mLocParent.mNode,
                aimVector=_aimVector, upVector=upAxis.p_vector,
                worldUpType='objectrotation', worldUpVector=upAxis.p_vector,
                worldUpObject=mUp.mNode)
        elif aimUpMode == 'orientToMaster':
            mc.orientConstraint(mUp.mNode, mLocParent.mNode, maintainOffset=1)
        elif aimUpMode == 'sequential':
            mc.aimConstraint(
                mAim.mNode, mLocParent.mNode,
                aimVector=_aimVector, upVector=upAxis.p_vector,
                worldUpType='objectrotation', worldUpVector=upAxis.p_vector,
                worldUpObject=mUpUse.mNode)
        elif aimUpMode == 'joint':
            mc.aimConstraint(
                mAim.mNode, mLocParent.mNode,
                aimVector=_aimVector, upVector=upAxis.p_vector,
                worldUpType='objectrotation', worldUpVector=upAxis.p_vector,
                worldUpObject=ml_sim[i].mNode)
        elif aimUpMode == 'curveNormal':
            mUpLoc = mLoc.doGroup(False, False, asMeta=True, typeModifier='up', setClass='cgmObject')
            mUpLoc.p_parent = mLocParent
            mc.aimConstraint(
                mAim.mNode, mLocParent.mNode,
                aimVector=_aimVector, upVector=upAxis.p_vector, worldUpType='object')
            mPlusMinusAverage = cgmMeta.cgmNode(
                name='{0}_pma'.format(mObj.p_nameBase), nodeType='plusMinusAverage')
            mPlusMinusAverage.operation = 3
            mPoci_obj.doConnectOut('position', '{0}.input3D[0]'.format(mPlusMinusAverage.mNode))
            mPoci_obj.doConnectOut('normalizedNormal', '{0}.input3D[1]'.format(mPlusMinusAverage.mNode))
            mUpLoc.doConnectIn('translate', '{0}.output3D'.format(mPlusMinusAverage.mNode))

        mLoc.p_parent = mLocParent
        mAim.p_parent = mGrp
        mLocParent.p_parent = mGrp

    mGrp.msgList_connect('mLocs', ml_locs)
    mGrp.msgList_connect('mAims', ml_aims)
    mGrp.msgList_connect('mParents', ml_prts)

    log.info(cgmGEN.logString_msg(_str_func, '{0} | {1} locs'.format(mGrp.p_nameBase, len(ml_locs))))
    return ml_locs, ml_aims, ml_prts


def _tear_down_hair_chain_follow_spline(mGrp):
    """Remove spline-IK driven follow rig (locators, driven joints, IK, outCurve)."""
    _str_func = '_tear_down_hair_chain_follow_spline'
    mGrp = cgmMeta.asMeta(mGrp)

    for mObj in mGrp.msgList_get('mLocs') or []:
        for _con in CONSTRAINTS.get_constraintsFrom(mObj.mNode) or []:
            try:
                mc.delete(_con)
            except Exception:
                pass

    _l_delete = []
    for _msg in ('mLocs', 'mDrivenJointChain'):
        for mObj in mGrp.msgList_get(_msg) or []:
            _l_delete.append(mObj.mNode)

    mIk = mGrp.getMessageAsMeta('mIkHandle')
    if mIk:
        for _con in CONSTRAINTS.get_constraintsFrom(mIk.mNode) or []:
            try:
                mc.delete(_con)
            except Exception:
                pass
        _l_delete.append(mIk.mNode)

    mOutCrv = mGrp.getMessageAsMeta('mOutCrv')
    if mOutCrv:
        try:
            mGrp.disconnectChildNode(mOutCrv.mNode, 'mOutCrv')
        except Exception:
            pass
        _l_delete.append(mOutCrv.mNode)

    _l_delete = list({n for n in _l_delete if n and mc.objExists(n)})
    if _l_delete:
        try:
            mc.delete(_l_delete)
        except Exception as err:
            log.warning(cgmGEN.logString_msg(_str_func, 'delete: {0}'.format(err)))

    for _msg in ('mLocs', 'mDrivenJointChain'):
        ATTR.msgList_clean(mGrp.mNode, _msg)
    _ikMsg = mGrp.getMessage('mIkHandle', asMeta=False)
    if _ikMsg:
        try:
            mGrp.disconnectChildNode(_ikMsg, 'mIkHandle')
        except Exception:
            pass

    log.info(cgmGEN.logString_msg(_str_func, mGrp.p_nameBase))


def _outcurve_spline_ik_meta(mOutCrv, mGrp=None, mFollicle=None):
    """
    NURBS curve transform meta for ik_utils.spline useCurve.

    Rest eval / outCurve.create can replace curve shapes; prefer live follicle or mOutCrv message
    when the passed node string is stale.
    """
    _str_func = '_outcurve_spline_ik_meta'

    def _meta_from_dag(node):
        if node is None:
            return None
        _node = VALID.mNodeString(node)
        if not _node or not mc.objExists(_node):
            return None
        if mc.nodeType(_node) == 'nurbsCurve':
            _parents = mc.listRelatives(_node, parent=True, fullPath=True) or []
            if not _parents:
                return None
            _node = _parents[0]
        return cgmMeta.asMeta(_node)

    mResolved = None
    if mOutCrv is not None:
        if hasattr(mOutCrv, 'mNode'):
            mResolved = _meta_from_dag(mOutCrv.mNode)
        else:
            mResolved = _meta_from_dag(mOutCrv)

    if mResolved is None and mGrp is not None:
        mLinked = cgmMeta.asMeta(mGrp).getMessageAsMeta('mOutCrv')
        if mLinked:
            mResolved = _meta_from_dag(mLinked.mNode)

    if mResolved is None and mFollicle is not None:
        mResolved = _follicle_outcurve_meta(mFollicle)

    if mResolved is None:
        raise ValueError(cgmGEN.logString_msg(
            _str_func, 'Could not resolve live outCurve transform'))

    if mc.nodeType(mResolved.mNode) == 'nurbsCurve':
        mResolved = mResolved.getTransform(asMeta=True)
    return mResolved


def _hair_spline_ik_orientation(fwdAxis, upAxis):
    """Map chain fwd/up simpleAxis to ik_utils.spline orientation + secondaryAxis."""
    _aim = fwdAxis.p_string[0]
    _up = upAxis.p_string[0]
    _rest = [c for c in ('x', 'y', 'z') if c not in (_aim, _up)]
    _out = _rest[0] if _rest else 'x'
    return '{0}{1}{2}'.format(_aim, _up, _out), upAxis.p_string


def _hair_advanced_twist_from_grp(mGrp):
    """Read advancedTwist bool from chain grp (default False)."""
    mGrp = cgmMeta.asMeta(mGrp)
    if mGrp.hasAttr('advancedTwist'):
        return bool(getattr(mGrp, 'advancedTwist', False))
    return False


def _ik_spline_handle_twist_axis_enum(ik_handle, attr_name, axis_string):
    """
    Map simpleAxis string (e.g. y+) to Maya ikHandle enum index for dForwardAxis / dWorldUpAxis.

    dWorldUpAxis includes closest* entries — never reuse the dForwardAxis integer map for it.
    """
    _ik = _dag_str(ik_handle)
    if not mc.attributeQuery(attr_name, node=_ik, exists=True):
        return None
    _enum = mc.attributeQuery(attr_name, node=_ik, listEnum=True)
    if _enum:
        _labels = _enum[0].split(':')
        _letter = axis_string[0].lower()
        _positive = '+' in axis_string
        for _idx, _lab in enumerate(_labels):
            _l = _lab.strip().lower()
            if 'closest' in _l:
                continue
            if _letter not in _l:
                continue
            if _positive and 'positive' in _l:
                return _idx
            if not _positive and 'negative' in _l:
                return _idx
    if attr_name == 'dForwardAxis':
        return SHARED._d_simple_axis_to_ikSpline_forward_axis_enum.get(axis_string)
    return SHARED._d_simple_axis_to_ikSpline_worldUp_axis_enum.get(axis_string)


def _apply_hair_spline_ik_advanced_twist(mIKHandle, fwdAxis, upAxis, mWorldUpStart, mWorldUpEnd):
    """
    Spline IK advanced twist: Object Rotation Up (Start/End), chain fwd/up axes, sim joint WU objects.
    """
    _str_func = '_apply_hair_spline_ik_advanced_twist'
    mIKHandle = cgmMeta.asMeta(mIKHandle)
    _ik = _dag_str(mIKHandle)
    _fwd_enum = _ik_spline_handle_twist_axis_enum(_ik, 'dForwardAxis', fwdAxis.p_string)
    _up_enum = _ik_spline_handle_twist_axis_enum(_ik, 'dWorldUpAxis', upAxis.p_string)
    if _fwd_enum is None or _up_enum is None:
        raise ValueError(cgmGEN.logString_msg(
            _str_func, 'Invalid fwd/up axis for ikSpline twist: {0} / {1}'.format(
                fwdAxis.p_string, upAxis.p_string)))

    if not mc.attributeQuery('dTwistControlEnable', node=_ik, exists=True):
        raise ValueError(cgmGEN.logString_msg(
            _str_func, 'ikHandle {0} has no spline advanced twist attrs — wrong solver?'.format(_ik)))

    mc.setAttr('{0}.dTwistControlEnable'.format(_ik), 1)
    mc.setAttr('{0}.dWorldUpType'.format(_ik), SHARED._ikSpline_worldUpType_objectRotationUpStartEnd)
    mc.setAttr('{0}.dForwardAxis'.format(_ik), _fwd_enum)
    if mc.attributeQuery('dWorldUpAxis', node=_ik, exists=True):
        mc.setAttr('{0}.dWorldUpAxis'.format(_ik), _up_enum)
        log.info(cgmGEN.logString_msg(
            _str_func, '{0}.{1}={2} ({3})'.format(
                _ik, 'dWorldUpAxis', _up_enum, upAxis.p_string)))
    else:
        log.warning(cgmGEN.logString_msg(_str_func, 'dWorldUpAxis missing on {0}'.format(_ik)))

    _wu = upAxis.p_vector
    mc.setAttr('{0}.dWorldUpVector'.format(_ik), _wu[0], _wu[1], _wu[2])
    mc.setAttr('{0}.dWorldUpVectorEnd'.format(_ik), _wu[0], _wu[1], _wu[2])

    _wu_start = _dag_str(mWorldUpStart)
    _wu_end = _dag_str(mWorldUpEnd)
    # AE "World Up Object" / "World Up Object 2" are matrix plugs, not message attrs (see ikHandle node docs).
    if mc.attributeQuery('dWorldUpMatrix', node=_ik, exists=True):
        mc.connectAttr('{0}.worldMatrix[0]'.format(_wu_start), '{0}.dWorldUpMatrix'.format(_ik), force=True)
        log.info(cgmGEN.logString_msg(
            _str_func, 'dWorldUpMatrix <- {0}.worldMatrix[0]'.format(_wu_start)))
        if mc.attributeQuery('dWorldUpMatrixEnd', node=_ik, exists=True):
            mc.connectAttr('{0}.worldMatrix[0]'.format(_wu_end), '{0}.dWorldUpMatrixEnd'.format(_ik), force=True)
            log.info(cgmGEN.logString_msg(
                _str_func, 'dWorldUpMatrixEnd <- {0}.worldMatrix[0]'.format(_wu_end)))
        else:
            log.warning(cgmGEN.logString_msg(_str_func, 'dWorldUpMatrixEnd missing on {0}'.format(_ik)))
    else:
        log.warning(cgmGEN.logString_msg(
            _str_func, 'dWorldUpMatrix missing on ikHandle {0}'.format(_ik)))

    log.info(cgmGEN.logString_msg(
        _str_func, '{0} | fwd={1} up={2} WU start={3} end={4}'.format(
            _ik, fwdAxis.p_string, upAxis.p_string,
            cgmMeta.asMeta(mWorldUpStart).p_nameShort,
            cgmMeta.asMeta(mWorldUpEnd).p_nameShort)))


def _prepare_spline_hair_outcurve(mFollicle, mFollicleShape, mHairSysShape, name, outCurveDegree):
    """
    Spline hair outCurve: follicle degree, regenerate via outCurve.create, rest eval (no CV match).

    Returns:
        (mOutCrv, outCurveShape): cgmMeta transform + nurbsCurve shape name
    """
    _configure_follicle_outcurve_degree(mFollicleShape, outCurveDegree)
    follicle_regenerate_out_curve(mFollicle, base_name='{0}_outCrv'.format(name))
    _hairShape = mHairSysShape.mNode if hasattr(mHairSysShape, 'mNode') else mHairSysShape
    _follicleShape = mFollicleShape.mNode if hasattr(mFollicleShape, 'mNode') else mFollicleShape
    _refresh_hair_rest_output(_follicleShape, _hairShape)
    mOutCrv = _follicle_outcurve_meta(mFollicle)
    if not mOutCrv:
        raise ValueError(cgmGEN.logString_msg(
            '_prepare_spline_hair_outcurve',
            'No outCurve on follicle after regenerate: {0}'.format(name)))
    _shapes = mOutCrv.getShapes(asMeta=False) or []
    if not _shapes:
        raise ValueError(cgmGEN.logString_msg(
            '_prepare_spline_hair_outcurve',
            'Out curve has no nurbsCurve shape: {0}'.format(mOutCrv.mNode)))
    return mOutCrv, _shapes[0]


def _ordered_joint_chain_from_root(mRoot):
    """Return root-to-tip joint metas for a single-child joint chain."""
    mRoot = cgmMeta.asMeta(mRoot)
    ml = [mRoot]
    mCurrent = mRoot
    while True:
        _kids = [
            c for c in (mCurrent.getChildren(asMeta=True) or [])
            if mc.nodeType(c.mNode) == 'joint']
        if not _kids:
            break
        mCurrent = _kids[0]
        ml.append(mCurrent)
    return ml


def _hair_reparent_sim_chain_ordered(ml_sim):
    """Force sim joints into one root→tip chain (order from normalize). Restores duplicate-root driven IK."""
    ml = _hair_normalize_sim_chain(ml_sim)
    for i in range(1, len(ml)):
        ml[i].p_parent = ml[i - 1]
    return ml


def _build_hair_driven_joint_chain(ml_sim, ml, name, mParent):
    """Duplicate sim joint hierarchy from root (renameChildren) for spline IK."""
    ml_sim = _hair_reparent_sim_chain_ordered(ml_sim)
    if not ml_sim:
        return []

    mRoot = ml_sim[0]
    _dupRoot = mc.duplicate(
        mRoot.mNode,
        renameChildren=False,
        inputConnections=False,
        upstreamNodes=False)[0]
    ml_driven = _ordered_joint_chain_from_root(_dupRoot)

    if len(ml_driven) != len(ml_sim):
        log.warning(cgmGEN.logString_msg(
            '_build_hair_driven_joint_chain',
            'Driven hierarchy {0} != sim {1} — check sim joint parenting'.format(
                len(ml_driven), len(ml_sim))))

    _count = min(len(ml_driven), len(ml_sim))
    for i in range(_count):
        ml_driven[i].rename('{0}_driven_{1:02d}_jnt'.format(name, i))

    mParent = cgmMeta.asMeta(mParent, noneValid=True)
    if mParent and ml_driven:
        ml_driven[0].p_parent = mParent
    return ml_driven[:_count] if _count else ml_driven


def _build_hair_chain_follow_spline(mGrp, mOutCrv, ml, ml_sim, name, fwdAxis=None, upAxis=None,
                                    mFollicle=None, ml_baseTargets=None, advancedTwist=None):
    """
    Duplicate sim joint chain, spline IK on outCurve, locators parented under driven joints.

    Args:
        mOutCrv: cgmMeta out curve transform (stays valid across reparent/rename)

    Returns (ml_locs, ml_driven, mIKHandle).
    """
    import cgm.core.rig.ik_utils as IKUTIL

    _str_func = '_build_hair_chain_follow_spline'
    mGrp = cgmMeta.asMeta(mGrp)
    mOutCrv = _outcurve_spline_ik_meta(mOutCrv, mGrp=mGrp, mFollicle=mFollicle)
    ml_sim = _hair_normalize_sim_chain(ml_sim)

    mFollicle = cgmMeta.asMeta(mFollicle, noneValid=True) if mFollicle else mGrp.getMessageAsMeta('mFollicle')
    _drivenParent = mFollicle if mFollicle else mGrp
    ml_driven = _build_hair_driven_joint_chain(ml_sim, ml, name, _drivenParent)

    if fwdAxis is None or upAxis is None:
        if mGrp.hasAttr('fwd') and mGrp.hasAttr('up'):
            fwdAxis = simpleAxis(mGrp.fwd)
            upAxis = simpleAxis(mGrp.up)
        else:
            fwdAxis = TRANS.closestAxisTowardObj_get(ml[0], ml[1])
            upAxis = TRANS.crossAxis_get(fwdAxis)
    _orientation, _secondaryAxis = _hair_spline_ik_orientation(fwdAxis, upAxis)

    _ikRes = IKUTIL.spline(
        ml_driven,
        useCurve=mOutCrv,
        baseName=name,
        parentGutsTo=mGrp,
        orientation=_orientation,
        secondaryAxis=_secondaryAxis,
        stretchBy=None)

    mIKHandle = _ikRes['mIKHandle']
    if advancedTwist is None:
        advancedTwist = _hair_advanced_twist_from_grp(mGrp)
    if advancedTwist:
        _n_base = len(ml_baseTargets) if ml_baseTargets else len(ml)
        _end_idx = max(0, min(_n_base - 1, len(ml_sim) - 1))
        _apply_hair_spline_ik_advanced_twist(
            mIKHandle, fwdAxis, upAxis, ml_sim[0], ml_sim[_end_idx])

    ml_locs = []
    for i, mTarget in enumerate(ml):
        mLoc = cgmMeta.asMeta(LOC.create(mTarget.getNameLong()))
        if i < len(ml_driven):
            mLoc.p_parent = ml_driven[i]
        ml_locs.append(mLoc)

    mGrp.msgList_connect('mLocs', ml_locs)
    mGrp.msgList_connect('mDrivenJointChain', ml_driven)
    mGrp.connectChildNode(mIKHandle.mNode, 'mIkHandle', 'chain')

    log.info(cgmGEN.logString_msg(
        _str_func, '{0} | {1} locs | spline IK'.format(mGrp.p_nameBase, len(ml_locs))))
    return ml_locs, ml_driven, mIKHandle


def _resolve_hair_curve_degrees(mGrp, mDynFK=None):
    """Read in/out curve degree from chain grp with setup defaults."""
    mGrp = cgmMeta.asMeta(mGrp)
    _in = 1
    _out = 2
    if mDynFK is not None:
        _in = getattr(mDynFK, 'inCurveDegree', _in)
        _out = getattr(mDynFK, 'outCurveDegree', _out)
    if mGrp.hasAttr('inCurveDegree'):
        try:
            _in = int(mGrp.inCurveDegree)
        except (TypeError, ValueError):
            pass
    if mGrp.hasAttr('outCurveDegree'):
        try:
            _out = int(mGrp.outCurveDegree)
        except (TypeError, ValueError):
            pass
    return MATHUTILS.Clamp(_in, 1, 3), MATHUTILS.Clamp(_out, 1, 3)


def _hair_sim_joint_chain_ordered(chain):
    """Root-to-tip sim joint metas (hierarchy walk from chain root)."""
    return _hair_normalize_sim_chain(chain)


def _hair_order_sim_joint_chain(ml_sim):
    """
    Root-to-tip order for joints in ml_sim only.

    Ignores stray joint children (e.g. leftover spline driven duplicates parented under sim).
    """
    ml = cgmMeta.asMeta(ml_sim, noneValid=True) or []
    ml = [
        m for m in ml
        if m and mc.objExists(m.mNode) and mc.nodeType(m.mNode) == 'joint']
    if len(ml) <= 1:
        return ml
    _by_node = {m.mNode: m for m in ml}
    m_roots = []
    for m in ml:
        _par = m.getParent(asMeta=False)
        if not _par or _par not in _by_node:
            m_roots.append(m)
    if len(m_roots) != 1:
        return ml
    ordered = []
    m_cur = m_roots[0]
    while m_cur and m_cur.mNode in _by_node:
        ordered.append(m_cur)
        _kids = [
            c for c in (m_cur.getChildren(asMeta=True) or [])
            if mc.nodeType(c.mNode) == 'joint' and c.mNode in _by_node]
        if len(_kids) != 1:
            break
        m_cur = _kids[0]
    return ordered if len(ordered) == len(ml) else ml


def _hair_rename_sim_joint_chain(ml_sim, name):
    """Enforce {name}_sim_##_jnt on ordered sim joints (rebuild / fix duplicate names)."""
    ml = _hair_order_sim_joint_chain(ml_sim)
    for i, mJ in enumerate(ml):
        _chain_rename_meta_short(mJ, '{0}_sim_{1:02d}_jnt'.format(name, i))
    return ml


def _hair_delete_stray_joints_under_sim(ml_sim):
    """Remove joint children of sim chain that are not in the sim joint list (orphan driven dupes)."""
    ml = _hair_order_sim_joint_chain(ml_sim)
    if not ml:
        return
    _keep = {m.mNode for m in ml}
    _delete = []
    for m in ml:
        for mChild in (m.getChildren(asMeta=True) or []):
            if mc.nodeType(mChild.mNode) != 'joint':
                continue
            if mChild.mNode in _keep:
                continue
            _delete.append(mChild.mNode)
    if _delete:
        try:
            mc.delete(_delete)
        except Exception as err:
            log.warning(cgmGEN.logString_msg(
                '_hair_delete_stray_joints_under_sim', 'delete: {0}'.format(err)))


def _hair_normalize_sim_chain(chain):
    """Ordered sim joint metas; accepts meta list, node list, or root-only chain."""
    ml = cgmMeta.asMeta(chain, noneValid=True) or []
    ml = [m for m in ml if m]
    if not ml:
        return []
    if mc.nodeType(ml[0].mNode) != 'joint':
        return ml
    _ordered = _hair_order_sim_joint_chain(ml)
    if len(_ordered) == len(ml):
        return _ordered
    ml_walk = _ordered_joint_chain_from_root(_ordered[0] if _ordered else ml[0])
    _ml_set = {m.mNode for m in ml}
    _filtered = [m for m in ml_walk if m.mNode in _ml_set]
    if len(_filtered) == len(ml):
        return _filtered
    return _ordered if _ordered else ml


def _hair_build_sim_joint_chain_from_targets(ml_baseTargets, name):
    """Create parented sim joints from target metas (matchTarget snap, indexed names)."""
    ml_targets = cgmMeta.asMeta(ml_baseTargets, noneValid=True) or []
    if not ml_targets:
        return []
    ml_chain = []
    for i, mTarget in enumerate(ml_targets):
        mc.select(cl=True)
        mJnt = mTarget.doCreateAt('joint')
        mJnt.rename('{0}_sim_{1:02d}_jnt'.format(name, i))
        if ml_chain:
            mJnt.p_parent = ml_chain[-1]
        SNAP.matchTarget_set(mJnt.mNode, mTarget.mNode)
        mMatch = mJnt.getMessageAsMeta('cgmMatchTarget')
        if mMatch:
            mJnt.doSnapTo(mMatch)
        ml_chain.append(mJnt)
    return ml_chain


def _resolve_hair_chain_l_pos(mGrp, ml_sim, ml_baseTargets):
    """Joint positions for inCurve rebuild (ordered sim chain ws positions)."""
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    if ml_sim:
        return [mJ.p_position for mJ in ml_sim]
    return [mObj.p_position for mObj in ml_baseTargets]


def _hair_add_end_joint_active(addEndJoint):
    """True when add-end-joint is enabled (False/None/0/off, or numeric distance)."""
    if addEndJoint in (None, False, 0):
        return False
    try:
        if float(addEndJoint) == 0.0:
            return False
    except (TypeError, ValueError):
        pass
    return True


def _hair_curve_extend_end_active(extendEnd):
    """True when curve extendEnd overshoot is enabled (same truthiness as addEndJoint distance)."""
    return _hair_add_end_joint_active(extendEnd)


def _hair_add_end_joint_from_grp(mGrp):
    """Read addEndJoint from chain grp (falls back to legacy extendEnd attr)."""
    mGrp = cgmMeta.asMeta(mGrp)
    if mGrp.hasAttr('addEndJoint'):
        return getattr(mGrp, 'addEndJoint', False)
    if mGrp.hasAttr('extendEnd'):
        return getattr(mGrp, 'extendEnd', False)
    return False


def _hair_curve_extend_end_from_grp(mGrp):
    """Read curve extendEnd from chain grp (pre-split chains: extendEnd attr is joint-only)."""
    mGrp = cgmMeta.asMeta(mGrp)
    if not mGrp.hasAttr('addEndJoint'):
        return False
    if mGrp.hasAttr('extendEnd'):
        return getattr(mGrp, 'extendEnd', False)
    return False


def _hair_resolve_create_extend_kws(addEndJoint=None, extendEnd=None):
    """
    chain_create / chain_create_hair entry: legacy callers used extendEnd for addEndJoint.
    Returns (addEndJoint, curve_extendEnd).
    """
    if addEndJoint is None and extendEnd is not None:
        return extendEnd, False
    return addEndJoint, extendEnd


def _hair_coerce_add_end_joint_kw(addEndJoint=None, extendEnd=None):
    """Deprecated — use _hair_resolve_create_extend_kws at API entry only."""
    if addEndJoint is not None:
        return addEndJoint
    return extendEnd


def _hair_resolve_add_end_distance_from_positions(pLast, pPrev, addEndJoint, upSetup, fwdAxis):
    if isinstance(addEndJoint, bool):
        if upSetup == 'manual' and fwdAxis is not None:
            return MATHUTILS.Clamp(DIST.get_distance_between_points(pLast, pPrev), 0.5, None)
        return DIST.get_distance_between_points(pPrev, pLast) / 2.0
    try:
        return float(addEndJoint)
    except (TypeError, ValueError):
        _num = VALID.valueArg(addEndJoint, noneValid=True)
        if _num in (None, False):
            return None
        return float(_num)


def _hair_resolve_add_end_distance(mBaseLast, mBasePrev, addEndJoint, upSetup, fwdAxis):
    """Numeric tip offset for add-end joint (bool = guess from last base segment)."""
    return _hair_resolve_add_end_distance_from_positions(
        mBaseLast.p_position, mBasePrev.p_position, addEndJoint, upSetup, fwdAxis)


def _hair_add_end_joint_tip_position(mBaseLast, mBasePrev, addEndJoint, upSetup, fwdAxis):
    """Add-end ws from last base joint + distance (doDuplicate / p_position); not used for curve aim."""
    if not _hair_add_end_joint_active(addEndJoint) or mBaseLast is None:
        return None
    _dist = _hair_resolve_add_end_distance(mBaseLast, mBasePrev, addEndJoint, upSetup, fwdAxis)
    if _dist is None:
        return None
    _axis = fwdAxis.p_string if fwdAxis is not None else 'z+'
    return mBaseLast.getPositionByAxisDistance(_axis, _dist)


# Legacy l_pos helper (dat / callers); sim joints use _hair_sync_add_end_sim_joint.
def _hair_add_end_joint_tip_to_l_pos(l_pos, addEndJoint, upSetup='guess', fwdAxis=None):
    if not _hair_add_end_joint_active(addEndJoint):
        return list(l_pos)
    l_pos = list(l_pos)
    if len(l_pos) < 2:
        return l_pos
    _dist = _hair_resolve_add_end_distance_from_positions(
        l_pos[-1], l_pos[-2], addEndJoint, upSetup, fwdAxis)
    if _dist is None:
        return l_pos
    if upSetup == 'manual' and fwdAxis is not None:
        l_pos.append(DIST.get_pos_by_vec_dist(l_pos[-1], fwdAxis.p_vector, _dist))
    else:
        _vecEnd = MATHUTILS.get_vector_of_two_points(l_pos[-2], l_pos[-1])
        l_pos.append(DIST.get_pos_by_vec_dist(l_pos[-1], _vecEnd, _dist))
    return l_pos


_hair_apply_extend_end_to_l_pos = _hair_add_end_joint_tip_to_l_pos


def _hair_append_distance_along_segment(l_pos, pLast, pPrev, distance_kw, upSetup='guess', fwdAxis=None):
    """Append one ws point past pLast along (pPrev -> pLast) or manual fwd."""
    l_pos = list(l_pos)
    _dist = _hair_resolve_add_end_distance_from_positions(
        pLast, pPrev, distance_kw, upSetup, fwdAxis)
    if _dist is None:
        return l_pos
    if upSetup == 'manual' and fwdAxis is not None:
        l_pos.append(DIST.get_pos_by_vec_dist(pLast, fwdAxis.p_vector, _dist))
    else:
        _vecEnd = MATHUTILS.get_vector_of_two_points(pPrev, pLast)
        l_pos.append(DIST.get_pos_by_vec_dist(pLast, _vecEnd, _dist))
    return l_pos


def _hair_incurve_l_pos_for_chain(mGrp, ml_sim, ml_baseTargets, extendStart=None, extendEnd=None,
                                  upSetup='guess', fwdAxis=None, addEndJoint=None):
    """Sim joint ws positions for inCurve; optional curve extendEnd CV past chain end."""
    l_pos = _resolve_hair_chain_l_pos(mGrp, ml_sim, ml_baseTargets)
    if not _hair_curve_extend_end_active(extendEnd):
        return l_pos
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    ml_baseTargets = ml_baseTargets or []
    if _hair_add_end_joint_active(addEndJoint) and len(ml_sim) >= 2:
        pLast = ml_sim[-1].p_position
        pPrev = ml_sim[-2].p_position
    elif len(ml_baseTargets) >= 2:
        pLast = ml_baseTargets[-1].p_position
        pPrev = ml_baseTargets[-2].p_position
    elif len(l_pos) >= 2:
        pLast = l_pos[-1]
        pPrev = l_pos[-2]
    else:
        return l_pos
    return _hair_append_distance_along_segment(
        l_pos, pLast, pPrev, extendEnd, upSetup=upSetup, fwdAxis=fwdAxis)


def _delete_hair_incurve_skincluster(mInCrv):
    """Remove skinCluster on inCurve so sim joint moves do not deform dynamic hair mid-rebuild."""
    mInCrv = cgmMeta.asMeta(mInCrv, noneValid=True)
    if not mInCrv:
        return
    _inCrv = VALID.mNodeString(mInCrv)
    _hist = []
    for _dag in ([_inCrv] + (mc.listRelatives(_inCrv, shapes=True, fullPath=True) or [])):
        _hist.extend(mc.listHistory(_dag, pdo=True) or [])
    for _sc in mc.ls(_hist, type='skinCluster') or []:
        try:
            mc.delete(_sc)
        except Exception:
            pass


def _hair_incurve_skin_bind(ml_sim, mInCrv, skinClusterName, l_pos=None):
    """Skin inCurve CVs to ordered sim joints (1 CV : 1 joint when no extendStart lead)."""
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    mInCrv = cgmMeta.asMeta(mInCrv)
    _l_joints = [mJ.mNode for mJ in ml_sim]
    if not _l_joints:
        raise ValueError('No sim joints for inCurve skinCluster')
    if l_pos is None:
        l_pos = [mJ.p_position for mJ in ml_sim]
    _inCrv = VALID.mNodeString(mInCrv)
    mSkinCluster = mc.skinCluster(
        _l_joints, _inCrv,
        name=skinClusterName,
        tsb=True,
        maximumInfluences=1,
        obeyMaxInfluences=True)[0]
    _inShape = mInCrv.getShapes(asMeta=False) or []
    _shape = _inShape[0] if _inShape else mc.listRelatives(
        mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
    _l_cvs = mc.ls('{0}.cv[*]'.format(_shape), flatten=True) or []
    if len(_l_cvs) == len(_l_joints):
        for i, _cv in enumerate(_l_cvs):
            mc.skinPercent(mSkinCluster, _cv, tv=[_l_joints[i], 1.0])
    else:
        for i, _cv in enumerate(_l_cvs):
            _jnt = _l_joints[i] if i < len(_l_joints) else _l_joints[-1]
            mc.skinPercent(mSkinCluster, _cv, tv=[_jnt, 1.0])
        log.warning(cgmGEN.logString_msg(
            '_hair_incurve_skin_bind',
            'CV count {0} != joint count {1} — tip CVs bound to last joint'.format(
                len(_l_cvs), len(_l_joints))))
    return mSkinCluster, ml_sim


def _hair_trim_add_end_joints(chain, num_base_joints, addEndJoint=None):
    """Remove tip add-end sim joints; keep base targets + one addEnd joint when enabled."""
    _max = num_base_joints + (1 if _hair_add_end_joint_active(addEndJoint) else 0)
    ml = _hair_normalize_sim_chain(chain)
    while len(ml) > _max:
        mTip = ml.pop()
        try:
            mTip.delete()
        except Exception:
            pass
    return ml


_hair_trim_extend_end_joints = _hair_trim_add_end_joints


def _hair_sync_add_end_sim_joint(ml_sim, ml_baseTargets, addEndJoint, upSetup, fwdAxis, name):
    """
    Add-end sim joint: duplicate last base joint (po, no inputs), parent under it,
    tip at last-base.getPositionByAxisDistance(fwd, distance). Rebuild moves tip the same way.
    """
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    _num_base = len(ml_baseTargets or [])
    ml_joints = _hair_trim_add_end_joints(ml_sim, _num_base, addEndJoint=addEndJoint)
    if not _hair_add_end_joint_active(addEndJoint) or _num_base < 2:
        return ml_joints if ml_joints else ml_sim
    if len(ml_joints) < _num_base:
        return ml_joints
    mBaseLast = ml_joints[_num_base - 1]
    mBasePrev = ml_joints[_num_base - 2]
    _tip_pos = _hair_add_end_joint_tip_position(mBaseLast, mBasePrev, addEndJoint, upSetup, fwdAxis)
    if _tip_pos is None:
        return ml_joints
    if len(ml_joints) >= _num_base + 1:
        mAddEnd = ml_joints[-1]
        mAddEnd.p_position = _tip_pos
        return _hair_normalize_sim_chain(ml_joints)
    mAddEnd = mBaseLast.doDuplicate(po=True, ic=False)
    mAddEnd.rename('{0}_sim_{1:02d}_jnt'.format(name, _num_base))
    mAddEnd.p_parent = mBaseLast
    mAddEnd.p_position = _tip_pos
    ml_joints.append(mAddEnd)
    return _hair_normalize_sim_chain(ml_joints)


def _hair_append_add_end_joint_at_tip_pos(ml_sim, tip_pos, name, num_base=None):
    """Legacy: one tip sim joint at ws position (prefer duplicate + p_position)."""
    ml = _hair_normalize_sim_chain(ml_sim)
    if tip_pos is None or not ml:
        return ml
    mBaseLast = ml[-1]
    mAddEnd = mBaseLast.doDuplicate(po=True, ic=False)
    _idx = num_base if num_base is not None else len(ml)
    mAddEnd.rename('{0}_sim_{1:02d}_jnt'.format(name, _idx))
    mAddEnd.p_parent = mBaseLast
    mAddEnd.p_position = tip_pos
    ml.append(mAddEnd)
    return _hair_normalize_sim_chain(ml)


def _hair_append_add_end_joint(ml_sim, *args, **kws):
    """
    Compat entry for add-end sim joint.

    Legacy (3 args): (ml_sim, tip_pos, name) — ws tip from inCurve CV.
    Current (6+ args): forwards to _hair_sync_add_end_sim_joint.
    Stale callers (3 args): (ml_sim, ml_baseTargets, addEndJoint) — resolve aim/name.
    """
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    if len(args) == 2:
        if isinstance(args[1], str):
            _tip = args[0]
            if isinstance(_tip, (list, tuple)) and len(_tip) >= 3:
                try:
                    float(_tip[0])
                    return _hair_append_add_end_joint_at_tip_pos(ml_sim, _tip, args[1])
                except (TypeError, ValueError):
                    pass
        else:
            ml_baseTargets, addEndJoint = args[0], args[1]
            _name = 'hair'
            if ml_baseTargets:
                try:
                    _name = ml_baseTargets[-1].p_nameBase
                except Exception:
                    pass
            _fwd = None
            if len(ml_baseTargets or []) >= 2:
                _fwd = TRANS.closestAxisTowardObj_get(ml_baseTargets[0], ml_baseTargets[1])
            return _hair_sync_add_end_sim_joint(
                ml_sim, ml_baseTargets, addEndJoint, 'guess', _fwd, _name)
    if len(args) >= 5:
        return _hair_sync_add_end_sim_joint(
            ml_sim, args[0], args[1], args[2], args[3], args[4])
    raise TypeError(
        '_hair_append_add_end_joint expected (ml_sim, tip_pos, name), '
        '(ml_sim, ml_baseTargets, addEndJoint), or 5 sync args; got {0}'.format(len(args)))


_hair_append_extend_end_joint = _hair_append_add_end_joint


def _hair_rebuild_sim_chain_for_incurve(mGrp, ml_sim, ml_baseTargets, tip_pos, name, addEndJoint=None,
                                        upSetup='guess', fwdAxis=None):
    """Trim / sync add-end sim joint; tip_pos ignored (distance from chain + addEndJoint)."""
    return _hair_sync_add_end_sim_joint(
        ml_sim, ml_baseTargets, addEndJoint, upSetup, fwdAxis, name)


def _hair_ensure_add_end_joint_chain(mGrp, ml_sim, ml_baseTargets, l_pos, addEndJoint, upSetup, fwdAxis, name,
                                     extendEnd=None, extendStart=None):
    """
    When addEndJoint is on: one sim joint past last target at add-end distance.
    Returns (inCurve l_pos from sim joints + optional curve extendEnd, ml_sim).
    """
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    if not _hair_add_end_joint_active(addEndJoint):
        return _hair_incurve_l_pos_for_chain(
            mGrp, ml_sim, ml_baseTargets, extendStart=extendStart, extendEnd=extendEnd,
            upSetup=upSetup, fwdAxis=fwdAxis, addEndJoint=addEndJoint), ml_sim
    _num_base = len(ml_baseTargets or [])
    if _num_base < 2 or len(ml_sim) < 2:
        _hair_validate_add_end_joint_count(
            ml_sim, ml_baseTargets, addEndJoint, l_pos=l_pos,
            context='addEndJoint on but fewer than 2 base positions')
        return _hair_incurve_l_pos_for_chain(
            mGrp, ml_sim, ml_baseTargets, extendStart=extendStart, extendEnd=extendEnd,
            upSetup=upSetup, fwdAxis=fwdAxis, addEndJoint=addEndJoint), ml_sim
    ml_sim = _hair_sync_add_end_sim_joint(
        ml_sim, ml_baseTargets, addEndJoint, upSetup, fwdAxis, name)
    _hair_validate_add_end_joint_count(
        ml_sim, ml_baseTargets, addEndJoint, context='ensure addEndJoint sim chain',
        required=False)
    l_pos = _hair_incurve_l_pos_for_chain(
        mGrp, ml_sim, ml_baseTargets, extendStart=extendStart, extendEnd=extendEnd,
        upSetup=upSetup, fwdAxis=fwdAxis, addEndJoint=addEndJoint)
    return l_pos, ml_sim


_hair_ensure_extend_end_sim_chain = _hair_ensure_add_end_joint_chain


def _hair_validate_add_end_joint_count(ml_sim, ml_baseTargets, addEndJoint, l_pos=None, context='',
                                     required=False):
    """Raise if addEndJoint is on (or required) but sim joint count is not base targets + 1."""
    if not (_hair_add_end_joint_active(addEndJoint) or required):
        return
    _num_base = len(ml_baseTargets or [])
    if _num_base < 1:
        return
    _expected = _num_base + 1
    ml_sim = _hair_normalize_sim_chain(ml_sim)
    _n_joints = len(ml_sim)
    if _n_joints != _expected:
        _n_pos = len(l_pos) if l_pos is not None else None
        raise ValueError(cgmGEN.logString_msg(
            '_hair_validate_add_end_joint_count',
            '{0} | addEndJoint {1}, {2} base target(s): expected {3} sim joint(s), '
            'got {4}{5}{6}'.format(
                context or 'hair chain',
                'required' if required and not _hair_add_end_joint_active(addEndJoint) else 'on',
                _num_base,
                _expected,
                _n_joints,
                ' | inCurve l_pos={0}'.format(_n_pos) if _n_pos is not None else '',
                ' | {0}'.format([m.p_nameShort for m in ml_sim]) if ml_sim else '')))


_hair_validate_extend_end_joint_count = _hair_validate_add_end_joint_count


def _resolve_ncloth_shape(node):
    """Return nClothShape from an nCloth shape or transform that owns one."""
    node = VALID.mNodeString(node)
    if mc.objectType(node) == 'nCloth':
        return node
    shapes = mc.listRelatives(node, shapes=True, type='nCloth', fullPath=True) or []
    return shapes[0] if shapes else None


def _wire_time1_current_time(node):
    """Connect timeline to sim node currentTime (Maya default for nucleus / nCloth)."""
    _node = VALID.mNodeString(node)
    if not mc.attributeQuery('currentTime', node=_node, exists=True):
        return False
    _dest = '{0}.currentTime'.format(_node)
    if mc.isConnected('time1.outTime', _dest):
        return True
    if mc.objExists('time1'):
        mc.connectAttr('time1.outTime', _dest, f=True)
        return True
    return False


def _scene_node_long(node):
    """Canonical long DAG name for nucleus / hairSystem identity checks."""
    if not node or not mc.objExists(node):
        return None
    _res = mc.ls(node, long=True) or []
    return _res[0] if _res else VALID.mNodeString(node)


def _nucleus_for_dyn_sim(sim_shape):
    """Nucleus node this sim shape feeds via ``currentState`` → ``inputActive``."""
    _sim = VALID.mNodeString(sim_shape)
    _con = mc.listConnections(
        '{0}.currentState'.format(_sim), type='nucleus', destination=True) or []
    if _con:
        return _con[0]
    for _plug in mc.listConnections(
            '{0}.currentState'.format(_sim), destination=True, plugs=True) or []:
        _node = _plug.split('.')[0]
        if mc.objExists(_node) and mc.objectType(_node) == 'nucleus':
            return _node
    return None


def _nucleus_dyn_sim_slot_index(nucleus, sim_shape):
    """``outputObjects`` index wiring ``sim_shape.nextState``, or None."""
    import re
    _sim = VALID.mNodeString(sim_shape)
    _nuc = _scene_node_long(nucleus)
    if not _nuc:
        return None
    _src = mc.listConnections('{0}.nextState'.format(_sim), source=True, plugs=True) or []
    if not _src:
        return None
    _plug = _src[0]
    if _scene_node_long(_plug.split('.')[0]) != _nuc or 'outputObjects[' not in _plug:
        return None
    _m = re.search(r'outputObjects\[(\d+)\]', _plug)
    return int(_m.group(1)) if _m else None


def _dedupe_nucleus_sim_plugs(sim_shape, nucleus, keep_idx):
    """Drop duplicate ``currentState`` / ``startState`` links to nucleus except ``keep_idx``."""
    _sim = VALID.mNodeString(sim_shape)
    _nuc = _scene_node_long(nucleus)
    if _nuc is None or keep_idx is None:
        return 0
    _removed = 0
    for _sim_attr, _nuc_attr in (('currentState', 'inputActive'), ('startState', 'inputActiveStart')):
        _sim_plug = '{0}.{1}'.format(_sim, _sim_attr)
        _keep = '{0}.{1}[{2}]'.format(_nuc, _nuc_attr, keep_idx)
        for _dst in mc.listConnections(_sim_plug, destination=True, plugs=True) or []:
            if not _dst.startswith(_nuc) or '.{0}['.format(_nuc_attr) not in _dst:
                continue
            if _dst == _keep:
                continue
            try:
                mc.disconnectAttr(_sim_plug, _dst)
                _removed += 1
            except Exception:
                pass
    return _removed


def _disconnect_dyn_sim_from_nucleus(sim_shape):
    _sim = VALID.mNodeString(sim_shape)
    for _plug in ('currentState', 'startState'):
        _sim_plug = '{0}.{1}'.format(_sim, _plug)
        for _dst in mc.listConnections(_sim_plug, destination=True, plugs=True) or []:
            try:
                mc.disconnectAttr(_sim_plug, _dst)
            except Exception:
                pass
        for _src in mc.listConnections(_sim_plug, source=True, plugs=True) or []:
            try:
                mc.disconnectAttr(_src, _sim_plug)
            except Exception:
                pass
    for _src in mc.listConnections('{0}.nextState'.format(_sim), source=True, plugs=True) or []:
        try:
            mc.disconnectAttr(_src, '{0}.nextState'.format(_sim))
        except Exception:
            pass


def _connect_dyn_sim_to_nucleus(sim_shape, nucleus):
    """
    Wire hairSystem / nClothShape to nucleus outputObjects (same pattern as makeCurvesDynamic).
    """
    _str_func = '_connect_dyn_sim_to_nucleus'
    _nuc = _scene_node_long(nucleus)
    _sim = VALID.mNodeString(sim_shape)

    _existing = _nucleus_for_dyn_sim(_sim)
    _existing_long = _scene_node_long(_existing)
    if _existing_long and _existing_long == _nuc:
        _idx = _nucleus_dyn_sim_slot_index(_nuc, _sim)
        if _idx is not None:
            _dedupe_nucleus_sim_plugs(_sim, _nuc, _idx)
        _wire_time1_current_time(_nuc)
        _wire_time1_current_time(_sim)
        return True

    if _existing_long and _existing_long != _nuc:
        log.info("|{0}| >> Moving {1} from nucleus {2} to {3}".format(
            _str_func, _sim, _existing_long, _nuc))
        _disconnect_dyn_sim_from_nucleus(_sim)

    _idx = ATTR.get_nextCompoundIndex(_nuc, 'outputObjects')
    mc.connectAttr('{0}.outputObjects[{1}]'.format(_nuc, _idx), '{0}.nextState'.format(_sim), f=True)
    mc.connectAttr('{0}.currentState'.format(_sim), '{0}.inputActive[{1}]'.format(_nuc, _idx), f=True)
    mc.connectAttr('{0}.startState'.format(_sim), '{0}.inputActiveStart[{1}]'.format(_nuc, _idx), f=True)

    _wire_time1_current_time(_nuc)
    _wire_time1_current_time(_sim)

    if mc.attributeQuery('startFrame', node=_sim, exists=True):
        _nucStart = '{0}.startFrame'.format(_nuc)
        _simStart = '{0}.startFrame'.format(_sim)
        if not mc.isConnected(_nucStart, _simStart):
            try:
                mc.connectAttr(_nucStart, _simStart, f=True)
            except Exception:
                pass

    log.info("|{0}| >> Wired {1} to nucleus {2} [outputObjects[{3}]]".format(
        _str_func, _sim, _nuc, _idx))
    return True


def get_mapped_cloth(mOwner):
    """
    Read setup ``mCloth`` message.

    Returns the linked nCloth transform meta, or False if unset.
    """
    import cgm.core.lib.nCloth_utils as NCLOTH

    mNode = mOwner.mNode if hasattr(mOwner, 'mNode') else str(mOwner)
    if not mc.objExists(mNode):
        return False
    if not mc.attributeQuery('mCloth', node=mNode, exists=True):
        return False

    # Transform .message links are dropped by ATTR.get_message (shapes=True).
    sources = mc.listConnections('{0}.mCloth'.format(mNode), source=True, destination=False) or []
    if not sources:
        return False

    nc = NCLOTH.get_nCloth(sources[0], noneValid=True)
    if not nc:
        return False

    parents = mc.listRelatives(nc, parent=True, fullPath=True) or []
    dag = parents[0] if parents else sources[0]
    return cgmMeta.validateObjArg(dag, noneValid=True)


def map_cloth_surface(mOwner, node=None):
    """
    Link an nCloth shape to setup ``mCloth`` (required for Attach to Cloth).

    Module-level entry — use from UI so cached meta instances pick up new code
    without relying on instance method resolution on reloaded classes.
    """
    _str_func = 'map_cloth_surface'
    import cgm.core.lib.nCloth_utils as NCLOTH

    if node is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            return log.error("|{0}| >> Nothing selected".format(_str_func))
        node = _sel[0]

    nc = _resolve_ncloth_shape(node)
    if not nc:
        return log.error("|{0}| >> Selection is not an nCloth node".format(_str_func))

    if not NCLOTH.get_out_mesh_shape(nc, noneValid=True):
        return log.error("|{0}| >> nCloth has no output mesh".format(_str_func))

    xforms = mc.listRelatives(nc, parent=True, fullPath=True) or []
    if not xforms:
        return log.error("|{0}| >> nCloth has no transform".format(_str_func))

    # Link transform — shape links use viewName and do not read back via getMessage.
    mOwner.connectChildNode(xforms[0], 'mCloth')
    log.info("|{0}| >> Mapped cloth: {1}".format(_str_func, xforms[0]))

    mSetupNucleus = mOwner.getMessageAsMeta('mNucleus')
    if mSetupNucleus:
        _connect_dyn_sim_to_nucleus(nc, mSetupNucleus.mNode)
    else:
        _clothNucleus = NCLOTH.get_nucleus(nc, noneValid=True)
        if _clothNucleus:
            mOwner.connectChildNode(_clothNucleus, 'mNucleus')
            _wire_time1_current_time(_clothNucleus)
            _wire_time1_current_time(nc)
            log.info("|{0}| >> Linked cloth nucleus: {1}".format(_str_func, _clothNucleus))

    return get_mapped_cloth(mOwner)


def _resolve_nucleus_node(node):
    """Resolve a nucleus node from a nucleus or its transform."""
    if not node or not mc.objExists(node):
        return None
    node = VALID.mNodeString(node)
    if mc.objectType(node) == 'nucleus':
        return node
    shapes = mc.listRelatives(node, shapes=True, type='nucleus', fullPath=True) or []
    return shapes[0] if shapes else None


def _resolve_hair_system_shape(node):
    """Resolve a hairSystem shape from a shape or its transform."""
    if not node or not mc.objExists(node):
        return None
    node = VALID.mNodeString(node)
    if mc.objectType(node) == 'hairSystem':
        return node
    shapes = mc.listRelatives(node, shapes=True, type='hairSystem', fullPath=True) or []
    if shapes:
        return shapes[0]
    # Follicle / curve → connected hairSystem
    for n in (mc.listHistory(node, future=True) or []) + (mc.listHistory(node, future=False) or []):
        if mc.objectType(n) == 'hairSystem':
            return n
    con = mc.listConnections(node, type='hairSystem', shapes=True) or []
    return con[0] if con else None


def _follicle_hair_system_shape_from_follicle(follicle_shape):
    """Resolve hairSystem shape wired to a follicle shape (post-MCD graph)."""
    follicle_shape = VALID.mNodeString(follicle_shape)
    if not follicle_shape or not mc.objExists(follicle_shape):
        return None
    _con = mc.listConnections('{0}.currentPosition'.format(follicle_shape), s=False, d=True) or []
    if not _con:
        _con = mc.listConnections(follicle_shape, type='hairSystem', shapes=True) or []
        return _con[0] if _con else None
    _node = _con[0]
    if mc.objectType(_node) == 'hairSystem':
        return _node
    _shapes = mc.listRelatives(_node, shapes=True, type='hairSystem', fullPath=True) or []
    if _shapes:
        return _shapes[0]
    _hs = mc.listConnections(_node, type='hairSystem', shapes=True) or []
    return _hs[0] if _hs else None


def hair_system_list_registered(mSetup):
    """All hairSystem shapes registered on a cgmDynFK setup."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return []
    ml = mSetup.msgList_get('mHairSystems') or []
    if ml:
        return ml
    mDefault = mSetup.getMessageAsMeta('mHairSysShape')
    return [mDefault] if mDefault else []


def hair_system_get_default(mSetup):
    """Setup default hairSystem shape meta (Presets → Hair menu target)."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return None
    return mSetup.getMessageAsMeta('mHairSysShape')


def hair_system_set_default(mSetup, mHairSysShape):
    """Set setup default hairSystem messages (does not register)."""
    _str_func = 'hair_system_set_default'
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mHair = cgmMeta.validateObjArg(mHairSysShape, noneValid=True)
    if not mSetup or not mHair:
        return None
    _hs = _resolve_hair_system_shape(mHair.mNode)
    if not _hs:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hairSystem'))
    mHair = cgmMeta.asMeta(_hs)
    mDag = mHair.getTransform(asMeta=True)
    mSetup.connectChildNode(mDag.mNode, 'mHairSysDag', 'owner')
    mSetup.connectChildNode(mHair.mNode, 'mHairSysShape', 'owner')
    return mHair


def hair_system_name_token(mHairSysShape):
    """Basename token for a hairSystem DAG (strips trailing ``_hairSys``)."""
    mHair = cgmMeta.validateObjArg(mHairSysShape, noneValid=True)
    if not mHair:
        return ''
    _hs = _resolve_hair_system_shape(mHair.mNode)
    if not _hs:
        return ''
    mHair = cgmMeta.asMeta(_hs)
    mDag = mHair.getTransform(asMeta=True)
    if not mDag:
        return ''
    _base = mDag.p_nameBase or ''
    if _base.endswith('_hairSys'):
        return _base[:-len('_hairSys')] or _base
    return _base


def hair_system_set_name(mSetup, mHairSysShape, name):
    """
    Rename a registered hairSystem transform to ``{token}_hairSys``.

    Does not rename follicles / chains — only the hairSystem DAG (+ Maya shape).
    """
    _str_func = 'hair_system_set_name'
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mHair = cgmMeta.validateObjArg(mHairSysShape, noneValid=True)
    if not mSetup or not mHair:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Need setup and hairSystem'))
    _hs = _resolve_hair_system_shape(mHair.mNode)
    if not _hs:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hairSystem'))
    mHair = cgmMeta.asMeta(_hs)
    mDag = mHair.getTransform(asMeta=True)
    if not mDag:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No hairSystem transform'))

    _token = _chain_clean_name_token(name)
    if not _token:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Empty or invalid name'))
    if _token.endswith('_hairSys'):
        _token = _token[:-len('_hairSys')] or _token
    _new_short = '{0}_hairSys'.format(_token)
    _old_short = mDag.p_nameBase or ''
    if _new_short == _old_short:
        return True

    for mOther in hair_system_list_registered(mSetup) or []:
        if not mOther or mOther.mNode == mHair.mNode:
            continue
        mOtherDag = mOther.getTransform(asMeta=True)
        if mOtherDag and mOtherDag.p_nameBase == _new_short:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'Hair system name already in use: {0}'.format(_new_short)))

    mc.undoInfo(openChunk=True, chunkName='cgmDynSimTool hairSystem rename')
    try:
        try:
            mDag.dagLock(False)
        except Exception:
            pass
        _chain_rename_meta_short(mDag, _new_short)
        try:
            mDag.dagLock()
        except Exception:
            pass
    finally:
        mc.undoInfo(closeChunk=True)

    log.info(cgmGEN.logString_msg(
        _str_func, '{0} -> {1}'.format(_old_short, mDag.p_nameBase)))
    return True


def hair_system_register(mSetup, mHairSysShape, setDefault=False):
    """
    Register a hairSystem on setup msgList ``mHairSystems``; parent DAG under setup.

    :param setDefault: When True or setup has no default, also set mHairSysShape / mHairSysDag.
    """
    _str_func = 'hair_system_register'
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    mHair = cgmMeta.validateObjArg(mHairSysShape, noneValid=True)
    if not mSetup or not mHair:
        return None
    _hs = _resolve_hair_system_shape(mHair.mNode)
    if not _hs:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hairSystem'))
    mHair = cgmMeta.asMeta(_hs)

    ml_reg = mSetup.msgList_get('mHairSystems') or []
    _known = {m.mNode for m in ml_reg}
    if mHair.mNode not in _known:
        ml_reg.append(mHair)
        mSetup.msgList_connect('mHairSystems', ml_reg)

    mDag = mHair.getTransform(asMeta=True)
    try:
        if mDag.getParent(asMeta=True) != mSetup:
            mDag.p_parent = mSetup
    except Exception as err:
        log.debug("|{0}| >> Parent hair dag skipped: {1}".format(_str_func, err))

    mNucleus = mSetup.getMessageAsMeta('mNucleus')
    if mNucleus:
        _nuc_long = _scene_node_long(mNucleus.mNode)
        _on_nuc = _scene_node_long(_nucleus_for_dyn_sim(mHair.mNode))
        if _on_nuc == _nuc_long:
            _idx = _nucleus_dyn_sim_slot_index(mNucleus.mNode, mHair.mNode)
            if _idx is not None:
                _n = _dedupe_nucleus_sim_plugs(mHair.mNode, mNucleus.mNode, _idx)
                if _n:
                    log.info(cgmGEN.logString_msg(
                        _str_func, 'Removed {0} duplicate nucleus plug(s) on {1}'.format(
                            _n, mHair.p_nameShort)))
        elif _on_nuc != _nuc_long:
            _connect_dyn_sim_to_nucleus(mHair.mNode, mNucleus.mNode)

    if setDefault or not mSetup.getMessageAsMeta('mHairSysShape'):
        hair_system_set_default(mSetup, mHair)

    log.info(cgmGEN.logString_msg(_str_func, mHair.p_nameShort))
    return mHair


def hair_system_backfill_chain(mGrp, mSetup):
    """Ensure chain mHairSysShape message and setup registry from follicle DG."""
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mGrp or not mSetup:
        return None
    if (getattr(mGrp, 'chainMode', None) or 'hair') != 'hair':
        return None
    mHair = mGrp.getMessageAsMeta('mHairSysShape')
    if mHair and mc.objExists(mHair.mNode):
        ml_reg = mSetup.msgList_get('mHairSystems') or []
        if mHair.mNode not in {m.mNode for m in ml_reg}:
            hair_system_register(mSetup, mHair, setDefault=False)
        return mHair
    mFollicle = mGrp.getMessageAsMeta('mFollicle')
    if not mFollicle:
        return None
    _fshape = mFollicle.getShapes(asMeta=False)
    if not _fshape:
        return None
    _hs = _follicle_hair_system_shape_from_follicle(_fshape[0])
    if not _hs:
        return None
    mHair = cgmMeta.asMeta(_hs)
    mGrp.connectChildNode(mHair.mNode, 'mHairSysShape', 'group')
    hair_system_register(mSetup, mHair, setDefault=False)
    return mHair


def hair_system_resolve_for_chain(mGrp, mSetup, backfill=True):
    """HairSystem meta for a hair chain grp."""
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mGrp or not mSetup:
        return None
    if backfill:
        hair_system_backfill_chain(mGrp, mSetup)
    mHair = mGrp.getMessageAsMeta('mHairSysShape')
    if mHair and mc.objExists(mHair.mNode):
        return mHair
    mHair = hair_system_get_default(mSetup)
    if mHair:
        return mHair
    mFollicle = mGrp.getMessageAsMeta('mFollicle')
    if mFollicle:
        _fshape = mFollicle.getShapes(asMeta=False)
        if _fshape:
            _hs = _follicle_hair_system_shape_from_follicle(_fshape[0])
            if _hs:
                return cgmMeta.asMeta(_hs)
    return None


def _hair_system_create_empty(mSetup, dag_name):
    """
    Create an empty hairSystem transform + shape on the setup, wired to setup nucleus.

    Used before makeCurvesDynamic when ``hairSystemMode=new`` but a hairSystem already
    exists on the nucleus (MCD would otherwise add the curve to the existing system).
    """
    _str_func = '_hair_system_create_empty'
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return None
    _dag_name = VALID.stringArg(dag_name, noneValid=True) or '{0}_hairSys'.format(mSetup.baseName)
    mDag = mSetup.doCreateAt()
    mDag.rename(_dag_name)
    _shape = mc.createNode('hairSystem', name='{0}Shape'.format(_dag_name), parent=mDag.mNode)
    mHair = cgmMeta.asMeta(_shape)

    mNucleus = mSetup.getMessageAsMeta('mNucleus')
    if not mNucleus:
        mNucleus = cgmMeta.validateObjArg('cgmDynFK_nucleus', noneValid=True)
    if mNucleus:
        _connect_dyn_sim_to_nucleus(mHair.mNode, mNucleus.mNode)
        if mSetup.startFrame is not None and mc.attributeQuery('startFrame', node=mHair.mNode, exists=True):
            try:
                mc.setAttr('{0}.startFrame'.format(mHair.mNode), mSetup.startFrame)
            except Exception:
                pass

    mDag.p_parent = mSetup
    hair_system_register(mSetup, mHair, setDefault=False)
    log.info(cgmGEN.logString_msg(_str_func, '{0} | {1}'.format(_dag_name, mHair.mNode)))
    return mHair


def _setup_has_existing_hair_sim(mSetup):
    """True when setup already has a hairSystem or hair chain (shared nucleus MCD would merge)."""
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return False
    if hair_system_list_registered(mSetup):
        return True
    if hair_system_get_default(mSetup):
        return True
    for mGrp in mSetup.msgList_get('chain') or []:
        if (getattr(mGrp, 'chainMode', None) or 'hair') != 'hair':
            continue
        if mGrp.getMessageAsMeta('mFollicle') or mGrp.getMessageAsMeta('mHairSysShape'):
            return True
    return False


def hair_system_resolve_for_create(mSetup, mode=None, chainName=None):
    """
    Resolve hairSystem for Make Dynamic Chain.

    :param mode: ``new`` | ``default`` | registered short name / index string
    :returns: ``(mHairSysShape or None, b_join_existing_for_mcd)``
    """
    mode = (mode or 'default').strip()
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mSetup:
        return None, False

    if mode.lower() in ('new', 'create'):
        return None, False

    ml_reg = hair_system_list_registered(mSetup)
    if mode.lower() in ('default', 'setup'):
        mHair = hair_system_get_default(mSetup)
        if mHair:
            return mHair, True
        if ml_reg:
            return ml_reg[0], True
        return None, False

    if mode.isdigit():
        _idx = int(mode)
        if 0 <= _idx < len(ml_reg):
            return ml_reg[_idx], True
        return None, False

    _mode_low = mode.lower()
    for mHair in ml_reg:
        if mHair.p_nameBase.lower() == _mode_low or mHair.p_nameShort.lower() == _mode_low:
            return mHair, True
        mDag = mHair.getTransform(asMeta=True)
        if mDag.p_nameBase.lower() == _mode_low or mDag.p_nameShort.lower() == _mode_low:
            return mHair, True

    mHair = hair_system_get_default(mSetup)
    if mHair:
        return mHair, True
    return None, False


def _rewire_follicle_hair_system(follicle_shape, target_hair_system_shape):
    """Move follicle sim hookup to another hairSystem (Maya assignHairSystem)."""
    _str_func = '_rewire_follicle_hair_system'
    follicle_shape = VALID.mNodeString(follicle_shape)
    target_hair_system_shape = VALID.mNodeString(target_hair_system_shape)
    if not follicle_shape or not target_hair_system_shape:
        return False
    _follicle_xform = (mc.listRelatives(follicle_shape, parent=True, fullPath=True) or [None])[0]
    _hs_xform = (mc.listRelatives(target_hair_system_shape, parent=True, fullPath=True) or [None])[0]
    if not _follicle_xform or not _hs_xform:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Missing follicle or hairSystem transform'))

    _current = _follicle_hair_system_shape_from_follicle(follicle_shape)
    if _current == target_hair_system_shape:
        return True

    try:
        mc.select(_hs_xform, _follicle_xform, replace=True)
        mel.eval('assignHairSystem;')
        mc.select(cl=True)
        _after = _follicle_hair_system_shape_from_follicle(follicle_shape)
        if _after == target_hair_system_shape:
            log.info(cgmGEN.logString_msg(_str_func, 'Rewired follicle to {0}'.format(target_hair_system_shape)))
            return True
    except Exception as err:
        log.warning(cgmGEN.logString_msg(_str_func, 'assignHairSystem failed: {0}'.format(err)))

    log.warning(cgmGEN.logString_msg(
        _str_func, 'Rewire may have failed — try Rebuild Chain on this hair chain'))
    return False


def chain_map_hair_system(mGrp, mSetup, node=None):
    """Map selection hairSystem to a hair chain (rewire follicle + messages)."""
    _str_func = 'chain_map_hair_system'
    mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
    mSetup = cgmMeta.validateObjArg(mSetup, noneValid=True)
    if not mGrp or not mSetup:
        return log.warning(cgmGEN.logString_msg(_str_func, 'Invalid chain or setup'))
    if (getattr(mGrp, 'chainMode', None) or 'hair') != 'hair':
        return log.warning(cgmGEN.logString_msg(_str_func, 'Not a hair chain'))

    if node is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            return log.error("|{0}| >> Nothing selected".format(_str_func))
        node = _sel[0]

    _hs = _resolve_hair_system_shape(node)
    if not _hs:
        return log.error("|{0}| >> Selection is not a hairSystem".format(_str_func))

    mHair = cgmMeta.asMeta(_hs)
    hair_system_register(mSetup, mHair, setDefault=False)

    mFollicle = mGrp.getMessageAsMeta('mFollicle')
    if mFollicle:
        _fshape = mFollicle.getShapes(asMeta=False)
        if _fshape:
            _rewire_follicle_hair_system(_fshape[0], mHair.mNode)

    mGrp.connectChildNode(mHair.mNode, 'mHairSysShape', 'group')

    _old_start = _resolve_hair_start_frame(mSetup, mGrp=mGrp)
    _new_start = mc.getAttr('{0}.startFrame'.format(mHair.mNode)) if mc.attributeQuery(
        'startFrame', node=mHair.mNode, exists=True) else None
    if _new_start is not None and _old_start != _new_start:
        log.warning(cgmGEN.logString_msg(
            _str_func, 'hairSystem startFrame {0} differs from connect frame basis {1}'.format(
                _new_start, _old_start)))

    log.info(cgmGEN.logString_msg(_str_func, '{0} -> chain {1}'.format(mHair.p_nameShort, mGrp.p_nameBase)))
    return mHair


def map_nucleus(mOwner, node=None):
    """
    Link a nucleus to setup ``mNucleus`` (from selection or arg).

    Rewires mapped cloth / hair sim to the linked nucleus when present.
    """
    _str_func = 'map_nucleus'
    import cgm.core.lib.nCloth_utils as NCLOTH

    if node is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            return log.error("|{0}| >> Nothing selected".format(_str_func))
        node = _sel[0]

    nucleus = _resolve_nucleus_node(node)
    if not nucleus:
        return log.error("|{0}| >> Selection is not a nucleus".format(_str_func))

    mOwner.connectChildNode(nucleus, 'mNucleus')
    _wire_time1_current_time(nucleus)
    log.info("|{0}| >> Mapped nucleus: {1}".format(_str_func, nucleus))

    mCloth = get_mapped_cloth(mOwner)
    if mCloth:
        nc = NCLOTH.get_nCloth(mCloth.mNode, noneValid=True)
        if nc:
            _connect_dyn_sim_to_nucleus(nc, nucleus)

    for mHair in hair_system_list_registered(mOwner):
        _connect_dyn_sim_to_nucleus(mHair.mNode, nucleus)

    return mOwner.getMessageAsMeta('mNucleus')


def map_hair_system(mOwner, node=None):
    """
    Link a hairSystem as setup default ``mHairSysShape`` / ``mHairSysDag``.

    Registers on ``mHairSystems`` and rewires to setup nucleus when mapped.
    """
    _str_func = 'map_hair_system'

    if node is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            return log.error("|{0}| >> Nothing selected".format(_str_func))
        node = _sel[0]

    hs = _resolve_hair_system_shape(node)
    if not hs:
        return log.error("|{0}| >> Selection is not a hairSystem".format(_str_func))

    mHair = hair_system_register(mOwner, hs, setDefault=True)
    log.info("|{0}| >> Mapped hairSystem (default): {1}".format(_str_func, hs))
    return mHair


def attach_to_cloth_dynFK(mOwner, objs=None, name=None, surfaceTrack='follicle', **kws):
    """
    Attach joint list to mapped nCloth outMesh via RIGCONSTRAINTS.attach_toShape.

    surfaceTrack: follicle | rivet | uvPin (mesh trackers on outMesh).
    Per target: track node + loc parented under track (mLocs for connect/bake).
    """
    _str_func = 'attach_to_cloth_dynFK'
    import cgm.core.lib.nCloth_utils as NCLOTH

    surfaceTrack = surfaceTrack or 'follicle'
    if surfaceTrack not in ('follicle', 'rivet', 'uvPin'):
        log.warning("|{0}| >> Unknown surfaceTrack '{1}' — using follicle".format(_str_func, surfaceTrack))
        surfaceTrack = 'follicle'

    mCloth = get_mapped_cloth(mOwner)
    if not mCloth:
        return log.error("|{0}| >> Map cloth surface first".format(_str_func))

    outMeshShape = NCLOTH.get_out_mesh_shape(mCloth.mNode, noneValid=False)
    if not outMeshShape:
        return log.error("|{0}| >> No output mesh on mapped nCloth".format(_str_func))

    if not objs:
        _sel = mc.ls(sl=1)
        if _sel:
            objs = _sel

    ml = cgmMeta.asMeta(objs, noneValid=True)
    ml_baseTargets = copy.copy(ml)

    if not ml:
        return log.warning("|{0}| >> No objects passed".format(_str_func))

    if not name:
        name = ml[-1].p_nameBase
    name = chain_resolve_unique_name(mOwner, name)

    mGrp = mOwner.doCreateAt(setClass=1)
    mGrp.p_parent = mOwner
    mGrp.rename("chain_{0}_grp".format(name))
    mGrp.dagLock()
    chain_connect_to_setup(mOwner, mGrp)
    mGrp.doStore('chainMode', 'clothAttach')
    mGrp.doStore('cgmName', name)
    mGrp.doStore('surfaceTrack', surfaceTrack)

    ml_follicles = []
    ml_rivets = []
    ml_uvpins = []
    ml_locs = []

    for mObj in ml:
        _res = RIGCONSTRAINTS.attach_toShape(
            mObj.mNode,
            outMeshShape,
            connectBy=None,
            parentTo=mGrp.mNode,
            surfaceTrack=surfaceTrack,
        )
        if not _res:
            return log.error("|{0}| >> attach_toShape failed on {1}".format(_str_func, mObj.mNode))

        md_res = {}
        if isinstance(_res, tuple):
            _res, md_res = _res

        mTrack = md_res.get('mTrack') or md_res.get('mFollicle') or md_res.get('mRivet') or md_res.get('mUvPin')
        if not mTrack:
            return log.error("|{0}| >> No surface track from attach_toShape on {1}".format(_str_func, mObj.mNode))

        mLoc = mObj.doLoc()
        mLoc.p_parent = mTrack

        if surfaceTrack == 'rivet':
            ml_rivets.append(mTrack)
        elif surfaceTrack == 'uvPin':
            ml_uvpins.append(mTrack)
        else:
            ml_follicles.append(mTrack)
        ml_locs.append(mLoc)
        SNAP.matchTarget_set(mObj.mNode, mLoc.mNode)

    if ml_follicles:
        mGrp.msgList_connect('mMeshFollicles', ml_follicles)
    if ml_rivets:
        mGrp.msgList_connect('mRivets', ml_rivets)
    if ml_uvpins:
        mGrp.msgList_connect('mUvPins', ml_uvpins)
    mGrp.msgList_connect('mLocs', ml_locs)
    mGrp.msgList_connect('mTargets', ml)
    mGrp.msgList_connect('mBaseTargets', ml_baseTargets)

    _idx = chain_setup_index(mOwner, mGrp)
    log.info(cgmGEN.logString_msg(_str_func, 'chain {0} attached ({1} {2} trackers)'.format(
        _idx, len(ml_locs), surfaceTrack)))
    return mGrp


def setup_sim_dynFK(baseName='DynamicChain', startFrame=None, applyPreset=True, mOwner=None):
    """
    Create or extend a cgmDynFK setup with nucleus only (no hair chain).

    Use before mapping cloth when you do not want Make Dynamic Chain first.
    """
    _str_func = 'setup_sim_dynFK'
    if mOwner:
        mSetup = cgmMeta.validateObjArg(mOwner, noneValid=True)
        if not mSetup or getattr(mSetup, 'mClass', None) != 'cgmDynFK':
            return log.error("|{0}| >> Owner is not a cgmDynFK setup".format(_str_func))
    else:
        # Explicit empty list — do not fall back to Maya selection / chain_create
        mSetup = cgmDynFK(baseName=baseName, objs=[], startFrame=startFrame)

    mSetup.setup_sim(startFrame=startFrame, applyPreset=applyPreset)
    log.info(cgmGEN.logString_msg(_str_func, mSetup.p_nameBase))
    return mSetup

    
class cgmDynFK(cgmMeta.cgmObject):
    baseName = None
    fwd = None
    up = None
    startFrame = None
    useExistingNucleus = True
    upSetup = 'liveStart'
    fixedSegmentLength = False
    follicleSegmentLength = FOLLICLE_FIXED_SEGMENT_LENGTH
    follicleSampleDensity = FOLLICLE_DEFAULT_SAMPLE_DENSITY
    hairFollowMode = HAIR_FOLLOW_MODE_SPLINE
    inCurveDegree = 1
    outCurveDegree = 2
    advancedTwist = False
    
    def __init__(self,node = None, name = None,
                 objs = None, fwd = 'z+', up = 'y+',
                 upSetup = 'guess',
                 hairSystem=None,
                 useExistingNucleus = True,
                 baseName = 'hair',
                 startFrame = -50,
                 extendStart = None,
                 extendEnd = None,
                 addEndJoint = None,
                 upControl = False,
                 aimUpMode = 'joint',
                 fixedSegmentLength = False,
                 follicleSegmentLength = None,
                 follicleSampleDensity = None,
                 hairFollowMode = None,
                 inCurveDegree = None,
                 outCurveDegree = None,
                 requireAddEndJoint = False,
                 advancedTwist = None,
                 *args,**kws):
        """ 
        
        upSetup
           liveStart
           control

        """
        ### input check
        # objs=None → optional Maya selection (legacy scripted create).
        # objs=[] → no targets / no chain (Init Sim / setup_sim_dynFK).
        _sel = mc.ls(sl=1)
        if objs is None and node is None:
            if _sel:
                objs = _sel
        
        super().__init__(node = node,name = baseName,nodeType = 'transform')
        #>>> TO USE Cached instance ---------------------------------------------------------
        if self.cached:
            return
        
        #====================================================================================
        #for a in 'arg_ml_dynParents','_mi_dynChild','_mi_followDriver','d_indexToAttr','l_dynAttrs':
            #if a not in self.UNMANAGED:
                #self.UNMANAGED.append(a)
                
        self.dagLock(ignore=['v'])

        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))
        
        self.fwd = fwd
        self.up = up
        self.startFrame = startFrame
        if node:
            if self.hasAttr('cgmName') and self.cgmName:
                self.baseName = self.cgmName
            else:
                _short = self.p_nameBase
                self.baseName = _short[:-6] if _short.endswith('_dynFK') else _short
        else:
            self.baseName = baseName
        self.useExistingNucleus = useExistingNucleus
        self.upSetup = upSetup
        addEndJoint, extendEnd = _hair_resolve_create_extend_kws(addEndJoint, extendEnd)
        self.addEndJoint = addEndJoint if addEndJoint is not None else False
        self.extendEnd = extendEnd if extendEnd is not None else False
        self.extendStart = extendStart
        self.aimUpMode = aimUpMode
        self.upControl = upControl
        self.fixedSegmentLength = fixedSegmentLength
        self.follicleSegmentLength = (
            follicleSegmentLength if follicleSegmentLength is not None else FOLLICLE_FIXED_SEGMENT_LENGTH)
        try:
            self.follicleSampleDensity = float(
                follicleSampleDensity if follicleSampleDensity is not None else FOLLICLE_DEFAULT_SAMPLE_DENSITY)
        except (TypeError, ValueError):
            self.follicleSampleDensity = FOLLICLE_DEFAULT_SAMPLE_DENSITY
        self.hairFollowMode = _resolve_hair_follow_mode(hairFollowMode, None, kws)
        self.inCurveDegree = MATHUTILS.Clamp(int(inCurveDegree if inCurveDegree is not None else 1), 1, 3)
        self.outCurveDegree = MATHUTILS.Clamp(int(outCurveDegree if outCurveDegree is not None else 2), 1, 3)
        self.requireAddEndJoint = bool(requireAddEndJoint)
        self.advancedTwist = bool(advancedTwist) if advancedTwist is not None else False
       
        if not node:
            self.rename("{0}_dynFK".format(self.baseName))
            self.doStore('cgmName', self.baseName)
            
        if objs:
            _hairSystemMode = kws.pop('hairSystemMode', 'default')
            self.chain_create(
                objs, fwd, up, name=name,
                upSetup=self.upSetup,
                extendStart=self.extendStart,
                addEndJoint=self.addEndJoint,
                extendEnd=self.extendEnd,
                upControl=self.upControl,
                aimUpMode=self.aimUpMode,
                fixedSegmentLength=self.fixedSegmentLength,
                follicleSegmentLength=self.follicleSegmentLength,
                follicleSampleDensity=self.follicleSampleDensity,
                hairFollowMode=self.hairFollowMode,
                inCurveDegree=self.inCurveDegree,
                outCurveDegree=self.outCurveDegree,
                requireAddEndJoint=self.requireAddEndJoint,
                hairSystemMode=_hairSystemMode,
            )
        
        self.report()

    def set_base_name(self, name):
        """Update setup base name and rename the cgmDynFK transform."""
        _str_func = 'set_base_name'
        _name = VALID.stringArg(name, noneValid=True)
        if not _name:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty name'))
        _name = _name.strip()
        if not _name:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty name'))
        if _name == self.baseName:
            return True

        self.baseName = _name
        self.doStore('cgmName', _name)
        self.rename("{0}_dynFK".format(_name))
        log.info(cgmGEN.logString_msg(_str_func, _name))
        return True
        
        if _sel:
            mc.select(_sel)
    
    def get_nextIdx(self):
        """Next free ``chain`` msgList slot (does not call ``get_dat``)."""
        return ATTR.get_nextAvailableSequentialAttrIndex(self.mNode, 'chain')
        
    def chain_rebuild(self, idx = None, objs = None, **kws):
        _str_func = 'chain_rebuild'
        dat = self.get_dat()
        mNucleus = dat['mNucleus']
        mHairSysShape = dat['mHairSysShape']
        
        l_do = []
        if idx:
            if dat['chains'].get(idx):
                l_do.append(idx)
        else:
            l_do = list(dat['chains'].keys())
            
        log.debug(cgmGEN.logString_msg(_str_func, 'To do: {0}'.format(l_do)))
        for idx in l_do:
            log.debug(cgmGEN.logString_sub(_str_func, 'On: {0}'.format(idx)))            
            _d = dat['chains'][idx]
            ml_targets = _d['mTargets']
            self.targets_disconnect(idx)#...remove contraints
            mDynFKParent = ml_targets[0].getMessageAsMeta('dynFKParentGroup')
            if mDynFKParent:
                ml_targets[0].p_parent = mDynFKParent.p_parent
                mDynFKParent.delete()
            
            self.chain_deleteByIdx(idx)
            
            self.chain_create(ml_targets,**kws)
            self.targets_connect(idx)#...remove contraints
            log.debug(cgmGEN.logString_msg(_str_func, 'chain {0} done'.format(idx)))
            

    
    def get_nucleus(self,mNucleus=None):
        """Try to get the nucleus from the scene to use for other setups"""
        if mNucleus is not None:
           return cgmMeta.validateObjArg(mNucleus,noneValid=True)
        if self.getMessageAsMeta('mNucleus'):
            return self.getMessageAsMeta('mNucleus')
        return cgmMeta.validateObjArg('cgmDynFK_nucleus',noneValid=True)

    def ensure_nucleus(self, mNucleus=None, startFrame=None):
        """Create or link setup mNucleus without a dynamic hair chain."""
        _str_func = 'ensure_nucleus'

        mExisting = self.getMessageAsMeta('mNucleus')
        if mExisting:
            _wire_time1_current_time(mExisting.mNode)
            return mExisting

        mNucleus = cgmMeta.validateObjArg(mNucleus, noneValid=True) if mNucleus else self.get_nucleus()
        if not mNucleus:
            mNucleus = cgmMeta.asMeta(mc.createNode('nucleus', name='cgmDynFK_nucleus'))
            mNucleus.p_parent = self
        elif not mc.objExists('cgmDynFK_nucleus'):
            mNucleus.rename('cgmDynFK_nucleus')

        self.connectChildNode(mNucleus.mNode, 'mNucleus')

        _start = startFrame if startFrame is not None else self.startFrame
        if _start is None:
            _start = mc.playbackOptions(q=True, min=True)
        mNucleus.startFrame = _start

        _wire_time1_current_time(mNucleus.mNode)

        log.info(cgmGEN.logString_msg(_str_func, mNucleus.p_nameBase))
        return mNucleus

    def setup_sim(self, startFrame=None, applyPreset=True):
        """Initialize nucleus on this setup (no makeCurvesDynamic / hair chain)."""
        _str_func = 'setup_sim'
        mNucleus = self.ensure_nucleus(startFrame=startFrame)
        if applyPreset:
            profile_load(mNucleus.mNode, 'base')
        _wire_time1_current_time(mNucleus.mNode)
        log.info(cgmGEN.logString_msg(_str_func, self.p_nameBase))
        return mNucleus

    def map_cloth_surface(self, node=None):
        return map_cloth_surface(self, node)

    def attach_to_cloth(self, objs=None, name=None, **kws):
        return attach_to_cloth_dynFK(self, objs=objs, name=name, **kws)
        
    def chain_deleteByIdx(self, idx = None):
        if idx is None:
            return log.warning("Must have an idx to remove")
        
        # mDat = self.get_dat()
        
        # _d = mDat['chains'].get(idx)
        # mGrp = _d.get('mGrp')

        chain = self.msgList_get('chain')[idx]
        
        #mGrp = self.getMessageAsMeta("chain_{0}".format(idx))
        if chain:
            chain.delete()
            ATTR.msgList_clean(self.mNode,'chain')
            return log.info("Removed idx: {0}".format(idx))
        else:
            return log.warning("No chain found at idx: {0}".format(idx))
            
    def chain_removeAll(self):
        ml = self.msgList_get('chain')
        for i,mGrp in enumerate(ml):
            log.warning("Removing: {0} | {1}".format(i,mGrp.mNode))
            mGrp.delete()
        
        self.msgList_purge('chain')
    
    def chain_setOrientUpByIdx(self, idx=None, axis=None):
        if idx is None:
            return log.warning("Must have an idx to set orient")

        chain = self.msgList_get('chain')[idx]

        for parent in chain.msgList_get('mParents'):
            for constraint in CONSTRAINTS.get_constraintsFrom(parent, typeFilter='aimConstraint'):
                constraintNode = cgmMeta.asMeta(constraint)
                if axis is None:
                    constraintNode.worldUpType = 4
                else:
                    constraintNode.worldUpType = 2
                    constraintNode.upVector = axis.p_vector
                    constraintNode.worldUpVector = axis.p_vector

        chain.up = str(axis)

        return str(axis)

    def chain_rebuild_hair(self, idx=None):
        """Rebuild hair follow rig — spline IK or legacy POC path."""
        ml_chains = self.msgList_get('chain') or []
        if idx is None:
            idx = 0
        if idx >= len(ml_chains):
            return log.warning(cgmGEN.logString_msg('chain_rebuild_hair', 'No chain at idx {0}'.format(idx)))
        mGrp = ml_chains[idx]
        if _get_chain_hair_follow_mode(mGrp) == HAIR_FOLLOW_MODE_SPLINE:
            return self.chain_rebuild_spline_follow(idx)
        return self.chain_rebuild_follow(idx)

    def chain_rebuild_spline_follow(self, idx=None):
        """
        Rebuild spline-IK follow at frame before sim start: inCurve, follicle outCurve, driven + locators.
        """
        _str_func = 'chain_rebuild_spline_follow'
        ml_chains = self.msgList_get('chain') or []
        if idx is None:
            idx = 0
        if idx >= len(ml_chains):
            return log.warning(cgmGEN.logString_msg(_str_func, 'No chain at idx {0}'.format(idx)))

        mGrp = ml_chains[idx]
        if _get_chain_hair_follow_mode(mGrp) != HAIR_FOLLOW_MODE_SPLINE:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'Chain {0} is not splineIk mode'.format(mGrp.p_nameBase)))

        mFollicle = mGrp.getMessageAsMeta('mFollicle')
        mInCrv = mGrp.getMessageAsMeta('mInCrv')
        ml = mGrp.msgList_get('mTargets')
        ml_baseTargets = mGrp.msgList_get('mBaseTargets') or ml
        ml_sim = _hair_normalize_sim_chain(mGrp.msgList_get('mObjJointChain'))
        if not all([mFollicle, mInCrv, ml, ml_sim]):
            return log.error(cgmGEN.logString_msg(_str_func, 'Incomplete hair chain on {0}'.format(mGrp.p_nameBase)))

        _name = mGrp.cgmName if mGrp.hasAttr('cgmName') else mGrp.p_nameBase
        mFollicleShape = mFollicle.getShapes(asMeta=True)[0]
        _follicleShape = mFollicleShape.mNode
        mHairSys = hair_system_resolve_for_chain(mGrp, self)
        _hairSystem = mHairSys.mNode if mHairSys else None
        if not _hairSystem:
            _hairSystem = _follicle_hair_system_shape_from_follicle(_follicleShape)
            if _hairSystem:
                mHairSys = cgmMeta.asMeta(_hairSystem)

        _inDeg, _outDeg = _resolve_hair_curve_degrees(mGrp, self)
        _skinName = '{0}_skinCluster'.format(_name)
        _b_connected = _chain_targets_connected(mGrp)
        if _b_connected:
            self.targets_disconnect(idx)

        _savedTime = mc.currentTime(q=True)
        _startFrame = _resolve_hair_start_frame(self, mGrp=mGrp)
        _rebuildFrame = _startFrame - 1
        mc.currentTime(_rebuildFrame, edit=True)

        _settings = _get_hair_chain_follow_settings(mGrp)
        if mGrp.hasAttr('fwd') and mGrp.hasAttr('up'):
            fwdAxis = simpleAxis(mGrp.fwd)
            upAxis = simpleAxis(mGrp.up)
        else:
            fwdAxis = TRANS.closestAxisTowardObj_get(ml_baseTargets[0], ml_baseTargets[1])
            upAxis = TRANS.crossAxis_get(fwdAxis)

        # Tear down follow + inCurve skin before moving sim joints (add-end distance).
        # Moving skinned joints while spline IK / hair is live can hang Maya DG.
        _tear_down_hair_chain_follow_spline(mGrp)
        _delete_hair_incurve_skincluster(mInCrv)
        _hair_delete_stray_joints_under_sim(ml_sim)
        ml_sim = _hair_rename_sim_joint_chain(ml_sim, _name)

        _suspend = False
        try:
            _suspend = mc.refresh(q=True, suspend=True)
        except Exception:
            pass
        cgmGEN.playback_stop()
        try:
            l_pos, ml_sim = _hair_ensure_add_end_joint_chain(
                mGrp, ml_sim, ml_baseTargets, None, _settings.get('addEndJoint'),
                _settings.get('upSetup'), fwdAxis, _name,
                extendStart=_settings.get('extendStart'),
                extendEnd=_settings.get('extendEnd'))
            ml_sim = _hair_rename_sim_joint_chain(ml_sim, _name)
            _hair_validate_add_end_joint_count(
                ml_sim, ml_baseTargets, _settings.get('addEndJoint'), l_pos=l_pos,
                context='{0} | after rebuild sim chain'.format(mGrp.p_nameBase))
            mGrp.msgList_connect('mObjJointChain', ml_sim)

            mInCrv = _consolidate_hair_incurve_after_mcd(
                mInCrv, mFollicleShape, mGrp, _name, ml_sim, l_pos, _skinName,
                fixedSegmentLength=bool(getattr(mGrp, 'fixedSegmentLength', self.fixedSegmentLength)),
                follicleSegmentLength=getattr(mGrp, 'follicleSegmentLength', self.follicleSegmentLength),
                inCurveDegree=_inDeg,
                use_follicle_input_curve=True,
                sampleDensity=_resolve_follicle_sample_density(mGrp, self))

            mOutCrv, _outCurveShape = _prepare_spline_hair_outcurve(
                mFollicle, mFollicleShape, mHairSys, _name, _outDeg)
            mOutCrv.p_parent = mGrp
            mOutCrv = _follicle_outcurve_meta(mFollicle) or mOutCrv
            _inShape = mc.listRelatives(
                mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
            _finalize_hair_outcurve_rest(
                _follicleShape, _hairSystem, _inShape, _outCurveShape,
                fixedSegmentLength=bool(getattr(mGrp, 'fixedSegmentLength', self.fixedSegmentLength)),
                follicleSegmentLength=getattr(mGrp, 'follicleSegmentLength', self.follicleSegmentLength),
                l_positions=l_pos,
                sampleDensity=_resolve_follicle_sample_density(mGrp, self))

            mGrp.connectChildNode(mOutCrv.mNode, 'mOutCrv', 'group')

            _build_hair_chain_follow_spline(
                mGrp, mOutCrv, ml, ml_sim, _name, fwdAxis=fwdAxis, upAxis=upAxis,
                mFollicle=mFollicle, ml_baseTargets=ml_baseTargets,
                advancedTwist=_settings.get('advancedTwist'))
        finally:
            try:
                mc.refresh(suspend=_suspend)
            except Exception:
                pass

        mc.currentTime(_savedTime, edit=True)
        if _b_connected:
            self.targets_connect(idx)

        log.info(cgmGEN.logString_msg(_str_func, 'Done: {0}'.format(mGrp.p_nameBase)))
        return True

    def chain_rebuild_follow(self, idx=None):
        """
        Re-sync outCurve rest at startFrame and rebuild POC/aim locators on current outCurve.

        Preserves follicle, inCurve, sim joints, and outCurve transform. Disconnects targets
        during rebuild if Connect Targets was active.
        """
        _str_func = 'chain_rebuild_follow'
        ml_chains = self.msgList_get('chain') or []
        if idx is None:
            idx = 0
        if idx >= len(ml_chains):
            return log.warning(cgmGEN.logString_msg(_str_func, 'No chain at idx {0}'.format(idx)))

        mGrp = ml_chains[idx]
        _chainMode = getattr(mGrp, 'chainMode', None) or 'hair'
        if _chainMode != 'hair':
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'Chain {0} is not hair mode'.format(mGrp.p_nameBase)))
        if _get_chain_hair_follow_mode(mGrp) == HAIR_FOLLOW_MODE_SPLINE:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'Spline chain — use chain_rebuild_hair / Rebuild Chain'))

        mFollicle = mGrp.getMessageAsMeta('mFollicle')
        mInCrv = mGrp.getMessageAsMeta('mInCrv')
        mOutCrv = mGrp.getMessageAsMeta('mOutCrv')
        ml = mGrp.msgList_get('mTargets')
        ml_baseTargets = mGrp.msgList_get('mBaseTargets') or ml
        ml_sim = _hair_normalize_sim_chain(mGrp.msgList_get('mObjJointChain'))
        if not all([mFollicle, mInCrv, mOutCrv, ml, ml_sim]):
            return log.error(cgmGEN.logString_msg(_str_func, 'Incomplete hair chain on {0}'.format(mGrp.p_nameBase)))

        _settings = _get_hair_chain_follow_settings(mGrp)
        _name = mGrp.cgmName if mGrp.hasAttr('cgmName') else mGrp.p_nameBase
        mFollicleShape = mFollicle.getShapes(asMeta=True)[0]
        _follicleShape = mFollicleShape.mNode
        _inShape = mc.listRelatives(
            mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
        outCurveShape = mc.listRelatives(mOutCrv.mNode, shapes=True)[0]

        mHairSys = hair_system_resolve_for_chain(mGrp, self)
        _hairSystem = mHairSys.mNode if mHairSys else None
        if not _hairSystem:
            _hairSystem = _follicle_hair_system_shape_from_follicle(_follicleShape)
            if _hairSystem:
                mHairSys = cgmMeta.asMeta(_hairSystem)

        _b_connected = _chain_targets_connected(mGrp)
        if _b_connected:
            self.targets_disconnect(idx)

        _savedTime = mc.currentTime(q=True)
        _startFrame = _resolve_hair_start_frame(self, mGrp=mGrp)
        if abs(_savedTime - _startFrame) > 0.001:
            log.warning(cgmGEN.logString_msg(
                _str_func,
                'Current frame {0} != startFrame {1} — rebuilding at startFrame'.format(
                    _savedTime, _startFrame)))

        mc.currentTime(_startFrame, edit=True)
        _finalize_hair_outcurve_rest(
            _follicleShape, _hairSystem, _inShape, outCurveShape)

        _tear_down_hair_chain_follow(mGrp)

        if mGrp.hasAttr('fwd') and mGrp.hasAttr('up'):
            fwdAxis = simpleAxis(mGrp.fwd)
            upAxis = simpleAxis(mGrp.up)
        else:
            fwdAxis = TRANS.closestAxisTowardObj_get(ml_baseTargets[0], ml_baseTargets[1])
            upAxis = TRANS.crossAxis_get(fwdAxis)

        _build_hair_chain_follow(
            mGrp, outCurveShape, ml, ml_baseTargets, ml_sim, _name,
            fwdAxis, upAxis,
            upSetup=_settings['upSetup'],
            upControl=_settings['upControl'],
            aimUpMode=_settings['aimUpMode'],
            addEndJoint=_settings['addEndJoint'],
            extendEnd=_settings.get('extendEnd'))

        mc.currentTime(_savedTime, edit=True)

        if _b_connected:
            self.targets_connect(idx)

        log.info(cgmGEN.logString_msg(_str_func, 'Done: {0}'.format(mGrp.p_nameBase)))
        return True

    def chain_create(self, objs = None,
                     fwd = None, up=None,
                     name = None,
                     upSetup = "guess",
                     extendStart = None,
                     addEndJoint = None,
                     extendEnd = None,
                     mNucleus=None,
                     upControl = None,
                     aimUpMode = None,
                     fixedSegmentLength = None,
                     follicleSegmentLength = None,
                     follicleSampleDensity = None,
                     chainMode = None,
                     requireAddEndJoint = False,
                     **kws):
        _chainMode = chainMode or kws.pop('chainMode', 'hair')
        if kws.pop('requireAddEndJoint', None):
            requireAddEndJoint = True
        addEndJoint, extendEnd = _hair_resolve_create_extend_kws(addEndJoint, extendEnd)
        if _chainMode == 'clothAttach':
            return attach_to_cloth_dynFK(self, objs=objs, name=name, **kws)
        _hairSystemMode = kws.pop('hairSystemMode', None)
        return self.chain_create_hair(
            objs=objs, fwd=fwd, up=up, name=name, upSetup=upSetup,
            extendStart=extendStart, addEndJoint=addEndJoint, extendEnd=extendEnd, mNucleus=mNucleus,
            upControl=upControl, aimUpMode=aimUpMode,
            fixedSegmentLength=fixedSegmentLength,
            follicleSegmentLength=follicleSegmentLength,
            follicleSampleDensity=follicleSampleDensity,
            requireAddEndJoint=requireAddEndJoint,
            hairSystemMode=_hairSystemMode,
            **kws)

    def chain_create_hair(self, objs = None,
                     fwd = None, up=None,
                     name = None,
                     upSetup = "guess",
                     extendStart = None,
                     addEndJoint = None,
                     extendEnd = None,
                     mNucleus=None,
                     upControl = None,
                     aimUpMode = None,
                     fixedSegmentLength = None,
                     follicleSegmentLength = None,
                     follicleSampleDensity = None,
                     requireAddEndJoint = False,
                     advancedTwist = None,
                     hairSystemMode = None,
                     **kws):
        
        _str_func = 'chain_create_hair'
        _hairSystemMode = hairSystemMode if hairSystemMode is not None else kws.pop('hairSystemMode', 'default')
        log.info(cgmGEN.logString_msg(
            _str_func, 'entry hairSystemMode={0!r} (reload dynamic_utils if missing multi-hair logs)'.format(
                _hairSystemMode)))
        
        if not objs:
            _sel = mc.ls(sl=1)
            if _sel:objs = _sel
        
        ml = cgmMeta.asMeta( objs, noneValid = True )
        ml_baseTargets = copy.copy(ml)
        
        if not ml:
            return log.warning("No objects passed. Unable to chain_create")
            
        if not name:
            name = ml[-1].p_nameBase
        name = chain_resolve_unique_name(self, name)

        #Make our sub group...
        mGrp = self.doCreateAt(setClass=1)
        mGrp.p_parent = self
        mGrp.rename("chain_{0}_grp".format(name))
        mGrp.dagLock()
        chain_connect_to_setup(self, mGrp)

        #holders and dat...
        ml_targets = []
        ml_posLocs = []
        ml_aim_locs = []
        
        _requireAddEndJoint = bool(requireAddEndJoint or kws.pop('requireAddEndJoint', False))
        
        fwd = fwd or self.fwd
        up = up or self.up
        upSetup = upSetup or self.upSetup
        if extendStart is None:
            extendStart = self.extendStart
        addEndJoint, extendEnd = _hair_resolve_create_extend_kws(addEndJoint, extendEnd)
        if addEndJoint is None:
            addEndJoint = getattr(self, 'addEndJoint', False)
        if extendEnd is None:
            extendEnd = getattr(self, 'extendEnd', False)
        if advancedTwist is None:
            advancedTwist = getattr(self, 'advancedTwist', False)
        if _requireAddEndJoint and not _hair_add_end_joint_active(addEndJoint):
            try:
                addEndJoint = float(getattr(self, 'addEndJoint', None) or 2.0)
            except (TypeError, ValueError):
                addEndJoint = 2.0
        log.info(cgmGEN.logString_msg(
            _str_func,
            'addEndJoint={0!r} active={1} extendEnd={2!r} curveActive={3} requireAddEndJoint={4} targets={5}'.format(
                addEndJoint,
                _hair_add_end_joint_active(addEndJoint),
                extendEnd,
                _hair_curve_extend_end_active(extendEnd),
                _requireAddEndJoint,
                len(ml_baseTargets))))
        upControl = upControl or self.upControl
        aimUpMode = aimUpMode or self.aimUpMode
        if fixedSegmentLength is None:
            fixedSegmentLength = self.fixedSegmentLength
        if follicleSegmentLength is None:
            follicleSegmentLength = self.follicleSegmentLength
        if follicleSampleDensity is None:
            follicleSampleDensity = getattr(self, 'follicleSampleDensity', FOLLICLE_DEFAULT_SAMPLE_DENSITY)
        try:
            follicleSampleDensity = float(follicleSampleDensity)
        except (TypeError, ValueError):
            follicleSampleDensity = FOLLICLE_DEFAULT_SAMPLE_DENSITY

        _hairFollowMode = _resolve_hair_follow_mode(kws.pop('hairFollowMode', None), self, kws)
        try:
            _inCurveDegree = int(kws.pop('inCurveDegree', None) or getattr(self, 'inCurveDegree', 1))
        except (TypeError, ValueError):
            _inCurveDegree = 1
        try:
            _outCurveDegree = int(kws.pop('outCurveDegree', None) or getattr(self, 'outCurveDegree', 2))
        except (TypeError, ValueError):
            _outCurveDegree = 2
        _inCurveDegree = MATHUTILS.Clamp(_inCurveDegree, 1, 3)
        _outCurveDegree = MATHUTILS.Clamp(_outCurveDegree, 1, 3)
        _use_follicle_input = (_hairFollowMode == HAIR_FOLLOW_MODE_SPLINE)
        
        #fwdAxis = simpleAxis(fwd)
        #upAxis = simpleAxis(up)

        fwdAxis = TRANS.closestAxisTowardObj_get(ml[0], ml[1])
        upAxis = TRANS.crossAxis_get(fwdAxis)

        mGrp.doStore('fwd', fwdAxis.p_string)
        mGrp.doStore('up', upAxis.p_string)

        #Curve positions...
        l_pos = []
        
        if upSetup == 'manual':
            if len(ml) < 2:
                log.debug(cgmGEN.logString_msg(_str_func, 'Single count. Adding extra handle.'))
                mLoc = ml[0].doLoc()
                mLoc.rename("chain_{0}_end_loc".format(name))
                _size = DIST.get_bb_size(ml[0],True,'max')
                mLoc.p_position = ml[0].getPositionByAxisDistance(fwdAxis.p_string,_size)
                ml.append(mLoc)
                mLoc.p_parent = mGrp
            
            for obj in ml:
                l_pos.append(obj.p_position)

        else:
            log.debug(cgmGEN.logString_msg(_str_func, 'Resolving aim'))
            if len(ml) < 2:
                return log.error(cgmGEN.logString_msg(_str_func, 'Single count. Must use manual upSetup and aim/up args'))
            
            for obj in ml_baseTargets:
                l_pos.append(obj.p_position)

        log.debug(cgmGEN.logString_sub(_str_func, 'skin setup'))
        ml_sim = _hair_build_sim_joint_chain_from_targets(ml_baseTargets, name)

        l_pos, ml_sim = _hair_ensure_add_end_joint_chain(
            mGrp, ml_sim, ml_baseTargets, l_pos, addEndJoint, upSetup, fwdAxis, name,
            extendEnd=extendEnd, extendStart=extendStart)

        ml_sim = _hair_rename_sim_joint_chain(ml_sim, name)
        ml_sim = _hair_reparent_sim_chain_ordered(ml_sim)

        log.info(cgmGEN.logString_msg(
            _str_func,
            'after ensure: simJoints={0} l_pos CVs={1} addEndJoint={2!r} extendEnd={3!r}'.format(
                len(_hair_normalize_sim_chain(ml_sim)), len(l_pos), addEndJoint, extendEnd)))

        _hair_validate_add_end_joint_count(
            ml_sim, ml_baseTargets, addEndJoint, l_pos=l_pos, required=_requireAddEndJoint,
            context='{0} | after ensure (pre inCurve)'.format(_str_func))

        crv = _create_hair_incurve(l_pos, name, _inCurveDegree)
        mInCrv = cgmMeta.asMeta(crv)
        mInCrv.rename("{0}_inCrv".format(name))
        mGrp.connectChildNode(mInCrv.mNode,'mInCrv')
        mInCrv.p_parent = mGrp

        ml_sim[0].p_parent = mGrp

        mSkinCluster, ml_sim = _hair_incurve_skin_bind(
            ml_sim, mInCrv, '{0}_skinCluster'.format(name), l_pos=l_pos)

        _l_jointPos = [mObj.p_position for mObj in ml]
        _l_paramFrac = CURVES.polyline_length_fractions(_l_jointPos)

        # makeCurvesDynamic expects the inCurve at world (not under chain grp)
        mc.parent(mInCrv.mNode, world=True)

        mc.select(cl=True)

        # make the dynamic setup
        log.debug(cgmGEN.logString_sub(_str_func,'dyn setup'))
        b_existing = False
        b_existing_nucleus = False
        _b_precreated_hair_system = False

        log.info(cgmGEN.logString_msg(
            _str_func, 'hairSystemMode={0!r} registered={1}'.format(
                _hairSystemMode, len(hair_system_list_registered(self)))))

        if self.useExistingNucleus or mNucleus:
            mNucleus = self.get_nucleus(mNucleus)
            if mNucleus:
                b_existing_nucleus = True
                log.info(cgmGEN.logString_msg(_str_func,'Using existing nucleus: {0}'.format(mNucleus.mNode)))
                self.connectChildNode(mNucleus.mNode,'mNucleus')

        _mode_low = (_hairSystemMode or 'default').strip().lower()
        _wants_new_hair_system = _mode_low in ('new', 'create')
        if _wants_new_hair_system and _setup_has_existing_hair_sim(self):
            _dag_name = '{0}_{1}_hairSys'.format(self.baseName, name)
            mHairSys = _hair_system_create_empty(self, _dag_name)
            if mHairSys:
                b_existing = True
                _b_precreated_hair_system = True
                log.info(cgmGEN.logString_msg(
                    _str_func, 'pre-created empty hairSystem for MCD: {0}'.format(mHairSys.mNode)))
            else:
                log.warning(cgmGEN.logString_msg(
                    _str_func, 'pre-create hairSystem failed — falling back to resolve_for_create'))
                mHairSys, b_existing = hair_system_resolve_for_create(self, _hairSystemMode, chainName=name)
        elif _wants_new_hair_system:
            mHairSys, b_existing = None, False
        else:
            mHairSys, b_existing = hair_system_resolve_for_create(self, _hairSystemMode, chainName=name)

        if mHairSys and b_existing:
            mHairSysDag = mHairSys.getTransform(asMeta=1)
            log.info(cgmGEN.logString_msg(
                _str_func, 'Using hairSystem for MCD: {0} (mode={1!r} precreated={2})'.format(
                    mHairSys.mNode, _hairSystemMode, _b_precreated_hair_system)))
            mc.select(mHairSysDag.mNode, add=True)
        else:
            mHairSys = None
        
        mc.select(mInCrv.mNode, add=True)
        mel.eval('makeCurvesDynamic 2 { "0", "0", "1", "1", "0" }')

        # get relevant nodes
        _follicleNode = _resolve_follicle_from_incurve(mInCrv.mNode)
        if not _follicleNode:
            return log.error(cgmGEN.logString_msg(
                _str_func, 'No follicle found after makeCurvesDynamic on {0}'.format(mInCrv.mNode)))

        mFollicle = cgmMeta.asMeta(_follicleNode)
        mFollicle.rename("{0}_foll".format(name))
        _melWrapper = (mc.listRelatives(
            _dag_str(mFollicle), parent=True, type='transform', fullPath=True) or [None])[0]
        mFollicle.p_parent = mGrp
        mFollicleShape = mFollicle.getShapes(asMeta=True)[0]
        if _melWrapper and _melWrapper not in (_dag_str(mGrp), _dag_str(self)):
            mc.delete(_melWrapper)
        
        _follicle = mFollicle.mNode
        mGrp.connectChildNode(mFollicle.mNode,'mFollicle','group')
        
        follicleShape = mFollicleShape.mNode#mc.listRelatives(mFollicle.mNode, shapes=True)[0]

        if _b_precreated_hair_system and mHairSys:
            _wired_hs = _follicle_hair_system_shape_from_follicle(follicleShape)
            if _wired_hs != mHairSys.mNode:
                log.info(cgmGEN.logString_msg(
                    _str_func, 'MCD used {0} — rewire follicle to {1}'.format(
                        _wired_hs, mHairSys.mNode)))
                _rewire_follicle_hair_system(follicleShape, mHairSys.mNode)

        mInCrv = _consolidate_hair_incurve_after_mcd(
            mInCrv, mFollicleShape, mGrp, name, ml_sim, l_pos, mSkinCluster,
            fixedSegmentLength=fixedSegmentLength,
            follicleSegmentLength=follicleSegmentLength,
            inCurveDegree=_inCurveDegree,
            use_follicle_input_curve=_use_follicle_input,
            sampleDensity=follicleSampleDensity)

        _hairSystem = mc.listRelatives( mc.listConnections('%s.currentPosition' % follicleShape)[0],
                                        shapes=True)[0]
        _follicle_hs = _follicle_hair_system_shape_from_follicle(follicleShape) or _hairSystem
        if _b_precreated_hair_system and mHairSys and _follicle_hs != mHairSys.mNode:
            log.warning(cgmGEN.logString_msg(
                _str_func,
                'Follicle wired to {0} not pre-created {1} — try Rebuild Chain'.format(
                    _follicle_hs, mHairSys.mNode)))
        if not b_existing:
            mHairSys = cgmMeta.asMeta(_hairSystem)
            mHairSysDag = mHairSys.getTransform(asMeta=1)
            mHairSysDag.rename('{0}_{1}_hairSys'.format(self.baseName, name))
            hair_system_register(
                self, mHairSys, setDefault=hair_system_get_default(self) is None)
            _hairSystem = mHairSys.mNode
        elif not mHairSys:
            mHairSys = cgmMeta.asMeta(_hairSystem)
        elif _follicle_hs:
            mHairSys = cgmMeta.asMeta(_follicle_hs)
            _hairSystem = mHairSys.mNode

        if _hairFollowMode == HAIR_FOLLOW_MODE_LEGACY:
            outCurve = mc.listConnections('%s.outCurve' % _follicle)[0]
            mCrv = cgmMeta.asMeta(outCurve)
            _legacyOutParent = (mc.listRelatives(
                _dag_str(mCrv), parent=True, type='transform', fullPath=True) or [None])[0]

            outCurveShape = mc.listRelatives(mCrv.mNode, shapes=True)[0]
            mCrv.p_parent = mGrp.mNode
            
            if _legacyOutParent:
                mc.delete(_legacyOutParent)

            _inShape = mc.listRelatives(
                mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
            _finalize_hair_outcurve_rest(
                follicleShape, _hairSystem, _inShape, outCurveShape,
                fixedSegmentLength=fixedSegmentLength,
                follicleSegmentLength=follicleSegmentLength,
                l_positions=l_pos,
                sampleDensity=follicleSampleDensity)
        else:
            mCrv, _outCurveShape = _prepare_spline_hair_outcurve(
                mFollicle, mFollicleShape, mHairSys, name, _outCurveDegree)
            mCrv.p_parent = mGrp
            _inShape = mc.listRelatives(
                mInCrv.mNode, shapes=True, type='nurbsCurve', fullPath=True)[0]
            _finalize_hair_outcurve_rest(
                follicleShape, _hairSystem, _inShape, _outCurveShape,
                fixedSegmentLength=fixedSegmentLength,
                follicleSegmentLength=follicleSegmentLength,
                l_positions=l_pos,
                sampleDensity=follicleSampleDensity)

        _warn_hair_system_extra_segments(_hairSystem)

        _nucleus = mc.listConnections( '%s.currentState' % mHairSys.mNode )[0]
        
        if not b_existing_nucleus:
            mNucleus = cgmMeta.asMeta(_nucleus)
            mNucleus.rename("cgmDynFK_nucleus")            
            #self.connectChildNode(mNucleus.mNode,'mNucleus','owner')
            self.connectChildNode(mNucleus.mNode,'mNucleus')
            
            if self.startFrame is not None:
                mNucleus.startFrame = self.startFrame
        else:
            #Because maya is crappy we gotta manually wire the existing nucleus
            ##startFrame out to startFrame in
            ##outputObjects[x] - nextState
            ##shape.currentState>inputActive[x]
            ##shape.startState>inputActiveStart[x]
            if cgmMeta.asMeta(_nucleus).mNode != mNucleus.mNode:
                mc.delete(_nucleus)

            _useNucleus = mNucleus.mNode

            """
            _useIdx = ATTR.get_nextCompoundIndex(mNucleus.mNode,'outputObjects')
            log.info("useIdx: {0}".format(_useIdx))
            ATTR.connect('{0}.outputObjects[{1}]'.format(_useNucleus,_useIdx),'{0}.nextState'.format(_hairSystem))
            ATTR.connect('{0}.currentState'.format(_hairSystem),'{0}.inputActive[{1}]'.format(_useNucleus,_useIdx))
            ATTR.connect('{0}.startState'.format(_hairSystem),'{0}.inputActiveStart[{1}]'.format(_useNucleus,_useIdx))"""            
            
            
        if _hairFollowMode != HAIR_FOLLOW_MODE_LEGACY:
            _mOutLive = _follicle_outcurve_meta(mFollicle)
            if _mOutLive:
                mCrv = _mOutLive

        mGrp.connectChildNode(mCrv.mNode, 'mOutCrv', 'group')

        _targetNode = _dag_str(ml[0])
        _follDriver = (mc.listRelatives(
            _targetNode, parent=True, type='transform', fullPath=True) or [None])[0]
        if not _follDriver:
            ml[0].doGroup(
                1, 1, asMeta=True, typeModifier='dynFKParent', setClass='cgmObject')
            _follDriver = (mc.listRelatives(
                _targetNode, parent=True, type='transform', fullPath=True) or [None])[0]
        if not _follDriver:
            raise ValueError(cgmGEN.logString_msg(
                _str_func, 'No parent transform to drive follicle for {0}'.format(_targetNode)))

        # set default properties
        mFollicleShape.pointLock = 1
        #mc.setAttr( '%s.pointLock' % follicleShape, 1 )
        ml_sim[0].p_parent = mFollicle
        mInCrv.p_parent = mGrp
        mc.parentConstraint(_follDriver, _dag_str(mFollicle), mo=True)
        
        if _hairFollowMode == HAIR_FOLLOW_MODE_LEGACY:
            _build_hair_chain_follow(
                mGrp, outCurveShape, ml, ml_baseTargets, ml_sim, name,
                fwdAxis, upAxis, _l_paramFrac=_l_paramFrac,
                upSetup=upSetup, upControl=upControl, aimUpMode=aimUpMode,
                addEndJoint=addEndJoint, extendEnd=extendEnd)
            mCrv.rename("{0}_outCrv".format(name))
            mCrvParent = mCrv.getParent(asMeta=1)
            mCrvParent.p_parent = mGrp
        else:
            _build_hair_chain_follow_spline(
                mGrp, mCrv, ml, ml_sim, name, fwdAxis=fwdAxis, upAxis=upAxis,
                mFollicle=mFollicle, ml_baseTargets=ml_baseTargets,
                advancedTwist=advancedTwist)
            mCrv.rename("{0}_outCrv".format(name))
        
        mGrp.msgList_connect('mTargets',ml)
        mGrp.msgList_connect('mBaseTargets',ml_baseTargets)
        mGrp.msgList_connect('mObjJointChain', ml_sim)
        mGrp.doStore('cgmName', name)
        mGrp.doStore('chainMode', 'hair')
        mGrp.doStore('hairFollowMode', _hairFollowMode)
        mGrp.doStore('inCurveDegree', _inCurveDegree)
        mGrp.doStore('outCurveDegree', _outCurveDegree)
        mGrp.doStore('fixedSegmentLength', bool(fixedSegmentLength))
        if fixedSegmentLength:
            mGrp.doStore('follicleSegmentLength', follicleSegmentLength)
        else:
            mGrp.doStore('follicleSampleDensity', follicleSampleDensity)
        self.follicleSampleDensity = follicleSampleDensity
        _store_hair_chain_follow_metadata(
            mGrp, aimUpMode, addEndJoint, extendStart, upControl, upSetup, extendEnd=extendEnd,
            advancedTwist=advancedTwist)

        _hair_validate_add_end_joint_count(
            ml_sim, ml_baseTargets, addEndJoint, l_pos=l_pos, required=_requireAddEndJoint,
            context='chain_create_hair {0}'.format(mGrp.p_nameBase))

        mGrp.connectChildNode(mHairSys.mNode, 'mHairSysShape', 'group')
        hair_system_register(self, mHairSys, setDefault=False)

        mNucleus.doConnectOut('startFrame',"{0}.startFrame".format(mHairSys.mNode))
        
    def report(self):
        _d = {'up':self.up,
              'fwd':self.fwd,
              'baseName':self.baseName}
        
        pprint.pprint(_d)
        pprint.pprint(self.get_dat())
        
    def get_dat(self):
        import cgm.core.lib.nCloth_utils as NCLOTH

        mCloth = get_mapped_cloth(self)
        mClothOutMesh = None
        if mCloth:
            _outXform = NCLOTH.get_out_mesh_transform(mCloth.mNode, noneValid=True)
            if _outXform:
                mClothOutMesh = cgmMeta.asMeta(_outXform)

        for mGrp in self.msgList_get('chain') or []:
            hair_system_backfill_chain(mGrp, self)

        _res = {'mNucleus':self.getMessageAsMeta('mNucleus'),
                'mHairSysDag':self.getMessageAsMeta('mHairSysDag'),
                'mHairSysShape':self.getMessageAsMeta('mHairSysShape'),
                'mHairSystems': hair_system_list_registered(self),
                'mCloth': mCloth,
                'mClothOutMesh': mClothOutMesh,
                'chains':{},
                }
        
        ml_chains = self.msgList_get('chain')
        for i,mGrp in enumerate(ml_chains):
            _chainMode = getattr(mGrp, 'chainMode', None) or 'hair'
            _d = {'mGrp':mGrp,
                  'chainMode': _chainMode,
                  'mFollicle':mGrp.getMessageAsMeta('mFollicle'),
                  'mInCrv':mGrp.getMessageAsMeta('mInCrv'),
                  'mOutCrv':mGrp.getMessageAsMeta('mOutCrv'),
                  'mMeshFollicles': mGrp.msgList_get('mMeshFollicles'),
                  'mRivets': mGrp.msgList_get('mRivets'),
                  'mUvPins': mGrp.msgList_get('mUvPins'),
                  }
            if _chainMode == 'clothAttach':
                _d['surfaceTrack'] = getattr(mGrp, 'surfaceTrack', None) or 'follicle'

            for lnk in 'mLocs','mAims','mParents','mTargets', 'mObjJointChain','mDrivenJointChain':
                _d[lnk] = mGrp.msgList_get(lnk)
            _d['mIkHandle'] = mGrp.getMessageAsMeta('mIkHandle')
            if _chainMode == 'hair':
                _d['mHairSysShape'] = hair_system_resolve_for_chain(mGrp, self, backfill=False)
                _d['hairFollowMode'] = _get_chain_hair_follow_mode(mGrp)
                if mGrp.hasAttr('inCurveDegree'):
                    _d['inCurveDegree'] = mGrp.inCurveDegree
                if mGrp.hasAttr('outCurveDegree'):
                    _d['outCurveDegree'] = mGrp.outCurveDegree
                _hair_settings = _get_hair_chain_follow_settings(mGrp)
                _ml_base = mGrp.msgList_get('mBaseTargets') or _d.get('mTargets')
                _hair_validate_add_end_joint_count(
                    _d.get('mObjJointChain'), _ml_base, _hair_settings.get('addEndJoint'),
                    context='get_dat chain {0}'.format(i))
            _res['chains'][i] = _d
        
        #pprint.pprint(_res)
        return _res
    
    def toggle(self,arg):
        _str_func = 'toggle'
        log.info("|{0}| >> {1}".format(_str_func,arg))
        
        mNucleus=self.getMessageAsMeta('mNucleus')
        if mNucleus:
            mNucleus.enable = arg
            
        ml_hair = hair_system_list_registered(self)
        if not ml_hair:
            mHairSysShape = self.getMessageAsMeta('mHairSysShape')
            if mHairSysShape:
                ml_hair = [mHairSysShape]
        for mHairSysShape in ml_hair:
            if not mHairSysShape:
                continue
            if arg:
                mHairSysShape.simulationMethod = 3
            else:
                mHairSysShape.simulationMethod = 0
                
        if arg:
            log.warning("|{0}| >> Playback rate set to every frame".format(_str_func))
            mc.playbackOptions(e=True, playbackSpeed = 0, maxPlaybackSpeed = 0)
        else:
            mc.playbackOptions(e=True, playbackSpeed = 1, maxPlaybackSpeed = 0)
            #playbackOptions -e -playbackSpeed 0 -maxPlaybackSpeed 0;
            
        
    def profile_load(self,arg='default',clean=True):
        mNucleus=self.getMessageAsMeta('mNucleus')
        mHairSysShape=self.getMessageAsMeta('mHairSysShape')
        if not mNucleus and mHairSysShape:
            return log.warning("Nucleus and hairShape required for profile load")
        
        
        profile_load(mNucleus,arg,clean=clean)
        profile_load(mHairSysShape,arg,clean=clean)
        
        
        
        return 
        #reload(dynFKPresets)
        _d = dynFKPresets.d_chain.get(arg)
        if not _d:
            return log.warning("Profile has no data: {0}".format(arg))
        
        d_n = _d.get('n') or {}
        d_hs = _d.get('hs') or {}
        
        pprint.pprint(_d)
        _nucleus = mNucleus.mNode
        for a,v in list(d_n.items()):
            log.debug("Nucleus || {0} | {1}".format(a,v))
            try:
                mNucleus.__setattr__(a,v)
            except Exception as err:
                log.warning("Nucleus | Failed to set: {0} | {1} | {2}".format(a,v,err))
                
        for a,v in list(d_hs.items()):
            log.debug("mHairSys || {0} | {1}".format(a,v))            
            try:
                mHairSysShape.__setattr__(a,v)
            except Exception as err:
                log.warning("mHairSys | Failed to set: {0} | {1} | {2}".format(a,v,err))
        return True
       
    def get_chains(self, idx=None):
        chains = self.msgList_get('chain')
        if idx:
            chains = [chains[idx]]

        return chains

    def targets_connect(self,idx=None):
        """
        Connect follow locs to rig targets at the frame before sim start:
        scrub to startFrame - 1, snap locs to target pose, set matchTarget, parentConstraint.
        """
        _str_func = 'targets_connect'
        _savedTime = mc.currentTime(q=True)
        try:
            for chain in self.get_chains(idx):
                _chainMode = getattr(chain, 'chainMode', None) or 'hair'
                if _chainMode == 'hair':
                    _startFrame = _resolve_hair_start_frame(self, mGrp=chain)
                else:
                    _startFrame = _resolve_hair_start_frame(self)
                _connectFrame = _startFrame - 1
                mc.currentTime(_connectFrame, edit=True)
                ml_locs = chain.msgList_get('mLocs') or []
                ml_targets = chain.msgList_get('mTargets') or []
                for i, mObj in enumerate(ml_targets):
                    if i >= len(ml_locs):
                        continue
                    mLoc = ml_locs[i]
                    _constraints = mObj.getConstraintsTo()
                    if _constraints:
                        mc.delete(_constraints)
                    SNAP.go(mLoc.mNode, mObj.mNode, True, True)
                    SNAP.matchTarget_set(mObj.mNode, mLoc.mNode)
                    mc.parentConstraint(mLoc.mNode, mObj.mNode)
                log.info(cgmGEN.logString_msg(
                    _str_func, 'chain {0} frame {1} (startFrame {2} - 1)'.format(
                        chain.p_nameBase, _connectFrame, _startFrame)))
        finally:
            mc.currentTime(_savedTime, edit=True)
    def targets_disconnect(self,idx=None):
        for chain in self.get_chains(idx):
            for i,mObj in enumerate(chain.msgList_get('mTargets')):
                _buffer = mObj.getConstraintsTo()

                if _buffer:
                    mc.delete(_buffer)

    def bake_nodes(self, mObjs, startFrame, endFrame, simulation=True):
        """Bake to keys (same pattern as bakeAndPrep / zoo dynamicChain)."""
        _str_func = 'bake_nodes'
        ml = cgmMeta.asMeta(mObjs, noneValid=True)
        if not ml:
            return log.warning(cgmGEN.logString_msg(_str_func, 'No objects'))

        _nodes = [mObj.mNode for mObj in ml]
        cgmGEN.playback_stop()

        log.info(cgmGEN.logString_msg(
            _str_func, '{0} | frames {1}-{2} | simulation={3}'.format(
                _nodes, startFrame, endFrame, simulation)))
        mc.bakeResults(
            _nodes,
            simulation=simulation,
            t=(startFrame, endFrame),
            sampleBy=1,
            disableImplicitControl=True,
            preserveOutsideKeys=True,
            sparseAnimCurveBake=True,
            minimizeRotation=True,
        )

        if simulation:
            _baked = {mObj.mNode for mObj in ml}
            for idx, chain in enumerate(self.msgList_get('chain')):
                ml_targets = chain.msgList_get('mTargets') or []
                if any(t.mNode in _baked for t in ml_targets):
                    self.targets_disconnect(idx)

        return True
    
    def targets_select(self,idx=None):
        ml= []
        for chain in self.get_chains(idx):
            for i,mObj in enumerate(chain.msgList_get('mTargets')):
                if 'loc' not in mObj.mNode:
                    ml.append(mObj)
        
        mc.select([mObj.mNode for mObj in ml])
        return ml

                
    def delete(self):
        pass


def _cut_input_joint_keys_in_range(nodes, startFrame, endFrame):
    """Clear TR keys in bake window so re-bakes stay fast (Bake Input only)."""
    _start = int(startFrame)
    _end = int(endFrame)
    for _node in nodes:
        try:
            mc.cutKey(
                _node,
                time=(_start, _end),
                attribute=_BAKE_INPUT_TR_ATTRS,
                option='keys',
                clear=True)
        except Exception:
            pass


def _input_bake_dg_isolate_begin(mSetup):
    """Pause nucleus/hair solve and viewport refresh during one input bakeResults."""
    _state = {'nucleus_enable': None, 'hair_sim_method': [], 'refresh_suspend': None}
    mNucleus = mSetup.getMessageAsMeta('mNucleus')
    if mNucleus and mc.objExists(mNucleus.mNode):
        if mc.attributeQuery('enable', node=mNucleus.mNode, exists=True):
            _state['nucleus_enable'] = (
                mNucleus.mNode, mc.getAttr('{0}.enable'.format(mNucleus.mNode)))
            mc.setAttr('{0}.enable'.format(mNucleus.mNode), 0)
    ml_hair = hair_system_list_registered(mSetup)
    if not ml_hair:
        mHairSysShape = mSetup.getMessageAsMeta('mHairSysShape')
        if mHairSysShape:
            ml_hair = [mHairSysShape]
    for mHairSysShape in ml_hair or []:
        if not mHairSysShape or not mc.objExists(mHairSysShape.mNode):
            continue
        if mc.attributeQuery('simulationMethod', node=mHairSysShape.mNode, exists=True):
            _plug = '{0}.simulationMethod'.format(mHairSysShape.mNode)
            _state['hair_sim_method'].append((mHairSysShape.mNode, mc.getAttr(_plug)))
            mc.setAttr(_plug, 0)
    try:
        _state['refresh_suspend'] = mc.refresh(query=True, suspend=True)
        mc.refresh(suspend=True)
    except Exception:
        _state['refresh_suspend'] = None
    return _state


def _input_bake_dg_isolate_end(isolate_state):
    if not isolate_state:
        return
    for _node, _val in isolate_state.get('hair_sim_method') or []:
        try:
            mc.setAttr('{0}.simulationMethod'.format(_node), _val)
        except Exception:
            pass
    _nucleus = isolate_state.get('nucleus_enable')
    if _nucleus:
        try:
            mc.setAttr('{0}.enable'.format(_nucleus[0]), _nucleus[1])
        except Exception:
            pass
    _refresh_su = isolate_state.get('refresh_suspend')
    if _refresh_su is not None:
        try:
            mc.refresh(suspend=_refresh_su)
        except Exception:
            mc.refresh(suspend=False)


def _input_bake_progress_step(progressBar, status, step=1):
    if not progressBar:
        return
    try:
        mc.progressBar(progressBar, edit=True, status=status, step=step)
        mc.refresh()
    except Exception:
        pass


def chain_bake_input_from_targets(mDynFK, startFrame, endFrame, idx=None):
    """
    Bake rig target motion onto input joints (mObjJointChain) for inCurve authoring.

    Auto-disconnects loc→target when needed. Temporary target→input parentConstraints,
    one bake_nodes batch (simulation=False), then delete temps. Does not auto-reconnect.
    """
    global _bake_input_run_counter
    _str_func = 'chain_bake_input_from_targets'
    mSetup = cgmMeta.validateObjArg(mDynFK, noneValid=True)
    if not mSetup or getattr(mSetup, 'mClass', None) != 'cgmDynFK':
        return log.error(cgmGEN.logString_msg(_str_func, 'Owner is not a cgmDynFK setup'))

    ml_chains = mSetup.msgList_get('chain') or []
    if idx is not None:
        if idx >= len(ml_chains):
            return log.warning(cgmGEN.logString_msg(_str_func, 'No chain at idx {0}'.format(idx)))
        ml_chains = [ml_chains[idx]]

    _chains_to_bake = []
    for mGrp in ml_chains:
        _chainMode = getattr(mGrp, 'chainMode', None) or 'hair'
        if _chainMode == 'clothAttach':
            continue
        if _hair_chain_integrity_missing(mGrp):
            return log.error(cgmGEN.logString_msg(
                _str_func, 'Broken chain {0} — fix or delete before Bake Input'.format(
                    mGrp.p_nameBase)))
        ml_driver = mGrp.msgList_get('mTargets') or []
        ml_input = _hair_normalize_sim_chain(mGrp.msgList_get('mObjJointChain'))
        if not ml_driver or not ml_input:
            return log.error(cgmGEN.logString_msg(
                _str_func, 'Chain {0} missing targets or input joints'.format(mGrp.p_nameBase)))
        _chains_to_bake.append((mGrp, ml_driver, ml_input))

    if not _chains_to_bake:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No hair chains to bake'))

    _bake_input_run_counter += 1
    _start = int(startFrame)
    _end = int(endFrame)
    log.info(cgmGEN.logString_msg(
        _str_func,
        'run={0} | chains={1} | frames {2}-{3}'.format(
            _bake_input_run_counter, len(_chains_to_bake), _start, _end)))

    _disconnected_chain_idxs = []
    for mGrp, _ml_driver, _ml_input in _chains_to_bake:
        if not _chain_targets_connected(mGrp):
            continue
        _chain_idx = mSetup.msgList_index('chain', mGrp.mNode)
        if _chain_idx is None:
            continue
        mSetup.targets_disconnect(_chain_idx)
        if _chain_idx not in _disconnected_chain_idxs:
            _disconnected_chain_idxs.append(_chain_idx)
    if _disconnected_chain_idxs:
        log.info(cgmGEN.logString_msg(
            _str_func, 'disconnected loc→target on chain idx {0}'.format(
                _disconnected_chain_idxs)))

    _progressBar = None
    try:
        _progressBar = CGMUI.doStartMayaProgressBar(
            2,
            'Bake Input | frames {0}-{1}'.format(_start, _end),
            interruptableState=True)
    except Exception:
        _progressBar = None

    _ml_bake = []
    _all_constraints = []
    _isolate_state = None
    _t_constraints = 0.0
    _t_bake = 0.0
    try:
        _t0 = time.time()
        for mGrp, ml_driver, ml_input in _chains_to_bake:
            _pair_count = min(len(ml_driver), len(ml_input))
            _skipped = max(0, len(ml_input) - _pair_count)
            log.info(cgmGEN.logString_msg(
                _str_func,
                '{0} | pairs={1} | input joints without target={2}'.format(
                    mGrp.p_nameBase, _pair_count, _skipped)))
            for i in range(_pair_count):
                _c = mc.parentConstraint(
                    ml_driver[i].mNode, ml_input[i].mNode, maintainOffset=False)
                if _c:
                    if isinstance(_c, (list, tuple)):
                        _all_constraints.extend(_c)
                    else:
                        _all_constraints.append(_c)
            _ml_bake.extend(ml_input)
        _t_constraints = time.time() - _t0

        _nodes = [mObj.mNode for mObj in _ml_bake]
        _cut_input_joint_keys_in_range(_nodes, _start, _end)

        _input_bake_progress_step(
            _progressBar, 'Bake Input: baking {0} joint(s)...'.format(len(_ml_bake)))

        _isolate_state = _input_bake_dg_isolate_begin(mSetup)
        _t_bake_start = time.time()
        try:
            mSetup.bake_nodes(_ml_bake, _start, _end, simulation=False)
        finally:
            _input_bake_dg_isolate_end(_isolate_state)
            _isolate_state = None
        _t_bake = time.time() - _t_bake_start

        _input_bake_progress_step(_progressBar, 'Bake Input: done', step=1)
    finally:
        if _isolate_state:
            _input_bake_dg_isolate_end(_isolate_state)
        if _all_constraints:
            mc.delete(_all_constraints)
        if _progressBar:
            CGMUI.doEndMayaProgressBar(_progressBar)

    log.info(cgmGEN.logString_msg(
        _str_func,
        'run={0} | constraints {1:.2f}s | bakeResults {2:.2f}s | joints={3}'.format(
            _bake_input_run_counter, _t_constraints, _t_bake, len(_ml_bake))))

    return True


#Profiles ========================================================================================
d_shortHand = {'nucleus':'n',
               'hairSystem':'hs'}
l_ignore = ['currentTime','startFrame']

# hairSystem: feel (.cgmSimHairDat) vs shape (.cgmSimHairShapeDat) vs scene-structural (never in hair dats)
d_attrMap_hs_shape_groups = ('base', 'clumpAndHairShape')
d_attrMap_hs_feel_groups = ('dynamicProperties', 'forces')
# Structural within feel groups — capture/apply skip (solver mode / length / master weight)
l_skipHairFeelAttrs = frozenset([
    'bendModel',
    'restLengthScale',
    'bendAnisotropy',
    'dynamicsWeight',
])
l_follicle_hairShape_attrs = (
    'sampleDensity', 'fixedSegmentLength', 'segmentLength', 'degree', 'pointLock',
)

d_attrMap = {'n':{'gravity':['gravity','gravityDirection',],
                  'air':['airDensity','windSpeed','windDirection','windNoise'],
                  'groundPlane':['usePlane','planeOrigin','planeNormal',
                                 'planeBounce','planeFriction','planeStickiness'],
                  'solverAttributes':['subSteps','maxCollisionIterations',
                                      'collisionLayerRange', 'timingOutput']},
             'hs':{'base':['simulationMethod','displayQuality'],
                   'clumpAndHairShape':['hairsPerClump','subSegments','thinning','clumpTwist','bendFollow',
                                        'clumpWidth','hairWidth', 'clumpWidthScale', 'hairWidthScale','clumpInterpolation',
                                        'curl','curlFrequency',
                                        'clumpCurl', 'clumpFlatness'],
                   'collisions':['collide','selfCollide',
                                 'collisionFlag','selfCollisionFlag',
                                 'collideStrength', 'collisionLayer','numCollideNeighbors',
                                 'collideGround','collideOverSample',
                                 'maxSelfCollisionIterations','drawCollideWidth',
                                 'maxSelfCollideIterations','collideWidthOffset','selfCollideWidthScale',
                                 'solverDisplay','bounce','friction','stickiness','staticCling'],
                   'dynamicProperties':['stretchResistance','compressionResistance','bendResistance',
                                        'bendModel', 'twistResistance', 'extraBendLinks', 'restLengthScale',
                                        'stiffnessScale', 'startCurveAttract', 'attractionDamp',
                                        'attractionScale', 'bendAnisotropy'],
                   'forces':['mass','drag','tangentialDrag','motionDrag','damp','stretchDamp', 'dynamicsWeight'],
                   'turbulance':['turbulenceStrength','turbulenceFrequency','turbulenceSpeed'],
                   'others':['detailNoise','noStretch','diffuseRand','displacementScale','groundHeight',
                             'iterations','interpolationRange','lengthFlex','stiffness','repulsion',
                             'noise','noiseFrequency','noiseMethod','valRand']}}

def _hs_attr_groups_for_scope(hs_profile_scope):
    """
    ``dynamic`` / ``feel`` — hair dat feel only (resistance + forces).
    ``shape`` — HairShape dat groups.
    ``all`` — legacy full hs (Reset → Base / Query).
    """
    _groups = d_attrMap.get('hs') or {}
    if hs_profile_scope == 'all':
        return list(_groups.keys())
    if hs_profile_scope == 'shape':
        return [g for g in d_attrMap_hs_shape_groups if g in _groups]
    # default: feel (not collisions / turbulance / others — those break tuned sims on clean seed)
    return [g for g in d_attrMap_hs_feel_groups if g in _groups]


def _hair_system_shape_attr_names():
    _names = []
    for _grp in d_attrMap_hs_shape_groups:
        _names.extend(d_attrMap.get('hs', {}).get(_grp) or [])
    return _names


def _hair_system_dynamic_attr_names():
    """Hair-feel attr names (resistance + forces), excluding structural skip list."""
    _names = []
    for _grp in _hs_attr_groups_for_scope('dynamic'):
        _names.extend(d_attrMap.get('hs', {}).get(_grp) or [])
    return [a for a in _names if a not in l_skipHairFeelAttrs]


def _normalize_compound_profile_value(value):
    """JSON compound ramps use string keys + lists — coerce for ATTR.set TdataCompound."""
    if not isinstance(value, dict):
        return value
    _out = {}
    for k, v in list(value.items()):
        try:
            _ik = int(k)
        except (TypeError, ValueError):
            _ik = k
        if isinstance(v, list):
            _out[_ik] = tuple(v)
        else:
            _out[_ik] = v
    return _out


def _base_hs_seed_for_kind(profileKind, module=dynFKPresets):
    """
    ``base.hs`` subset for clean seed.

    - ``hair`` — feel attrs only (not collide / iterations / shape)
    - ``hairShape`` — shape groups only
    - other — full ``base.hs``
    """
    _base_hs = (profile_get('base', module) or {}).get('hs') or {}
    if not _base_hs:
        return {}
    if profileKind == 'hairShape':
        _allowed = set(_hair_system_shape_attr_names())
    elif profileKind == 'hair':
        _allowed = set(_hair_system_dynamic_attr_names())
    else:
        return copy.deepcopy(_base_hs)
    _seed = {}
    for a in _allowed:
        if a not in _base_hs:
            continue
        _seed[a] = _normalize_compound_profile_value(
            copy.deepcopy(_base_hs[a]))
    return _seed


def hair_profile_filter_feel(profile):
    """
    Keep hair-feel attrs only.

    Drops HairShape keys, collision/solver structural keys, and ``l_skipHairFeelAttrs``.
    Returns (feel_profile, removed_keys).
    """
    if not profile:
        return {}, []
    _feel = set(_hair_system_dynamic_attr_names())
    _kept = {}
    _removed = []
    for k, v in list(profile.items()):
        if k in _feel:
            _kept[k] = _normalize_compound_profile_value(v)
        else:
            _removed.append(str(k))
    return _kept, _removed


def hair_profile_partition_legacy_shape(profile):
    """
    Legacy helper — prefer ``hair_profile_filter_feel`` for hair dat apply.

    Returns (feel_profile, removed_keys) via feel allowlist.
    """
    return hair_profile_filter_feel(profile)


def hair_profile_partition_shape_only(profile):
    """
    Keep HairShape keys (follicle + hairSystem shape groups); drop everything else.

    Returns (shape_profile, removed_keys).
    """
    if not profile:
        return {}, []
    _allowed = set(_hair_system_shape_attr_names()) | set(l_follicle_hairShape_attrs)
    _shape = {}
    _removed = []
    for k, v in list(profile.items()):
        if k in _allowed:
            _shape[k] = _normalize_compound_profile_value(v)
        else:
            _removed.append(str(k))
    return _shape, _removed


def _query_node_attr_dict(node, attr_names, differential=False, base_section=None, module=dynFKPresets):
    _res = {}
    _node = VALID.mNodeString(node)
    for a in attr_names:
        if a in l_ignore:
            continue
        if not mc.attributeQuery(a, node=_node, exists=True):
            continue
        try:
            _v = ATTR.get(_node, a)
        except Exception as err:
            log.error("Failed to query: {0} | {1} | {2}".format(_node, a, err))
            continue
        if _v is None or _v is False:
            continue
        _res[str(a)] = _v
    if differential and base_section:
        _d_base = profile_get('base', module) or {}
        _d_baseSet = _d_base.get(base_section) or {}
        _res_use = {}
        for k, v in list(_res.items()):
            _base_v = _d_baseSet.get(k)
            if _base_v is None or v != _base_v:
                _res_use[k] = v
        return _res_use
    return _res


def get_hair_shape_profile(mGrp, mDynFK=None, differential=True):
    """Follicle shape + hairSystem shape attrs for per-chain HairShape dat."""
    _str_func = 'get_hair_shape_profile'
    mGrp = cgmMeta.asMeta(mGrp, noneValid=True)
    if not mGrp:
        return log.warning(cgmGEN.logString_msg(_str_func, 'No chain grp'))
    _profile = {}
    mFollicle = mGrp.getMessageAsMeta('mFollicle')
    if mFollicle:
        for _shape in mFollicle.getShapes(asMeta=False) or []:
            if mc.nodeType(_shape) != 'follicle':
                continue
            _profile.update(_query_node_attr_dict(
                _shape, l_follicle_hairShape_attrs, differential=False))
    mHair = hair_system_resolve_for_chain(mGrp, mDynFK) if mDynFK else None
    if mHair:
        _hs_shape = _query_node_attr_dict(
            mHair.mNode, _hair_system_shape_attr_names(),
            differential=differential, base_section='hs')
        _profile.update(_hs_shape)
    return _profile


def get_hair_system_shape_profile(target, differential=True, module=dynFKPresets):
    """hairSystem shape groups only (for SimHairShapeDat / per-system apply)."""
    _prof = get_dat(
        target, differential=differential, module=module, hs_profile_scope='shape')
    if isinstance(_prof, dict):
        return _prof.get('hs') or {}
    return {}


def apply_hair_system_shape_profile(target, profile=None, clean=False, module=dynFKPresets):
    """Apply hairSystem shape attrs only; drops follicle + dynamic feel keys."""
    profile = copy.deepcopy(profile or {})
    if not profile:
        return 0
    _hs_profile = {
        k: v for k, v in list(profile.items())
        if k not in l_follicle_hairShape_attrs}
    _hs_profile, _removed_dyn = hair_profile_partition_shape_only(_hs_profile)
    if _removed_dyn:
        log.warning(cgmGEN.logString_msg(
            'apply_hair_system_shape_profile',
            "Dropped dynamic feel attrs from HairShape apply: {0}".format(
                ', '.join(sorted(_removed_dyn)))))
    if not _hs_profile:
        return 0
    mTar = cgmMeta.asMeta(target, noneValid=True)
    if not mTar:
        return log.error(cgmGEN.logString_msg('apply_hair_system_shape_profile', 'No target'))
    return profile_apply_section(
        mTar.mNode, _hs_profile, section='hs', clean=clean, profileKind='hairShape')


def apply_hair_shape_profile(mGrp, mDynFK=None, profile=None, clean=False):
    """Apply HairShape dat profile to follicle shape + chain hairSystem shape attrs."""
    _str_func = 'apply_hair_shape_profile'
    mGrp = cgmMeta.asMeta(mGrp, noneValid=True)
    if not mGrp:
        return log.error(cgmGEN.logString_msg(_str_func, 'No chain grp'))
    profile = copy.deepcopy(profile or {})
    if not profile:
        return 0

    _count = 0
    _follicle_keys = [k for k in list(profile.keys()) if k in l_follicle_hairShape_attrs]
    _follicle_profile = {k: profile.pop(k) for k in _follicle_keys}

    mFollicle = mGrp.getMessageAsMeta('mFollicle')
    if mFollicle and _follicle_profile:
        for _shape in mFollicle.getShapes(asMeta=False) or []:
            if mc.nodeType(_shape) != 'follicle':
                continue
            _c, _ch = _apply_profile_attr_dict(
                _shape, _follicle_profile,
                log_name=_str_func, node_type='follicle')
            _count += _c

    mHair = hair_system_resolve_for_chain(mGrp, mDynFK) if mDynFK else None
    if mHair and profile:
        _count += apply_hair_system_shape_profile(
            mHair.mNode, profile, clean=clean)
    log.info(cgmGEN.logString_msg(_str_func, '{0} | {1} attrs'.format(mGrp.p_nameBase, _count)))
    return _count


def get_dat(target=None, differential=False, module=dynFKPresets, hs_profile_scope='dynamic'):
    _str_func = 'get_dat'
    mTar = cgmMeta.asMeta(target, noneValid = True)
    if not mTar:
        return log.error(cgmGEN.logString_msg(_str_func, "No valid target"))
    
    _type = mTar.getMayaType()
    _key = d_shortHand.get(_type,_type)    
    log.info(cgmGEN.logString_msg(_str_func,"mTar: {0} | {1}".format(_type, mTar)))
    
    #_d = ATTR.get_attrsByTypeDict(mTar.mNode)
    #pprint.pprint(_d)
    _res = {}
    _tar = mTar.mNode
    _group_keys = list(d_attrMap.get(_key).items())
    if _key == 'hs':
        _allowed = set(_hs_attr_groups_for_scope(hs_profile_scope))
        _group_keys = [(g, l) for g, l in _group_keys if g in _allowed]
    for section, l in _group_keys:
        log.debug(cgmGEN.logString_msg(_str_func,section))        
        for a in l:
            if a in l_ignore:
                continue
            if _key == 'hs' and a in l_skipHairFeelAttrs:
                continue
            if not mc.attributeQuery(a, node=_tar, exists=True):
                continue
            _v = None
            try:
                _v = ATTR.get(_tar, a)
                log.debug(cgmGEN.logString_msg(_str_func, "{0} | {1}".format(a, _v)))
            except Exception as err:
                log.error("Failed to query: {0} | {1} | {2}".format(_tar, a, err))
            if _v is None or _v is False:
                continue
            _res[str(a)] = _v

    if differential:
        log.debug(cgmGEN.logString_msg(_str_func,"Getting differential"))
        _d_base = profile_get('base', module) or {}
        _d_baseSet = _d_base.get(_key) or {}
        if _d_baseSet:
            log.debug(cgmGEN.logString_msg(_str_func,"Found base set..."))
            _res_use = {}
            for k, v in list(_res.items()):
                if k in l_skipHairFeelAttrs:
                    continue
                _base_v = _d_baseSet.get(k)
                if _base_v is None or v != _base_v:
                    log.debug(cgmGEN.logString_msg(_str_func,"Storing: {0} | {1}".format(k,v)))
                    _res_use[k] = v
            return {_key:_res_use}
        
    #pprint.pprint(_res)
    return _res

def _is_profile_dict(v):
    return isinstance(v, dict) and ('n' in v or 'hs' in v)


def profile_kind(name, module=dynFKPresets):
    """Return profile kind: hair | wind | solver | base | None."""
    if not name:
        return None
    cgmGEN._reloadMod(module)
    kind = module.__dict__.get('d_profileKind', {}).get(name)
    if kind:
        return kind
    _d = profile_get(name, module)
    if not _d:
        return None
    if _d.get('hs') and not _d.get('n'):
        return 'hair'
    if name.startswith('wind') or ( _d.get('n') and _d.get('hs') and name == 'wind'):
        return 'wind'
    if name == 'base':
        return 'base'
    if _d.get('n') and not _d.get('hs'):
        return 'solver'
    return 'hair' if _d.get('hs') else 'solver'


def profile_list(module=dynFKPresets, key=None, category=None):
    """Return sorted profile names from cgmDynFK_presets (module attrs + d_chain).

    :param key: Optional 'n'/'hs' — profile must define that section.
    :param category: Optional kind filter: hair | wind | solver | base
    """
    cgmGEN._reloadMod(module)
    names = set()
    for k, v in list(module.__dict__.items()):
        if k.startswith('_') or k in ('d_chain', 'd_profileKind'):
            continue
        if _is_profile_dict(v):
            names.add(k)
    d_chain = module.__dict__.get('d_chain') or {}
    if isinstance(d_chain, dict):
        for k, v in list(d_chain.items()):
            if _is_profile_dict(v):
                names.add(k)
    filtered = []
    for name in names:
        _d = profile_get(name, module)
        if not _d:
            continue
        if key is not None and _d.get(key) is None:
            continue
        if category and profile_kind(name, module) != category:
            continue
        filtered.append(name)
    return sorted(filtered)

def profile_get(arg = None, module = dynFKPresets ):
    cgmGEN._reloadMod(module)
    _d = module.__dict__.get(arg)
    if _is_profile_dict(_d):
        return _d
    d_chain = module.__dict__.get('d_chain') or {}
    if isinstance(d_chain, dict):
        return d_chain.get(arg)
    return None

def _format_profile_attr_value(value):
    """Compact value string for Script Editor attr-change lines."""
    if isinstance(value, dict):
        try:
            _items = []
            for k in sorted(value.keys(), key=lambda x: (str(type(x)), x)):
                _v = value[k]
                if isinstance(_v, (list, tuple)):
                    _v = '({0})'.format(', '.join('{0:g}'.format(float(x))
                                                   if isinstance(x, (int, float)) else repr(x)
                                                   for x in _v))
                _items.append('{0}:{1}'.format(k, _v))
            return '{' + ', '.join(_items) + '}'
        except Exception:
            return repr(value)
    if isinstance(value, float):
        return '{0:g}'.format(value)
    if isinstance(value, (list, tuple)):
        try:
            return '({0})'.format(', '.join(
                '{0:g}'.format(float(x)) if isinstance(x, (int, float)) else repr(x)
                for x in value))
        except Exception:
            return repr(value)
    return repr(value)


def _profile_values_equal(a, b):
    """Loose equality for preset apply change logging (ramps / float noise)."""
    if a is b:
        return True
    if a is None or b is None:
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            # JSON may use str keys vs int
            try:
                _na = _normalize_compound_profile_value(a)
                _nb = _normalize_compound_profile_value(b)
                if set(_na.keys()) != set(_nb.keys()):
                    return False
                return all(_profile_values_equal(_na[k], _nb[k]) for k in _na)
            except Exception:
                return False
        return all(_profile_values_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_profile_values_equal(x, y) for x, y in zip(a, b))
    try:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) < 1e-6
    except Exception:
        pass
    return a == b


def _apply_profile_attr_dict(node, d_use, log_name='profile_apply_section', node_type=''):
    """
    Set attrs on node; log each change as ``attr: old >> new``.

    :returns: (set_count, changed_count)
    """
    if not node or not d_use:
        return 0, 0
    _set = 0
    _changed = 0
    for a in sorted(d_use.keys(), key=lambda x: str(x)):
        v = d_use[a]
        _old = None
        _old_ok = False
        try:
            if mc.attributeQuery(a, node=node, exists=True):
                _old = ATTR.get(node, a)
                _old_ok = True
        except Exception:
            _old_ok = False
        try:
            ATTR.set(node, a, v)
            _set += 1
        except Exception as err:
            log.warning("{0} | Failed to set: {1} | {2} | {3}".format(
                node_type or log_name, a, v, err))
            continue
        if not _old_ok:
            log.info(cgmGEN.logString_msg(
                log_name, '{0}: <missing> >> {1}'.format(
                    a, _format_profile_attr_value(v))))
            _changed += 1
        elif not _profile_values_equal(_old, v):
            log.info(cgmGEN.logString_msg(
                log_name, '{0}: {1} >> {2}'.format(
                    a,
                    _format_profile_attr_value(_old),
                    _format_profile_attr_value(v))))
            _changed += 1
        else:
            log.debug(cgmGEN.logString_msg(
                log_name, '{0}: unchanged ({1})'.format(
                    a, _format_profile_attr_value(v))))
    return _set, _changed


def profile_apply_section(target=None, attrs=None, section='hs', clean=True,
                          profileKind='hair', module=dynFKPresets):
    """
    Apply a flat attr dict to a hairSystem (``hs``) or nucleus (``n``) node.

    Mirrors ``profile_load`` clean/seed rules for dat-file apply.

    Hair feel (``profileKind=hair``): clean seeds **dynamic** ``base.hs`` only —
    never clump/width/subSegments (those belong to HairShape dats).
    """
    _str_func = 'profile_apply_section'
    import cgm.core.lib.nCloth_utils as NCLOTH

    if not attrs:
        return 0

    mTar = cgmMeta.asMeta(target, noneValid=True)
    if not mTar:
        return log.error(cgmGEN.logString_msg(_str_func, "No valid target"))

    _type = mTar.getMayaType()
    _key = d_shortHand.get(_type, _type)
    if section != _key:
        log.warning(cgmGEN.logString_msg(
            _str_func, "Section {0} != target key {1} for {2}".format(section, _key, _type)))

    attrs = copy.deepcopy(attrs)
    if profileKind == 'hair' and _key == 'hs':
        attrs, _removed = hair_profile_filter_feel(attrs)
        if _removed:
            log.warning(cgmGEN.logString_msg(
                _str_func,
                "Dropped non-feel attrs from hair apply: {0}".format(
                    ', '.join(sorted(_removed)))))
        if not attrs:
            return 0
    elif profileKind == 'hairShape' and _key == 'hs':
        attrs, _removed_dyn = hair_profile_partition_shape_only(attrs)
        if _removed_dyn:
            log.warning(cgmGEN.logString_msg(
                _str_func,
                "Dropped non-shape attrs from HairShape apply: {0}".format(
                    ', '.join(sorted(_removed_dyn)))))
        if not attrs:
            return 0

    d_use = {}

    if clean:
        if _key == 'hs' and profileKind == 'hairShape':
            d_use = _base_hs_seed_for_kind('hairShape', module)
        elif _key == 'hs' and profileKind == 'hair':
            d_use = _base_hs_seed_for_kind('hair', module)
        elif profileKind == 'base':
            _base = profile_get('base', module) or {}
            d_use = copy.deepcopy(_base.get(_key) or {})
        else:
            d_use = {}
    else:
        d_use = {}

    d_use.update(attrs)

    if _key == 'n':
        NCLOTH._remap_nucleus_scene_axes(d_use)
        log.info(cgmGEN.logString_msg(
            _str_func, "Scene up: {0} | gravityDirection: {1}".format(
                NCLOTH.scene_up_get(), d_use.get('gravityDirection'))))

    _node = mTar.mNode
    _count, _changed = _apply_profile_attr_dict(
        _node, d_use, log_name=_str_func, node_type=_type)

    log.info(cgmGEN.logString_msg(
        _str_func, "{0} | section={1} kind={2} | {3} set | {4} changed".format(
            _node, _key, profileKind, _count, _changed)))
    return _count


def profile_load(target = None, arg = None, module = dynFKPresets, clean = True):
    """
    Apply a dynFK profile section to a nucleus or hairSystem target.

    Hair feel (kind=hair): seeds dynamic base.hs when clean (not shape groups),
    writes hs feel only. Wind / solver on nucleus: layer keys only unless kind is base.
    """
    _str_func = 'profile_apply'
    import cgm.core.lib.nCloth_utils as NCLOTH

    mTar = cgmMeta.asMeta(target, noneValid = True)
    if not mTar:
        return log.error(cgmGEN.logString_msg(_str_func, "No valid target"))
    
    _type = mTar.getMayaType()
    _key = d_shortHand.get(_type,_type)    
    log.info(cgmGEN.logString_msg(_str_func,"mTar: {0} | {1}".format(_type, mTar)))
    
    _d_profile = profile_get(arg,module)
    if not _d_profile:
        log.warning("Invalid profile: {0}".format(arg))        
        return False
    
    _d_type = _d_profile.get(_key)
    if not _d_type:
        log.warning("No {0}  dat".format(_type))
        return False

    _kind = profile_kind(arg, module)
    
    if clean:
        # Hair feel: seed dynamic base.hs only (not shape). Base reset: full section.
        # Sim layers: no full base.n dump.
        if _kind == 'base':
            d_use = copy.deepcopy(profile_get('base', module).get(_key) or {})
            d_use.update(copy.deepcopy(_d_type))
        elif _kind == 'hair' and _key == 'hs':
            d_use = _base_hs_seed_for_kind('hair', module)
            _hs_overlay, _ = hair_profile_filter_feel(
                copy.deepcopy(_d_type))
            d_use.update(_hs_overlay)
        else:
            d_use = copy.deepcopy(_d_type)
    else:
        d_use = copy.deepcopy(_d_type)
        if _kind == 'hair' and _key == 'hs':
            d_use, _ = hair_profile_filter_feel(d_use)

    if _key == 'n':
        NCLOTH._remap_nucleus_scene_axes(d_use)
        log.info(cgmGEN.logString_msg(
            _str_func, "Scene up: {0} | gravityDirection: {1}".format(
                NCLOTH.scene_up_get(), d_use.get('gravityDirection'))))
    
    _node = mTar.mNode
    _count, _changed = _apply_profile_attr_dict(
        _node, d_use, log_name=_str_func, node_type=_type)
    log.info(cgmGEN.logString_msg(
        _str_func, "{0} | profile={1} | {2} set | {3} changed".format(
            _node, arg, _count, _changed)))
    
    
#=========================================================================      
# R9 Stuff - We force the update on the Red9 internal registry  
#=========================================================================      
cgmMeta.r9Meta.registerMClassInheritanceMapping()
