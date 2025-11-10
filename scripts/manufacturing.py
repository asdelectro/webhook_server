#!/usr/bin/env python3
"""
Скрипт для обработки сканирования в производстве manufacturing.py
"""
import sys
import json
from datetime import datetime
from pathlib import Path
from aux.InvenTreeStockManager import InvenTreeStockManager

# Добавляем путь к AzureConnector
sys.path.insert(0, str(Path(__file__).parent.parent))

from AzureConnector import RadiacodeManager
from logger_config import get_manufacturing_logger

# Получаем настроенный логгер (без StreamHandler!)
logger = get_manufacturing_logger()

# Конфигурация
BARCODE_PREFIX = 'RC-'
MIN_BARCODE_LENGTH = 10
ALLOWED_TOPICS = ['production/ready']

def process_new_device(serial_number: str):
    """
    Adds a new device to InvenTree based on its serial number.
    """
    manager = InvenTreeStockManager(logger=logger)#logger=logger enabled logging in InvenTreeStockManager
    success, message = manager.add_device_by_serial(serial_number)

    if success:
        logger.info(f"OK! Device {serial_number} success add in InvenTree: {message}")
    else:
        logger.info(f"ERROR {serial_number} not add in InvenTree: {message}")


def validate_barcode(barcode):
    """Валидация штрихкода"""
    if not barcode:
        return False, "Barcode is required"
    
    if not barcode.startswith(BARCODE_PREFIX):
        return False, f"Invalid barcode format. Expected format: {BARCODE_PREFIX}XXXXXXXXX (min {MIN_BARCODE_LENGTH} chars)"
    
    if len(barcode) < MIN_BARCODE_LENGTH:
        return False, f"Invalid barcode format. Expected format: {BARCODE_PREFIX}XXXXXXXXX (min {MIN_BARCODE_LENGTH} chars)"
    
    return True, "OK"


def process_manufacturing(data):
    """
    Обработка данных производства
    """
    try:
        # Получаем данные
        logger.info(f"Получены данные: {data}")

        # Проверяем топик
        topic = data.get('topic', '')
        logger.info(f"Данные получены из топика: {topic}")
        
        # Проверка топика
        topic_allowed = False
        for allowed_topic in ALLOWED_TOPICS:
            if topic == allowed_topic or topic.startswith(allowed_topic):
                topic_allowed = True
                break
                
        if not topic_allowed:
            logger.warning(f"Данные получены из неразрешенного топика: {topic}")
            result = {
                'error': 'Unauthorized topic',
                'topic': topic,
                'allowed_topics': ALLOWED_TOPICS
            }
            print(json.dumps(result))
            return 1

        # Парсим payload как JSON строку
        payload_str = data.get('payload', '{}')
        payload_json = json.loads(payload_str)

        # Извлекаем штрихкод (серийный номер)
        barcode = payload_json.get('msg', '').strip()
        
        logger.info(f"Парсинг: barcode={barcode}, topic={topic}")

        # Валидация штрихкода
        is_valid, error_msg = validate_barcode(barcode)
        if not is_valid:
            logger.warning(error_msg)
            print(json.dumps({'error': error_msg}))
            return 1
        #Add new device to InvenTree
        process_new_device(barcode)

        # Записываем дату изготовления
        manager = RadiacodeManager()
        success = manager.WriteManufacturingDate(barcode)
        operation = 'manufacturing'
        date_field = 'manufacturing_date'
        
        if success:
            logger.info(f"Успешно записана {operation} дата для: {barcode} из топика: {topic}")
            response_data = {
                'status': 'success',
                'barcode': barcode,
                'topic': topic,
                'operation': operation,
                date_field: datetime.now().isoformat(),
                'message': f'{operation.capitalize()} date recorded successfully'
            }
            print(json.dumps(response_data))
            return 0
        else:
            logger.error(f"Ошибка записи {operation} даты для: {barcode}")
            print(json.dumps({'error': f'Failed to record {operation} date'}))
            return 1
            
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON payload: {e}")
        print(json.dumps({'error': 'Invalid JSON payload'}))
        return 1
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        print(json.dumps({'error': f'Server error: {str(e)}'}))
        return 1


if __name__ == '__main__':
    try:
        # Читаем данные из аргумента (от webhook)
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            # Или из stdin
            data = json.load(sys.stdin)
        
        exit_code = process_manufacturing(data)
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)