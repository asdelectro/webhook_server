#!/usr/bin/env python3
"""
Скрипт для обработки запросов на получение списка недавно изготовленных устройств get_devices.py
"""
import sys
import json
from datetime import datetime
from pathlib import Path

# Добавляем путь к AzureConnector
sys.path.insert(0, str(Path(__file__).parent.parent))

from AzureConnector import RadiacodeManager
from logger_config import get_devices_logger

# Получаем настроенный логгер (без StreamHandler!)
logger = get_devices_logger()


def get_recent_devices(data):
    """
    Обработка запроса на получение списка недавно изготовленных устройств
    """
    try:
        # Получаем данные
        logger.info(f"Получены данные: {data}")

        # Извлекаем параметры с проверкой типов
        limit = data.get('limit', 100)
        minutes = data.get('minutes', 600)

        # Проверяем и преобразуем параметры в int
        try:
            limit = int(limit)
            minutes = int(minutes)
        except (ValueError, TypeError):
            logger.error("Параметры limit и minutes должны быть целыми числами")
            print(json.dumps({
                'success': False,
                'error': 'Parameters limit and minutes must be integers',
                'devices': []
            }))
            return 1

        # Валидация параметров
        if limit < 1 or limit > 100:
            logger.error("Параметр limit должен быть в диапазоне 1-100")
            print(json.dumps({
                'success': False,
                'error': 'Parameter limit must be between 1 and 100',
                'devices': []
            }))
            return 1
        if minutes < 1 or minutes > 1440:
            logger.error("Параметр minutes должен быть в диапазоне 1-1440")
            print(json.dumps({
                'success': False,
                'error': 'Parameter minutes must be between 1 and 1440',
                'devices': []
            }))
            return 1

        # Получаем данные из RadiacodeManager
        manager = RadiacodeManager()
        devices_data = manager.GetRecentDevices(minutes=minutes, limit=limit)

        # Форматируем данные для совместимости с фронтендом
        devices = []
        for device in devices_data:
            device_info = {
                'barcode': device['serial'],
                'serial': device['serial'],
                'manufacturing_date': device['manufacturing_date'].isoformat() if device['manufacturing_date'] else None,
                'sale_date': device['sale_date'].isoformat() if device['sale_date'] else None,
                'status': device['status'],
                'age_minutes': device['age_minutes'],
                'age_seconds': device['age_seconds'],
                'scan_timestamp': device['manufacturing_date'].isoformat() if device['manufacturing_date'] else None,
                'timestamp': device['manufacturing_date'].strftime('%d.%m.%Y %H:%M') if device['manufacturing_date'] else 'Unknown',
                'scanner_id': 'manufacturing'
            }
            devices.append(device_info)

        logger.info(f"Найдено {len(devices)} устройств за последние {minutes} минут (UTC)")
        response_data = {
            'success': True,
            'devices': devices,
            'count': len(devices),
            'message': f'Found {len(devices)} devices manufactured in last {minutes} minutes'
        }
        print(json.dumps(response_data))
        return 0

    except Exception as e:
        logger.error(f"Ошибка получения устройств: {e}")
        response_data = {
            'success': False,
            'error': str(e),
            'devices': []
        }
        print(json.dumps(response_data))
        return 1


if __name__ == '__main__':
    try:
        # Читаем данные из аргумента или stdin
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)

        exit_code = get_recent_devices(data)
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)