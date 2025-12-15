"""model loading and management"""

import hashlib
import os

import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2

# global model instance - loaded once at startup
# avoids loading overhead on each request
model = None
model_path = os.getenv("MODEL_PATH", "").strip() or None
model_version = os.getenv("MODEL_VERSION", "unknown").strip() or "unknown"
model_sha256 = "unknown"


def _sha256_file(path: str) -> str:
    """compute sha256 for a file (used for model provenance)"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_model():
    """load a model once at startup"""
    global model, model_sha256
    try:
        if model_path:
            # file-based model so deploy-by-restart is real
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"MODEL_PATH not found: {model_path}")
            print(f"loading model from path: {model_path}")
            model = tf.keras.models.load_model(model_path)
            model_sha256 = _sha256_file(model_path)
        else:
            print("loading mobilenetv2 model...")
            # mobilenetv2 is ~14MB, designed for mobile/edge devices
            model = MobileNetV2(weights="imagenet")
            model_sha256 = "unknown"

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


def get_model_identity():
    """return model identity info for status/metrics"""
    return {
        "model_version": model_version,
        "model_sha256": model_sha256,
        "model_path": model_path,
    }

