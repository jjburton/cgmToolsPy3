"""
MRS block-level Bezier IK helpers (shapes, controls pickwalk, stretch aim, squash compensate).

Shared by Segment, Head neck, and Limb bezier paths. Solver math lives in ik_utils / bezier_utils.
"""
import copy
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
import cgm.core.rig.constraint_utils as RIGCONSTRAINT
import cgm.core.rig.constraint_utils as CONSTRAINT

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
    Inflate `{rigJoint}_inflateScale` above direct rig controls (FK-visible).

    `ml_blendJoints` arg is the per-index DAG parent for the inflate null:
    **blendJoints** when `segmentType=parent`, **segmentJoints** when segment
    bezier deform drives seg chain.

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

    return segment_inflate_parent_direct_controls(
        d_stretch_res, aim_axis, l_entries)


def segment_inflate_parent_direct_controls(d_stretch_res, aim_axis, l_entries):
    """Segment / limb: wire ``{rig}_inflateScale`` above direct rig controls."""
    return bezier_inflate_parent_direct_controls(d_stretch_res, aim_axis, l_entries)


def segment_inflate_parent_rig_direct_controls(
        mRigNull, d_stretch_res, ml_parent_joints, ml_rigJoints, aim_axis):
    """
    Segment block: parent inflate nulls on ``ml_parent_joints`` (blend or seg chain),
    re-parent each rig direct's masterGroup. Expects ``l_inflateDirectPlugs`` on
    ``d_stretch_res`` (from ``bezier_spline_stretch`` or ``segment_inflate_stretch_result_from_volume_joints``).
    """
    return bezier_inflate_parent_segment_direct_controls(
        mRigNull, d_stretch_res, ml_parent_joints, ml_rigJoints, aim_axis)


def _segment_inflate_volume_plug_from_ik_joint(m_jnt, l_volume_scale):
    """First live driver on volume scale attrs (ribbon legacy may use scaleX/Y)."""
    m_jnt = cgmMeta.validateObjArg(m_jnt, 'cgmObject', noneValid=True)
    if not m_jnt:
        return None
    l_tried = []
    for str_attr in l_volume_scale:
        l_tried.append(str_attr)
        str_plug = ATTR.get_driver('{0}.{1}'.format(m_jnt.mNode, str_attr))
        if str_plug:
            return str_plug
    for str_attr in ('scaleX', 'scaleY', 'scaleZ'):
        if str_attr in l_tried:
            continue
        str_plug = ATTR.get_driver('{0}.{1}'.format(m_jnt.mNode, str_attr))
        if str_plug:
            return str_plug
    return None


_SEGMENT_INFLATE_OVERLAY_SEGMENT_TYPES = (
    'parent', 'ribbon', 'ribbonLive', 'spline', 'curve', 'bezier', 'linear')

# Segment deform ribbon is built in rig_segments (after rig_frame); inflate must wire there.
_SEGMENT_INFLATE_AFTER_DEFORM_RIBBON_TYPES = ('ribbon', 'ribbonLive')


def segment_inflate_direct_parent_joint_list(mRigNull, str_segment_type):
    """DAG parent for `{rig}_inflateScale` — blend on parent segment, else segmentJoints."""
    if not mRigNull:
        return []
    if str_segment_type == 'parent':
        return mRigNull.msgList_get('blendJoints') or []
    return mRigNull.msgList_get('segmentJoints') or []


def segment_inflate_result_from_module_volume(
        self_seg, mBlock, mRigNull, mSettings, ml_volume_joints,
        leave_joint_volume_wiring=True):
    """
    ``rig_inflate`` only: inflate settings + direct-parent plugs from volume
    already on ``ml_volume_joints`` (stretch built in rig_frame / rig_segments).
    """
    if not block_squash_inflate_control(mBlock) or not self_seg.b_squashSetup:
        return None
    ml_volume_joints = cgmMeta.validateObjListArg(
        ml_volume_joints, 'cgmObject', noneValid=True) or []
    mSettings = cgmMeta.validateObjArg(mSettings, noneValid=True)
    if not ml_volume_joints or not mSettings:
        return None
    _d_ss = getattr(self_seg, 'd_squashStretch', None) or {}
    _f_inf_min, _f_inf_max = block_squash_inflate_factor_min_max(mBlock, _d_ss)
    _str_inf_mode = _d_ss.get(
        'squashInflateFactorMode',
        block_squash_inflate_factor_mode(mBlock, 'midPeak'))
    str_part = self_seg.d_module['partName']
    return segment_inflate_stretch_result_from_volume_joints(
        ml_volume_joints,
        mSettings,
        segment_squash_stretch_aim_axis(self_seg),
        '{0}_segInflate'.format(str_part),
        inflate_factor_min=_f_inf_min,
        inflate_factor_max=_f_inf_max,
        inflate_factor_mode=_str_inf_mode,
        inflate_factor_base_name='{0}_inflate'.format(str_part),
        parentGutsTo=mRigNull,
        extra_keyable=True,
        leave_joint_volume_wiring=leave_joint_volume_wiring)


def segment_inflate_stretch_result_from_volume_joints(
        ml_volume_joints,
        mSettings,
        aim_axis,
        str_base,
        inflate_factor_min=0.0,
        inflate_factor_max=1.0,
        inflate_factor_mode='midPeak',
        inflate_factor_base_name=None,
        parentGutsTo=None,
        extra_keyable=True,
        leave_joint_volume_wiring=False):
    """
    Build inflate factor plugs for direct rig controls when volume squash already
    exists on a joint chain (ribbon **segmentJoints**, curve IK joints, etc.).

    ``leave_joint_volume_wiring=True`` for ribbon segment deform: read existing
    ribbon squash drivers only — do not reconnect segment joint scale (inflate
    rides on direct-parent nulls).

    Returns the same shape as ``bezier_spline_stretch`` inflate slice for
    ``segment_inflate_parent_rig_direct_controls``.
    """
    import cgm.core.rig.ik_utils as IKUTIL

    _str_func = 'segment_inflate_stretch_result_from_volume_joints'
    ml_volume_joints = cgmMeta.validateObjListArg(
        ml_volume_joints, 'cgmObject', noneValid=True) or []
    mSettings = cgmMeta.validateObjArg(mSettings, noneValid=True)
    if len(ml_volume_joints) < 2 or not mSettings:
        log.info(cgmGEN.logString_msg(_str_func, 'skip | joints or settings missing'))
        return None

    _, _, l_volume_scale = IKUTIL._bezier_stretch_axis_data(aim_axis)
    str_inflate_factor_base = inflate_factor_base_name or str_base

    mPlug_inflate, mPlug_inflate_offset = (
        IKUTIL._bezier_stretch_settings_inflate_plugs(mSettings, extra_keyable))
    int_inflate_max_factor_idx = IKUTIL._bezier_stretch_inflate_max_factor_index(
        len(ml_volume_joints), None)
    d_inflate_offset_shared = IKUTIL._bezier_stretch_inflate_offset_shared(
        str_base, mPlug_inflate_offset, int_inflate_max_factor_idx)
    ml_inflate_dg = list(d_inflate_offset_shared.get('ml_nodes') or [])

    l_inflate_factors = MATH.get_blendList(
        len(ml_volume_joints), inflate_factor_max, inflate_factor_min,
        inflate_factor_mode)
    log.info(cgmGEN.logString_msg(
        _str_func,
        'inflateFactor ramp ({0}) mode:{1} min:{2} max:{3}'.format(
            len(ml_volume_joints), inflate_factor_mode,
            inflate_factor_min, inflate_factor_max)))

    md_inflate_factor_plugs = IKUTIL._bezier_stretch_inflate_factor_plugs_ensure(
        mSettings, str_inflate_factor_base, l_inflate_factors,
        int_inflate_max_factor_idx, extra_keyable)

    l_indices_with_volume = []
    for int_i, m_jnt in enumerate(ml_volume_joints[:-1]):
        if _segment_inflate_volume_plug_from_ik_joint(m_jnt, l_volume_scale):
            l_indices_with_volume.append(int_i)
    if not l_indices_with_volume:
        log.info(cgmGEN.logString_msg(
            _str_func, 'skip wiring | no volume drivers on joint chain'))
        return None

    l_inflate_direct_plugs = []
    str_inflate_shift = d_inflate_offset_shared.get('str_shift')

    for int_i, m_jnt in enumerate(ml_volume_joints[:-1]):
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
        if leave_joint_volume_wiring:
            l_inflate_direct_plugs.append({
                'i': int_i,
                'str_plug': str_inflate_scale,
            })
        else:
            IKUTIL._bezier_stretch_connect_inflate_joint_or_direct(
                m_jnt, l_volume_scale, str_vol_scale, str_inflate_scale,
                True, l_inflate_direct_plugs, int_i)

    if len(ml_volume_joints) >= 1:
        int_tip = len(ml_volume_joints) - 1
        m_tip = ml_volume_joints[int_tip]
        str_tip_vol = _segment_inflate_volume_plug_from_ik_joint(
            m_tip, l_volume_scale)
        if not str_tip_vol and int_tip > 0:
            str_tip_vol = _segment_inflate_volume_plug_from_ik_joint(
                ml_volume_joints[int_tip - 1], l_volume_scale)
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
            if leave_joint_volume_wiring:
                l_inflate_direct_plugs.append({
                    'i': int_tip,
                    'str_plug': str_inflate_scale,
                })
            else:
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
    """Map block ikSplineBezierMode enum to IK.bezier_spline bezierAnchorMode (uniform | bend)."""
    if not mBlock:
        return 'uniform'
    _attr = 'ikSplineBezierMode'
    if not mBlock.hasAttr(_attr) and mBlock.hasAttr('splineBezierMode'):
        _attr = 'splineBezierMode'
    if mBlock.hasAttr(_attr):
        _mode = mBlock.getEnumValueString(_attr)
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


def rig_shapes_bezier_module_joint_spacing_chain(mRigNull):
    import cgm.core.mrs.lib.builder_utils as BUILDUTILS
    return BUILDUTILS.segment_handle_cast_spacing_joint_chain(mRigNull)


def rig_shapes_bezier_segment_handle_semisphere_size(
        mBlock, offset, scale=1.0, ml_chain=None, mRigNull=None):
    import cgm.core.mrs.lib.builder_utils as BUILDUTILS
    return BUILDUTILS.segment_handle_cast_semisphere_size(
        mBlock, mRigNull, offset, ml_chain=ml_chain, scale=scale)


def rig_shapes_bezier_segment_handle_shape(
        self, mObj, mHandleFactory, aim_vector, offset, scale=1.0,
        control_type='accent', ml_chain=None):
    """limbSegmentHandle semiSphere cast (limb bezier subs / neck handleJoints style)."""
    mBlock = self.mBlock
    f_size = rig_shapes_bezier_segment_handle_semisphere_size(
        mBlock, offset, scale, ml_chain=ml_chain, mRigNull=self.mRigNull)
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
    m_chain_start = mRigNull.getMessageAsMeta('bezierIKChainStart')
    m_chain_end = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    if m_chain_start and mMain == m_chain_start:
        if segment_bezier_ik_uses_hips_chain_mains(mBlock):
            return 0
        return min(int_seg_base, len(ml_fkShapes) - 1)
    if m_chain_end and mMain == m_chain_end:
        idx = int_handle_end
        if abs(idx) > len(ml_fkShapes):
            idx = -1
        return idx
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


def rig_shapes_bezier_ik_apply_from_fk(
        self, ml_fkShapes, ml_fkCastTargets, mHandleFactory, skip_base_end=False):
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

    if not skip_base_end:
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


def rig_shapes_bezier_segment_hips_chain_mains(
        self, ml_fkJoints, ml_fkShapes, mHandleFactory, ml_ikJoints=None):
    """
    Segment ikSetup=bezier + ikBase=hips: bezier mains on FK chain ends (not prerig IK helpers).
    Hip/chest controlIKBase/controlIK keep ribbon-style shapes from ik_base / ik_end.
    rig_shapes: snap chain start/end to ikJoints ends (masterGroup parenting at rig_frame).
    """
    _str_func = 'rig_shapes_bezier_segment_hips_chain_mains'
    mRigNull = self.mRigNull
    mBlock = self.mBlock
    if not ml_fkJoints or not ml_fkShapes:
        log.warning(cgmGEN.logString_msg(_str_func, 'skip | missing fk joints/shapes'))
        return
    if not ml_ikJoints:
        ml_ikJoints = mRigNull.msgList_get('ikJoints', asMeta=True)
    if not ml_ikJoints:
        log.warning(cgmGEN.logString_msg(_str_func, 'skip | missing ikJoints'))
        return

    int_handle_end = getattr(self, 'int_handleEndIdx', -1)
    str_shape_mode = block_ik_bezier_control_shape(mBlock)
    offset = getattr(self, 'v_offset', None)

    m_ik_start = ml_ikJoints[0]
    m_shape_start = ml_fkShapes[0]

    idx_end = int_handle_end
    if abs(idx_end) > len(ml_ikJoints):
        idx_end = -1
    idx_shape_end = int_handle_end
    if abs(idx_shape_end) > len(ml_fkShapes):
        idx_shape_end = -1
    m_ik_end = ml_ikJoints[idx_end]
    m_shape_end = ml_fkShapes[idx_shape_end]

    l_build = (
        ('bezierIKChainStart', m_ik_start, m_ik_start, m_shape_start),
        ('bezierIKChainEnd', m_ik_end, m_ik_end, m_shape_end),
    )

    for str_msg, m_snap, m_name_src, m_fk_shape in l_build:
        mMain = m_snap.doCreateAt(setClass=True)
        mMain.doSnapTo(m_snap)
        mMain.doCopyNameTagsFromObject(
            m_name_src.mNode,
            ignore=['cgmType', 'cgmTypeModifier', 'cgmNameModifier', 'cgmAlias'])
        mMain.doStore('cgmNameModifier', 'bezierChain')
        if str_shape_mode == 'segmentHandle':
            rig_shapes_bezier_main_cube_cast_sized(
                self, mMain, m_fk_shape, offset=offset)
        else:
            rig_shapes_bezier_ik_cube_from_fk(
                self, mMain, m_snap, m_fk_shape)
        rig_shapes_bezier_main_ik_type(mMain, mHandleFactory)
        mRigNull.connectChildNode(mMain, str_msg, 'rigNull')
        log.info(cgmGEN.logString_msg(
            _str_func, '{0} | {1}'.format(str_msg, mMain.p_nameShort)))


def rig_frame_bezier_segment_hips_chain_master_groups(mRigNull, mBlock):
    """
    Hips bezier chain: parent chain start/end MODULECONTROL masterGroups under
    controlIKBase and controlIK (after those IK controls are on the IK group).
    """
    _str_func = 'rig_frame_bezier_segment_hips_chain_master_groups'
    if not segment_bezier_ik_uses_hips_chain_mains(mBlock):
        return

    m_ik_base = mRigNull.getMessageAsMeta('controlIKBase')
    m_ik_end = mRigNull.getMessageAsMeta('controlIK')
    m_chain_start = mRigNull.getMessageAsMeta('bezierIKChainStart')
    m_chain_end = mRigNull.getMessageAsMeta('bezierIKChainEnd')

    l_pairs = (
        (m_chain_start, m_ik_base, 'bezierIKChainStart', 'controlIKBase'),
        (m_chain_end, m_ik_end, 'bezierIKChainEnd', 'controlIK'),
    )
    for m_chain, m_ik_parent, str_chain, str_ik in l_pairs:
        if not m_chain or not m_ik_parent:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'skip | missing {0} or {1}'.format(str_chain, str_ik)))
            continue
        m_master = m_chain.masterGroup
        if not m_master:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'skip | no masterGroup on {0}'.format(
                    m_chain.p_nameShort)))
            continue
        m_master.p_parent = m_ik_parent
        log.info(cgmGEN.logString_msg(
            _str_func,
            '{0}.masterGroup -> {1}'.format(
                m_chain.p_nameShort, m_ik_parent.p_nameShort)))


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
    return segment_squash_stretch_aim_axis(self)


def segment_squash_stretch_aim_axis(self):
    """Volume squash / inflate aim axis for segment blocks (not rotate-order string)."""
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


def segment_bezier_ik_uses_hips_chain_mains(mBlock):
    """Segment ikSetup=bezier + ikBase=hips: hip/chest IK + separate chain bezier mains."""
    if not mBlock or not mBlock.ikSetup:
        return False
    if mBlock.getEnumValueString('ikSetup') != 'bezier':
        return False
    if mBlock.getEnumValueString('ikBase') != 'hips':
        return False
    return True


def segment_bezier_ik_mid_span_drivers(mRigNull, md_subs_by_slot=None):
    """
    Bezier module IK mid follow: span between chain start/end mains.
    Drivers = start main forward sub + end main back sub (fallback to mains).
    """
    ml_mains = bezier_ik_resolve_main_ik_list(mRigNull)
    if len(ml_mains) < 2:
        return None
    m_start = ml_mains[0]
    m_end = ml_mains[-1]
    m_slot_base = (
        mRigNull.getMessageAsMeta('bezierIKChainStart')
        or mRigNull.getMessageAsMeta('controlIKBase'))
    m_slot_end = (
        mRigNull.getMessageAsMeta('bezierIKChainEnd')
        or mRigNull.getMessageAsMeta('controlIK'))
    md_subs = dict(md_subs_by_slot or {})
    if not md_subs:
        for mMain in ml_mains:
            str_slot = rig_shapes_bezier_main_slot_key(
                mMain, ml_mains, m_slot_base, m_slot_end)
            str_attr = bezier_ik_slot_msglist_attr(str_slot)
            if mRigNull.msgList_exists(str_attr):
                md_subs[str_slot] = mRigNull.msgList_get(str_attr) or []
    str_slot_start = rig_shapes_bezier_main_slot_key(
        m_start, ml_mains, m_slot_base, m_slot_end)
    str_slot_end = rig_shapes_bezier_main_slot_key(
        m_end, ml_mains, m_slot_base, m_slot_end)
    _ml_back_s, ml_fwd_s = bezier_ik_subs_split_by_modifier(
        md_subs.get(str_slot_start, []))
    ml_back_e, _ml_fwd_e = bezier_ik_subs_split_by_modifier(
        md_subs.get(str_slot_end, []))
    m_fwd = ml_fwd_s[0] if ml_fwd_s else m_start
    m_back = ml_back_e[0] if ml_back_e else m_end
    return m_fwd, m_back, m_start, m_end, ml_mains


def segment_bezier_module_ik_mid_setup(
        self, mIKGroup, mIKBaseControl, mIKControl, ml_ikJoints):
    """
    Segment ikSetup=bezier + parent (module bezier mains): honor ikMidSetup using
    bezier start/end span drivers (not ribbonIKDrivers). Matches limb bezier mid contract.
    """
    import cgm.core.rig.ik_utils as IK
    import cgm.core.mrs.lib.blockShapes_utils as BLOCKSHAPES

    _str_func = 'segment_bezier_module_ik_mid_setup'
    mBlock = self.mBlock
    mRigNull = self.mRigNull
    mModule = self.mModule
    ml_handles = self.ml_ikMidControls or []
    if not ml_handles:
        return

    _str_mode = mBlock.getEnumValueString('ikMidSetup')
    if _str_mode == 'none':
        return

    _span = segment_bezier_ik_mid_span_drivers(
        mRigNull, getattr(self, 'md_bezierIKSubsBySlot', None))
    if not _span:
        log.warning(cgmGEN.logString_msg(
            _str_func, 'skip | need 2+ bezier mains on rigNull'))
        return
    m_fwd, m_back, m_start, m_end, _ml_mains = _span
    ml_span_drivers = [m_fwd, m_back]

    log.info(cgmGEN.logString_msg(
        _str_func,
        'ikMidSetup={0} | mids={1} | span {2} -> {3}'.format(
            _str_mode,
            len(ml_handles),
            m_fwd.p_nameShort,
            m_back.p_nameShort)))

    _base = '{0}_midBezier'.format(self.d_module['partName'])

    for mHandle in ml_handles:
        mHandle.masterGroup.parent = mIKGroup
        mDriver = mHandle.doCreateAt('joint', setClass='cgmObject')
        mDriver.rename('{0}_mainDriver'.format(mHandle.p_nameBase))
        mDriver.p_parent = mHandle.masterGroup
        mHandle.doStore('mainDriver', mDriver.mNode, 'msg')

    if _str_mode == 'ribbon':
        ml_mid_track = [m_start] + list(ml_handles) + [m_end]
        d_mid = {
            'jointList': [mJnt.mNode for mJnt in ml_mid_track],
            'baseName': '{0}_midRibbon'.format(_base),
            'driverSetup': None,
            'squashStretch': None,
            'msgDriver': 'masterGroup',
            'specialMode': 'noStartEnd',
            'paramaterization': 'floating',
            'connectBy': 'constraint',
            'influences': ml_span_drivers,
            'moduleInstance': mModule}
        IK.ribbon(**d_mid)

    elif _str_mode == 'prntConstraint':
        _l_targets = [mObj.mNode for mObj in ml_span_drivers]
        for mHandle in ml_handles:
            _pc = mc.parentConstraint(
                _l_targets, mHandle.masterGroup.mNode, maintainOffset=True)
            _vList = DIST.get_normalizedWeightsByDistance(
                mHandle.masterGroup.mNode, _l_targets)
            CONSTRAINT.set_weightsByDistance(_pc[0], _vList)

    elif _str_mode in ['linearTrack', 'cubicTrack']:
        _track_curve, _l_clusters = CORERIG.create_at(
            [mObj.mNode for mObj in ml_span_drivers],
            _str_mode,
            baseName='{0}_mid{1}'.format(_base, _str_mode))
        m_crv = cgmMeta.asMeta(_track_curve)
        m_shape = cgmMeta.asMeta(m_crv.getShapes()[0])
        ml_clusters = cgmMeta.asMeta([s[1] for s in _l_clusters])
        for m_obj in [m_crv] + ml_clusters:
            m_obj.overrideEnabled = 1
            cgmMeta.cgmAttr(mModule.rigNull.mNode, 'gutsVis', lock=False).doConnectOut(
                '%s.%s' % (_track_curve, 'overrideVisibility'))
            cgmMeta.cgmAttr(mModule.rigNull.mNode, 'gutsLock', lock=False).doConnectOut(
                '%s.%s' % (_track_curve, 'overrideDisplayType'))
        m_crv.p_parent = mModule.rigNull.mNode
        for mHandle in ml_handles:
            BLOCKSHAPES.attachToCurve(
                mHandle,
                m_crv,
                m_shape,
                parentTo=mModule.rigNull.mNode,
                trackLink='masterGroup')
            mc.orientConstraint(
                m_fwd.mNode,
                mHandle.masterGroup.mNode,
                maintainOffset=True)
    else:
        raise ValueError(
            '{0} | unknown ikMidSetup: {1}'.format(_str_func, _str_mode))


def segment_bezier_module_ik_mid_uses_bezier_span(mBlock):
    """Segment bezier rig_frame: mid follow uses bezier mains, not ribbonIKDrivers."""
    if not mBlock or not mBlock.ikSetup:
        return False
    if mBlock.getEnumValueString('ikSetup') != 'bezier':
        return False
    if mBlock.getEnumValueString('segmentType') == 'parent':
        return True
    return segment_bezier_uses_module_ik_curve(mBlock)


def segment_ik_module_follow_end_control(m_rig_null):
    """
    Module end IK anim control for segment ``rig_frame`` follow (``rigNull.controlIK``).

    Separate from ``bezierIKChainEnd`` CV mains — hips bezier uses both; this path
    parents follow dups and ``followIK`` on the IK end control only.
    """
    if not m_rig_null:
        return None
    return m_rig_null.getMessageAsMeta('controlIK')


def segment_ik_module_follow_base_control(m_rig_null):
    """Module base IK anim control for segment ``rig_frame`` follow (``rigNull.controlIKBase``)."""
    if not m_rig_null:
        return None
    return m_rig_null.getMessageAsMeta('controlIKBase')


def segment_ik_spline_orient_follow_setup(m_skin_joint,
                                          m_spline_span_joint,
                                          m_follow_influence,
                                          str_attr='followIK',
                                          f_default=1.0,
                                          b_start=False):
    """
    Spline IK orient follow on a skin joint (tip or root).

    ``followIK`` / ``followEnd`` driver: **0** = solver span orient, **1** = follow
    the influence transform hierarchy (swapped ``blendChainsBy`` chain order).
    """
    m_skin = cgmMeta.validateObjArg(m_skin_joint, 'cgmObject', noneValid=False)
    m_span = cgmMeta.validateObjArg(m_spline_span_joint, 'cgmObject', noneValid=False)
    m_infl = cgmMeta.validateObjArg(m_follow_influence, 'cgmObject', noneValid=False)

    mc.pointConstraint([m_span.mNode], m_skin.mNode, maintainOffset=True)
    m_spline_control = m_skin.doDuplicate()
    if b_start:
        m_spline_control.rename('{0}_splineControlStart'.format(m_skin.p_nameBase))
    else:
        m_spline_control.rename('{0}_splineControl'.format(m_skin.p_nameBase))
    m_spline_control.p_parent = m_infl

    m_plug_follow = cgmMeta.cgmAttr(
        m_infl.mNode, str_attr, attrType='float', lock=False,
        keyable=True, defaultValue=f_default)
    m_plug_follow.p_value = f_default
    ATTR.set_default(m_infl.mNode, str_attr, f_default)

    log.info(cgmGEN.logString_msg(
        'segment_ik_spline_orient_follow_setup',
        '{0} on {1} | skin:{2} span:{3}'.format(
            str_attr, m_infl.p_nameShort, m_skin.p_nameShort, m_span.p_nameShort)))

    RIGCONSTRAINT.blendChainsBy(
        m_spline_control, m_span, m_skin,
        driver=m_plug_follow.p_combinedName,
        l_constraints=['orient'])
    return {
        'mSplineControl': m_spline_control,
        'mPlug_follow': m_plug_follow,
    }


def segment_ik_base_orient_follow_setup(m_segment,
                                        m_ik_pelvis,
                                        m_ik_base_control,
                                        str_attr='followIK',
                                        f_default=1.0):
    """
    Hips ``rig_frame``: ``followIK`` orient on ``*_ikOrientFrame``; ``ml_ikUse[0]`` unchanged.

    ``m_segment`` — segment block build instance (``self`` in ``rig_frame``); sets
    ``m_segment.ml_ikBlendUse[0]`` to ``*_ikOrientFrame`` for FK/IK blend.
    ``m_ik_pelvis`` — ``ml_ikJoints[0]`` / spline IK pelvis.
    ``m_ik_base_control`` — ``rigNull.controlIKBase``.

    Builds ``{pelvis}_ikOrientFrame`` under pelvis and ``{pelvis}_splineControlStart`` under
    IK base. ``blendChainsBy``: followIK **0** = spline control start, **1** = ik pelvis;
    orient constraint on ``*_ikOrientFrame``.
    """
    if not m_segment or not getattr(m_segment, 'ml_ikBlendUse', None):
        raise ValueError(
            'segment_ik_base_orient_follow_setup requires m_segment.ml_ikBlendUse '
            '(copy of ikJoints from rig_frame)')

    m_ik_pelvis = cgmMeta.validateObjArg(m_ik_pelvis, 'cgmObject', noneValid=False)
    m_ik_base_control = cgmMeta.validateObjArg(
        m_ik_base_control, 'cgmObject', noneValid=False)

    m_ik_orient_frame = m_ik_pelvis.doDuplicate(po=True, ic=False)
    m_ik_orient_frame.rename(
        '{0}_ikOrientFrame'.format(m_ik_pelvis.p_nameBase))
    m_ik_orient_frame.p_parent = m_ik_pelvis

    m_orient_follow_joint = m_ik_pelvis.doDuplicate(po=True, ic=False)
    m_orient_follow_joint.rename(
        '{0}_splineControlStart'.format(m_ik_pelvis.p_nameBase))
    m_orient_follow_joint.p_parent = m_ik_base_control

    m_plug_follow = cgmMeta.cgmAttr(
        m_ik_base_control.mNode, str_attr, attrType='float', lock=False,
        keyable=True, defaultValue=f_default)
    m_plug_follow.p_value = f_default
    ATTR.set_default(m_ik_base_control.mNode, str_attr, f_default)

    log.info(cgmGEN.logString_msg(
        'segment_ik_base_orient_follow_setup',
        '{0} on {1} | ikOrientFrame:{2} orientFollow:{3} ikPelvis:{4}'.format(
            str_attr, m_ik_base_control.p_nameShort,
            m_ik_orient_frame.p_nameShort, m_orient_follow_joint.p_nameShort,
            m_ik_pelvis.p_nameShort)))

    mc.pointConstraint(
        [m_ik_pelvis.mNode], m_ik_orient_frame.mNode, maintainOffset=True)
    RIGCONSTRAINT.blendChainsBy(
        m_orient_follow_joint,
        m_ik_pelvis,
        m_ik_orient_frame,
        driver=m_plug_follow.p_combinedName,
        l_constraints=['orient'])

    m_segment.ml_ikBlendUse[0] = m_ik_orient_frame


def segment_bezier_ik_module_chain_volume_squash(mBlock, str_segment_type):
    """
    ``ikSetup=bezier`` volume squash + settings ramp on the module **ik** chain.

    ``segmentType=parent``: IK bezier owns squash (joints follow handles).
    Any other segment deform (ribbon, segment bezier, …): squash stays on
    **segmentJoints** only; module IK gets arc-length stretch without volume.
    """
    if not mBlock or not mBlock.ikSetup:
        return False
    if mBlock.getEnumValueString('ikSetup') != 'bezier':
        return False
    return str_segment_type == 'parent'


def segment_bezier_ik_module_chain_stretch_squash_measure(
        mBlock, str_segment_type, d_squash_share=None):
    """
    ``squashStretchMain`` for module **ik** ``bezier_spline_stretch``.

    Non-**parent** segment types always use **arcLength** (no pointDist POCI on IK).
    **parent** uses block ``squashMeasure`` / shared squash kwargs.
    """
    if not segment_bezier_ik_module_chain_volume_squash(mBlock, str_segment_type):
        return 'arcLength'
    _squash_main = (
        (d_squash_share or {}).get('squashStretchMain') or 'arcLength')
    if mBlock and mBlock.squashMeasure:
        return mBlock.getEnumValueString('squashMeasure') or _squash_main
    return _squash_main


def segment_bezier_uses_module_ik_curve(mBlock):
    """segmentType=bezier + ikSetup=bezier: segment deform shares module bezierIKCurve."""
    if not mBlock:
        return False
    if mBlock.getEnumValueString('ikSetup') != 'bezier':
        return False
    if mBlock.getEnumValueString('segmentType') != 'bezier':
        return False
    return True


def bezier_ik_resolve_main_ik_list(mRigNull, ml_ik_mid_controls=None):
    """
    Bezier CV mains for wire / subs / pickwalk.
    Hips layout: bezierIKChainStart/End on FK chain ends; else controlIKBase/mids/controlIK.
    """
    if not mRigNull:
        return []
    m_chain_start = mRigNull.getMessageAsMeta('bezierIKChainStart')
    m_chain_end = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    if m_chain_start and m_chain_end:
        ml_mid = (
            ml_ik_mid_controls
            if ml_ik_mid_controls is not None
            else bezier_ik_mid_controls_from_rigNull(mRigNull))
        ml_out = [m_chain_start]
        if ml_mid:
            ml_out.extend(ml_mid)
        ml_out.append(m_chain_end)
        return ml_out
    m_base = mRigNull.getMessageAsMeta('controlIKBase')
    ml_mid = (
        ml_ik_mid_controls
        if ml_ik_mid_controls is not None
        else bezier_ik_mid_controls_from_rigNull(mRigNull))
    m_end = mRigNull.getMessageAsMeta('controlIK')
    return bezier_ik_bezier_main_ik_list(m_base, ml_mid, m_end)


def bezier_ik_main_ik_list_from_rigNull(mRigNull):
    """Base + mid + end mains from rigNull only (verify / pickwalk)."""
    return bezier_ik_resolve_main_ik_list(mRigNull)


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
    m_base = mRigNull.getMessageAsMeta('bezierIKChainStart')
    if not m_base:
        m_base = mRigNull.getMessageAsMeta('controlIKBase')
    m_end = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    if not m_end:
        m_end = mRigNull.getMessageAsMeta('controlIK')
    ml_mains = bezier_ik_resolve_main_ik_list(mRigNull)
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

    ml_mains = bezier_ik_resolve_main_ik_list(mRigNull)

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
    mBase = mRigNull.getMessageAsMeta('bezierIKChainStart')
    if not mBase:
        mBase = mRigNull.getMessageAsMeta('controlIKBase')
    mEnd = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    if not mEnd:
        mEnd = mRigNull.getMessageAsMeta('controlIK')
    ml_mains = bezier_ik_resolve_main_ik_list(mRigNull)
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
    m_slot_base = mRigNull.getMessageAsMeta('bezierIKChainStart') or mControlIKBase
    m_slot_end = mRigNull.getMessageAsMeta('bezierIKChainEnd') or mControlIK

    ml_bezierMainIK = bezier_ik_resolve_main_ik_list(
        mRigNull, self.ml_ikMidControls)

    if len(ml_bezierMainIK) < 2:
        return

    str_shape_mode = block_ik_bezier_control_shape(mBlock)
    offset = getattr(self, 'v_offset', None)
    aim_vector = (
        rig_shapes_bezier_cast_aim_vector(self)
        if str_shape_mode == 'segmentHandle' else None)
    ml_spacing_chain = rig_shapes_bezier_module_joint_spacing_chain(mRigNull)

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
                    control_type='accent',
                    ml_chain=ml_spacing_chain or ml_bezierMainIK)
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
            mMain, ml_bezierMainIK, m_slot_base, m_slot_end)
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


def segment_bezier_mains_from_handle_joints(mRigNull, mBlock=None):
    """Ordered bezier CV mains for Segment segmentType=bezier (full handleJoints chain)."""
    ml_handles = mRigNull.msgList_get('handleJoints') or []
    return list(ml_handles)


def segment_bezier_main_slot_key(mMain, ml_mains):
    """Slot id for segment handle mains: base | midN | end."""
    if not ml_mains:
        return 'mid0'
    if mMain == ml_mains[0]:
        return 'base'
    if mMain == ml_mains[-1]:
        return 'end'
    int_mid = 0
    for m in ml_mains[1:-1]:
        int_mid += 1
        if m == mMain:
            return 'mid{0}'.format(int_mid)
    return 'mid0'


def bezier_ik_pickwalk_controls_from_mains(ml_mains, md_subs_by_slot=None):
    """Pickwalk along handle mains (segment segmentType=bezier)."""
    if not ml_mains:
        return []
    ml_out = []
    int_last = len(ml_mains) - 1
    md_subs = dict(md_subs_by_slot or {})
    for i, mMain in enumerate(ml_mains):
        str_slot = segment_bezier_main_slot_key(mMain, ml_mains)
        ml_subs_on_main = mMain.msgList_get(BEZIER_IK_MAIN_SUB_MSGLIST)
        if ml_subs_on_main:
            ml_subs = ml_subs_on_main
        else:
            ml_subs = md_subs.get(str_slot, []) or []
        bezier_ik_pickwalk_append_main_index(ml_out, i, int_last, mMain, ml_subs)
    return ml_out


def bezier_ik_rig_controls_build_controls_segment_bezier(mRigNull, ml_mains, md_subs_by_slot=None):
    """Build controlsSegmentBezier pickwalk + flat bezierIKSubControls on rigNull."""
    if not ml_mains:
        return []
    bezier_ik_connect_main_sub_msglists_for_mains(
        ml_mains, md_subs_by_slot, ml_mains[0], ml_mains[-1])
    ml_pickwalk = bezier_ik_pickwalk_controls_from_mains(ml_mains, md_subs_by_slot)
    ml_dags = bezier_ik_filter_pickwalk_dags(ml_pickwalk, ml_mains)
    if ml_dags:
        mRigNull.msgList_connect(
            BEZIER_IK_AGGREGATE_MSGLIST_LIMB,
            [mObj.mNode for mObj in ml_dags])
    set_main_longs = {m.p_nameLong for m in ml_mains if m}
    ml_subs_flat = [m for m in ml_dags if m.p_nameLong not in set_main_longs]
    if ml_subs_flat:
        mRigNull.msgList_connect(
            'bezierIKSubControls',
            [mObj.mNode for mObj in ml_subs_flat])
    return ml_dags


def rig_shapes_bezier_segment_handles(self, ml_fkShapes, ml_fkCastTargets, mHandleFactory):
    """Bezier CV mains + subs on rigNull handleJoints (Segment segmentType=bezier)."""
    mRigNull = self.mRigNull
    mBlock = self.mBlock
    self.ml_bezierIKSubControls = []
    self.ml_bezierIKTrackCurves = []
    self.md_bezierIKSubsBySlot = {}

    ml_mains = segment_bezier_mains_from_handle_joints(mRigNull, mBlock)
    if len(ml_mains) < 2:
        log.warning('rig_shapes_bezier_segment_handles | need 2+ handleJoints, got {0}'.format(
            len(ml_mains)))
        return

    str_shape_mode = block_ik_bezier_control_shape(mBlock)
    offset = getattr(self, 'v_offset', None)
    aim_vector = (
        rig_shapes_bezier_cast_aim_vector(self)
        if str_shape_mode == 'segmentHandle' else None)
    ml_spacing_chain = rig_shapes_bezier_module_joint_spacing_chain(mRigNull)
    for i, mMain in enumerate(ml_mains):
        fk_idx = rig_shapes_closest_fk_shape_idx(mMain.p_position, ml_fkCastTargets)
        if str_shape_mode == 'segmentHandle':
            rig_shapes_bezier_main_cube_cast_sized(
                self, mMain, ml_fkShapes[fk_idx], offset=offset)
        else:
            rig_shapes_bezier_ik_cube_from_fk(
                self, mMain, mMain, ml_fkShapes[fk_idx], scale=1.2)
        rig_shapes_bezier_main_ik_type(mMain, mHandleFactory)

        v_main = mMain.p_position
        l_sub_defs = []
        if i == 0:
            l_sub_defs.append(('forward', ml_mains[i + 1].p_position))
        elif i == len(ml_mains) - 1:
            l_sub_defs.append(('back', ml_mains[i - 1].p_position))
        else:
            l_sub_defs.append(('back', ml_mains[i - 1].p_position))
            l_sub_defs.append(('forward', ml_mains[i + 1].p_position))

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
                    control_type='accent',
                    ml_chain=ml_spacing_chain or ml_mains)
            else:
                rig_shapes_bezier_ik_shape_from_fk(
                    self, mSub, ml_fkShapes[fk_idx], 'sphere', mSub, 1.2)
                mHandleFactory.color(mSub.mNode, controlType='accent')
            mSub.p_parent = mMain

            mTrackCrv = rig_shapes_bezier_main_to_sub_track(
                self, mMain, mSub, str_nameMod, mHandleFactory)
            self.ml_bezierIKTrackCurves.append(mTrackCrv)
            ml_subs.append(mSub)
            self.ml_bezierIKSubControls.append(mSub)

        str_slot = segment_bezier_main_slot_key(mMain, ml_mains)
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

    log.info(cgmGEN.logString_msg(
        'rig_shapes_bezier_segment_handles',
        'mains={0} subs={1} tracks={2}'.format(
            len(ml_mains),
            len(self.ml_bezierIKSubControls),
            len(self.ml_bezierIKTrackCurves))))


def rig_controls_bezier_segment_handles(
        self, mRigNull, ml_controlsAll, ml_blendJoints, ml_fkJoints,
        d_controlSpaces, mPlug_visSub):
    """MODULECONTROL register for segment handle bezier mains/subs."""
    import cgm.core.mrs.lib.ModuleControlFactory as MODULECONTROL

    _str_func = 'rig_controls_bezier_segment_handles'
    ml_mains = segment_bezier_mains_from_handle_joints(mRigNull, self.mBlock)
    if not ml_mains:
        log.warning('|{0}| >> no handle bezier mains'.format(_str_func))
        return

    d_mid_spaces = copy.copy(d_controlSpaces)
    if d_mid_spaces.get('addSpacePivots'):
        d_mid_spaces.pop('addSpacePivots')

    md_registered = {}
    for i, mMain in enumerate(ml_mains):
        _d = MODULECONTROL.register(
            mMain,
            addDynParentGroup=True,
            mirrorSide=self.d_module['mirrorDirection'],
            mirrorAxis='translateX,rotateY,rotateZ',
            makeAimable=True,
            **d_mid_spaces)
        mMain = _d['mObj']
        md_registered[mMain.mNode] = mMain
        if ml_blendJoints and i < len(ml_blendJoints):
            mMain.masterGroup.parent = ml_blendJoints[i]
        elif ml_fkJoints:
            mMain.masterGroup.parent = ml_fkJoints[min(i, len(ml_fkJoints) - 1)]
        ml_controlsAll.append(mMain)
        ATTR.connect(
            mPlug_visSub.p_combinedShortName,
            '{0}.visibility'.format(mMain.masterGroup.mNode))
        ATTR.set_hidden(mMain.mNode, 'radius', True)

    if self.d_module['mirrorDirection'] == 'Centre':
        _bezier_sub_mirror_axis = 'translateY,translateZ,rotateY,rotateZ'
    else:
        _bezier_sub_mirror_axis = 'translateX,translateY,rotateZ'

    ml_subs = (
        mRigNull.msgList_get('bezierIKSubControls')
        or self.ml_bezierIKSubControls
        or [])
    for mSub in ml_subs:
        if not mSub:
            continue
        nid = mSub.mNode
        if nid in md_registered:
            continue
        mParentMain = mSub.getParent(asMeta=True)
        _d = MODULECONTROL.register(
            mSub,
            addDynParentGroup=False,
            mirrorSide=self.d_module['mirrorDirection'],
            mirrorAxis=_bezier_sub_mirror_axis,
            makeAimable=False)
        mSub = _d['mObj']
        md_registered[nid] = mSub
        if mc.attributeQuery('radius', node=mSub.mNode, exists=True):
            ATTR.set_hidden(mSub.mNode, 'radius', True)
        if mParentMain:
            mParentMain = md_registered.get(mParentMain.mNode, mParentMain)
            mSub.masterGroup.p_parent = mParentMain
        ml_controlsAll.append(mSub)

    bezier_ik_reinit_session_meta(self)
    bezier_ik_rig_controls_build_controls_segment_bezier(
        mRigNull, ml_mains, self.md_bezierIKSubsBySlot)


def rig_controls_bezier_segment_parent_hips_chain(
        self, mRigNull, ml_controlsAll, mRootParent, ml_ikJoints,
        d_controlSpaces, mPlug_visSub):
    """
    Segment ikSetup=bezier + ikBase=hips: register chain bezier mains/subs
    as visSub handles (like segmentType=bezier handle CVs). Hip/chest controlIK*
    are registered separately as main IK.
    """
    import cgm.core.mrs.lib.ModuleControlFactory as MODULECONTROL

    _str_func = 'rig_controls_bezier_segment_parent_hips_chain'
    ml_mains = bezier_ik_resolve_main_ik_list(mRigNull, self.ml_ikMidControls)
    if len(ml_mains) < 2:
        log.warning(cgmGEN.logString_msg(_str_func, 'skip | need 2+ bezier mains'))
        return

    d_mid_spaces = copy.copy(d_controlSpaces)
    if d_mid_spaces.get('addSpacePivots'):
        d_mid_spaces.pop('addSpacePivots')

    ml_ik = ml_ikJoints or mRigNull.msgList_get('ikJoints', asMeta=True) or []
    int_handle_end = getattr(self, 'int_handleEndIdx', -1)
    m_chain_start = mRigNull.getMessageAsMeta('bezierIKChainStart')
    m_chain_end = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    str_vis_sub = mPlug_visSub.p_combinedShortName

    md_registered = {}
    for mMain in ml_mains:
        _d = MODULECONTROL.register(
            mMain,
            addDynParentGroup=True,
            mirrorSide=self.d_module['mirrorDirection'],
            mirrorAxis='translateX,rotateY,rotateZ',
            makeAimable=True,
            **d_mid_spaces)
        mMain = _d['mObj']
        md_registered[mMain.mNode] = mMain
        mMain.masterGroup.parent = mRootParent
        if ml_ik:
            if m_chain_start and mMain.p_nameLong == m_chain_start.p_nameLong:
                self.atUtils('get_switchTarget', mMain, ml_ik[0])
            elif m_chain_end and mMain.p_nameLong == m_chain_end.p_nameLong:
                idx = int_handle_end
                if abs(idx) >= len(ml_ik):
                    idx = -1
                self.atUtils('get_switchTarget', mMain, ml_ik[idx])
            else:
                self.atUtils(
                    'get_switchTarget',
                    mMain,
                    DIST.get_closestTarget(
                        mMain.mNode, [mJ.mNode for mJ in ml_ik]))
        ATTR.connect(str_vis_sub, '{0}.visibility'.format(mMain.masterGroup.mNode))
        if mc.attributeQuery('radius', node=mMain.mNode, exists=True):
            ATTR.set_hidden(mMain.mNode, 'radius', True)
        ml_controlsAll.append(mMain)

    m_start_reg = mRigNull.getMessageAsMeta('bezierIKChainStart')
    m_end_reg = mRigNull.getMessageAsMeta('bezierIKChainEnd')
    ml_mid_reg = []
    for mMain in bezier_ik_resolve_main_ik_list(mRigNull, self.ml_ikMidControls):
        if m_start_reg and mMain.p_nameLong == m_start_reg.p_nameLong:
            continue
        if m_end_reg and mMain.p_nameLong == m_end_reg.p_nameLong:
            continue
        ml_mid_reg.append(mMain)
    if ml_mid_reg:
        self.ml_ikMidControls = ml_mid_reg
        mRigNull.msgList_connect(
            'controlSegMidIK',
            [mObj.mNode for mObj in self.ml_ikMidControls])

    if self.d_module['mirrorDirection'] == 'Centre':
        _bezier_sub_mirror_axis = 'translateY,translateZ,rotateY,rotateZ'
    else:
        _bezier_sub_mirror_axis = 'translateX,translateY,translateZ'

    ml_subs = (
        mRigNull.msgList_get('bezierIKSubControls')
        or self.ml_bezierIKSubControls
        or [])
    for mSub in ml_subs:
        if not mSub:
            continue
        if mSub.mNode in md_registered:
            continue
        mParentMain = mSub.getParent(asMeta=True)
        _d = MODULECONTROL.register(
            mSub,
            addDynParentGroup=False,
            mirrorSide=self.d_module['mirrorDirection'],
            mirrorAxis=_bezier_sub_mirror_axis,
            makeAimable=False)
        mSub = _d['mObj']
        md_registered[mSub.mNode] = mSub
        if mc.attributeQuery('radius', node=mSub.mNode, exists=True):
            ATTR.set_hidden(mSub.mNode, 'radius', True)
        if mParentMain:
            mParentMain = md_registered.get(mParentMain.mNode, mParentMain)
            mSub.masterGroup.p_parent = mParentMain
        ml_controlsAll.append(mSub)

    bezier_ik_reinit_session_meta(self)
    bezier_ik_rig_controls_build_controls_ik(mRigNull, self.md_bezierIKSubsBySlot)
    log.info(cgmGEN.logString_msg(
        _str_func,
        'mains={0} subs={1}'.format(len(ml_mains), len(ml_subs))))


def _segment_bezier_should_run_spline_stretch(self, mBlock):
    if not getattr(self, 'b_scaleSetup', False):
        return False
    if not mBlock.hasAttr('squash') or not mBlock.squash:
        return True
    str_mode = mBlock.getEnumValueString('squash')
    return str_mode in ['simple', 'both', 'none']


def _segment_bezier_volume_squash_active(mBlock):
    if not mBlock.hasAttr('squash') or not mBlock.squash:
        return False
    return mBlock.getEnumValueString('squash') in ['simple', 'both']


def _segment_bezier_rig_segments_joint_chain(self, ml_segJoints, mRoot):
    """Parent segmentJoints, segMeasure scale, spline-end dup for ikSpline span."""
    for mJnt in ml_segJoints:
        mJnt.drawStyle = 2
        ATTR.set(mJnt.mNode, 'radius', 0)
        mJnt.segmentScaleCompensate = False

    ml_segJoints[0].parent = mRoot

    res_seg_scale = self.UTILS.get_blockScale(self, 'segMeasure', ml_segJoints)
    mPlug_masterScale = res_seg_scale[0]
    mMasterCurve = res_seg_scale[1]
    self.fnc_connect_toRigGutsVis(mMasterCurve)
    mMasterCurve.p_parent = mRoot

    for i, mJnt in enumerate(ml_segJoints[1:], 1):
        mJnt.p_parent = ml_segJoints[i - 1]

    ml_ik_use = copy.copy(ml_segJoints)
    m_ik_spline_end = ml_segJoints[-1].doDuplicate()
    m_ik_spline_end.rename('{0}_splineEnd'.format(ml_segJoints[-1].p_nameBase))
    ml_ik_use[-1] = m_ik_spline_end
    m_ik_spline_end.p_parent = ml_segJoints[-1].p_parent

    return ml_ik_use, m_ik_spline_end, mPlug_masterScale, mMasterCurve


def _segment_bezier_rig_segments_stretch(
        self, mBlock, mRigNull, ml_seg_joints, ml_ik_use, m_driver_curve,
        mSettings, mPlug_masterScale, d_squash_share, str_base):
    """bezier_spline_stretch on segment ik span; sets d_segmentBezierStretch."""
    import cgm.core.rig.ik_utils as IK

    if not _segment_bezier_should_run_spline_stretch(self, mBlock):
        return

    _b_volume_squash = _segment_bezier_volume_squash_active(mBlock)
    _str_aim = bezier_ik_stretch_aim_axis(self)
    _squash_main = (
        (d_squash_share or {}).get('squashStretchMain')
        or (getattr(self, 'd_squashStretch', None) or {}).get('squashStretchMain')
        or 'arcLength')
    if mBlock.squashMeasure:
        _squash_main = mBlock.getEnumValueString('squashMeasure') or _squash_main

    b_scale_stretch = self.str_segmentStretchBy == 'scale'
    # Deform chain is ml_seg_joints; ml_ik_use[-1] is a spline-end dup for ikSpline.
    if ml_seg_joints:
        for mJnt in ml_seg_joints:
            mJnt.segmentScaleCompensate = b_scale_stretch
    if ml_ik_use and ml_seg_joints:
        m_spline_end = ml_ik_use[-1]
        if m_spline_end.mNode != ml_seg_joints[-1].mNode:
            m_spline_end.segmentScaleCompensate = False

    d_stretch = IK.bezier_spline_stretch(
        jointList=[mObj.mNode for mObj in ml_ik_use],
        mDriverCurve=m_driver_curve,
        mSettings=mSettings,
        aimAxis=_str_aim,
        stretchBy=self.str_segmentStretchBy,
        globalScalePlug=mPlug_masterScale.p_combinedShortName if mPlug_masterScale else None,
        baseName=str_base,
        squashStretchMain=_squash_main,
        extraSquashControl=mBlock.squashExtraControl if _b_volume_squash else False,
        extraInflateControl=False,
        squashFactorMin=mBlock.squashFactorMin,
        squashFactorMax=mBlock.squashFactorMax,
        squashFactorMode=self.str_squashFactorMode,
        parentGutsTo=mRigNull,
        inflateDriveDirectParents=False,
        useUndoChunk=False)
    self.d_segmentBezierStretch = d_stretch

    if mSettings:
        if mSettings.hasAttr('stretch'):
            ATTR.set_default(mSettings.mNode, 'stretch', 1.0)
            ATTR.set(mSettings.mNode, 'stretch', 1.0)
        if mSettings.hasAttr('squash'):
            if _b_volume_squash:
                ATTR.set_default(mSettings.mNode, 'squash', 1.0)
                ATTR.set(mSettings.mNode, 'squash', 1.0)
            else:
                ATTR.set_default(mSettings.mNode, 'squash', 0.0)
                ATTR.set(mSettings.mNode, 'squash', 0.0)


def _segment_bezier_ik_subs_per_main_from_rig(self, mRigNull, ml_bezier_main_ik):
    """Parallel sub lists for module IK bezier mains (rig_frame wire order)."""
    m_slot_base = mRigNull.getMessageAsMeta('bezierIKChainStart') or ml_bezier_main_ik[0]
    m_slot_end = mRigNull.getMessageAsMeta('bezierIKChainEnd') or ml_bezier_main_ik[-1]
    ml_bezier_subs_per_main = []
    for mMain in ml_bezier_main_ik:
        str_slot = rig_shapes_bezier_main_slot_key(
            mMain, ml_bezier_main_ik, m_slot_base, m_slot_end)
        ml_bezier_subs_per_main.append(
            list((self.md_bezierIKSubsBySlot or {}).get(str_slot, [])))
    return ml_bezier_subs_per_main


def segment_rig_segments_bezier_shared_module_curve(
        self, mRigNull, mBlock, mModule, ml_segJoints, mRoot, mSettings,
        d_squash_share=None):
    """
    segmentType=bezier + ikSetup=bezier: own bezierIKCurve + driver on segmentJoints
    (avoids DG cycles from reusing module bezier shape). CVs driven from the same
    module IK bezier mains/subs already wired on bezierIKCurve in rig_frame.
    """
    import cgm.core.rig.ik_utils as IK
    import cgm.core.rig.bezier_utils as RIGBEZIER

    _str_func = 'segment_rig_segments_bezier_shared_module_curve'
    ml_ik_use, m_ik_spline_end, mPlug_masterScale, mMasterCurve = (
        _segment_bezier_rig_segments_joint_chain(self, ml_segJoints, mRoot))

    ml_bezier_main_ik = bezier_ik_resolve_main_ik_list(
        mRigNull, getattr(self, 'ml_ikMidControls', None))
    if len(ml_bezier_main_ik) < 2:
        log.warning('|{0}| >> need 2+ module IK bezier mains'.format(_str_func))
        return

    ml_bezier_subs_per_main = _segment_bezier_ik_subs_per_main_from_rig(
        self, mRigNull, ml_bezier_main_ik)
    int_bezier_sections = max(1, len(ml_bezier_main_ik) - 1)
    str_base = '{0}_seg_ikBezier'.format(self.d_module['partName'])

    log.info(cgmGEN.logString_msg(
        _str_func,
        'parallelSegmentCurve:True | segJoints:{0} | ikMains:{1} sections:{2}'.format(
            len(ml_ik_use), len(ml_bezier_main_ik), int_bezier_sections)))

    cgmGEN._reloadMod(IK)
    res_bezier = IK.bezier_spline(
        jointList=[mObj.mNode for mObj in ml_ik_use],
        baseName=str_base,
        bezierSections=int_bezier_sections,
        bezierAnchorMode=block_bezier_anchor_mode(mBlock),
        advancedTwistSetup=True,
        moduleInstance=mModule,
        parentGutsTo=mRigNull,
        useUndoChunk=False)

    m_seg_bezier = res_bezier['mBezierCurve']
    m_seg_driver = res_bezier['mDriverCurve']
    m_seg_ik_handle = res_bezier['mIKHandle']

    mRigNull.connectChildNode(
        m_seg_bezier.mNode, 'segmentBezierIKCurve', 'rigNull')
    mRigNull.connectChildNode(
        m_seg_driver.mNode, 'segmentBezierIKDriverCurve', 'rigNull')
    mRigNull.connectChildNode(
        m_seg_ik_handle.mNode, 'segmentBezierIKSplineHandle', 'rigNull')

    res_wire = RIGBEZIER.bezier_controls_wire_from_handles(
        m_seg_bezier,
        ml_anchorControls=ml_bezier_main_ik,
        ml_subs_per_main=ml_bezier_subs_per_main,
        baseName=str_base,
        templateCurve=True,
        snapHandles=False)

    m_seg_controls_grp = res_wire.get('mControlsGroup')
    if m_seg_controls_grp:
        mRigNull.connectChildNode(
            m_seg_controls_grp.mNode, 'segmentBezierIKControlsGrp', 'rigNull')

    ml_guts_vis = [
        m_seg_bezier, m_seg_driver, m_seg_ik_handle, mMasterCurve]
    if m_seg_controls_grp:
        ml_guts_vis.append(m_seg_controls_grp)
    self.fnc_connect_toRigGutsVis(ml_guts_vis)

    if mPlug_masterScale and m_seg_driver.hasAttr('masterScale'):
        m_seg_driver.doConnectIn(
            'masterScale', mPlug_masterScale.p_combinedShortName)

    bezier_ik_connect_spline_advanced_twist(
        m_seg_driver,
        m_seg_ik_handle,
        mBlock,
        self.d_orientation,
        mWorldUpStart=ml_bezier_main_ik[0],
        mWorldUpEnd=ml_bezier_main_ik[-1],
        wire_driver_twist_from_mains=False)

    mc.pointConstraint(
        [m_ik_spline_end.mNode], ml_segJoints[-1].mNode, maintainOffset=True)

    _segment_bezier_rig_segments_stretch(
        self, mBlock, mRigNull, ml_segJoints, ml_ik_use, m_seg_driver, mSettings,
        mPlug_masterScale, d_squash_share, str_base)

    if mSettings and mc.attributeQuery('result_IKon', node=mSettings.mNode, exists=True):
        m_plug_ik_on = cgmMeta.cgmAttr(mSettings.mNode, 'result_IKon')
        rig_frame_bezier_ik_track_vis(
            mRigNull, m_plug_ik_on, ml_track_curves=self.ml_bezierIKTrackCurves)

    log.debug(cgmGEN._str_subLine)


def segment_rig_segments_bezier(self, mRigNull, mBlock, mModule, ml_segJoints,
                                ml_handleJoints, ml_blendJoints, mRoot, mSettings,
                                d_squash_share=None):
    """Single-chain bezier spline on segmentJoints; CV anchors = handleJoints."""
    import cgm.core.rig.ik_utils as IK
    import cgm.core.rig.bezier_utils as RIGBEZIER

    _str_func = 'segment_rig_segments_bezier'
    if len(ml_segJoints) < 2:
        log.warning('|{0}| >> need 2+ segment joints'.format(_str_func))
        return

    if segment_bezier_uses_module_ik_curve(mBlock):
        m_module_bezier = mRigNull.getMessageAsMeta('bezierIKCurve')
        m_module_driver = mRigNull.getMessageAsMeta('bezierIKDriverCurve')
        if m_module_bezier and m_module_driver:
            bezier_ik_reinit_session_meta(self)
            segment_rig_segments_bezier_shared_module_curve(
                self, mRigNull, mBlock, mModule, ml_segJoints, mRoot, mSettings,
                d_squash_share=d_squash_share)
            return
        log.warning(cgmGEN.logString_msg(
            _str_func,
            'parallelSegmentCurve:False | missing module bezier on rigNull — '
            'fallback handle-joint bezier'))

    bezier_ik_reinit_session_meta(self)
    ml_mains = segment_bezier_mains_from_handle_joints(mRigNull, mBlock)
    if len(ml_mains) < 2:
        log.warning('|{0}| >> need 2+ bezier mains'.format(_str_func))
        return

    md_subs = dict(self.md_bezierIKSubsBySlot or {})
    if not md_subs:
        for mMain in ml_mains:
            str_slot = segment_bezier_main_slot_key(mMain, ml_mains)
            ml_slot = mRigNull.msgList_get(bezier_ik_slot_msglist_attr(str_slot))
            if ml_slot:
                md_subs[str_slot] = ml_slot

    ml_bezier_subs_per_main = []
    for mMain in ml_mains:
        str_slot = segment_bezier_main_slot_key(mMain, ml_mains)
        ml_bezier_subs_per_main.append(list(md_subs.get(str_slot, [])))

    ml_ik_use, m_ik_spline_end, mPlug_masterScale, mMasterCurve = (
        _segment_bezier_rig_segments_joint_chain(self, ml_segJoints, mRoot))

    str_base = '{0}_seg_bezier'.format(self.d_module['partName'])
    int_bezier_sections = max(1, len(ml_mains) - 1)

    log.info(cgmGEN.logString_msg(
        _str_func,
        'mains={0} subs={1} joints={2} sections={3}'.format(
            len(ml_mains),
            sum(len(ml) for ml in ml_bezier_subs_per_main),
            len(ml_ik_use),
            int_bezier_sections)))

    cgmGEN._reloadMod(IK)
    res_bezier = IK.bezier_spline(
        jointList=[mObj.mNode for mObj in ml_ik_use],
        baseName=str_base,
        bezierSections=int_bezier_sections,
        bezierAnchorMode=block_bezier_anchor_mode(mBlock),
        advancedTwistSetup=True,
        moduleInstance=mModule,
        useUndoChunk=False)

    m_bezier_curve = res_bezier['mBezierCurve']
    m_driver_curve = res_bezier['mDriverCurve']
    m_ik_handle = res_bezier['mIKHandle']

    mRigNull.connectChildNode(m_bezier_curve.mNode, 'bezierIKCurve', 'rigNull')
    mRigNull.connectChildNode(m_driver_curve.mNode, 'bezierIKDriverCurve', 'rigNull')
    mRigNull.connectChildNode(m_ik_handle.mNode, 'ikSplineHandle', 'rigNull')

    res_wire = RIGBEZIER.bezier_controls_wire_from_handles(
        m_bezier_curve,
        ml_anchorControls=ml_mains,
        ml_subs_per_main=ml_bezier_subs_per_main,
        baseName=str_base,
        templateCurve=True,
        snapHandles=True)
    mRigNull.connectChildNode(
        res_wire['mControlsGroup'].mNode, 'bezierIKControlsGrp', 'rigNull')

    ml_guts_vis = [m_bezier_curve, m_driver_curve, m_ik_handle, mMasterCurve]
    m_controls_grp = res_wire.get('mControlsGroup')
    if m_controls_grp:
        ml_guts_vis.append(m_controls_grp)
    self.fnc_connect_toRigGutsVis(ml_guts_vis)

    if mPlug_masterScale and m_driver_curve.hasAttr('masterScale'):
        m_driver_curve.doConnectIn(
            'masterScale', mPlug_masterScale.p_combinedShortName)

    bezier_ik_connect_spline_advanced_twist(
        m_driver_curve,
        m_ik_handle,
        mBlock,
        self.d_orientation,
        mWorldUpStart=ml_mains[0],
        mWorldUpEnd=ml_mains[-1],
        wire_driver_twist_from_mains=True)

    mc.pointConstraint(
        [m_ik_spline_end.mNode], ml_segJoints[-1].mNode, maintainOffset=True)

    _segment_bezier_rig_segments_stretch(
        self, mBlock, mRigNull, ml_segJoints, ml_ik_use, m_driver_curve, mSettings,
        mPlug_masterScale, d_squash_share, str_base)

    if mSettings and mc.attributeQuery('result_IKon', node=mSettings.mNode, exists=True):
        m_plug_ik_on = cgmMeta.cgmAttr(mSettings.mNode, 'result_IKon')
        rig_frame_bezier_ik_track_vis(
            mRigNull, m_plug_ik_on, ml_track_curves=self.ml_bezierIKTrackCurves)

    log.debug(cgmGEN._str_subLine)
