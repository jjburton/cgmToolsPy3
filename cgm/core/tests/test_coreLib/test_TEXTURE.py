"""
------------------------------------------
cgm.core.tests.test_coreLib.test_TEXTURE
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

remap_missing with explicit content/export — does not read project optionVars.
================================================================
"""
import os
import tempfile
import unittest
import logging

import maya.cmds as mc
from cgm.core.lib import texture_utils as TEXTURE

log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)


class Test_remap_missing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='cgmTexTest_')
        self.content = os.path.join(self._tmp, 'content')
        self.export = os.path.join(self._tmp, 'export')
        maps = os.path.join(self.content, 'maps')
        os.makedirs(maps)
        os.makedirs(self.export)
        self.on_disk = os.path.join(maps, 'foo.png')
        with open(self.on_disk, 'wb') as f:
            f.write(b'x')
        self.node = mc.shadingNode('file', asTexture=True, name='cgmTexFile')

    def tearDown(self):
        if mc.objExists(self.node):
            mc.delete(self.node)

    def test_rebuilds_under_content(self):
        missing = r'Z:\old\content\maps\foo.png'
        mc.setAttr(self.node + '.fileTextureName', missing, type='string')
        TEXTURE.remap_missing(content=self.content, export=self.export)
        got = os.path.normpath(mc.getAttr(self.node + '.fileTextureName'))
        self.assertEqual(got, os.path.normpath(self.on_disk))

    def test_leaves_existing_path(self):
        mc.setAttr(self.node + '.fileTextureName', self.on_disk, type='string')
        TEXTURE.remap_missing(content=self.content, export=self.export)
        got = os.path.normpath(mc.getAttr(self.node + '.fileTextureName'))
        self.assertEqual(got, os.path.normpath(self.on_disk))
