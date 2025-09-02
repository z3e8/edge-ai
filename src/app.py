import base64
import io
import logging
import os
import queue
import threading
import time
import uuid
from flask import Flask, jsonify, request
from PIL import Image
from model import load_model, get_model
from preprocessing import preprocess_image
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions
from logging_config import setup_logging

# setup logging
logger = setup_logging()

app = Flask(__name__)

# config from env vars
QUEUE_SIZE = int(os.getenv('QUEUE_SIZE', 10))

# create request queue
request_queue = queue.Queue(maxsize=QUEUE_SIZE)

# dict to store results {request_id: result}
results = {}

# load model at startup
try:
    logger.info("loading model...")
    load_model()
    logger.info("model loaded successfully")
except Exception as e:
    logger.error(f"error loading model, exiting: {e}")
    exit(1)

def worker_thread():
    """worker that processes inference requests from queue"""
    logger.info("worker thread started")
    while True:
        try:
            # get request from queue
            req_id, image = request_queue.get()
            
            logger.info(f"processing request", extra={'request_id': req_id})
            
            # preprocess
            img_array = preprocess_image(image)
            
            # run inference
            model = get_model()
            predictions = model.predict(img_array)
            
            # decode top 5 predictions
            decoded = decode_predictions(predictions, top=5)[0]
            
            # format results
            preds = [
                {"class": label, "confidence": float(score)}
                for (_, label, score) in decoded
            ]
            
            # store result with request_id
            results[req_id] = {
                "request_id": req_id,
                "predictions": preds
            }
            
            logger.info(f"completed request", extra={'request_id': req_id})
            
            # mark task as done
            request_queue.task_done()
            
        except Exception as e:
            logger.error(f"error processing request: {e}", extra={'request_id': req_id})
            results[req_id] = {"request_id": req_id, "error": str(e)}

# start worker thread
worker = threading.Thread(target=worker_thread, daemon=True)
worker.start()

@app.route('/')
def hello():
    return jsonify({"message": "hello world"})

@app.route('/infer', methods=['POST'])
def infer():
    # generate request id
    req_id = str(uuid.uuid4())
    
    try:
        logger.info("received inference request", extra={'request_id': req_id})
        
        # get base64 image from request
        data = request.get_json()
        img_b64 = data.get('image')
        
        # decode base64 to image
        img_bytes = base64.b64decode(img_b64)
        image = Image.open(io.BytesIO(img_bytes))
        
        # check if queue is full
        if request_queue.full():
            logger.warning("queue full, rejecting request", extra={'request_id': req_id})
            return jsonify({"error": "service overloaded, queue full"}), 503
        
        # put request in queue for worker to process
        request_queue.put((req_id, image), block=False)
        logger.info("request queued", extra={'request_id': req_id})
        
        # wait for result from worker thread
        while req_id not in results:
            time.sleep(0.01)  # poll every 10ms
        
        # get and return result
        result = results.pop(req_id)
        return jsonify(result)
    
    except queue.Full:
        # queue became full between check and put
        logger.warning("queue full, rejecting request", extra={'request_id': req_id})
        return jsonify({"error": "service overloaded, queue full"}), 503
    
    except Exception as e:
        # handle invalid image format or decoding errors
        logger.error(f"error processing request: {e}", extra={'request_id': req_id})
        return jsonify({"request_id": req_id, "error": f"invalid image format: {str(e)}"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

