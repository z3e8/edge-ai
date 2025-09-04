import base64
import io
import logging
import os
import queue
import signal
import sys
import threading
import time
import uuid
from flask import Flask, jsonify, request
from PIL import Image
from model import load_model, get_model
from preprocessing import preprocess_image
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions
from logging_config import setup_logging

# setup logging (will be configured with LOG_LEVEL below)
logger = None

app = Flask(__name__)

# config from env vars
QUEUE_SIZE = int(os.getenv('QUEUE_SIZE', 10))
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 5000))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# setup logging with configured level
logger = setup_logging(LOG_LEVEL)

# track startup time for uptime calculation
startup_time = time.time()

# create request queue
request_queue = queue.Queue(maxsize=QUEUE_SIZE)

# dict to store results {request_id: result}
results = {}

# metrics tracking
metrics = {
    "total_requests": 0,
    "requests_rejected": 0,
    "total_latency_ms": 0,
    "completed_requests": 0
}

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
            req_id, image, start_time = request_queue.get()
            
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
            
            # calculate latency
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # update metrics
            metrics['completed_requests'] += 1
            metrics['total_latency_ms'] += latency_ms
            
            # store result with request_id
            results[req_id] = {
                "request_id": req_id,
                "predictions": preds,
                "latency_ms": round(latency_ms, 2)
            }
            
            logger.info(f"completed request", extra={'request_id': req_id})
            
            # mark task as done
            request_queue.task_done()
            
        except Exception as e:
            logger.error(f"error processing request: {e}", extra={'request_id': req_id})
            results[req_id] = {"request_id": req_id, "error": str(e)}

# flag for graceful shutdown
shutdown_flag = False

# start worker thread
worker = threading.Thread(target=worker_thread, daemon=True)
worker.start()

def signal_handler(sig, frame):
    """handle SIGTERM/SIGINT for graceful shutdown"""
    global shutdown_flag
    logger.info("shutdown signal received, draining queue...")
    shutdown_flag = True
    
    # wait for queue to drain (with timeout)
    try:
        request_queue.join()  # wait for all tasks to complete
        logger.info("queue drained, shutting down")
    except:
        logger.warning("queue drain timeout, forcing shutdown")
    
    sys.exit(0)

# register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@app.route('/')
def hello():
    return jsonify({"message": "hello world"})

@app.route('/health', methods=['GET'])
def health():
    """health check endpoint"""
    # check if model is loaded
    model = get_model()
    is_healthy = model is not None
    
    return jsonify({
        "status": "healthy" if is_healthy else "unhealthy",
        "model_loaded": is_healthy
    }), 200 if is_healthy else 503

@app.route('/metrics', methods=['GET'])
def get_metrics():
    """metrics endpoint"""
    avg_latency = 0
    if metrics['completed_requests'] > 0:
        avg_latency = metrics['total_latency_ms'] / metrics['completed_requests']
    
    return jsonify({
        "total_requests": metrics['total_requests'],
        "requests_rejected": metrics['requests_rejected'],
        "average_latency_ms": round(avg_latency, 2),
        "current_queue_depth": request_queue.qsize()
    })

@app.route('/status', methods=['GET'])
def get_status():
    """status endpoint showing system info"""
    uptime = time.time() - startup_time
    
    return jsonify({
        "model": "MobileNetV2",
        "queue_capacity": QUEUE_SIZE,
        "queue_current": request_queue.qsize(),
        "uptime_seconds": round(uptime, 2),
        "version": "1.0.0"
    })

@app.route('/infer', methods=['POST'])
def infer():
    # generate request id and start timer
    req_id = str(uuid.uuid4())
    start_time = time.time()
    
    # increment total requests
    metrics['total_requests'] += 1
    
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
            metrics['requests_rejected'] += 1
            logger.warning("queue full, rejecting request", extra={'request_id': req_id})
            return jsonify({"error": "service overloaded, queue full"}), 503
        
        # put request in queue for worker to process (include start time)
        request_queue.put((req_id, image, start_time), block=False)
        logger.info("request queued", extra={'request_id': req_id})
        
        # wait for result from worker thread
        while req_id not in results:
            time.sleep(0.01)  # poll every 10ms
        
        # get and return result
        result = results.pop(req_id)
        return jsonify(result)
    
    except queue.Full:
        # queue became full between check and put
        metrics['requests_rejected'] += 1
        logger.warning("queue full, rejecting request", extra={'request_id': req_id})
        return jsonify({"error": "service overloaded, queue full"}), 503
    
    except Exception as e:
        # handle invalid image format or decoding errors
        logger.error(f"error processing request: {e}", extra={'request_id': req_id})
        return jsonify({"request_id": req_id, "error": f"invalid image format: {str(e)}"}), 400

if __name__ == '__main__':
    logger.info(f"starting server on {HOST}:{PORT}, queue size: {QUEUE_SIZE}")
    app.run(host=HOST, port=PORT)

