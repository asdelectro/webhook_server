#!/usr/bin/env python3
"""
Script for processing sale messages
"""
import sys
import json
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from AzureConnector import RadiacodeManager

# Add path to AzureConnector
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_sale_logger

logger = get_sale_logger()

ALLOWED_TOPICS = ['sale/ready']

# InvenTree configuration
INVENTREE_URL = "http://192.168.88.132:8080"
INVENTREE_TOKEN = "inv-3d1c37e2156c24a5af7e384099de32dfd12e522d-20251015"
SHIPPING_ENDPOINT = f"{INVENTREE_URL}/plugin/shipingmanager/add-to-queue/"



class BarcodeValidator:
    def __init__(self):
        self.rules = [
            {
                'name': 'Acccesory',
                'pattern': r'^634240\d{6}$',  # 634240 + 6 цифр
                'extractor': lambda bc: bc,
                'min_length': 12,
                'max_length': 12
            },
            {
                'name': 'RC',
                'pattern': r'^RC-\d{3}-\d{6}$',
                'extractor': lambda bc: bc,
                'min_length': 13,
                'max_length': 13
            },
            {
                'name': 'Amazon',
                'pattern': r'^FBA.+U.+$',
                'extractor': lambda bc: f"FBA{bc[3:bc.index('U')]}",
                'min_length': 19,
                'max_length': 19
            },
            {
                'name': 'Shopify',
                'pattern': r'^\d{34}$',
                'extractor': lambda bc: bc[-12:],
                'min_length': 34,
                'max_length': 34
            },
            {
                'name': 'Amazon',
                'pattern': r'.+', # Любой код, главное чтобы длина была > 10
                'extractor': lambda bc: bc,
                'min_length': 10,
                'max_length': 12 #
            }
        ]

    def validate(self, barcode: str) -> dict:
        barcode = barcode.strip()
        barcode_len = len(barcode)

        for rule in self.rules:
            if rule['min_length'] <= barcode_len:
                if rule['max_length'] is None or barcode_len <= rule['max_length']:
                    if re.match(rule['pattern'], barcode):
                        try:
                            serial = rule['extractor'](barcode)
                            return {
                                'valid': True,
                                'serial': serial,
                                'type': rule['name'],
                                'original': barcode,
                                'error': None
                            }
                        except Exception as e:
                            continue

        return {
            'valid': False,
            'serial': None,
            'type': 'Unknown',
            'original': barcode,
            'error': f"No matching pattern for barcode length {barcode_len}"
        }

validator = BarcodeValidator()



def write_to_db(serial: str, barcode_type: str, scanner_id: str) -> bool:
    """Write scan event to the Radiacode database queue."""

    # Validate serial format early
    if not serial.startswith("RC-"):
        logger.info(
            f"DB SKIP: serial='{serial}' does not start with 'RC-'. Nothing written."
        )
        return True  # Not an error, just skipping
    
    try:
        manager = RadiacodeManager()
        result = manager.WriteSaleDate(serial)

        if result:
            logger.info(
                f"DB OK: serial='{serial}', type='{barcode_type}', scanner='{scanner_id}'"
            )
            return True
        else:
            logger.error(
                f"DB FAIL: WriteSaleDate returned False for serial='{serial}' "
                f"(type={barcode_type}, scanner={scanner_id})"
            )
            return False

    except Exception as e:
        logger.exception(
            f"DB ERROR: exception while writing serial='{serial}', "
            f"type='{barcode_type}', scanner='{scanner_id}': {e}"
        )
        return False


def send_to_shipping_queue(serial: str, barcode_type: str, scanner_id: str, original_barcode: str) -> dict:
    """Send barcode to InvenTree ShipingManager queue"""
    try:
        # First check if endpoint exists
        try:
            check_response = requests.get(
                f"{INVENTREE_URL}/plugin/shipingmanager/get-queue/",
                headers={'Authorization': f'Token {INVENTREE_TOKEN}'},
                timeout=5
            )
            if check_response.status_code != 200:
                logger.error(f"❌ ShipingManager plugin not accessible: HTTP {check_response.status_code}")
                logger.error(f"   Check if plugin is enabled at {INVENTREE_URL}")
                return {
                    'success': False,
                    'message': f'Plugin endpoint not available: {check_response.status_code}'
                }
        except Exception as e:
            logger.error(f"❌ Cannot reach InvenTree at {INVENTREE_URL}: {e}")
            return {
                'success': False,
                'message': f'InvenTree unreachable: {str(e)}'
            }
        if barcode_type == 'Shopify':
           original_barcode = original_barcode[-12:]
        payload = {
            "serial": serial,
            "barcode_type": barcode_type,
            "scanner_id": scanner_id,
            "original_barcode": original_barcode,
            "timestamp": datetime.utcnow().isoformat(),
            "validation": {
                "valid": True,
                "pattern_matched": barcode_type
            }
        }
        
        logger.info(f"📤 Sending to {SHIPPING_ENDPOINT}")
        logger.info(f"📤 Payload: {json.dumps(payload)}")
        
        headers = {
            'Authorization': f'Token {INVENTREE_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            SHIPPING_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        logger.info(f"📥 Response status={response.status_code}, content-type={response.headers.get('content-type', 'unknown')}")
        
        # Check if response is HTML (error page)
        content_type = response.headers.get('content-type', '')
        if 'text/html' in content_type:
            logger.error(f"❌ InvenTree returned HTML instead of JSON - plugin endpoint not found")
            logger.error(f"   URL: {SHIPPING_ENDPOINT}")
            logger.error(f"   Ensure ShipingManager plugin is enabled")
            return {
                'success': False,
                'message': 'Plugin endpoint not found - check if ShipingManager is enabled'
            }
        
        if response.status_code in [200, 201]:
            try:
                data = response.json()
                logger.info(f"✅ Added to InvenTree queue: added_count={data.get('added_count', 0)}, queue_length={data.get('queue_length', 0)}, ids={data.get('added_ids', [])}")
                return {
                    'success': True,
                    'added_count': data.get('added_count', 0),
                    'added_ids': data.get('added_ids', []),
                    'queue_length': data.get('queue_length', 0),
                    'errors': data.get('errors', []),
                    'message': data.get('message', 'Added to shipping queue')
                }
            except json.JSONDecodeError as je:
                logger.error(f"❌ JSON decode error: {je}")
                logger.error(f"   Response text: {response.text[:200]}")
                return {
                    'success': False,
                    'message': f'Invalid JSON response: {response.text[:200]}'
                }
        else:
            logger.error(f"❌ InvenTree queue error: HTTP {response.status_code}")
            logger.error(f"   Response: {response.text[:500]}")
            return {
                'success': False,
                'message': f'HTTP {response.status_code}: {response.text[:200]}'
            }
            
    except requests.exceptions.RequestException as re:
        logger.error(f"❌ Request error: {re}")
        return {
            'success': False,
            'message': f'Request failed: {str(re)}'
        }
    except Exception as e:
        logger.error(f"❌ InvenTree queue error: {e}")
        return {
            'success': False,
            'message': str(e)
        }


def process_sale(data):
    try:
        logger.info(f"Received data: {data}")

        topic = data.get('topic', '')
        logger.info(f"Data from topic: {topic}")
        
        if topic not in ALLOWED_TOPICS:
            logger.warning(f"Unauthorized topic: {topic}")
            result = {
                'error': 'Unauthorized topic',
                'topic': topic,
                'allowed_topics': ALLOWED_TOPICS
            }
            print(json.dumps(result))
            return 1

        payload_str = data.get('payload', '{}')
        payload_json = json.loads(payload_str)

        barcode = payload_json.get('msg', '').strip()
        scanner_id = payload_json.get('id', 'unknown')
        
        logger.info(f"Parsing: barcode={barcode}, topic={topic}")

        result = validator.validate(barcode)
        
        if not result['valid']:
            logger.warning(f"Validation error: {result['error']}")
            print(json.dumps({'error': result['error'], 'barcode': barcode}))
            return 1
        
        serial = result['serial']
        barcode_type = result['type']
        
        logger.info(f"Validation OK: type={barcode_type}, serial={serial}")

        # Write to database
        db_success = write_to_db(serial, barcode_type, scanner_id)
        
        # Send to InvenTree shipping queue
        inventree_result = send_to_shipping_queue(serial, barcode_type, scanner_id, barcode)
        logger.info(f"Send to invenree={barcode_type}, serial={serial}")

        
        response_data = {
            'status': 'success',
            'barcode': barcode,
            'serial': serial,
            'type': barcode_type,
            'scanner_id': scanner_id,
            'topic': topic,
            'db_written': db_success,
            'inventree_queue': inventree_result,
            'message': 'Barcode validated and queued successfully'
        }
        print(json.dumps(response_data))
        return 0
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        print(json.dumps({'error': 'Invalid JSON payload'}))
        return 1
    except Exception as e:
        logger.error(f"General error: {e}")
        print(json.dumps({'error': f'Server error: {str(e)}'}))
        return 1


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)
        
        exit_code = process_sale(data)
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)