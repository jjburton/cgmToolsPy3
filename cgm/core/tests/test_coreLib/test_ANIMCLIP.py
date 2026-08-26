"""
AnimClip Phase 1 curve round-trip + Phase 2a range capture.

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
    from cgm.core.lib.animClip_dat import AnimClip
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
    return node


class Test_curveRoundTrip(unittest.TestCase):
    def setUp(self):
        mc.file(new=True, f=True)
        cgmGEN._reloadMod(ANIMCLIPCURVE)

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
        self._assert_rt(src, 'ac_inf_y_rt')

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
        clip = AnimClip()
        clip.from_curve(src)
        fd, path = tempfile.mkstemp(suffix='.cgmAnimClip')
        os.close(fd)
        try:
            self.assertTrue(clip.write(filepath=path))
            loaded = AnimClip()
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
        cgmGEN._reloadMod(ANIMCLIPCURVE)
        cgmGEN._reloadMod(ANIMCLIPDAT)

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
        self.assertTrue(all(1 <= t <= 10 for t in times))

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
