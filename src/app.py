#!/usr/bin/env python3
"""edge ai inference service - main application"""

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
from datetime import datetime
from flask import Flask, jsonify, request
from PIL import Image
from model import load_model, get_model, get_model_identity
from preprocessing import preprocess_image
from telemetry import TelemetryClient
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions
from logging_config import setup_logging

# setup logging (will be configured with LOG_LEVEL below)
logger = None

app = Flask(__name__)

# config from env vars
QUEUE_SIZE = int(os.getenv('QUEUE_SIZE', 10))  # max queue depth
HOST = os.getenv('HOST', '0.0.0.0')  # bind to all interfaces
PORT = int(os.getenv('PORT', 5000))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# mode + identity (standalone is default)
EDGE_MODE = os.getenv("EDGE_MODE", "standalone").strip().lower()
if EDGE_MODE not in ("standalone", "tier1"):
    EDGE_MODE = "standalone"

DEVICE_ID = os.getenv("DEVICE_ID", "dev-001").strip()
if not DEVICE_ID:
    DEVICE_ID = "dev-001"

# tier1 telemetry config (used only when EDGE_MODE=tier1)
CONTROL_PLANE_URL = os.getenv("CONTROL_PLANE_URL", "http://127.0.0.1:8000").strip()
TELEMETRY_PATH = os.getenv("TELEMETRY_PATH", "/telemetry").strip() or "/telemetry"
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "").strip() or None
TELEMETRY_FLUSH_INTERVAL_SECONDS = float(os.getenv("TELEMETRY_FLUSH_INTERVAL_SECONDS", "3"))
TELEMETRY_BATCH_SIZE = int(os.getenv("TELEMETRY_BATCH_SIZE", "50"))

# setup logging with configured level
logger = setup_logging(LOG_LEVEL)

# track startup time for uptime calculation
startup_time = time.time()

# create bounded request queue
# rejects with 503 when full (backpressure handling)
request_queue = queue.Queue(maxsize=QUEUE_SIZE)

# dict to pass results from worker thread back to api handlers
# keyed by request_id
results = {}

# basic metrics tracking
# note: not thread-safe, but good enough for demo
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

# start telemetry in tier1 mode (runs out of band)
telemetry = TelemetryClient(
    enabled=(EDGE_MODE == "tier1"),
    device_id=DEVICE_ID,
    identity_provider=get_model_identity,
    control_plane_url=CONTROL_PLANE_URL,
    telemetry_path=TELEMETRY_PATH,
    device_token=DEVICE_TOKEN,
    flush_interval_s=TELEMETRY_FLUSH_INTERVAL_SECONDS,
    batch_size=TELEMETRY_BATCH_SIZE,
    logger=logger,
)
telemetry.start()

def worker_thread():
    """
    worker that processes inference requests from queue
    runs continuously, processing one request at a time
    single worker = sequential processing = simple concurrency model
    """
    logger.info("worker thread started")
    while True:
        try:
            # blocking get - waits for next request
            req_id, image, start_time = request_queue.get()
            
            logger.info(f"processing request", extra={'request_id': req_id})
            
            # preprocess image for model input
            img_array = preprocess_image(image)
            
            # run inference (cpu-bound, takes ~100-300ms on pi5)
            model = get_model()
            predictions = model.predict(img_array)
            
            # decode imagenet class labels
            decoded = decode_predictions(predictions, top=5)[0]
            
            # format as json-friendly list
            preds = [
                {"class": label, "confidence": float(score)}
                for (_, label, score) in decoded
            ]
            
            # calculate end-to-end latency
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # update metrics (not thread-safe but good enough)
            metrics['completed_requests'] += 1
            metrics['total_latency_ms'] += latency_ms
            
            # store result for api handler to pick up
            results[req_id] = {
                "request_id": req_id,
                "predictions": preds,
                "latency_ms": round(latency_ms, 2)
            }

            # tier1: send perf/overload signals out of band
            telemetry.enqueue(
                {
                    "request_id": req_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "latency_ms": round(latency_ms, 2),
                    "queue_depth": request_queue.qsize(),
                    "http_status": 200,
                }
            )
            
            logger.info(f"completed request", extra={'request_id': req_id})
            
            # signal queue that task is done
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
    # join() waits for all queue.task_done() calls
    queue_size = request_queue.qsize()
    logger.info(f"waiting for {queue_size} queued requests to complete...")
    
    try:
        # wait up to 60 seconds for queue to drain
        # assumes ~10 req/sec worst case = 6s per request
        import threading
        drain_thread = threading.Thread(target=request_queue.join)
        drain_thread.start()
        drain_thread.join(timeout=60)
        
        if drain_thread.is_alive():
            logger.warning("queue drain timeout after 60s, forcing shutdown")
        else:
            logger.info("queue drained successfully, shutting down cleanly")
    except Exception as e:
        logger.error(f"error during shutdown: {e}")
    
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
        "current_queue_depth": request_queue.qsize(),
        "telemetry_batches_sent": telemetry.batches_sent,
        "telemetry_send_failures": telemetry.send_failures,
        "telemetry_backlog_events": telemetry.backlog(),
    })

@app.route('/status', methods=['GET'])
def get_status():
    """status endpoint showing system info"""
    uptime = time.time() - startup_time
    ident = get_model_identity()
    
    return jsonify({
        "device_id": DEVICE_ID,
        "edge_mode": EDGE_MODE,
        "model": "MobileNetV2",
        "model_version": ident.get("model_version"),
        "model_sha256": ident.get("model_sha256"),
        "telemetry_enabled": bool(telemetry.enabled),
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
        
        # get json data
        data = request.get_json()
        if data is None:
            logger.error("missing json body", extra={'request_id': req_id})
            return jsonify({
                "request_id": req_id,
                "error": "missing json body"
            }), 400
        
        # check for image field
        img_b64 = data.get('image')
        if not img_b64:
            logger.error("missing image field", extra={'request_id': req_id})
            return jsonify({
                "request_id": req_id,
                "error": "missing 'image' field in request"
            }), 400
        
        # decode base64
        try:
            img_bytes = base64.b64decode(img_b64)
        except Exception as e:
            logger.error(f"invalid base64: {e}", extra={'request_id': req_id})
            return jsonify({
                "request_id": req_id,
                "error": "invalid base64 encoding"
            }), 400
        
        # open image
        try:
            image = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            logger.error(f"invalid image format: {e}", extra={'request_id': req_id})
            return jsonify({
                "request_id": req_id,
                "error": "unsupported image format (use jpeg, png, etc)"
            }), 400
        
        # check if queue is full
        if request_queue.full():
            metrics['requests_rejected'] += 1
            logger.warning("queue full, rejecting request", extra={'request_id': req_id})
            telemetry.enqueue(
                {
                    "request_id": req_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "latency_ms": None,
                    "queue_depth": request_queue.qsize(),
                    "http_status": 503,
                }
            )
            return jsonify({
                "request_id": req_id,
                "error": "service overloaded, queue is full. try again later."
            }), 503
        
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
        telemetry.enqueue(
            {
                "request_id": req_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "latency_ms": None,
                "queue_depth": request_queue.qsize(),
                "http_status": 503,
            }
        )
        return jsonify({
            "request_id": req_id,
            "error": "service overloaded, queue is full. try again later."
        }), 503
    
    except Exception as e:
        # catch-all for unexpected errors
        logger.error(f"unexpected error: {e}", extra={'request_id': req_id})
        return jsonify({
            "request_id": req_id,
            "error": f"internal server error: {str(e)}"
        }), 500

if __name__ == '__main__':
    logger.info(f"starting server on {HOST}:{PORT}, queue size: {QUEUE_SIZE}")
    app.run(host=HOST, port=PORT)

