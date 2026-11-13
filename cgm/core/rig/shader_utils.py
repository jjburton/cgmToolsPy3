"""
------------------------------------------
shader_utils: cgm.core.lib
Author: Josh Burton & David Bokser
email: cgmonks.info@gmail.com
Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------

"""
__MAYALOCAL = 'SHADERS'

# From Python =============================================================
import copy
import re
import pprint

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# From Maya =============================================================
import maya.cmds as mc

# From cgm ==============================================================
from cgm.core import cgm_General as cgmGen
import cgm.core.cgm_Meta as cgmMeta
from cgm.core.cgmPy import validateArgs as VALID

from cgm.core.lib import attribute_utils as ATTR
from cgm.core.lib import name_utils as coreNames
from cgm.core.lib import search_utils as SEARCH
from cgm.core.lib import shared_data as SHARED
from cgm.core.lib import snap_utils as SNAP
from cgm.core.lib import transform_utils as TRANS
import cgm.core.lib.name_utils as NAMES
import cgm.core.lib.math_utils as MATH



def create_uvPickerNetwork(target = None,
                           name = 'iris',
                           mode = 'singleSquare',
                           enums = None,
                           count = 9, split = 3,
                           maxValue = .999):
    """
    
    maxValue | float | the factor max value for our splits
    """
    _str_func = 'create_uvPickerNetwork'
    log.debug("|{0}| >> ".format(_str_func)+ '-'*80)

    if count/split != split:
        raise ValueError("{0} || Split must divide evently to count. count: {1} | split: {2}".format(_str_func,count,split))
    
    if not target:
        target = mc.group(em=True,name='uvPickerDefault')
    
    
    if mode == 'twoAttr':
        log.debug(cgmGen.logString_msg(_str_func,'2 Attr mode'))
        
        if not enums:
            enums = ['{0}_{1}'.format(name,i) for i in range(2)]
            
        for a in enums:
            ATTR.add(target,a,'enum',enumOptions=[str(i) for i in range(split)])
            
            
        for a in 'U','V':
            _a = 'res_{0}{1}'.format(name,a)
            ATTR.add(target,_a,'float',keyable=False,hidden=False)
            ATTR.set_hidden(target,_a,False)    
        
        mMD = cgmMeta.cgmNode(name = "{0}_picker_md".format(name),
                                nodeType = 'multiplyDivide')
        mMD.operation = 2
        mMD.input2X = split
        mMD.input2Y = split
        
        
        mMD.doConnectIn('input1X', "{0}.{1}".format(target,enums[0]))
        mMD.doConnectIn('input1Y', "{0}.{1}".format(target,enums[1]))
        
        
        mMD.doConnectOut('outputX', '{0}.res_{1}U'.format(target,name))
        mMD.doConnectOut('outputY', '{0}.res_{1}V'.format(target,name))
        
    elif mode == 'singleSquare':
        #split is our square split number 16 would be 4, 9 would be 3 etc
        l_base = MATH.get_splitValueList(0,maxValue,split+1)
        #l_second = MATH.get_splitValueList(0,1,split+1)
        #l_second.reverse()
        l_dat = []
        d_dat = {}
        for i in range(split):
            d_dat[i] = []
            for i2 in range(split):
                d_dat[i].append([l_base[i2], l_base[i]])
                
        l_keys = list(d_dat.keys())
        l_keys.sort()
        l_set = l_keys[1:]
        l_set.reverse()
        l_keys = [l_keys[0]] + l_set
        
        for k in l_keys:
            l_dat.extend(d_dat[k])
        
        
        pprint.pprint(l_dat)
                
        for a in ['U','V']:
            _a = 'res_{0}{1}'.format(name,a)
            ATTR.add(target,_a,'float',keyable=False,hidden=False)
            ATTR.set_hidden(target,_a,False)
            
            if a == 'U':
                _strU = "{0}.{1}".format(target,_a)
            else:
                _strV = "{0}.{1}".format(target,_a)
            
            
        ATTR.add(target,name,'int')
        mAttr = cgmMeta.cgmAttr(target,name)
        mAttr.p_maxValue = len(l_dat)
        mAttr.p_minValue = 0       
        mAttr.p_hidden = False
        
        _str_driver = mAttr.p_combinedName
        
        
        for i,vSet in enumerate(l_dat):
            log.info(cgmGen.logString_msg(_str_func, "{0} | {1} | {2}".format(_strU, i, vSet[0])))
            mc.setDrivenKeyframe(_strU,
                                 currentDriver = _str_driver,
                                 driverValue = i, value = vSet[0])
            
            log.info(cgmGen.logString_msg(_str_func, "{0} | {1} | {2}".format(_strV, i, vSet[1])))
            mc.setDrivenKeyframe(_strV,
                                 currentDriver = _str_driver,
                                 driverValue = i, value = vSet[1])
            
            
        
    else:
        log.debug(cgmGen.logString_msg(_str_func,'1 Attr mode'))
        
        _d_values = {9:[[.999,.666],
                        [.333,.666],
                        [.666,.666],
                        [.999,.333],
                        [.333,.333],
                        [.666,.333],
                        [.999,.999],
                        [.333,.999],
                        [.666,.999],],
                    16:[[.999,.666],
                        [.333,.666],
                        [.666,.666],
                        [.999,.333],
                        [.333,.333],
                        [.666,.333],
                        [.999,.999],
                        [.333,.999],
                        [.666,.999],
                        ]}
        
        l_dat = _d_values.get(count)
        if not l_dat:
            raise ValueError("{0} | count {1} not supported".format(_str_func,count))
    
        
        
        
        for a in 'U','V':
            _a = 'res_{0}{1}'.format(name,a)
            ATTR.add(target,_a,'float',keyable=False,hidden=False)
            ATTR.set_hidden(target,_a,False)
            
        mPMA = cgmMeta.cgmNode(name = "{0}_picker_pma".format(name),
                                nodeType = 'plusMinusAverage')
        mPMA.operation = 1
            
        ATTR.add(target,name,'enum',enumOptions=[str(i) for i in range(9)])
        mAttr = cgmMeta.cgmAttr(target,name)
        
        for i,vSet in enumerate(l_dat):
            _iterBase = "{0}_{1}".format(name,i)
            
            if mc.objExists('%s_condNode'%_iterBase):
                mc.delete('%s_condNode'%_iterBase)
            
            mNode = cgmMeta.cgmNode(name = "{0}_condNode".format(_iterBase),
                                    nodeType = 'condition') 
            
    
            mNode.secondTerm = i
            mNode.colorIfTrueR = vSet[0]
            mNode.colorIfTrueG = vSet[1]
            
            mNode.colorIfFalseR = 0
            mNode.colorIfFalseG = 0
            
    
            mAttr.doConnectOut('%s.firstTerm'%mNode.mNode)
            ATTR.connect('%s.outColor'%mNode.mNode, "{0}.input3D[{1}]".format(mPMA.mNode,i))
            #attributes.doConnectAttr('%s.outColorR'%mNode.mNode,'%s.%s'%(c,self.connectToAttr))         
    
        mPMA.doConnectOut('output3Dx', '{0}.res_{1}U'.format(target,name))
        mPMA.doConnectOut('output3Dy', '{0}.res_{1}V'.format(target,name))



def create_uvPickerNetworkBAK(target = None, name = 'iris', split = 9):
    _str_func = 'create_uvPickerNetwork'
    log.debug("|{0}| >> ".format(_str_func)+ '-'*80)
    
    _d_values = {9:[[.999,.666],
                    [.333,.666],
                    [.666,.666],
                    [.999,.333],
                    [.333,.333],
                    [.666,.333],
                    [.999,.999],
                    [.333,.999],
                    [.666,.999],
                    ]}
    
    l_dat = _d_values.get(split)
    if not l_dat:
        raise ValueError("{0} | split {1} not supported".format(_str_func,split))
    
    if not target:
        target = mc.group(em=True,name='uvPickerDefault')
    
    md_pmas = {}
    
    for a in 'U','V':
        _a = '{0}{1}'.format(name,a)
        ATTR.add(target,_a,'float',keyable=False,hidden=False)
        ATTR.set_hidden(target,_a,False)
        
        #if mc.objExists('%s_pma'%_iterBase):
            #mc.delete('%s_condNode'%_iterBase)
            
        mPMA = cgmMeta.cgmNode(name = "{0}_pma".format(_iterBase),
                                nodeType = 'plusMinusAverage')
        mPMA.operation = 1
        md_pmas[a] = mPMA
        
    ATTR.add(target,name,'enum',enumOptions=[str(i) for i in range(9)])
    mAttr = cgmMeta.cgmAttr(target,name)
    
    
    #Pma nodes -------------------------------------------------    
    #Condition loop ----------------------------------------
    #place 2d texture = number of rolls 
    for i,vSet in enumerate(l_dat):
        _iterBase = "{0}_{1}".format(name,i)
        
        if mc.objExists('%s_condNode'%_iterBase):
            mc.delete('%s_condNode'%_iterBase)
        
        mNode = cgmMeta.cgmNode(name = "{0}_condNode".format(_iterBase),
                                nodeType = 'condition') 
        

        mNode.secondTerm = i
        mNode.colorIfTrueR = vSet[0]
        mNode.colorIfTrueR = vSet[1]
        
        mNode.colorIfFalseR = 0
        mNode.colorIfFalseG = 0
        
        #attributes.doSetAttr(i_node.mNode,'colorIfTrueR',1)
        #attributes.doSetAttr(i_node.mNode,'colorIfFalseR',0)
        #i_node.colorIfTrueR = 1
        #i_node.colorIfTrueR = 0

        mAttr.doConnectOut('%s.firstTerm'%i_node.mNode)
        ATTR.connect('%s.outColorR'%i_node.mNode,'%s.%s'%(c,self.connectToAttr))        

    
    
        
        
    
    
    
    
    


class build_conditionNetworkFromGroup(object):
    def __init__(self, group, chooseAttr = 'switcher', controlObject = None, connectTo = 'visibility',*args,**kws):
        """Constructor"""
        self.d_iAttrs = {}#attr instances stores as {index:instance}
        self.l_iAttrs = []#Indices for iAttrs
        self.d_resultNetworksToBuild = {}#Index desctiptions of networks to build {target:[[1,2],3]}
        self.i_group = False
        self.i_control = False
        self.connectToAttr = connectTo
        self.i_attr = False

        #>>>Keyword args	
        log.debug(">>> build_conditionNetworkFromGroup.__init__")
        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))

        #Check our group
        if not mc.objExists(group):
            log.error("Group doesn't exist: '%s'"%group)
            return
        elif not SEARCH.get_mayaType(group) == 'group':
            log.error("Object is not a group: '%s'"%SEARCH.get_mayaType(group))
            return
        self.i_group = cgmMeta.cgmObject(group)
        if not self.i_group.getChildren():
            log.error("No children detected: '%s'"%group)
            return	

        #Check our control
        if controlObject is None or not mc.objExists(controlObject):
            log.error("No suitable control object found: '%s'"%controlObject)
            return
        else:
            i_controlObject = cgmMeta.cgmNode(controlObject)
            self.i_attr = cgmMeta.cgmAttr(i_controlObject,chooseAttr,attrType = 'enum',initialValue = 1)
        if self.buildNetwork(*args,**kws):
            log.debug("Chooser Network good to go")

    def buildNetwork(self,*args,**kws):
        if kws:log.debug("kws: %s"%str(kws))
        if args:log.debug("args: %s"%str(args))

        #children = self.i_group.getChildren()
        mChildren = self.i_group.getChildren(asMeta=True)
        children = [mObj.p_nameShort for mObj in mChildren]
        children.insert(0,'none')

        #Make our attr
        if len(children) == 2:
            self.i_attr.doConvert('bool')#Like bool better
            #self.i_attr.setEnum('off:on')
        else:
            self.i_attr.setEnum(':'.join(children))

        for i,c in enumerate(children[1:]):
            i_c = cgmMeta.cgmNode(c)
            #see if the node exists
            condNodeTest = ATTR.get_driver('%s.%s'%(c,self.connectToAttr), getNode=True)
            if condNodeTest:
                i_node = cgmMeta.cgmNode(condNodeTest)
            else:
                if mc.objExists('%s_condNode'%c):
                    mc.delete('%s_condNode'%c)
                i_node = cgmMeta.cgmNode(name = 'tmp', nodeType = 'condition') #Make our node

            i_node.addAttr('cgmName', i_c.getShortName(), attrType = 'string')
            i_node.addAttr('cgmType','condNode')
            i_node.doName()
            i_node.secondTerm = i+1
            ATTR.set(i_node.mNode,'colorIfTrueR',1)
            ATTR.set(i_node.mNode,'colorIfFalseR',0)
            #i_node.colorIfTrueR = 1
            #i_node.colorIfTrueR = 0

            self.i_attr.doConnectOut('%s.firstTerm'%i_node.mNode)
            ATTR.connect('%s.outColorR'%i_node.mNode,'%s.%s'%(c,self.connectToAttr))

        return True
    
    
#>> Localize referenced shading =========================================================================
_str_localizedFromAttr = 'cgmLocalizedFrom'
_l_sgInputSkipAttrs = ('dagSetMembers', 'dnSetMembers', 'groupNodes', 'partition',
                       'memberWireframeColor', 'message')

def _shadingEngine_shaderInputs(sg):
    """[(sgAttr, srcPlug)] feeding the shadingEngine's shader slots (surface/volume/displacement/renderer)."""
    _l = mc.listConnections(sg, s=True, d=False, plugs=True, connections=True) or []
    _res = []
    for i in range(0, len(_l), 2):
        _dst, _src = _l[i], _l[i+1]
        _attr = _dst.split('.', 1)[-1].split('[')[0]
        if _attr in _l_sgInputSkipAttrs:
            continue
        _srcNode = _src.split('.')[0]
        if mc.objectType(_srcNode, isAType='dagNode') or mc.objectType(_srcNode) in ('groupId', 'partition'):
            continue
        _res.append((_dst.split('.', 1)[-1], _src))
    return _res

def _shadingEngine_isReferenced(sg):
    if mc.referenceQuery(sg, isNodeReferenced=True):
        return True
    for _attr, _src in _shadingEngine_shaderInputs(sg):
        if mc.referenceQuery(_src.split('.')[0], isNodeReferenced=True):
            return True
    return False

def _shadingEngine_localGet(sg):
    """Existing local copy made by shadingEngine_localize (tagged cgmLocalizedFrom), or None."""
    for _sgLocal in mc.ls(type='shadingEngine') or []:
        if mc.referenceQuery(_sgLocal, isNodeReferenced=True):
            continue
        if not mc.attributeQuery(_str_localizedFromAttr, node=_sgLocal, exists=True):
            continue
        if mc.getAttr('{0}.{1}'.format(_sgLocal, _str_localizedFromAttr)) == sg:
            return _sgLocal
    return None

def shadingEngine_localize(sg):
    """
    Scene-local copy of a referenced shadingEngine: duplicates each upstream shader network
    (material, textures, place2d) and wires it into a new local SG. Reuses a copy already made for sg.
    Members are NOT moved here. Returns the local SG name.
    """
    _str_func = 'shadingEngine_localize'
    _sgLocal = _shadingEngine_localGet(sg)
    if _sgLocal:
        log.debug("|{0}| >> reuse: {1} -> {2}".format(_str_func, sg, _sgLocal))
        return _sgLocal

    _base = sg.split('|')[-1].split(':')[-1]
    _sgLocal = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name='{0}_local'.format(_base))
    mc.addAttr(_sgLocal, ln=_str_localizedFromAttr, dt='string')
    mc.setAttr('{0}.{1}'.format(_sgLocal, _str_localizedFromAttr), sg, type='string')

    d_dup = {}#src shader node -> duplicated node; one dup per network even if it feeds several slots
    for _attr, _src in _shadingEngine_shaderInputs(sg):
        _srcNode, _srcAttr = _src.split('.', 1)
        if _srcNode not in d_dup:
            _dup = mc.duplicate(_srcNode, upstreamNodes=True)[0]
            d_dup[_srcNode] = mc.rename(_dup, '{0}_local'.format(_srcNode.split(':')[-1]))
        mc.connectAttr('{0}.{1}'.format(d_dup[_srcNode], _srcAttr), '{0}.{1}'.format(_sgLocal, _attr), force=True)
    log.info("|{0}| >> {1} -> {2} | shaders: {3}".format(_str_func, sg, _sgLocal, list(d_dup.values())))
    return _sgLocal

def shadingEngines_localize(nodes = None):
    """
    For mesh/nurbs under nodes (transforms or shapes), move any assignment on a referenced shadingEngine
    (or one fed by a referenced material) to a scene-local duplicate network. Per-face assignments kept.

    :returns: {referencedSG: localSG}
    """
    _str_func = 'shadingEngines_localize'
    if not nodes:
        nodes = mc.ls(sl=1)
    nodes = VALID.listArg(nodes)

    l_shapes = []
    for _node in nodes:
        _node = _node.mNode if hasattr(_node, 'mNode') else _node
        _l = mc.ls(_node, long=True, type=['mesh', 'nurbsSurface']) or []
        _l += mc.listRelatives(_node, allDescendents=True, fullPath=True, type=['mesh', 'nurbsSurface']) or []
        for _shape in _l:
            if _shape not in l_shapes and not mc.getAttr('{0}.intermediateObject'.format(_shape)):
                l_shapes.append(_shape)

    d_map = {}
    for _shape in l_shapes:
        _trans = mc.listRelatives(_shape, parent=True, fullPath=True)[0]
        _l_mine = [_shape, _trans]
        for sg in list(set(mc.listConnections(_shape, type='shadingEngine', d=True, s=False) or [])):
            if sg not in d_map:
                if not _shadingEngine_isReferenced(sg):
                    continue
                d_map[sg] = shadingEngine_localize(sg)
            _l_members = []
            for _m in mc.sets(sg, q=True) or []:
                _l_obj = mc.ls(_m, objectsOnly=True, long=True) or []
                if _l_obj and _l_obj[0] in _l_mine:
                    _l_members.append(_m)
            if _l_members:
                mc.sets(_l_members, e=True, forceElement=d_map[sg])
                log.info("|{0}| >> {1} | {2} -> {3} | members: {4}".format(
                    _str_func, _trans.split('|')[-1], sg, d_map[sg], len(_l_members)))
    if not d_map:
        log.info("|{0}| >> no referenced shading on {1} shapes".format(_str_func, len(l_shapes)))
    return d_map

def shaderDat_get(nodes = []):
    if not nodes:
        nodes = mc.ls(sl=1)
        
    _res = {}
    mNodes = cgmMeta.asMeta(nodes)
    for mNode in mNodes:
        _node = mNode.mNode
        try:
            _d = {}
            
            for a in mNode.getAttrs():
                try:
                    
                    if ATTR.get_driver(_node,a):
                        continue
                    _d[a] = mNode.getMayaAttr(a)
                except Exception as err:
                    log.error("{0} | {1}".format(mNode,err))
            
            _res[mNode.mNode] = _d
            
        except Exception as err:
            log.error("{0} | {1}".format(mNode,err))
    pprint.pprint(_res)
    return _res

def shaderDat_set(dat = {},  key = None, nodes = []):
    _d = dat.get(key,False)
    if not _d:
        return False
    
    if not nodes:
        nodes = mc.ls(sl=1)
    _res = {}
    mNodes = cgmMeta.asMeta(nodes)
    
    for node in nodes:
        for a,v in list(_d.items()):
            if a  in ['color']:
                continue
            log.info(node)
            try:
                log.info('{0} --> {1}'.format(a,v))
                ATTR.set(node,a,v)
            except Exception as err:
                log.error("{0} | {1}".format(node,err))
            
            
