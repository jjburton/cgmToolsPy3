"""
------------------------------------------
cgm.core.tests.test_coreLib.test_ATTR
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya unit tests for cgm.core.lib.attribute_utils.
Creates nodes — runner already does file-new before this module.
================================================================
"""
import unittest
import logging

try:
    import maya.cmds as mc
    from cgm.core.lib import attribute_utils as ATTR
except ImportError:
    raise Exception('test_ATTR can only be run in Maya')

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_crud(unittest.TestCase):
    def setUp(self):
        self.obj = mc.spaceLocator(name='cgmAttrTestLoc')[0]
        ATTR.add(self.obj, 'cgmTest', 'float', value=1.5)

    def tearDown(self):
        if mc.objExists(self.obj):
            mc.delete(self.obj)

    def test_has_attr(self):
        self.assertTrue(ATTR.has_attr(self.obj, 'cgmTest'))
        self.assertFalse(ATTR.has_attr(self.obj, 'noSuchAttr'))

    def test_get_set(self):
        self.assertEqual(ATTR.get(self.obj, 'cgmTest'), 1.5)
        ATTR.set(self.obj, 'cgmTest', 3.0)
        self.assertEqual(ATTR.get(self.obj, 'cgmTest'), 3.0)

    def test_type(self):
        # Maya may report float or double; ATTR treats them as the same family.
        self.assertTrue(
            ATTR.validate_attrTypeMatch(ATTR.get_type(self.obj, 'cgmTest'), 'float'),
            "float add should match float/double family, got {0}".format(
                ATTR.get_type(self.obj, 'cgmTest')))


class Test_message(unittest.TestCase):
    def setUp(self):
        self.holder = mc.spaceLocator(name='cgmMsgHolder')[0]
        self.target = mc.spaceLocator(name='cgmMsgTarget')[0]
        ATTR.add(self.holder, 'cgmLink', 'message')
        ATTR.set_message(self.holder, 'cgmLink', self.target, simple=True)

    def tearDown(self):
        for o in (self.holder, self.target):
            if mc.objExists(o):
                mc.delete(o)

    def test_returnMessageData_short(self):
        res = ATTR.returnMessageData(self.holder, 'cgmLink', longNames=False)
        self.assertTrue(res)
        self.assertEqual(mc.ls(res[0], shortNames=True)[0],
                         mc.ls(self.target, shortNames=True)[0])

    def test_returnMessageData_missing(self):
        self.assertFalse(ATTR.returnMessageData(self.holder, 'noMsg'))
