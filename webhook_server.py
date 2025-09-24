from flask import Flask, request, jsonify
import logging
import json
from datetime import datetime, timedelta
from AzureConnector import RadiacodeManager

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация разрешенных топиков
MANUFACTURING_CONFIG = {
    'ALLOWED_TOPICS': [
        'production/ready',
        'sale/ready'
    ],
    'TOPIC_VALIDATION_ENABLED': True,  # Можно отключить для тестирования
    'BARCODE_PREFIX': 'RC-',
    'MIN_BARCODE_LENGTH': 10
}

# Создаем экземпляр менеджера
manager = RadiacodeManager()


@app.route('/', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    return jsonify({
        'status': 'OK',
        'service': 'Radiacode Manufacturing Server',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/device', methods=['POST'])
def handle_device_scan():
    """Основной endpoint для обработки данных сканера"""
    try:
        # Получаем данные от EMQX
        data = request.get_json()
        logger.info(f"Получены данные: {data}")

        # Проверяем топик (если включена валидация)
        topic = data.get('topic', '')
        logger.info(f"Данные получены из топика: {topic}")
        
        if MANUFACTURING_CONFIG['TOPIC_VALIDATION_ENABLED']:
            allowed_topics = MANUFACTURING_CONFIG['ALLOWED_TOPICS']
            
            # Проверяем точное совпадение или по паттерну
            topic_allowed = False
            for allowed_topic in allowed_topics:
                if topic == allowed_topic or topic.startswith(allowed_topic):
                    topic_allowed = True
                    break
                    
            if not topic_allowed:
                logger.warning(f"Данные получены из неразрешенного топика: {topic}")
                return jsonify({
                    'error': 'Unauthorized topic',
                    'topic': topic,
                    'allowed_topics': allowed_topics
                }), 403

        # Парсим payload как JSON строку
        payload_str = data.get('payload', '{}')
        payload_json = json.loads(payload_str)

        # Извлекаем штрихкод (серийный номер)
        barcode = payload_json.get('msg', '').strip()
        
        logger.info(f"Парсинг: barcode={barcode}, topic={topic}")

        # Валидация штрихкода
        if not barcode:
            logger.warning(f"Получен пустой штрихкод из payload: {payload_str}")
            return jsonify({'error': 'Barcode is required'}), 400

        # Дополнительная валидация формата штрихкода Radiacode
        barcode_prefix = MANUFACTURING_CONFIG['BARCODE_PREFIX']
        min_length = MANUFACTURING_CONFIG['MIN_BARCODE_LENGTH']
        
        if not barcode.startswith(barcode_prefix) or len(barcode) < min_length:
            logger.warning(f"Неверный формат штрихкода Radiacode: {barcode}")
            return jsonify({
                'error': f'Invalid barcode format. Expected format: {barcode_prefix}XXXXXXXXX (min {min_length} chars)'
            }), 400

        # Выбираем действие в зависимости от топика
        if topic == 'production/ready':
            # Записываем дату изготовления
            success = manager.WriteManufacturingDate(barcode)
            operation = 'manufacturing'
            date_field = 'manufacturing_date'
        elif topic == 'sale/ready':
            # Записываем дату продажи
            success = manager.WriteSaleDate(barcode)
            operation = 'sale'
            date_field = 'sale_date'
        else:
            # Этот случай не должен произойти из-за проверки топика выше
            logger.error(f"Неизвестный топик: {topic}")
            return jsonify({'error': 'Unknown topic'}), 500
        
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
            return jsonify(response_data)
        else:
            logger.error(f"Ошибка записи {operation} даты для: {barcode}")
            return jsonify({'error': f'Failed to record {operation} date'}), 500

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON payload: {e}")
        return jsonify({'error': 'Invalid JSON payload'}), 400
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/device/<serial>', methods=['GET'])
def get_manufacturing_date(serial):
    """GET endpoint для получения даты изготовления по серийному номеру"""
    try:
        if not serial or not serial.strip():
            return jsonify({"success": False, "message": "Серийный номер пустой"})

        serial = serial.strip()
        logger.info(f"Запрос даты изготовления для: {serial}")

        # Читаем дату изготовления
        manufacturing_date = manager.ReadManufacturingDate(serial)
        
        if manufacturing_date is None:
            return jsonify({
                "success": False,
                "message": "Устройство не найдено",
                "serial": serial
            }), 404

        # Проверяем, что дата изготовления не старше 1 часа
        current_time = datetime.now()
        time_diff = current_time - manufacturing_date
        
        # Если разница меньше 1 часа (3600 секунд)
        is_fresh = time_diff.total_seconds() <= 3600
        
        return jsonify({
            "success": True,
            "serial": serial,
            "manufacturing_date": manufacturing_date.isoformat(),
            "is_fresh": is_fresh,
            "age_seconds": int(time_diff.total_seconds()),
            "age_minutes": int(time_diff.total_seconds() / 60),
            "status": "ready" if is_fresh else "expired"
        })

    except Exception as e:
        logger.error(f"Ошибка получения даты изготовления для {serial}: {e}")
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Получение списка недавно изготовленных устройств"""
    try:
        # Получаем параметры из запроса
        limit = request.args.get('limit', 10, type=int)
        minutes = request.args.get('minutes', 30, type=int)
        
        # Используем новый UTC метод из RadiacodeManager
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
        
        return jsonify({
            'success': True,
            'devices': devices,
            'count': len(devices),
            'message': f'Found {len(devices)} devices manufactured in last {minutes} minutes'
        })

    except Exception as e:
        logger.error(f"Ошибка получения устройств: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'devices': []
        }), 500
    

@app.route('/api/getalldevices/<serial>', methods=['GET'])
def get_device_by_serial(serial):
    """
    GET endpoint для получения ВСЕХ полей устройства по серийному номеру
    URL: localhost:3000/api/devices/RC-103G-001665
    """
    try:
        if not serial or not serial.strip():
            return jsonify({
                "success": False, 
                "message": "Серийный номер пустой",
                "serial": serial
            }), 400

        serial = serial.strip()
        logger.info(f"Запрос всех данных для устройства: {serial}")

        # Используем функцию ReadManufacturingDateAll
        device_data = manager.ReadManufacturingDateAll(serial)
        
        if device_data is None:
            return jsonify({
                "success": False,
                "message": "Устройство не найдено",
                "serial": serial
            }), 404

        return jsonify({
            "success": True,
            "serial": serial,
            "device_data": device_data,
            "message": f"Найдено устройство {serial}"
        })

    except Exception as e:
        logger.error(f"Ошибка получения данных для {serial}: {e}")
        return jsonify({
            "success": False,
            "message": f"Ошибка сервера: {str(e)}",
            "serial": serial
        }), 500    

@app.route('/api/check-status', methods=['POST'])
def check_device_status():
    """POST endpoint для проверки статуса устройства по штрихкоду (для совместимости)"""
    try:
        data = request.get_json()
        barcode = data.get("barcode", "").strip()

        if not barcode:
            return jsonify({"success": False, "message": "Штрихкод пустой"})

        # Читаем дату изготовления
        manufacturing_date = manager.ReadManufacturingDate(barcode)
        
        if manufacturing_date is None:
            return jsonify({
                "success": True,
                "scanned": False,
                "message": "Устройство не найдено или не отсканировано"
            })

        # Проверяем, что дата изготовления не старше 1 часа
        current_time = datetime.now()
        time_diff = current_time - manufacturing_date
        
        # Если разница меньше 1 часа (3600 секунд)
        if time_diff.total_seconds() <= 3600:
            return jsonify({
                "success": True,
                "scanned": True,
                "status": "ready",
                "manufacturing_date": manufacturing_date.isoformat(),
                "message": f"Устройство готово (отсканировано {int(time_diff.total_seconds())} секунд назад)"
            })
        else:
            return jsonify({
                "success": True,
                "scanned": True,
                "status": "expired",
                "manufacturing_date": manufacturing_date.isoformat(),
                "message": f"Устройство отсканировано более часа назад ({int(time_diff.total_seconds() / 60)} минут)"
            })

    except Exception as e:
        logger.error(f"Ошибка проверки статуса: {e}")
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Получение статистики (упрощенная версия)"""
    try:
        return jsonify({
            'date': datetime.now().date().isoformat(),
            'service': 'Radiacode Manufacturing Server',
            'status': 'active'
        })
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("🚀 Запуск Radiacode Manufacturing сервера...")
    logger.info("📋 Доступные endpoints:")
    logger.info("   GET  /                      - Проверка здоровья")
    logger.info("   POST /webhook/device        - Прием данных от EMQX")
    logger.info("   GET  /api/device/<serial>   - Получение даты изготовления по серийнику")
    logger.info("   POST /api/check-status      - Проверка статуса (совместимость)")
    logger.info("   GET  /api/stats             - Статистика")
    logger.info("   GET  /api/devices           - Совместимость (возвращает пустой список)")

    # Проверка подключения к БД при запуске
    try:
        # Проверяем, что класс RadiacodeManager импортирован и работает
        logger.info("✅ RadiacodeManager успешно импортирован из AzureConnector")
        logger.info(f"✅ Manager создан: {type(manager).__name__}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RadiacodeManager: {e}")

    app.run(host='0.0.0.0', port=3000, debug=False)