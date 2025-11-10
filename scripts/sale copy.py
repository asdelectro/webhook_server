#!/usr/bin/env python3
"""
Test script for InvenTree plugin endpoint
"""
import requests
import json
from datetime import datetime

# InvenTree Configuration
INVENTREE_URL = "http://192.168.88.132:8080"
INVENTREE_TOKEN = "inv-3d1c37e2156c24a5af7e384099de32dfd12e522d-20251015"
ENDPOINT_URL = f"{INVENTREE_URL}/plugin/shipingmanager/add-to-queue/"

def test_connection():
    """Test basic connection to InvenTree"""
    try:
        print("🔍 Testing connection to InvenTree...")
        response = requests.get(
            f"{INVENTREE_URL}/api/",
            headers={'Authorization': f'Token {INVENTREE_TOKEN}'},
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✅ InvenTree API is accessible")
            return True
        else:
            print(f"❌ InvenTree API error: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def test_queue_get():
    """Test getting queue from plugin"""
    try:
        print("\n🔍 Testing GET queue endpoint...")
        response = requests.get(
            f"{INVENTREE_URL}/plugin/shipingmanager/get-queue/",
            headers={'Authorization': f'Token {INVENTREE_TOKEN}'},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Queue endpoint accessible")
            print(f"   Queue count: {data.get('count', 0)}")
            print(f"   Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Queue endpoint error: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Queue endpoint error: {e}")
        return False


def test_add_to_queue(barcode_type: str = "RC", serial: str = "RC-102-999999"):
    """Test adding item to queue"""
    try:
        print(f"\n🔍 Testing ADD to queue: {barcode_type} / {serial}...")
        
        payload = {
            "serial": serial,
            "barcode_type": barcode_type,
            "scanner_id": "test_scanner",
            "original_barcode": serial,
            "timestamp": datetime.utcnow().isoformat(),
            "validation": {
                "valid": True,
                "pattern_matched": barcode_type
            }
        }
        
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            ENDPOINT_URL,
            json=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Token {INVENTREE_TOKEN}'
            },
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            print(f"✅ Successfully added to queue")
            print(f"   Queue ID: {data.get('queue_id', 'N/A')}")
            print(f"   Queue length: {data.get('queue_length', 'N/A')}")
            print(f"   Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ Add to queue error: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Add to queue error: {e}")
        return False


def test_all_barcode_types():
    """Test all barcode types"""
    test_cases = [
        ("RC", "RC-102-123456"),
        ("Amazon", "B08X6N7Y2K"),
        ("Amazon", "FBAX001234567"),
        ("Shopify", "567890123456"),
    ]
    
    print("\n" + "="*60)
    print("Testing all barcode types...")
    print("="*60)
    
    results = []
    for barcode_type, serial in test_cases:
        success = test_add_to_queue(barcode_type, serial)
        results.append((barcode_type, serial, success))
    
    print("\n" + "="*60)
    print("Test Results:")
    print("="*60)
    for barcode_type, serial, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {barcode_type:10} : {serial}")
    
    return all(r[2] for r in results)


if __name__ == '__main__':
    print("="*60)
    print("InvenTree Plugin Endpoint Test")
    print("="*60)
    print(f"InvenTree URL: {INVENTREE_URL}")
    print(f"Plugin Endpoint: {ENDPOINT_URL}")
    print("="*60)
    
    # Test connection
    if not test_connection():
        print("\n❌ Basic connection failed. Check InvenTree URL and token.")
        exit(1)
    
    # Test get queue
    if not test_queue_get():
        print("\n❌ Queue endpoint not accessible. Check if plugin is installed.")
        exit(1)
    
    # Test adding to queue
    test_all_barcode_types()
    
    # Final queue check
    print("\n" + "="*60)
    print("Final queue state:")
    print("="*60)
    test_queue_get()
    
    print("\n✅ All tests completed!")