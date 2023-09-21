from PIL import Image, ImageFilter, ImageChops, PngImagePlugin
import random
from math import ceil, sqrt
import base64
from io import BytesIO
import os
from cgm.lib import files
import tempfile

import numpy as np
import cv2
from scipy.spatial import cKDTree

def expand_uv_borders(image, dilation_radius=5, erosion_radius=3):
    # 2. Convert the PIL image to a numpy array
    image_np = np.array(image)

    # Create a binary mask where the texture exists (non-black pixels)
    uv_mask = np.any(image_np[:, :, :3] != [0, 0, 0], axis=-1).astype(np.uint8)

    # Erode the UV mask if erosion_radius is provided
    if erosion_radius > 0:
        erosion_kernel = np.ones((erosion_radius, erosion_radius), np.uint8)
        uv_mask = cv2.erode(uv_mask, erosion_kernel, iterations=erosion_radius)

    # 3. Dilate the UV mask to create the expansion area
    dilation_kernel = np.ones((dilation_radius, dilation_radius), np.uint8)
    dilated_mask = cv2.dilate(uv_mask, dilation_kernel, iterations=erosion_radius + dilation_radius)

    # 4. Identify the new border pixels
    border_mask = dilated_mask - uv_mask

    # Find coordinates of border pixels and UV pixels
    border_coords = np.column_stack(np.where(border_mask > 0))
    uv_coords = np.column_stack(np.where(uv_mask > 0))

    # Use cKDTree to find nearest UV pixel for each boundary pixel
    tree = cKDTree(uv_coords)
    distances, indices = tree.query(border_coords)

    # Replace boundary pixels with color of nearest UV pixel
    for border_coord, uv_index in zip(border_coords, indices):
        y, x = border_coord
        nearest_y, nearest_x = uv_coords[uv_index]
        image_np[y, x] = image_np[nearest_y, nearest_x]

    # 5. Convert the numpy array back to a PIL image and return
    return Image.fromarray(image_np)

def multiply(image1, image2):
    return ImageChops.multiply(image1, image2)

def adjust_opacity(image, opacity):
    alpha = Image.new('L', image.size, int(255 * opacity))
    return Image.composite(image, Image.new(image.mode, image.size), alpha)

def blurImage(image, blur_radius=2):
    # Apply the blur filter with the specified radius
    blurred_image = image.filter(ImageFilter.GaussianBlur(blur_radius))

    # Save the blurred image to the specified output path
    return blurred_image

def encodeImageToString(path):
    with open(path, "rb") as c:
        # Read the image data
        data = c.read()

        # Encode the image data as base64
        base64encoded = base64.b64encode(data)

        # Convert the base64 bytes to string
        image_string = base64encoded.decode("utf-8")

        c.close()
    
    return image_string

def decodeStringToImage(image_string):
    # Convert the base64 string to bytes
    image_bytes = base64.b64decode(image_string)
    
    # Create a BytesIO object
    image_io = BytesIO(image_bytes)
    
    # Load the image data into a PIL Image object
    image = Image.open(image_io)
    
    return image


def addMonochromaticNoise(image, noise_intensity=0.1, blur_radius=0):
    # Create a new image with the same size as the input image
    noise_image = Image.new('L', image.size)

    # Fill the noise image with random monochromatic noise
    for x in range(image.size[0]):
        for y in range(image.size[1]):
            noise_value = int(random.gauss(128, 128 * noise_intensity))
            noise_image.putpixel((x, y), (noise_value,))

    noise_image = blurImage(noise_image, blur_radius)
    
    # Convert the input image to grayscale
    grayscale_image = image.convert('L')

    #noise_image = adjust_opacity(noise_image, noise_intensity)

    # Blend the input image with the noise image
    noise_image = multiply(grayscale_image, noise_image)

    noisy_image = Image.blend(grayscale_image, noise_image, noise_intensity)

    return noisy_image    

def createContactSheet(images):
    widths, heights = zip(*(i.size for i in images))
    max_width = max(widths)
    max_height = max(heights)
    num_images = len(images)
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    contact_sheet = Image.new('RGB', (num_cols * max_width, num_rows * max_height))
    x_offset = 0
    y_offset = 0
    for i, im in enumerate(images):
        contact_sheet.paste(im, (x_offset, y_offset))
        x_offset += im.size[0]
        if (i + 1) % num_cols == 0:
            x_offset = 0
            y_offset += max_height
    return contact_sheet

def getResolutionFromContactSheet(contact_sheet, num_images):
    # Calculate number of columns and rows
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    
    # Width and height of the widest and tallest image respectively
    max_width = contact_sheet.size[0] // num_cols
    max_height = contact_sheet.size[1] // num_rows

    return max_width, max_height

def createContactSheetFromStrings(image_strings):
    images = [decodeStringToImage(x) for x in image_strings]
    return createContactSheet(images)

def createContactSheetFromPaths(image_paths):
    images = [Image.open(path) for path in image_paths]
    return createContactSheet(images)

def splitContactSheet(contact_sheet, resolution=(512, 512), image_path=None):
    width, height = contact_sheet.size
    res_width, res_height = resolution
    num_cols = width // res_width
    num_rows = height // res_height
    image_paths = []
    if not image_path:
        tmpdir = tempfile.TemporaryDirectory().name
        os.mkdir(tmpdir)
        image_path = os.path.join(tmpdir, "split_contact_sheet.png")
    base, ext = os.path.splitext(image_path)

    for row in range(num_rows):
        for col in range(num_cols):
            x1 = col * res_width
            y1 = row * res_height
            x2 = x1 + res_width
            y2 = y1 + res_height
            box = (x1, y1, x2, y2)
            
            image = contact_sheet.crop(box)
            wantedName = f'{base}_{row}_{col}.{ext}'
            image_path = files.create_unique_filename(wantedName)
            image.save(image_path)
            image_paths.append(image_path)
    return image_paths

def getPngMetadata(filePath):
    try:
        with Image.open(filePath) as img:
            # Basic metadata
            width, height = img.size
            mode = img.mode
            format = img.format

            # PNG specific metadata
            pngInfo = img.info

            # Combine basic and PNG specific metadata into one dictionary
            metadata = {
                "width": width,
                "height": height,
                "mode": mode,
                "format": format,
                "pngInfo": pngInfo
            }

            return metadata
    except IOError:
        print(f"Error: File {filePath} does not appear to exist.")
        return None

def makePngInfo(metadata):
    try:
        # Open the image file
        #img = Image.open(img_path)

        # PNG specific metadata
        pngInfo = PngImagePlugin.PngInfo()

        # If there's an 'pngInfo' in metadata
        for k, v in metadata.items():
            print("adding", k, v)
            pngInfo.add_text(k, v)

        return pngInfo
    except IOError:
        print(f"Error: File does not appear to exist.")
        return None