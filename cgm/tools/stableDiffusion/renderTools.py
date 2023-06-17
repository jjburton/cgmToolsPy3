import maya.cmds as mc
import maya.mel as mel
import cgm.images as cgmImages
import os.path
from cgm.core import cgm_Meta as cgmMeta
import json
from cgm.lib import files
import tempfile
import time
import numpy as np
import os
from PIL import Image, ImageChops, ImageMath
import copy

import logging

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

width, height = (512, 512)


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
    """Create a shader of the given type"""
    shaderName = mc.shadingNode(shaderType, asShader=True)
    sgName = mc.sets(
        renderable=True, noSurfaceShader=True, empty=True, name=(shaderName + "SG")
    )
    mc.connectAttr(shaderName + ".outColor", sgName + ".surfaceShader")
    return (shaderName, sgName)


# Helper function for assigning a material
def assignMaterial(shapeName, shadingGroupName):
    mc.sets(shapeName, forceElement=shadingGroupName)


def makeDepthShader():
    baseName = "cgmDepthRamp"

    # Create nodes
    shader, sg = makeShader("surfaceShader")
    shader = mc.rename(shader, "cgmDepthMaterial")
    ramp = mc.shadingNode("ramp", asTexture=True, name=baseName + "_ramp")
    mult_div = mc.shadingNode(
        "multiplyDivide", asUtility=True, name=baseName + "_multiplyDivide"
    )
    sampler_info = mc.shadingNode(
        "samplerInfo", asUtility=True, name=baseName + "_samplerInfo"
    )
    negate_distance = mc.shadingNode(
        "multiplyDivide", asUtility=True, name=baseName + "_negateDistance"
    )
    clamp = mc.shadingNode("clamp", asUtility=True, name=baseName + "_clamp")
    minDistanceClamp = mc.shadingNode(
        "clamp", asUtility=True, name=baseName + "_minDistanceClamp"
    )
    positionAdd = mc.shadingNode(
        "plusMinusAverage", asUtility=True, name=baseName + "_positionAdd"
    )
    distanceDiff = mc.shadingNode(
        "plusMinusAverage", asUtility=True, name=baseName + "_distanceDiff"
    )

    # Create a distance attribute on the shader node
    mc.addAttr(shader, ln="maxDistance", at="float", dv=100.0)
    mc.addAttr(shader, ln="minDistance", at="float", dv=0)

    # clamp min distance to max distance
    mc.connectAttr("%s.minDistance" % shader, "%s.inputR" % minDistanceClamp)
    mc.connectAttr("%s.minDistance" % shader, "%s.minR" % minDistanceClamp)
    mc.connectAttr("%s.maxDistance" % shader, "%s.maxR" % minDistanceClamp)

    # connect min distance clamp to distance diff
    mc.connectAttr("%s.maxDistance" % shader, "%s.input1D[0]" % distanceDiff)
    mc.connectAttr("%s.outputR" % minDistanceClamp, "%s.input1D[1]" % distanceDiff)
    mc.setAttr("%s.operation" % distanceDiff, 2)

    # Connect distance attribute to multiply divide input 2X
    mc.connectAttr("%s.output1D" % distanceDiff, "%s.input2X" % mult_div)

    mc.connectAttr("%s.output1D" % distanceDiff, "%s.input1X" % negate_distance)
    mc.setAttr("%s.input2X" % negate_distance, -1.0)

    # connect negate to clamp min
    mc.connectAttr("%s.outputX" % negate_distance, "%s.minR" % clamp)

    mc.setAttr("%s.maxR" % clamp, -0.001)

    # connect sampler info to clamp input
    mc.connectAttr("%s.pointCameraZ" % sampler_info, "%s.input1D[0]" % positionAdd)
    mc.connectAttr("%s.outputR" % minDistanceClamp, "%s.input1D[1]" % positionAdd)
    mc.connectAttr("%s.output1D" % positionAdd, "%s.inputR" % clamp)

    # Set multiply divide node to divide mode
    mc.setAttr("%s.operation" % mult_div, 2)

    # Connect sampler info point Camera X to multiply divide input 1X
    mc.connectAttr("%s.outputR" % clamp, "%s.input1X" % mult_div)

    # Connect multiply divide outputX to ramp u and v coords
    mc.connectAttr("%s.outputX" % mult_div, "%s.uCoord" % ramp)
    mc.connectAttr("%s.outputX" % mult_div, "%s.vCoord" % ramp)

    # Connect ramp out color to surface shader out color
    mc.connectAttr("%s.outColor" % ramp, "%s.outColor" % shader)

    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_depth")

    shader = mc.rename(shader, "cgmDepthShader")

    return shader, sg

def makeNormalShader():
    baseName = "cgmNormalRamp"

    # Create nodes
    shader, sg = makeShader("surfaceShader")
    shader = mc.rename(shader, "cgmNormalMaterial")
    sampler_info = mc.shadingNode(
        "samplerInfo", asUtility=True, name=baseName + "_samplerInfo"
    )

    # connect sampler info Normal Camera to shader out color
    mc.connectAttr("%s.normalCamera" % sampler_info, "%s.outColor" % shader)

    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_normal")

    shader = mc.rename(shader, "cgmNormalShader")

    return shader, sg

def makeXYZShader():
    # Create a surface shader
    shader, sg = makeShader("surfaceShader")
    shader = mc.rename(shader, "cgmXYZMaterial")

    # make a samplerInfo node
    samplerInfo = mc.shadingNode("samplerInfo", asUtility=True)

    mc.addAttr(shader, ln="bboxMax", at="double3")
    mc.addAttr(shader, ln="bboxMaxX", at="double", p="bboxMax")
    mc.addAttr(shader, ln="bboxMaxY", at="double", p="bboxMax")
    mc.addAttr(shader, ln="bboxMaxZ", at="double", p="bboxMax")

    mc.addAttr(shader, ln="bboxMin", at="double3")
    mc.addAttr(shader, ln="bboxMinX", at="double", p="bboxMin")
    mc.addAttr(shader, ln="bboxMinY", at="double", p="bboxMin")
    mc.addAttr(shader, ln="bboxMinZ", at="double", p="bboxMin")

    # make a plusMinusAverage node
    plusMinusAverage = mc.shadingNode("plusMinusAverage", asUtility=True)
    mc.setAttr(f"{plusMinusAverage}.operation", 2)

    # subtract the min from the pointWorld of the sampler
    mc.connectAttr("%s.pointWorld" % samplerInfo, "%s.input3D[0]" % plusMinusAverage)
    mc.connectAttr("%s.bboxMin" % shader, "%s.input3D[1]" % plusMinusAverage)

    # make a multiplyDivide node
    multiplyDivide = mc.shadingNode("multiplyDivide", asUtility=True)

    # set to divide
    mc.setAttr("%s.operation" % multiplyDivide, 2)

    # subtract the min from the max
    plusMinus2 = mc.shadingNode("plusMinusAverage", asUtility=True)
    mc.setAttr("%s.operation" % plusMinus2, 2)
    mc.connectAttr("%s.bboxMax" % shader, "%s.input3D[0]" % plusMinus2)
    mc.connectAttr("%s.bboxMin" % shader, "%s.input3D[1]" % plusMinus2)

    mc.connectAttr("%s.output3D" % plusMinus2, "%s.input2" % multiplyDivide)

    # make a clamp node
    clamp = mc.shadingNode("clamp", asUtility=True)

    # connect the multiplyDivide to the clamp
    mc.connectAttr("%s.output3D" % plusMinusAverage, "%s.input1" % multiplyDivide)
    mc.connectAttr("%s.output" % multiplyDivide, "%s.input" % clamp)

    # set the clamp min and max
    mc.setAttr("%s.min" % clamp, 0.0, 0.0, 0.0, type="double3")
    mc.setAttr("%s.max" % clamp, 1.0, 1.0, 1.0, type="double3")

    # connect the clamp to the shader
    mc.connectAttr("%s.output" % clamp, "%s.outColor" % shader)

    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_xyz")

    shader = mc.rename(shader, "cgmXYZShader")

    return shader, sg


def makeProjectionShader(cameraShape, makeLayeredTexture=False):
    # Create a surface shader
    shader, sg = makeShader("surfaceShader")
    shader = mc.rename(shader, "cgmProjectionMaterial")

    # create a layered texture node
    layeredTexture = None

    # create a projection node
    projection = mc.shadingNode("projection", asTexture=True)

    # create a file node
    fileNode = mc.shadingNode("file", asTexture=True)

    # create a place2dTexture node
    place2d = mc.shadingNode("place2dTexture", asUtility=True)

    mc.setAttr("%s.defaultColor" % fileNode, 0.0, 0.0, 0.0, type="double3")

    # connect the place2d node to the file node
    mc.connectAttr("%s.coverage" % place2d, "%s.coverage" % fileNode)
    mc.connectAttr("%s.translateFrame" % place2d, "%s.translateFrame" % fileNode)
    mc.connectAttr("%s.rotateFrame" % place2d, "%s.rotateFrame" % fileNode)
    mc.connectAttr("%s.mirrorU" % place2d, "%s.mirrorU" % fileNode)
    mc.connectAttr("%s.mirrorV" % place2d, "%s.mirrorV" % fileNode)
    mc.connectAttr("%s.stagger" % place2d, "%s.stagger" % fileNode)
    mc.connectAttr("%s.wrapU" % place2d, "%s.wrapU" % fileNode)
    mc.connectAttr("%s.wrapV" % place2d, "%s.wrapV" % fileNode)
    mc.connectAttr("%s.repeatUV" % place2d, "%s.repeatUV" % fileNode)
    mc.connectAttr("%s.offset" % place2d, "%s.offset" % fileNode)
    mc.connectAttr("%s.rotateUV" % place2d, "%s.rotateUV" % fileNode)
    mc.connectAttr("%s.noiseUV" % place2d, "%s.noiseUV" % fileNode)
    mc.connectAttr("%s.vertexUvOne" % place2d, "%s.vertexUvOne" % fileNode)
    mc.connectAttr("%s.vertexUvTwo" % place2d, "%s.vertexUvTwo" % fileNode)
    mc.connectAttr("%s.vertexUvThree" % place2d, "%s.vertexUvThree" % fileNode)
    mc.connectAttr("%s.vertexCameraOne" % place2d, "%s.vertexCameraOne" % fileNode)
    mc.connectAttr("%s.outUV" % place2d, "%s.uv" % fileNode)
    mc.connectAttr("%s.outUvFilterSize" % place2d, "%s.uvFilterSize" % fileNode)

    # set wrapping to off
    mc.setAttr("%s.wrapU" % place2d, 0)
    mc.setAttr("%s.wrapV" % place2d, 0)

    # connect the file node to the projection node
    mc.connectAttr("%s.outColor" % fileNode, "%s.image" % projection)

    if makeLayeredTexture:
        layeredTexture = mc.shadingNode("layeredTexture", asTexture=True)
        # connect the projection node to the layered texture node
        mc.connectAttr(
            "%s.outColor" % projection, "%s.inputs[0].color" % layeredTexture
        )
        # connect the layered texture node to the surface shader
        mc.connectAttr("%s.outColorR" % layeredTexture, "%s.outColorR" % shader)
        mc.connectAttr("%s.outColorG" % layeredTexture, "%s.outColorG" % shader)
        mc.connectAttr("%s.outColorB" % layeredTexture, "%s.outColorB" % shader)
    else:
        mc.connectAttr("%s.outColorR" % projection, "%s.outColorR" % shader)
        mc.connectAttr("%s.outColorG" % projection, "%s.outColorG" % shader)
        mc.connectAttr("%s.outColorB" % projection, "%s.outColorB" % shader)

    # set the projection node to perspective
    mc.setAttr("%s.projType" % projection, 8)

    # connect the camera
    mc.connectAttr("%s.worldMatrix[0]" % cameraShape, "%s.linkedCamera" % projection)

    # set the file node to the grid texture
    mc.setAttr(
        "%s.fileTextureName" % fileNode,
        os.path.join(cgmImages.__path__[0], "grid.png"),
        type="string",
    )

    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_projection")

    shader = mc.rename(shader, "cgmProjectionShader")

    return shader, sg


def makeAlphaProjectionShader(cameraShape):
    shader, sg = makeProjectionShader(cameraShape, False)

    shader = mc.rename(shader, "cgmAlphaProjectionMaterial")
    # layeredTexture = mc.listConnections('%s.outColorR' % shader, type='layeredTexture')[0]
    projection = mc.listConnections("%s.outColorR" % shader, type="projection")[0]
    fileNode = mc.listConnections("%s.image" % projection, type="file")[0]
    multNode = mc.shadingNode("multiplyDivide", asUtility=True)

    # connect the mult node out to the shader outColor
    mc.connectAttr("%s.outputX" % multNode, "%s.outColorR" % shader, f=True)
    mc.connectAttr("%s.outputY" % multNode, "%s.outColorG" % shader, f=True)
    mc.connectAttr("%s.outputZ" % multNode, "%s.outColorB" % shader, f=True)

    # create a ramp node
    # ramp = mc.shadingNode('ramp', asTexture=True)

    # create a samplerInfo node
    sampler_info = mc.shadingNode("samplerInfo", asUtility=True)

    mc.setAttr(
        "%s.fileTextureName" % fileNode,
        os.path.join(cgmImages.__path__[0], "white.png"),
        type="string",
    )

    # connect projection color to the mult node
    mc.connectAttr("%s.outColor" % projection, "%s.input1" % multNode)

    # connect sampler info facing ratio to the mult node X
    mc.connectAttr("%s.facingRatio" % sampler_info, "%s.input2X" % multNode)

    # set mult Y to 1
    mc.setAttr("%s.input2Y" % multNode, 1)

    # create the vignette projection ramp
    vignetteRamp = mc.shadingNode("ramp", asTexture=True)
    vignetteProjection = mc.shadingNode("projection", asTexture=True)

    # set projection to perspective and link camera
    mc.setAttr("%s.projType" % vignetteProjection, 8)
    mc.connectAttr(
        "%s.worldMatrix[0]" % cameraShape, "%s.linkedCamera" % vignetteProjection
    )

    # connect the ramp node to the projection node
    mc.connectAttr("%s.outColor" % vignetteRamp, "%s.image" % vignetteProjection)

    # set the ramp node to linear
    mc.setAttr("%s.interpolation" % vignetteRamp, 1)

    # set to box ramp
    mc.setAttr("%s.type" % vignetteRamp, 5)

    # set first color to white and last color to black
    mc.setAttr("%s.colorEntryList[0].position" % vignetteRamp, 0)
    mc.setAttr("%s.colorEntryList[1].position" % vignetteRamp, 1)
    mc.setAttr("%s.colorEntryList[0].color" % vignetteRamp, 1, 1, 1, type="double3")
    mc.setAttr("%s.colorEntryList[1].color" % vignetteRamp, 0, 0, 0, type="double3")

    # connect projection outputR to shaders inputB
    mc.connectAttr(
        "%s.outColorR" % vignetteProjection, "%s.input2Z" % multNode, force=True
    )

    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_alpha")

    shader = mc.rename(shader, "cgmAlphaProjectionShader")

    return shader, sg


def makeAlphaMatteShader():
    shader = mc.shadingNode("lambert", asShader=True)
    sg = mc.sets(
        renderable=True, noSurfaceShader=True, empty=True, name="%sSG" % shader
    )

    mc.connectAttr("%s.outColor" % shader, "%s.surfaceShader" % sg)

    shader = mc.rename(shader, "cgmAlphaMatteMaterial")

    return shader, sg


# Create a camera that projects a texture onto the selected object
def makeProjectionCamera():
    camera, shape = mc.camera(name="cgmProjectionCamera")

    mc.setAttr("%s.renderable" % (shape), 1)
    # set film aspect ratio to 1
    mc.setAttr("%s.horizontalFilmAperture" % (shape), 1)
    mc.setAttr("%s.verticalFilmAperture" % (shape), 1)

    # set the lens squeeze ratio to 1
    mc.setAttr("%s.lensSqueezeRatio" % (shape), 1)

    mc.setAttr("%s.filmFit" % (shape), 2)

    mc.setAttr("%s.mask" % (shape), False)

    mShape = cgmMeta.asMeta(shape)
    mShape.doStore("cgmCamera", "projection")

    return (camera, shape)


def bakeProjection(material, meshObj, resolution=(2048, 2048)):
    convertedFile = mc.convertSolidTx(
        "%s.outColor" % material,
        meshObj,
        antiAlias=1,
        bm=1,
        fts=1,
        sp=0,
        sh=0,
        alpha=False,
        doubleSided=0,
        componentRange=0,
        resolutionX=resolution[0],
        resolutionY=resolution[1],
        fileFormat="png",
    )

    if convertedFile:
        convertedFile = convertedFile[0]
    else:
        return None

    return convertedFile


def copyRemapValues(source, destination):
    _str_func = "copyRemapValues"
    log.debug(
        "|{0}| >>  source: {1}  >>  destination: {2}".format(
            _str_func, source, destination
        )
    )


def addImageToCompositeShader(shader, color, alpha):
    _str_func = "addImageToCompositeShader"

    log.debug(
        "|{0}| >>  shader: {1}  >>  color: {2}  >>  alpha: {3}".format(
            _str_func, shader, color, alpha
        )
    )

    layeredTexture = mc.listConnections("%s.outColor" % shader, type="layeredTexture")[
        0
    ]
    connections = mc.listConnections(layeredTexture, p=True, s=True, d=False) or []

    inputs = []
    if connections:
        # outColorConnections = [c for c in connections if '.outColor' in c]
        inputs = mc.listConnections(connections, p=True, d=True, s=False) or []
        # get only the inputs with .inputs
        inputs = [i for i in inputs if ".inputs" in i]

        # input_connection = inputs[0]
        for input_connection in reversed(inputs):
            current_index = int(input_connection.split("inputs[")[1].split("]")[0])
            next_index = current_index + 1

            connectionPlug = input_connection.split(".")[-1]
            # Disconnect empty connections
            connected_attr = "%s.inputs[%d].%s" % (
                layeredTexture,
                current_index,
                connectionPlug,
            )
            src_attr = mc.listConnections(connected_attr, p=True, s=True, d=False)

            if src_attr:
                mc.disconnectAttr(src_attr[0], connected_attr)

            # Shift the connections down the line
            mc.connectAttr(
                src_attr[0],
                input_connection.replace(f"[{current_index}]", f"[{next_index}]"),
                f=True,
            )

    firstConnection = len(inputs) == 0

    remapColor, mult2 = remapAndMultiplyColorChannels(
        alpha, ["Facing Ratio", "Distance", "Vignette"]
    )

    mc.setAttr("%s.red[0].red_Position" % remapColor, 0.1)
    mc.setAttr("%s.red[1].red_Position" % remapColor, 0.5)
    mc.setAttr("%s.red[0].red_FloatValue" % remapColor, 1 if firstConnection else 0)

    mc.setAttr("%s.green[0].green_Position" % remapColor, 0)
    mc.setAttr("%s.green[1].green_Position" % remapColor, 0.5)
    mc.setAttr("%s.green[0].green_FloatValue" % remapColor, 1 if firstConnection else 0)
    mc.setAttr("%s.green[1].green_FloatValue" % remapColor, 1)

    mc.setAttr("%s.blue[0].blue_Position" % remapColor, 0)
    mc.setAttr("%s.blue[1].blue_Position" % remapColor, 0.4)
    mc.setAttr("%s.blue[0].blue_FloatValue" % remapColor, 1 if firstConnection else 0)
    mc.setAttr("%s.blue[1].blue_FloatValue" % remapColor, 1)

    # connect multiply out X to layered texture alpha
    mc.connectAttr("%s.outColor" % color, "%s.inputs[0].color" % layeredTexture, f=True)
    mc.connectAttr("%s.outputX" % mult2, "%s.inputs[0].alpha" % layeredTexture, f=True)

    return 0, remapColor


def remapAndMultiplyColorChannels(color, labels=["Red", "Green", "Blue"]):
    remapColor = mc.shadingNode("remapColor", asUtility=True)
    mult = mc.shadingNode("multiplyDivide", asUtility=True)
    mult2 = mc.shadingNode("multiplyDivide", asUtility=True)

    mc.connectAttr("%s.outColorR" % remapColor, "%s.input1X" % mult, f=True)
    mc.connectAttr("%s.outColorG" % remapColor, "%s.input2X" % mult, f=True)

    mc.connectAttr("%s.outputX" % mult, "%s.input1X" % mult2, f=True)
    mc.connectAttr("%s.outColorB" % remapColor, "%s.input2X" % mult2, f=True)

    mc.connectAttr("%s.outColor" % color, "%s.color" % remapColor, f=True)

    # add label attributes as strings called cgmRedLabel, cgmGreenLabel, cgmBlueLabel
    for i, channel in enumerate(["Red", "Green", "Blue"]):
        mc.addAttr(remapColor, ln=f"cgm{channel}Label", dt="string")
        mc.setAttr(f"{remapColor}.cgm{channel}Label", labels[i], type="string")

    return remapColor, mult2


def updateAlphaMatteShader(alphaShader, compositeShader):
    layeredTexture = mc.listConnections(
        "%s.outColor" % alphaShader, type="layeredTexture"
    )[0]
    compositelayeredTexture = mc.listConnections(
        "%s.outColor" % compositeShader, type="layeredTexture"
    )[0]

    connections = mc.listConnections(layeredTexture, p=True, s=True, d=False) or []
    if connections:
        for connection in connections:
            outConnections = (
                mc.listConnections(connection, p=True, s=False, d=True) or []
            )
            for out in outConnections:
                if layeredTexture in out:
                    mc.disconnectAttr(connection, out)

    connections = (
        mc.listConnections(compositelayeredTexture, p=True, s=True, d=False) or []
    )
    for connection in connections:
        outConnections = mc.listConnections(connection, p=True, s=False, d=True) or []
        for out in outConnections:
            if "alpha" in out:
                index = int(out.split("inputs[")[-1].split("]")[0])
                connectionNode, connectionNodeType = mc.ls(
                    connection.split(".")[0], st=True
                )

                if connectionNodeType == "multiplyDivide":
                    connectionDupe = mc.duplicate(connectionNode, upstreamNodes=True)
                    for i, n in enumerate(connectionDupe):
                        connectionDupe[i] = mc.rename(n, "%s_alpha" % n)
                    connection = "%s.%s" % (
                        connectionDupe[0],
                        ".".join(connection.split(".")[1:]),
                    )

                # Check if input entry is empty before connecting
                input_color_attrs = [
                    "%s.inputs[%d].colorR" % (layeredTexture, index),
                    "%s.inputs[%d].colorG" % (layeredTexture, index),
                    "%s.inputs[%d].colorB" % (layeredTexture, index),
                ]
                if not any(
                    mc.listConnections(attr, p=True, s=True, d=False)
                    for attr in input_color_attrs
                ):
                    mc.connectAttr(connection, input_color_attrs[0])
                    mc.connectAttr(connection, input_color_attrs[1])
                    mc.connectAttr(connection, input_color_attrs[2])

                mc.setAttr("%s.inputs[%d].blendMode" % (layeredTexture, index), 1)


def assignImageToProjectionShader(shader, image_path, data):
    projection = mc.listConnections("%s.outColorR" % shader, type="projection")[0]
    fileNode, place2d = createFileNode(image_path)

    mc.connectAttr(fileNode + ".outColor", projection + ".image", force=True)

    # set wrap UV to false
    mc.setAttr("%s.wrapU" % place2d, 0)
    mc.setAttr("%s.wrapV" % place2d, 0)

    # set default color to black
    mc.setAttr("%s.defaultColor" % fileNode, 0, 0, 0, type="double3")

    mFile = cgmMeta.asMeta(fileNode)
    mFile.doStore("cgmImageProjectionData", json.dumps(data))


def createFileNode(image_path=""):
    fileNode = mc.shadingNode("file", asTexture=True, isColorManaged=True)

    if image_path:
        mc.setAttr(fileNode + ".fileTextureName", image_path, type="string")

    # create texture placement node
    place2d = mc.shadingNode("place2dTexture", asUtility=True)
    mc.connectAttr(place2d + ".coverage", fileNode + ".coverage", force=True)
    mc.connectAttr(
        place2d + ".translateFrame", fileNode + ".translateFrame", force=True
    )
    mc.connectAttr(place2d + ".rotateFrame", fileNode + ".rotateFrame", force=True)
    mc.connectAttr(place2d + ".mirrorU", fileNode + ".mirrorU", force=True)
    mc.connectAttr(place2d + ".mirrorV", fileNode + ".mirrorV", force=True)
    mc.connectAttr(place2d + ".stagger", fileNode + ".stagger", force=True)
    mc.connectAttr(place2d + ".wrapU", fileNode + ".wrapU", force=True)
    mc.connectAttr(place2d + ".wrapV", fileNode + ".wrapV", force=True)
    mc.connectAttr(place2d + ".repeatUV", fileNode + ".repeatUV", force=True)
    mc.connectAttr(place2d + ".offset", fileNode + ".offset", force=True)
    mc.connectAttr(place2d + ".rotateUV", fileNode + ".rotateUV", force=True)
    mc.connectAttr(place2d + ".noiseUV", fileNode + ".noiseUV", force=True)
    mc.connectAttr(place2d + ".vertexUvOne", fileNode + ".vertexUvOne", force=True)
    mc.connectAttr(place2d + ".vertexUvTwo", fileNode + ".vertexUvTwo", force=True)
    mc.connectAttr(place2d + ".vertexUvThree", fileNode + ".vertexUvThree", force=True)
    mc.connectAttr(
        place2d + ".vertexCameraOne", fileNode + ".vertexCameraOne", force=True
    )
    mc.connectAttr(place2d + ".outUV", fileNode + ".uv", force=True)
    mc.connectAttr(place2d + ".outUvFilterSize", fileNode + ".uvFilterSize", force=True)

    return fileNode, place2d


def renderMaterialPass(
    material=None,
    meshes=None,
    fileName=None,
    format="png",
    camera=None,
    resolution=None,
):
    # print("renderMaterialPass(%s, %s, %s, %s, %s)" % (material, meshObj, fileName, asJpg, camera))

    tmpdir = tempfile.TemporaryDirectory().name
    log.debug(f"Created temporary directory: {tmpdir}")

    currentResolution = [
        mc.getAttr("defaultResolution.width"),
        mc.getAttr("defaultResolution.height"),
    ]

    pAx = mc.getAttr("defaultResolution.pixelAspect")
    pAr = mc.getAttr("defaultResolution.deviceAspectRatio")
    al = mc.getAttr("defaultResolution.aspectLock")

    if resolution != None:
        mc.setAttr("defaultResolution.aspectLock", 0)
        mc.setAttr("defaultResolution.width", resolution[0])
        mc.setAttr("defaultResolution.height", resolution[1])
        mc.setAttr("defaultResolution.pixelAspect", pAx)
        mc.setAttr("defaultResolution.deviceAspectRatio", pAr)
        mc.refresh()
    else:
        resolution = currentResolution

    wantedName = os.path.join(tmpdir, "<RenderLayer>", "RenderPass")
    if material:
        # assign depth shader
        sg = mc.listConnections(material, type="shadingEngine")
        if sg:
            sg = sg[0]

        if sg and meshes:
            for meshObj in meshes:
                assignMaterial(meshObj, sg)
        else:
            log.warning("No shading group or meshes found for material %s" % material)

        wantedName = os.path.join(tmpdir, "<RenderLayer>", material)

    if fileName:
        wantedName = os.path.join(tmpdir, "<RenderLayer>", fileName)

    # setAttr "defaultRenderGlobals.imageFormat" 8;
    currentImageFormat = mc.getAttr("defaultRenderGlobals.imageFormat")
    currentFilenamePrefix = mc.getAttr("defaultRenderGlobals.imageFilePrefix")

    if format.lower() == "jpg" or format.lower() == "jpeg":
        mc.setAttr("defaultRenderGlobals.imageFormat", 8)
    elif format.lower() == "png":
        mc.setAttr("defaultRenderGlobals.imageFormat", 32)

    # mc.setAttr("defaultRenderGlobals.imageFilePrefix", wantedName, type="string")

    # outputFileName = mc.renderSettings(fullPathTemp=True, firstImageName=True)

    uniqueFileName = files.create_unique_filename(wantedName)
    # newName = os.path.splitext(os.path.split(uniqueFileName)[-1])[0]

    log.debug("uniqueFileName: %s" % uniqueFileName)

    mc.setAttr("defaultRenderGlobals.imageFilePrefix", uniqueFileName, type="string")

    if camera:
        cameras = mc.ls(type="camera")

        # iterate through the cameras and set them to not be renderable
        for renderCam in cameras:
            if renderCam == camera:
                mc.setAttr(renderCam + ".renderable", 1)
            else:
                mc.setAttr(renderCam + ".renderable", 0)

    imagePath = mc.render(batch=False, rep=True, x=resolution[0], y=resolution[1])

    log.debug("currentFilenamePrefix: %s" % currentFilenamePrefix)
    mc.setAttr("defaultRenderGlobals.imageFormat", currentImageFormat)
    mc.setAttr(
        "defaultRenderGlobals.imageFilePrefix",
        currentFilenamePrefix or "",
        type="string",
    )
    mc.setAttr("defaultResolution.aspectLock", al)
    mc.setAttr("defaultResolution.width", currentResolution[0])
    mc.setAttr("defaultResolution.height", currentResolution[1])
    mc.setAttr("defaultResolution.pixelAspect", pAx)
    mc.setAttr("defaultResolution.deviceAspectRatio", pAr)

    log.debug("Rendered material pass, %s, %s" % (material, imagePath))
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


def getAllConnectedNodesOfType(sourceShadingNode, nodeType, traverseUserDefined=True):
    result = []

    def walkConnections(node, nodeType, visited=None, traverseUserDefined=True):
        if visited is None:
            visited = set()
        connectedNodes = []
        connections = mc.listConnections(
            node, source=True, destination=False, plugs=True
        )

        if not traverseUserDefined:
            # Filter out any user defined attributes
            userDefinedAttributes = mc.listAttr(node, ud=True)
            if userDefinedAttributes:
                connection = connections[0]
                for connection in connections:
                    sourceConnections = mc.listConnections(connection, p=True)
                    for sourceConnection in sourceConnections:
                        if sourceConnection.split(".")[1] in userDefinedAttributes:
                            connections.remove(connection)

        if connections:
            for connection in connections:
                connectedNode = connection.split(".")[0]
                connectedNodeType = mc.nodeType(connectedNode)

                if connectedNodeType == nodeType:
                    # Modify the returned list to include the destination attribute instead of the source attribute
                    connectedNodes.append(
                        [
                            connectedNode,
                            mc.listConnections(
                                connection, source=False, destination=True, plugs=True
                            )[0],
                        ]
                    )

                if connectedNode not in visited:
                    visited.add(connectedNode)
                    connectedNodes.extend(
                        walkConnections(
                            connectedNode, nodeType, visited, traverseUserDefined
                        )
                    )

        return connectedNodes

    result = walkConnections(
        sourceShadingNode, nodeType, traverseUserDefined=traverseUserDefined
    )

    # get first element of each item in the list
    result = [item[0] for item in result]

    # Remove any duplicates from the returned list
    result = list(set(result))

    return result


def getInputConnections(node_attr):
    base_attr = ".".join(node_attr.split(".")[:-1])
    sub_attrs = mc.listAttr(node_attr, multi=True)
    input_connections = []
    if sub_attrs:
        for sub_attr in sub_attrs:
            full_attr = base_attr + "." + sub_attr
            if "[" in sub_attr and not "." in sub_attr:
                continue

            connected_attrs = mc.listConnections(full_attr, plugs=True)
            if connected_attrs:
                for conn_attr in connected_attrs:
                    input_connections.append(
                        [conn_attr, full_attr, mc.getAttr(conn_attr)]
                    )
            else:
                input_connections.append([None, full_attr, mc.getAttr(full_attr)])
    return input_connections


def reconnectConnections(connections, node_attr, src_attr):
    _str_func = "reconnectConnections"

    log.debug(
        "\n\n|{0}| >>  \nnode_attr: {1} \nsrc_attr: {2} \nconnections: {3}\n".format(
            _str_func, node_attr, src_attr, connections
        )
    )

    for attr in mc.listAttr(node_attr):
        if not mc.objExists(node_attr + "." + attr):
            continue
        cons = mc.listConnections(node_attr + "." + attr, plugs=True) or []
        for con in cons:
            mc.disconnectAttr(con, node_attr + "." + attr)

    for conn_attr, sub_attr, value in connections:
        if conn_attr:
            mc.connectAttr(conn_attr, sub_attr.replace(src_attr, node_attr), force=True)
        try:
            mc.setAttr(sub_attr.replace(src_attr, node_attr), value)
        except RuntimeError:
            continue


def reorderLayeredTexture(layeredTexture, source_index, destination_index):
    """
    Reorders the connections of a layeredTexture node, moving the source index to the destination index.
    :param layeredTexture: The name of the layeredTexture node.
    :param source_index: The index to move.
    :param destination_index: The index to move the source index to.
    :return: True if successful, False otherwise.
    """

    log.debug(
        "Reordering layeredTexture node: %s, source index: %s, destination index: %s"
        % (layeredTexture, source_index, destination_index)
    )

    if (
        not mc.objExists(layeredTexture)
        or mc.nodeType(layeredTexture) != "layeredTexture"
    ):
        log.warning("Invalid layeredTexture node provided.")
        return False

    num_inputs = mc.getAttr(layeredTexture + ".inputs", multiIndices=True)

    if source_index >= len(num_inputs) or destination_index >= len(num_inputs):
        log.warning("Invalid source or destination index provided.")
        return False

    if source_index == destination_index:
        log.warning("Source and destination indices are the same, no action required.")
        return True

    src_input_index = num_inputs[source_index]
    dst_input_index = num_inputs[destination_index]
    if source_index < destination_index:
        indices_to_move = num_inputs[source_index + 1 : destination_index + 1]
    else:
        indices_to_move = num_inputs[destination_index:source_index]

    src_attr = layeredTexture + ".inputs[{}]".format(src_input_index)
    src_connections = getInputConnections(src_attr)

    def disconnectConnections(connections):
        for conn_attr, sub_attr, _ in connections:
            if conn_attr:
                if mc.isConnected(conn_attr, sub_attr):
                    mc.disconnectAttr(conn_attr, sub_attr)

    # Disconnect source connections
    disconnectConnections(src_connections)

    for i, index in enumerate(indices_to_move):
        current_index = num_inputs.index(index)
        current_attr = layeredTexture + ".inputs[{}]".format(index)

        if source_index < destination_index:
            next_attr = layeredTexture + ".inputs[{}]".format(
                num_inputs[current_index - 1]
            )
        else:
            next_attr = layeredTexture + ".inputs[{}]".format(
                num_inputs[current_index + 1]
            )

        current_connections = getInputConnections(current_attr)
        next_connections = copy.deepcopy(current_connections)

        for j, conn in enumerate(next_connections):
            next_connections[j][1] = current_connections[j][1].replace(
                current_attr, next_attr
            )

        # Disconnect current connections
        disconnectConnections(current_connections)

        reconnectConnections(next_connections, next_attr, current_attr)

    dst_attr = layeredTexture + ".inputs[{}]".format(dst_input_index)
    reconnectConnections(src_connections, dst_attr, src_attr)

    return True

    for i, index in enumerate(indices_to_move):
        current_index = num_inputs.index(index)
        current_attr = layeredTexture + ".inputs[{}]".format(index)
        next_attr = (
            layeredTexture + ".inputs[{}]".format(num_inputs[current_index - 1])
            if i + 1 < len(num_inputs)
            else layeredTexture + ".inputs[{}]".format(num_inputs[current_index + 1])
        )

        current_connections = getInputConnections(current_attr)
        next_connections = copy.deepcopy(current_connections)

        for j, conn in enumerate(next_connections):
            next_connections[j][1] = current_connections[j][1].replace(
                current_attr, next_attr
            )

        # Disconnect current connections
        disconnectConnections(current_connections)

        reconnectConnections(next_connections, next_attr, current_attr)

    dst_attr = layeredTexture + ".inputs[{}]".format(dst_input_index)
    reconnectConnections(src_connections, dst_attr, src_attr)

    return True


def removeUnusedLayeredTextureInputs(layeredTexture):
    """
    Removes any unused inputs from a layeredTexture node.
    :param layeredTexture: The name of the layeredTexture node.
    :return: True if successful, False otherwise.
    """

    if (
        not mc.objExists(layeredTexture)
        or mc.nodeType(layeredTexture) != "layeredTexture"
    ):
        print("Invalid layeredTexture node provided.")
        return False

    num_inputs = mc.getAttr(layeredTexture + ".inputs", multiIndices=True)
    # i = 2
    # index = num_inputs[2]

    removal_attributes = []

    for i, index in enumerate(num_inputs):
        if i != index:
            # get connections
            src_attr = layeredTexture + ".inputs[{}]".format(index)
            src_connections = getInputConnections(src_attr)
            dst_attr = layeredTexture + ".inputs[{}]".format(i)
            # make a copy of src connections in dst connections
            dst_connections = getInputConnections(src_attr)

            for j, conn in enumerate(dst_connections):
                dst_connections[j][1] = dst_connections[j][1].replace(
                    src_attr, dst_attr
                )

            # add index to remove
            removal_attributes.append(src_attr)

            # disconnect
            for conn_attr, sub_attr, _ in src_connections:
                if conn_attr:
                    if mc.isConnected(conn_attr, sub_attr):
                        mc.disconnectAttr(conn_attr, sub_attr)

            # reconnect
            reconnectConnections(dst_connections, dst_attr, src_attr)

    removal_attributes.reverse()
    for src_attr in removal_attributes:
        mc.removeMultiInstance(src_attr, b=True)

    return True


def getRemapColorInfo(remapColor):
    remapInterpolationType = ["None", "Linear", "Smooth", "Spline"]
    remapColorData = {}
    fileNode = mc.listConnections(f"{remapColor}.color", type="file")
    if fileNode:
        remapColorData["imagePath"] = mc.getAttr(f"{fileNode[0]}.fileTextureName")
    else:
        remapColorData["imagePath"] = None

    for channel in ["red", "green", "blue"]:
        indices = mc.getAttr(f"{remapColor}.{channel}", multiIndices=True)

        channelData = []
        for index in indices:
            position = mc.getAttr(f"{remapColor}.{channel}[{index}].{channel}_Position")
            value = mc.getAttr(f"{remapColor}.{channel}[{index}].{channel}_FloatValue")
            interp = remapInterpolationType[
                mc.getAttr(f"{remapColor}.{channel}[{index}].{channel}_Interp")
            ]
            channelData.append(
                {"index": index, "position": position, "value": value, "interp": interp}
            )
        remapColorData[channel] = channelData[:]

    return remapColorData


def remapImageColors(remapColorData):
    start_time = time.time()

    def create_lut(channelData, channelName):
        channelDataCopy = channelData.copy()
        channelDataCopy.sort(key=lambda x: x["position"])

        lut = np.zeros(256, dtype=np.uint8)
        previous = None
        next_point = channelDataCopy[0] if len(channelDataCopy) > 0 else None

        for i in range(256):
            value = i / 255.0

            while next_point is not None and value > next_point["position"]:
                previous = next_point
                channelDataCopy.pop(0)
                next_point = channelDataCopy[0] if len(channelDataCopy) > 0 else None

            if previous is None and next_point is not None:
                lut[i] = int(255 * next_point["value"])
            elif next_point is None and previous is not None:
                lut[i] = int(255 * previous["value"])
            elif previous is not None and next_point is not None:
                t = (value - previous["position"]) / (
                    next_point["position"] - previous["position"]
                )
                lut[i] = int(
                    255
                    * (
                        previous["value"]
                        + t * (next_point["value"] - previous["value"])
                    )
                )

        return lut

    def apply_lut(image, lut_r, lut_g, lut_b):
        image_data = np.array(image)
        remapped_data = np.zeros(image_data.shape, dtype=np.uint8)

        remapped_data[:, :, 0] = lut_r[image_data[:, :, 0]]
        remapped_data[:, :, 1] = lut_g[image_data[:, :, 1]]
        remapped_data[:, :, 2] = lut_b[image_data[:, :, 2]]

        remapped_image = Image.fromarray(remapped_data)
        return remapped_image

    load_image_start_time = time.time()
    image = Image.open(remapColorData["imagePath"]).convert("RGB")
    load_image_end_time = time.time()

    create_lut_start_time = time.time()
    lut_red = create_lut(remapColorData["red"], "red_lut")
    lut_green = create_lut(remapColorData["green"], "green_lut")
    lut_blue = create_lut(remapColorData["blue"], "blue_lut")
    create_lut_end_time = time.time()

    apply_lut_start_time = time.time()
    remapped_image = apply_lut(image, lut_red, lut_green, lut_blue)
    apply_lut_end_time = time.time()

    end_time = time.time()

    print(f"Start Time: {time.ctime(start_time)}")
    print(f"Load Image Start Time: {time.ctime(load_image_start_time)}")
    print(f"Load Image End Time: {time.ctime(load_image_end_time)}")
    print(f"Create LUT Start Time: {time.ctime(create_lut_start_time)}")
    print(f"Create LUT End Time: {time.ctime(create_lut_end_time)}")
    print(f"Apply LUT Start Time: {time.ctime(apply_lut_start_time)}")
    print(f"Apply LUT End Time: {time.ctime(apply_lut_end_time)}")
    print(f"End Time: {time.ctime(end_time)}")
    print(f"Load Image Time: {load_image_end_time - load_image_start_time:.2f} seconds")
    print(f"Create LUT Time: {create_lut_end_time - create_lut_start_time:.2f} seconds")
    print(f"Apply LUT Time: {apply_lut_end_time - apply_lut_start_time:.2f} seconds")
    print(f"Total Time: {end_time - start_time:.2f} seconds")

    return remapped_image


def getLayeredTextureImages(layeredTextureNode):
    _blendModes = (
        "None",
        "Over",
        "In",
        "Out",
        "Add",
        "Subtract",
        "Multiply",
        "Difference",
        "Lighten",
        "Darken",
        "Saturate",
        "Desaturate",
        "Illuminate",
        "CPV Modulate",
    )

    inputCount = mc.getAttr(layeredTextureNode + ".inputs", size=True)
    inputData = []

    tmpdir = tempfile.TemporaryDirectory().name
    print(f"Created temporary directory: {tmpdir}")

    # if tmpdir doesn't exist, create it
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

    for i in range(inputCount):
        colorAttr = layeredTextureNode + f".inputs[{i}].color"
        alphaAttr = layeredTextureNode + f".inputs[{i}].alpha"

        imagePath = None
        alphaPaths = []

        fileNodes = getAllConnectedNodesOfType(
            colorAttr, "file", traverseUserDefined=False
        )
        if fileNodes:
            imagePath = mc.getAttr(fileNodes[0] + ".fileTextureName")

        remapColorNodes = getAllConnectedNodesOfType(
            alphaAttr, "remapColor", traverseUserDefined=False
        )

        for j, remapColorNode in enumerate(remapColorNodes):
            remapColorData = getRemapColorInfo(remapColorNode)
            remapColorImage = remapImageColors(remapColorData)

            redLabel = (
                mc.getAttr(remapColorNode + ".cgmRedLabel")
                if mc.objExists(remapColorNode + ".cgmRedLabel")
                else "R"
            )
            greenLabel = (
                mc.getAttr(remapColorNode + ".cgmGreenLabel")
                if mc.objExists(remapColorNode + ".cgmGreenLabel")
                else "G"
            )
            blueLabel = (
                mc.getAttr(remapColorNode + ".cgmBlueLabel")
                if mc.objExists(remapColorNode + ".cgmBlueLabel")
                else "B"
            )

            # combine strings and replace spaces with underscores
            remapColorNodeLabel = f"{redLabel}{greenLabel}{blueLabel}".replace(" ", "_")

            alphaPath = os.path.join(
                tmpdir, f"alpha{i}_{remapColorNode}_{remapColorNodeLabel}.png"
            )
            remapColorImage.save(alphaPath)

            alphaPaths.append(alphaPath)

        if imagePath:
            inputData.append(
                {
                    "color": imagePath,
                    "alpha": alphaPaths,
                    "blendMode": _blendModes[
                        mc.getAttr(layeredTextureNode + f".inputs[{i}].blendMode")
                    ],
                    "isVisible": mc.getAttr(
                        layeredTextureNode + f".inputs[{i}].isVisible"
                    ),
                }
            )

    return inputData


def apply_blend_mode(image1, image2, blend_mode):
    if blend_mode == "Over":
        return Image.alpha_composite(image1, image2)
    elif blend_mode == "Add":
        return ImageChops.add(image1, image2)
    elif blend_mode == "Subtract":
        return ImageChops.subtract(image1, image2)
    elif blend_mode == "Multiply":
        return ImageChops.multiply(image1, image2)
    elif blend_mode == "Difference":
        return ImageChops.difference(image1, image2)
    elif blend_mode == "Lighten":
        return ImageChops.lighter(image1, image2)
    elif blend_mode == "Darken":
        return ImageChops.darker(image1, image2)
    else:
        return image1


def overlay_images(images_data):
    base_image = None

    for data in images_data:
        if data["isVisible"]:
            color_image = Image.open(data["color"]).convert("RGBA")

            # Process and multiply multiple alpha images
            merged_alpha_image = None
            for alpha_path in data["alpha"]:
                alpha_image = Image.open(alpha_path).convert("RGB")
                r, g, b = alpha_image.split()
                alpha_image = ImageMath.eval(
                    "r*g*b / (255 * 255)", r=r, g=g, b=b
                ).convert("L")

                if merged_alpha_image is None:
                    merged_alpha_image = alpha_image
                else:
                    merged_alpha_image = ImageMath.eval(
                        "a * b / (255)", a=merged_alpha_image, b=alpha_image
                    ).convert("L")

            if merged_alpha_image is not None:
                color_image.putalpha(merged_alpha_image)

            # Initialize base image if it does not exist
            if base_image is None:
                base_image = color_image
            else:
                # Apply blend mode and combine images
                blend_mode = data["blendMode"]
                if blend_mode in [
                    "Over",
                    "Add",
                    "Subtract",
                    "Multiply",
                    "Difference",
                    "Lighten",
                    "Darken",
                ]:
                    base_image = apply_blend_mode(base_image, color_image, blend_mode)
                else:
                    print(
                        f"Blend mode '{blend_mode}' not supported by PIL. Skipping this layer."
                    )
        else:
            continue

    return base_image


def makeImagePlane(imagePath, info, shader=None):
    # get the image size with PIL
    image = Image.open(imagePath)
    info["width"] = image.size[0]
    info["height"] = image.size[1]

    # Create a polyPlane and a shading group
    plane = mc.polyPlane(
        name="imagePlane",
        width=info["width"] * 0.01,
        height=info["height"] * 0.01,
        subdivisionsX=1,
        subdivisionsY=1,
        axis=(0, 0, 1),
        constructionHistory=False,
    )[0]
    shape = mc.listRelatives(plane, shapes=True)[0]

    if not shader:
        shader, sg = makeShader("surfaceShader")
    else:
        sg = mc.listConnections(shader, type="shadingEngine")[0]

    # Create a file texture node and connect it to the shading group
    fileNode, place2d = createFileNode(imagePath)
    mc.connectAttr(fileNode + ".outColor", shader + ".outColor")

    assignMaterial(shape, sg)

    return plane, shader, fileNode