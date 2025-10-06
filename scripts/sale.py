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
import psycopg2

# Add path to AzureConnector
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_sale_logger

logger = get_sale_logger()

ALLOWED_TOPICS = ['sale/ready']

# InvenTree configuration
INVENTREE_URL = "http://192.168.88.132:8080"
INVENTREE_TOKEN = "inv-7da8fcf64559e1b037158a386b63bf9f0ca58ffe-20250930"  

DB_CONFIG = {
    'host': 'localhost',  #
    'database': 'scan_tmp_db',
    'user': 'scaner',
    'password': 'zxtbd',
    'port': 5432
}


class BarcodeValidator:
    def __init__(self):
        self.rules = [
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
            }
        ]
    
    def validate(self, barcode: str) -> dict:
        barcode = barcode.strip()
        
        for rule in self.rules:
            if rule['min_length'] <= len(barcode) <= rule['max_length']:
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
            'error': f"No matching pattern for barcode length {len(barcode)}"
        }


validator = BarcodeValidator()



def write_to_db(serial: str, barcode_type: str, scanner_id: str) -> bool:
    """Write scan to database queue"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO scan_queue (serial, barcode_type, scanner_id) VALUES (%s, %s, %s)",
            (serial, barcode_type, scanner_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✅ Written to DB: serial={serial}, type={barcode_type}, scanner_id={scanner_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ DB write error: {e}")
        return False


def send_to_inventree_plugin(serial: str, barcode_type: str) -> dict:
    """Send RC serial to InvenTree - only for logging, does NOT move"""
    try:
        if barcode_type != 'RC':
            return {'success': False, 'message': 'Not RC type, skipped'}
        
        headers = {
            'Authorization': f'Token {INVENTREE_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Use webhook endpoint - does NOT move device
        response = requests.post(
            f'{INVENTREE_URL}/plugin/blogger_manager/api/webhook/',
            headers=headers,
            json={'serial_number': serial},
            timeout=5
        )
        
        if response.status_code == 200:
            return {'success': True, 'message': 'Logged in InvenTree'}
        else:
            return {'success': False, 'message': f'HTTP {response.status_code}'}
            
    except Exception as e:
        logger.error(f"InvenTree webhook error: {e}")
        return {'success': False, 'message': str(e)}


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

        db_success = write_to_db(serial, barcode_type, scanner_id)
        
      
        
        response_data = {
            'status': 'success',
            'barcode': barcode,
            'serial': serial,
            'type': barcode_type,
            'scanner_id': scanner_id,
            'topic': topic,
            'db_written': db_success,
            'message': 'Barcode validated successfully'
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