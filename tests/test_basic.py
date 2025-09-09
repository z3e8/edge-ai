#!/usr/bin/env python3
"""basic integration test for inference endpoint"""

import base64
import requests
import sys

# test server url
BASE_URL = "http://localhost:5000"

def test_health():
    """test health endpoint"""
    print("testing /health...")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"  status: {resp.status_code}")
    print(f"  response: {resp.json()}")
    assert resp.status_code == 200
    assert resp.json()['status'] == 'healthy'
    print("  ✓ health check passed")

def test_inference():
    """test inference with a simple test image"""
    print("\ntesting /infer...")
    
    # create a simple 100x100 red image for testing
    from PIL import Image
    import io
    
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    
    # send request
    resp = requests.post(
        f"{BASE_URL}/infer",
        json={"image": img_b64}
    )
    
    print(f"  status: {resp.status_code}")
    data = resp.json()
    print(f"  request_id: {data.get('request_id')}")
    print(f"  latency: {data.get('latency_ms')}ms")
    print(f"  top prediction: {data['predictions'][0]}")
    
    assert resp.status_code == 200
    assert 'predictions' in data
    assert len(data['predictions']) == 5
    print("  ✓ inference test passed")

def test_metrics():
    """test metrics endpoint"""
    print("\ntesting /metrics...")
    resp = requests.get(f"{BASE_URL}/metrics")
    print(f"  status: {resp.status_code}")
    data = resp.json()
    print(f"  total_requests: {data['total_requests']}")
    print(f"  avg_latency: {data['average_latency_ms']}ms")
    assert resp.status_code == 200
    print("  ✓ metrics test passed")

if __name__ == '__main__':
    try:
        test_health()
        test_inference()
        test_metrics()
        print("\n✓ all tests passed!")
    except Exception as e:
        print(f"\n✗ test failed: {e}")
        sys.exit(1)

