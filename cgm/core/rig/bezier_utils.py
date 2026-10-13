"""
------------------------------------------
bezier_utils: cgm.core.rig
Bezier curve control rigs (CV drivers).

================================================================
"""
import logging
import math

import maya.cmds as mc

from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.lib import attribute_utils as ATTR
from cgm.core.lib import curve_Utils as CURVES
from cgm.core.lib import rigging_utils as CORERIG
from cgm.core.lib import search_utils as SEARCH
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def bezier_curve_resolve(mCurve=None, require_bezier_ik=True):
    """
    Resolve the animator Bezier transform + shape (cgmType bezierIKCurve).

    Intended for the curve from IK.bezier_spline — not the hidden splineIKCurve driver.

    :returns: (mBezierTransform, str_shape)
    """
    _str_func = 'bezier_curve_resolve'

    if mCurve is None:
        _sel = mc.ls(sl=True, long=True) or []
        if not _sel:
            raise ValueError('|{0}| >> Select a Bezier curve transform or shape.'.format(_str_func))
        _node = _sel[0]
    else:
        _node = cgmMeta.validateObjArg(mCurve, noneValid=False).mNode

    _type = mc.nodeType(_node)
    if _type in ('bezierCurve', 'nurbsCurve'):
        str_shape = _node
        str_xform = mc.listRelatives(str_shape, parent=True, fullPath=True)[0]
    else:
        str_xform = SEARCH.get_transform(_node) or _node
        _shapes = mc.listRelatives(
            str_xform, shapes=True, noIntermediate=True, fullPath=True) or []
        _shapes = [
            _s for _s in _shapes
            if mc.nodeType(_s) in ('bezierCurve', 'nurbsCurve')]
        if not _shapes:
            raise ValueError(
                '|{0}| >> No curve shape on {1}.'.format(_str_func, str_xform))
        str_shape = _shapes[0]

    if mc.nodeType(str_shape) != 'bezierCurve':
        raise ValueError(
            '|{0}| >> Shape must be bezierCurve. Got {1} on {2}.'.format(
                _str_func, mc.nodeType(str_shape), str_xform))

    mBezier = cgmMeta.asMeta(str_xform, 'cgmObject', setClass=True)

    if require_bezier_ik:
        _cgm_type = None
        if mc.attributeQuery('cgmType', node=mBezier.mNode, exists=True):
            _cgm_type = ATTR.get(mBezier.mNode, 'cgmType')
        if _cgm_type != 'bezierIKCurve':
            raise ValueError(
                '|{0}| >> Select the bezierIKCurve from IK.bezier_spline (not the hidden '
                'ikDriver / splineIKCurve). Found cgmType: {1}'.format(_str_func, _cgm_type))

    return mBezier, str_shape


def _bezier_control_size_from_curve(mBezier):
    _bb = mc.exactWorldBoundingBox(mBezier.mNode)
    _w = _bb[3] - _bb[0]
    _h = _bb[4] - _bb[1]
    _d = _bb[5] - _bb[2]
    _diag = math.sqrt((_w * _w) + (_h * _h) + (_d * _d))
    return max(_diag * 0.025, 0.1)


def _bezier_create_anchor_control(str_name, f_size):
    _xform = CURVES.create_fromName(
        'circle', size=f_size, direction='x+', bakeScale=True)
    _xform = mc.rename(_xform, str_name)
    CORERIG.override_color(_xform, 'yellow')
    return cgmMeta.asMeta(_xform, 'cgmObject', setClass=True)


def _bezier_create_tangent_control(str_name, f_size):
    _l_pts = [
        (0.0, f_size, 0.0),
        (0.0, 0.0, f_size),
        (0.0, -f_size, 0.0),
        (0.0, 0.0, -f_size),
        (0.0, f_size, 0.0),
    ]
    _xform = mc.curve(name=str_name, degree=1, point=_l_pts)
    CORERIG.override_color(_xform, 'blueSky')
    return cgmMeta.asMeta(_xform, 'cgmObject', setClass=True)


def _bezier_handle_drive_meta(mCtrl):
    """Control transform for CV matrix drive (matches bezier_controls_add)."""
    return mCtrl


def _bezier_cv_world_position(str_shape, cv_index):
    return mc.pointPosition(
        '{0}.cv[{1}]'.format(str_shape, cv_index), world=True)


def _bezier_snap_handle_to_cv(mCtrl, str_shape, cv_index):
    v_pos = _bezier_cv_world_position(str_shape, cv_index)
    mGrp = mCtrl.getMessageAsMeta('masterGroup')
    if mGrp:
        mGrp.p_position = v_pos
    else:
        mCtrl.p_position = v_pos


def bezier_control_drive_cv(mControl, mBezier, str_shape, cv_index, str_baseName):
    """Drive a curve CV from a control world matrix (curve-local translation)."""
    mMult = cgmMeta.cgmNode(nodeType='multMatrix', name='{0}_multMtx'.format(str_baseName))
    mDecomp = cgmMeta.cgmNode(
        nodeType='decomposeMatrix', name='{0}_decompMtx'.format(str_baseName))

    ATTR.connect(mControl.mNode + '.worldMatrix[0]', mMult.mNode + '.matrixIn[0]')
    ATTR.connect(mBezier.mNode + '.worldInverseMatrix[0]', mMult.mNode + '.matrixIn[1]')
    ATTR.connect(mMult.mNode + '.matrixSum', mDecomp.mNode + '.inputMatrix')
    ATTR.connect(
        mDecomp.mNode + '.outputTranslate',
        '{0}.controlPoints[{1}]'.format(str_shape, cv_index))

    return mMult, mDecomp


def bezier_controls_add(mCurve=None,
                        controlSize=None,
                        baseName=None,
                        templateCurve=True,
                        useUndoChunk=True):
    """
    Add anchor + tangent transform controls driving Bezier CVs on a bezierIKCurve.

    Workflow: IK.bezier_spline(...) → select mBezierCurve → bezier_controls_add().

    Anchor CV indices: 0, 3, 6, …
    Tangent CV 3n+1 = out, 3n+2 = in (in tangent parents under anchor n).

    :returns:
        dict with mBezierCurve, mControlsGroup, ml_anchorControls, …
    """
    _str_func = 'bezier_controls_add'
    log.info(cgmGEN.logString_msg(_str_func, 'start'))

    mBezier, str_shape = bezier_curve_resolve(mCurve)

    _cvs = mc.ls(str_shape + '.cv[*]', flatten=True) or []
    _cv_count = len(_cvs)
    if _cv_count < 4 or (_cv_count - 1) % 3:
        raise ValueError(
            '|{0}| >> Expected cubic Bezier (3n + 1 CVs). Found {1}.'.format(
                _str_func, _cv_count))

    if controlSize is None:
        f_size = _bezier_control_size_from_curve(mBezier)
    else:
        f_size = VALID.valueArg(controlSize, noneValid=False)

    str_base = VALID.stringArg(baseName, noneValid=True) or mBezier.p_nameBase

    _undo_open = False
    if useUndoChunk:
        mc.undoInfo(openChunk=True)
        _undo_open = True

    try:
        mControlsGroup = cgmMeta.cgmObject(name='{0}_controls_grp'.format(str_base))
        mControlsGroup.addAttr('cgmName', str_base, lock=True)
        mControlsGroup.addAttr('cgmTypeModifier', 'bezierControls', lock=True)
        mControlsGroup.doName()

        mAnchorGroup = cgmMeta.cgmObject(name='{0}_anchors_grp'.format(str_base))
        mAnchorGroup.addAttr('cgmName', str_base, lock=True)
        mAnchorGroup.addAttr('cgmTypeModifier', 'bezierAnchors', lock=True)
        mAnchorGroup.doName()
        mAnchorGroup.p_parent = mControlsGroup

        md_anchors = {}
        ml_tangent_meta = []
        ml_util = []

        _anchor_indices = list(range(0, _cv_count, 3))

        for _anchor_num, _cv_index in enumerate(_anchor_indices):
            _pos = mc.pointPosition(
                '{0}.cv[{1}]'.format(str_shape, _cv_index), world=True)

            _ctrl_name = '{0}_anchor_{1:02d}_ctrl'.format(str_base, _anchor_num)
            mControl = _bezier_create_anchor_control(_ctrl_name, f_size)

            _offset = mc.group(mControl.mNode, name='{0}_offset'.format(_ctrl_name))
            mOffset = cgmMeta.asMeta(_offset, 'cgmObject', setClass=True)
            mc.xform(mOffset.mNode, worldSpace=True, translation=_pos)
            mOffset.p_parent = mAnchorGroup

            ml_util.extend(bezier_control_drive_cv(
                mControl, mBezier, str_shape, _cv_index, _ctrl_name))

            md_anchors[_anchor_num] = {
                'mControl': mControl,
                'mOffset': mOffset,
                'cvIndex': _cv_index,
            }

        for _cv_index in range(_cv_count):
            _rem = _cv_index % 3
            if _rem == 0:
                continue

            if _rem == 1:
                _anchor_num = _cv_index // 3
                _tangent_type = 'out'
            else:
                _anchor_num = (_cv_index + 1) // 3
                _tangent_type = 'in'

            _pos = mc.pointPosition(
                '{0}.cv[{1}]'.format(str_shape, _cv_index), world=True)

            _ctrl_name = '{0}_anchor_{1:02d}_{2}_ctrl'.format(
                str_base, _anchor_num, _tangent_type)
            mControl = _bezier_create_tangent_control(
                _ctrl_name, f_size * 0.7)

            _offset = mc.group(mControl.mNode, name='{0}_offset'.format(_ctrl_name))
            mOffset = cgmMeta.asMeta(_offset, 'cgmObject', setClass=True)
            mc.xform(mOffset.mNode, worldSpace=True, translation=_pos)

            mAnchorControl = md_anchors[_anchor_num]['mControl']
            mc.parent(mOffset.mNode, mAnchorControl.mNode, absolute=True)

            ml_util.extend(bezier_control_drive_cv(
                mControl, mBezier, str_shape, _cv_index, _ctrl_name))

            ml_tangent_meta.append(mControl)

        if templateCurve:
            ATTR.set(mBezier.mNode, 'template', True)

        mBezier.connectChildNode(mControlsGroup.mNode, 'bezierControls', 'bezierIKCurve')

        ml_anchors = [md_anchors[k]['mControl'] for k in sorted(md_anchors.keys())]
        mc.select([mCtrl.mNode for mCtrl in ml_anchors], replace=True)

        _res = {
            'mBezierCurve': mBezier,
            'mControlsGroup': mControlsGroup,
            'mAnchorGroup': mAnchorGroup,
            'ml_anchorControls': ml_anchors,
            'ml_tangentControls': ml_tangent_meta,
            'ml_utilityNodes': ml_util,
            'md_anchors': md_anchors,
        }
        log.info(cgmGEN.logString_msg(
            _str_func,
            'done | anchors:{0} tangents:{1}'.format(
                len(ml_anchors), len(ml_tangent_meta))))
        return _res

    finally:
        if _undo_open:
            mc.undoInfo(closeChunk=True)


def bezier_controls_wire_from_handles(mCurve=None,
                                      ml_anchorControls=None,
                                      ml_subs_per_main=None,
                                      baseName=None,
                                      templateCurve=True,
                                      snapHandles=True):
    """
    Drive bezierIKCurve CVs from existing MRS ikBezier / ikBezierSub controls.

    Anchor CVs: 0, 3, 6, … — one main handle per anchor.
    Tangents: sub handles with cgmNameModifier forward (out) / back (in).

    :returns:
        dict like bezier_controls_add (no new control transforms created).
    """
    _str_func = 'bezier_controls_wire_from_handles'
    log.info(cgmGEN.logString_msg(_str_func, 'start'))

    if not ml_anchorControls:
        raise ValueError('|{0}| >> ml_anchorControls required.'.format(_str_func))

    mBezier, str_shape = bezier_curve_resolve(mCurve)
    ml_anchorControls = cgmMeta.validateObjListArg(
        ml_anchorControls, mType='cgmObject', noneValid=False)

    _cvs = mc.ls(str_shape + '.cv[*]', flatten=True) or []
    _cv_count = len(_cvs)
    _anchor_count = len(ml_anchorControls)
    if _cv_count < 4 or (_cv_count - 1) % 3:
        raise ValueError(
            '|{0}| >> Expected cubic Bezier (3n + 1 CVs). Found {1}.'.format(
                _str_func, _cv_count))
    if _anchor_count != int((_cv_count - 1) / 3) + 1:
        raise ValueError(
            '|{0}| >> Anchor count {1} does not match curve CVs {2}.'.format(
                _str_func, _anchor_count, _cv_count))

    str_base = VALID.stringArg(baseName, noneValid=True) or mBezier.p_nameBase
    ml_subs_per_main = ml_subs_per_main or []
    if ml_subs_per_main and len(ml_subs_per_main) != _anchor_count:
        raise ValueError(
            '|{0}| >> ml_subs_per_main length {1} must match anchors {2}.'.format(
                _str_func, len(ml_subs_per_main), _anchor_count))

    mControlsGroup = cgmMeta.cgmObject(name='{0}_controls_grp'.format(str_base))
    mControlsGroup.addAttr('cgmName', str_base, lock=True)
    mControlsGroup.addAttr('cgmTypeModifier', 'bezierControls', lock=True)
    mControlsGroup.doName()

    ml_util = []
    ml_tangent_meta = []
    l_sub_wire = []

    if snapHandles:
        for _anchor_num, mMain in enumerate(ml_anchorControls):
            _bezier_snap_handle_to_cv(mMain, str_shape, _anchor_num * 3)
        for _anchor_num, mMain in enumerate(ml_anchorControls):
            ml_subs = ml_subs_per_main[_anchor_num] if ml_subs_per_main else []
            _cv_index = _anchor_num * 3
            for mSub in ml_subs or []:
                _name_mod = None
                if mc.attributeQuery('cgmNameModifier', node=mSub.mNode, exists=True):
                    _name_mod = ATTR.get(mSub.mNode, 'cgmNameModifier')
                if _name_mod == 'forward':
                    _tan_cv = _cv_index + 1
                elif _name_mod == 'back':
                    _tan_cv = _cv_index - 1
                else:
                    continue
                _bezier_snap_handle_to_cv(mSub, str_shape, _tan_cv)

    for _anchor_num, mMain in enumerate(ml_anchorControls):
        _cv_index = _anchor_num * 3
        _ctrl_name = '{0}_anchor_{1:02d}'.format(str_base, _anchor_num)
        mDrive = _bezier_handle_drive_meta(mMain)
        ml_util.extend(bezier_control_drive_cv(
            mDrive, mBezier, str_shape, _cv_index, _ctrl_name))

        ml_subs = ml_subs_per_main[_anchor_num] if ml_subs_per_main else []
        for mSub in ml_subs or []:
            _name_mod = None
            if mc.attributeQuery('cgmNameModifier', node=mSub.mNode, exists=True):
                _name_mod = ATTR.get(mSub.mNode, 'cgmNameModifier')
            if _name_mod == 'forward':
                _tan_cv = _cv_index + 1
            elif _name_mod == 'back':
                _tan_cv = _cv_index - 1
            else:
                log.warning('|{0}| >> Skip sub {1} — cgmNameModifier not forward/back.'.format(
                    _str_func, mSub.p_nameShort))
                continue
            l_sub_wire.append((_anchor_num, _name_mod, _tan_cv, mSub))

    for _anchor_num, _name_mod, _tan_cv, mSub in l_sub_wire:
        _tan_name = '{0}_anchor_{1:02d}_{2}'.format(
            str_base, _anchor_num, _name_mod)
        mSubDrive = _bezier_handle_drive_meta(mSub)
        ml_util.extend(bezier_control_drive_cv(
            mSubDrive, mBezier, str_shape, _tan_cv, _tan_name))
        ml_tangent_meta.append(mSub)

    if templateCurve:
        ATTR.set(mBezier.mNode, 'template', True)

    mBezier.connectChildNode(mControlsGroup.mNode, 'bezierControls', 'bezierIKCurve')

    _res = {
        'mBezierCurve': mBezier,
        'mControlsGroup': mControlsGroup,
        'ml_anchorControls': ml_anchorControls,
        'ml_tangentControls': ml_tangent_meta,
        'ml_utilityNodes': ml_util,
    }
    log.info(cgmGEN.logString_msg(
        _str_func,
        'done | anchors:{0} tangents:{1}'.format(
            len(ml_anchorControls), len(ml_tangent_meta))))
    return _res
