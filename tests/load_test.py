#!/usr/bin/env python3
"""load test to trigger queue rejections"""

import base64
import io
import requests
import threading
import time
from PIL import Image

BASE_URL = "http://localhost:5000"

# create a test image
img = Image.new('RGB', (100, 100), color='blue')
buf = io.BytesIO()
img.save(buf, format='JPEG')
img_b64 = base64.b64encode(buf.getvalue()).decode()

results = {
    "success": 0,
    "rejected": 0,
    "errors": 0
}

def send_request(num):
    """send a single inference request"""
    try:
        resp = requests.post(
            f"{BASE_URL}/infer",
            json={"image": img_b64},
            timeout=30
        )
        
        if resp.status_code == 200:
            results["success"] += 1
            print(f"  request {num}: success")
        elif resp.status_code == 503:
            results["rejected"] += 1
            print(f"  request {num}: rejected (queue full)")
        else:
            results["errors"] += 1
            print(f"  request {num}: error {resp.status_code}")
    except Exception as e:
        results["errors"] += 1
        print(f"  request {num}: exception {e}")

def run_load_test(num_requests=20):
    """run load test with concurrent requests"""
    print(f"running load test with {num_requests} concurrent requests...")
    print("(expect some 503 rejections when queue fills up)\n")
    
    threads = []
    for i in range(num_requests):
        t = threading.Thread(target=send_request, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.05)  # small delay between requests
    
    # wait for all to complete
    for t in threads:
        t.join()
    
    print(f"\nload test complete:")
    print(f"  successful: {results['success']}")
    print(f"  rejected (503): {results['rejected']}")
    print(f"  errors: {results['errors']}")
    print(f"  total: {sum(results.values())}")
    
    if results['rejected'] > 0:
        print("\n✓ queue rejection working correctly!")
    else:
        print("\n⚠ no rejections - try increasing num_requests")

if __name__ == '__main__':
    run_load_test(20)

