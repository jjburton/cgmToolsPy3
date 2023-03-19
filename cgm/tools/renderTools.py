import maya.cmds as mc
import maya.app.renderSetup.model.renderSetup as renderSetup
import cgm.images as cgmImages
import os.path
import cgm.lib.geometry as cgmGeometry
import cgm.core.lib.math_utils as math_utils
from cgm.core.lib import euclid as EUCLID
from cgm.core import cgm_Meta as cgmMeta
import json
from cgm.lib import files

width, height = (512,512)

def getImagesPath():
    # Get the current workspace path
    workspace_path = mc.workspace(q=True, rootDirectory=True)

    # Construct the path to the images folder
    images_path = os.path.join(workspace_path, "images")
    
    # Check if the images folder exists
    if not os.path.exists(images_path):
        # make a path in the current file directory
        images_path = os.path.join(os.path.dirname(mc.file(q=True, loc=True)), "images")
        if not os.path.exists(images_path):
            os.makedirs(images_path)
        print("Images folder path: ", images_path)
        return images_path
    else:
        print("Images folder path: ", images_path)
        return images_path

# Helper function for creating a shader
def makeShader(shaderType):
    """ Create a shader of the given type"""
    shaderName = mc.shadingNode(shaderType, asShader=True)
    sgName = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=(shaderName + "SG"))
    mc.connectAttr(shaderName + ".outColor", sgName + ".surfaceShader")
    return (shaderName, sgName)
	
# Helper function for assigning a material
def assignMaterial(shapeName, shadingGroupName):
    mc.sets(shapeName, forceElement=shadingGroupName)

def makeDepthShader():
    # Create nodes
    shader, sg = makeShader('surfaceShader')
    shader = mc.rename(shader, 'cgmDepthMaterial')
    ramp = mc.shadingNode('ramp', asTexture=True)
    mult_div = mc.shadingNode('multiplyDivide', asUtility=True)
    sampler_info = mc.shadingNode('samplerInfo', asUtility=True)
    negate_distance = mc.shadingNode('multiplyDivide', asUtility=True)
    clamp = mc.shadingNode('clamp', asUtility=True)

    # Create a distance attribute on the shader node
    mc.addAttr(shader, ln='distance', at='float', dv=100.0)
    
    # Connect distance attribute to multiply divide input 2X
    mc.connectAttr("%s.distance" % (shader), "%s.input2X" % mult_div)
    
    mc.connectAttr("%s.distance" % (shader), "%s.input1X" % negate_distance)
    mc.setAttr("%s.input2X" % negate_distance, -1.0)

    # connect negate to clamp min
    mc.connectAttr("%s.outputX" % negate_distance, "%s.minR" % clamp)
    mc.connectAttr("%s.outputX" % negate_distance, "%s.minG" % clamp)
    mc.connectAttr("%s.outputX" % negate_distance, "%s.minB" % clamp)

    # connect sampler info to clamp input
    mc.connectAttr("%s.pointCameraZ" % sampler_info, "%s.inputR" % clamp)

    # Set multiply divide node to divide mode
    mc.setAttr("%s.operation" % mult_div, 2)
    
    # Connect sampler info point Camera X to multiply divide input 1X
    mc.connectAttr("%s.outputR" % clamp, "%s.input1X" % mult_div)
    
    # Connect multiply divide outputX to ramp u and v coords
    mc.connectAttr("%s.outputX" % mult_div, "%s.uCoord" % ramp)
    mc.connectAttr("%s.outputX" % mult_div, "%s.vCoord" % ramp)
    
    # Connect ramp out color to surface shader out color
    mc.connectAttr("%s.outColor" % ramp, "%s.outColor" % shader)

    return shader, sg

def makeProjectionShader(cameraShape, makeLayeredTexture=False):
    # Create a surface shader
    shader, sg = makeShader('surfaceShader')
    shader = mc.rename(shader, 'cgmProjectionMaterial')
    
    # create a layered texture node
    layeredTexture = None

    # create a projection node
    projection = mc.shadingNode('projection', asTexture=True)

    # create a file node
    fileNode = mc.shadingNode('file', asTexture=True)

    # create a place2dTexture node
    place2d = mc.shadingNode('place2dTexture', asUtility=True)

    mc.setAttr("%s.defaultColor" % fileNode, 0.0, 0.0, 0.0, type='double3')

    # connect the place2d node to the file node
    mc.connectAttr('%s.coverage' % place2d, '%s.coverage' % fileNode)
    mc.connectAttr('%s.translateFrame' % place2d, '%s.translateFrame' % fileNode)
    mc.connectAttr('%s.rotateFrame' % place2d, '%s.rotateFrame' % fileNode)
    mc.connectAttr('%s.mirrorU' % place2d, '%s.mirrorU' % fileNode)
    mc.connectAttr('%s.mirrorV' % place2d, '%s.mirrorV' % fileNode)
    mc.connectAttr('%s.stagger' % place2d, '%s.stagger' % fileNode)
    mc.connectAttr('%s.wrapU' % place2d, '%s.wrapU' % fileNode)
    mc.connectAttr('%s.wrapV' % place2d, '%s.wrapV' % fileNode)
    mc.connectAttr('%s.repeatUV' % place2d, '%s.repeatUV' % fileNode)
    mc.connectAttr('%s.offset' % place2d, '%s.offset' % fileNode)
    mc.connectAttr('%s.rotateUV' % place2d, '%s.rotateUV' % fileNode)
    mc.connectAttr('%s.noiseUV' % place2d, '%s.noiseUV' % fileNode)
    mc.connectAttr('%s.vertexUvOne' % place2d, '%s.vertexUvOne' % fileNode)
    mc.connectAttr('%s.vertexUvTwo' % place2d, '%s.vertexUvTwo' % fileNode)
    mc.connectAttr('%s.vertexUvThree' % place2d, '%s.vertexUvThree' % fileNode)
    mc.connectAttr('%s.vertexCameraOne' % place2d, '%s.vertexCameraOne' % fileNode)
    mc.connectAttr('%s.outUV' % place2d, '%s.uv' % fileNode)
    mc.connectAttr('%s.outUvFilterSize' % place2d, '%s.uvFilterSize' % fileNode)

    # set wrapping to off
    mc.setAttr('%s.wrapU' % place2d, 0)
    mc.setAttr('%s.wrapV' % place2d, 0)

    # connect the file node to the projection node
    mc.connectAttr('%s.outColor' % fileNode, '%s.image' % projection)

    if makeLayeredTexture:
        layeredTexture = mc.shadingNode('layeredTexture', asTexture=True)
        # connect the projection node to the layered texture node
        mc.connectAttr('%s.outColor' % projection, '%s.inputs[0].color' % layeredTexture)
        # connect the layered texture node to the surface shader
        mc.connectAttr('%s.outColorR' % layeredTexture, '%s.outColorR' % shader)
        mc.connectAttr('%s.outColorG' % layeredTexture, '%s.outColorG' % shader)
        mc.connectAttr('%s.outColorB' % layeredTexture, '%s.outColorB' % shader)
    else:
        mc.connectAttr('%s.outColorR' % projection, '%s.outColorR' % shader)
        mc.connectAttr('%s.outColorG' % projection, '%s.outColorG' % shader)
        mc.connectAttr('%s.outColorB' % projection, '%s.outColorB' % shader)

    # set the projection node to perspective
    mc.setAttr('%s.projType' % projection, 8) 

    # connect the camera
    mc.connectAttr('%s.worldMatrix[0]' % cameraShape, '%s.linkedCamera' % projection)

    # set the file node to the grid texture
    mc.setAttr('%s.fileTextureName' % fileNode, os.path.join(cgmImages.__path__[0], "grid.png"), type='string')

    return shader, sg

def makeAlphaProjectionShader(cameraShape):
    shader, sg = makeProjectionShader(cameraShape, True)

    shader = mc.rename(shader, 'cgmAlphaProjectionMaterial')
    layeredTexture = mc.listConnections('%s.outColorR' % shader, type='layeredTexture')[0]
    projection = mc.listConnections('%s.inputs[0].color' % layeredTexture, type='projection')[0]
    fileNode = mc.listConnections('%s.image' % projection, type='file')[0]

    #create a ramp node
    ramp = mc.shadingNode('ramp', asTexture=True)

    # create a samplerInfo node
    sampler_info = mc.shadingNode('samplerInfo', asUtility=True)

    mc.setAttr('%s.fileTextureName' % fileNode, os.path.join(cgmImages.__path__[0], "white.png"), type='string')

    # set the ramp node to linear
    mc.setAttr('%s.interpolation' % ramp, 1)

    # set the ramp node to 2 positions
    mc.setAttr('%s.colorEntryList[0].position' % ramp, 0)
    mc.setAttr('%s.colorEntryList[1].position' % ramp, 1)

    # set the ramp node to 2 colors
    mc.setAttr('%s.colorEntryList[0].color' % ramp, 0, 0, 0, type='double3')
    mc.setAttr('%s.colorEntryList[1].color' % ramp, 1, 1, 1, type='double3')

    # connect the sampler info facing ratio to the u and v coords on the ramp node
    mc.connectAttr('%s.facingRatio' % sampler_info, '%s.uCoord' % ramp)
    mc.connectAttr('%s.facingRatio' % sampler_info, '%s.vCoord' % ramp)

    # connect the ramp node alpha to the layered texture node alpha
    mc.connectAttr('%s.outAlpha' % ramp, '%s.inputs[0].alpha' % layeredTexture)

    return shader, sg

def makeAlphaMatteShader():
    shader = mc.shadingNode('lambert', asShader=True)
    sg = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name='%sSG' % shader)

    mc.connectAttr('%s.outColor' % shader, '%s.surfaceShader' % sg)

    shader = mc.rename(shader, 'cgmAlphaMatteMaterial')

    return shader, sg

# Create a camera that projects a texture onto the selected object
def makeProjectionCamera():
    camera, shape = mc.camera(name="cgmProjectionCamera")

    mc.setAttr('%s.renderable'%(shape), 1)
    # set film aspect ratio to 1
    mc.setAttr('%s.horizontalFilmAperture'%(shape), 1)
    mc.setAttr('%s.verticalFilmAperture'%(shape), 1)

    # set the lens squeeze ratio to 1
    mc.setAttr('%s.lensSqueezeRatio'%(shape), 1)

    mc.setAttr('%s.filmFit'%(shape), 2)

    mc.setAttr('%s.mask'%(shape), False)

    mShape = cgmMeta.asMeta(shape)
    mShape.doStore('cgmCamera','projection')

    return (camera, shape)

def bakeProjection(material, meshObj, resolution=(2048, 2048)):
    convertedFile = mc.convertSolidTx("%s.outColor" % material, meshObj, antiAlias=1, bm=1, fts=1, sp=0, sh=0, alpha=False, doubleSided=0, componentRange=0, resolutionX=resolution[0], resolutionY=resolution[1], fileFormat="png")

    if(convertedFile):
        convertedFile = convertedFile[0]
    else:
        return None
    
    return convertedFile

# def addImageToCompositeShader(shader, color, alpha):
#     layeredTexture = mc.listConnections('%s.outColor' % shader, type="layeredTexture")[0]
#     connections = mc.listConnections(layeredTexture, p=True, s=True, d=False)
#     # get connections to "outColor"
#     #outColorConnections = [c for c in connections if c.endswith(".outColor")]
#     # get the index of the last connection
#     index = 0
#     if(connections):
#         outColorConnections = [c for c in connections if c.endswith(".outColor")]
#         # get the index of the last connection
#         inputs = mc.listConnections(outColorConnections, p=True, d=True, s=False)
#         index = int(inputs[-1].split("inputs[")[1].split("]")[0]) + 1

#     remapColor = mc.shadingNode('remapColor', asUtility=True )

#     mc.setAttr( "%s.red[0].red_Position" % remapColor, 0)
#     mc.setAttr("%s.red[1].red_Position" % remapColor, 0.1)

#     mc.connectAttr('%s.outColor' % color, '%s.inputs[%d].color' % (layeredTexture, index), f=True)
#     mc.connectAttr('%s.outColor' % alpha, '%s.color' % remapColor, f=True)
#     mc.connectAttr('%s.outColorR' % remapColor, '%s.inputs[%d].alpha' % (layeredTexture, index), f=True)

#     return index, remapColor

def addImageToCompositeShader(shader, color, alpha):
    layeredTexture = mc.listConnections('%s.outColor' % shader, type="layeredTexture")[0]
    connections = mc.listConnections(layeredTexture, p=True, s=True, d=False) or []

    if connections:
        outColorConnections = [c for c in connections if '.outColor' in c]
        inputs = mc.listConnections(outColorConnections, p=True, d=True, s=False) or []
        #input_connection = inputs[0]
        for input_connection in reversed(inputs):
            current_index = int(input_connection.split("inputs[")[1].split("]")[0])
            next_index = current_index + 1
            
            connectionPlug = input_connection.split('.')[-1]
            # Disconnect empty connections
            connected_attr = '%s.inputs[%d].%s' % (layeredTexture, current_index, connectionPlug)
            src_attr = mc.listConnections(connected_attr, p=True, s=True, d=False)

            if src_attr:
                mc.disconnectAttr(src_attr[0], connected_attr)

            # Shift the connections down the line
            mc.connectAttr(src_attr[0], input_connection.replace(f'[{current_index}]', f'[{next_index}]'), f=True)

    remapColor = mc.shadingNode('remapColor', asUtility=True)
    mult = mc.shadingNode('multiplyDivide', asUtility=True)
    mult2 = mc.shadingNode('multiplyDivide', asUtility=True)

    mc.setAttr("%s.red[0].red_Position" % remapColor, 0)
    mc.setAttr("%s.red[1].red_Position" % remapColor, 0.1)

    # set green position to 1
    mc.setAttr("%s.green[0].green_Position" % remapColor, 0)
    mc.setAttr("%s.green[1].green_Position" % remapColor, 1)
    mc.setAttr("%s.green[0].green_FloatValue" % remapColor, 1)
    mc.setAttr("%s.green[1].green_FloatValue" % remapColor, 1)

    # set blue position to 1
    mc.setAttr("%s.blue[0].blue_Position" % remapColor, 0)
    mc.setAttr("%s.blue[1].blue_Position" % remapColor, 1)
    mc.setAttr("%s.blue[0].blue_FloatValue" % remapColor, 1)
    mc.setAttr("%s.blue[1].blue_FloatValue" % remapColor, 1)

    # connect remap color r and g to multiply
    mc.connectAttr('%s.outColorR' % remapColor, '%s.input1X' % mult, f=True)
    mc.connectAttr('%s.outColorG' % remapColor, '%s.input2X' % mult, f=True)

    # multiply remap color b with multiply out X
    mc.connectAttr('%s.outColorB' % remapColor, '%s.input1X' % mult2, f=True)
    mc.connectAttr('%s.outputX' % mult, '%s.input2X' % mult2, f=True)

    # connect multiply out X to layered texture alpha
    mc.connectAttr('%s.outColor' % color, '%s.inputs[0].color' % layeredTexture, f=True)
    mc.connectAttr('%s.outColor' % alpha, '%s.color' % remapColor, f=True)
    mc.connectAttr('%s.outputX' % mult2, '%s.inputs[0].alpha' % layeredTexture, f=True)

    return 0, remapColor





# def updateAlphaMatteShader(alphaShader, compositeShader):
#     layeredTexture = mc.listConnections('%s.outColor' % alphaShader, type="layeredTexture")[0]
#     compositelayeredTexture = mc.listConnections('%s.outColor' % compositeShader, type="layeredTexture")[0]

#     connections = mc.listConnections(layeredTexture, p=True, s=True, d=False)
#     if(connections):
#         for connection in connections:
#             outConnections = mc.listConnections(connection, p=True, s=False, d=True)
#             for out in outConnections:
#                 if(layeredTexture in out):
#                     mc.disconnectAttr(connection, out)

#     connections = mc.listConnections(compositelayeredTexture, p=True, s=True, d=False)
#     for connection in connections:
#         outConnections = mc.listConnections(connection, p=True, s=False, d=True)
#         for out in outConnections:
#             if 'alpha' in out:
#                 index = int(out.split('inputs[')[-1].split(']')[0])
#                 connectionNode, connectionNodeType = mc.ls(connection.split('.')[0], st=True)

#                 if(connectionNodeType == 'remapColor'):
#                     connectionDupe = mc.duplicate(connectionNode, n='%s_alphaRemap' % connectionNode, ic=True)
#                     connection = '%s.%s' % (connectionDupe[0], '.'.join(connection.split('.')[1:]))
                
#                 mc.connectAttr(connection, '%s.inputs[%d].colorR' % (layeredTexture, index))
#                 mc.connectAttr(connection, '%s.inputs[%d].colorG' % (layeredTexture, index))
#                 mc.connectAttr(connection, '%s.inputs[%d].colorB' % (layeredTexture, index))

def updateAlphaMatteShader(alphaShader, compositeShader):
    layeredTexture = mc.listConnections('%s.outColor' % alphaShader, type="layeredTexture")[0]
    compositelayeredTexture = mc.listConnections('%s.outColor' % compositeShader, type="layeredTexture")[0]

    connections = mc.listConnections(layeredTexture, p=True, s=True, d=False) or []
    if connections:
        for connection in connections:
            outConnections = mc.listConnections(connection, p=True, s=False, d=True) or []
            for out in outConnections:
                if layeredTexture in out:
                    mc.disconnectAttr(connection, out)

    connections = mc.listConnections(compositelayeredTexture, p=True, s=True, d=False) or []
    for connection in connections:
        outConnections = mc.listConnections(connection, p=True, s=False, d=True) or []
        for out in outConnections:
            if 'alpha' in out:
                index = int(out.split('inputs[')[-1].split(']')[0])
                connectionNode, connectionNodeType = mc.ls(connection.split('.')[0], st=True)

                if connectionNodeType == 'multiplyDivide':
                    connectionDupe = mc.duplicate(connectionNode, upstreamNodes=True)
                    for i,n in enumerate(connectionDupe):
                        connectionDupe[i] = mc.rename(n, '%s_alpha' % n)
                    connection = '%s.%s' % (connectionDupe[0], '.'.join(connection.split('.')[1:]))
                
                # Check if input entry is empty before connecting
                input_color_attrs = [
                    '%s.inputs[%d].colorR' % (layeredTexture, index),
                    '%s.inputs[%d].colorG' % (layeredTexture, index),
                    '%s.inputs[%d].colorB' % (layeredTexture, index)
                ]
                if not any(mc.listConnections(attr, p=True, s=True, d=False) for attr in input_color_attrs):
                    mc.connectAttr(connection, input_color_attrs[0])
                    mc.connectAttr(connection, input_color_attrs[1])
                    mc.connectAttr(connection, input_color_attrs[2])

def assignImageToProjectionShader(shader, image_path, data):
    projection = mc.listConnections('%s.outColorR' % shader, type='projection')[0]
    fileNode = mc.shadingNode('file', asTexture=True, isColorManaged=True)
    mc.setAttr(fileNode + '.fileTextureName', image_path, type='string')
    mc.connectAttr(fileNode + '.outColor', projection + '.image', force=True)

    mc.setAttr('%s.wrapU' % fileNode, False)
    mc.setAttr('%s.wrapV' % fileNode, False)

    mFile = cgmMeta.asMeta(fileNode)
    mFile.doStore('cgmImageProjectionData',json.dumps(data))

def renderMaterialPass(material, meshObj, fileName = None, asJpg=False, camera = None):
    #print("renderMaterialPass(%s, %s, %s, %s, %s)" % (material, meshObj, fileName, asJpg, camera))

    wantedName = ""
    if(material):
        # assign depth shader
        sg = mc.listConnections(material, type='shadingEngine')
        if sg:
            sg = sg[0]

        assignMaterial(meshObj, sg)

        wantedName = material

    if fileName:
        wantedName = fileName

    # setAttr "defaultRenderGlobals.imageFormat" 8;
    currentImageFormat = mc.getAttr("defaultRenderGlobals.imageFormat")

    if asJpg:
        mc.setAttr("defaultRenderGlobals.imageFormat", 8)
    else:
        mc.setAttr("defaultRenderGlobals.imageFormat", 32)

    mc.setAttr("defaultRenderGlobals.imageFilePrefix", wantedName, type="string")

    outputFileName = mc.renderSettings(fullPathTemp=True, firstImageName=True)

    uniqueFileName = files.create_unique_filename(outputFileName[0])
    newName = os.path.splitext(os.path.split(uniqueFileName)[-1])[0]

    mc.setAttr("defaultRenderGlobals.imageFilePrefix", newName, type="string")

    if camera:
        cameras = mc.ls(type='camera')

        # iterate through the cameras and set them to not be renderable
        for renderCam in cameras:
            if renderCam == camera:
                mc.setAttr(renderCam + '.renderable', 1)
            else:
                mc.setAttr(renderCam + '.renderable', 0)

    imagePath = mc.render(batch=True, rep=True)

    mc.setAttr("defaultRenderGlobals.imageFormat", currentImageFormat)

    print("Rendered material pass, %s, %s" % (material, imagePath))
    return imagePath


"""
getAllConnectedNodesOfType - Returns a list of all connected nodes of a specified type to a given source shading node.

@param sourceShadingNode: The name of the source shading node.
@type sourceShadingNode: str

@param nodeType: The type of node to search for.
@type nodeType: str

@return: A list of unique connections between the source shading node and nodes of the specified type. Each connection is represented as a list containing the name of the connected node and the name of the destination attribute.
@rtype: list[list[str]]
"""
def getAllConnectedNodesOfType(sourceShadingNode, nodeType):
    result = []

    def walkConnections(node, nodeType, visited=None):
        if visited is None:
            visited = set()
        connectedNodes = []
        connections = mc.listConnections(node, source=True, destination=False, plugs=True)

        if connections:
            for connection in connections:
                connectedNode = connection.split('.')[0]
                connectedNodeType = mc.nodeType(connectedNode)

                if connectedNodeType == nodeType:
                    # Modify the returned list to include the destination attribute instead of the source attribute
                    connectedNodes.append([connectedNode, mc.listConnections(connection, source=False, destination=True, plugs=True)[0]])

                if connectedNode not in visited:
                    visited.add(connectedNode)
                    connectedNodes.extend(walkConnections(connectedNode, nodeType, visited))

        return connectedNodes

    result = walkConnections(sourceShadingNode, nodeType)
    # Remove any duplicates from the returned list
    result = list(set(map(tuple, result)))
    result = [list(t) for t in result]
    return result

