import maya.cmds as cmds
import maya.OpenMaya as om
import cgm.core.lib.position_utils as POS
import cgm.core.lib.transform_utils as TRANS
from cgm.core.lib import euclid as EUCLID

import cgm.core.lib.camera_utils as CAMUTILS
import importlib
importlib.reload(CAMUTILS)

from PIL import Image

def lerp(start, end, percent):
    '''Linearly interpolate between 2 numbers by percentage'''
    return (start + percent*(end - start))
        
def sample_texture_color(img, u, v):
    # Convert UV to pixel coordinates
    width, height = img.size
    x = int(u * width)
    y = int((1.0 - v) * height)  # flip v coordinate
    
    # Clamp the coordinates to be within image bounds
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))

    # Sample the color
    pixel_value = img.getpixel((x, y))

    # Depending on the image mode, handle pixel data differently
    if isinstance(pixel_value, int):
        # Grayscale image
        r = g = b = pixel_value / 255.0
        a = 1.0
    else:
        r, g, b = pixel_value[:3]
        r /= 255.0
        g /= 255.0
        b /= 255.0
        # If image has alpha
        a = pixel_value[3] / 255.0 if len(pixel_value) == 4 else 1.0

    return om.MColor(r, g, b, a)

# sets vert positions off depth texture and current camera
def displace_vertices_by_texture(mesh, texture_file, min_depth, max_depth):
    # Open the texture once
    img = Image.open(texture_file)
    
    # Convert vertices to UVs and retrieve them
    uvs = cmds.polyListComponentConversion(mesh, fromVertex=True, toUV=True)
    uv_list = cmds.filterExpand(uvs, selectionMask=35)

    if not uv_list:
        print("No UVs found for mesh: {}".format(mesh))
        return

    uv_coords = [cmds.polyEditUV(uv, query=True) for uv in uv_list]

    # Use MFnMesh to manipulate vertex positions
    selectionList = om.MSelectionList()
    selectionList.add(mesh)
    dagPath = om.MDagPath()
    selectionList.getDagPath(0, dagPath)
    meshFn = om.MFnMesh(dagPath)

    vertex_positions = om.MPointArray()
    meshFn.getPoints(vertex_positions, om.MSpace.kWorld)
    
    cam = CAMUTILS.getCurrentCamera()

    for i, uv in enumerate(uv_coords):
        color = sample_texture_color(img, uv[0], uv[1])
        displacement = lerp(max_depth, min_depth, color.r / 255.0)
        #print("color: {}, displacement: {}".format(color.r, displacement))
        worldPos = screenToWorld(cam, uv, displacement)
        vertex_positions[i].x = worldPos.x
        vertex_positions[i].y = worldPos.y
        vertex_positions[i].z = worldPos.z

    meshFn.setPoints(vertex_positions, om.MSpace.kWorld)

# resets position of verts preserving the current distance to camera
def reorganize_vertices_by_texture(mesh):
    # Convert vertices to UVs and retrieve them
    uvs = cmds.polyListComponentConversion(mesh, fromVertex=True, toUV=True)
    uv_list = cmds.filterExpand(uvs, selectionMask=35)

    if not uv_list:
        print("No UVs found for mesh: {}".format(mesh))
        return

    uv_coords = [cmds.polyEditUV(uv, query=True) for uv in uv_list]

    # Use MFnMesh to manipulate vertex positions
    selectionList = om.MSelectionList()
    selectionList.add(mesh)
    dagPath = om.MDagPath()
    selectionList.getDagPath(0, dagPath)
    meshFn = om.MFnMesh(dagPath)

    vertex_positions = om.MPointArray()
    meshFn.getPoints(vertex_positions, om.MSpace.kWorld)

    cam = CAMUTILS.getCurrentCamera()
    camPos = POS.get(cam, asEuclid=1)
    
    for i, uv in enumerate(uv_coords):
        displacement = (EUCLID.Vector3(vertex_positions[i].x, vertex_positions[i].y, vertex_positions[i].z) - camPos).magnitude()
        #print("color: {}, displacement: {}".format(color.r, displacement))
        worldPos = screenToWorld(cam, uv, displacement)
        vertex_positions[i].x = worldPos.x
        vertex_positions[i].y = worldPos.y
        vertex_positions[i].z = worldPos.z

    meshFn.setPoints(vertex_positions, om.MSpace.kWorld)

def screenToWorld(cam, screenPos, depth):
    projected_point = CAMUTILS.screenToWorld(screenPos, 0, camera_shape=mc.listRelatives(cam, shapes=True, type='camera')[0])
    proj_point = EUCLID.Point3(projected_point[0], projected_point[1], projected_point[2])
    cam_pos = POS.get(cam, asEuclid=1)
    line = EUCLID.Line3( proj_point, EUCLID.Point3(cam_pos.x, cam_pos.y, cam_pos.z) )
    planePoint = TRANS.transformDirection(cam, EUCLID.Vector3(0,0,-depth)) + cam_pos
    planeNormal = TRANS.transformDirection(cam, EUCLID.Vector3(0,0,1))
    cam_plane = EUCLID.Plane( EUCLID.Point3(planePoint.x, planePoint.y, planePoint.z), EUCLID.Point3(planeNormal.x, planeNormal.y, planeNormal.z) )
    return cam_plane.intersect(line)


# Example usage
# texture_file = 'E:/Dropbox/DarkWeb/content/environment/office2/sourceimages/office_depth2.png'
# mesh = 'pPlaneShape4'
# cam = 'camera1'
# min_depth = 6
# max_depth = 30.0
# displace_vertices_by_texture(mesh, texture_file, min_depth, max_depth)

# reorganize_vertices_by_texture(mesh, texture_file)