"""
name_utils
Josh Burton 
www.cgmonastery.com

"""
__MAYALOCAL = 'NODES'

# From Python =============================================================
import copy
import re
import pprint

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# From Maya =============================================================
import maya.cmds as mc
import maya.mel as mel

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGeneral
from cgm.core.lib import search_utils as SEARCH
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.lib import shared_data as SHARED
from cgm.core.lib import attribute_utils as ATTR

#import cgm.core.lib.list_utils as LISTS
#reload(SHARED)

#CANNOT IMPORT: DIST, LOC
from cgm.core.lib import attribute_utils as ATTR
from cgm.lib import attributes

#>>> Utilities
#===================================================================
def add_follicle(mesh, name = 'follicle'):
    """
    Creates named follicle node on a mesh
    
    :parameters:
        mesh(str): Surface to attach to
        name(str): base name for the follicle

    :returns
        [newNode, newTransform]
    """   
    _str_func = "add_follicle"
    
    _node= create(name,'follicle')
    
    if SEARCH.is_shape(mesh):
        _surface = mesh
    else:
        _surface = mc.listRelatives(mesh,shapes=True,fullPath = True)[0]
    _type = VALID.get_mayaType(_surface)
    _trans = SEARCH.get_transform(_node)
    
    ATTR.connect((_surface+'.worldMatrix[0]'),(_node+'.inputWorldMatrix'))#surface to follicle node 
    if _type == 'mesh': 
        ATTR.connect((_surface+'.outMesh'),(_node+'.inputMesh'))    #surface mesh to follicle input mesh
    else:
        ATTR.connect((_surface+'.local'),(_node+'.inputSurface'))    #surface mesh to follicle input mesh
        
    ATTR.connect((_node+'.outTranslate'),(_trans+'.translate'))
    ATTR.connect((_node+'.outRotate'),(_trans+'.rotate'))    
    
    #ATTR.set_message(_node,'follTrans',_trans)
    #ATTR.set_message(_trans,'follNode',_node)
    
    ATTR.set_standardFlags(_trans)
        
    return [_node,_trans]    
    
    """follicleNode = createNamedNode((name),'follicle')
        
    #closestPointNode = createNamedNode((targetObj+'_to_'+mesh),'closestPointOnMesh')
    controlSurface = mc.listRelatives(mesh,shapes=True)[0]
    follicleTransform = mc.listRelatives(follicleNode,p=True)[0]
    
    ATTR.connect((controlSurface+'.worldMatrix[0]'),(follicleNode+'.inputWorldMatrix'))#surface to follicle node 
    if objType == 'mesh': 
        ATTR.connect((controlSurface+'.outMesh'),(follicleNode+'.inputMesh'))    #surface mesh to follicle input mesh
    else:
        ATTR.connect((controlSurface+'.local'),(follicleNode+'.inputSurface'))    #surface mesh to follicle input mesh
        
    ATTR.connect((follicleNode+'.outTranslate'),(follicleTransform+'.translate'))
    ATTR.connect((follicleNode+'.outRotate'),(follicleTransform+'.rotate'))    
    
    ATTR.set_standardFlags(follicleTransform)
    
    return [follicleNode,follicleTransform] """
    
def create(name = None, nodeType = None):
    """
    Create a named node
    
    :parameters:
        name(str): base name
        nodeType(str): 
            follicle

    :returns
        [newNode, newTransform]
    """   
    _str_func = "create"
    
    if name is None:
        name = 'i_should_have_given_a_name'
    _suffix = SHARED._d_node_to_suffix.get(nodeType,nodeType)
    if _suffix == False:
        raise ValueError("Update cgm.core.lib.shared_data._d_node_to_suffix with nodeType: {0}".format(nodeType))
    
    _l_utilityNodes = ['plusMinusAverage','condition']
    
    if nodeType in _l_utilityNodes:
        return mc.shadingNode (nodeType,name= (name+'_'+_suffix), asUtility=True)
    else:
        return mc.createNode (nodeType,name= (name+'_'+_suffix),)
    
def curveInfo(curve,baseName = 'curveInfo'):
    """
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    DESCRIPTION:
    Creates a curve lenght measuring node

    ARGUMENTS:
    polyFace(string) - face of a poly

    RETURNS:
    length(float)
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    """
    _str_func = 'curveInfo'
    
    if VALID.is_shape(curve):
        l_shapes = [curve]
    else:
        l_shapes = mc.listRelatives(curve, s=True,fullPath = True)
    
    if len(l_shapes)>1:
        raise ValueError(cgmGeneral.logString_msg(__str_func,"Must have one shape. Found {0} | {1}".format(len(l_shapes),l_shapes)))
    

    infoNode = create(baseName,'curveInfo')
    ATTR.connect((l_shapes[0]+'.worldSpace'),(infoNode+'.inputCurve'))
    return infoNode
    
#Dup function from Shapes to avoid circle import
def get_original(shape):
    """
    Get the original shape on a transform
    
    :parameters:
        shape(str): Shape to check

    :returns
        non intermediate shape(string)
    """   
    _str_func = "get_original"
    connections = mc.listConnections(shape, source=True, destination=False, shapes=True)
    
    if connections:
        for connection in connections:
            if mc.nodeType(connection) in ["mesh","nurbsSurface"]:
                return connection
            #elif mc.nodeType(connection) == "transform":
            #    return get_original(connection)
    return None

def create_UVPin(targetSurface, pin = None, name = 'uvPin', u=.5,v=.5, normalAxis = 2, tangentAxis = 0, useExising = True) :
    """
    Creates named uvPin node on a mesh
    
    Keywords
    mesh -- mesh to attach to
    name -- base name to use ('follicle' default)
    
    Returns
    [uvPinNode,pin]
    """
    _str_func = 'create_UVPin'
    if SEARCH.is_shape(targetSurface):
        l_shapes = [targetSurface]
    else:
        l_shapes = mc.listRelatives(targetSurface, s=True,fullPath = True)
    if not l_shapes:
        raise ValueError("Must have shapes to check.")


    _shape = l_shapes[0]
    
    _type = VALID.get_mayaType(_shape)    
    
    if _type == "mesh":
        componentPrefix = ".vtx"
        cAttr = ".inMesh"
        cAttr2 = ".worldMesh[0]"
        cAttr3 = ".outMesh"
    elif _type == "nurbsSurface":
        componentPrefix = ".cv"
        cAttr = ".create"
        cAttr2 = ".worldSpace[0]"
        cAttr3 = ".local"
        #if components == [0]:
        #    components = [[0,0]]
    else:
        raise ValueError("{} unknown type: {}".format(_str_func,_type))
    
    
    
    uvPinNode = ATTR.get_message(_shape, 'uvPinNode')
    if ATTR.get_message(_shape, 'uvPinNode'):
        uvPinNode = uvPinNode[0]
        log.warning(cgmGeneral.logString_msg(_str_func, "Using existing uvPinNode: {}".format(uvPinNode)))
    
    else:
        #Creating new pin node
        log.debug("_shape: {0}".format(_shape))
        
        #objType = search.returnObjectType(mesh)
        #assert objType in ['mesh','nurbsSurface'],("'%s' isn't a mesh"%mesh)
            
        uvPinNode = create((name),'uvPin')
        
        #Get original shape
        _shapeOrig = get_original(_shape) or _shape
        
        
        """ make the closest point node """
        #closestPointNode = createNamedNode((targetObj+'_to_'+mesh),'closestPointOnMesh')
        #controlSurface = mc.listRelatives(_shape,shapes=True)[0]
        #follicleTransform = mc.listRelatives(uvPinNode,p=True,fullPath = True)[0]
        #pin = mc.rename("uvPin")
        
        mc.connectAttr("{0}{1}".format(_shape,cAttr2),"{0}.deformedGeometry".format(uvPinNode))
        mc.connectAttr("{0}{1}".format(_shapeOrig,cAttr3),"{0}.originalGeometry".format(uvPinNode))
    
        ATTR.set_message(_shape, 'uvPinNode', uvPinNode)
        

        
    ATTR.set(uvPinNode,'normalAxis',normalAxis)
    ATTR.set(uvPinNode,'tangentAxis',tangentAxis)
    
    
    _idx = ATTR.get_nextCompoundIndex(uvPinNode,'coordinate')
    if pin == None:
        pin = mc.spaceLocator(name = '{}_{}_pin'.format(name,_idx))[0]
    
    #Set our coordinate
    mc.setAttr("{}.coordinate[{}]".format(uvPinNode,_idx), u,v)
    mc.connectAttr("{}.outputMatrix[{}]".format(uvPinNode,_idx), "{0}.offsetParentMatrix".format(pin))
    
    #ATTR.set_standardFlags(follicleTransform)
    
    return [uvPinNode,pin,_idx]

def createFollicleOnMesh(targetSurface, name = 'follicle'):
    """
    Creates named follicle node on a mesh
    
    Keywords
    mesh -- mesh to attach to
    name -- base name to use ('follicle' default)
    
    Returns
    [follicleNode,follicleTransform]
    """
    
    if SEARCH.is_shape(targetSurface):
        l_shapes = [targetSurface]
    else:
        l_shapes = mc.listRelatives(targetSurface, s=True,fullPath = True)
    if not l_shapes:
        raise ValueError("Must have shapes to check.")


    _shape = l_shapes[0]
    log.debug("_shape: {0}".format(_shape))
    _type = VALID.get_mayaType(_shape)    
    
    #objType = search.returnObjectType(mesh)
    #assert objType in ['mesh','nurbsSurface'],("'%s' isn't a mesh"%mesh)
        
    follicleNode = create((name),'follicle')
    
    """ make the closest point node """
    #closestPointNode = createNamedNode((targetObj+'_to_'+mesh),'closestPointOnMesh')
    #controlSurface = mc.listRelatives(_shape,shapes=True)[0]
    follicleTransform = mc.listRelatives(follicleNode,p=True,fullPath = True)[0]
    
    ATTR.connect((_shape+'.worldMatrix[0]'),(follicleNode+'.inputWorldMatrix'))#surface to follicle node 
    
    if _type == 'mesh': 
        ATTR.connect((_shape+'.outMesh'),(follicleNode+'.inputMesh'))    #surface mesh to follicle input mesh
    else:
        ATTR.connect((_shape+'.local'),(follicleNode+'.inputSurface'))    #surface mesh to follicle input mesh
        
    ATTR.connect((follicleNode+'.outTranslate'),(follicleTransform+'.translate'))
    ATTR.connect((follicleNode+'.outRotate'),(follicleTransform+'.rotate'))    
    
    ATTR.set_standardFlags(follicleTransform)
    
    return [follicleNode,follicleTransform]


def _rivetClosestFaceIndex(shape, targetObj=None, targetPoint=None):
    """Return closest face index on mesh shape for a world position."""
    from cgm.core.lib import position_utils as POS

    if targetObj is not None:
        _point = POS.get(targetObj)
    elif targetPoint:
        _point = targetPoint
    else:
        raise ValueError("Need targetObj or targetPoint")

    _cpom = mc.createNode('closestPointOnMesh')
    mc.connectAttr('{0}.worldMesh[0]'.format(shape), '{0}.inMesh'.format(_cpom), f=True)
    mc.setAttr('{0}.inPosition'.format(_cpom), _point[0], _point[1], _point[2], type='double3')
    _face = int(mc.getAttr('{0}.closestFaceIndex'.format(_cpom)))
    mc.delete(_cpom)
    return _face


def _createRivet_mayaConstraint(shape, face_id):
    """
    Use Maya's built-in Rivet constraint path (Constraints menu) when available.
    """
    _str_func = '_createRivet_mayaConstraint'
    _priorSel = mc.ls(sl=True, long=True) or []
    try:
        mc.select(cl=True)
        mc.select('{0}.f[{1}]'.format(shape, face_id), r=True)
        try:
            import maya.internal.nodes.uvpin.cmd_create as ptguv
            ptguv.Command().execute(setupMode=0, outputConnect=3, allowCreateWithoutInputs=False)
        except ImportError:
            return None

        _rivet = mc.ls(sl=True, type='transform', long=True) or []
        if _rivet:
            return _rivet[0]
        log.debug("|{0}| >> Rivet command ran but no transform selected".format(_str_func))
        return None
    except Exception as err:
        log.debug("|{0}| >> {1}".format(_str_func, err))
        return None
    finally:
        if _priorSel:
            mc.select(_priorSel, r=True)
        else:
            mc.select(cl=True)


def _createRivet_classic(shape, face_id, name='rivet'):
    """Classic polygon rivet node network (curveFromMeshEdge + loft + POSI)."""
    _str_func = '_createRivet_classic'
    _edges = mc.polyListComponentConversion('{0}.f[{1}]'.format(shape, face_id),
                                            fromFace=True, toEdge=True)
    _edgeList = mc.ls(_edges, flatten=True) or []
    if len(_edgeList) < 2:
        raise ValueError("|{0}| >> Need at least two edges on face {1}".format(_str_func, face_id))

    _e1 = int(_edgeList[0].split('[')[-1].rstrip(']'))
    _e2 = int(_edgeList[1].split('[')[-1].rstrip(']'))

    _cfme1 = mc.createNode('curveFromMeshEdge', n='{0}_rivetCFME1'.format(name))
    mc.setAttr('{0}.ihi'.format(_cfme1), 1)
    mc.setAttr('{0}.ei[0]'.format(_cfme1), _e1)

    _cfme2 = mc.createNode('curveFromMeshEdge', n='{0}_rivetCFME2'.format(name))
    mc.setAttr('{0}.ihi'.format(_cfme2), 1)
    mc.setAttr('{0}.ei[0]'.format(_cfme2), _e2)

    _loft = mc.createNode('loft', n='{0}_rivetLoft1'.format(name))
    mc.setAttr('{0}.ic[0].ik'.format(_loft), 1)
    mc.setAttr('{0}.ic[1].ik'.format(_loft), 1)
    mc.setAttr('{0}.u'.format(_loft), True)

    _posi = mc.createNode('pointOnSurfaceInfo', n='{0}_rivetPOSI1'.format(name))

    mc.connectAttr('{0}.os'.format(_loft), '{0}.is'.format(_posi), f=True)
    mc.connectAttr('{0}.oc'.format(_cfme1), '{0}.ic[0]'.format(_loft), f=True)
    mc.connectAttr('{0}.oc'.format(_cfme2), '{0}.ic[1]'.format(_loft), f=True)
    mc.connectAttr('{0}.worldMesh[0]'.format(shape), '{0}.im'.format(_cfme1), f=True)
    mc.connectAttr('{0}.worldMesh[0]'.format(shape), '{0}.im'.format(_cfme2), f=True)

    _rivetXform = mc.createNode('transform', n=name)
    mc.createNode('locator', n='{0}Shape'.format(_rivetXform), p=_rivetXform)

    _ac = mc.createNode('aimConstraint', p=_rivetXform, n='{0}_rivetAimConstraint1'.format(_rivetXform))
    mc.setAttr('{0}.tg[0].tw'.format(_ac), 1)
    mc.setAttr('{0}.a'.format(_ac), 0, 1, 0, type='double3')
    mc.setAttr('{0}.u'.format(_ac), 0, 0, 1, type='double3')
    for _attr in ('v', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
        mc.setAttr('{0}.{1}'.format(_ac, _attr), k=False)

    mc.connectAttr('{0}.position'.format(_posi), '{0}.translate'.format(_rivetXform), f=True)
    mc.connectAttr('{0}.n'.format(_posi), '{0}.tg[0].tt'.format(_ac), f=True)
    mc.connectAttr('{0}.tv'.format(_posi), '{0}.wu'.format(_ac), f=True)
    mc.connectAttr('{0}.crx'.format(_ac), '{0}.rx'.format(_rivetXform), f=True)
    mc.connectAttr('{0}.cry'.format(_ac), '{0}.ry'.format(_rivetXform), f=True)
    mc.connectAttr('{0}.crz'.format(_ac), '{0}.rz'.format(_rivetXform), f=True)

    return _rivetXform


def createRivetOnMesh(targetSurface, targetObj=None, targetPoint=None, name='rivet'):
    """
    Create a rivet on the closest face to a target position.

    Tries Maya's Constraints > Rivet API first, then classic edge-loft rivet nodes.

    :param targetSurface: mesh shape or transform
    :param targetObj: object to sample position from
    :param targetPoint: [x,y,z] world position (if no targetObj)
    :param name: base name (rivet transform is renamed via caller meta naming)
    :returns: rivet transform (str)
    """
    _str_func = 'createRivetOnMesh'

    _shape = SEARCH.get_nonintermediateShape(targetSurface)
    if not _shape or VALID.get_mayaType(_shape) != 'mesh':
        raise ValueError("|{0}| >> Rivet requires a mesh surface".format(_str_func))

    _face = _rivetClosestFaceIndex(_shape, targetObj=targetObj, targetPoint=targetPoint)

    _rivet = _createRivet_mayaConstraint(_shape, _face)
    if _rivet:
        return _rivet

    log.debug("|{0}| >> Falling back to classic rivet network".format(_str_func))
    return _createRivet_classic(_shape, _face, name=name)


def create_UVPinOnMesh(targetSurface, targetObj=None, targetPoint=None, u=None, v=None,
                       name='uvPin', pin=None, useExisting=True):
    """
    Create a uvPin-driven tracker on mesh at closest-point UV (or explicit u/v).

    :returns: [uvPinNode, pinTransform, coordinateIndex]
    """
    _str_func = 'create_UVPinOnMesh'
    from cgm.core.lib import distance_utils as DIST

    _shape = SEARCH.get_nonintermediateShape(targetSurface)
    if not _shape or VALID.get_mayaType(_shape) != 'mesh':
        raise ValueError("|{0}| >> uvPin requires a mesh surface".format(_str_func))

    if u is None or v is None:
        _dat = DIST.get_closest_point_data_from_mesh(_shape, targetObj=targetObj, targetPoint=targetPoint)
        u = _dat['parameterU']
        v = _dat['parameterV']

    return create_UVPin(_shape, pin=pin, name=name, u=u, v=v, useExising=useExisting)



d_function_to_Operator = {'==':0,'!=':1,'>':2,'>=':3,'<':4,'<=':5,#condition
                          '*':1,'/':2,'^':3,#md
                          '+':1,'-':2,'><':3}#pma

d_operator_to_NodeType = {'clamp':['clamp('],
                          'setRange':['setRange('],
                          'condition':[' == ',' != ',' > ',' < ',' >= ',' <= '],
                          'multiplyDivide':[' * ',' / ',' ^ '],
                          'plusMinusAverage':[' + ',' - ',' >< ']}#>< we're using for average

d_node_to_input = {'multiplyDivide':{'in':['input1','input2'],
                                     'out':'output'},
                   'plusMinusAverage':{'in':['input1'],
                                       'out':'output'}}

def optimize(nodeTypes='multiplyDivide'):
    _str_func = 'optimize'
    log.debug("|{0}| >>  ".format(_str_func)+ '-'*80)
    
    _nodeTypes = VALID.listArg(nodeTypes)
    d_modeToNodes = {}
    d_modeToPlugs = {}
    l_oldNodes = []
    
    for t in _nodeTypes:
        if t in ['plusMinusAverage']:
            raise ValueError("Don't handle type: {0}".format(t))
        nodes = mc.ls(type=t)
        l_oldNodes.extend(nodes)
        for n in nodes:
            _mode = ATTR.get(n,'operation')
            _operator = ATTR.get_enumValueString(n,'operation')
            #d_operator_to_NodeType[t][_mode]
            
            if not d_modeToNodes.get(_mode):
                d_modeToNodes[_mode] = []
            d_modeToNodes[_mode].append(n)
            
            d_plugs = {}
            d_plugValues = {}
            for i,inPlug in enumerate(d_node_to_input[t]['in']):
                d_plugs[i] = ATTR.get_children(n,inPlug) or []
                for p in d_plugs[i]:
                    c = ATTR.get_driver(n,p,False,skipConversionNodes=True)
                    if c:
                        d_plugValues[p] = c
                    else:
                        d_plugValues[p] = ATTR.get(n,p)
                    
            l_outs = ATTR.get_children(n,d_node_to_input[t]['out']) or []
            for p in l_outs:
                d_plugValues[p] = ATTR.get_driven(n,p,False,skipConversionNodes=True)
            
            #pprint.pprint(d_modeToNodes)
            #pprint.pprint(d_plugs)
            #print l_outs
            #print cgmGeneral._str_subLine
            #pprint.pprint(d_plugValues)
            
            for i in range(len(l_outs)):
                _out = d_plugValues[l_outs[i]]
                if _out:
                    d_set = {'out':_out, 'in':[]}
                    log.debug("|{0}| >> Output found on: {1} ".format(_str_func,_out))
                    _keys = list(d_plugs.keys())
                    _keys.sort()
                    for k in _keys:
                        d_set['in'].append(d_plugValues[  d_plugs[k][i] ])
                        #d_set['in'].append(d_plugs[k][i])
                    #pprint.pprint(d_set)
                    
                    if not d_modeToPlugs.get(_mode):
                        d_modeToPlugs[_mode] = []
                    d_modeToPlugs[_mode].append(d_set)
                    
            #    if VALID.stringArg()



    l_inPlugs = ['input1','input2']
    l_outplugs = ['output']
    l_new = []
    _cnt = 0
        
    for operator,d_sets in list(d_modeToPlugs.items()):
        if operator == 1:
            for nodeSet in d_sets:
                newNode = mc.createNode('multDoubleLinear')
                newNode = mc.rename(newNode,'optimize_{0}_mdNode'.format(_cnt))
                _cnt+=1
                l_new.append(newNode)
                
                _ins = d_set['in']
                _outs = d_set['out']
                
                for iii,inPlug in enumerate(_ins):
                    if mc.objExists(inPlug):
                        ATTR.connect(inPlug, "{0}.{1}".format(newNode, l_inPlugs[iii]))
                    else:
                        ATTR.set(newNode,l_inPlugs[iii], inPlug)
                    
                for out in _outs:
                    ATTR.connect("{0}.output".format(newNode), out)
                    
        #pprint.pprint(d_setsSorted)
        print((len(d_sets)))
        #print len(d_setsSorted)    
    
    
    
    """
    
    l_inPlugs = {0: [u'input1X', u'input1Y', u'input1Z'],
               1: [u'input2X', u'input2Y', u'input2Z']}
    l_outplugs = [u'outputX', u'outputY', u'outputZ']
    
    for operator,d_sets in d_modeToPlugs.iteritems():
        d_setsSorted = LISTS. get_chunks(d_sets,3)
        for nodeSet in d_setsSorted:
            newNode = mc.createNode('multiplyDivide')
            newNode = mc.rename(newNode,'optimize_{0}_mdNode'.format(_cnt))
            _cnt+=1
            l_new.append(newNode)
            ATTR.set(newNode,'operation',operator)
            
            for i,d_set in enumerate(nodeSet):
                _ins = d_set['in']
                _outs = d_set['out']
                
                for iii,inPlug in enumerate(_ins):
                    if mc.objExists(inPlug):
                        ATTR.connect(inPlug, "{0}.{1}".format(newNode, l_inPlugs[iii][i]))
                    else:
                        ATTR.set(newNode,l_inPlugs[iii][i], inPlug)
                    
                for out in _outs:
                    ATTR.connect("{0}.{1}".format(newNode, l_outplugs[i]), out)
                    
        #pprint.pprint(d_setsSorted)
        print len(d_sets)
        print len(d_setsSorted)
        """
    mc.delete(l_oldNodes)
    return len(l_new)
    
    

    
def renderer_clean(check='Mayatomr',clean=False):
    """
    Hattip: https://forums.autodesk.com/t5/maya-shading-lighting-and/maya-2017-scene-error-warning-about-mental-ray-nodes/td-p/6627874
    """
    d_rendererNodes = {'turtle':['TurtleRenderOptions',
                                 'TurtleUIOptions',
                                 'TurtleBakeLayerManager',
                                 'TurtleDefaultBakeLayer']}
    _str_func = 'renderer_clean'
    log.debug("|{0}| >> [{1}] | clean: {2}...".format(_str_func,check,clean))
    
    if check in ['Mayatomr']:
        l = mc.ls(type='unknown')
        log.debug("|{0}| >> unknown nodes: {1}".format(_str_func,len(l)))
        
        for n in l:
            try:
                _test = mc.unknownNode(n, q=True,p=1)
                if _test == check:
                    log.debug("|{0}| >> matches: {1}".format(_str_func,n))
                    if clean:
                        mc.delete(n)
            except:pass
            
        if check in mc.unknownPlugin(q=1,list=1) or []:
            log.debug("|{0}| >> Found: {1}".format(_str_func,check))
            if clean:
                log.debug("|{0}| >> Removing: {1}".format(_str_func,check))
                mc.unknownPlugin(check,remove=1)
    else:
        l = d_rendererNodes.get(check.lower())
        for n in l:
            if mc.objExists(n):
                log.debug("|{0}| >> matches: {1}".format(_str_func,n))
                if clean:
                    try:mc.delete(n)
                    except Exception as err:
                        log.debug("|{0}| >> Failed: {1} | {2}".format(_str_func,n,err))
        """
        for n in mc.ls():
            if 'turtle' in n.lower():
                for n in l:
                    try:
                        _test = mc.unknownNode(n, q=True,p=1)
                        if _test == check:
                            log.debug("|{0}| >> matches: {1}".format(_str_func,n))
                            if clean:
                                mc.delete(n)"""
                
    
    

    
    
    

