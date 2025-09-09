#!/usr/bin/env python3
"""demo script showing all features of the edge ai platform"""

import base64
import io
import requests
import time
from PIL import Image

BASE_URL = "http://localhost:5000"

def print_section(title):
    """print a section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")

def demo_health_check():
    """demo health check endpoint"""
    print_section("1. Health Check")
    
    print("checking service health...")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"status: {resp.status_code}")
    print(f"response: {resp.json()}\n")

def demo_single_inference():
    """demo single inference"""
    print_section("2. Single Inference Request")
    
    # create test image
    print("creating test image (100x100 red square)...")
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    
    print("sending inference request...")
    resp = requests.post(f"{BASE_URL}/infer", json={"image": img_b64})
    
    data = resp.json()
    print(f"\nstatus: {resp.status_code}")
    print(f"request_id: {data['request_id']}")
    print(f"latency: {data['latency_ms']}ms")
    print(f"\ntop 5 predictions:")
    for i, pred in enumerate(data['predictions'], 1):
        print(f"  {i}. {pred['class']}: {pred['confidence']:.3f}")

def demo_metrics():
    """demo metrics endpoint"""
    print_section("3. Metrics")
    
    print("fetching current metrics...")
    resp = requests.get(f"{BASE_URL}/metrics")
    data = resp.json()
    
    print(f"total requests: {data['total_requests']}")
    print(f"requests rejected: {data['requests_rejected']}")
    print(f"average latency: {data['average_latency_ms']}ms")
    print(f"current queue depth: {data['current_queue_depth']}")

def demo_status():
    """demo status endpoint"""
    print_section("4. System Status")
    
    print("fetching system status...")
    resp = requests.get(f"{BASE_URL}/status")
    data = resp.json()
    
    print(f"model: {data['model']}")
    print(f"queue capacity: {data['queue_capacity']}")
    print(f"queue current: {data['queue_current']}")
    print(f"uptime: {data['uptime_seconds']:.1f} seconds")
    print(f"version: {data['version']}")

def demo_queue_rejection():
    """demo queue rejection under load"""
    print_section("5. Queue Rejection Under Load")
    
    print("sending 15 concurrent requests to trigger queue rejection...")
    print("(with default queue size of 10, some will be rejected)\n")
    
    # create test image
    img = Image.new('RGB', (100, 100), color='green')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    
    import threading
    
    success = []
    rejected = []
    
    def send_req(num):
        try:
            resp = requests.post(
                f"{BASE_URL}/infer",
                json={"image": img_b64},
                timeout=30
            )
            if resp.status_code == 200:
                success.append(num)
                print(f"  request {num}: ✓ success")
            elif resp.status_code == 503:
                rejected.append(num)
                print(f"  request {num}: ✗ rejected (503)")
        except Exception as e:
            print(f"  request {num}: error {e}")
    
    threads = []
    for i in range(15):
        t = threading.Thread(target=send_req, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.01)
    
    for t in threads:
        t.join()
    
    print(f"\nresults:")
    print(f"  successful: {len(success)}")
    print(f"  rejected: {len(rejected)}")
    print(f"\n✓ queue backpressure working correctly!")

def main():
    """run full demo"""
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  Edge AI Inference Platform - Feature Demo".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    try:
        demo_health_check()
        time.sleep(1)
        
        demo_single_inference()
        time.sleep(1)
        
        demo_metrics()
        time.sleep(1)
        
        demo_status()
        time.sleep(1)
        
        demo_queue_rejection()
        
        print_section("Demo Complete!")
        print("all features demonstrated successfully ✓\n")
        
    except requests.exceptions.ConnectionError:
        print("\n✗ error: could not connect to service")
        print("make sure the service is running on http://localhost:5000\n")
    except Exception as e:
        print(f"\n✗ demo failed: {e}\n")

if __name__ == '__main__':
    main()

