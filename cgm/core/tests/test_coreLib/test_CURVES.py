"""
------------------------------------------
cgm.core.tests.test_coreLib.test_CURVES
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Core callers use create_fromName / shapeParent_in_place / override_color /
SHAPES.combine — not lib createControlCurve / parentShapeInPlace /
setCurveColorByName / combineCurves.
create_controlCurve returns a list and always colors; it is not a drop-in.
================================================================
"""
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import curve_Utils as CURVES
from cgm.core.lib import shape_utils as SHAPES
from cgm.core.lib import rigging_utils as CORERIG

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_create_fromName(unittest.TestCase):
    def test_circle_has_shape(self):
        crv = CURVES.create_fromName('circle', size=1)
        self.assertTrue(mc.objExists(crv))
        self.assertTrue(mc.listRelatives(crv, shapes=True))


class Test_combine(unittest.TestCase):
    def test_onto_first(self):
        a = CURVES.create_fromName('circle', size=1)
        b = CURVES.create_fromName('circle', size=0.5)
        out = SHAPES.combine([a, b])
        self.assertEqual(out, a)
        self.assertFalse(mc.objExists(b))
        self.assertGreaterEqual(len(mc.listRelatives(a, shapes=True) or []), 2)


class Test_shapeParent_in_place(unittest.TestCase):
    def test_keep_source_default(self):
        host = mc.spaceLocator()[0]
        src = CURVES.create_fromName('circle', size=1)
        CORERIG.shapeParent_in_place(host, src)
        self.assertTrue(mc.objExists(src))
        self.assertTrue(mc.listRelatives(host, shapes=True))


class Test_override_color(unittest.TestCase):
    def test_named_color(self):
        crv = CURVES.create_fromName('circle', size=1)
        CORERIG.override_color(crv, 'yellow')
        shapes = mc.listRelatives(crv, shapes=True, fullPath=True)
        self.assertTrue(mc.getAttr(shapes[0] + '.overrideEnabled'))
