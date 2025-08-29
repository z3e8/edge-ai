import numpy as np
from PIL import Image
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

def preprocess_image(image):
    """
    resize and normalize image for mobilenetv2
    expects PIL Image, returns numpy array ready for inference
    """
    # mobilenetv2 expects 224x224
    img = image.resize((224, 224))
    
    # convert to array
    img_array = np.array(img)
    
    # add batch dimension
    img_array = np.expand_dims(img_array, axis=0)
    
    # mobilenetv2 preprocessing (normalization)
    img_array = preprocess_input(img_array)
    
    return img_array

