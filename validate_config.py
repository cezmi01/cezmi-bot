# -*- coding: utf-8 -*-
"""
Config Validation Script
------------------------
config.json dosyasını doğrular ve eksik/hatalı adresleri raporlar
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Tuple

CONFIG_PATH = Path("config.json")


def is_valid_eth_address(address: str) -> bool:
    """Ethereum address validation (0x ile başlayan 42 karakter)"""
    return bool(re.match(r'^0x[a-fA-F0-9]{40}$', address))


def is_valid_btc_address(address: str) -> bool:
    """Bitcoin address validation (basit kontrol)"""
    # BTC adresleri 1, 3 veya bc1 ile başlar, 26-35 karakter arası
    return bool(re.match(r'^(1|3|bc1)[a-zA-Z0-9]{25,62}$', address))


def is_valid_trc20_address(address: str) -> bool:
    """TRON TRC20 address validation (T ile başlar)"""
    return bool(re.match(r'^T[a-zA-Z0-9]{33}$', address))


def is_placeholder(address: str) -> bool:
    """Placeholder mı kontrol et"""
    return 'YOUR_' in address.upper() or 'HERE' in address.upper()


def validate_address(symbol: str, network: str, address: str) -> Tuple[bool, str]:
    """
    Address formatını network'e göre doğrula
    Returns: (is_valid, error_message)
    """
    if is_placeholder(address):
        return False, "Placeholder - gerçek address girilmemiş"
    
    # Network bazlı validasyon
    network_upper = network.upper()
    
    if 'ERC20' in network_upper or network_upper == 'ETH':
        if not is_valid_eth_address(address):
            return False, "Geçersiz Ethereum address formatı (0x ile başlamalı, 42 karakter)"
    
    elif 'TRC20' in network_upper or network_upper == 'TRC20':
        if not is_valid_trc20_address(address):
            return False, "Geçersiz TRC20 address formatı (T ile başlamalı, 34 karakter)"
    
    elif network_upper == 'BTC' or symbol.upper() == 'BTC':
        if not is_valid_btc_address(address):
            return False, "Geçersiz Bitcoin address formatı"
    
    # Diğer networkler için basit kontrol
    elif len(address) < 10:
        return False, "Address çok kısa"
    
    return True, "OK"


def validate_config() -> Dict:
    """Config dosyasını doğrula ve rapor oluştur"""
    
    if not CONFIG_PATH.exists():
        return {
            'valid': False,
            'error': f'{CONFIG_PATH} dosyası bulunamadı!',
            'items': []
        }
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return {
            'valid': False,
            'error': f'JSON parse hatası: {e}',
            'items': []
        }
    
    if not isinstance(config, list):
        return {
            'valid': False,
            'error': 'Config bir liste olmalı',
            'items': []
        }
    
    results = []
    has_error = False
    
    for idx, item in enumerate(config):
        item_result = {
            'index': idx,
            'symbol': item.get('symbol', 'UNKNOWN'),
            'network': item.get('network', 'UNKNOWN'),
            'btcturk': {},
            'paribu': {}
        }
        
        # BTCTurk validation
        if 'btcturk' in item:
            btc_addr = item['btcturk'].get('address', '')
            is_valid, msg = validate_address(item['symbol'], item['network'], btc_addr)
            item_result['btcturk'] = {
                'address': btc_addr,
                'valid': is_valid,
                'message': msg,
                'memo': item['btcturk'].get('memo')
            }
            if not is_valid:
                has_error = True
        else:
            item_result['btcturk'] = {
                'valid': False,
                'message': 'BTCTurk konfigürasyonu eksik'
            }
            has_error = True
        
        # Paribu validation
        if 'paribu' in item:
            paribu_addr = item['paribu'].get('address', '')
            is_valid, msg = validate_address(item['symbol'], item['network'], paribu_addr)
            item_result['paribu'] = {
                'address': paribu_addr,
                'valid': is_valid,
                'message': msg,
                'memo': item['paribu'].get('memo')
            }
            if not is_valid:
                has_error = True
        else:
            item_result['paribu'] = {
                'valid': False,
                'message': 'Paribu konfigürasyonu eksik'
            }
            has_error = True
        
        results.append(item_result)
    
    return {
        'valid': not has_error,
        'error': None,
        'items': results,
        'total': len(config),
        'valid_count': sum(1 for r in results if r['btcturk']['valid'] and r['paribu']['valid'])
    }


def print_report(validation_result: Dict):
    """Validation sonuçlarını güzel bir formatta yazdır"""
    
    print("\n" + "="*70)
    print("CONFIG.JSON DOĞRULAMA RAPORU")
    print("="*70)
    
    if validation_result.get('error'):
        print(f"\n❌ HATA: {validation_result['error']}\n")
        return
    
    total = validation_result['total']
    valid = validation_result['valid_count']
    invalid = total - valid
    
    print(f"\nToplam: {total} coin/network")
    print(f"✓ Geçerli: {valid}")
    print(f"✗ Hatalı/Eksik: {invalid}")
    
    if validation_result['valid']:
        print("\n🎉 Tüm adresler geçerli!")
    else:
        print("\n⚠️  Bazı adresler eksik veya hatalı!")
    
    print("\n" + "-"*70)
    print("DETAYLI SONUÇLAR")
    print("-"*70)
    
    for item in validation_result['items']:
        symbol = item['symbol']
        network = item['network']
        
        print(f"\n{item['index'] + 1}. {symbol} ({network})")
        print("   " + "-"*64)
        
        # BTCTurk
        btc = item['btcturk']
        status = "✓" if btc['valid'] else "✗"
        print(f"   BTCTurk: {status} {btc.get('message', '')}")
        if btc.get('address'):
            addr_display = btc['address'][:20] + "..." if len(btc['address']) > 20 else btc['address']
            print(f"            Address: {addr_display}")
        if btc.get('memo'):
            print(f"            Memo: {btc['memo']}")
        
        # Paribu
        paribu = item['paribu']
        status = "✓" if paribu['valid'] else "✗"
        print(f"   Paribu:  {status} {paribu.get('message', '')}")
        if paribu.get('address'):
            addr_display = paribu['address'][:20] + "..." if len(paribu['address']) > 20 else paribu['address']
            print(f"            Address: {addr_display}")
        if paribu.get('memo'):
            print(f"            Memo: {paribu['memo']}")
    
    print("\n" + "="*70)
    
    if not validation_result['valid']:
        print("\n💡 İPUCU:")
        print("   - Eksik adresleri tamamlamak için: python address_fetcher.py")
        print("   - Manuel güncellemek için: python address_fetcher.py manual")
        print("   - Dokümantasyon için: ADRES_GUNCELLEME.md dosyasına bakın")
    
    print()


def check_duplicates(config: List[Dict]) -> List[str]:
    """Aynı symbol/network kombinasyonunun tekrarlanıp tekrarlanmadığını kontrol et"""
    seen = {}
    duplicates = []
    
    for idx, item in enumerate(config):
        key = f"{item['symbol']}-{item['network']}"
        if key in seen:
            duplicates.append(f"#{idx + 1}: {key} (ilk görüldüğü: #{seen[key] + 1})")
        else:
            seen[key] = idx
    
    return duplicates


def main():
    print("Config doğrulama başlatılıyor...")
    
    # Validasyon yap
    result = validate_config()
    
    # Raporu yazdır
    print_report(result)
    
    # Duplicate kontrolü
    if result.get('items'):
        config = []
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        dupes = check_duplicates(config)
        if dupes:
            print("\n⚠️  UYARI: Tekrarlanan konfigürasyonlar:")
            for dupe in dupes:
                print(f"   - {dupe}")
    
    # Exit code
    if result.get('valid'):
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
