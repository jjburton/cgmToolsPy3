from PIL import Image, ImageFilter
import random

def blurImage(input_image_path, output_image_path, blur_radius=2):
    # Open the input image
    image = Image.open(input_image_path)

    # Apply the blur filter with the specified radius
    blurred_image = image.filter(ImageFilter.GaussianBlur(blur_radius))

    # Save the blurred image to the specified output path
    blurred_image.save(output_image_path)

def addMonochromaticNoise(image, noise_intensity=0.1):
    # Create a new image with the same size as the input image
    noise_image = Image.new('L', image.size)

    # Fill the noise image with random monochromatic noise
    for x in range(image.size[0]):
        for y in range(image.size[1]):
            noise_value = int(random.gauss(128, 128 * noise_intensity))
            noise_image.putpixel((x, y), (noise_value,))

    # Convert the input image to grayscale
    grayscale_image = image.convert('L')

    # Blend the input image with the noise image
    noisy_image = Image.blend(grayscale_image, noise_image, noise_intensity)

    return noisy_image