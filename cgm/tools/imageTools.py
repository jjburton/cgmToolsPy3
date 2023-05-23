from PIL import Image, ImageFilter, ImageChops
import random

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