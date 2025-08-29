import base64
import io
from flask import Flask, jsonify, request
from PIL import Image
from model import load_model, get_model
from preprocessing import preprocess_image
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions

app = Flask(__name__)

# load model at startup
try:
    load_model()
except Exception as e:
    print(f"error loading model, exiting: {e}")
    exit(1)

@app.route('/')
def hello():
    return jsonify({"message": "hello world"})

@app.route('/infer', methods=['POST'])
def infer():
    try:
        # get base64 image from request
        data = request.get_json()
        img_b64 = data.get('image')
        
        # decode base64 to image
        img_bytes = base64.b64decode(img_b64)
        image = Image.open(io.BytesIO(img_bytes))
        
        # preprocess
        img_array = preprocess_image(image)
        
        # run inference
        model = get_model()
        predictions = model.predict(img_array)
        
        # decode top 5 predictions
        decoded = decode_predictions(predictions, top=5)[0]
        
        # format results
        results = [
            {"class": label, "confidence": float(score)}
            for (_, label, score) in decoded
        ]
        
        return jsonify({"predictions": results})
    
    except Exception as e:
        # handle invalid image format or decoding errors
        return jsonify({"error": f"invalid image format: {str(e)}"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

