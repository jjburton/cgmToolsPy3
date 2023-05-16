import numpy as np

def is_point_in_tetrahedron(tetra_points, input_point):
    v0, v1, v2, v3 = np.array(tetra_points)
    v = np.array(input_point)
    
    # Calculate the volume of the whole tetrahedron
    vol_total = np.abs(np.dot((v1 - v0), np.cross(v2 - v0, v3 - v0)))
    
    # Calculate the volumes of the four sub-tetrahedrons
    # that the point forms with the vertices of the tetrahedron
    vol0 = np.abs(np.dot((v1 - v), np.cross(v2 - v, v3 - v)))
    vol1 = np.abs(np.dot((v0 - v), np.cross(v2 - v, v3 - v)))
    vol2 = np.abs(np.dot((v0 - v), np.cross(v1 - v, v3 - v)))
    vol3 = np.abs(np.dot((v0 - v), np.cross(v1 - v, v2 - v)))
    
    # The point is inside the tetrahedron if and only if
    # the sum of the four sub-volumes is equal to the total volume
    return np.isclose(vol_total, vol0 + vol1 + vol2 + vol3)