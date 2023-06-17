from PIL import Image, ImageFilter, ImageChops, PngImagePlugin
import random
from math import ceil, sqrt
import base64
from io import BytesIO

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

def createContactSheetFromStrings(image_strings):
    images = [decodeStringToImage(x) for x in image_strings]
    return createContactSheet(images)

def createContactSheetFromPaths(image_paths):
    images = [Image.open(path) for path in image_paths]
    return createContactSheet(images)

def splitContactSheet(contact_sheet, resolution=(512, 512)):
    width, height = contact_sheet.size
    res_width, res_height = resolution
    num_cols = width // res_width
    num_rows = height // res_height
    image_paths = []
    for row in range(num_rows):
        for col in range(num_cols):
            x1 = col * res_width
            y1 = row * res_height
            x2 = x1 + res_width
            y2 = y1 + res_height
            box = (x1, y1, x2, y2)
            image = contact_sheet.crop(box)
            image_path = f'F:/image_{row}_{col}.jpg'
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