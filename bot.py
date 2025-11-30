#!/usr/bin/env python3
"""
API'den veri çeken ve adresleri kaydeden bot
"""

import requests
import json
import os
from datetime import datetime
from typing import List, Dict, Optional


class AddressBot:
    def __init__(self, api_url: str, output_file: str = "addresses.json"):
        """
        Bot'u başlatır
        
        Args:
            api_url: Veri çekilecek API endpoint'i
            output_file: Adreslerin kaydedileceği dosya
        """
        self.api_url = api_url
        self.output_file = output_file
        self.addresses = self.load_addresses()
    
    def load_addresses(self) -> List[Dict]:
        """Kaydedilmiş adresleri yükler"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        return []
    
    def save_addresses(self):
        """Adresleri dosyaya kaydeder"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.addresses, f, ensure_ascii=False, indent=2)
        print(f"✓ {len(self.addresses)} adres kaydedildi: {self.output_file}")
    
    def fetch_data(self, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        API'den veri çeker
        
        Args:
            params: API isteği için parametreler
            
        Returns:
            API'den dönen veri veya None
        """
        try:
            response = requests.get(self.api_url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"✗ API hatası: {e}")
            return None
    
    def extract_addresses(self, data: Dict) -> List[Dict]:
        """
        API verisinden adresleri çıkarır
        
        Bu fonksiyon API yapısına göre özelleştirilmelidir
        
        Args:
            data: API'den gelen ham veri
            
        Returns:
            Çıkarılan adres listesi
        """
        addresses = []
        
        # Örnek: Eğer API'den gelen veri bir liste ise
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Adres alanını bul (örnek: 'address', 'wallet', 'adres' vb.)
                    address = item.get('address') or item.get('wallet') or item.get('adres')
                    if address:
                        addresses.append({
                            'address': address,
                            'timestamp': datetime.now().isoformat(),
                            'data': item  # Orijinal veriyi de sakla
                        })
        
        # Örnek: Eğer API'den gelen veri bir dict ise ve içinde 'results' gibi bir alan varsa
        elif isinstance(data, dict):
            # 'results', 'data', 'addresses' gibi alanları kontrol et
            items = data.get('results') or data.get('data') or data.get('addresses') or []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        address = item.get('address') or item.get('wallet') or item.get('adres')
                        if address:
                            addresses.append({
                                'address': address,
                                'timestamp': datetime.now().isoformat(),
                                'data': item
                            })
        
        return addresses
    
    def is_duplicate(self, address: str) -> bool:
        """Adresin daha önce kaydedilip kaydedilmediğini kontrol eder"""
        return any(addr.get('address') == address for addr in self.addresses)
    
    def add_addresses(self, new_addresses: List[Dict]):
        """
        Yeni adresleri ekler (duplikasyon kontrolü ile)
        
        Args:
            new_addresses: Eklenecek adres listesi
        """
        added_count = 0
        for addr in new_addresses:
            address_str = addr.get('address')
            if address_str and not self.is_duplicate(address_str):
                self.addresses.append(addr)
                added_count += 1
            elif address_str:
                print(f"⚠ Adres zaten kayıtlı: {address_str}")
        
        if added_count > 0:
            print(f"✓ {added_count} yeni adres eklendi")
        else:
            print("ℹ Yeni adres bulunamadı")
    
    def run(self, params: Optional[Dict] = None):
        """
        Bot'u çalıştırır: API'den veri çeker, adresleri çıkarır ve kaydeder
        
        Args:
            params: API isteği için parametreler
        """
        print(f"🔄 API'den veri çekiliyor: {self.api_url}")
        data = self.fetch_data(params)
        
        if data is None:
            print("✗ Veri çekilemedi")
            return
        
        print(f"✓ Veri alındı, adresler çıkarılıyor...")
        addresses = self.extract_addresses(data)
        
        if addresses:
            self.add_addresses(addresses)
            self.save_addresses()
        else:
            print("⚠ Veri içinde adres bulunamadı")


def main():
    """Ana fonksiyon - API URL'i ve parametreleri buradan ayarlanabilir"""
    
    # API URL'ini buraya ekleyin
    API_URL = os.getenv('API_URL', 'https://api.example.com/addresses')
    
    # İsteğe bağlı parametreler
    params = {
        # 'page': 1,
        # 'limit': 100,
    }
    
    bot = AddressBot(api_url=API_URL)
    bot.run(params=params)


if __name__ == "__main__":
    main()
