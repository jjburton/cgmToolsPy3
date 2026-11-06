"""
------------------------------------------
cgm.core.tests.test_coreLib.test_UISMOKE
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Open/close shipped cgm windows. Does not exercise tool behavior.
Needs a Maya GUI session (skip in batch / mayapy).

Skip: Red9, ngSkin, ml_tools, marking menus, SceneOld, base cgmGUI,
actions (fix rotation, reload, Update last-branch).
================================================================
"""
import importlib
import unittest
import logging

import maya.cmds as mc

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)

# Keep cgmVar_loadCount off GuiFactory thanks-window intervals (10, 25, 50, ...).
_THANKS_SAFE_COUNT = 51

# (test id, module, class attr on that module)
_WINDOWS = (
    ('toolbox', 'cgm.core.tools.toolbox', 'ui'),
    ('attrTools', 'cgm.core.tools.attrTools', 'ui'),
    ('locinator', 'cgm.core.tools.locinator', 'ui'),
    ('setTools', 'cgm.core.tools.setTools', 'ui'),
    ('snapTools', 'cgm.core.tools.snapTools', 'ui'),
    ('dynParentTool', 'cgm.core.tools.dynParentTool', 'ui'),
    ('mocapBakeTools', 'cgm.core.tools.mocapBakeTools', 'ui'),
    ('animClip', 'cgm.core.lib.animClip_dat', 'ui'),
    ('jointTools', 'cgm.core.tools.jointTools', 'ui'),
    ('transformTools', 'cgm.core.tools.transformTools', 'ui'),
    ('dynFKTool', 'cgm.core.tools.dynFKTool', 'ui'),
    ('animFilterTool', 'cgm.core.tools.animFilterTool', 'ui'),
    ('meshTools', 'cgm.core.tools.meshTools', 'go'),
    ('builder', 'cgm.core.mrs.Builder', 'ui'),
    ('blockEditor', 'cgm.core.mrs.Builder', 'ui_blockEditor'),
    ('blockCreate', 'cgm.core.mrs.Builder', 'ui_createBlock'),
    ('blockPicker', 'cgm.core.mrs.Builder', 'ui_blockPicker'),
    ('mrsAnimate', 'cgm.core.mrs.Animate', 'ui'),
    ('mrsPicker', 'cgm.core.mrs.Animate', 'ui_picker'),
    ('mrsPoser', 'cgm.core.mrs.PoseManager', 'ui'),
    ('mrsAnimClip', 'cgm.core.mrs.mrsAnimClip', 'ui'),
    ('scene', 'cgm.core.mrs.Scene', 'ui'),
    ('project', 'cgm.core.tools.Project', 'ui'),
    ('cgmDat', 'cgm.core.cgm_Dat', 'ui'),
    ('blockDat', 'cgm.core.mrs.MRSDat', 'uiBlockDat'),
    ('blockConfig', 'cgm.core.mrs.MRSDat', 'uiBlockConfigDat'),
    ('shapeDat', 'cgm.core.mrs.MRSDat', 'uiShapeDat'),
    ('p4Tool', 'cgm.core.tools.p4Tool', 'ui'),
    ('p4UnknownTool', 'cgm.core.tools.p4UnknownTool', 'ui'),
    ('updateTool', 'cgm.core.tools.updateTool', 'ui'),
    ('SVGator', 'cgm.core.tools.SVGator', 'ui'),
    ('keyEaser', 'cgm.core.tools.keyEaser', 'ui'),
    ('funcIterTime', 'cgm.core.tools.funcIterTime', 'ui'),
    ('randomizeAttribute', 'cgm.core.tools.randomizeAttribute', 'ui'),
    ('animDrawTool', 'cgm.core.tools.animDrawTool', 'ui'),
    ('controllerPuppetTool', 'cgm.core.tools.controllerPuppetTool', 'ui'),
)


def _gui_session():
    return not mc.about(batch=True)


def _flush_idle():
    try:
        import maya.utils as MAYAUTILS
        MAYAUTILS.processIdleEvents()
    except Exception:
        pass


def _close_window(name, ui_cls=None):
    if name and mc.window(name, exists=True):
        closer = getattr(ui_cls, 'Close', None) if ui_cls is not None else None
        if callable(closer):
            try:
                closer(skipVerify=True)
            except TypeError:
                closer()
        if mc.window(name, exists=True):
            try:
                mc.window(name, edit=True, closeCommand=lambda *a: None)
            except Exception:
                pass
            mc.deleteUI(name)
    _flush_idle()


def _clear_singleton_caches():
    try:
        import cgm.core.mrs.Builder as BUILDER
        BUILDER.UI = None
        BUILDER.BLOCKEDITOR = None
        BUILDER.BLOCKPICKER = None
    except Exception:
        pass
    try:
        import cgm.core.mrs.Scene as SCENE
        SCENE.UI = None
    except Exception:
        pass


class Test_open_allowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._had_count = mc.optionVar(exists='cgmVar_loadCount')
        cls._old_count = mc.optionVar(q='cgmVar_loadCount') if cls._had_count else None
        mc.optionVar(iv=('cgmVar_loadCount', _THANKS_SAFE_COUNT))

    @classmethod
    def tearDownClass(cls):
        if cls._had_count:
            mc.optionVar(iv=('cgmVar_loadCount', int(cls._old_count)))
        elif mc.optionVar(exists='cgmVar_loadCount'):
            mc.optionVar(remove='cgmVar_loadCount')
        _clear_singleton_caches()

    def setUp(self):
        if not _gui_session():
            self.skipTest('UI smoke needs a Maya GUI session')

    def _open_close(self, module_name, ui_attr='ui'):
        mod = importlib.import_module(module_name)
        ui_cls = getattr(mod, ui_attr)
        win = ui_cls.WINDOW_NAME
        try:
            ui_cls()
            _flush_idle()
            self.assertTrue(mc.window(win, exists=True), win)
        finally:
            _close_window(win, ui_cls)
            _clear_singleton_caches()

    def test_shots(self):
        import cgm.core.mrs.Shots as SHOTS
        name = 'pyunify_ShotsUI'
        try:
            SHOTS.ShotUI()
            _flush_idle()
            self.assertTrue(mc.window(name, exists=True), name)
        finally:
            _close_window(name)


def _install_window_tests():
    def _make(module_name, ui_attr):
        def _test(self):
            self._open_close(module_name, ui_attr)
        return _test

    for name, module_name, ui_attr in _WINDOWS:
        setattr(Test_open_allowlist, 'test_{0}'.format(name),
                _make(module_name, ui_attr))


_install_window_tests()
