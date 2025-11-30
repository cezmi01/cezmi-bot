# 🚀 Quick Start Guide

Bot'u 5 dakikada çalıştırmak için hızlı başlangıç rehberi.

## ⚡ Hızlı Kurulum (5 Dakika)

### 1️⃣ Dependencies Yükle (30 saniye)

```bash
pip install aiohttp python-dotenv
```

### 2️⃣ API Keys Ayarla (1 dakika)

```bash
# .env.example'ı kopyala
cp .env.example .env

# Düzenle ve API key'lerini gir
nano .env  # veya vim, code, vb.
```

Minimum gerekli:
```bash
# Kaynak borsa (en az birini)
BYBIT_KEY=your_key
BYBIT_SECRET=your_secret
```

### 3️⃣ Deposit Adreslerini Gir (2 dakika)

#### Hızlı Yöntem: Manuel

```bash
python3 address_fetcher.py manual
```

Program size interaktif olarak her coin için address soracak.

#### Veya: Doğrudan config.json'ı Düzenle

```bash
nano config.json
```

**ÖNEMLİ**: Her `YOUR_BTCTURK...` ve `YOUR_PARIBU...` placeholder'ını gerçek adreslerle değiştirin!

Örnek:
```json
{
  "symbol": "USDT",
  "network": "TRC20",
  "btcturk": {
    "address": "TYourRealBTCTurkAddress123456789"
  },
  "paribu": {
    "address": "TYourRealParibuAddress123456789"
  }
}
```

### 4️⃣ Adresleri Doğrula (30 saniye)

```bash
python3 validate_config.py
```

Tüm adresler ✓ olmalı! ✗ varsa düzeltin.

### 5️⃣ Bot'u Başlat! (5 saniye)

```bash
python3 bot.py
```

GUI penceresi açılacak. Test için küçük miktar (10-20 USDT) deneyin!

---

## 🎯 İlk Transfer Checklist

Transfer yapmadan önce kontrol edin:

- [ ] API key'ler `.env` dosyasında ve doğru
- [ ] Deposit adresleri `config.json`'da ve doğru
- [ ] `validate_config.py` tüm ✓ gösteriyor
- [ ] Kaynak borsada yeterli bakiye var
- [ ] Network seçimi doğru (TRC20 = TRC20, ERC20 = ERC20)
- [ ] İlk transfer küçük miktar (10-20 USDT)

---

## ⚠️ Sık Yapılan Hatalar

### ❌ Hata: "YOUR_BTCTURK..."

**Sorun**: Deposit adresleri girilmemiş

**Çözüm**: 
```bash
python3 address_fetcher.py manual
```

### ❌ Hata: "Invalid address format"

**Sorun**: Address formatı yanlış

**Çözüm**: 
- TRC20 adresi `T` ile başlamalı (34 karakter)
- ERC20/ETH adresi `0x` ile başlamalı (42 karakter)
- BTC adresi `1`, `3` veya `bc1` ile başlamalı

### ❌ Hata: "API key invalid"

**Sorun**: API key yanlış veya başında/sonunda boşluk var

**Çözüm**:
```bash
# .env dosyasında boşluk olmadığından emin olun
# YANLIŞ: BYBIT_KEY= abc123 
# DOĞRU:  BYBIT_KEY=abc123
```

### ❌ Hata: "Insufficient balance"

**Sorun**: Yeterli bakiye yok

**Çözüm**:
- Kaynak borsada bakiyenizi kontrol edin
- Fee için ekstra bakiye bırakın (örn: 55 USDT transfer için 60 USDT olmalı)

---

## 🔄 Günlük Kullanım

### Sabah Rutini

```bash
# 1. Bot'u başlat
python3 bot.py

# 2. GUI'de:
#    - Kaynak borsa seç (Bybit)
#    - Coin seç (USDT)
#    - Hedef seç (BTCTurk veya Paribu)
#    - Miktar gir
#    - TRANSFER ET tıkla

# 3. Logları kontrol et
tail -5 withdraw_logs.jsonl
```

### Transfer Sonrası Kontrol

```bash
# 1. Log'da success mesajı
grep "success" withdraw_logs.jsonl | tail -1

# 2. Hedef borsada parayı kontrol et (5-30 dakika sürebilir)
#    - BTCTurk → Wallet → Deposit History
#    - Paribu → Cüzdan → Deposit İşlemleri

# 3. Blockchain'de kontrol (opsiyonel)
#    - TRC20: tronscan.org
#    - ERC20: etherscan.io
#    - BTC: blockchain.com
```

---

## 📊 Örnek Kullanım Senaryoları

### Senaryo 1: Bybit'ten BTCTurk'e USDT (TRC20)

```
1. Bot'u aç: python3 bot.py
2. Kaynak: Bybit
3. Coin: USDT
4. Network: TRC20 (otomatik seçilir veya manuel)
5. Hedef: BTCTurk
6. Miktar: 50
7. TRANSFER ET
8. Sonuç: ~30 saniye içinde withdraw request gönderilir
9. Bekle: 5-10 dakika içinde BTCTurk'te görünür
```

**Avantaj**: TRC20 düşük fee (~1 USDT)

### Senaryo 2: Binance'den Paribu'ya ETH

```
1. Bot'u aç
2. Kaynak: Binance
3. Coin: ETH
4. Network: ETH (Ethereum mainnet)
5. Hedef: Paribu
6. Miktar: 0.1
7. TRANSFER ET
8. Bekle: 10-30 dakika (Ethereum ağı yavaş olabilir)
```

**Not**: ETH fee yüksektir (~0.005-0.01 ETH = $10-20)

### Senaryo 3: Toplu Transfer (Script)

Birden fazla coin aynı anda:

```python
# custom_batch.py
import subprocess

coins = [
    {"coin": "USDT", "amount": "50"},
    {"coin": "BTC", "amount": "0.001"},
    {"coin": "ETH", "amount": "0.05"}
]

for item in coins:
    print(f"Transferring {item['amount']} {item['coin']}...")
    # GUI yerine API call yapın
    # veya GUI'yi otomatize edin
```

---

## 🛠️ Troubleshooting Komutları

```bash
# Config'i kontrol et
python3 validate_config.py

# Config'in JSON syntax'ını kontrol et
python3 -c "import json; json.load(open('config.json'))" && echo "✓ JSON OK"

# API bağlantısını test et
python3 -c "from bot import BybitAdapter; import asyncio; print('Testing...'); asyncio.run(BybitAdapter().preflight())"

# Son 10 log entry
tail -10 withdraw_logs.jsonl

# Hataları filtrele
grep -i "error\|fail" withdraw_logs.jsonl

# Başarılı transferleri say
grep -i "success" withdraw_logs.jsonl | wc -l

# Bugünkü transferler
grep "$(date +%Y-%m-%d)" withdraw_logs.jsonl
```

---

## 💡 Pro Tips

### Tip 1: Network Seçimi

**Düşük Fee**:
- ✅ TRC20 (Tron) - ~1 USDT fee
- ✅ BSC (BNB Chain) - ~0.1-0.5 USDT fee

**Yüksek Fee**:
- ❌ ERC20 (Ethereum) - ~5-50 USDT fee (gas price'a bağlı)

**Öneri**: USDT için hep TRC20 kullanın (BTCTurk ve Paribu destekliyorsa)

### Tip 2: Timing

**En İyi Zamanlar**:
- 🌅 Sabah 09:00-11:00 (düşük network trafiği)
- 🌙 Gece 02:00-05:00 (en düşük fee)

**Kaçınılacak Zamanlar**:
- ❌ Cuma akşam-Cumartesi (yüksek volume)
- ❌ Major coin listing zamanları
- ❌ Market crash zamanları (network tıkanabilir)

### Tip 3: Güvenlik

```bash
# API key izinlerini sınırlayın
# ✓ Enable: Spot Trading, Withdrawal
# ✗ Disable: Futures, Margin, P2P

# IP Whitelist kullanın
# Sadece kendi IP'nizden erişim

# Withdrawal Whitelist
# Sadece BTCTurk ve Paribu adreslerine izin ver
```

### Tip 4: Otomation

```bash
# Crontab ile günlük otomatik transfer (Linux/Mac)
# Her gün 10:00'da 50 USDT transfer et
0 10 * * * cd /path/to/cezmi-bot && /usr/bin/python3 bot.py --auto --amount=50 --coin=USDT

# Not: --auto flag'i için bot.py'yi modifiye etmeniz gerekir
```

---

## 📞 Yardım Lazım?

1. **Dokümantasyonu Oku**:
   - [README.md](README.md) - Detaylı bilgi
   - [ADRES_GUNCELLEME.md](ADRES_GUNCELLEME.md) - Adres rehberi

2. **Validation Çalıştır**:
   ```bash
   python3 validate_config.py
   ```

3. **Logları İncele**:
   ```bash
   tail -50 withdraw_logs.jsonl
   ```

4. **Test Transfer Yap**:
   - Küçük miktar (10 USDT)
   - İlk kez kullanılan adres için

5. **Borsa Support**:
   - BTCTurk: support@btcturk.com
   - Paribu: destek@paribu.com
   - Bybit: Live chat on website
   - Binance: https://support.binance.com

---

## ✅ Başarılı Kurulum Kontrolü

Her şey hazır mı? Kontrol edin:

```bash
# 1. Dependencies
python3 -c "import aiohttp, dotenv" && echo "✓ Dependencies OK"

# 2. API Keys
test -f .env && echo "✓ .env file exists"

# 3. Config
python3 validate_config.py && echo "✓ Config valid"

# 4. Bot
python3 -c "import bot" && echo "✓ Bot import OK"
```

Tümü ✓ ise hazırsınız! 🎉

```bash
python3 bot.py
```

---

**Happy Trading! 🚀**
