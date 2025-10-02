#!/usr/bin/env python3
"""webcam inference mode - takes pictures and runs inference"""

import os
import sys
import time
from PIL import Image
from model import load_model, get_model
from preprocessing import preprocess_image
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions

try:
    import cv2
except ImportError:
    print("error: opencv-python not installed. run: pip install opencv-python")
    sys.exit(1)

# config
INTERVAL_SECONDS = int(os.getenv('CAMERA_INTERVAL', 5))  # default 5 seconds
CAMERA_INDEX = int(os.getenv('CAMERA_INDEX', 0))  # default first camera

def main():
    """main loop - capture images and run inference"""
    print(f"starting webcam inference mode (interval: {INTERVAL_SECONDS}s)")
    
    # load model
    print("loading model...")
    try:
        load_model()
        print("model loaded")
    except Exception as e:
        print(f"error loading model: {e}")
        sys.exit(1)
    
    # open camera
    print(f"opening camera {CAMERA_INDEX}...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    
    if not cap.isOpened():
        print(f"error: could not open camera {CAMERA_INDEX}")
        sys.exit(1)
    
    print("camera ready, starting capture loop...")
    print("press ctrl+c to stop\n")
    
    model = get_model()
    frame_count = 0
    
    try:
        while True:
            # capture frame
            ret, frame = cap.read()
            if not ret:
                print("error: failed to capture frame")
                time.sleep(1)
                continue
            
            frame_count += 1
            print(f"[frame {frame_count}] captured image, running inference...")
            
            # convert opencv BGR to RGB for PIL
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            
            # preprocess and run inference
            start_time = time.time()
            img_array = preprocess_image(img)
            predictions = model.predict(img_array, verbose=0)
            decoded = decode_predictions(predictions, top=5)[0]
            latency_ms = (time.time() - start_time) * 1000
            
            # print results
            print(f"  latency: {latency_ms:.1f}ms")
            print(f"  top predictions:")
            for i, (_, label, score) in enumerate(decoded, 1):
                print(f"    {i}. {label}: {score:.4f}")
            print()
            
            # wait for next interval
            time.sleep(INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        cap.release()
        print("camera released, exiting")

if __name__ == '__main__':
    main()

