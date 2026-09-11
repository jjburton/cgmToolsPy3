"""
SimChain dat — preset + setup dat (Phase 1–2).

Run from Toolbox Unittesting → Test Modules → coreLib → SIMCHAIN
"""
import os
import tempfile
import unittest
import logging

try:
    import maya.cmds as mc
    import cgm.core.lib.simChain_dat as SIMDAT
    import cgm.core.lib.nCloth_utils as NCLOTH
    import cgm.core.rig.dynamic_utils as RIGDYN
    from cgm.core import cgm_General as cgmGEN
except ImportError:
    raise Exception('SIMCHAIN tests can only be run in Maya')

logging.basicConfig()
log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


def _library_has_key(options, *parts):
    suffix = '.'.join(parts)
    return any(k == suffix or k.endswith('.{0}'.format(suffix)) for k in options)


class Test_simChainDatSchema(unittest.TestCase):
    def setUp(self):
        cgmGEN._reloadMod(SIMDAT)
        cgmGEN._reloadMod(NCLOTH)
        cgmGEN._reloadMod(RIGDYN)

    def _seed_path(self, *parts):
        return os.path.join(SIMDAT.get_library_path('dev'), *parts)

    def test_seed_files_read(self):
        _files = (
            ('hair', 'bob.cgmSimHairDat'),
            ('hair', 'bob_hold.cgmSimHairDat'),
            ('hair', 'bangs_firm.cgmSimHairDat'),
            ('hair', 'ponytail.cgmSimHairDat'),
            ('hair', 'shoulder.cgmSimHairDat'),
            ('hair', 'long_flow.cgmSimHairDat'),
            ('hair', 'ribbon.cgmSimHairDat'),
            ('hair', 'tail.cgmSimHairDat'),
            ('hair', 'tail_firm.cgmSimHairDat'),
            ('hair', 'limb.cgmSimHairDat'),
            ('hair', 'rope.cgmSimHairDat'),
            ('cloth', 'silk.cgmSimClothDat'),
            ('cloth', 'chiffon.cgmSimClothDat'),
            ('cloth', 'cotton.cgmSimClothDat'),
            ('cloth', 'denim.cgmSimClothDat'),
            ('cloth', 'leather.cgmSimClothDat'),
            ('cloth', 'burlap.cgmSimClothDat'),
            ('nucleus', 'solver_balanced.cgmSimNucleusDat'),
            ('nucleus', 'solver_quality.cgmSimNucleusDat'),
            ('nucleus', 'solver_high.cgmSimNucleusDat'),
            ('nucleus', 'wind_calm.cgmSimNucleusDat'),
        )
        for folder, fname in _files:
            path = self._seed_path(folder, fname)
            self.assertTrue(os.path.exists(path), path)
            inst, dat = SIMDAT.read_dat(path)
            self.assertIsNotNone(inst, path)
            self.assertEqual(dat.get('schemaVersion'), 1)
            self.assertTrue(dat.get('profile') is not None)
            self.assertEqual(dat.get('section'), inst.section)

    def test_library_scan(self):
        _options, _types = SIMDAT.get_library_options(force=True, mode='dev')
        self.assertTrue(_library_has_key(_options, 'hair', 'bob'))
        self.assertTrue(_library_has_key(_options, 'hair', 'bob_hold'))
        self.assertTrue(_library_has_key(_options, 'hair', 'ponytail'))
        self.assertTrue(_library_has_key(_options, 'hair', 'tail_firm'))
        self.assertTrue(_library_has_key(_options, 'cloth', 'cotton'))
        self.assertTrue(_library_has_key(_options, 'cloth', 'silk'))
        self.assertTrue(_library_has_key(_options, 'cloth', 'denim'))
        self.assertTrue(_library_has_key(_options, 'nucleus', 'solver_balanced'))
        self.assertTrue(_library_has_key(_options, 'nucleus', 'solver_quality'))
        self.assertTrue(_library_has_key(_options, 'nucleus', 'solver_high'))

    def test_from_module_profile_hair(self):
        dat = SIMDAT.SimHairDat.from_module_profile('bob')
        self.assertIsNotNone(dat)
        self.assertEqual(dat.get('name'), 'bob')
        self.assertEqual(dat.get('datKind'), 'hair')
        self.assertEqual(dat.get('section'), 'hs')
        self.assertTrue(dat.get('profile'))

    def test_from_module_profile_cloth(self):
        dat = SIMDAT.SimClothDat.from_module_profile('cotton')
        self.assertIsNotNone(dat)
        self.assertEqual(dat.get('profileKind'), 'fabric')
        self.assertIn('stretchResistance', dat.get('profile', {}))

    def test_normalize_ramp_keys_on_read(self):
        path = self._seed_path('hair', 'bob.cgmSimHairDat')
        inst = SIMDAT.SimHairDat()
        inst.read(path)
        _scale = inst.dat['profile'].get('attractionScale') or {}
        if _scale:
            self.assertIn(0, _scale)

    def test_json_write_read_roundtrip(self):
        src = SIMDAT.SimClothDat.from_module_profile('cotton')
        self.assertIsNotNone(src)
        inst = SIMDAT.SimClothDat(dat=src)
        fd, path = tempfile.mkstemp(suffix='.cgmSimClothDat')
        os.close(fd)
        try:
            self.assertTrue(inst.write(filepath=path, startDirMode='dev'))
            loaded = SIMDAT.SimClothDat()
            self.assertTrue(loaded.read(path))
            self.assertEqual(loaded.dat.get('name'), 'cotton')
            self.assertEqual(
                loaded.dat.get('profile', {}).get('stretchResistance'),
                src.get('profile', {}).get('stretchResistance'),
            )
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_skip_attrs_not_in_module_profile(self):
        dat = SIMDAT.SimClothDat.from_module_profile('cotton')
        prof = dat.get('profile') or {}
        for skip in NCLOTH.l_skipPresetAttrs:
            self.assertNotIn(skip, prof)

    def test_profile_apply_section_nucleus(self):
        mc.file(new=True, f=True)
        nuc = mc.createNode('nucleus', name='simchain_test_nuc')
        dat = SIMDAT.SimNucleusDat.from_module_profile('solver_preview')
        self.assertIsNotNone(dat)
        inst = SIMDAT.SimNucleusDat(dat=dat)
        count = inst.apply(target=nuc, clean=True)
        self.assertGreater(count, 0)
        self.assertEqual(mc.getAttr('{0}.subSteps'.format(nuc)), 3)


class Test_simChainSetupDat(unittest.TestCase):
    def setUp(self):
        cgmGEN._reloadMod(SIMDAT)
        cgmGEN._reloadMod(RIGDYN)

    def test_setup_empty_schema(self):
        inst = SIMDAT.SimChainSetup()
        self.assertEqual(inst.dat.get('schemaVersion'), 1)
        self.assertIn('mapped', inst.dat)
        self.assertIn('chains', inst.dat)

    def test_setup_json_roundtrip(self):
        inst = SIMDAT.SimChainSetup()
        inst.dat = SIMDAT.SimChainSetup._empty_setup_dat('test_setup')
        inst.dat['mapped'] = {'nucleus': '|test_nucleus'}
        inst.dat['chains'] = [{
            'index': 0,
            'name': 'test_chain',
            'chainMode': 'clothAttach',
            'surfaceTrack': 'follicle',
            'targets': ['|jnt1', '|jnt2'],
            'presetRefs': {'cloth': 'cloth/cotton', 'nucleus': 'nucleus/solver_balanced'},
        }]
        fd, path = tempfile.mkstemp(suffix='.cgmSimChainSetup')
        os.close(fd)
        try:
            self.assertTrue(inst.write(filepath=path, startDirMode='dev'))
            loaded = SIMDAT.SimChainSetup()
            self.assertTrue(loaded.read(path))
            self.assertEqual(loaded.dat.get('baseName'), 'test_setup')
            self.assertEqual(len(loaded.dat.get('chains') or []), 1)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_resolve_library_filepath_suffix(self):
        _options, _ = SIMDAT.get_library_options(force=True, mode='dev')
        _path = SIMDAT.resolve_library_filepath('hair/bob')
        self.assertTrue(_path)
        self.assertTrue(os.path.isfile(_path))
        self.assertTrue(_path.endswith('bob.cgmSimHairDat'))

    def test_read_dat_setup_class(self):
        inst = SIMDAT.SimChainSetup()
        inst.dat = inst._empty_setup_dat('roundtrip')
        fd, path = tempfile.mkstemp(suffix='.cgmSimChainSetup')
        os.close(fd)
        try:
            inst.write(filepath=path, startDirMode='dev')
            loaded, dat = SIMDAT.read_dat(path)
            self.assertIsInstance(loaded, SIMDAT.SimChainSetup)
            self.assertEqual(dat.get('name'), 'roundtrip')
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == '__main__':
    unittest.main()
