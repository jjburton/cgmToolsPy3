"""
------------------------------------------
texture_utils: cgm.core.lib
Author: Josh Burton
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

Maya file-texture path remap / localize against project content and export roots.
"""
__MAYALOCAL = 'TEXTURE'

import os
from difflib import SequenceMatcher
from shutil import copyfile

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

from cgm.core.lib import attribute_utils as ATTR


def _project_user_paths():
    from cgm.core import cgm_Meta as cgmMeta
    from cgm.core.tools import Project as Project

    optionVar = cgmMeta.cgmOptionVar('cgmVar_projectCurrent', varType='string')
    project = Project.data(filepath=optionVar.getValue())
    return project.userPaths_get() or {}


def _content_export(content=None, export=None):
    """Resolve content/export roots. Missing args come from the current project."""
    if not content or not export:
        paths = _project_user_paths()
        content = content or paths.get('content')
        export = export or paths.get('export')
    if not content or not export:
        raise ValueError('Need project content and export paths')
    return os.path.normpath(content), os.path.normpath(export)


def _candidate_under_root(texture_path, root):
    match = SequenceMatcher(None, texture_path, root).find_longest_match(
        0, len(texture_path), 0, len(root))
    return root + texture_path[match.size + match.a:]


def remap_missing(content=None, export=None):
    """
    For each Maya `file` node whose texture path is missing on disk, try to rebuild
    the path under project content, then under export.
    """
    content, export = _content_export(content, export)

    for node in mc.ls(type='file') or []:
        texture_path = os.path.normpath(ATTR.get(node, 'fileTextureName') or '')
        if not texture_path or os.path.exists(texture_path):
            continue

        new_path = _candidate_under_root(texture_path, content)
        if os.path.exists(new_path):
            log.info('changing %s.fileTextureName to %s' % (node, new_path))
            ATTR.set(node, 'fileTextureName', new_path)
            continue

        new_path = _candidate_under_root(texture_path, export)
        if os.path.exists(new_path):
            log.info('changing %s.fileTextureName to %s' % (node, new_path))
            ATTR.set(node, 'fileTextureName', new_path)
            continue

        log.warning("Can't find %s" % texture_path)


def localize(content=None, export=None):
    """
    Copy file textures that are not under project content next to the scene
    (or the referencing file) under a `textures` folder, then retarget the plug.

    `export` is unused; kept so call sites can pass `userPaths_get()` as-is.
    """
    if not content:
        content = _project_user_paths().get('content')
    if not content:
        raise ValueError('Need project content path')
    content = os.path.normpath(content)

    scene_path = mc.file(q=True, loc=True)
    scene_dir = os.path.dirname(scene_path) if scene_path else ''

    for node in mc.ls(type='file') or []:
        texture_name = ATTR.get(node, 'fileTextureName') or ''
        if not texture_name:
            continue
        if content in texture_name:
            continue
        if not (os.path.exists(texture_name) and os.path.isfile(texture_name)):
            continue

        dest_dir = scene_dir
        if mc.referenceQuery(node, inr=True):
            dest_dir = os.path.dirname(mc.referenceQuery(node, filename=True))

        if not dest_dir:
            log.warning('No scene path to localize %s' % texture_name)
            continue

        new_filename = os.path.join(dest_dir, 'textures', os.path.split(texture_name)[1])
        parent = os.path.dirname(new_filename)
        if not os.path.exists(parent):
            os.makedirs(parent)

        if os.path.normpath(texture_name) != os.path.normpath(new_filename):
            copyfile(texture_name, new_filename)
            log.info('remapped %s to %s' % (texture_name, new_filename))
            ATTR.set(node, 'fileTextureName', new_filename)
