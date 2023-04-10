import maya.cmds as mc
import http.client
import json
from io import BytesIO
import os

import base64
from PIL import Image, PngImagePlugin

from cgm.tools import renderTools as rt
from cgm.core import cgm_Meta as cgmMeta
from cgm.lib import files
import cgm.core.tools.Project as PROJECT

import re
import time

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# adjusts the local position of a mesh based on the R value of a texture
# useful for creating a z-depth push effect
# usage:
# adjust_position_based_on_texture("pPlane1", "file1", 800, [0,0,1], False)
def adjustPositionBasedOnTexture(mesh_name, texture_name, z_depth, axis, invert = False):
    # Get the texture file path
    texture_path = mc.getAttr(texture_name + ".fileTextureName")

    # Get the width and height of the texture image
    texture_width = mc.getAttr(texture_name + ".outSizeX")
    texture_height = mc.getAttr(texture_name + ".outSizeY")

    # Loop through each vertex and adjust the z position based on the R value of the texture at the corresponding UV coordinate
    verts = mc.ls(mesh_name + ".vtx[*]", flatten=True)
    for vtx in mc.ls(mesh_name + ".vtx[*]", flatten=True):
        # Get the UV coordinate of the vertex
        uv = mc.polyEditUV(mc.polyListComponentConversion(vtx, fv=True, tuv=True)[0], u=True, v=True, query=True)
        
        # Convert UV coordinates to pixel coordinates
        pixel_u = int(uv[0] * texture_width)
        pixel_v = int(uv[1] * texture_height)

        # Get the R value of the texture at the corresponding pixel
        r_value = mc.colorAtPoint(texture_name, o="RGB", u=uv[0], v=uv[1])[0]
        if invert:
            r_value = 1.0-r_value
        # Adjust the z position of the vertex based on the R value and z-depth parameter
        mc.move(r_value * z_depth * axis[0], r_value * z_depth* axis[1], r_value * z_depth* axis[2], vtx, relative=True, os=True)

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
    payload = {
        "prompt": data['prompt'],
        "negative_prompt": data['negative_prompt'],
        "steps": data['sampling_steps'],
        "seed":data['seed'],
        "width":data['width'],
        "height":data['height'],
        "sampler_index":data['sampling_method'],
        "batch_size":data['batch_size'],
        "n_iter":data['batch_count'],
        "cfg_scale":data['cfg_scale'],
    }

    if data['control_net_enabled']:
        payload["alwayson_scripts"] = {
            "controlnet": {
                "args": [
                    {
                    "lowvram": data['control_net_low_v_ram'],
                    "module": data['control_net_preprocessor'],
                    "model": data['control_net_model'],
                    "weight": data['control_net_weight'],
                    "resize_mode": "Scale to Fit (Inner Fit)",
                    "input_image": data['control_net_image'],
                    "processor_res": 512,
                    "threshold_a": 100,
                    "threshold_b": 255,
                    "guidance_start": data['control_net_guidance_start'],
                    "guidance_end": data['control_net_guidance_end'],
                    "guessmode": False,
                    }
            ]}
        }

    endpoint = '/sdapi/v1/txt2img'

    if('init_images' in data):
        endpoint = '/sdapi/v1/img2img'
        payload['init_images'] = data['init_images']
        payload['denoising_strength'] = data['denoising_strength']

    if('mask' in data):
        payload['mask'] = data['mask']
        if 'mask_blur' in data:
            payload['mask_blur'] = data['mask_blur']
        if 'inpainting_mask_invert' in data:
            payload['inpainting_mask_invert'] = data['inpainting_mask_invert']

    conn = http.client.HTTPConnection(data['automatic_url'])
    headers = {'Content-Type': 'application/json'}
    jsonData = json.dumps(payload)

    print("Sending to Automatic1111 with payload: ", jsonData)

    conn.request('POST', endpoint, jsonData, headers)
    response = conn.getresponse()

    print(response.status, response.reason)

    decoded = response.read()

    conn.close()

    if(response.status != 200):
        print("Error: ", response.reason, decoded)
        return [], {}

    print("Response: ", decoded)
    outputData = json.loads(decoded) 

    # assuming i contains the base64 encoded image string

    output_images = []
    info = json.loads(outputData['info'])

    for i, image in enumerate(outputData['images']):
        img_str = image  # extract the base64 encoded data from the string

        # convert the base64 encoded data to bytes and create a BytesIO object
        img_bytes = base64.b64decode(img_str)
        img_buffer = BytesIO(img_bytes)

        imageName = re.sub("[^A-Za-z]", "_", info['prompt'])[:60]
        imageName = imageName.replace('__', '_')
        imageName = imageName + ".png"

        # open the image using PIL's Image module
        img = Image.open(img_buffer)

        output_path = os.path.join(data['output_path'], imageName)
        output_path = files.create_unique_filename(output_path)
        print("output_path", output_path)

        # if the output directory doesnt exist, create it
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))

        img.save(output_path)
        output_images.append(output_path)

    return output_images, info

def getFromAutomatic1111(endpoint, url = '127.0.0.1:7860'):
    try:
        conn = http.client.HTTPConnection(url)
        conn.request('GET', endpoint)
    except:
        print("Error: Could not connect to Automatic1111 at ", url)
        return {}

    response = conn.getresponse()

    if(response.status != 200):
        return {}
    
    #print(response.status, response.reason)
    decoded = response.read().decode()
    data = json.loads(decoded)

    return data

def getModelsFromAutomatic1111(url = '127.0.0.1:7860'):
    endpoint = '/sdapi/v1/sd-models'
    return getFromAutomatic1111(endpoint, url)

def getSamplersFromAutomatic1111(url = '127.0.0.1:7860'):
    endpoint = '/sdapi/v1/samplers'
    return getFromAutomatic1111(endpoint, url)

def getControlNetPreprocessorsFromAutomatic1111(url = '127.0.0.1:7860'):
    return ['none', 'canny', 'depth', 'openpose', 'segmentation']

def getControlNetModelsFromAutomatic1111(url = '127.0.0.1:7860'):
    endpoint = '/controlnet/model_list'
    return getFromAutomatic1111(endpoint, url)

def getOptionsFromAutomatic(url = '127.0.0.1:7860'):
    endpoint = '/sdapi/v1/options'
    return getFromAutomatic1111(endpoint, url)

def setModel(model, url = '127.0.0.1:7860'):
    endpoint = '/sdapi/v1/options'
    options = getOptionsFromAutomatic(url)

    options['sd_model_checkpoint'] = model['title']
    
    data = json.dumps(options)

    conn = http.client.HTTPConnection(url)
    headers = {'Content-Type': 'application/json'}

    conn.request('POST', endpoint, data, headers)
    response = conn.getresponse()

    conn.close()

    if(response.status != 200):
        print("Error: ", response.reason)
        return False
    
    return True

def makeCompositeShader():
    shader, sg = rt.makeShader('surfaceShader')
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_composite')

    shader = mc.rename(shader, 'cgmCompositeShader')

    # create a layered texture and hook it up to the shader
    layeredTexture = mc.shadingNode('layeredTexture', asTexture=True)
    mc.connectAttr(layeredTexture + ".outColor", shader + ".outColor", force=True)

    return shader, sg

def makeAlphaMatteShader():
    shader, sg = rt.makeShader('surfaceShader')
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_alphaMatte')

    shader = mc.rename(shader, 'cgmAlphaMatteShader')

    # create a layered texture and hook it up to the shader
    layeredTexture = mc.shadingNode('layeredTexture', asTexture=True)
    mc.connectAttr(layeredTexture + ".outColor", shader + ".outColor", force=True)

    return shader, sg

def makeMergedShader():
    shader, sg = rt.makeShader('surfaceShader')
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_merged')

    shader = mc.rename(shader, 'cgmMergedShader')

    return shader, sg

def getModelsFromAutomatic(url = '127.0.0.1:7860'):
    conn = http.client.HTTPConnection(url)
    endpoint = '/sdapi/v1/sd-models'

    try:
        conn.request('GET', endpoint)
    except:
        print("Error: Could not connect to Automatic at ", url)
        return []

    response = conn.getresponse()

    print(response.status, response.reason)

    if(response.status != 200):
        return []
    
    decoded = response.read().decode()
    models = json.loads(decoded)

    conn.close()

    return models

def load_settings_from_image(fileNode):
    if not mc.objExists('%s.cgmImageProjectionData' % fileNode):
        return
    
    data = json.loads(mc.getAttr('%s.cgmImageProjectionData' % fileNode))
    return data

def encode_pil_to_base64(image, format = 'PNG', jpegQuality = 75):
    with BytesIO() as output_bytes:

        if format.lower() == 'png':
            use_metadata = False
            metadata = PngImagePlugin.PngInfo()
            for key, value in image.info.items():
                if isinstance(key, str) and isinstance(value, str):
                    metadata.add_text(key, value)
                    use_metadata = True
            image.save(output_bytes, format="PNG", pnginfo=(metadata if use_metadata else None), quality=jpegQuality)

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

    layeredTexture = mc.listConnections('%s.outColor' % compositeShader, type = 'layeredTexture')[0]

    # Your code snippet
    images_data = rt.getLayeredTextureImages(layeredTexture)
    images_data.reverse()
    result_image = rt.overlay_images(images_data)

    # Get the current time after running the code
    endTime = time.time()

    # Calculate the time difference
    timeDifference = endTime - startTime

    # Print the time before, after, and the time difference
    print("Start time: ", startTime)
    print("End time: ", endTime)
    print("Time difference: ", timeDifference)

    mergedPath = files.create_unique_filename(os.path.join(imagePath, f'{compositeShader}_merged.png'))
    result_image.save(mergedPath)

    fileNode = None

    messageConnections = mc.listConnections(f'{layeredTexture}.message', type="file", p=True)
    if(messageConnections):
        for messageConnection in messageConnections:
            fileNode, plug = messageConnection.split('.')
            if plug == 'cgmCompositeTextureSource':
                layeredTextureConnection = mc.listConnections(f'{fileNode}.outColor', type="layeredTexture")
                if layeredTextureConnection:
                    print("merging to existing file node")
                    mc.setAttr('%s.fileTextureName' % fileNode, os.path.join(imagePath, f'{compositeShader}_merged.png'), type = 'string')
                    mc.connectAttr(layeredTextureConnection[0] + ".outColor", '%s.outColor' % compositeShader, force=True)
                    return fileNode

    # create a file node and load the image
    fileNode = mc.shadingNode('file', name = f'{compositeShader}_merged', asUtility=True)
    mc.setAttr('%s.fileTextureName' % fileNode, os.path.join(imagePath, f'{compositeShader}_merged.png'), type = 'string')

    # create a place2dTexture node and hook it up to the file node
    place2dTexture = mc.shadingNode('place2dTexture', asUtility=True)
    mc.connectAttr(place2dTexture + ".coverage", fileNode + ".coverage", force=True)
    mc.connectAttr(place2dTexture + ".translateFrame", fileNode + ".translateFrame", force=True)
    mc.connectAttr(place2dTexture + ".rotateFrame", fileNode + ".rotateFrame", force=True)
    mc.connectAttr(place2dTexture + ".mirrorU", fileNode + ".mirrorU", force=True)
    mc.connectAttr(place2dTexture + ".mirrorV", fileNode + ".mirrorV", force=True)
    mc.connectAttr(place2dTexture + ".stagger", fileNode + ".stagger", force=True)
    mc.connectAttr(place2dTexture + ".wrapU", fileNode + ".wrapU", force=True)
    mc.connectAttr(place2dTexture + ".wrapV", fileNode + ".wrapV", force=True)
    mc.connectAttr(place2dTexture + ".repeatUV", fileNode + ".repeatUV", force=True)
    mc.connectAttr(place2dTexture + ".offset", fileNode + ".offset", force=True)
    mc.connectAttr(place2dTexture + ".rotateUV", fileNode + ".rotateUV", force=True)
    mc.connectAttr(place2dTexture + ".noiseUV", fileNode + ".noiseUV", force=True)
    mc.connectAttr(place2dTexture + ".vertexUvOne", fileNode + ".vertexUvOne", force=True)
    mc.connectAttr(place2dTexture + ".vertexUvTwo", fileNode + ".vertexUvTwo", force=True)
    mc.connectAttr(place2dTexture + ".vertexUvThree", fileNode + ".vertexUvThree", force=True)
    mc.connectAttr(place2dTexture + ".vertexCameraOne", fileNode + ".vertexCameraOne", force=True)
    mc.connectAttr(place2dTexture + ".outUV", fileNode + ".uv", force=True)
    mc.connectAttr(place2dTexture + ".outUvFilterSize", fileNode + ".uvFilterSize", force=True)

    # hook the file node up to the shader
    mc.connectAttr(fileNode + ".outColor", mergedShader + ".outColor", force=True)

    newLayeredTexture = mc.shadingNode('layeredTexture', asTexture=True)
    mc.connectAttr(newLayeredTexture + ".outColor", compositeShader + ".outColor", force=True)

    # connect fileNode to the new layered texture
    mc.connectAttr(fileNode + ".outColor", newLayeredTexture + ".inputs[0].color", force=True)

    # add a message attribute to the file node and connect the original layered texture to it
    mc.addAttr(fileNode, longName='cgmCompositeTextureSource', dataType='string')
    mc.connectAttr(layeredTexture + ".message", fileNode + ".cgmCompositeTextureSource", force=True)


    return fileNode

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

        mc.setAttr(shader + '.bboxMin', bbox[0], bbox[1], bbox[2], type='double3')
        mc.setAttr(shader + '.bboxMax', bbox[3], bbox[4], bbox[5], type='double3')
    
    return shader, sg

def initializeProjectionMeshes(meshes):
    _str_func = 'initiateProjectionMeshes'
    log.debug("|{0}| >> ...".format(_str_func))

    if not meshes:
        return

    materialData = {'cgmCompositeMaterial':makeCompositeShader,
                    'cgmAlphaMatteMaterial':makeAlphaMatteShader,
                    'cgmMergedMaterial':makeMergedShader,
                    'cgmXYZMaterial':makeXYZShader}

    for mesh in meshes:
        for attr, func in materialData.items():
            if not mc.objExists(f'{mesh}.{attr}'):
                mc.addAttr(mesh, longName=attr, attributeType='message')
            
            # if there is no connection to the attribute, create a new shader and connect it
            if not mc.listConnections(f'{mesh}.{attr}'):
                shader, sg = func()
                mc.connectAttr(f'{shader}.message', f'{mesh}.{attr}')
                shader = mc.rename(shader, f'{mesh}_{shader}')

def validateProjectionMesh(obj):

    attrs = ['cgmCompositeMaterial', 'cgmAlphaMatteMaterial', 'cgmMergedMaterial', 'cgmXYZMaterial']

    for attr in attrs:
        if not mc.objExists(f'{obj}.{attr}'):
            return False
        
        if not mc.listConnections(f'{obj}.{attr}'):
            return False
    
    return True