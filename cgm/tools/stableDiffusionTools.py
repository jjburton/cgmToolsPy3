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

import re

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
    conn = http.client.HTTPConnection(url)
    conn.request('GET', endpoint)

    response = conn.getresponse()

    if(response.status != 200):
        return []
    
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

def makeProjectionShader(camera):
    shader, sg = rt.makeProjectionShader(camera)
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_projection')

    shader = mc.rename(shader, 'cgmProjectionShader')

    return shader, sg

def makeAlphaShader(camera):
    shader, sg = rt.makeAlphaProjectionShader(camera)
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_alpha')

    shader = mc.rename(shader, 'cgmAlphaProjectionShader')

    return shader, sg

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

def makeDepthShader():
    shader, sg = rt.makeDepthShader()
    mShader = cgmMeta.asMeta(shader)
    mShader.doStore('cgmShader','sd_depth')

    shader = mc.rename(shader, 'cgmDepthShader')

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

    conn.request('GET', endpoint)

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

