"""model loading and management"""

import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions

# global model instance - loaded once at startup
# avoids loading overhead on each request
model = None

def load_model():
    """load mobilenetv2 with imagenet weights"""
    global model
    try:
        print("loading mobilenetv2 model...")
        # mobilenetv2 is ~14MB, designed for mobile/edge devices
        # good accuracy vs size tradeoff
        model = MobileNetV2(weights='imagenet')
        print("model loaded successfully")
        return model
    except Exception as e:
        print(f"failed to load model: {e}")
        raise

def get_model():
    """get the loaded model instance"""
    if model is None:
        load_model()
    return model

