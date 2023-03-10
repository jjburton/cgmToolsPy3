import maya.cmds as mc
import http.client
import json
from io import BytesIO

import base64
from PIL import Image

# adjusts the local position of a mesh based on the R value of a texture
# useful for creating a z-depth push effect
# usage:
# adjust_position_based_on_texture("pPlane1", "file1", 800, [0,0,1], False)
def adjust_position_based_on_texture(mesh_name, texture_name, z_depth, axis, invert = False):
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

def get_image_from_automatic1111(prompt = "maltese puppy", negative_prompt="", steps = 5, seed = -1, size=(512, 512), model="deliberate_v2", url = '127.0.0.1:7860'):
    payload = {
        "prompt": prompt,
        "steps": steps,
        "seed":seed,
        "width":size[0],
        "height":size[1],
    }

    endpoint = '/sdapi/v1/txt2img'

    conn = http.client.HTTPConnection(url)
    headers = {'Content-Type': 'application/json'}
    data = json.dumps(payload)

    conn.request('POST', endpoint, data, headers)
    response = conn.getresponse()

    print(response.status, response.reason)
    decoded = response.read().decode()
    data = json.loads(decoded)
    conn.close()


    # assuming i contains the base64 encoded image string
    img_str = data['images'][0]  # extract the base64 encoded data from the string

    # convert the base64 encoded data to bytes and create a BytesIO object
    img_bytes = base64.b64decode(img_str)
    img_buffer = BytesIO(img_bytes)

    # open the image using PIL's Image module
    img = Image.open(img_buffer)

    output_path = 'f:\output.jpg'
    img.save(output_path)

    return output_path

def get_models_from_automatic1111(url = '127.0.0.1:7860'):
    endpoint = '/sdapi/v1/sd-models'

    conn = http.client.HTTPConnection(url)
    conn.request('GET', endpoint)

    response = conn.getresponse()

    #print(response.status, response.reason)
    decoded = response.read().decode()
    data = json.loads(decoded)

    return data