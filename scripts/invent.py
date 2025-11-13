#!/usr/bin/env python3
import sys
import json
import re
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from logger_config import get_invent_logger
from Digitkey_API import DigiKeyClient

logger = get_invent_logger()

RS = '\x1e'  # Record Separator
GS = '\x1d'  # Group Separator
EOT = '\x04' # End of Transmission

# ===== Настройка клиента Digi-Key =====
DIGIKEY_CLIENT_ID = "s72V1FevIthESyuv3HwWoG1ihutJcCdmfhnmwLjH6p1uAZ4J"
DIGIKEY_CLIENT_SECRET = "lXRuQUfdZvRDCOpqfTAnOjNUkjfIAudCg1f0xkTxbLcypSaXPCbuiGlcK9os62oR"
dk_client = DigiKeyClient(DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET)

# ===== Настройка InvenTree =====
INVENTREE_URL = "http://192.168.88.132:8080"  # 
INVENTREE_TOKEN = "inv-3d1c37e2156c24a5af7e384099de32dfd12e522d-20251015"
INVENTREE_LOCATION_ID = 11
INVENTREE_CATEGORY = "RnD Components"

def send_to_inventree(part_data: dict, quantity: int) -> bool:
    """
    Отправляет данные о компоненте в InvenTree через плагин StockMaster Components.
    
    Args:
        part_data: Словарь с данными компонента (DigiKey, Description, Manufacturer, Size)
        quantity: Количество компонентов
        
    Returns:
        bool: True если успешно, False если ошибка
    """
    url = f"{INVENTREE_URL}/plugin/stockmaster-components/add-to-queue/"
    
    # Добавляем quantity в part_data
    part_data_with_qty = part_data.copy()
    part_data_with_qty['quantity'] = quantity
    
    payload = {
        "part_data": part_data_with_qty,
        "location_id": INVENTREE_LOCATION_ID,
        "category_name": INVENTREE_CATEGORY
    }
    
    headers = {
        "Authorization": f"Token {INVENTREE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"📤 Отправка в InvenTree: {part_data.get('DigiKey')} x{quantity}")
        logger.info(f"🌐 URL: {url}")
        logger.info(f"📦 Payload: {json.dumps(payload, ensure_ascii=False)}")
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        logger.info(f"📊 HTTP Status: {response.status_code}")
        logger.info(f"📄 Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        logger.info(f"📝 Response: {response.text}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('success'):
                    logger.info(f"✅ Добавлено в очередь InvenTree! Queue ID: {data.get('queue_id')}")
                    return True
                else:
                    logger.error(f"❌ InvenTree вернул ошибку: {data.get('error')}")
                    return False
            except ValueError as e:
                logger.error(f"❌ Ошибка парсинга JSON ответа: {e}")
                return False
        else:
            logger.error(f"❌ HTTP ошибка {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка подключения к InvenTree: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при отправке в InvenTree: {e}")
        return False

def parse_digikey_payload(payload_str):
    payload_str = payload_str.replace(EOT, '')
    records = payload_str.split(RS)
    return [record for record in records if record.strip()]

def extract_part_qty(record):
    part_number = None
    quantity = None
    fields = record.split(GS)
    for field in fields:
        if field.startswith('P'):
            part_number = field[1:]
        elif field.startswith('Q'):
            quantity = field[1:]
    return part_number or 'N/A', quantity or 'N/A'

def process_sale(data):
    logger.info(f"Received data: {data}")

    try:
        raw_payload = data.get('payload', '{}')

        # Экранируем управляющие символы для json.loads
        safe_payload = re.sub(r'[\x00-\x1f]', lambda m: '\\u%04x' % ord(m.group()), raw_payload)
        payload = json.loads(safe_payload)
        msg = payload.get('msg', '')

        # Проверяем, это ли структурированный DigiKey баркод
        if msg.startswith('[)>') or RS in msg or GS in msg:
            # ===== ОБРАБОТКА DIGIKEY БАРКОДА =====
            logger.info("🏷️ Обнаружен структурированный DigiKey баркод")
            
            # Разделяем header и остальную часть
            if msg.startswith('[)>'):
                header, rest = msg.split('\x1e', 1)
            else:
                header, rest = '', msg

            records = parse_digikey_payload(rest)
            data_record = records[0] if records else ''
            part_number, quantity_str = extract_part_qty(data_record)

            # Преобразуем количество в число
            try:
                quantity = int(quantity_str) if quantity_str != 'N/A' else 1
            except ValueError:
                quantity = 1
                logger.warning(f"⚠️ Не удалось распознать количество '{quantity_str}', используем 1")

            # Получаем данные через DigiKey API
            if part_number != 'N/A':
                logger.info(f"🔍 Запрос данных о компоненте {part_number} из DigiKey API...")
                
                part_info = dk_client.get_json_info(part_number)
                
                if part_info:
                    manufacturer = part_info.get("Manufacturer", "N/A")
                    description = part_info.get("Description", "N/A")
                    size = part_info.get("Size", "N/A")
                    
                    # Логируем полученные данные
                    logger.info(
                        f"📦 Digi-Key Header: {header} | "
                        f"Part Number: {part_number} | "
                        f"Quantity: {quantity} | "
                        f"Manufacturer: {manufacturer} | "
                        f"Description: {description} | "
                        f"Size: {size}"
                    )
                    
                    # Отправляем в InvenTree
                    logger.info("=" * 60)
                    logger.info("🚀 Начинаем отправку в InvenTree...")
                    success = send_to_inventree(part_info, quantity)
                    logger.info("=" * 60)
                    
                    if success:
                        logger.info("🎉 Компонент успешно добавлен в очередь InvenTree!")
                        logger.info("💡 Откройте плагин в браузере и нажмите 'Обработать' для создания компонента")
                    else:
                        logger.error("❌ Не удалось добавить компонент в InvenTree")
                        
                else:
                    logger.error(f"❌ Не удалось получить данные о компоненте {part_number} из DigiKey API")
            else:
                logger.warning("⚠️ Part number не найден в данных DigiKey сканера")
                
            return []
            
        else:
            # ===== ОБРАБОТКА ПРОСТОГО БАРКОДА =====
            logger.info("📋 Обнаружен простой баркод (не DigiKey)")
            
            # Используем весь msg как part number
            simple_barcode = msg.strip()
            quantity = 1  # По умолчанию количество = 1
            
            logger.info(f"📦 Простой баркод: {simple_barcode} | Quantity: {quantity}")
            
            # Создаем простую структуру данных без DigiKey API
            simple_part_info = {
                "DigiKey": simple_barcode,
                "Description": f"Компонент {simple_barcode}",
                "Manufacturer": "Unknown",
                "Size": "N/A"
            }
            
            logger.info(f"📋 Создана структура для простого баркода: {simple_part_info}")
            
            # Отправляем в InvenTree
            logger.info("=" * 60)
            logger.info("🚀 Отправляем простой баркод в InvenTree...")
            success = send_to_inventree(simple_part_info, quantity)
            logger.info("=" * 60)
            
            if success:
                logger.info(f"🎉 Простой баркод {simple_barcode} успешно добавлен в очередь InvenTree!")
                logger.info("💡 Откройте плагин в браузере и нажмите 'Обработать' для создания компонента")
            else:
                logger.error(f"❌ Не удалось добавить простой баркод {simple_barcode} в InvenTree")
                
            return []
        
    except Exception as e:
        logger.error(f"Error parsing payload: {e}", exc_info=True)
        return []

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)

        process_sale(data)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)