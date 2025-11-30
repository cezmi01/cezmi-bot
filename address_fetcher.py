# -*- coding: utf-8 -*-
"""
BTCTurk ve Paribu Deposit Adresi Çekme Scripti
----------------------------------------------
Bu script BTCTurk ve Paribu API'lerinden deposit adreslerini çeker
ve config.json dosyasını günceller.
"""

import os
import json
import hmac
import time
import base64
import hashlib
import asyncio
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path("config.json")


class BTCTurkAPI:
    """BTCTurk Pro API client"""
    BASE_URL = "https://api.btcturk.com"
    
    def __init__(self):
        self.api_key = os.getenv("BTCTURK_KEY", "").strip()
        self.api_secret = os.getenv("BTCTURK_SECRET", "").strip()
    
    def _generate_signature(self, api_key: str, api_secret: str, nonce: str) -> str:
        """Generate BTCTurk API signature"""
        message = f"{api_key}{nonce}"
        signature = hmac.new(
            base64.b64decode(api_secret),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')
    
    async def get_deposit_address(self, session: aiohttp.ClientSession, currency: str):
        """Get deposit address for a specific currency"""
        try:
            nonce = str(int(time.time() * 1000))
            signature = self._generate_signature(self.api_key, self.api_secret, nonce)
            
            headers = {
                "X-PCK": self.api_key,
                "X-Stamp": nonce,
                "X-Signature": signature,
            }
            
            url = f"{self.BASE_URL}/api/v1/users/balances"
            
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"BTCTurk API error: {resp.status}")
                    return None
                
                data = await resp.json()
                
                # Belirli currency için deposit address bilgisini bul
                for item in data:
                    if item.get('asset') == currency or item.get('assetCode') == currency:
                        # Deposit address endpoint'i farklı olabilir
                        return await self._get_crypto_address(session, currency, headers)
                
                return None
                
        except Exception as e:
            print(f"BTCTurk error for {currency}: {e}")
            return None
    
    async def _get_crypto_address(self, session, currency, headers):
        """Get crypto deposit address - BTCTurk specific endpoint"""
        try:
            # BTCTurk'te deposit address almak için özel endpoint
            url = f"{self.BASE_URL}/api/v1/users/crypto/deposit/address/{currency}"
            
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"BTCTurk crypto address error: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text}")
                    return None
                
                data = await resp.json()
                return data
                
        except Exception as e:
            print(f"BTCTurk crypto address error for {currency}: {e}")
            return None


class ParibuAPI:
    """Paribu API client"""
    BASE_URL = "https://www.paribu.com/api"
    
    def __init__(self):
        self.api_key = os.getenv("PARIBU_KEY", "").strip()
        self.api_secret = os.getenv("PARIBU_SECRET", "").strip()
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate Paribu API signature"""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def get_deposit_address(self, session: aiohttp.ClientSession, currency: str):
        """Get deposit address for a specific currency"""
        try:
            timestamp = str(int(time.time() * 1000))
            path = f"/v1/deposit/address/{currency}"
            signature = self._generate_signature(timestamp, "GET", path)
            
            headers = {
                "X-PRB-APIKEY": self.api_key,
                "X-PRB-SIGNATURE": signature,
                "X-PRB-TIMESTAMP": timestamp,
            }
            
            url = f"{self.BASE_URL}{path}"
            
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"Paribu API error: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text}")
                    return None
                
                data = await resp.json()
                return data
                
        except Exception as e:
            print(f"Paribu error for {currency}: {e}")
            return None


async def fetch_addresses():
    """Fetch deposit addresses from both exchanges"""
    btcturk = BTCTurkAPI()
    paribu = ParibuAPI()
    
    # Config'den mevcut yapıyı oku
    if not CONFIG_PATH.exists():
        print("config.json bulunamadı!")
        return
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    async with aiohttp.ClientSession() as session:
        for item in config:
            symbol = item['symbol']
            network = item['network']
            
            print(f"\n{'='*50}")
            print(f"Fetching addresses for {symbol} ({network})")
            print(f"{'='*50}")
            
            # BTCTurk address
            if 'YOUR_BTCTURK' in item['btcturk']['address']:
                print(f"BTCTurk {symbol} ({network}) adresi çekiliyor...")
                btc_data = await btcturk.get_deposit_address(session, symbol)
                if btc_data:
                    print(f"BTCTurk data: {btc_data}")
                    # Address'i parse et ve kaydet
                    # BTCTurk API response yapısına göre düzenle
                    if isinstance(btc_data, dict):
                        address = btc_data.get('address') or btc_data.get('depositAddress')
                        memo = btc_data.get('tag') or btc_data.get('memo')
                        if address:
                            item['btcturk']['address'] = address
                            if memo:
                                item['btcturk']['memo'] = memo
                            print(f"✓ BTCTurk {symbol} address: {address}")
                else:
                    print(f"✗ BTCTurk {symbol} address alınamadı")
            else:
                print(f"✓ BTCTurk {symbol} address zaten mevcut: {item['btcturk']['address']}")
            
            # Paribu address
            if 'YOUR_PARIBU' in item['paribu']['address']:
                print(f"Paribu {symbol} ({network}) adresi çekiliyor...")
                paribu_data = await paribu.get_deposit_address(session, symbol)
                if paribu_data:
                    print(f"Paribu data: {paribu_data}")
                    # Address'i parse et ve kaydet
                    # Paribu API response yapısına göre düzenle
                    if isinstance(paribu_data, dict):
                        address = paribu_data.get('address') or paribu_data.get('depositAddress')
                        memo = paribu_data.get('tag') or paribu_data.get('memo')
                        if address:
                            item['paribu']['address'] = address
                            if memo:
                                item['paribu']['memo'] = memo
                            print(f"✓ Paribu {symbol} address: {address}")
                else:
                    print(f"✗ Paribu {symbol} address alınamadı")
            else:
                print(f"✓ Paribu {symbol} address zaten mevcut: {item['paribu']['address']}")
            
            # Rate limiting
            await asyncio.sleep(1)
    
    # Config'i güncelle
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*50}")
    print("✓ config.json güncellendi!")
    print(f"{'='*50}")


async def manual_update():
    """Manuel address ekleme modu"""
    print("Manuel Address Güncelleme Modu")
    print("=" * 50)
    
    if not CONFIG_PATH.exists():
        print("config.json bulunamadı!")
        return
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    for idx, item in enumerate(config):
        symbol = item['symbol']
        network = item['network']
        
        print(f"\n{idx + 1}. {symbol} ({network})")
        print("-" * 40)
        
        # BTCTurk
        current_btc = item['btcturk']['address']
        if 'YOUR_BTCTURK' in current_btc:
            print(f"BTCTurk {symbol} address eksik!")
            addr = input(f"BTCTurk {symbol} ({network}) address girin (Enter=skip): ").strip()
            if addr:
                item['btcturk']['address'] = addr
                memo = input(f"BTCTurk {symbol} memo/tag (Enter=none): ").strip()
                if memo:
                    item['btcturk']['memo'] = memo
        else:
            print(f"BTCTurk: {current_btc}")
        
        # Paribu
        current_paribu = item['paribu']['address']
        if 'YOUR_PARIBU' in current_paribu:
            print(f"Paribu {symbol} address eksik!")
            addr = input(f"Paribu {symbol} ({network}) address girin (Enter=skip): ").strip()
            if addr:
                item['paribu']['address'] = addr
                memo = input(f"Paribu {symbol} memo/tag (Enter=none): ").strip()
                if memo:
                    item['paribu']['memo'] = memo
        else:
            print(f"Paribu: {current_paribu}")
    
    # Config'i kaydet
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print("\n✓ config.json güncellendi!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        asyncio.run(manual_update())
    else:
        print("BTCTurk ve Paribu API'lerinden deposit adresleri çekiliyor...")
        print("Not: .env dosyasında BTCTURK_KEY, BTCTURK_SECRET, PARIBU_KEY, PARIBU_SECRET olmalı\n")
        asyncio.run(fetch_addresses())
