"""
------------------------------------------
cgm.core.tests.test_coreLib.test_GUI
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

OptionVar helpers on GuiFactory. Do not call purgeCGM here — it
wipes every Maya optionVar whose name contains 'cgm'.
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.classes import GuiFactory as cgmUI

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)

_TEST_VAR = 'cgmVar_libToCoreGuiPurgeTest'


class Dummy(object):
    def __init__(self):
        self.optionVars = []


class Test_purgeOptionVar(unittest.TestCase):
    def tearDown(self):
        if mc.optionVar(exists=_TEST_VAR):
            mc.optionVar(remove=_TEST_VAR)

    def test_missing_returns_false(self):
        self.assertIs(cgmUI.do_purgeOptionVar(_TEST_VAR), False)

    def test_removes_existing(self):
        mc.optionVar(iv=(_TEST_VAR, 1))
        self.assertTrue(mc.optionVar(exists=_TEST_VAR))
        self.assertTrue(cgmUI.do_purgeOptionVar(_TEST_VAR))
        self.assertFalse(mc.optionVar(exists=_TEST_VAR))


class Test_optionVarHolder(unittest.TestCase):
    def test_append_once(self):
        dummy = Dummy()
        if 'cgmVar_a' not in dummy.optionVars:
            dummy.optionVars.append('cgmVar_a')
        if 'cgmVar_a' not in dummy.optionVars:
            dummy.optionVars.append('cgmVar_a')
        self.assertEqual(dummy.optionVars, ['cgmVar_a'])

    def test_reset_purges_listed_vars(self):
        mc.optionVar(iv=(_TEST_VAR, 1))
        try:
            cgmUI.do_resetGuiInstanceOptionVars([_TEST_VAR])
            self.assertFalse(mc.optionVar(exists=_TEST_VAR))
        finally:
            if mc.optionVar(exists=_TEST_VAR):
                mc.optionVar(remove=_TEST_VAR)
