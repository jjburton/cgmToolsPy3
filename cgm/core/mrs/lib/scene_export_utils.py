"""
Scene export path resolution — planned FBX output paths before bake/prep.

Extracted from ExportScene so preflight can run paths-first.
"""
import os
import logging

import cgm.core.lib.string_utils as CORESTRING

log = logging.getLogger(__name__)


def resolve_no_shot_export_name(export_name, no_shot_list_export_name='asset', shot_list=None,
                                scene_file=None):
    """When shot list is empty, optionally use scene file stem instead of browser exportName."""
    if shot_list:
        return export_name
    if no_shot_list_export_name != 'sceneFile':
        return export_name
    if not scene_file:
        import maya.cmds as mc
        scene_file = mc.file(q=True, sn=True) or mc.file(q=True, loc=True) or ''
    if not scene_file:
        log.warning("resolve_no_shot_export_name | noShotListExportName=sceneFile but no scene path; using exportName")
        return export_name
    _stem = os.path.splitext(os.path.basename(scene_file))[0]
    if _stem.endswith('_baked'):
        _stem = _stem[:-len('_baked')]
    _safe = CORESTRING.stripInvalidChars(_stem)
    if not _safe:
        log.warning("resolve_no_shot_export_name | empty stem after sanitize; using exportName")
        return export_name
    return '{0}.fbx'.format(_safe)


def _asset_name_from_hint(export_obj):
    """First namespace token or DAG leaf — matches ExportScene assetName."""
    return str(export_obj).split(':')[0].split('|')[-1]


def _static_base_name(export_obj):
    """Short name for static FBX stem (approximates cgmObj.p_nameBase from hint)."""
    return str(export_obj).split('|')[-1].split(':')[-1]


def _base_export_file_for_obj(export_obj, export_static=False, export_as_rig=False,
                              add_namespace_suffix=False, export_name=None,
                              effective_export_name=None, export_asset_path=None,
                              export_anim_path=None):
    """Single-object export path before per-shot branching."""
    asset_name = _asset_name_from_hint(export_obj)
    if export_static:
        export_file = os.path.normpath(os.path.join(
            export_asset_path, '{0}.fbx'.format(_static_base_name(export_obj))))
    elif export_as_rig:
        _stem, _ext = os.path.splitext(export_name or '')
        if not _ext:
            _ext = '.fbx'
        _rig_file_name = '{0}_rig{1}'.format(asset_name, _ext)
        export_file = os.path.normpath(os.path.join(export_asset_path, _rig_file_name))
    else:
        export_file = os.path.normpath(os.path.join(
            export_anim_path, effective_export_name or export_name or ''))

    if add_namespace_suffix and not export_as_rig and not export_static:
        export_file = export_file.replace('.fbx', '_{0}.fbx'.format(asset_name))
    return export_file


def resolve_export_fbx_paths(export_objs=None,
                             export_fbx_file=False,
                             export_as_rig=False,
                             export_as_cutscene=False,
                             export_static=False,
                             add_namespace_suffix=False,
                             export_name=None,
                             effective_export_name=None,
                             export_asset_path=None,
                             export_anim_path=None,
                             export_shots_to_individual_files=False,
                             shot_list=None,
                             cameras=None):
    """
    Return deduped planned FBX output paths ExportScene would write (pre-bake).

    Each entry: {path, exportObj, shotName, kind}
    """
    if not export_fbx_file:
        return []

    export_objs = list(export_objs or [])
    cameras = list(cameras or [])
    shot_list = list(shot_list or [])
    export_asset_path = os.path.normpath(export_asset_path) if export_asset_path else None
    export_anim_path = os.path.normpath(export_anim_path) if export_anim_path else None

    if export_as_rig and len(export_objs) > 1:
        _path = os.path.normpath(os.path.join(export_asset_path, export_name or ''))
        return [{
            'path': _path,
            'exportObj': ', '.join(export_objs),
            'shotName': None,
            'kind': 'rig_multi',
        }]

    _out = []
    _seen = set()

    def _append(path, export_obj, shot_name=None, kind='single'):
        _norm = os.path.normpath(path)
        _key = os.path.normcase(_norm)
        if _key in _seen:
            return
        _seen.add(_key)
        _out.append({
            'path': _norm,
            'exportObj': export_obj,
            'shotName': shot_name,
            'kind': kind,
        })

    _per_shot_mode = (
        (export_shots_to_individual_files or export_as_cutscene)
        and not export_as_rig
        and not export_static
    )

    for export_obj in export_objs:
        export_file = _base_export_file_for_obj(
            export_obj,
            export_static=export_static,
            export_as_rig=export_as_rig,
            add_namespace_suffix=add_namespace_suffix,
            export_name=export_name,
            effective_export_name=effective_export_name,
            export_asset_path=export_asset_path,
            export_anim_path=export_anim_path,
        )

        if _per_shot_mode and export_obj not in cameras and shot_list:
            export_dir = os.path.split(export_file)[0]
            base_name = os.path.splitext(os.path.basename(export_file))[0]
            if export_as_cutscene or len(export_objs) == 1:
                base_dir = export_dir
            else:
                base_dir = os.path.join(export_dir, base_name)

            for shot in shot_list:
                shot_name = shot[0]
                safe = CORESTRING.stripInvalidChars(shot_name)
                if export_as_cutscene:
                    _fbx_stem = CORESTRING.stripInvalidChars('{0}_{1}'.format(safe, _asset_name_from_hint(export_obj)))
                    out_file = os.path.join(base_dir, '{0}.fbx'.format(_fbx_stem))
                else:
                    out_file = os.path.join(base_dir, '{0}.fbx'.format(safe))
                _append(out_file, export_obj, shot_name=shot_name, kind='per_shot')
        else:
            _append(export_file, export_obj, kind='single_fallback' if _per_shot_mode else 'single')

    return _out
