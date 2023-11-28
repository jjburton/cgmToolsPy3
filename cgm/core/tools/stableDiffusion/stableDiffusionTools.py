import maya.cmds as mc
import http.client
import json
from io import BytesIO
import os
import pprint
import base64
from PIL import Image, PngImagePlugin
from datetime import datetime

from cgm.core.tools.stableDiffusion import renderTools as rt
from cgm.core.tools import imageTools as it
from cgm.core import cgm_Meta as cgmMeta
from cgm.lib import files
import cgm.core.tools.Project as PROJECT

import re
import time
from collections import defaultdict

import logging

import cgm.core.lib.position_utils as POS
from cgm.core.lib import euclid as EUCLID
from cgm.core.lib import transform_utils as TRANS
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core.lib import math_utils as MATHUTILS
from cgm.core.lib import camera_utils as CAM
import cgm.core.lib.distance_utils as DIST

import math

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


# adjusts the local position of a mesh based on the R value of a texture
# useful for creating a z-depth push effect
# usage:
# adjust_position_based_on_texture("pPlane1", "file1", 800, [0,0,1], False)
def adjustPositionBasedOnTexture(mesh_name, texture_name, z_depth, axis, invert=False):
    # Get the texture file path
    texture_path = mc.getAttr(texture_name + ".fileTextureName")

    # Get the width and height of the texture image
    texture_width = mc.getAttr(texture_name + ".outSizeX")
    texture_height = mc.getAttr(texture_name + ".outSizeY")

    # Loop through each vertex and adjust the z position based on the R value of the texture at the corresponding UV coordinate
    verts = mc.ls(mesh_name + ".vtx[*]", flatten=True)
    for vtx in mc.ls(mesh_name + ".vtx[*]", flatten=True):
        # Get the UV coordinate of the vertex
        uv = mc.polyEditUV(
            mc.polyListComponentConversion(vtx, fv=True, tuv=True)[0],
            u=True,
            v=True,
            query=True,
        )

        # Convert UV coordinates to pixel coordinates
        pixel_u = int(uv[0] * texture_width)
        pixel_v = int(uv[1] * texture_height)

        # Get the R value of the texture at the corresponding pixel
        r_value = mc.colorAtPoint(texture_name, o="RGB", u=uv[0], v=uv[1])[0]
        if invert:
            r_value = 1.0 - r_value
        # Adjust the z position of the vertex based on the R value and z-depth parameter
        mc.move(
            r_value * z_depth * axis[0],
            r_value * z_depth * axis[1],
            r_value * z_depth * axis[2],
            vtx,
            relative=True,
            os=True,
        )


# _defaultOptions = {
#         'automatic_url':'127.0.0.1:7860',
#         'prompt':'',
#         'negative_prompt':'',
#         'steps':5,
#         'seed':-1,
#         'width':512,
#         'height':512,
#         'sampling_steps':5,
#         'depth_distance':30.0,
#         'control_net_enabled':True,
#         'control_net_low_v_ram':False,
#         'control_net_preprocessor':'none',
#         'control_net_weight':1.0,
#         'control_net_guidance_start':0.0,
#         'control_net_guidance_end':1.0,
# }
def getImageFromAutomatic1111(data):
    _str_func = 'getImageFromAutomatic1111'
    log.debug("|{0}| >> data: {1}".format(_str_func, data))

    payload = {
        "prompt": data["prompt"],
        "negative_prompt": data["negative_prompt"],
        "steps": data["sampling_steps"],
        "seed": data["seed"],
        "width": data["width"],
        "height": data["height"],
        "sampler_index": data["sampling_method"],
        "batch_size": data["batch_size"],
        "n_iter": data["batch_count"],
        "cfg_scale": data["cfg_scale"],
    }

    controlNets = []
    for i, controlNetDict in enumerate(data["control_nets"]):
        if controlNetDict["control_net_enabled"]:
            controlNetArgs = {
                        "lowvram": controlNetDict["control_net_low_v_ram"],
                        "module": controlNetDict["control_net_preprocessor"],
                        "model": controlNetDict["control_net_model"],
                        "weight": controlNetDict["control_net_weight"],
                        "resize_mode": "Scale to Fit (Inner Fit)",
                        "input_image": controlNetDict["control_net_image"],
                        "processor_res": 512,
                        "threshold_a": 100,
                        "threshold_b": 255,
                        "guidance_start": controlNetDict["control_net_guidance_start"],
                        "guidance_end": controlNetDict["control_net_guidance_end"],
                        "controlmode": "Balanced",
                    }
            controlNets.append(controlNetArgs)

    if len(controlNets) > 0:
        payload["alwayson_scripts"] = {
            "controlnet": {
                "args": controlNets
            }
        }

    endpoint = "/sdapi/v1/txt2img"

    if "init_images" in data:
        endpoint = "/sdapi/v1/img2img"
        payload["init_images"] = data["init_images"]
        payload["denoising_strength"] = data["denoising_strength"]

    if "mask" in data:
        payload["mask"] = data["mask"]
        if "mask_blur" in data:
            payload["mask_blur"] = data["mask_blur"]
        if "inpainting_mask_invert" in data:
            payload["inpainting_mask_invert"] = data["inpainting_mask_invert"]

    jsonData = json.dumps(payload)

    return generateWithPayload(
        jsonData, data["output_path"], data["automatic_url"], endpoint
    )


def generateWithPayload(
    payload, outputDir, url="127.0.0.1:7860", endpoint="/sdapi/v1/txt2img"
):
    print("Sending to Automatic1111 with payload: ", payload)

    conn = http.client.HTTPConnection(url)

    headers = {"Content-Type": "application/json"}

    conn.request("POST", endpoint, payload, headers)
    response = conn.getresponse()

    print(response.status, response.reason)

    decoded = response.read()

    conn.close()

    if response.status != 200:
        print("Error: ", response.reason, decoded)
        return [], {}

    print("Response: ", decoded)
    outputData = json.loads(decoded)

    # assuming i contains the base64 encoded image string

    output_images = []
    info = {}
    if 'info' in outputData:
        info = json.loads(outputData["info"])

    print("info: ", info)

    for i, image in enumerate(outputData.get("images", [outputData['image']] if 'image' in outputData else [])):
        img_str = image  # extract the base64 encoded data from the string

        # convert the base64 encoded data to bytes and create a BytesIO object
        img_bytes = base64.b64decode(img_str)
        img_buffer = BytesIO(img_bytes)

        # default imageName to "output.png" if info["prompt" is empty

        leading_number = files.find_last_leading_number(outputDir)+1

        now = datetime.now()
        imageName = now.strftime("Image_%Y%m%d_%H%M%S")
        if 'all_seeds' in info and 'prompt' in info:
            imageName = '%04d_%d_%s' % (leading_number, info["all_seeds"][min(i, len(info["all_seeds"])-1)], re.sub("[^A-Za-z0-9]", "_", info["prompt"][:50].strip()))
        if imageName == "":
            imageName = "output-image" % leading_number
        # remove any non-alphanumeric characters from the prompt and truncate
        # remove any double underscores
        imageName = imageName.replace("__", "_")
        imageName = imageName + ".png"

        # open the image using PIL's Image module
        img = Image.open(img_buffer)

        output_path = os.path.join(outputDir, imageName)
        output_path = files.create_unique_filename(output_path)
        print("output_path", output_path)

        # if the output directory doesnt exist, create it
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))

        # save the image
        # try:
        #     pngInfo = it.setPngMetadata(img, {'parameters': convertOptionsToA1111Metadata(info, i)})
        # except:
        #     print("Error: Could not set PNG metadata")
        #     pngInfo = None
        #     print(info)
        
        parameters = info['infotexts'][min(i, len(info['infotexts']) - 1)] if 'infotexts' in info else ""
        pngInfo = it.makePngInfo({'parameters':  parameters})
        img.save(output_path, "PNG", pnginfo=pngInfo)
        img.close()

        output_images.append(output_path)

    return output_images, info


def getFromAutomatic1111(endpoint, url="127.0.0.1:7860"):
    try:
        conn = http.client.HTTPConnection(url)
        conn.request("GET", endpoint)
    except:
        print("Error: Could not connect to Automatic1111 at ", url)
        return {}

    response = conn.getresponse()

    if response.status != 200:
        return {}

    # print(response.status, response.reason)
    decoded = response.read().decode()
    data = json.loads(decoded)

    return data


def getModelsFromAutomatic1111(url="127.0.0.1:7860"):
    endpoint = "/sdapi/v1/sd-models"
    return getFromAutomatic1111(endpoint, url)

def getSamplersFromAutomatic1111(url="127.0.0.1:7860"):
    endpoint = "/sdapi/v1/samplers"
    return getFromAutomatic1111(endpoint, url)

# def getControlNetPreprocessorsFromAutomatic1111(url="127.0.0.1:7860"):
#     return ["none", "canny", "depth", "openpose", "segmentation"]

def getControlNetModelsFromAutomatic1111(url="127.0.0.1:7860"):
    endpoint = "/controlnet/model_list"
    return getFromAutomatic1111(endpoint, url)

def getControlNetPreprocessorsFromAutomatic1111(url="127.0.0.1:7860"):
    endpoint = "/controlnet/module_list"
    return getFromAutomatic1111(endpoint, url)

def getOptionsFromAutomatic(url="127.0.0.1:7860"):
    endpoint = "/sdapi/v1/options"
    return getFromAutomatic1111(endpoint, url)


def setModel(model, url="127.0.0.1:7860"):
    endpoint = "/sdapi/v1/options"
    options = getOptionsFromAutomatic(url)

    options["sd_model_checkpoint"] = model["title"]

    data = json.dumps(options)

    conn = http.client.HTTPConnection(url)
    headers = {"Content-Type": "application/json"}

    conn.request("POST", endpoint, data, headers)
    response = conn.getresponse()

    conn.close()

    if response.status != 200:
        print("Error: ", response.reason)
        return False

    return True


def makeCompositeShader():
    shader, sg = rt.makeShader("surfaceShader")
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_composite")

    shader = mc.rename(shader, "cgmCompositeShader")

    # create a layered texture and hook it up to the shader
    layeredTexture = mc.shadingNode("layeredTexture", asTexture=True)
    mc.connectAttr(layeredTexture + ".outColor", shader + ".outColor", force=True)

    return shader, sg


def makeAlphaMatteShader():
    shader, sg = rt.makeShader("surfaceShader")
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_alphaMatte")

    shader = mc.rename(shader, "cgmAlphaMatteShader")

    # create a layered texture and hook it up to the shader
    layeredTexture = mc.shadingNode("layeredTexture", asTexture=True)
    mc.connectAttr(layeredTexture + ".outColor", shader + ".outColor", force=True)

    return shader, sg


def makeMergedShader():
    shader, sg = rt.makeShader("surfaceShader")
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore("cgmShader", "sd_merged")

    shader = mc.rename(shader, "cgmMergedShader")

    return shader, sg


def getModelsFromAutomatic(url="127.0.0.1:7860"):
    conn = http.client.HTTPConnection(url)
    endpoint = "/sdapi/v1/sd-models"

    try:
        conn.request("GET", endpoint)
    except:
        print("Error: Could not connect to Automatic at ", url)
        return []

    response = conn.getresponse()

    print(response.status, response.reason)

    if response.status != 200:
        return []

    decoded = response.read().decode()
    models = json.loads(decoded)

    conn.close()

    return models


def load_settings_from_image(fileNode):
    if not mc.objExists("%s.cgmImageProjectionData" % fileNode):
        return

    data = json.loads(mc.getAttr("%s.cgmImageProjectionData" % fileNode))
    return data


def encode_pil_to_base64(image, format="PNG", jpegQuality=75):
    with BytesIO() as output_bytes:
        if format.lower() == "png":
            use_metadata = False
            metadata = PngImagePlugin.PngInfo()
            for key, value in image.info.items():
                if isinstance(key, str) and isinstance(value, str):
                    metadata.add_text(key, value)
                    use_metadata = True
            image.save(
                output_bytes,
                format="PNG",
                pnginfo=(metadata if use_metadata else None),
                quality=jpegQuality,
            )

        elif format.lower() in ("jpg", "jpeg", "webp"):
            if format.lower() in ("jpg", "jpeg"):
                image.save(output_bytes, format="JPEG", quality=jpegQuality)
            else:
                image.save(output_bytes, format="WEBP", quality=jpegQuality)

        else:
            print("Invalid image format")

        bytes_data = output_bytes.getvalue()

    return base64.b64encode(bytes_data)


def mergeCompositeShaderToImage(compositeShader, mergedShader):
    imagePath = PROJECT.getImagePath()

    # Get the current time before running the code
    startTime = time.time()

    layeredTexture = mc.listConnections(
        "%s.outColor" % compositeShader, type="layeredTexture"
    )[0]

    # Your code snippet
    images_data = rt.getLayeredTextureImages(layeredTexture)
    images_data.reverse()
    result_image = rt.overlay_images(images_data)

    result_image = it.expand_uv_borders(result_image)

    # Get the current time after running the code
    endTime = time.time()

    # Calculate the time difference
    timeDifference = endTime - startTime

    # Print the time before, after, and the time difference
    print("Start time: ", startTime)
    print("End time: ", endTime)
    print("Time difference: ", timeDifference)

    mergedPath = files.create_unique_filename(
        os.path.join(imagePath, f"{compositeShader}_merged.png")
    )
    result_image.save(mergedPath)

    fileNode = None

    messageConnections = mc.listConnections(
        f"{layeredTexture}.message", type="file", p=True
    )
    if messageConnections:
        for messageConnection in messageConnections:
            fileNode, plug = messageConnection.split(".")
            if plug == "cgmCompositeTextureSource":
                layeredTextureConnection = mc.listConnections(
                    f"{fileNode}.outColor", type="layeredTexture"
                )
                if layeredTextureConnection:
                    print("merging to existing file node")
                    mc.setAttr(
                        "%s.fileTextureName" % fileNode, mergedPath, type="string"
                    )
                    mc.connectAttr(
                        layeredTextureConnection[0] + ".outColor",
                        "%s.outColor" % compositeShader,
                        force=True,
                    )
                    return fileNode

    # create a file node and load the image
    fileNode = mc.shadingNode("file", name=f"{compositeShader}_merged", asUtility=True)
    mc.setAttr("%s.fileTextureName" % fileNode, mergedPath, type="string")

    # create a place2dTexture node and hook it up to the file node
    place2dTexture = mc.shadingNode("place2dTexture", asUtility=True)
    mc.connectAttr(place2dTexture + ".coverage", fileNode + ".coverage", force=True)
    mc.connectAttr(
        place2dTexture + ".translateFrame", fileNode + ".translateFrame", force=True
    )
    mc.connectAttr(
        place2dTexture + ".rotateFrame", fileNode + ".rotateFrame", force=True
    )
    mc.connectAttr(place2dTexture + ".mirrorU", fileNode + ".mirrorU", force=True)
    mc.connectAttr(place2dTexture + ".mirrorV", fileNode + ".mirrorV", force=True)
    mc.connectAttr(place2dTexture + ".stagger", fileNode + ".stagger", force=True)
    mc.connectAttr(place2dTexture + ".wrapU", fileNode + ".wrapU", force=True)
    mc.connectAttr(place2dTexture + ".wrapV", fileNode + ".wrapV", force=True)
    mc.connectAttr(place2dTexture + ".repeatUV", fileNode + ".repeatUV", force=True)
    mc.connectAttr(place2dTexture + ".offset", fileNode + ".offset", force=True)
    mc.connectAttr(place2dTexture + ".rotateUV", fileNode + ".rotateUV", force=True)
    mc.connectAttr(place2dTexture + ".noiseUV", fileNode + ".noiseUV", force=True)
    mc.connectAttr(
        place2dTexture + ".vertexUvOne", fileNode + ".vertexUvOne", force=True
    )
    mc.connectAttr(
        place2dTexture + ".vertexUvTwo", fileNode + ".vertexUvTwo", force=True
    )
    mc.connectAttr(
        place2dTexture + ".vertexUvThree", fileNode + ".vertexUvThree", force=True
    )
    mc.connectAttr(
        place2dTexture + ".vertexCameraOne", fileNode + ".vertexCameraOne", force=True
    )
    mc.connectAttr(place2dTexture + ".outUV", fileNode + ".uv", force=True)
    mc.connectAttr(
        place2dTexture + ".outUvFilterSize", fileNode + ".uvFilterSize", force=True
    )

    # hook the file node up to the shader
    mc.connectAttr(fileNode + ".outColor", mergedShader + ".outColor", force=True)

    newLayeredTexture = mc.shadingNode("layeredTexture", asTexture=True)
    mc.connectAttr(
        newLayeredTexture + ".outColor", compositeShader + ".outColor", force=True
    )

    # connect fileNode to the new layered texture
    mc.connectAttr(
        fileNode + ".outColor", newLayeredTexture + ".inputs[0].color", force=True
    )

    # add a message attribute to the file node and connect the original layered texture to it
    mc.addAttr(fileNode, longName="cgmCompositeTextureSource", dataType="string")
    mc.connectAttr(
        layeredTexture + ".message", fileNode + ".cgmCompositeTextureSource", force=True
    )

    return fileNode

def clean_and_reorder_layeredTexture(layeredTexture):
    # Store current attributes and connections
    connectionList = mc.listConnections(f'{layeredTexture}.inputs', p=True, connections=True) or []
    connections = {(src, dest) for src, dest in zip(connectionList[::2], connectionList[1::2])}

    # Remove all current attributes
    multiAttrs = mc.listAttr(f'{layeredTexture}.inputs', multi=True) or []
    attr_indices = {x.split('[')[1].split(']')[0] for x in multiAttrs if '[' in x and ']' in x}
    for attr_index in attr_indices:
        mc.removeMultiInstance(f'{layeredTexture}.inputs[{attr_index}]', b=True)

    # Remap attributes
    index_grouped = defaultdict(list)
    remapped_connections = set()
  
    for src, dest in connections:
        index = src.split('[')[1].split(']')[0]
        index_grouped[index].append((src, dest))
  
    new_index = 0
    for _, pairs in index_grouped.items():
        for src, dest in pairs:
            remapped_src = f'{src.split(".inputs")[0]}.inputs[{new_index}].{src.split(".")[-1]}'
            remapped_connections.add((remapped_src, dest))
        new_index += 1

    # Reconnect the attributes
    for remapped_src, dest in remapped_connections:
        mc.connectAttr(dest, remapped_src, f=True)

# def makeImagePlane(imagePath, info):

#     shader, sg = makeCompositeShader()

#     plane, shader = rt.makeImagePlane(imagePath, info, shader=shader)

#     shape = mc.listRelatives(plane, shapes=True)[0]

#     mc.addAttr(shape, longName='cgmCompositeMaterial', attributeType='message')
#     mc.connectAttr(f'{shader}.message', f'{shape}.cgmCompositeMaterial')

#     initializeProjectionMeshes([shape])

#     return plane, shader


def makeXYZShader(mesh=None):
    shader, sg = rt.makeXYZShader()

    if mesh and mc.objExists(mesh):
        bbox = mc.exactWorldBoundingBox(mesh)

        mc.setAttr(shader + ".bboxMin", bbox[0], bbox[1], bbox[2], type="double3")
        mc.setAttr(shader + ".bboxMax", bbox[3], bbox[4], bbox[5], type="double3")

    return shader, sg


def initializeProjectionMeshes(meshes):
    _str_func = "initiateProjectionMeshes"
    log.debug("|{0}| >> ...".format(_str_func))

    if not meshes:
        return

    materialData = {
        "cgmCompositeMaterial": makeCompositeShader,
        "cgmAlphaMatteMaterial": makeAlphaMatteShader,
        "cgmMergedMaterial": makeMergedShader,
        "cgmXYZMaterial": makeXYZShader,
    }

    for mesh in meshes:
        for attr, func in materialData.items():
            if not mc.objExists(f"{mesh}.{attr}"):
                mc.addAttr(mesh, longName=attr, attributeType="message")

            # if there is no connection to the attribute, create a new shader and connect it
            if not mc.listConnections(f"{mesh}.{attr}"):
                shader, sg = func()
                mc.connectAttr(f"{shader}.message", f"{mesh}.{attr}")
                shader = mc.rename(shader, f"{mesh}_{shader}")


def validateProjectionMesh(obj):
    attrs = [
        "cgmCompositeMaterial",
        "cgmAlphaMatteMaterial",
        "cgmMergedMaterial",
        "cgmXYZMaterial",
    ]

    for attr in attrs:
        if not mc.objExists(f"{obj}.{attr}"):
            return False

        if not mc.listConnections(f"{obj}.{attr}"):
            return False

    return True


def copyRemapColorValues(remapColorNode):
    # store remap color remap curves in temporary optionVar as a json string
    # this is so we can copy and paste remap color nodes between maya sessions
    # without losing the remap curves

    # get the remap curves
    remapCopy = {}

    for color in ["red", "green", "blue"]:
        remapCopy[color] = {}

        for attr in mc.listAttr("%s.%s" % (remapColorNode, color), multi=True):
            if "." in attr:
                remapCopy[color][attr] = mc.getAttr("%s.%s" % (remapColorNode, attr))
            else:
                remapCopy[color][attr] = mc.getAttr("%s.%s" % (remapColorNode, attr))[0]

    return remapCopy


def pasteRemapColorValues(remapColorNode, valueDict):
    # paste the remap curves from the temporary optionVar
    # this is so we can copy and paste remap color nodes between maya sessions
    # without losing the remap curves

    for color in ["red", "green", "blue"]:
        for attr, value in valueDict[color].items():
            if "." in attr:
                mc.setAttr("%s.%s" % (remapColorNode, attr), value)
            else:
                mc.setAttr(
                    "%s.%s" % (remapColorNode, attr),
                    value[0],
                    value[1],
                    value[2],
                    type="double3",
                )

    # iterate through attr list again and delete any attrs that are not in the valueDict
    for color in ["red", "green", "blue"]:
        for attr in mc.listAttr("%s.%s" % (remapColorNode, color), multi=True):
            if attr not in valueDict[color]:
                if not "." in attr:
                    mc.removeMultiInstance("%s.%s" % (remapColorNode, attr), b=True)

    return True


def guess_depth_min_max(source, targets):
    """
    quick call to guess the min max values for the depth settings of GrAIBox
    source: cam most likey
    targets: targets to check the size of and cast at


    returns: (min,max)
    """
    import cgm.core.lib.distance_utils as DIST
    import cgm.core.lib.rayCaster as RAYS

    pCam = POS.get(source)  # ...get cam pos

    bb_minMax = DIST.get_min_max_bbPoints_distances(
        source, targets
    )  # ...get min max distances from bounding box of targets
    
    
    p_cast = RAYS.get_cast_pos(
        source, "z-", "far", mark=False, maxDistance=bb_minMax[1] * 2.0
    )  # ...raycast for alternative max. max dist 2x the bounding box to be safe
    if not p_cast:
        return bb_minMax[0], bb_minMax[1]
        
    d_cast = DIST.get_distance_between_points(pCam, p_cast)  # ...cast dist

    # pprint.pprint(vars())

    if bb_minMax[1] > d_cast:
        d_max = bb_minMax[1]
    else:
        d_max = d_cast

    return bb_minMax[0], d_max

def guess_depth_min_max2(source, targets, debug=False):
    boundingBox = mc.exactWorldBoundingBox(targets)
    cam = cgmMeta.asMeta(source)

    pCam = POS.get(source, asEuclid=True)  # ...get cam pos
    fwd = (CAM.screenToWorld((.5,.5), 1.0, asEuclid=True) - pCam).normalized()

    # separate bounding box sides into 6 planes
    planePoints = POS.get_bb_points(targets, shapes=True, asEuclid=True)
    planeNormals = [EUCLID.Vector3(-1,0,0), EUCLID.Vector3(1,0,0), EUCLID.Vector3(0,1,0), EUCLID.Vector3(0,-1,0), EUCLID.Vector3(0,0,-1), EUCLID.Vector3(0,0,1)]

    if debug:
        for point in planePoints:
            mc.xform(mc.spaceLocator()[0], ws=True, t=point)

    minDist = math.inf
    maxDist = -math.inf

    for i, point in enumerate(planePoints):
        localPos = TRANS.transformInversePoint(cam, point)
        dist = max(-localPos.z, 0)
        if dist < minDist:
            minDist = dist
        if dist > maxDist:
            maxDist = dist

    return minDist, maxDist

def clean_cgm_sd_tags(objs=[]):
    if not objs:
        ml_objs = cgmMeta.asMeta(sl=1)
    else:
        ml_objs = cgmMeta.asMeta(objs)
        
    #Get our shapes
    ml_shapes = []
    for mObj in ml_objs:
        if not cgmMeta.VALID.is_shape(mObj.mNode):
            ml_shapes.extend(mObj.getShapes(asMeta=1))
        else:
            ml_shapes.append(mObj)
      
    for mShape in ml_shapes:
        for a in ['AlphaMatteMaterial','CompositeMaterial','MergedMaterial','XYZMaterial']:
            _a = 'cgm{}'.format(a)
            if mShape.hasAttr(_a):
                print("Removing attr: {}.{}".format(mShape.p_nameShort, _a))
                mShape.delAttr(_a)

######################################################################
#>> Metadata
######################################################################
   
def parametersToDict(s):
    """
    Parse the parameters string from the A1111 metadata block into a dictionary.

    Parameters
    ----------
    s : str
        The parameter string to parse.

    Returns
    -------
    dict
        The parsed parameters as a dictionary.
    """
    # Initialize an empty dictionary to store the key-value pairs
    result = {}

    # Special handling for ControlNet blocks
    control_net_blocks = []

    # Separate ControlNet blocks from the rest of the parameters
    while 'ControlNet' in s:
        control_net_start = s.index('ControlNet')
        control_net_end = s.index(')"') + 2  # 2 for ')"'
        control_net_blocks.append(s[control_net_start:control_net_end])
        s = s[:control_net_start] + s[control_net_end+1:]

    # Separate the prompt from the rest of the string
    lines = s.split('\n')
    s = lines.pop()
    prompts = '\n'.join([x.strip() for x in lines]).split('Negative prompt:')
    result['Prompt'] = prompts[0].strip()
    if len(prompts) > 1:
        result['Negative prompt'] = prompts[-1].strip()

    # Split the string into parts
    parts = [part.strip() for part in s.split(', ') if part.strip()]
    
    print("Parts:\n",parts, "\n\ns:\n", s)
    
    # Process the remaining parts
    for part in parts:
        try:
            # Split the part into key and value
            key, value = part.split(': ', 1)

            # Try to convert value into int or float or keep as string
            try:
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass

            # Add the key and value to the result dictionary
            result[key] = value
        except ValueError as e:
            print(f"Error processing part '{part}': {e}")

    # Process ControlNet blocks
    for block in control_net_blocks:
        try:
            # Split the block into key and value
            key, value = block.split(': ', 1)
            value = value.strip('"')  # Remove the quotes

            # Initialize an empty sub-dictionary
            controlNet_dict = {}

            # Split the value into sub-parts, avoiding breaking tuples
            sub_parts = [sub_part.strip() for sub_part in re.split(r', (?![^()]*\))', value) if sub_part.strip()]

            # Process each sub-part
            for sub_part in sub_parts:
                try:
                    # Split the sub-part into sub-key and sub-value
                    sub_key, sub_value = sub_part.split(': ', 1)

                    # Try to convert sub-value into int or float or tuple or keep as string
                    try:
                        if '(' in sub_value and ')' in sub_value:
                            sub_value = tuple(map(float if '.' in sub_value else int, sub_value.strip('()').split(', ')))
                        elif '.' in sub_value:
                            sub_value = float(sub_value)
                        else:
                            sub_value = int(sub_value)
                    except ValueError:
                        if sub_value == 'False':
                            sub_value = False
                        elif sub_value == 'True':
                            sub_value = True

                    # Add the sub-key and sub-value to the sub-dictionary
                    controlNet_dict[sub_key] = sub_value
                except ValueError as e:
                    print(f"Error processing sub_part '{sub_part}': {e}")

            # Add the key and the sub-dictionary to the result dictionary
            result[key] = controlNet_dict
        except ValueError as e:
            print(f"Error processing block '{block}': {e}")

    return result

def convertOptionsToA1111Metadata(data, index=0):
    """
    Convert the options dictionary to a string that can be used as the A1111 metadata.

    Parameters
    ----------
    options : dict
        The options dictionary to convert.

    Returns
    -------
    str
        The options dictionary converted to a string that can be used as the A1111 metadata.
    """

    ignore = ['prompt', 'all_prompts', 'all_subseeds', 'negative_prompt', 'all_negative_prompts', 'extra_generation_params', 'all_seeds', 'seed']

    s = ""

    # Add the prompt
    s += f"{data['all_prompts'][min(index, len(data['all_prompts'])-1)]}\n"

    # Add the negative prompt
    if 'negative_prompt' in data:
        s += f"Negative prompt: {data['all_negative_prompts'][min(index, len(data['all_negative_prompts'])-1)]}\n"

    # Add the parameters
    for key, value in data.items():
        if key in ['prompt', 'negative_prompt']:
            continue    # Skip the prompt and negative prompt
        if key == 'extra_generation_params':
            for sub_key, sub_value in value.items():
                # convert sub_value dict to string
                sub_value = str(sub_value)
                s += f"{sub_key}: \"{sub_value}\", "
        if key == 'all_seeds':
            s += f"Seed: {value[min(index, len(value)-1)]}, "
        else:
            if key in ignore:
                continue
            s += f"{key.replace('_', ' ').capitalize()}: {value}, "

    return s

def getMeshMaterial(mesh, materialType):
    _str_func = 'getMeshMaterial'

    attrs = {
        "composite": "cgmCompositeMaterial",
        "alphaMatte": "cgmAlphaMatteMaterial",
        "merged": "cgmMergedMaterial",
        "xyz": "cgmXYZMaterial",
    }
    if materialType not in attrs:
        log.error(
            "|{0}| >> Invalid material type {1}.".format(_str_func, materialType)
        )
        return None

    attr = attrs[materialType]
    if not mc.objExists(mesh + "." + attr):
        log.error(
            "|{0}| >> Mesh doesn't have attribute {1}.".format(_str_func, attr)
        )
        return None

    connections = mc.listConnections(mesh + "." + attr)[0]
    if not connections:
        log.error(
            "|{0}| >> Mesh doesn't have connected material {1}.".format(
                _str_func, attr
            )
        )
        return None

    return connections

def bakeProjection(meshes, projectionShader, alphaShader, additionalImageProjectionData={}):
    if not isinstance(additionalImageProjectionData, dict):
        additionalImageProjectionData = {}
    
    for mesh in meshes:
        bakedImage = rt.bakeProjection(projectionShader, mesh)
        bakedAlpha = rt.bakeProjection(alphaShader, mesh)

        mFile = cgmMeta.asMeta(bakedImage)

        projection = mc.listConnections(projectionShader, type="projection")
        if projection:
            projection = projection[0]
            projectionFile = mc.listConnections(f"{projection}.image")
            if projectionFile:
                mFile.doStore(
                    "cgmSourceProjectionImage",
                    mc.getAttr(f"{projectionFile[0]}.fileTextureName"),
                )

                cgmImageProjectionData = json.loads(mc.getAttr(f"{projectionFile[0]}.cgmImageProjectionData")) or {}
                log.debug(f"Found cgmImageProjectionData: {cgmImageProjectionData}")
                
                cgmImageProjectionData.update(additionalImageProjectionData)

                mFile.doStore(
                    "cgmImageProjectionData",
                    json.dumps(cgmImageProjectionData),
                )

        compositeShader = getMeshMaterial(mesh, "composite")
        alphaMatteShader = getMeshMaterial(mesh, "alphaMatte")

        rt.addImageToCompositeShader(compositeShader, bakedImage, bakedAlpha)
        rt.updateAlphaMatteShader(alphaMatteShader, compositeShader)
