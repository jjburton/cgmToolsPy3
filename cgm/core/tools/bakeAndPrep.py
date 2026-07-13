import maya.cmds as mc
import os
import pprint
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging

from cgm.core import cgm_Meta as cgmMeta
from cgm.core import cgm_General as cgmGEN

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

def BakeAndPrep(bakeSetName = 'bake_tdSet',
                deleteSetName = "delete_tdSet",
                exportSetName = "export_tdSet",
                startFrame = None,
                endFrame = None,
                sampleBy=1.0,                
                euler = True,
                tangent = 'auto',
                simplify = False,
                reducer = True):
    
    baked = Bake(bakeSetName,startFrame = startFrame,endFrame=endFrame, sampleBy=sampleBy,euler=euler, tangent=tangent, simplify=simplify, reducer=reducer)
    if baked:
        prepped = Prep(deleteSetName,
                       exportSetName)
    else:
        print("Not baked, so not prepping")

    if not prepped:
        print("Not prepped")

    return prepped

def Bake(assets, bakeSetName = 'bake_tdSet',
         startFrame = None,
         endFrame = None,
         sampleBy=1.0,
         euler = True,
         tangent = 'auto',
         simplify = False,
         reducer = True):
    
    _str_func = 'Bake'

    cgmGEN.playback_stop()
    
    if startFrame is None:
        startFrame =  mc.playbackOptions(q=True, min=True)
    if endFrame is None:
        endFrame =  mc.playbackOptions(q=True, max=True)
        
    
    baked = False

    #if(mc.optionVar(exists='cgm_bake_set')):
        #bakeSetName = mc.optionVar(q='cgm_bake_set')

    # set tangent options to spline
    currentTangent = mc.keyTangent( q=True, g=True, ott=True )[0]
    mc.keyTangent( g=True, ott="linear" )
    
    #Eval mode ----
    _evalMode = mc.evaluationManager(q=True, mode=True)
    mc.evaluationManager(mode='off')
    
    bakeTransforms = []
    bakeSets = []
    missingBakeSets = []

    currentTime = mc.currentTime(q=True)
    log.info("{0} ||currentTime: {1}".format(_str_func,currentTime))

    for asset in assets:
        #if ':' in assets:
        log.info("{0} || asset: {1}".format(_str_func,asset))

        _assetShort = asset.split('|')[-1]
        topNodeSN = _assetShort.split(':')[-1]
        if topNodeSN:
            namespaces = _assetShort.split(':')[:-1]
            bakeSet = resolve_td_set_for_asset(bakeSetName, namespaces)
            if bakeSet:
                if bakeSet not in bakeSets:
                    bakeSets.append(bakeSet)
                    _stuff = mc.sets(bakeSet, q=True) or []
                    if isinstance(_stuff, str):
                        _stuff = [_stuff]
                    if _stuff:
                        log.info("{0} || using bakeSet: {1} | members: {2}".format(_str_func, bakeSet, len(_stuff)))
                        bakeTransforms += _stuff
                    else:
                        log.warning("{0} || bakeSet found but empty: {1}".format(_str_func, bakeSet))
            else:
                _bakeSetCandidates = []
                if namespaces:
                    _nsAccum = []
                    for _part in namespaces:
                        _nsAccum.append(_part)
                        _bakeSetCandidates.append('{0}:{1}'.format(':'.join(_nsAccum), bakeSetName))
                for c in (bakeSetName,):
                    if c not in _bakeSetCandidates:
                        _bakeSetCandidates.append(c)
                for _candidate in _bakeSetCandidates:
                    if _candidate not in missingBakeSets:
                        missingBakeSets.append(_candidate)
                bakeTransforms.append(asset)
                log.info("{0} || no bakeSet candidate found. candidates: {1}".format(_str_func, _bakeSetCandidates))
        else:
            if mc.objExists(bakeSetName):
                if bakeSetName not in bakeSets:
                    bakeSets.append(bakeSetName)
                    _stuff = mc.sets(bakeSetName, q=True)
                    if _stuff:
                        bakeTransforms += _stuff
                    log.info("{0} || bakeSet: {1}".format(_str_func,bakeSetName))                    
            elif asset not in bakeTransforms:
                bakeTransforms.append(asset)
                log.info("{0} || bake: {1}".format(_str_func,asset))
                
                #else:
                #    bakeTransforms.append(asset)
    #pprint.pprint(vars())
    log.info("Shall we bake...")
    if len(bakeTransforms) > 0:
        log.info("{0} || baking transforms...".format(_str_func))
        
        #pprint.pprint(bakeTransforms)
        log.info("{0} || time | start: {1} | end: {2}".format(_str_func,startFrame,endFrame))
        
        mc.bakeResults( bakeTransforms, 
                        simulation=True, 
                        t=( startFrame, endFrame), 
                        sampleBy=sampleBy, 
                        disableImplicitControl=True,
                        preserveOutsideKeys = False, 
                        sparseAnimCurveBake = False,
                        removeBakedAttributeFromLayer = False, 
                        removeBakedAnimFromLayer = True, 
                        bakeOnOverrideLayer = False, 
                        minimizeRotation = True, 
                        controlPoints = False, 
                        # smart= True,
                        # sparseAnimCurveBake = .00001,
                        shape = True )

        mc.setInfinity(bakeTransforms, pri='constant', poi='constant')

        #Simplify
        
        #Filter euler
        if euler or tangent or reducer or simplify:
            for obj in bakeTransforms:
                if euler:
                    for a in ['rotateX','rotateY','rotateZ']:
                        if mc.objExists( obj + '_' + a ):
                            try:mc.filterCurve( obj + '_' + a )
                            except Exception as err:
                                print(("{0} | {1} | {2}".format(obj,a,err)))
                            
                if tangent:
                    _anim = mc.listConnections(obj, type = 'animCurve')
                    if _anim:
                        if tangent == 'step':
                            mc.keyTangent(_anim, e=1, itt='stepnext',ott='step',animation='keysOrObjects')  
                        else:
                            mc.keyTangent(_anim, e=1, itt=tangent,ott=tangent,animation='keysOrObjects')            
            
                if simplify:
                    _anim = mc.listConnections(obj, type = 'animCurve')
                    if _anim:
                        mc.simplify(_anim, time=":", float=":", timeTolerance=0.05, valueTolerance=0.00001)

                if reducer:
                    _anim = mc.listConnections(obj, type = 'animCurve')
                    if _anim:
                        mc.filterCurve(_anim, 
                                        filter="keyReducer", 
                                        precisionMode=1, 
                                        precision=0.1, 
                                        preserveKeyTangent="auto")

        baked = True
    else:
        baked = False
        log.warning("{0} || No bake transforms resolved. assets={1} | bakeSetName={2}".format(
            _str_func, assets, bakeSetName))
        if missingBakeSets:
            log.warning("{0} || Missing bake sets encountered: {1}".format(_str_func, missingBakeSets))

    mc.keyTangent( g=True, ott=currentTangent )

    #eval mode restore ----
    if _evalMode[0] != 'off':
        print(("Eval mode restored: {0}".format(_evalMode[0])))
        mc.evaluationManager(mode = _evalMode[0])

    mc.currentTime(currentTime)

    return baked

def BreakTextureLinks(exportObjs=None):
    """
    Break texture links by clearing fileTextureName attributes on all file texture nodes.
    
    Args:
        exportObjs: Optional list of objects to scope texture breaking to.
                    If None, breaks all file textures in the scene.
    
    Returns:
        int: Number of texture links broken
    """
    _str_func = 'BreakTextureLinks'
    log.info("{0} || Starting...".format(_str_func))
    
    # Find all file texture nodes
    fileNodes = mc.ls(type='file')
    
    if not fileNodes:
        log.info("{0} || No file texture nodes found".format(_str_func))
        return 0
    
    # If exportObjs is provided, filter file nodes to only those connected to export objects
    if exportObjs:
        # Get all shading engines connected to export objects
        shadingEngines = set()
        for obj in exportObjs:
            try:
                shapes = mc.listRelatives(obj, shapes=True, fullPath=True) or []
                for shape in shapes:
                    # Get shading groups connected to this shape
                    sg = mc.listConnections(shape, type='shadingEngine') or []
                    shadingEngines.update(sg)
            except Exception as err:
                log.warning("{0} || Failed gathering shading groups for {1}: {2}".format(_str_func, obj, err))
        
        # Get file nodes connected to these shading engines
        connectedFileNodes = set()
        for sg in shadingEngines:
            try:
                # Get file nodes connected through the shading network
                files = mc.listConnections(sg, type='file', source=True, destination=False) or []
                connectedFileNodes.update(files)
            except Exception as err:
                log.warning("{0} || Failed gathering file nodes for shadingEngine {1}: {2}".format(_str_func, sg, err))
        
        # Filter to only connected file nodes
        fileNodes = [f for f in fileNodes if f in connectedFileNodes]
    
    brokenCount = 0
    failedNodes = []
    
    for fileNode in fileNodes:
        try:
            # Check if fileTextureName attribute exists and is not locked
            if mc.objExists('{}.fileTextureName'.format(fileNode)):
                if not mc.getAttr('{}.fileTextureName'.format(fileNode), lock=True):
                    # Get current path for logging
                    currentPath = mc.getAttr('{}.fileTextureName'.format(fileNode))
                    
                    # Clear the texture path
                    mc.setAttr('{}.fileTextureName'.format(fileNode), '', type='string')
                    
                    log.info("{0} || Broke texture link: {1} | was: {2}".format(_str_func, fileNode, currentPath))
                    brokenCount += 1
                else:
                    log.warning("{0} || Skipping locked file node: {1}".format(_str_func, fileNode))
                    failedNodes.append(fileNode)
        except Exception as err:
            log.error("{0} || Failed to break texture link on {1}: {2}".format(_str_func, fileNode, err))
            failedNodes.append(fileNode)
    
    if brokenCount > 0:
        log.info("{0} || Broke {1} texture link(s)".format(_str_func, brokenCount))
    
    if failedNodes:
        log.warning("{0} || Failed to break {1} texture link(s)".format(_str_func, len(failedNodes)))
    
    return brokenCount


def resolve_delete_set(deleteSetName, namespace_prefix=None):
    """Pick existing objectSet for delete_tdSet-style names.

    When *namespace_prefix* is set, only explicit names for that rig are tried
    (no global ``*:delete_tdSet`` scan) so multi-reference scenes cannot pick
    another rig's delete set.
    """
    base = deleteSetName.split(':')[-1]
    candidates = []
    if namespace_prefix:
        _prefix = namespace_prefix.lstrip('|')
        candidates.append('{0}:{1}'.format(_prefix, base))
        for c in (deleteSetName, base):
            if c not in candidates:
                candidates.append(c)
        seen = set()
        for name in candidates:
            if name in seen:
                continue
            seen.add(name)
            if mc.objExists(name):
                return name
        return None

    if deleteSetName:
        candidates.append(deleteSetName)
    if base not in candidates:
        candidates.append(base)
    for s in mc.ls('*:{0}'.format(base), type='objectSet') or []:
        if s not in candidates:
            candidates.append(s)
    seen = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        if mc.objExists(name):
            return name
    return None


def resolve_td_set_for_asset(setName, namespaces=None):
    """Find bake/export/delete tdSet-style objectSet for a namespaced asset root.

    Tries each namespace prefix outer-to-inner (e.g. ``Ref:``, then ``Ref:Inner:``),
    then unqualified names. Without *namespaces*, falls back to a global ``*:base`` scan.
    """
    base = setName.split(':')[-1]
    candidates = []

    if namespaces:
        _nsAccum = []
        for _part in namespaces:
            _nsAccum.append(_part)
            candidates.append('{0}:{1}'.format(':'.join(_nsAccum), base))

    for c in (setName, base):
        if c not in candidates:
            candidates.append(c)

    if not namespaces:
        for s in mc.ls('*:{0}'.format(base), type='objectSet') or []:
            if s not in candidates:
                candidates.append(s)

    seen = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        if mc.objExists(name):
            return name
    return None


def ProcessDeleteSet(deleteSetName, namespace_prefix=None, resolved_set=None, _str_func='ProcessDeleteSet'):
    """
    Resolve delete set (namespaced or root) and delete members; log survivors.
    Used by Prep (referenced) and Scene ExportScene non-referenced path.

    If *resolved_set* is passed and exists, it is used directly (per-rig, no
    cross-namespace resolution).
    """
    if resolved_set and mc.objExists(resolved_set):
        resolved = resolved_set
    else:
        resolved = resolve_delete_set(deleteSetName, namespace_prefix)
    if not resolved:
        log.warning("{0} || No delete set found | deleteSetName={1} | namespace_prefix={2}".format(
            _str_func, deleteSetName, namespace_prefix))
        return False

    log.info("{0} || delete set resolved: {1}".format(_str_func, resolved))
    l_deleteFailures = []
    l_deleteSurvivors = []
    l_deleteTargets = mc.sets(resolved, q=True) or []
    if isinstance(l_deleteTargets, str):
        l_deleteTargets = [l_deleteTargets]
    log.info("{0} || delete targets: {1}".format(_str_func, len(l_deleteTargets)))

    for o in l_deleteTargets:
        try:
            mc.delete(o)
        except Exception as err:
            l_deleteFailures.append((o, err))
            log.error("{0} || delete failed: {1} | err: {2}".format(_str_func, o, err))

    for o in l_deleteTargets:
        if mc.objExists(o):
            l_deleteSurvivors.append(o)

    if l_deleteFailures or l_deleteSurvivors:
        log.warning(cgmGEN._str_hardBreak)
        log.warning("{0} || Delete-set cleanup issues detected".format(_str_func))
        if l_deleteFailures:
            log.warning("{0} || delete exceptions: {1}".format(_str_func, len(l_deleteFailures)))
            for i, d in enumerate(l_deleteFailures):
                log.warning("{0} || fail[{1}] target={2} | err={3}".format(_str_func, i, d[0], d[1]))
        if l_deleteSurvivors:
            log.warning("{0} || delete survivors still exist: {1}".format(_str_func, len(l_deleteSurvivors)))
            for i, o in enumerate(l_deleteSurvivors):
                log.warning("{0} || survivor[{1}] {2}".format(_str_func, i, o))
        log.warning("{0} || Troubleshooting: check namespace changes and locked/reference state.".format(_str_func))
        log.warning(cgmGEN._str_hardBreak)
        return False

    log.info("{0} || delete set cleanup ok | members={1}".format(_str_func, len(l_deleteTargets)))
    return True


def export_select_targets_resolve(export_root_hint,
                                  exportSetName='export_tdSet',
                                  member_hints=None,
                                  _str_func='export_select_targets_resolve'):
    """
    Return surviving DAG paths for FBX export after delete-set cleanup.

    *export_root_hint* is the export context string (e.g. ``master``, ``Crate:master``);
    it is used for namespace / tdSet correlation only — the hint node may already be
    deleted (e.g. ``master`` in ``delete_tdSet``).

    *member_hints* optional list of DAG paths or short names captured before delete;
    when omitted, members are read from the resolved export set.
    """
    _hintShort = (export_root_hint or '').split('|')[-1]
    namespaces = _hintShort.split(':')[:-1] if ':' in _hintShort else []

    l_memberNodes = []
    if member_hints:
        for m in member_hints:
            if not m:
                continue
            if mc.objExists(m):
                l_memberNodes.append(m)
            else:
                _short = m.split('|')[-1].split(':')[-1]
                _resolved = (mc.ls(_short, l=True) or [None])[0]
                if _resolved and mc.objExists(_resolved):
                    l_memberNodes.append(_resolved)
    else:
        resolved_export = resolve_td_set_for_asset(exportSetName, namespaces or None)
        if resolved_export and mc.objExists(resolved_export):
            _setMembers = mc.sets(resolved_export, q=True) or []
            if isinstance(_setMembers, str):
                _setMembers = [_setMembers]
            for m in _setMembers:
                if not m:
                    continue
                if mc.objExists(m):
                    l_memberNodes.append(m)
                else:
                    _short = m.split('|')[-1].split(':')[-1]
                    _resolved = (mc.ls(_short, l=True) or [None])[0]
                    if _resolved and mc.objExists(_resolved):
                        l_memberNodes.append(_resolved)
                    else:
                        log.warning("{0} || export set member missing after delete: {1}".format(_str_func, m))
        else:
            log.warning("{0} || export set not found | hint={1} | namespaces={2}".format(
                _str_func, export_root_hint, namespaces))

    if not l_memberNodes and member_hints:
        resolved_export_post = resolve_td_set_for_asset(exportSetName, None)
        if resolved_export_post and mc.objExists(resolved_export_post):
            _setMembers = mc.sets(resolved_export_post, q=True) or []
            if isinstance(_setMembers, str):
                _setMembers = [_setMembers]
            for m in _setMembers:
                if not m:
                    continue
                if mc.objExists(m):
                    l_memberNodes.append(m)
                else:
                    _short = m.split('|')[-1].split(':')[-1]
                    _resolved = (mc.ls(_short, l=True) or [None])[0]
                    if _resolved and mc.objExists(_resolved):
                        l_memberNodes.append(_resolved)
                    else:
                        log.warning("{0} || export set member missing after delete: {1}".format(_str_func, m))

    l_select = []
    _seen = set()
    for m in l_memberNodes:
        _short = m.split('|')[-1].split(':')[-1]
        _resolved = (mc.ls(_short, l=True) or [None])[0]
        if _resolved and mc.objExists(_resolved) and _resolved not in _seen:
            _seen.add(_resolved)
            l_select.append(_resolved)
        elif mc.objExists(m) and m not in _seen:
            _seen.add(m)
            l_select.append(m)

    if not l_select:
        for _cand in (export_root_hint,
                      _hintShort,
                      _hintShort.split(':')[-1] if _hintShort else ''):
            if _cand and mc.objExists(_cand) and _cand not in _seen:
                l_select.append(_cand)
                break

    if not l_select:
        log.error("{0} || No export targets resolved | hint={1} | namespaces={2} | member_hints={3}".format(
            _str_func, export_root_hint, namespaces, member_hints))
        return None

    log.info("{0} || resolved {1} export target(s) | hint={2}".format(_str_func, len(l_select), export_root_hint))
    return l_select


def export_unparent_members_to_world(member_nodes, _str_func='export_unparent_members_to_world'):
    """Unparent export set members to world so delete_tdSet roots (e.g. master) do not remove them."""
    for mNode in member_nodes or []:
        if not mNode or not mc.objExists(mNode):
            continue
        _path = (mc.ls(mNode, l=True) or [mNode])[0]
        if not _path or not mc.objExists(_path):
            continue
        if mc.listRelatives(_path, parent=True):
            try:
                mc.parent(_path, world=True)
                log.info("{0} || unparented to world: {1}".format(_str_func, _path))
            except Exception as err:
                log.warning("{0} || unparent failed | node={1} | err={2}".format(_str_func, _path, err))


def export_constraints_clear_on_members(member_nodes, zeroRoot=False, _str_func='export_constraints_clear_on_members'):
    """Remove constraints (and optionally zero rootMotion) on export set members before delete."""
    for mNode in member_nodes or []:
        if not mNode or not mc.objExists(mNode):
            continue
        _constraints = mc.listRelatives(mNode, ad=True, type='constraint', fullPath=True) or []
        if _constraints:
            mc.delete(_constraints)
        if zeroRoot and mc.objExists('{0}.cgmTypeModifier'.format(mNode)):
            if mc.getAttr('{0}.cgmTypeModifier'.format(mNode)) == 'rootMotion':
                log.info("{0} || Zeroing root: {1}".format(_str_func, mNode))
                mc.cutKey(mNode, at=['translate', 'rotate'], clear=True)
                mc.setAttr('{0}.translate'.format(mNode), 0, 0, 0, type='float3')
                mc.setAttr('{0}.rotate'.format(mNode), 0, 0, 0, type='float3')


def export_prep_non_referenced(export_root_hint,
                               deleteSetName='delete_tdSet',
                               exportSetName='export_tdSet',
                               removeNamespace=False,
                               zeroRoot=False,
                               parentExportToWorld=True,
                               _str_func='export_prep_non_referenced'):
    """
    Non-referenced export prep: constraints on export members, per-rig delete sets,
    optional namespace merge, then resolve export selection (not the export hint root).
    Returns list of DAG paths for FBX selection, or None on failure.
    """
    _shortObj = export_root_hint.split('|')[-1]
    namespaces = _shortObj.split(':')[:-1] if ':' in _shortObj else []

    resolved_export = resolve_td_set_for_asset(exportSetName, namespaces or None)
    l_exportMemberNodes = []
    if resolved_export and mc.objExists(resolved_export):
        _setMembers = mc.sets(resolved_export, q=True) or []
        if isinstance(_setMembers, str):
            _setMembers = [_setMembers]
        l_exportMemberNodes = [m for m in _setMembers if m]
        log.info("{0} || export set resolved: {1} | members: {2}".format(
            _str_func, resolved_export, len(l_exportMemberNodes)))
    else:
        log.warning("{0} || export set not found before delete | hint={1}".format(_str_func, export_root_hint))

    export_constraints_clear_on_members(l_exportMemberNodes, zeroRoot=zeroRoot, _str_func=_str_func)
    if parentExportToWorld:
        export_unparent_members_to_world(l_exportMemberNodes, _str_func=_str_func)

    resolved_delete_pre = resolve_td_set_for_asset(deleteSetName, namespaces or None) if namespaces else None
    if resolved_delete_pre:
        ProcessDeleteSet(deleteSetName,
                         resolved_set=resolved_delete_pre,
                         _str_func='{0}|delete_pre_ns'.format(_str_func))

    if removeNamespace and ':' in export_root_hint:
        _nsParts = _shortObj.split(':')[:-1]
        _namespaces = []
        _nsAccum = []
        for _part in _nsParts:
            _nsAccum.append(_part)
            _namespaces.append(':'.join(_nsAccum))
        for _ns in reversed(_namespaces):
            if mc.namespace(exists=_ns):
                try:
                    mc.namespace(removeNamespace=_ns, mergeNamespaceWithRoot=True)
                    log.info("{0} || Removed namespace: {1}".format(_str_func, _ns))
                except Exception as err:
                    log.error("{0} || namespace merge failed | ns={1} | err={2}".format(_str_func, _ns, err))
                    return None

    resolved_delete_post = resolve_td_set_for_asset(deleteSetName, None)
    if resolved_delete_post and resolved_delete_post != resolved_delete_pre:
        ProcessDeleteSet(deleteSetName,
                         resolved_set=resolved_delete_post,
                         _str_func='{0}|delete_post_ns'.format(_str_func))
    elif resolved_delete_post and not resolved_delete_pre:
        ProcessDeleteSet(deleteSetName,
                         resolved_set=resolved_delete_post,
                         _str_func='{0}|delete_post_ns'.format(_str_func))

    return export_select_targets_resolve(export_root_hint,
                                         exportSetName=exportSetName,
                                         member_hints=l_exportMemberNodes,
                                         _str_func='{0}|select'.format(_str_func))


def Prep(removeNamespace = False, 
         deleteSetName = "delete_tdSet",
         exportSetName = "export_tdSet",
         zeroRoot = False,
         breakTextures = True,
         parentExportToWorld = True):
    
    _str_func = 'Prep'
    
    prepped = True
    
    #if(mc.optionVar(exists='cgm_delete_set')):
    #    deleteSetName = mc.optionVar(q='cgm_delete_set')
    #if(mc.optionVar(exists='cgm_export_set')):
    #    exportSetName = mc.optionVar(q='cgm_export_set')

    try:
        _sel = mc.ls(sl=True) or []
        if not _sel:
            log.error("{0} || No selection found. Select top node and try again.".format(_str_func))
            return False
        topNode = cgmMeta.asMeta(_sel[0])
    except Exception:
        log.exception("{0} || Failed to resolve selected top node.".format(_str_func))
        return False

    currentTime = mc.currentTime(q=True)

    _topShort = topNode.mNode.split('|')[-1]
    topNodeSN = _topShort.split(':')[-1]
    namespaces = _topShort.split(':')[:-1]
    _exportRootHint = _topShort

    log.info("{0} || mNode: {1}".format(_str_func,topNode.mNode))
    log.info("{0} || topNode: {1} | namespaces: {2}".format(_str_func,topNodeSN,namespaces))
    log.info("{0} || ref import".format(_str_func))
    
    # import reference
    if( mc.referenceQuery(topNode.mNode, isNodeReferenced=True) ):
        refFile = mc.referenceQuery( topNode.mNode ,filename=True )
        topRefNode = mc.referenceQuery( topNode.mNode, referenceNode=True, topReference=True)
        topRefFile = mc.referenceQuery(topRefNode, filename=True)

        while refFile != topRefFile:
            mc.file(topRefFile, ir=True)
            topRefNode = mc.referenceQuery( topNode.mNode, referenceNode=True, topReference=True)
            topRefFile = mc.referenceQuery(topRefNode, filename=True)

        mc.file(topRefFile, ir=True)

    # Break texture links if requested
    if breakTextures:
        log.info("{0} || breaking texture links".format(_str_func))
        # We'll break all textures in the scene since export objects aren't determined yet
        # This ensures textures are broken before any further processing
        BreakTextureLinks()

    log.info("{0} || namespaces".format(_str_func))
    
    if len(namespaces) > 0:
        for space in namespaces[:-1]:
            mc.namespace( removeNamespace = space, mergeNamespaceWithRoot = True)
        ns = '%s:' % namespaces[-1]
    else:
        ns = None
        #ns = "%s_" % topNode.mNode

    _ns_hint = namespaces[-1] if namespaces else None
    resolved_export = resolve_td_set_for_asset(exportSetName, namespaces)
    _exportMemberHintStrings = []
    if resolved_export:
        exportSet = resolved_export
        log.info("{0} || export set resolved: {1}".format(_str_func, exportSet))
        _setMembersRaw = mc.sets(exportSet, q=True) or []
        if isinstance(_setMembersRaw, str):
            _setMembersRaw = [_setMembersRaw]
        _exportMemberHintStrings = [m for m in _setMembersRaw if m]
        exportSetObjs = cgmMeta.asMeta(_setMembersRaw)
    else:
        exportSet = "{0}{1}".format(ns, exportSetName) if ns else exportSetName
        log.warning("{0} || export set not found, using top node | tried={1}".format(_str_func, exportSet))
        exportSetObjs = [topNode]
        if topNode.mNode:
            _exportMemberHintStrings = [topNode.mNode]

    if not exportSetObjs:
        exportSetObjs = [topNode]
        if topNode.mNode and not _exportMemberHintStrings:
            _exportMemberHintStrings = [topNode.mNode]

    log.info("{0} || export set: {1}".format(_str_func, exportSet))
    if exportSetObjs:
        for exportObj in exportSetObjs:
            log.info("{0} || exportObj: {1}".format(_str_func,exportObj.mNode))
            mc.delete(mc.listRelatives(exportObj.mNode, ad=True, type='constraint', fullPath = 1))

            if zeroRoot and mc.objExists('{0}.cgmTypeModifier'.format(exportObj.mNode)):
                if mc.getAttr('{0}.cgmTypeModifier'.format(exportObj.mNode)) == 'rootMotion':
                    log.info("{0} || Zeroing root: {1}".format(_str_func,exportObj.mNode))
                    mc.cutKey(exportObj.mNode, at=['translate', 'rotate'], clear=True)
                    mc.setAttr('{0}.translate'.format(exportObj.mNode), 0, 0, 0, type='float3')
                    mc.setAttr('{0}.rotate'.format(exportObj.mNode), 0, 0, 0, type='float3')
                
    if parentExportToWorld:
        export_unparent_members_to_world(_exportMemberHintStrings, _str_func='{0}|unparent'.format(_str_func))

    # export
    newTopNode = '%s%s' % (ns, topNodeSN)
    if not mc.objExists(newTopNode):
        if mc.objExists(topNode.mNode):
            newTopNode = topNode
    else:
        newTopNode = cgmMeta.asMeta(newTopNode)
            
    log.info("{0} || topNode: {1}".format(_str_func,newTopNode.mNode))
            
    
    # revert to old name
    #for i, tempObj in enumerate(namespaceTransforms):
    #    tempObj.name = origNames[i]

    # revert to previous settings
    mc.currentTime(currentTime)

    if resolved_export and mc.objExists(resolved_export):
        _setMembers = mc.sets(resolved_export, q=True) or []
        if _setMembers:
            mc.select(_setMembers)
        else:
            mc.select([x.mNode for x in exportSetObjs])
    else:
        log.info("{0} || selecting export fallback objects".format(_str_func))
        mc.select([x.mNode for x in exportSetObjs])

    exportObjs = cgmMeta.asMeta(mc.ls(sl=True))

    # delete garbage (optional — missing delete set is not a hard failure)
    log.info("{0} || delete set (Prep) | namespace_prefix={1}".format(_str_func, _ns_hint))
    resolved_delete = resolve_td_set_for_asset(deleteSetName, namespaces)
    if resolved_delete:
        if not ProcessDeleteSet(deleteSetName, resolved_set=resolved_delete, _str_func=_str_func):
            prepped = False
    else:
        log.warning("{0} || No delete set found (optional) | deleteSetName={1} | namespace_prefix={2}".format(
            _str_func, deleteSetName, _ns_hint))

    if removeNamespace and namespaces:
        _last_ns = namespaces[-1]
        if mc.namespace(exists=_last_ns):
            try:
                mc.namespace(removeNamespace=_last_ns, mergeNamespaceWithRoot=True)
                log.info("{0} || merged namespace: {1}".format(_str_func, _last_ns))
            except Exception as err:
                log.warning("{0} || namespace merge failed | ns={1} | err={2}".format(_str_func, _last_ns, err))
        else:
            log.info("{0} || namespace already removed | ns={1}".format(_str_func, _last_ns))

    _memberHints = list(_exportMemberHintStrings)
    l_select = export_select_targets_resolve(_exportRootHint,
                                             exportSetName=exportSetName,
                                             member_hints=_memberHints,
                                             _str_func='{0}|select'.format(_str_func))
    if not l_select:
        l_select = [x.mNode for x in exportObjs if getattr(x, 'mNode', None) and mc.objExists(x.mNode)]
    if l_select:
        mc.select(l_select)
    else:
        log.error("{0} || No export selection after delete prep".format(_str_func))
        prepped = False

    mc.refresh()
            

    return prepped

def MakeExportCam(inputCam):
    inputCamShape = mc.listRelatives(inputCam, shapes=True, fullPath = 1)[0]
    exportCam, exportCamShape = mc.camera(name='exportCam')
    mc.parentConstraint(inputCam, exportCam, mo=False)
    mc.connectAttr('%s.focalLength' % inputCam, '%s.focalLength' % exportCamShape)
    
    mObj = cgmMeta.asMeta(exportCam)
    mObj.rename('exportCam')

    return mObj.mNode