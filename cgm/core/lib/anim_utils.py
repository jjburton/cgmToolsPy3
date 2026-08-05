"""
------------------------------------------
anim_utils: cgm.core.lib
Author: David Bokser, Josh Burton
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

================================================================
"""
import itertools
import pprint
import logging

import maya.cmds as mc
import maya.api.OpenMaya as om

import cgm.core.lib.math_utils as COREMATH
import cgm.core.lib.position_utils as POS
import cgm.core.lib.distance_utils as DIST
from cgm.core import cgm_General as cgmGEN
import cgm.core.lib.attribute_utils as ATTR

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

log_msg = cgmGEN.logString_msg
log_sub = cgmGEN.logString_sub
log_start = cgmGEN.logString_start

def get_anim_value_by_time(node = None, attributes = [], time = 0.0):
    _str_func = 'get_anim_value_by_time'    
    _res = []
    for a in attributes:
        _comb = "{}.{}".format(node,a)
        anim_curve_node = mc.listConnections(_comb, source=True, destination=False, type="animCurve")
        if anim_curve_node:
            anim_curve_node = anim_curve_node[0]
        else:
            log.error(log_msg(_str_func,"| Doesn't have anim: {}".format(_comb)))
            continue
        _res.append(mc.getAttr("{}.output".format(anim_curve_node), time = time))
        
    if _res and len(_res)==1:
        return _res[0]
    return _res


def project_animCurve_value(node = None, targetFrame = None, sampleStart = None, sampleEnd = None,
                            attributes = ['tx','ty','tz','rx','ry','rz','sx','sy','sz'],
                            mode = 'project',
                            setValue = False):
    """
    
    """
    _res = []
    _timeDelta = COREMATH.get_fixedTimeDelta()
    
    for a in attributes:
        mVector = []
        mVelocity = []
        
        mValues = []
    
        #_current = mc.currentTime(q=True)
        
        for frame in range(int(sampleStart), int(sampleEnd+1)):
            #print(frame)
            #mc.currentTime(frame, edit=True)
            _v = get_anim_value_by_time(node,[a],frame)
            mValues.append( COREMATH.Vector3(_v,frame,0) )
            
            #mPos.append(POS.get(obj,asEuclid=1))
            
    
        for i,v in enumerate(mValues):
            if v != mValues[-1]:
                mVector.append( COREMATH.get_vector_of_two_points(v,mValues[i+1],asEuclid=True))
    
            if i:
                _vel = DIST.get_distance_between_points(v,mValues[i-1]) / (_timeDelta)
                mVelocity.append(_vel)
    
    
        if len(mVelocity) ==1:
            mVelocity.append(mVelocity[-1])
        if len(mVector) == 1:
            mVector.append(mVector[-1])
    
        _timePassed = (targetFrame - sampleEnd) * _timeDelta
    
        #pprint.pprint([mPos,mVector,mVelocity,_timePassed])
    
        _tmp = COREMATH.average_vector_args(mVector)#...average the vectors
        if mode == 'reflect':
            _tmp = [-v for v in _tmp]
        mVec = COREMATH.Vector3(_tmp[0],_tmp[1],_tmp[2])
        #    mVec.reflect(COREMATH.Vector3(-1,-1,-1))
            
        mVel = COREMATH.average(mVelocity)
        
        #mVel.normalize()
        #pprint.pprint([mVec,mVel,_timePassed])
    
        final_point = [mValues[-1].x + (mVec.x * mVel * _timePassed), 
                       mValues[-1].y + (mVec.y * mVel * _timePassed), 
                       mValues[-1].z + (mVec.z * mVel * _timePassed)] 
        pprint.pprint(final_point)
        #mc.currentTime(_current)
        _res.append(final_point)
        if setValue:
            mc.setKeyframe( node, t=[targetFrame], at=a, v=final_point[0])
            mc.dgdirty(node)
    return _res


_ROTATE_ORDERS = {
    0: om.MEulerRotation.kXYZ,
    1: om.MEulerRotation.kYZX,
    2: om.MEulerRotation.kZXY,
    3: om.MEulerRotation.kXZY,
    4: om.MEulerRotation.kYXZ,
    5: om.MEulerRotation.kZYX,
}


def _deg_to_rad(value):
    return om.MAngle(value, om.MAngle.kDegrees).asRadians()


def _rad_to_deg(value):
    return om.MAngle(value, om.MAngle.kRadians).asDegrees()


def _euler_from_degrees(values, rotate_order):
    return om.MEulerRotation(
        _deg_to_rad(values[0]),
        _deg_to_rad(values[1]),
        _deg_to_rad(values[2]),
        rotate_order
    )


def _degrees_from_euler(euler):
    return [
        _rad_to_deg(euler.x),
        _rad_to_deg(euler.y),
        _rad_to_deg(euler.z),
    ]


def _distance_squared(values, reference):
    return sum(
        (values[index] - reference[index]) ** 2
        for index in range(3)
    )


def _nearby_360_candidates(values, reference):
    channel_candidates = []

    for value, reference_value in zip(values, reference):
        nearest_wrap = int(
            round((reference_value - value) / 360.0)
        )

        channel_candidates.append([
            value + ((nearest_wrap - 1) * 360.0),
            value + (nearest_wrap * 360.0),
            value + ((nearest_wrap + 1) * 360.0),
        ])

    return [
        list(candidate)
        for candidate in itertools.product(*channel_candidates)
    ]


def closest_euler_solution(rotation_degrees,
                           reference_degrees,
                           rotate_order):
    source_euler = _euler_from_degrees(
        rotation_degrees,
        rotate_order
    )

    quaternion = source_euler.asQuaternion()

    primary = quaternion.asEulerRotation()
    primary.reorderIt(rotate_order)

    alternate = om.MEulerRotation.computeAlternateSolution(primary)

    base_solutions = [
        _degrees_from_euler(primary),
        _degrees_from_euler(alternate),
    ]

    candidates = []

    for solution in base_solutions:
        candidates.extend(
            _nearby_360_candidates(
                solution,
                reference_degrees
            )
        )

    return min(
        candidates,
        key=lambda candidate: _distance_squared(
            candidate,
            reference_degrees
        )
    )


def fix_selected_rotation_key(reference=(0.0, 0.0, 0.0)):
    """
    Replaces the selected transforms' rotation keys at the current frame with
    the equivalent Euler solution closest to reference.

    Example:
        fix_selected_rotation_key()

        fix_selected_rotation_key(reference=(10.0, 0.0, 0.0))
    """
    nodes = mc.ls(
        selection=True,
        long=True,
        type='transform'
    ) or []

    if not nodes:
        mc.warning('Select one or more transforms.')
        return []

    current_time = mc.currentTime(query=True)
    results = []

    mc.undoInfo(openChunk=True)

    try:
        for node in nodes:
            original = list(
                mc.getAttr(
                    '{}.rotate'.format(node),
                    time=current_time
                )[0]
            )

            rotate_order = _ROTATE_ORDERS[
                mc.getAttr('{}.rotateOrder'.format(node))
            ]

            solved = closest_euler_solution(
                rotation_degrees=original,
                reference_degrees=list(reference),
                rotate_order=rotate_order
            )

            for attribute, value in zip(
                ('rotateX', 'rotateY', 'rotateZ'),
                solved
            ):
                plug = '{}.{}'.format(node, attribute)

                if not mc.getAttr(plug, settable=True):
                    mc.warning(
                        'Cannot set locked or connected attribute: {}'.format(
                            plug
                        )
                    )
                    continue

                mc.setKeyframe(
                    node,
                    attribute=attribute,
                    time=current_time,
                    value=value
                )

            results.append({
                'node': node,
                'time': current_time,
                'original': original,
                'solved': solved,
            })

            print(
                '{0} at frame {1}\n'
                '  Original: {2}\n'
                '  Solved:   {3}'.format(
                    node,
                    current_time,
                    original,
                    solved
                )
            )

    finally:
        mc.undoInfo(closeChunk=True)

    mc.refresh(force=True)

    return results


def fix_selected_rotation_animation():
    """
    Fixes all existing rotation keyframes on selected transforms.

    The first keyed frame is solved toward zero. Each subsequent frame is
    solved toward the previous corrected rotation for continuity.
    """
    nodes = mc.ls(
        selection=True,
        long=True,
        type='transform'
    ) or []

    if not nodes:
        mc.warning('Select one or more animated transforms.')
        return []

    processed = []

    mc.undoInfo(openChunk=True)

    try:
        for node in nodes:
            key_times = set()

            for attribute in ('rotateX', 'rotateY', 'rotateZ'):
                times = mc.keyframe(
                    node,
                    attribute=attribute,
                    query=True,
                    timeChange=True
                ) or []

                key_times.update(times)

            key_times = sorted(key_times)

            if not key_times:
                mc.warning(
                    'No rotation keys found on: {}'.format(node)
                )
                continue

            rotate_order = _ROTATE_ORDERS[
                mc.getAttr('{}.rotateOrder'.format(node))
            ]

            original_values = {}

            for time_value in key_times:
                original_values[time_value] = [
                    mc.getAttr(
                        '{}.rotateX'.format(node),
                        time=time_value
                    ),
                    mc.getAttr(
                        '{}.rotateY'.format(node),
                        time=time_value
                    ),
                    mc.getAttr(
                        '{}.rotateZ'.format(node),
                        time=time_value
                    ),
                ]

            solved_values = {}
            reference = [0.0, 0.0, 0.0]

            for time_value in key_times:
                solved = closest_euler_solution(
                    rotation_degrees=original_values[time_value],
                    reference_degrees=reference,
                    rotate_order=rotate_order
                )

                solved_values[time_value] = solved
                reference = solved

            for time_value in key_times:
                solved = solved_values[time_value]

                for attribute, value in zip(
                    ('rotateX', 'rotateY', 'rotateZ'),
                    solved
                ):
                    plug = '{}.{}'.format(node, attribute)

                    if not mc.getAttr(plug, settable=True):
                        mc.warning(
                            'Cannot set locked or connected attribute: {}'.format(
                                plug
                            )
                        )
                        continue

                    mc.setKeyframe(
                        node,
                        attribute=attribute,
                        time=time_value,
                        value=value
                    )

            processed.append(node)

            print(
                'Fixed {} rotation keys on {}'.format(
                    len(key_times),
                    node
                )
            )

    finally:
        mc.undoInfo(closeChunk=True)

    mc.refresh(force=True)

    return processed
