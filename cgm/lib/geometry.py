import maya.cmds as mc

def is_point_outside_polygon_3d(poly_points, test_point):
    """
    Check if a test point is outside the boundaries of a 4 point polygon in 3D space.

    :param poly_points: A list of four 3D points representing a polygon.
    :param test_point: A 3D point to test for being outside the polygon.
    :return: True if the test point is outside the polygon, False otherwise.
    """
    x, y, z = test_point
    # Check if the test point is outside the bounding box of the polygon
    x_vals = [p[0] for p in poly_points]
    y_vals = [p[1] for p in poly_points]
    z_vals = [p[2] for p in poly_points]
    if (x < min(x_vals) or x > max(x_vals) or
        y < min(y_vals) or y > max(y_vals) or
        z < min(z_vals) or z > max(z_vals)):
        return True
    # Check if the test point is outside the polygon using the winding number algorithm
    winding_number = 0
    for i in range(4):
        j = (i + 1) % 4
        if ((poly_points[i][1] <= y < poly_points[j][1] or poly_points[j][1] <= y < poly_points[i][1]) and
            (poly_points[i][2] <= z < poly_points[j][2] or poly_points[j][2] <= z < poly_points[i][2])):
            if x < (poly_points[j][0] - poly_points[i][0]) * (y - poly_points[i][1]) / (poly_points[j][1] - poly_points[i][1]) + poly_points[i][0]:
                winding_number += 1
    return winding_number % 2 == 1

def ray_box_intersection(ray_origin, ray_direction, box_points, max_distance):
    print ("ray_origin: ", ray_origin, "ray_direction: ", ray_direction, "box_points: ", box_points, "max_distance: ", max_distance)

    # Calculate the two intersection points of the ray with the box's planes
    t_min = [(box_points[i][0] - ray_origin[0]) / ray_direction[0] for i in range(2)]
    t_max = [(box_points[i+2][0] - ray_origin[0]) / ray_direction[0] for i in range(2)]

    for i in range(3):
        if ray_direction[i] != 0:
            t1 = (box_points[0][i] - ray_origin[i]) / ray_direction[i]
            t2 = (box_points[1][i] - ray_origin[i]) / ray_direction[i]
            t_min[i] = min(t1, t2)
            t_max[i] = max(t1, t2)

    # Order the intersection points based on which axis they intersect with first
    t_order = sorted(range(3), key=lambda k: t_min[k])
    t_min = [t_min[k] for k in t_order]
    t_max = [t_max[k] for k in t_order]

    # Find the maximum t value that is less than or equal to the maximum distance
    valid_t = max([t for t in t_min if t >= 0 and t <= max_distance])

    # If there is a valid intersection point within the maximum distance
    if valid_t >= 0:
        # Calculate the intersection point and return it
        intersection_point = [ray_origin[i] + valid_t * ray_direction[i] for i in range(3)]
        return intersection_point
    else:
        # If there is no valid intersection point, return None
        return None

# get the plane position and normals for the 6 sides of the bounding box
def getPlanes(boundingBox):
    # get the center points of the 6 sides of the bounding box
    planes = []
    planes.append([(boundingBox[0] + boundingBox[3]) / 2, boundingBox[1], (boundingBox[2] + boundingBox[5]) / 2])
    planes.append([(boundingBox[0] + boundingBox[3]) / 2, boundingBox[4], (boundingBox[2] + boundingBox[5]) / 2])
    planes.append([boundingBox[0], (boundingBox[1] + boundingBox[4]) / 2, (boundingBox[2] + boundingBox[5]) / 2])
    planes.append([boundingBox[3], (boundingBox[1] + boundingBox[4]) / 2, (boundingBox[2] + boundingBox[5]) / 2])
    planes.append([(boundingBox[0] + boundingBox[3]) / 2, (boundingBox[1] + boundingBox[4]) / 2, boundingBox[2]])
    planes.append([(boundingBox[0] + boundingBox[3]) / 2, (boundingBox[1] + boundingBox[4]) / 2, boundingBox[5]])

    # get the normals of the 6 sides of the bounding box
    normals = []
    normals.append([0, -1, 0])
    normals.append([0, 1, 0])
    normals.append([-1, 0, 0])
    normals.append([1, 0, 0])
    normals.append([0, 0, -1])
    normals.append([0, 0, 1])

    # Generate all possible combinations of X, Y, and Z values
    points = [
        [boundingBox[0], boundingBox[1], boundingBox[5]],  # Top front left
        [boundingBox[3], boundingBox[1], boundingBox[5]],  # Top front right
        [boundingBox[0], boundingBox[1], boundingBox[2]],  # Bottom front left
        [boundingBox[3], boundingBox[1], boundingBox[2]],  # Bottom front right
        [boundingBox[0], boundingBox[4], boundingBox[5]],  # Top back left
        [boundingBox[3], boundingBox[4], boundingBox[5]],   # Top back right
        [boundingBox[0], boundingBox[4], boundingBox[2]],  # Bottom back left
        [boundingBox[3], boundingBox[4], boundingBox[2]]  # Bottom back right
    ]

    return planes, normals, points

# create locators for each plane position
def createLocators():
    # get the bounding box of the object
    objectBB = mc.exactWorldBoundingBox(mc.ls(selection=True)[0])

    # get the plane position and normals for the 6 sides of the bounding box
    planes, normals, points = getPlanes(objectBB)

    locators = []
    for plane in planes:
        locators.append(mc.spaceLocator(p=plane)[0])

    #create locators for each point
    for point in points:
        locators.append(mc.spaceLocator(p=point)[0])
    

    return locators
