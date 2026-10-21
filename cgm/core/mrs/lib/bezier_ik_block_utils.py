"""
MRS block-level Bezier IK helpers (shapes, controls pickwalk, stretch aim, squash compensate).

Shared by Segment, Head neck, and Limb bezier paths. Solver math lives in ik_utils / bezier_utils.
"""
import logging

import maya.cmds as mc

import cgm.core.cgm_General as cgmGEN
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.classes.NodeFactory as NODEFACTORY
import cgm.core.lib.attribute_utils as ATTR
import cgm.core.rig.dynamic_utils as RIGDYN
from cgm.core.cgmPy import validateArgs as VALID
import cgm.core.lib.curve_Utils as CURVES
import cgm.core.lib.distance_utils as DIST
import cgm.core.lib.math_utils as MATH
import cgm.core.lib.position_utils as POS
import cgm.core.lib.rigging_utils as CORERIG
import cgm.core.lib.string_utils as CORESTRING
import cgm.core.tools.lib.snap_calls as SNAPCALLS

log = logging.getLogger(__name__)


def block_squash_inflate_control(mBlock):
    """Block flag for bezier_spline_stretch extraInflateControl (legacy: squashExtraControl)."""
    if mBlock and mBlock.hasAttr('squashInflateControl'):
        return bool(mBlock.squashInflateControl)
    if mBlock and mBlock.hasAttr('squashExtraControl'):
        return bool(mBlock.squashExtraControl)
    return False


def block_squash_inflate_factor_min_max(mBlock, d_squash_stretch=None):
    """
    Block bounds for settings {part}_inflate_inflateFactor_* ramp (get_blendList).
    Prefer squashInflateFactorMin/Max; legacy inflateFactorMin/Max; then squashFactor*.
    """
    _d = d_squash_stretch or {}
    f_min = _d.get('squashInflateFactorMin')
    f_max = _d.get('squashInflateFactorMax')
    if f_min is None and mBlock and mBlock.hasAttr('squashInflateFactorMin'):
        f_min = float(mBlock.squashInflateFactorMin)
    elif f_min is None and mBlock and mBlock.hasAttr('inflateFactorMin'):
        f_min = float(mBlock.inflateFactorMin)
    if f_max is None and mBlock and mBlock.hasAttr('squashInflateFactorMax'):
        f_max = float(mBlock.squashInflateFactorMax)
    elif f_max is None and mBlock and mBlock.hasAttr('inflateFactorMax'):
        f_max = float(mBlock.inflateFactorMax)
    if f_min is None:
        f_min = 0.0
    if f_max is None:
        f_max = 1.0
    if f_max <= f_min and mBlock:
        if mBlock.hasAttr('squashFactorMin') and mBlock.hasAttr('squashFactorMax'):
            f_min = float(mBlock.squashFactorMin)
            f_max = float(mBlock.squashFactorMax)
        if f_max <= f_min:
            f_min, f_max = 0.0, 1.0
    return f_min, f_max


def block_squash_inflate_factor_mode(mBlock, default='midPeak'):
    """
    Block enum for per-joint inflate factor ramp (ik_utils MATH.get_blendList).
    Parallel to squashFactorMode; legacy blocks may still have inflateFactorMode.
    """
    if not mBlock:
        return default
    if mBlock.hasAttr('squashInflateFactorMode'):
        return mBlock.getEnumValueString('squashInflateFactorMode') or default
    if mBlock.hasAttr('inflateFactorMode'):
        return mBlock.getEnumValueString('inflateFactorMode') or default
    return default


def _bezier_inflate_volume_scale_attrs(d_stretch_res, aim_axis):
    l_volume_scale = (d_stretch_res or {}).get('l_volumeScaleAttrs')
    if not l_volume_scale:
        import cgm.core.rig.ik_utils as IKUTIL
        _, _, l_volume_scale = IKUTIL._bezier_stretch_axis_data(aim_axis)
    return l_volume_scale


def bezier_inflate_parent_direct_controls(d_stretch_res, aim_axis, l_entries):
    """
    Wire inflate scale onto parents of direct rig controls (FK-visible).

    l_entries: list of dicts with keys m_rig, m_parent (null parents under this),
        str_plug (inflate scale source).
    """
    _str_func = 'bezier_inflate_parent_direct_controls'
    if not d_stretch_res or not d_stretch_res.get('inflateDriveDirectParents'):
        return []
    if not l_entries:
        return []

    l_volume_scale = _bezier_inflate_volume_scale_attrs(d_stretch_res, aim_axis)
    ml_inflate_nodes = []
    for d_entry in l_entries:
        m_rig = cgmMeta.validateObjArg(
            d_entry.get('m_rig'), 'cgmObject', noneValid=True)
        m_parent = cgmMeta.validateObjArg(
            d_entry.get('m_parent'), 'cgmObject', noneValid=True)
        str_scale_plug = d_entry.get('str_plug')
        if not m_rig or not m_parent or not str_scale_plug:
            continue

        m_inflate = m_parent.doCreateAt('null')
        m_inflate.rename('{0}_inflateScale'.format(m_rig.p_nameBase))
        if not m_inflate.hasAttr('cgmTypeModifier'):
            m_inflate.addAttr('cgmTypeModifier', 'inflateScale', lock=True)
        else:
            ATTR.set(m_inflate.mNode, 'cgmTypeModifier', 'inflateScale')
        m_inflate.p_parent = m_parent

        for str_attr in l_volume_scale:
            ATTR.connect(
                str_scale_plug,
                '{0}.{1}'.format(m_inflate.mNode, str_attr))

        m_rig.connectChildNode(m_inflate, 'inflateScale', 'rigJoint')

        m_master = m_rig.getMessageAsMeta('masterGroup')
        if m_master:
            m_master.p_parent = m_inflate
        else:
            m_rig.p_parent = m_inflate

        ml_inflate_nodes.append(m_inflate)

    log.info(cgmGEN.logString_msg(
        _str_func, 'wired | count:{0}'.format(len(ml_inflate_nodes))))
    return ml_inflate_nodes


def bezier_inflate_parent_segment_direct_controls(
        mRigNull, d_stretch_res, ml_blendJoints, ml_rigJoints, aim_axis):
    """
    Segment parent segmentType: inflate on a parent of direct rig joints (FK-visible).

    Expects bezier_spline_stretch with inflateDriveDirectParents and l_inflateDirectPlugs.
    """
    _str_func = 'bezier_inflate_parent_segment_direct_controls'
    l_plugs = (d_stretch_res or {}).get('l_inflateDirectPlugs') or []
    if not l_plugs:
        return []

    ml_blendJoints = cgmMeta.validateObjListArg(
        ml_blendJoints, 'cgmObject', noneValid=True) or []
    ml_rigJoints = cgmMeta.validateObjListArg(
        ml_rigJoints, 'cgmObject', noneValid=True) or []
    if (not ml_blendJoints or not ml_rigJoints
            or len(ml_blendJoints) != len(ml_rigJoints)):
        log.warning(cgmGEN.logString_msg(
            _str_func,
            'skip | blend:{0} rig:{1}'.format(
                len(ml_blendJoints), len(ml_rigJoints))))
        return []

    l_entries = []
    for d_plug in l_plugs:
        int_i = d_plug.get('i', 0)
        if int_i < 0 or int_i >= len(ml_rigJoints):
            continue
        str_scale_plug = d_plug.get('str_plug')
        if not str_scale_plug:
            continue
        l_entries.append({
            'm_rig': ml_rigJoints[int_i],
            'm_parent': ml_blendJoints[int_i],
            'str_plug': str_scale_plug,
        })

    return bezier_inflate_parent_direct_controls(
        d_stretch_res, aim_axis, l_entries)


def _segment_inflate_volume_plug_from_ik_joint(m_jnt, l_volume_scale):
    """First live driver on secondary scale attrs (ribbon/curve volume squash output)."""
    m_jnt = cgmMeta.validateObjArg(m_jnt, 'cgmObject', noneValid=True)
    if not m_jnt:
        return None
    for str_attr in l_volume_scale:
        str_plug = ATTR.get_driver('{0}.{1}'.format(m_jnt.mNode, str_attr))
        if str_plug:
            return str_plug
    return None


def segment_inflate_stretch_result_from_ik_joints(
        ml_ikJoints,
        mSettings,
        aim_axis,
        str_base,
        inflate_factor_min=0.0,
        inflate_factor_max=1.0,
        inflate_factor_mode='midPeak',
        inflate_factor_base_name=None,
        parentGutsTo=None,
        extra_keyable=True):
    """
    Build inflate settings + additive scale plugs from existing IK volume drivers.

    Does not change ribbon/curve squash/stretch; IK joints keep volume-only drivers.
    Returns the same dict slice as bezier_spline_stretch for inflate parent wiring.
    """
    import cgm.core.rig.ik_utils as IKUTIL

    _str_func = 'segment_inflate_stretch_result_from_ik_joints'
    ml_ikJoints = cgmMeta.validateObjListArg(
        ml_ikJoints, 'cgmObject', noneValid=True) or []
    mSettings = cgmMeta.validateObjArg(mSettings, noneValid=True)
    if len(ml_ikJoints) < 2 or not mSettings:
        log.info(cgmGEN.logString_msg(_str_func, 'skip | joints or settings missing'))
        return None

    _, _, l_volume_scale = IKUTIL._bezier_stretch_axis_data(aim_axis)
    str_inflate_factor_base = inflate_factor_base_name or str_base

    l_indices_with_volume = []
    for int_i, m_jnt in enumerate(ml_ikJoints[:-1]):
        if _segment_inflate_volume_plug_from_ik_joint(m_jnt, l_volume_scale):
            l_indices_with_volume.append(int_i)
    if not l_indices_with_volume:
        log.info(cgmGEN.logString_msg(
            _str_func, 'skip | no volume drivers on IK joints'))
        return None

    mPlug_inflate, mPlug_inflate_offset = (
        IKUTIL._bezier_stretch_settings_inflate_plugs(mSettings, extra_keyable))
    int_inflate_max_factor_idx = IKUTIL._bezier_stretch_inflate_max_factor_index(
        len(ml_ikJoints), None)
    d_inflate_offset_shared = IKUTIL._bezier_stretch_inflate_offset_shared(
        str_base, mPlug_inflate_offset, int_inflate_max_factor_idx)
    ml_inflate_dg = list(d_inflate_offset_shared.get('ml_nodes') or [])

    l_inflate_factors = MATH.get_blendList(
        len(ml_ikJoints), inflate_factor_max, inflate_factor_min,
        inflate_factor_mode)
    log.info(cgmGEN.logString_msg(
        _str_func,
        'inflateFactor ramp ({0}) mode:{1} min:{2} max:{3}'.format(
            len(ml_ikJoints), inflate_factor_mode,
            inflate_factor_min, inflate_factor_max)))

    md_inflate_factor_plugs = IKUTIL._bezier_stretch_inflate_factor_plugs_ensure(
        mSettings, str_inflate_factor_base, l_inflate_factors,
        int_inflate_max_factor_idx, extra_keyable)

    l_inflate_direct_plugs = []
    str_inflate_shift = d_inflate_offset_shared.get('str_shift')

    for int_i, m_jnt in enumerate(ml_ikJoints[:-1]):
        str_vol_scale = _segment_inflate_volume_plug_from_ik_joint(
            m_jnt, l_volume_scale)
        if not str_vol_scale:
            continue
        str_factor_sample, ml_sample = (
            IKUTIL._bezier_stretch_inflate_offset_sample_network(
                str_base, int_i, int_i, int_inflate_max_factor_idx,
                str_inflate_shift, md_inflate_factor_plugs))
        ml_inflate_dg.extend(ml_sample)
        d_inflate = IKUTIL._bezier_stretch_joint_inflate_additive_network(
            str_base, int_i, str_vol_scale,
            str_factor_sample, mPlug_inflate)
        str_inflate_scale = d_inflate['str_scale']
        ml_inflate_dg.extend(d_inflate['ml_nodes'])
        IKUTIL._bezier_stretch_connect_inflate_joint_or_direct(
            m_jnt, l_volume_scale, str_vol_scale, str_inflate_scale,
            True, l_inflate_direct_plugs, int_i)

    if len(ml_ikJoints) >= 1:
        int_tip = len(ml_ikJoints) - 1
        m_tip = ml_ikJoints[int_tip]
        str_tip_vol = _segment_inflate_volume_plug_from_ik_joint(
            m_tip, l_volume_scale)
        if not str_tip_vol and int_tip > 0:
            str_tip_vol = _segment_inflate_volume_plug_from_ik_joint(
                ml_ikJoints[int_tip - 1], l_volume_scale)
        if str_tip_vol:
            int_g = int_tip
            str_factor_sample, ml_sample = (
                IKUTIL._bezier_stretch_inflate_offset_sample_network(
                    str_base, int_tip, int_g, int_inflate_max_factor_idx,
                    str_inflate_shift, md_inflate_factor_plugs))
            ml_inflate_dg.extend(ml_sample)
            d_inflate = IKUTIL._bezier_stretch_joint_inflate_additive_network(
                str_base, int_tip, str_tip_vol,
                str_factor_sample, mPlug_inflate)
            str_inflate_scale = d_inflate['str_scale']
            ml_inflate_dg.extend(d_inflate['ml_nodes'])
            IKUTIL._bezier_stretch_connect_inflate_joint_or_direct(
                m_tip, l_volume_scale, str_tip_vol, str_inflate_scale,
                True, l_inflate_direct_plugs, int_tip)

    if parentGutsTo and ml_inflate_dg:
        m_guts_grp = IKUTIL._bezier_stretch_guts_group(str_base, parentGutsTo)
        if m_guts_grp:
            IKUTIL._bezier_stretch_parent_dag_under(ml_inflate_dg, m_guts_grp)

    log.info(cgmGEN.logString_msg(
        _str_func, 'done | plugs:{0}'.format(len(l_inflate_direct_plugs))))
    return {
        'inflateDriveDirectParents': True,
        'l_inflateDirectPlugs': l_inflate_direct_plugs,
        'l_volumeScaleAttrs': l_volume_scale,
    }


def block_bezier_anchor_mode(mBlock):
    """Map block splineBezierMode enum to IK.bezier_spline bezierAnchorMode (uniform | bend)."""
    if mBlock and mBlock.hasAttr('splineBezierMode'):
        _mode = mBlock.getEnumValueString('splineBezierMode')
        if _mode:
            return _mode
    return 'uniform'


def block_ik_bezier_control_shape(mBlock):
    """Segment ikBezierControlShape: ball (FK cube + sphere subs) vs segmentHandle (cast-thin cube + limbSegmentHandle subs)."""
    if mBlock and mBlock.hasAttr('ikBezierControlShape'):
        _mode = mBlock.getEnumValueString('ikBezierControlShape')
        if _mode == 'segmentHandle':
            return 'segmentHandle'
    return 'ball'


def rig_shapes_bezier_cast_aim_vector(self):
    """Cast aim vector for limbSegmentHandle shapes (matches segment rig_shapes)."""
    mBlock = self.mBlock
    d_orients = self.d_orientation or {}
    _castVector = mBlock.getEnumValueString('castVector')
    return d_orients.get('vector{0}'.format(CORESTRING.capFirst(_castVector)))


def rig_shapes_bezier_segment_handle_semisphere_size(mBlock, offset, scale=1.0):
    f_base = mBlock.getMayaAttr('jointRadius') if mBlock.hasAttr('jointRadius') else None
    if not f_base:
        f_base = offset
    return f_base * scale


def rig_shapes_bezier_segment_handle_shape(
        self, mObj, mHandleFactory, aim_vector, offset, scale=1.0,
        control_type='accent'):
    """limbSegmentHandle semiSphere cast (limb bezier subs / neck handleJoints style)."""
    mBlock = self.mBlock
    f_size = rig_shapes_bezier_segment_handle_semisphere_size(mBlock, offset, scale)
    ml_shapes = self.atBuilderUtils(
        'shapes_fromCast',
        targets=mObj,
        offset=offset,
        aimVector=aim_vector,
        mode='limbSegmentHandle',
        size=f_size)
    if not ml_shapes:
        return
    CORERIG.shapeParent_in_place(
        mObj.mNode, ml_shapes[0].mNode, False, replaceShapes=True)
    mHandleFactory.color(mObj.mNode, controlType=control_type)
    try:
        ml_shapes[0].delete()
    except Exception:
        pass


def rig_shapes_fk_shape_cross_size(mFKShape, scale=1.0):
    """Width of a cast FK frame shape (avg of the two smaller axis-box axes)."""
    l_axis = POS.get_axisBox_size(mFKShape.mNode, False)
    return MATH.average(sorted(l_axis)[:2]) * scale


def rig_shapes_closest_fk_shape_idx(v_pos, ml_fkCastTargets):
    idx_best = 0
    f_best = None
    for i, mTar in enumerate(ml_fkCastTargets):
        f_dist = DIST.get_distance_between_points(v_pos, mTar.p_position)
        if f_best is None or f_dist < f_best:
            f_best = f_dist
            idx_best = i
    return idx_best


def rig_shapes_bezier_sub_pos(v_main, v_neighbor):
    """Position 1/3 from main toward neighbor (world space)."""
    f_dist = DIST.get_distance_between_points(v_main, v_neighbor) / 3.0
    v_vec = MATH.get_vector_of_two_points(v_main, v_neighbor)
    return DIST.get_pos_by_vec_dist(v_main, v_vec, f_dist)


def rig_shapes_bezier_ik_shape_from_fk(
        self, mIKControl, mFKShape, str_shape='cube', mSnapSource=None, scale=1.2):
    """IK handle curve sized from FK cast cross-section (ikSetup bezier)."""
    if mSnapSource is None:
        mSnapSource = mIKControl
    f_size = rig_shapes_fk_shape_cross_size(mFKShape, scale)
    _ik_shape = CURVES.create_fromName(str_shape, size=f_size)
    mIKShape = cgmMeta.validateObjArg(_ik_shape, 'cgmObject', setClass=True)
    mIKShape.doSnapTo(mSnapSource)
    CORERIG.shapeParent_in_place(
        mIKControl.mNode, mIKShape.mNode, False, replaceShapes=True)


def rig_shapes_bezier_ik_cube_from_fk(self, mIKControl, mSnapSource, mFKShape, scale=1.2):
    rig_shapes_bezier_ik_shape_from_fk(
        self, mIKControl, mFKShape, 'cube', mSnapSource, scale)


def rig_shapes_bezier_cast_mesh_spans(self, mObj, str_meshShape, offset):
    """Cast spans at mObj (limbSegmentHandle / limb bezier main cube sizing)."""
    str_orientation = self.d_orientation['str']
    pos_obj = mObj.p_position
    dist_fallback = offset * 5
    md_sides = {}
    for axis in str_orientation:
        md_sides[axis] = {}
        for d in ['+', '-']:
            p = SNAPCALLS.get_special_pos(
                [mObj.mNode, str_meshShape], 'cast', axis + d)
            if not p:
                p = DIST.get_pos_by_axis_dist(
                    mObj.mNode, axis + d, dist_fallback)
            md_sides[axis][d] = DIST.get_distance_between_points(p, pos_obj)

    l_cross = []
    for axis in (str_orientation[1], str_orientation[2]):
        l_cross.append(md_sides[axis]['+'])
        l_cross.append(md_sides[axis]['-'])
    _max = max(l_cross)
    _distCheck = MATH.average([v for v in l_cross if v is not _max]) * 2.0

    def _axis_span(axis, b_filter_cross):
        d_pos = md_sides[axis]['+']
        d_neg = md_sides[axis]['-']
        if b_filter_cross and axis in (str_orientation[1], str_orientation[2]):
            if d_pos > _distCheck:
                d_pos = None
            if d_neg > _distCheck:
                d_neg = None
        l_use = [v for v in (d_pos, d_neg) if v is not None]
        if not l_use:
            return dist_fallback * 2.0
        if len(l_use) == 2:
            return l_use[0] + l_use[1]
        return l_use[0] * 2.0

    mBlock = self.mBlock
    f_aim = (
        mBlock.getMayaAttr('jointRadius') if mBlock.hasAttr('jointRadius') else None)
    if not f_aim:
        f_aim = offset
    f_cross_a = _axis_span(str_orientation[1], True)
    f_cross_b = _axis_span(str_orientation[2], True)
    return {
        str_orientation[0]: f_aim,
        str_orientation[1]: f_cross_a,
        str_orientation[2]: f_cross_b,
    }


def rig_shapes_bezier_main_cast_box_size(self, mMain, offset=None):
    """Cube [sx,sy,sz] from proxy cast — aim axis uses jointRadius (limb bezier mains)."""
    _str_func = 'rig_shapes_bezier_main_cast_box_size'
    offset = offset if offset is not None else getattr(self, 'v_offset', None)
    if not offset and getattr(self, 'mPuppet', None):
        offset = self.mPuppet.atUtils('get_shapeOffset')
    mMesh = self.mBlock.atUtils('get_castMesh', True)
    if not mMesh:
        log.warning(cgmGEN.logString_msg(_str_func, 'no cast mesh'))
        return None
    str_meshShape = mMesh.getShapes()[0]
    try:
        md_span = rig_shapes_bezier_cast_mesh_spans(
            self, mMain, str_meshShape, offset)
    except Exception as err:
        log.warning(cgmGEN.logString_msg(
            _str_func, 'cast fail {0} | {1}'.format(mMain.p_nameShort, err)))
        md_span = None
    finally:
        try:
            mMesh.delete()
        except Exception:
            pass
    if not md_span:
        return None
    return [md_span['x'], md_span['y'], md_span['z']]


def rig_shapes_bezier_main_cube_cast_sized(
        self, mMain, mFKShape=None, offset=None, scale=1.2):
    """Cast-thin cube on main IK (jointRadius on aim); FK fallback if cast fails."""
    offset = offset if offset is not None else getattr(self, 'v_offset', None)
    l_size = rig_shapes_bezier_main_cast_box_size(self, mMain, offset)
    if not l_size and mFKShape:
        f_cross = rig_shapes_fk_shape_cross_size(mFKShape, scale)
        mBlock = self.mBlock
        f_aim = (
            mBlock.getMayaAttr('jointRadius')
            if mBlock.hasAttr('jointRadius') else None)
        if not f_aim:
            f_aim = offset or 1.0
        _d_orient = self.d_orientation or {}
        str_aim = (_d_orient.get('stringAim') or '{0}+'.format(
            _d_orient.get('str', 'zyx')[0]))[0].lower()
        l_size = [f_cross, f_cross, f_cross]
        l_size[{'x': 0, 'y': 1, 'z': 2}.get(str_aim, 2)] = f_aim
    if not l_size:
        return
    _ik_shape = CURVES.create_fromName('cube', size=l_size, bakeScale=True)
    mIKShape = cgmMeta.validateObjArg(_ik_shape, 'cgmObject', setClass=True)
    mIKShape.doSnapTo(mMain)
    CORERIG.shapeParent_in_place(
        mMain.mNode, mIKShape.mNode, False, replaceShapes=True)


def rig_shapes_bezier_main_fk_idx(self, mMain, mRigNull, mBlock, ml_fkCastTargets,
                                  ml_fkShapes, mControlIK, mControlIKBase):
    int_handle_end = getattr(self, 'int_handleEndIdx', -1)
    int_seg_base = getattr(self, 'int_segBaseIdx', 0)
    if mMain == mControlIKBase:
        return min(int_seg_base, len(ml_fkShapes) - 1)
    if mMain == mControlIK:
        idx = int_handle_end
        if abs(idx) > len(ml_fkShapes):
            idx = -1
        return idx
    for i, mMid in enumerate(self.ml_ikMidControls):
        if mMain == mMid:
            return rig_shapes_closest_fk_shape_idx(
                self.ml_ikMidHelpers[i].p_position, ml_fkCastTargets)
    return 0


def rig_shapes_bezier_main_ik_type(mMain, mHandleFactory):
    mMain.doStore('cgmTypeModifier', 'ikBezier')
    mMain.doStore('cgmType', 'handle')
    mMain.doName()
    mHandleFactory.color(mMain.mNode, controlType='main')


def rig_shapes_bezier_ik_apply_from_fk(self, ml_fkShapes, ml_fkCastTargets, mHandleFactory):
    """Bezier IK cube mains + ikBezier typing (segment / head rig_shapes)."""
    mRigNull = self.mRigNull
    mBlock = self.mBlock
    str_shape_mode = block_ik_bezier_control_shape(mBlock)
    int_handle_end = getattr(self, 'int_handleEndIdx', -1)
    int_seg_base = getattr(self, 'int_segBaseIdx', 0)
    offset = getattr(self, 'v_offset', None)

    def _shape_main(mIKControl, mSnapSource, mFKShape):
        if str_shape_mode == 'segmentHandle':
            rig_shapes_bezier_main_cube_cast_sized(
                self, mIKControl, mFKShape, offset=offset)
        else:
            rig_shapes_bezier_ik_cube_from_fk(
                self, mIKControl, mSnapSource, mFKShape)
        rig_shapes_bezier_main_ik_type(mIKControl, mHandleFactory)

    mControlIK = mRigNull.getMessageAsMeta('controlIK')
    if mControlIK:
        idx = int_handle_end
        if abs(idx) > len(ml_fkShapes):
            idx = -1
        mSnapEnd = getattr(mBlock, 'ikEndHandle', None) or mControlIK
        _shape_main(mControlIK, mSnapEnd, ml_fkShapes[idx])

    mControlIKBase = mRigNull.getMessageAsMeta('controlIKBase')
    if mControlIKBase:
        idx = min(int_seg_base, len(ml_fkShapes) - 1)
        mSnapStart = getattr(mBlock, 'ikStartHandle', None) or mControlIKBase
        _shape_main(mControlIKBase, mSnapStart, ml_fkShapes[idx])

    for i, mHelper in enumerate(self.ml_ikMidControls):
        idx = rig_shapes_closest_fk_shape_idx(
            self.ml_ikMidHelpers[i].p_position, ml_fkCastTargets)
        _shape_main(mHelper, self.ml_ikMidHelpers[i], ml_fkShapes[idx])


def rig_frame_bezier_ik_track_vis(mRigNull, mPlug_IKon, ml_track_curves=None):
    """Bezier main→sub track curves follow FK/IK vis (result_IKon)."""
    ml_tracks = ml_track_curves or mRigNull.msgList_get('bezierIKTrackCurves') or []
    str_vis = mPlug_IKon.p_combinedShortName
    for mTrack in ml_tracks:
        mTrack = cgmMeta.validateObjArg(mTrack, 'cgmObject', noneValid=True)
        if not mTrack:
            continue
        for mShape in mTrack.getShapes(asMeta=True):
            mShape.overrideEnabled = 1
            ATTR.connect(str_vis, '{0}.overrideVisibility'.format(mShape.mNode))


def rig_shapes_bezier_main_to_sub_track(self, mMain, mSub, str_nameMod, mHandleFactory):
    """Linear track curve main → sub (limb midIK / knee pattern)."""
    str_base = '{0}_{1}_bezierSubTrack'.format(mMain.p_nameBase, str_nameMod)
    trackcrv, l_clusters = CORERIG.create_at(
        [mMain.mNode, mSub.mNode],
        'linearTrack',
        baseName=str_base)
    mTrackCrv = cgmMeta.asMeta(trackcrv)
    mTrackCrv.p_parent = self.mModule
    mHandleFactory.color(mTrackCrv.mNode, controlType='aux')
    for mShape in mTrackCrv.getShapes(asMeta=True):
        mShape.overrideEnabled = 1
        mShape.overrideDisplayType = 2
    return mTrackCrv


def rig_shapes_bezier_main_slot_key(mMain, ml_bezierMainIK, mControlIKBase, mControlIK):
    """Slot id for md_bezierIKSubsBySlot: base | midN | end (vocabulary, not DAG names)."""
    if mControlIKBase and mMain == mControlIKBase:
        return 'base'
    if mControlIK and mMain == mControlIK:
        return 'end'
    int_mid = 0
    for m in ml_bezierMainIK:
        if mControlIKBase and m == mControlIKBase:
            continue
        if mControlIK and m == mControlIK:
            continue
        int_mid += 1
        if m == mMain:
            return 'mid{0}'.format(int_mid)
    return 'mid0'


def bezier_ik_stretch_aim_axis(self):
    """Joint aim axis for bezier_spline_stretch (not rotate-order string)."""
    str_aim = self.d_orientation.get('stringAim') or self.d_orientation['str'][0]
    return str(str_aim)[0].lower()


def squash_ik_fk_blend_segment_scale_compensate(self,
                                              ml_ikJoints=None,
                                              ml_fkJoints=None,
                                              ml_blendJoints=None):
    """segmentScaleCompensate on ik/fk/blend chains when squash stretch is active."""
    if not self.b_squashSetup:
        return
    for ml in (ml_ikJoints, ml_fkJoints, ml_blendJoints):
        if not ml:
            continue
        for mJnt in ml:
            mJnt.segmentScaleCompensate = True


def bezier_ik_mid_controls_from_rigNull(mRigNull):
    """Mid IK mains from rigNull msgList (or legacy single message)."""
    if not mRigNull:
        return []
    ml_mid = list(mRigNull.msgList_get('controlSegMidIK') or [])
    if not ml_mid:
        m_single = mRigNull.getMessageAsMeta('controlSegMidIK')
        if m_single:
            ml_mid = [m_single]
    return ml_mid


def bezier_ik_bezier_main_ik_list(mIKBaseControl, ml_ikMidControls, mIKControl):
    """Anchor mains in rig_shapes / rig_frame wire order."""
    ml_bezierMainIK = []
    if mIKBaseControl:
        ml_bezierMainIK.append(mIKBaseControl)
    if ml_ikMidControls:
        ml_bezierMainIK.extend(ml_ikMidControls)
    if mIKControl:
        ml_bezierMainIK.append(mIKControl)
    return ml_bezierMainIK


def bezier_ik_main_ik_list_from_rigNull(mRigNull):
    """Base + mid + end mains from rigNull only (verify / pickwalk)."""
    if not mRigNull:
        return []
    m_base = mRigNull.getMessageAsMeta('controlIKBase')
    ml_mid = bezier_ik_mid_controls_from_rigNull(mRigNull)
    m_end = mRigNull.getMessageAsMeta('controlIK')
    return bezier_ik_bezier_main_ik_list(m_base, ml_mid, m_end)


def bezier_ik_slot_msglist_attr(str_slot):
    """rigNull msgList attr for subs in a main slot (base | midN | end)."""
    if str_slot == 'base':
        return 'bezierIKSubsBase'
    if str_slot == 'end':
        return 'bezierIKSubsEnd'
    if str_slot.startswith('mid'):
        return 'bezierIKSubs{0}'.format(str_slot.capitalize())
    return 'bezierIKSubs_{0}'.format(str_slot)


BEZIER_IK_MAIN_SUB_MSGLIST = 'bezierIKSubs'
BEZIER_IK_AGGREGATE_MSGLIST_SEGMENT = 'controlsIK'
BEZIER_IK_AGGREGATE_MSGLIST_LIMB = 'controlsSegmentBezier'
BEZIER_IK_AGGREGATE_MSGLIST_NECK = 'controlsNeckBezier'


def _bezier_ik_pickwalk_dag(mObj):
    """Pickwalk targets: registered bezier IK anim DAGs (not track curves)."""
    try:
        if not mObj or not mc.objExists(mObj.mNode):
            return False
    except Exception:
        return False
    if mc.objectType(mObj.mNode) != 'transform':
        return False
    if 'bezierSubTrack' in mObj.mNode:
        return False
    if mc.attributeQuery('cgmTypeModifier', node=mObj.mNode, exists=True):
        _mod = ATTR.get(mObj.mNode, 'cgmTypeModifier')
        if _mod and 'track' in str(_mod).lower():
            return False
        if _mod in ('ikBezier', 'ikBezierSub'):
            return True
    if mc.attributeQuery('cgmType', node=mObj.mNode, exists=True):
        _type = str(ATTR.get(mObj.mNode, 'cgmType') or '')
        if _type == 'handle':
            return True
        if _type == 'controlAnim':
            if mc.attributeQuery('mClass', node=mObj.mNode, exists=True):
                _mclass = str(ATTR.get(mObj.mNode, 'mClass') or '')
                if _mclass and 'cgmControl' in _mclass:
                    return True
            return False
        return False
    return True


def bezier_ik_rignull_has_bezier_ik_data(mRigNull):
    """Scene/rigNull signals bezier IK without block attrs."""
    if not mRigNull:
        return False
    if mRigNull.getMessage('bezierIKDriverCurve'):
        return True
    if mRigNull.msgList_get('bezierIKSubControls'):
        return True
    for mMain in bezier_ik_main_ik_list_from_rigNull(mRigNull):
        if mMain and mMain.msgList_get(BEZIER_IK_MAIN_SUB_MSGLIST):
            return True
    return False


def bezier_ik_filter_pickwalk_dags(ml_pickwalk, ml_mains=None):
    """Filter pickwalk list to anim DAGs; never drop known main anchors."""
    set_main = {m.p_nameLong for m in (ml_mains or []) if m}
    ml_dags = []
    for mObj in ml_pickwalk or []:
        if not mObj:
            continue
        if mObj.p_nameLong in set_main or _bezier_ik_pickwalk_dag(mObj):
            ml_dags.append(mObj)
    if not ml_dags and ml_pickwalk:
        log.warning(
            'bezier_ik_filter_pickwalk_dags | filter dropped all {0} targets; using unfiltered list'.format(
                len(ml_pickwalk)))
        ml_dags = list(ml_pickwalk)
    return ml_dags


def bezier_ik_ensure_aggregate_ik_msglist(mRigNull, str_tag=BEZIER_IK_AGGREGATE_MSGLIST_SEGMENT):
    """
    Repair ordered IK pickwalk msgList on rigNull from mains/subs (no block/session).
    No-op when list exists, referenced, or no bezier data.
    """
    if not mRigNull:
        return []
    try:
        if mRigNull.isReferenced():
            return mRigNull.msgList_get(str_tag) or []
    except Exception:
        pass
    ml_existing = mRigNull.msgList_get(str_tag) or []
    if ml_existing:
        return ml_existing
    if not bezier_ik_rignull_has_bezier_ik_data(mRigNull):
        return []
    bezier_ik_connect_main_sub_msglists(mRigNull, None)
    ml_mains = bezier_ik_main_ik_list_from_rigNull(mRigNull)
    ml_pickwalk = bezier_ik_pickwalk_controls(mRigNull)
    ml_dags = bezier_ik_filter_pickwalk_dags(ml_pickwalk, ml_mains)
    if ml_dags:
        mRigNull.msgList_connect(str_tag, [mObj.mNode for mObj in ml_dags])
    return ml_dags


def bezier_ik_subs_pickwalk_order_for_anchor(i_main, int_last, ml_subs):
    """Per-main bezierIKSubs msgList order (subs only, not including main)."""
    ml_back, ml_fwd = bezier_ik_subs_split_by_modifier(ml_subs)
    if i_main == 0:
        return list(ml_fwd)
    if i_main == int_last:
        return list(ml_back)
    return list(ml_back) + list(ml_fwd)


def bezier_ik_pickwalk_append_main_index(ml_out, i_main, int_last, mMain, ml_subs):
    """
    Append one main anchor to aggregate IK pickwalk:
    base + forward; mid back + main + forward; end back + end main.
    """
    ml_back, ml_fwd = bezier_ik_subs_split_by_modifier(ml_subs or [])
    if i_main == 0:
        ml_out.append(mMain)
        ml_out.extend(ml_fwd)
    elif i_main == int_last:
        ml_out.extend(ml_back)
        ml_out.append(mMain)
    else:
        ml_out.extend(ml_back)
        ml_out.append(mMain)
        ml_out.extend(ml_fwd)


def bezier_ik_connect_main_sub_msglists_for_mains(
        ml_mains, md_subs_by_slot, m_control_ik_base=None, m_control_ik_end=None):
    """Per-section or single-chain: each main DAG gets ordered bezierIKSubs."""
    if not ml_mains:
        return
    m_base = m_control_ik_base or ml_mains[0]
    m_end = m_control_ik_end or ml_mains[-1]
    int_last = len(ml_mains) - 1
    for i, mMain in enumerate(ml_mains):
        str_slot = rig_shapes_bezier_main_slot_key(
            mMain, ml_mains, m_base, m_end)
        ml_subs = (md_subs_by_slot or {}).get(str_slot) or []
        if not ml_subs:
            continue
        ml_ordered = bezier_ik_subs_pickwalk_order_for_anchor(
            i, int_last, ml_subs)
        ml_ordered = [m for m in ml_ordered if _bezier_ik_pickwalk_dag(m)]
        if ml_ordered:
            mMain.msgList_connect(
                BEZIER_IK_MAIN_SUB_MSGLIST,
                [mObj.mNode for mObj in ml_ordered])


def bezier_ik_connect_main_sub_msglists(mRigNull, md_subs_by_slot):
    """
    Each main bezier IK DAG owns bezierIKSubs msgList (ordered subs) at rig_controls build.
    """
    m_base = mRigNull.getMessageAsMeta('controlIKBase')
    ml_mid = bezier_ik_mid_controls_from_rigNull(mRigNull)
    m_end = mRigNull.getMessageAsMeta('controlIK')
    ml_mains = bezier_ik_bezier_main_ik_list(m_base, ml_mid, m_end)
    bezier_ik_connect_main_sub_msglists_for_mains(
        ml_mains, md_subs_by_slot, m_base, m_end)


def controller_getDat_ik_merge_bezier_msglist(ml_ik, mRigNull,
                                              str_msglist='controlsIK'):
    """
    Keep legacy controller_getDat checkList entries; append built pickwalk order
    from rigNull msgList (dedupe by long name).
    """
    ml_built = mRigNull.msgList_get(str_msglist) or []
    if not ml_built:
        return list(ml_ik or [])
    set_built = {m.p_nameLong for m in ml_built}
    ml_out = [m for m in (ml_ik or []) if m.p_nameLong not in set_built]
    ml_out.extend(ml_built)
    return ml_out


def bezier_ik_rig_controls_build_controls_ik(
        mRigNull,
        md_subs_by_slot=None,
        m_neck_root=None,
        str_aggregate_msglist=BEZIER_IK_AGGREGATE_MSGLIST_SEGMENT):
    """
    Build ordered bezier IK pickwalk on rigNull (controlsIK / controlsNeckBezier / …)
    + flat bezierIKSubControls. Call after MODULECONTROL.register + reinit.
    """
    bezier_ik_connect_main_sub_msglists(mRigNull, md_subs_by_slot)

    m_base = mRigNull.getMessageAsMeta('controlIKBase')
    ml_mid = bezier_ik_mid_controls_from_rigNull(mRigNull)
    m_end = mRigNull.getMessageAsMeta('controlIK')
    ml_mains = bezier_ik_bezier_main_ik_list(m_base, ml_mid, m_end)

    ml_pickwalk = bezier_ik_pickwalk_controls(mRigNull)
    if m_neck_root and _bezier_ik_pickwalk_dag(m_neck_root):
        ml_pickwalk = [m_neck_root] + list(ml_pickwalk)

    ml_dags = bezier_ik_filter_pickwalk_dags(ml_pickwalk, ml_mains)
    if ml_dags:
        mRigNull.msgList_connect(
            str_aggregate_msglist,
            [mObj.mNode for mObj in ml_dags])

    set_main_longs = {m.p_nameLong for m in ml_mains if m}
    if m_neck_root:
        set_main_longs.add(m_neck_root.p_nameLong)
    ml_subs_flat = [
        m for m in ml_dags if m.p_nameLong not in set_main_longs]
    if ml_subs_flat:
        mRigNull.msgList_connect(
            'bezierIKSubControls',
            [mObj.mNode for mObj in ml_subs_flat])
    return ml_dags


def bezier_ik_subs_split_by_modifier(ml_subs):
    ml_back, ml_fwd = [], []
    for mSub in ml_subs or []:
        _name_mod = None
        if mc.attributeQuery('cgmNameModifier', node=mSub.mNode, exists=True):
            _name_mod = ATTR.get(mSub.mNode, 'cgmNameModifier')
        if _name_mod == 'back':
            ml_back.append(mSub)
        elif _name_mod == 'forward':
            ml_fwd.append(mSub)
    return ml_back, ml_fwd


def bezier_ik_pickwalk_controls(mRigNull, md_subs_by_slot=None):
    """
    IK pickwalk order along the bezier chain:
    base, base_forward, mid1_back, mid1, mid1_forward, …, end_back, end.
    """
    mBase = mRigNull.getMessageAsMeta('controlIKBase')
    ml_mid = bezier_ik_mid_controls_from_rigNull(mRigNull)
    mEnd = mRigNull.getMessageAsMeta('controlIK')
    ml_mains = bezier_ik_bezier_main_ik_list(mBase, ml_mid, mEnd)
    if not ml_mains:
        return []

    md_subs = dict(md_subs_by_slot or {})
    if not md_subs:
        for mMain in ml_mains:
            str_slot = rig_shapes_bezier_main_slot_key(mMain, ml_mains, mBase, mEnd)
            str_attr = bezier_ik_slot_msglist_attr(str_slot)
            if mRigNull.msgList_exists(str_attr):
                md_subs[str_slot] = mRigNull.msgList_get(str_attr) or []

    ml_out = []
    int_last = len(ml_mains) - 1
    for i, mMain in enumerate(ml_mains):
        str_slot = rig_shapes_bezier_main_slot_key(mMain, ml_mains, mBase, mEnd)
        ml_subs_on_main = mMain.msgList_get(BEZIER_IK_MAIN_SUB_MSGLIST)
        if ml_subs_on_main:
            ml_subs = ml_subs_on_main
        else:
            ml_subs = md_subs.get(str_slot, []) or []
        bezier_ik_pickwalk_append_main_index(ml_out, i, int_last, mMain, ml_subs)
    return ml_out


def bezier_ik_reinit_session_meta(self):
    """Re-wrap bezier IK session meta after MODULECONTROL.register."""
    def _reinit(ml_handles):
        ml_out = []
        for mObj in ml_handles or []:
            if not mObj:
                continue
            mFresh = cgmMeta.reinitializeMetaClass(mObj)
            ml_out.append(mFresh if mFresh else mObj)
        return ml_out

    self.ml_bezierIKSubControls = _reinit(self.ml_bezierIKSubControls)
    self.ml_bezierIKTrackCurves = _reinit(self.ml_bezierIKTrackCurves)
    md_subs = {}
    for str_slot, ml_subs in (self.md_bezierIKSubsBySlot or {}).items():
        md_subs[str_slot] = _reinit(ml_subs)
    self.md_bezierIKSubsBySlot = md_subs


def rig_shapes_bezier_ik_subs(self, ml_fkShapes, ml_fkCastTargets, mHandleFactory):
    """Bezier tangent sub-handles (ikBezierSub) for rig_shapes; rig_controls registers later."""
    mRigNull = self.mRigNull
    mBlock = self.mBlock
    self.ml_bezierIKSubControls = []
    self.ml_bezierIKTrackCurves = []
    self.md_bezierIKSubsBySlot = {}

    mControlIK = mRigNull.getMessageAsMeta('controlIK')
    mControlIKBase = mRigNull.getMessageAsMeta('controlIKBase')

    ml_bezierMainIK = bezier_ik_bezier_main_ik_list(
        mControlIKBase, self.ml_ikMidControls, mControlIK)

    if len(ml_bezierMainIK) < 2:
        return

    str_shape_mode = block_ik_bezier_control_shape(mBlock)
    offset = getattr(self, 'v_offset', None)
    aim_vector = (
        rig_shapes_bezier_cast_aim_vector(self)
        if str_shape_mode == 'segmentHandle' else None)

    f_mainIkScale = 1.2
    f_subScale = f_mainIkScale

    for i, mMain in enumerate(ml_bezierMainIK):
        v_main = mMain.p_position
        l_sub_defs = []
        if i == 0:
            l_sub_defs.append(('forward', ml_bezierMainIK[i + 1].p_position))
        elif i == len(ml_bezierMainIK) - 1:
            l_sub_defs.append(('back', ml_bezierMainIK[i - 1].p_position))
        else:
            l_sub_defs.append(('back', ml_bezierMainIK[i - 1].p_position))
            l_sub_defs.append(('forward', ml_bezierMainIK[i + 1].p_position))

        fk_idx = rig_shapes_bezier_main_fk_idx(
            self, mMain, mRigNull, mBlock, ml_fkCastTargets, ml_fkShapes,
            mControlIK, mControlIKBase)
        ml_subs = []

        for str_nameMod, v_neighbor in l_sub_defs:
            mSub = mMain.doCreateAt(setClass=True)
            mSub.p_position = rig_shapes_bezier_sub_pos(v_main, v_neighbor)
            mSub.doCopyNameTagsFromObject(
                mMain.mNode,
                ignore=['cgmType', 'cgmTypeModifier', 'cgmNameModifier', 'cgmAlias'])
            mSub.doStore('cgmTypeModifier', 'ikBezierSub')
            mSub.doStore('cgmNameModifier', str_nameMod)
            mSub.doStore('cgmType', 'handle')
            mSub.doName()

            if str_shape_mode == 'segmentHandle':
                rig_shapes_bezier_segment_handle_shape(
                    self, mSub, mHandleFactory, aim_vector, offset,
                    scale=f_subScale, control_type='accent')
            else:
                rig_shapes_bezier_ik_shape_from_fk(
                    self, mSub, ml_fkShapes[fk_idx], 'sphere', mSub, f_subScale)
                mBlock.asHandleFactory(mSub.mNode).color(
                    mSub.mNode, controlType='accent')
            mSub.p_parent = mMain

            mTrackCrv = rig_shapes_bezier_main_to_sub_track(
                self, mMain, mSub, str_nameMod, mHandleFactory)
            self.ml_bezierIKTrackCurves.append(mTrackCrv)

            ml_subs.append(mSub)
            self.ml_bezierIKSubControls.append(mSub)

        str_slot = rig_shapes_bezier_main_slot_key(
            mMain, ml_bezierMainIK, mControlIKBase, mControlIK)
        self.md_bezierIKSubsBySlot[str_slot] = ml_subs
        mRigNull.msgList_connect(
            bezier_ik_slot_msglist_attr(str_slot),
            [mObj.mNode for mObj in ml_subs])

    if self.ml_bezierIKSubControls:
        mRigNull.msgList_connect(
            'bezierIKSubControls',
            [mObj.mNode for mObj in self.ml_bezierIKSubControls])
    if self.ml_bezierIKTrackCurves:
        mRigNull.msgList_connect(
            'bezierIKTrackCurves',
            [mObj.mNode for mObj in self.ml_bezierIKTrackCurves])


def bezier_ik_block_twist_world_up_vectors(mBlock):
    """Block ikSplineTwistUpStart/End enums → (v_start, v_end) for spline IK WU vectors."""
    if not mBlock or not mBlock.hasAttr('ikSplineTwistUpStart'):
        return None, None
    _str_start = mBlock.getEnumValueString('ikSplineTwistUpStart')
    _str_end = mBlock.getEnumValueString('ikSplineTwistUpEnd')
    if not _str_start or not _str_end:
        return None, None
    return (
        VALID.simpleAxis(_str_start).p_vector,
        VALID.simpleAxis(_str_end).p_vector)


def bezier_ik_connect_spline_advanced_twist(
        mDriverCurve,
        mIKHandle,
        mBlock,
        d_orientation,
        mWorldUpStart,
        mWorldUpEnd,
        str_mainRotAxis=None,
        wire_driver_twist_from_mains=False,
        v_worldUpStart=None,
        v_worldUpEnd=None):
    """
    Driver twistStart/End (optional) + ikSpline advanced twist: Object Rotation Up
    (Start/End), dForwardAxis / dWorldUpAxis, WU matrices from start/end controls.

    Segment/Head: call after RIGFRAME.bezier twistEndAdd wiring (wire_driver_twist_from_mains=False).
    Limb roll sections: wire_driver_twist_from_mains=True (direct r-axis from section mains).
    """
    _str_func = 'bezier_ik_connect_spline_advanced_twist'
    if not mDriverCurve or not mIKHandle:
        return
    if not mWorldUpStart or not mWorldUpEnd:
        log.warning(cgmGEN.logString_msg(
            _str_func, 'skip | missing world up start/end controls'))
        return

    _str_twist = str_mainRotAxis
    if not _str_twist and mBlock and mBlock.hasAttr('ikSplineTwistAxis'):
        _str_twist = mBlock.getEnumValueString('ikSplineTwistAxis')
    if not _str_twist:
        _str_twist = (d_orientation or {}).get('str', 'xyz')[2]

    if wire_driver_twist_from_mains:
        if mDriverCurve.hasAttr('twistStart'):
            NODEFACTORY.argsToNodes(
                '{0}.twistStart = {1}.r{2}'.format(
                    mDriverCurve.mNode, mWorldUpStart.mNode, _str_twist)).doBuild()
        if mDriverCurve.hasAttr('twistEnd'):
            NODEFACTORY.argsToNodes(
                '{0}.twistEnd = {1}.r{2}'.format(
                    mDriverCurve.mNode, mWorldUpEnd.mNode, _str_twist)).doBuild()
        if mDriverCurve.hasAttr('twistType'):
            ATTR.set_default(mDriverCurve.mNode, 'twistType', 1)
            ATTR.set(mDriverCurve.mNode, 'twistType', 1)

    if v_worldUpStart is None and v_worldUpEnd is None and mBlock:
        v_worldUpStart, v_worldUpEnd = bezier_ik_block_twist_world_up_vectors(mBlock)

    _d_orient = d_orientation or {}
    _str_fwd = _d_orient.get('stringAim') or '{0}+'.format(_d_orient.get('str', 'zyx')[0])
    _str_up = _d_orient.get('stringUp') or '{0}+'.format(_d_orient.get('str', 'zyx')[1])
    try:
        mFwd = VALID.simpleAxis(_str_fwd)
        mUp = VALID.simpleAxis(_str_up)
        if v_worldUpStart is not None or v_worldUpEnd is not None:
            log.info(cgmGEN.logString_msg(
                _str_func,
                'WU vectors start={0} end={1}'.format(v_worldUpStart, v_worldUpEnd)))
        RIGDYN._apply_hair_spline_ik_advanced_twist(
            mIKHandle,
            mFwd,
            mUp,
            mWorldUpStart,
            mWorldUpEnd,
            v_worldUpStart=v_worldUpStart,
            v_worldUpEnd=v_worldUpEnd)
    except Exception as err:
        log.warning(cgmGEN.logString_msg(_str_func, 'advanced WU | {0}'.format(err)))
