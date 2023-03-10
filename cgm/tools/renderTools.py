import maya.cmds as mc
import maya.app.renderSetup.model.renderSetup as renderSetup
import cgm.images as cgmImages
import os.path
import cgm.lib.geometry as cgmGeometry
import cgm.core.lib.math_utils as math_utils
from cgm.core.lib import euclid as EUCLID

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
def createShader(shaderType):
    """ Create a shader of the given type"""
    shaderName = mc.shadingNode(shaderType, asShader=True)
    sgName = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=(shaderName + "SG"))
    mc.connectAttr(shaderName + ".outColor", sgName + ".surfaceShader")
    return (shaderName, sgName)
	
# Helper function for assigning a material
def assignMaterial(shapeName, shadingGroupName):
    mc.sets(shapeName, forceElement=shadingGroupName)

def createDepthShader():
    # Create nodes
    shader, sg = createShader('surfaceShader')
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

def createProjectionShader(cameraShape):
    # Create a surface shader
    shader, sg = createShader('surfaceShader')
    shader = mc.rename(shader, 'cgmProjectionMaterial')
    # create a layered texture node
    layered_texture = mc.shadingNode('layeredTexture', asTexture=True)

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

    # connect the projection node to the layered texture node
    mc.connectAttr('%s.outColor' % projection, '%s.inputs[0].color' % layered_texture)

    # connect the layered texture node to the surface shader
    mc.connectAttr('%s.outColor' % layered_texture, '%s.outColor' % shader)

    # set the projection node to perspective
    mc.setAttr('%s.projType' % projection, 8) 

    # connect the camera
    mc.connectAttr('%s.worldMatrix[0]' % cameraShape, '%s.linkedCamera' % projection)

    # set the file node to the grid texture
    mc.setAttr('%s.fileTextureName' % fileNode, os.path.join(cgmImages.__path__[0], "grid.png"), type='string')

    return shader, sg

def createAlphaProjectionShader(cameraShape):
    shader, sg = createProjectionShader(cameraShape)

    shader = mc.rename(shader, 'cgmAlphaProjectionMaterial')
    layered_texture = mc.listConnections('%s.outColor' % shader, type='layeredTexture')[0]
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
    mc.connectAttr('%s.outAlpha' % ramp, '%s.inputs[0].alpha' % layered_texture)

    return shader, sg

# Create a camera that projects a texture onto the selected object
def createProjectionCamera():
    camera, shape = mc.camera(name="cgmProjectionCamera")

    mc.setAttr('%s.renderable'%(shape), 1)
    # set film aspect ratio to 1
    mc.setAttr('%s.horizontalFilmAperture'%(shape), 1)
    mc.setAttr('%s.verticalFilmAperture'%(shape), 1)

    # set the lens squeeze ratio to 1
    mc.setAttr('%s.lensSqueezeRatio'%(shape), 1)

    mc.setAttr('%s.filmFit'%(shape), 2)

    return (camera, shape)

def getDepthDistanceFromCamera(camera, object):
    # Get the camera position
    cameraPos = mc.xform(camera, q=True, ws=True, t=True)
    fwd = math_utils.transform_direction("cgmProjectionCamera1", EUCLID.Vector3(0,0,-1))
    
    # Get the bounding box of the object
    objectBB = mc.exactWorldBoundingBox(object)

    # get the plane position and normals for the 6 sides of the bounding box
    planes, normals, points = cgmGeometry.getPlanes(objectBB)

    intersectPos = cgmGeometry.ray_box_intersection(cameraPos, [fwd.x, fwd.y, fwd.z], points, 100)

    # Calculate the distance between the camera and the object
    distance = math.sqrt((cameraPos[0] - intersectPos[0])**2 + (cameraPos[1] - intersectPos[1])**2 + (cameraPos[2] - intersectPos[2])**2)

    #create locator at intersection
    mc.spaceLocator(n="cgmDepthLocator")
    mc.xform(ws=True, t=intersectPos)

    return distance

def bakeProjection(material, meshObj, resolution=(2048, 2048)):
    convertedFile = mc.convertSolidTx("%s.outColor" % material, meshObj, antiAlias=1, bm=1, fts=1, sp=0, sh=0, alpha=False, doubleSided=0, componentRange=0, resolutionX=resolution[0], resolutionY=resolution[1], fileFormat="png")

    if(convertedFile):
        convertedFile = convertedFile[0]
    else:
        return None
    
    return convertedFile

def createRenderLayer(width, height, camera):
    # Check if anything is selected
    if not mc.ls(selection=True):
        raise ValueError("Nothing is selected.")

    sel = mc.ls(sl=True)

    # Create a new render setup
    rs = renderSetup.instance()

    # Create a new layer and add it to the render setup
    layer = rs.createRenderLayer('SDDepthPass')
    rs.switchToLayer(layer)

    # Add the object to the layer and enable rendering for it
    c1 = layer.createCollection('FogElements')
    for obj in mc.ls(sel,l=True):
        c1.getSelector().setPattern(obj)

    # Set the render settings for the layer
    mc.setAttr('defaultResolution.width', width)
    mc.setAttr('defaultResolution.height', height)
    mc.setAttr('defaultRenderQuality.edgeAntiAliasing', 0)

    # Create an environment fog and connect it to the defaultRenderGlobals
    depth_shader, shader_sg = create_depth_shader()

    outColorShaderOvr = c1.createAbsoluteOverride(depth_shader, 'outColor')

    # Get the selected object's furthest position in front of the camera
    bb = mc.exactWorldBoundingBox(sel[0])
    cam_pos = mc.xform(camera, query=True, worldSpace=True, translation=True)
    distances = []
    points = []

    if distances:
        distance = max(distances)
    else:
        distance = 0.0
    
    # Set the depth distance to the furthest position of the selected object
    depth_shader = mc.ls(type='depthShader')[0]
    mc.setAttr('%s.distance' % depth_shader, distance)

    return

    # Render the layer
    mc.render()

    # Remove the layer and any additional nodes created
    rs.deleteLayer(layer)
    mc.delete(shader)