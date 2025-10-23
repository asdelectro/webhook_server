#!/usr/bin/env python3
import requests
from typing import Optional, Dict

class DigiKeyClient:
    BASE_URL = "https://api.digikey.com"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None

    def _get_token(self):
        """Получить токен доступа"""
        url = f"{self.BASE_URL}/v1/oauth2/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        r = requests.post(url, data=data)
        r.raise_for_status()
        self.access_token = r.json()["access_token"]

    def _headers(self):
        if not self.access_token:
            self._get_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

    def _get_product(self, part_number: str) -> Optional[Dict]:
        """Получить данные компонента"""
        url = f"{self.BASE_URL}/products/v4/search/{part_number}/productdetails"
        r = requests.get(url, headers=self._headers())
        if r.status_code == 200:
            return r.json().get("Product", {})
        return None

    # ===== Подметоды для извлечения данных =====
    def get_manufacturer(self, data: Dict) -> Optional[str]:
        """Производитель"""
        mfr = data.get("Manufacturer")
        if isinstance(mfr, dict):
            return mfr.get("Name")
        return str(mfr) if mfr else None

    def get_nominal(self, data: Dict) -> Optional[str]:
        """Номинал (емкость/сопротивление/индуктивность)"""
        for p in data.get("Parameters", []):
            name = p["ParameterText"].lower()
            if name in ["capacitance", "resistance", "inductance"]:
                return p["ValueText"]
        return None

    def get_capacitance(self, data: Dict) -> Optional[str]:
        for p in data.get("Parameters", []):
            if p["ParameterText"].lower() == "capacitance":
                return p["ValueText"]
        return None

    def get_power(self, data: Dict) -> Optional[str]:
        for p in data.get("Parameters", []):
            if "power" in p["ParameterText"].lower():
                return p["ValueText"]
        return None

    def get_voltage(self, data: Dict) -> Optional[str]:
        for p in data.get("Parameters", []):
            if "voltage" in p["ParameterText"].lower():
                return p["ValueText"]
        return None

    def get_quantity(self, data: Dict) -> Optional[int]:
        return data.get("QuantityAvailable")

    def get_basic_info(self, part_number: str) -> Optional[Dict]:
        """Универсальный метод — возвращает все ключевые параметры"""
        data = self._get_product(part_number)
        if not data:
            return None
        return {
            "manufacturer": self.get_manufacturer(data),
            "nominal": self.get_nominal(data),
            "capacitance": self.get_capacitance(data),
            "power": self.get_power(data),
            "voltage": self.get_voltage(data),
            "quantity": self.get_quantity(data),
        }



if __name__ == "__main__":
    api = DigiKeyClient(
        client_id="s72V1FevIthESyuv3HwWoG1ihutJcCdmfhnmwLjH6p1uAZ4J",
        client_secret="lXRuQUfdZvRDCOpqfTAnOjNUkjfIAudCg1f0xkTxbLcypSaXPCbuiGlcK9os62oR",
    )

    part_number = "1276-CL05A474KO5NNNCTR-ND"
    info = api.get_basic_info(part_number)

    if info:
        print("Производитель:", info["manufacturer"])
        print("Номинал:", info["nominal"])
        print("Ёмкость:", info["capacitance"])
        print("Мощность:", info["power"])
        print("Напряжение:", info["voltage"])
        print("В наличии:", info["quantity"])
    else:
        print("Ошибка: компонент не найден")
