#!/usr/bin/env python3
"""
Script for getting devices from scan_queue with time and scanner filters
"""
import sys
import json
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_devices_logger

logger = get_devices_logger()

DB_CONFIG = {
    'host': 'localhost',
    'database': 'scan_tmp_db',
    'user': 'scaner',
    'password': 'zxtbd',
    'port': 5432
}


def get_scanned_devices(data):
    """Get scanned devices with optional filters and mark them as processed"""
    try:
        logger.info(f"Received data: {data}")

        limit = data.get('limit', 10)
        minutes = data.get('minutes', None)
        seconds = data.get('seconds', None)
        scanner_id = data.get('scanner_id', None)
        session_id = data.get('session_id', 'get_devices_request')

        if minutes is None and seconds is None:
            minutes = 30

        try:
            limit = int(limit)
            if minutes is not None:
                minutes = int(minutes)
            if seconds is not None:
                seconds = int(seconds)
        except (ValueError, TypeError):
            print(json.dumps({'success': False, 'error': 'Parameters must be integers', 'devices': []}))
            return 1

        if limit < 1 or limit > 100:
            print(json.dumps({'success': False, 'error': 'Limit must be between 1 and 100', 'devices': []}))
            return 1

        if seconds is not None:
            if seconds < 1 or seconds > 86400:
                print(json.dumps({'success': False, 'error': 'Seconds must be between 1 and 86400', 'devices': []}))
                return 1
            time_desc = f"{seconds} seconds"
        else:
            if minutes < 1 or minutes > 1440:
                print(json.dumps({'success': False, 'error': 'Minutes must be between 1 and 1440', 'devices': []}))
                return 1
            seconds = minutes * 60
            time_desc = f"{minutes} minutes"

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        if scanner_id:
            sql = """
                SELECT id, serial, barcode_type, scanner_id, scanned_at, created_at,
                       EXTRACT(EPOCH FROM (NOW() - scanned_at)) as seconds_ago
                FROM scan_queue
                WHERE EXTRACT(EPOCH FROM (NOW() - scanned_at)) <= %s 
                  AND scanner_id = %s 
                  AND processed = FALSE
                ORDER BY scanned_at DESC
                LIMIT %s
            """
            cur.execute(sql, (seconds, scanner_id, limit))
        else:
            sql = """
                SELECT id, serial, barcode_type, scanner_id, scanned_at, created_at,
                       EXTRACT(EPOCH FROM (NOW() - scanned_at)) as seconds_ago
                FROM scan_queue
                WHERE EXTRACT(EPOCH FROM (NOW() - scanned_at)) <= %s 
                  AND processed = FALSE
                ORDER BY scanned_at DESC
                LIMIT %s
            """
            cur.execute(sql, (seconds, limit))

        rows = cur.fetchall()
        
        devices = []
        device_ids = []
        
        for row in rows:
            device_id, serial, barcode_type, scan_id, scanned_at, created_at, seconds_ago = row
            
            device_ids.append(device_id)
            age_seconds = int(seconds_ago)
            age_minutes = int(seconds_ago / 60)

            devices.append({
                'id': device_id,
                'barcode': serial,
                'serial': serial,
                'barcode_type': barcode_type,
                'scanner_id': scan_id or 'unknown',
                'scanned_at': scanned_at.isoformat() if scanned_at else None,
                'created_at': created_at.isoformat() if created_at else None,
                'age_minutes': age_minutes,
                'age_seconds': age_seconds,
                'timestamp': scanned_at.strftime('%d.%m.%Y %H:%M:%S') if scanned_at else 'Unknown',
                'status': 'scanned'
            })

        # Mark devices as processed
        if device_ids:
            cur.execute("""
                UPDATE scan_queue
                SET processed = TRUE, session_id = %s
                WHERE id = ANY(%s)
            """, (session_id, device_ids))
            conn.commit()
            logger.info(f"Marked {len(device_ids)} devices as processed")

        cur.close()
        conn.close()

        filter_msg = f" from scanner '{scanner_id}'" if scanner_id else ""
        logger.info(f"Found {len(devices)} unprocessed devices{filter_msg} in last {time_desc}")
        
        print(json.dumps({
            'success': True,
            'devices': devices,
            'count': len(devices),
            'scanner_id': scanner_id,
            'time_filter': time_desc,
            'message': f'Found {len(devices)} devices{filter_msg} scanned in last {time_desc}'
        }))
        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        print(json.dumps({'success': False, 'error': str(e), 'devices': []}))
        return 1


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)

        sys.exit(get_scanned_devices(data))

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)