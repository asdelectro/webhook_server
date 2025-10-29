#!/usr/bin/env python3
import requests
import json
from typing import Optional, Dict, List

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

    # ===== Подметоды =====
    def get_manufacturer(self, data: Dict) -> Optional[str]:
        mfr = data.get("Manufacturer")
        if isinstance(mfr, dict):
            return mfr.get("Name")
        return str(mfr) if mfr else None    

    def get_description(self, data: Dict) -> Optional[str]:
        description = data.get("Description", {})
        return description.get("ProductDescription")

    def get_size(self, data: Dict) -> Optional[str]:
        for p in data.get("Parameters", []):
            name = p["ParameterText"].lower()
            if any(key in name for key in ["package / case", "size / dimension", "case size", "package case"]):
                return p["ValueText"]
        return None

    # ===== Основная функция =====
    def get_json_info(self, part_number: str) -> Optional[Dict]:
        """Возвращает данные в JSON-формате с ключами:
        DigiKey, Description, Manufacturer, Size
        
        Args:
            part_number: Номер компонента DigiKey
            
        Returns:
            dict: Словарь с данными компонента или None если не найден
        """
        data = self._get_product(part_number)
        if not data:
            return None
        return {
            "DigiKey": part_number,
            "Description": self.get_description(data),
            "Manufacturer": self.get_manufacturer(data),
            "Size": self.get_size(data),
        }


if __name__ == "__main__":
    api = DigiKeyClient(
        client_id="s72V1FevIthESyuv3HwWoG1ihutJcCdmfhnmwLjH6p1uAZ4J",
        client_secret="lXRuQUfdZvRDCOpqfTAnOjNUkjfIAudCg1f0xkTxbLcypSaXPCbuiGlcK9os62oR",
    )

    # 🧩 Тестовые артикула с Digi-Key
    test_parts = [
        "RC0402FR-0710KL", "CRCW06031M00FKEA",
        "GRM188R71C105KA12D", "C0603C104K5RAC7081",
        "LQG18HN10NJ00D", "NRS4018T4R7MDGJ",
        "LP2985A-33DBVR", "MP1584EN-LF-Z",
        "BC547BTA", "IRLZ44NPBF",
        "1N4007-T", "1N5819G",
        "497-16569-ND", "ATMEGA328P-PU-ND",
        "LTST-C190KRKT", "B3U-1000P",
        "ABLS-16.000MHZ-B4-T", "609-3329-ND",
    ]

    results: List[Dict] = []

    for part_number in test_parts:
        print(f"🔹 Проверяем: {part_number}")
        info = api.get_json_info(part_number)
        if info:
            results.append(info)
            print(f"  ✅ {info.get('Description', 'N/A')}")
        else:
            print("  ⚠️ Ошибка: компонент не найден")

    # Выводим итоговый JSON красиво
    print("\n=== JSON результат ===")
    print(json.dumps(results, indent=4, ensure_ascii=False))