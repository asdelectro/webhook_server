#!/usr/bin/env python3
"""
Скрипт для получения данных устройства по серийному номеру get_device_by_serial.py
"""
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from AzureConnector import RadiacodeManager
from logger_config import get_device_logger

# Получаем настроенный логгер (без StreamHandler!)
logger = get_device_logger()


def process_device_request(data):
    try:
        serial = data.get('serial', '').strip()
        logger.info(f"Получен запрос для серийного номера: {serial}")

        if not serial:
            logger.warning("Серийный номер пустой")
            response = {'success': False, 'message': 'Serial number is required'}
            print(json.dumps(response))
            return 1

        manager = RadiacodeManager()
        device_data = manager.ReadManufacturingDateAll(serial)

        if device_data:
            logger.info(f"Найдено устройство {serial}")
            response = {
                'success': True,
                'serial': serial,
                'device_data': device_data,
                'message': f'Найдено устройство {serial}'
            }
            print(json.dumps(response))
            return 0
        else:
            logger.warning(f"Устройство {serial} не найдено")
            response = {
                'success': False,
                'serial': serial,
                'message': f'Устройство {serial} не найдено'
            }
            print(json.dumps(response))
            return 1

    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {e}")
        response = {'success': False, 'message': f'Server error: {str(e)}'}
        print(json.dumps(response))
        return 1


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)
        
        exit_code = process_device_request(data)
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        response = {'success': False, 'message': str(e)}
        print(json.dumps(response))
        sys.exit(1)