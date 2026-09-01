"""
AnimClip Phase 1 curve round-trip + Phase 2 capture + Phase 3 paste + Phase 4 Pose mapping + Phase 6 animLayer.

Run from Toolbox Unittesting → Test Modules → coreLib → ANIMCLIP
(opens a new file).
"""
import os
import tempfile
import unittest
import logging

try:
    import maya.cmds as mc
    import cgm.core.lib.animClip_curve as ANIMCLIPCURVE
    import cgm.core.lib.animClip_dat as ANIMCLIPDAT
    import cgm.core.lib.attribute_utils as ATTR
    import cgm.core.lib.search_utils as SEARCH
    from cgm.core import cgm_General as cgmGEN
except ImportError:
    raise Exception('ANIMCLIP tests can only be run in Maya')

logging.basicConfig()
log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


def _roundtrip(src, name='ac_rt'):
    cgmGEN._reloadMod(ANIMCLIPCURVE)
    snap = ANIMCLIPCURVE.snapshot(src)
    dst = ANIMCLIPCURVE.rebuild(snap, name=name)
    errs = ANIMCLIPCURVE.compare(snap, dst)
    return snap, dst, errs


def _curve(ctype='animCurveTL', name='ac_src', keys=None, weighted=False,
           pri='constant', poi='constant'):
    node = mc.createNode(ctype, name=name)
    keys = keys or [(1.0, 0.0, 'linear', 'linear', False)]
    for t, v, itt, ott, bd in keys:
        mc.setKeyframe(node, time=(t,), value=v, breakdown=bd)
    if keys:
        mc.keyTangent(node, edit=True, weightedTangents=bool(weighted))
        for i, (_t, _v, itt, ott, _bd) in enumerate(keys):
            idx = (i, i)
            mc.keyTangent(node, index=idx, edit=True, lock=False)
            mc.keyTangent(node, index=idx, edit=True,
                          inTangentType=itt, outTangentType=ott)
            mc.keyTangent(node, index=idx, edit=True, lock=True)
        mc.setInfinity(node, pri=pri, poi=poi)
        ANIMCLIPCURVE.set_curve_infinity(node, pri=pri, poi=poi)
    return node


class Test_curveRoundTrip(unittest.TestCase):
    def setUp(self):
        mc.file(new=True, f=True)
        cgmGEN._reloadMod(ANIMCLIPCURVE)
        cgmGEN._reloadMod(ANIMCLIPDAT)

    def _assert_rt(self, src, name='ac_rt'):
        snap, dst, errs = _roundtrip(src, name=name)
        self.assertFalse(errs, '\n'.join(errs))
        return snap, dst

    def test_linear(self):
        src = _curve(name='ac_lin', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (10.0, 5.0, 'linear', 'linear', False),
        ])
        self._assert_rt(src, 'ac_lin_rt')

    def test_spline(self):
        src = _curve(name='ac_spl', keys=[
            (1.0, 0.0, 'spline', 'spline', False),
            (5.0, 2.0, 'spline', 'spline', False),
            (12.0, 0.0, 'spline', 'spline', False),
        ])
        self._assert_rt(src, 'ac_spl_rt')

    def test_stepped(self):
        src = _curve(name='ac_stp', keys=[
            (1.0, 0.0, 'linear', 'step', False),
            (8.0, 3.0, 'linear', 'step', False),
        ])
        self._assert_rt(src, 'ac_stp_rt')

    def test_auto(self):
        src = _curve(name='ac_auto', keys=[
            (1.0, 0.0, 'auto', 'auto', False),
            (10.0, 4.0, 'auto', 'auto', False),
        ])
        self._assert_rt(src, 'ac_auto_rt')

    def test_weighted(self):
        src = _curve(name='ac_wt', weighted=True, keys=[
            (1.0, 0.0, 'spline', 'spline', False),
            (10.0, 6.0, 'spline', 'spline', False),
        ])
        mc.keyTangent(src, index=(0, 0), edit=True, lock=False, weightLock=False)
        mc.keyTangent(src, index=(0, 0), edit=True, inWeight=2.0, outWeight=3.5)
        mc.keyTangent(src, index=(0, 0), edit=True, lock=True, weightLock=True)
        self._assert_rt(src, 'ac_wt_rt')

    def test_breakdown(self):
        src = _curve(name='ac_bd', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (5.0, 1.0, 'linear', 'linear', True),
            (10.0, 2.0, 'linear', 'linear', False),
        ])
        self._assert_rt(src, 'ac_bd_rt')

    def test_infinity_constant(self):
        src = _curve(name='ac_inf_c', pri='constant', poi='constant', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (10.0, 2.0, 'linear', 'linear', False),
        ])
        self._assert_rt(src, 'ac_inf_c_rt')

    def test_infinity_cycle(self):
        src = _curve(name='ac_inf_y', pri='cycle', poi='cycle', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (10.0, 2.0, 'linear', 'linear', False),
        ])
        snap, _dst = self._assert_rt(src, 'ac_inf_y_rt')
        self.assertEqual(snap['preInfinity'], 'cycle')
        self.assertEqual(snap['postInfinity'], 'cycle')

    def test_animCurveTL(self):
        src = _curve('animCurveTL', 'ac_tl', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (4.0, 1.0, 'linear', 'linear', False),
        ])
        snap, _dst = self._assert_rt(src, 'ac_tl_rt')
        self.assertEqual(snap['curveType'], 'animCurveTL')

    def test_animCurveTA(self):
        src = _curve('animCurveTA', 'ac_ta', keys=[
            (1.0, 0.0, 'linear', 'linear', False),
            (4.0, 15.0, 'linear', 'linear', False),
        ])
        snap, _dst = self._assert_rt(src, 'ac_ta_rt')
        self.assertEqual(snap['curveType'], 'animCurveTA')

    def test_single_key(self):
        src = _curve(name='ac_one', keys=[
            (3.0, 7.0, 'linear', 'linear', False),
        ])
        self._assert_rt(src, 'ac_one_rt')

    def test_rejects_unitless(self):
        node = mc.createNode('animCurveUL', name='ac_ul')
        self.assertRaises(ValueError, ANIMCLIPCURVE.snapshot, node)

    def test_json_file_roundtrip(self):
        src = _curve(name='ac_json', keys=[
            (1.0, 0.0, 'spline', 'spline', False),
            (8.0, 2.5, 'spline', 'spline', False),
        ])
        clip = ANIMCLIPDAT.AnimClip()
        clip.from_curve(src)
        fd, path = tempfile.mkstemp(suffix='.cgmAnimClip')
        os.close(fd)
        try:
            self.assertTrue(clip.write(filepath=path))
            loaded = ANIMCLIPDAT.AnimClip()
            self.assertTrue(loaded.read(filepath=path))
            curve_dat = loaded.dat['objects'][0]['channels'][0]['curve']
            rebuilt = ANIMCLIPCURVE.rebuild(curve_dat, name='ac_json_rt')
            errs = ANIMCLIPCURVE.compare(src, rebuilt)
            self.assertFalse(errs, '\n'.join(errs))
        finally:
            if os.path.exists(path):
                os.remove(path)


class Test_capture(unittest.TestCase):
    def setUp(self):
        mc.file(new=True, f=True)
        cgmGEN._reloadMod(SEARCH)
        cgmGEN._reloadMod(ANIMCLIPCURVE)
        cgmGEN._reloadMod(ANIMCLIPDAT)
        ANIMCLIPDAT.reload_dependencies()

    def test_locator_tx_in_range(self):
        loc = mc.spaceLocator(name='ac_capLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=1, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=10, value=5)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=1, end=10)
        objs = clip.dat['objects']
        self.assertEqual(len(objs), 1)
        chans = objs[0]['channels']
        attrs = [c['attr'] for c in chans]
        self.assertIn('translateX', attrs)
        tx = [c for c in chans if c['attr'] == 'translateX'][0]
        self.assertEqual(len(tx['curve']['keys']), 2)
        times = [k['time'] for k in tx['curve']['keys']]
        self.assertEqual(len(times), 2)
        self.assertAlmostEqual(times[0], 0.0)
        self.assertAlmostEqual(times[1], 9.0)
        self.assertTrue(clip.dat.get('relative'))
        self.assertEqual(objs[0]['shortName'], 'ac_capLoc')
        self.assertFalse(clip.dat.get('namespace'))

    def test_capture_namespace_on_clip_header(self):
        if not mc.namespace(exists='acClipNS'):
            mc.namespace(add='acClipNS')
        loc = mc.spaceLocator(name='acClipNS:ac_nsLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=1, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=10, value=1)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=1, end=10)
        self.assertEqual(clip.dat.get('namespace'), 'acClipNS')
        obj = clip.dat['objects'][0]
        self.assertEqual(obj['shortName'], 'ac_nsLoc')
        self.assertNotIn(':', obj['shortName'])
        self.assertFalse(obj.get('namespace'))
        self.assertNotIn('acClipNS:', obj.get('longName') or '')

    def test_slice_drops_outside_keys(self):
        loc = mc.spaceLocator(name='ac_sliceLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=1, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=10, value=5)
        mc.setKeyframe(loc, attribute='translateX', time=50, value=9)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=1, end=10)
        tx = [c for c in clip.dat['objects'][0]['channels']
              if c['attr'] == 'translateX'][0]
        times = [k['time'] for k in tx['curve']['keys']]
        self.assertEqual(len(times), 2)
        self.assertTrue(all(0 <= t <= 9 for t in times))

    def test_relative_to_start(self):
        loc = mc.spaceLocator(name='ac_relLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=10, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=20, value=5)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=10, end=20)
        self.assertEqual(clip.dat['sourceStart'], 10)
        self.assertEqual(clip.dat['sourceEnd'], 20)
        tx = [c for c in clip.dat['objects'][0]['channels']
              if c['attr'] == 'translateX'][0]
        times = [k['time'] for k in tx['curve']['keys']]
        self.assertEqual(len(times), 2)
        self.assertAlmostEqual(times[0], 0.0)
        self.assertAlmostEqual(times[1], 10.0)

    def test_no_boundary_samples_unless_requested(self):
        loc = mc.spaceLocator(name='ac_noBoundLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=0, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=20, value=20)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=5, end=15)
        self.assertFalse(clip.dat.get('keyStartEnd'))
        chans = clip.dat['objects'][0]['channels']
        self.assertFalse(chans)

    def test_boundary_samples_unkeyed_start_end(self):
        loc = mc.spaceLocator(name='ac_boundLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=0, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=20, value=20)
        driver = ATTR.get_driver(loc, 'translateX', getNode=True, skipConversionNodes=True)
        mc.keyTangent(driver, edit=True, inTangentType='linear', outTangentType='linear')
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=5, end=15, keyStartEnd=True)
        tx = [c for c in clip.dat['objects'][0]['channels']
              if c['attr'] == 'translateX'][0]
        keys = tx['curve']['keys']
        self.assertEqual(len(keys), 2)
        self.assertAlmostEqual(keys[0]['time'], 0.0)
        self.assertAlmostEqual(keys[1]['time'], 10.0)
        self.assertAlmostEqual(keys[0]['value'], 5.0)
        self.assertAlmostEqual(keys[1]['value'], 15.0)

    def test_no_start_sample_when_pre_infinity(self):
        # Locator setKeyframe / connectAttr resets curve infinity; test the skip on a naked curve
        # the same way AnimClip.get does (snapshot → ensure_boundary_keys → slice → offset).
        src = _curve(name='ac_preInfCrv', pri='linear', poi='constant', keys=[
            (10.0, 0.0, 'linear', 'linear', False),
            (20.0, 10.0, 'linear', 'linear', False),
        ])
        snap = ANIMCLIPCURVE.snapshot(src)
        self.assertEqual(snap['preInfinity'], 'linear')
        dat = ANIMCLIPCURVE.ensure_boundary_keys(snap, src, 1, 20)
        dat = ANIMCLIPCURVE.slice_keys(dat, 1, 20)
        dat = ANIMCLIPCURVE.offset_keys(dat, 1)
        times = [round(k['time'], 4) for k in dat['keys']]
        self.assertNotIn(0.0, times)
        self.assertAlmostEqual(times[0], 9.0)
        self.assertEqual(dat['preInfinity'], 'linear')

    def test_no_end_sample_when_post_infinity(self):
        src = _curve(name='ac_postInfCrv', pri='constant', poi='cycle', keys=[
            (0.0, 0.0, 'linear', 'linear', False),
            (10.0, 10.0, 'linear', 'linear', False),
        ])
        snap = ANIMCLIPCURVE.snapshot(src)
        self.assertEqual(snap['postInfinity'], 'cycle')
        dat = ANIMCLIPCURVE.ensure_boundary_keys(snap, src, 0, 20)
        dat = ANIMCLIPCURVE.slice_keys(dat, 0, 20)
        dat = ANIMCLIPCURVE.offset_keys(dat, 0)
        times = [round(k['time'], 4) for k in dat['keys']]
        self.assertNotIn(20.0, times)
        self.assertEqual(len(times), 2)
        self.assertEqual(dat['postInfinity'], 'cycle')

    def test_interior_boundary_samples_with_cycle_infinity(self):
        src = _curve(name='ac_cycBoundCrv', pri='cycle', poi='cycle', keys=[
            (0.0, 0.0, 'linear', 'linear', False),
            (20.0, 20.0, 'linear', 'linear', False),
        ])
        snap = ANIMCLIPCURVE.snapshot(src)
        self.assertEqual(snap['preInfinity'], 'cycle')
        self.assertEqual(snap['postInfinity'], 'cycle')
        dat = ANIMCLIPCURVE.ensure_boundary_keys(snap, src, 5, 15)
        dat = ANIMCLIPCURVE.slice_keys(dat, 5, 15)
        dat = ANIMCLIPCURVE.offset_keys(dat, 5)
        keys = dat['keys']
        self.assertEqual(len(keys), 2)
        self.assertAlmostEqual(keys[0]['time'], 0.0)
        self.assertAlmostEqual(keys[1]['time'], 10.0)
        self.assertAlmostEqual(keys[0]['value'], 5.0)
        self.assertAlmostEqual(keys[1]['value'], 15.0)

    def test_follows_unitConversion_to_curve(self):
        loc = mc.spaceLocator(name='ac_ucLoc')[0]
        curve = mc.createNode('animCurveTA', name='ac_ucCurve')
        mc.setKeyframe(curve, time=1, value=0)
        mc.setKeyframe(curve, time=10, value=15)
        uc = mc.createNode('unitConversion', name='ac_uc')
        mc.connectAttr('{}.output'.format(curve), '{}.input'.format(uc))
        mc.connectAttr('{}.output'.format(uc), '{}.rotateX'.format(loc))
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=1, end=10)
        chans = clip.dat['objects'][0]['channels']
        self.assertIn('rotateX', [c['attr'] for c in chans])
        rx = [c for c in chans if c['attr'] == 'rotateX'][0]
        self.assertEqual(len(rx['curve']['keys']), 2)
        self.assertEqual(rx['curve']['curveType'], 'animCurveTA')

    def test_paste_replace_at_frame(self):
        loc = mc.spaceLocator(name='ac_pasteLoc')[0]
        mc.setKeyframe(loc, attribute='translateX', time=10, value=0)
        mc.setKeyframe(loc, attribute='translateX', time=20, value=5)
        mc.select(loc)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=10, end=20)
        n = clip.apply(atFrame=50, mode='Replace', mapping='Name')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(loc, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertIn(50.0, by_time)
        self.assertIn(60.0, by_time)
        self.assertAlmostEqual(by_time[50.0], 0.0)
        self.assertAlmostEqual(by_time[60.0], 5.0)

    def test_paste_onto_unkeyed_other_object(self):
        src = mc.spaceLocator(name='ac_pasteSrc')[0]
        mc.setKeyframe(src, attribute='translateX', time=10, value=0)
        mc.setKeyframe(src, attribute='translateX', time=20, value=5)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=10, end=20)
        dst = mc.spaceLocator(name='ac_pasteDst')[0]
        mc.select(dst)
        n = clip.apply(atFrame=50, mode='Replace', mapping='Index')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        self.assertTrue(driver)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertIn(50.0, by_time)
        self.assertIn(60.0, by_time)
        self.assertAlmostEqual(by_time[50.0], 0.0)
        self.assertAlmostEqual(by_time[60.0], 5.0)

    def test_paste_insert_shifts_later_keys(self):
        src = mc.spaceLocator(name='ac_insSrc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=5)
        mc.setKeyframe(src, attribute='translateX', time=10, value=6)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_insDst')[0]
        mc.setKeyframe(dst, attribute='translateX', time=10, value=0)
        mc.setKeyframe(dst, attribute='translateX', time=30, value=10)
        mc.select(dst)
        n = clip.apply(atFrame=20, mode='Insert', mapping='Index')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[10.0], 0.0)
        self.assertAlmostEqual(by_time[20.0], 5.0)
        self.assertAlmostEqual(by_time[30.0], 6.0)
        self.assertAlmostEqual(by_time[40.0], 10.0)

    def test_paste_stripPrefix_mapping(self):
        src = mc.spaceLocator(name='pfx_ac_poseLoc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=3)
        mc.setKeyframe(src, attribute='translateX', time=10, value=7)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_poseLoc')[0]
        mc.select(dst)
        n = clip.apply(atFrame=40, mode='Replace', mapping='stripPrefix')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[40.0], 3.0)
        self.assertAlmostEqual(by_time[50.0], 7.0)

    def test_preview_mapping_does_not_paste(self):
        src = mc.spaceLocator(name='pfx_ac_prevLoc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=3)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_prevLoc')[0]
        mc.select(dst)
        pairs, nHit = ANIMCLIPDAT._preview_mapping(
            clip.dat.get('objects') or [], 'stripPrefix', clip.dat.get('namespace') or '')
        self.assertEqual(nHit, 1)
        self.assertEqual(pairs[0][1], 'ac_prevLoc')
        self.assertFalse(mc.keyframe(dst, query=True, name=True) or [])

    def test_metaData_falls_back_to_stripPrefix(self):
        src = mc.spaceLocator(name='pfx_ac_metaLoc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=3)
        mc.setKeyframe(src, attribute='translateX', time=10, value=7)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_metaLoc')[0]
        mc.select(dst)
        n = clip.apply(atFrame=40, mode='Replace', mapping='metaData')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[40.0], 3.0)
        self.assertAlmostEqual(by_time[50.0], 7.0)

    def test_pose_mapping_uses_selection_only(self):
        src = mc.spaceLocator(name='pfx_ac_leafLoc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=4)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        grp = mc.group(em=True, name='ac_leafGrp')
        dst = mc.spaceLocator(name='ac_leafLoc')[0]
        mc.parent(dst, grp)
        mc.select(grp)
        n = clip.apply(atFrame=20, mode='Replace', mapping='stripPrefix')
        self.assertEqual(n, 0)
        mc.select(dst)
        n = clip.apply(atFrame=20, mode='Replace', mapping='stripPrefix')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[20.0], 4.0)

    def test_mirrorIndex_mapping(self):
        import Red9.core.Red9_AnimationUtils as r9Anim
        mh = r9Anim.MirrorHierarchy()
        src = mc.spaceLocator(name='ac_mirSrc')[0]
        dst = mc.spaceLocator(name='ac_mirDst')[0]
        mh.setMirrorIDs(src, side='Left', slot=4)
        mh.setMirrorIDs(dst, side='Left', slot=4)
        mc.setKeyframe(src, attribute='translateX', time=0, value=2)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        mc.select(dst)
        n = clip.apply(atFrame=30, mode='Replace', mapping='mirrorIndex')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[30.0], 2.0)

    def test_mirrorIndex_ID_maps_opposite_side(self):
        import Red9.core.Red9_AnimationUtils as r9Anim
        mh = r9Anim.MirrorHierarchy()
        src = mc.spaceLocator(name='ac_mirIdSrc')[0]
        dst = mc.spaceLocator(name='ac_mirIdDst')[0]
        mh.setMirrorIDs(src, side='Left', slot=5)
        mh.setMirrorIDs(dst, side='Right', slot=5)
        mc.setKeyframe(src, attribute='translateX', time=0, value=8)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        mc.select(dst)
        n = clip.apply(atFrame=12, mode='Replace', mapping='mirrorIndex_ID')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[12.0], 8.0)

    def test_empty_selection_falls_back_to_name(self):
        src = mc.spaceLocator(name='ac_emptyMapLoc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=1)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        mc.rename(src, 'ac_emptyMapSrc')
        dst = mc.spaceLocator(name='ac_emptyMapLoc')[0]
        mc.select(cl=True)
        n = clip.apply(atFrame=5, mode='Replace', mapping='stripPrefix')
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[5.0], 1.0)

    def test_paste_to_animLayer_creates_layer_keys(self):
        src = mc.spaceLocator(name='ac_layerSrc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=9)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_layerDst')[0]
        mc.setKeyframe(dst, attribute='translateX', time=0, value=0)
        mc.select(dst)
        n = clip.apply(atFrame=20, mode='Replace', mapping='Index',
                       layer='ac_clipLayer', layerOverride=True)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(mc.objExists('ac_clipLayer'))
        self.assertEqual(mc.nodeType('ac_clipLayer'), 'animLayer')
        self.assertTrue(mc.animLayer('ac_clipLayer', q=True, override=True))
        self.assertTrue(SEARCH.animLayer_contains('ac_clipLayer', dst, attr='translateX'))
        curves = mc.animLayer('ac_clipLayer', q=True, animCurves=True) or []
        self.assertTrue(curves)
        snap = ANIMCLIPCURVE.snapshot(curves[0])
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[20.0], 9.0)
        mc.currentTime(20)
        mc.animLayer('ac_clipLayer', e=True, mute=True)
        self.assertAlmostEqual(mc.getAttr(dst + '.translateX'), 0.0, places=3)
        mc.animLayer('ac_clipLayer', e=True, mute=False)
        self.assertAlmostEqual(mc.getAttr(dst + '.translateX'), 9.0, places=3)

    def test_ensure_anim_layer_override_only_on_create(self):
        add = ANIMCLIPCURVE.ensure_anim_layer('ac_addLayer', override=False)
        self.assertEqual(mc.nodeType(add), 'animLayer')
        self.assertFalse(bool(mc.animLayer(add, q=True, override=True)))
        ovr = ANIMCLIPCURVE.ensure_anim_layer('ac_ovrLayer', override=True)
        self.assertTrue(bool(mc.animLayer(ovr, q=True, override=True)))
        again = ANIMCLIPCURVE.ensure_anim_layer('ac_addLayer', override=True)
        self.assertEqual(again, add)
        self.assertFalse(bool(mc.animLayer(add, q=True, override=True)))

    def test_get_nodes_ignores_selection(self):
        src = mc.spaceLocator(name='ac_hookSrc')[0]
        other = mc.spaceLocator(name='ac_hookOther')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=4)
        mc.setKeyframe(other, attribute='translateX', time=0, value=7)
        mc.select(other)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10, nodes=[src])
        names = [o.get('shortName') for o in clip.dat.get('objects') or []]
        self.assertIn('ac_hookSrc', names)
        self.assertNotIn('ac_hookOther', names)

    def test_apply_dests_uses_given_list(self):
        src = mc.spaceLocator(name='ac_hookApplySrc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=6)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_hookApplyDst')[0]
        decoy = mc.spaceLocator(name='ac_hookApplyDecoy')[0]
        mc.select(decoy)
        n = clip.apply(atFrame=8, mode='Replace', mapping='Index', dests=[dst])
        self.assertGreaterEqual(n, 1)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        self.assertTrue(driver)
        snap = ANIMCLIPCURVE.snapshot(driver)
        by_time = {round(k['time'], 4): k['value'] for k in snap['keys']}
        self.assertAlmostEqual(by_time[8.0], 6.0)
        decoy_driver = ATTR.get_driver(decoy, 'translateX', getNode=True,
                                      skipConversionNodes=True)
        self.assertFalse(decoy_driver)

    def test_apply_empty_dests_does_nothing(self):
        src = mc.spaceLocator(name='ac_hookEmptySrc')[0]
        mc.setKeyframe(src, attribute='translateX', time=0, value=3)
        mc.select(src)
        clip = ANIMCLIPDAT.AnimClip()
        clip.get(start=0, end=10)
        dst = mc.spaceLocator(name='ac_hookEmptyDst')[0]
        mc.select(dst)
        n = clip.apply(atFrame=5, mode='Replace', mapping='Index', dests=[])
        self.assertEqual(n, 0)
        driver = ATTR.get_driver(dst, 'translateX', getNode=True, skipConversionNodes=True)
        self.assertFalse(driver)
