#!/usr/bin/env python3
"""generate sample test images"""

from PIL import Image

# red square
img = Image.new('RGB', (224, 224), color='red')
img.save('red_square.jpg', 'JPEG')

# blue square
img = Image.new('RGB', (224, 224), color='blue')
img.save('blue_square.jpg', 'JPEG')

# green square
img = Image.new('RGB', (224, 224), color='green')
img.save('green_square.jpg', 'JPEG')

print("generated 3 sample test images")

