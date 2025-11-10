import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os
from dotenv import load_dotenv
import base64
import logging
from pathlib import Path
from datetime import datetime, timezone
import struct
import json

load_dotenv()

# Настройка логирования - ТОЛЬКО в файл, БЕЗ StreamHandler
log_dir = Path('/home/asd/webhook_server/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'azure_connector.log', encoding='utf-8')
        # StreamHandler() УБРАН - логи НЕ идут в stdout
    ]
)
logger = logging.getLogger(__name__)


class RadiacodeManager:
    """
    Manager class for Radiacode device database operations
    """

    def __init__(self):
        self.MYSQL_HOST = os.getenv("MYSQL_HOST")
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
        self.MYSQL_USERNAME = os.getenv("MYSQL_USERNAME")
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

    def _get_connection(self):
        """Create and return database connection"""
        return mysql.connector.connect(
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            user=self.MYSQL_USERNAME,
            password=self.MYSQL_PASSWORD,
            database=self.MYSQL_DATABASE,
            ssl_disabled=True,
            autocommit=True,
        )

    def _check_device_exists(self, serial):
        """
        Check if device with given serial number exists

        Args:
            serial: device serial number (str)

        Returns:
            bool: True if device exists, False otherwise
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT SerialNumber, ManufDate, SaleDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                serial_num, manuf_date, sale_date = result
                logger.info(f"Device found: {serial_num}")
                logger.info(f"Current ManufDate: {manuf_date.isoformat() if manuf_date else 'Not set'}")
                logger.info(f"Current SaleDate: {sale_date.isoformat() if sale_date else 'Not set'}")
                return True
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def WriteManufacturingDate(self, serial):
        """
        Write current server time as manufacturing date for specified serial number

        Args:
            serial: device serial number (str)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_device_exists(serial):
            return False

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info(f"Will set ManufDate to: {current_time.isoformat()}")

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            UPDATE radiacode 
            SET ManufDate = %s
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (current_time, serial))

            if cursor.rowcount > 0:
                logger.info(f"Manufacturing date updated for {serial}: {current_time.isoformat()}")
                return True
            else:
                logger.warning(f"Update failed for {serial}")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def WriteSaleDate(self, serial):
        """
        Write current server time as sale date for specified serial number

        Args:
            serial: device serial number (str)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_device_exists(serial):
            return False

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info(f"Will set SaleDate to: {current_time.isoformat()}")

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            UPDATE radiacode 
            SET SaleDate = %s
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (current_time, serial))

            if cursor.rowcount > 0:
                logger.info(f"Sale date updated for {serial}: {current_time.isoformat()}")
                return True
            else:
                logger.warning(f"Update failed for {serial}")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def ReadManufacturingDate(self, serial):
        """
        Read manufacturing date for specified serial number

        Args:
            serial: device serial number (str)

        Returns:
            datetime or None: manufacturing date if found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT ManufDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                manuf_date = result[0]
                logger.info(f"Manufacturing date for {serial}: {manuf_date.isoformat() if manuf_date else 'Not set'}")
                return manuf_date
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def _parse_calibration_data(self, calibration_hex):
        """
        Parse calibration data and extract Ti-61 and Cs-60 float32 values
        
        Args:
            calibration_hex: hex string of calibration data
            
        Returns:
            dict: {'Ti': float_value, 'Cs': float_value} or None if patterns not found
        """
        try:
            if not calibration_hex:
                logger.warning("Calibration data is empty")
                return None
                
            result = {}
            
            # Ищем паттерн для Ti-61: 01006100
            ti_pattern = '01006100'
            ti_pos = calibration_hex.find(ti_pattern)
            
            if ti_pos != -1:
                # Читаем следующие 4 байта (8 hex символов) после паттерна
                ti_hex = calibration_hex[ti_pos + len(ti_pattern):ti_pos + len(ti_pattern) + 8]
                # Конвертируем hex в bytes и затем в float32
                ti_bytes = bytes.fromhex(ti_hex)
                ti_value = struct.unpack('<f', ti_bytes)[0]  # '<f' = little-endian float
                result['Ti'] = round(ti_value, 2)
                logger.info(f"Found Ti-61: {ti_hex} = {ti_value}")
            else:
                logger.warning("Ti-61 pattern (01006100) not found")
                result['Ti'] = None
            
            # Ищем паттерн для Cs-60: 01006000
            cs_pattern = '01006000'
            cs_pos = calibration_hex.find(cs_pattern)
            
            if cs_pos != -1:
                # Читаем следующие 4 байта (8 hex символов) после паттерна
                cs_hex = calibration_hex[cs_pos + len(cs_pattern):cs_pos + len(cs_pattern) + 8]
                # Конвертируем hex в bytes и затем в float32
                cs_bytes = bytes.fromhex(cs_hex)
                cs_value = struct.unpack('<f', cs_bytes)[0]  # '<f' = little-endian float
                result['Cs'] = round(cs_value, 2)
                logger.info(f"Found Cs-60: {cs_hex} = {cs_value}")
            else:
                logger.warning("Cs-60 pattern (01006000) not found")
                result['Cs'] = None
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing calibration data: {e}")
            return None

    def ReadManufacturingDateAll(self, serial):
        """
        Read ALL fields for specified serial number and parse calibration data

        Args:
            serial: device serial number (str)

        Returns:
            dict or None: all device fields with parsed calibration, None if not found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor(dictionary=True)

            query = """
            SELECT * 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                logger.info(f"All data for {serial}: found {len(result)} fields")
                
                # Конвертируем все значения для JSON совместимости
                formatted_result = {}
                calibration_hex = None
                
                for key, value in result.items():
                    if isinstance(value, datetime):
                        formatted_result[key] = value.isoformat()
                        logger.debug(f"  {key}: {value.isoformat()}")
                    elif isinstance(value, bytes):
                        # Сохраняем hex для CalibrationData
                        if key == 'CalibrationData':
                            calibration_hex = value.hex().upper()
                            formatted_result[key] = calibration_hex
                            logger.debug(f"  {key}: <bytes data, length: {len(value)}>")
                        else:
                            formatted_result[key] = base64.b64encode(value).decode('utf-8')
                            logger.debug(f"  {key}: <bytes data, length: {len(value)}>")
                    elif value is None:
                        formatted_result[key] = None
                        logger.debug(f"  {key}: None")
                    else:
                        formatted_result[key] = value
                        logger.debug(f"  {key}: {value}")
                
                # Парсим калибровочные данные
                        if calibration_hex:
                            calibration_values = self._parse_calibration_data(calibration_hex)
                            if calibration_values:
                                ti_val = calibration_values.get('Ti', 0.0)
                                cs_val = calibration_values.get('Cs', 0.0)
                                
                                # Безопасное форматирование с проверкой на None
                                ti_str = f"{ti_val:.2f}" if ti_val is not None else "N/A"
                                cs_str = f"{cs_val:.2f}" if cs_val is not None else "N/A"
                                
                                formatted_result['CalibrationParsed'] = f"Ti={ti_str}, Cs={cs_str}"
                                formatted_result['Ti_value'] = ti_val
                                formatted_result['Cs_value'] = cs_val
                            else:
                                formatted_result['CalibrationParsed'] = "Parse failed"
                        
                return formatted_result
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def ReadSaleDate(self, serial):
        """
        Read sale date for specified serial number

        Args:
            serial: device serial number (str)

        Returns:
            datetime or None: sale date if found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT SaleDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                sale_date = result[0]
                logger.info(f"Sale date for {serial}: {sale_date.isoformat() if sale_date else 'Not set'}")
                return sale_date
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def GetRecentDevices(self, minutes=30, limit=30):
        """
        Get devices that were manufactured in the last N minutes (using UTC time)

        Args:
            minutes: number of minutes to look back (default: 30)
            limit: maximum number of devices to return (default: 30)

        Returns:
            list: List of dictionaries with device information, or empty list on error
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()
            query = """
            SELECT SerialNumber, ManufDate, SaleDate
            FROM radiacode
            WHERE ManufDate >= UTC_TIMESTAMP() - INTERVAL %s MINUTE
            ORDER BY ManufDate DESC
            LIMIT %s
            """

            cursor.execute(query, (minutes, limit))
            results = cursor.fetchall()

            devices = []
            current_time_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            
            for result in results:
                serial, manuf_date, sale_date = result
                
                if manuf_date:
                    time_diff = current_time_utc - manuf_date
                    age_minutes = int(time_diff.total_seconds() / 60)
                    age_seconds = int(time_diff.total_seconds())
                    
                    status = "ready" if time_diff.total_seconds() <= 36000 else "expired"
                    
                    device_info = {
                        'serial': serial,
                        'manufacturing_date': manuf_date,
                        'sale_date': sale_date,
                        'age_minutes': age_minutes,
                        'age_seconds': age_seconds,
                        'status': status
                    }
                    devices.append(device_info)

            logger.info(f"Found {len(devices)} devices manufactured in last {minutes} minutes (UTC)")
            return devices

        except Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"General error: {e}")
            return []
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()


# Example usage
if __name__ == "__main__":
    manager = RadiacodeManager()

    # Write manufacturing date
   # manager.WriteManufacturingDate("RC-103G-001665")

    # Write sale date
  #  manager.WriteSaleDate("RC-103G-001665")

    # Read manufacturing date
   # manager.ReadManufacturingDate("RC-103G-001665")

    # Read sale date
   # manager.ReadSaleDate("RC-103G-001665")

   
    result = manager.ReadManufacturingDateAll("RC-103-015148")
    #result = manager.ReadManufacturingDateAll("RC-102-006783")
    print(json.dumps(result, indent=2, ensure_ascii=False))