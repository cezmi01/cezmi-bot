# 🤖 Cezmi Bot - Multi-Exchange Transfer Bot

Çoklu kripto borsaları arası otomatik transfer botu. Binance, Bybit, OKX gibi kaynak borsalardan BTCTurk ve Paribu'ya otomatik kripto transferi yapar.

## 🌟 Özellikler

- ✅ **Çoklu Kaynak Borsa**: Binance, Bybit, OKX, Gate.io, Bitget
- ✅ **Çoklu Hedef Borsa**: BTCTurk, Paribu
- ✅ **GUI Arayüz**: Kullanıcı dostu tkinter arayüzü
- ✅ **Otomatik Network Seçimi**: En uygun network'ü otomatik seçer
- ✅ **Fee Optimizasyonu**: Düşük fee'li networkler öncelikli
- ✅ **Detaylı Loglama**: Tüm işlemler `withdraw_logs.jsonl` dosyasına kaydedilir
- ✅ **Rate Limiting**: API limitlerini aşmamak için otomatik bekleme
- ✅ **Hata Yönetimi**: Timestamp, rate limit ve diğer API hatalarını otomatik yönetir

## 📋 Gereksinimler

### Sistem Gereksinimleri
- Python 3.8+
- İnternet bağlantısı
- API key'leri (kaynak borsalar için)

### Python Paketleri

```bash
pip install -r requirements.txt
```

Gerekli paketler:
- `aiohttp` - Async HTTP istekleri
- `python-dotenv` - Environment variable yönetimi
- `tkinter` - GUI (genelde Python ile birlikte gelir)

## 🚀 Kurulum

### 1. Repository'yi İndirin

```bash
git clone <repo-url>
cd cezmi-bot
```

### 2. Dependencies Yükleyin

```bash
pip install -r requirements.txt
```

### 3. Environment Variables Ayarlayın

`.env.example` dosyasını `.env` olarak kopyalayın:

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin ve API key'lerinizi girin:

```bash
# Bybit API Keys
BYBIT_KEY=your_bybit_api_key
BYBIT_SECRET=your_bybit_secret

# Binance API Keys
BINANCE_KEY=your_binance_api_key
BINANCE_SECRET=your_binance_secret

# OKX API Keys (opsiyonel)
OKX_KEY=your_okx_api_key
OKX_SECRET=your_okx_secret
OKX_PASSPHRASE=your_okx_passphrase
```

⚠️ **Güvenlik Notu**: `.env` dosyasını asla paylaşmayın veya commit etmeyin!

### 4. Deposit Adreslerini Ayarlayın

Bu en önemli adımdır! Bot'un çalışması için BTCTurk ve Paribu deposit adreslerini `config.json` dosyasına girmeniz gerekir.

#### Yöntem A: Otomatik (API ile)

BTCTurk ve Paribu API key'leriniz varsa:

```bash
# .env dosyasına BTCTurk ve Paribu API key'lerini ekleyin
python address_fetcher.py
```

#### Yöntem B: Manuel (İnteraktif)

```bash
python address_fetcher.py manual
```

Script size her coin için address soracak.

#### Yöntem C: Doğrudan Düzenleme

`config.json` dosyasını açın ve adresleri manuel girin:

```json
{
  "symbol": "USDT",
  "network": "TRC20",
  "btcturk": {
    "address": "BURAYA_BTCTURK_USDT_TRC20_ADRESİ",
    "memo": null
  },
  "paribu": {
    "address": "BURAYA_PARIBU_USDT_TRC20_ADRESİ",
    "memo": null
  }
}
```

Detaylı bilgi için: [ADRES_GUNCELLEME.md](ADRES_GUNCELLEME.md)

### 5. Config'i Doğrulayın

Adresleri girdikten sonra doğrulama yapın:

```bash
python validate_config.py
```

Bu komut size:
- ✅ Hangi adreslerin doğru formatta olduğunu
- ❌ Hangi adreslerin eksik veya hatalı olduğunu
- 📊 Genel bir özet rapor

gösterecektir.

## 💻 Kullanım

### Bot'u Başlatma

```bash
python bot.py
```

GUI penceresi açılacak. Burada:

1. **Kaynak Borsa Seçin**: Binance, Bybit, OKX, vb.
2. **Coin Seçin**: USDT, BTC, ETH, vb.
3. **Hedef Borsa Seçin**: BTCTurk veya Paribu
4. **Miktar Girin**: Transfer edilecek miktar
5. **TRANSFER ET** butonuna tıklayın

### Test Önerileri

İlk kullanımda:

1. ✅ **Küçük Miktarlarla Test Edin**
   ```
   Örn: 10-20 USDT
   ```

2. ✅ **Network'ü Kontrol Edin**
   ```
   TRC20 adresi için TRC20 seçildiğinden emin olun
   ```

3. ✅ **Logları Takip Edin**
   ```bash
   tail -f withdraw_logs.jsonl
   ```

## 📂 Dosya Yapısı

```
cezmi-bot/
├── bot.py                    # Ana bot dosyası (GUI + transfer logic)
├── address_fetcher.py        # Deposit adresi çekme yardımcı scripti
├── validate_config.py        # Config doğrulama scripti
├── config.json              # Deposit adresleri konfigürasyonu
├── .env                     # API keys (GİZLİ - commit edilmemeli)
├── .env.example             # Environment variables şablonu
├── requirements.txt         # Python dependencies
├── withdraw_logs.jsonl      # Transfer logları (otomatik oluşturulur)
├── README.md               # Bu dosya
├── ADRES_GUNCELLEME.md     # Adres güncelleme rehberi
└── .gitignore              # Git ignore dosyası
```

## 🔧 Konfigürasyon

### config.json Yapısı

```json
[
  {
    "symbol": "USDT",
    "network": "TRC20",
    "btcturk": {
      "symbol": "USDT",
      "network": "TRC20",
      "address": "TxxxxxxxxxxxxxxxxxxxxxxxxxxxxYourAddress",
      "memo": null
    },
    "paribu": {
      "symbol": "USDT", 
      "network": "TRC20",
      "address": "TxxxxxxxxxxxxxxxxxxxxxxxxxxxxYourAddress",
      "memo": null
    }
  }
]
```

### Desteklenen Coinler

Botun desteklediği coinler `config.json` içinde tanımlıdır. Varsayılan:

- **USDT** (TRC20, ERC20)
- **BTC** (Bitcoin Network)
- **ETH** (Ethereum Network)

Yeni coin eklemek için `config.json`'a yeni entry ekleyin.

### Network İsimleri

Farklı borsalar farklı network isimleri kullanır:

| Gerçek Network | Binance | Bybit | OKX |
|---------------|---------|-------|-----|
| Tron | TRC20 | TRC20 | TRC20 |
| Ethereum | ERC20 | ETH | ERC20 |
| Bitcoin | BTC | BTC | Bitcoin |

Bot bu farklılıkları otomatik yönetir.

## 📊 Loglama

Tüm transfer işlemleri `withdraw_logs.jsonl` dosyasına JSON Lines formatında kaydedilir:

```json
{"exchange": "BYBIT", "symbol": "USDT", "action": "WITHDRAW", "amount": "50.0", "address": "Txxx...", "timestamp": "2025-11-30T10:30:00"}
```

Logları görmek için:

```bash
# Tüm loglar
cat withdraw_logs.jsonl

# Son 10 log
tail -10 withdraw_logs.jsonl

# Gerçek zamanlı takip
tail -f withdraw_logs.jsonl

# Belirli bir coin için filtrele
grep "USDT" withdraw_logs.jsonl

# JSON formatında güzel görünüm
cat withdraw_logs.jsonl | jq '.'
```

## 🔒 Güvenlik

### API Key Güvenliği

1. ✅ **Sadece Gerekli İzinleri Verin**
   - ✓ Spot Trading / Withdrawal
   - ✗ Futures Trading
   - ✗ P2P Trading

2. ✅ **IP Whitelist Kullanın**
   - API key'lerinizi belirli IP'lerle sınırlayın
   - Farklı locasyon'lardan erişimi engelleyin

3. ✅ **Withdrawal Whitelist**
   - Sadece bilinen adreslere withdrawal yapılmasına izin verin
   - Botun kullanacağı BTCTurk/Paribu adreslerini whitelist'e ekleyin

4. ✅ **2FA Aktif Tutun**
   - API key oluştururken 2FA zorunlu
   - Hesap güvenliğinizi artırır

### Address Güvenliği

⚠️ **ÇOK ÖNEMLİ**: Yanlış adres veya network = Para kaybı!

1. ✅ **Address'i Çift Kontrol Edin**
   ```bash
   python validate_config.py
   ```

2. ✅ **Network Uyumunu Kontrol Edin**
   - TRC20 adresi → TRC20 network
   - ERC20 adresi → ERC20 network
   - **KARIŞTIRMAYIN!**

3. ✅ **Test Transfer Yapın**
   - İlk transferde küçük miktar (10-20 USDT)
   - Başarılı olduktan sonra büyük miktarlar

### .env Güvenliği

```bash
# .env dosyasının izinlerini sınırlayın (Linux/Mac)
chmod 600 .env

# .gitignore'da olduğundan emin olun
echo ".env" >> .gitignore
```

## 🐛 Sorun Giderme

### API Bağlantı Hataları

**Hata**: `Invalid API key`

**Çözüm**:
- API key'in doğru kopyalandığından emin olun
- Başında/sonunda boşluk olmadığını kontrol edin
- API key'in aktif olduğunu kontrol edin

---

**Hata**: `IP not whitelisted`

**Çözüm**:
- Borsa panelinden IP adresinizi whitelist'e ekleyin
- Veya IP kısıtlamasını kaldırın (daha az güvenli)

---

**Hata**: `Timestamp error`

**Çözüm**:
- Sistem saatinizin doğru olduğundan emin olun
- NTP sync aktif mi kontrol edin:
  ```bash
  # Linux
  sudo timedatectl set-ntp true
  
  # Mac
  sudo sntp -sS time.apple.com
  ```

### Address Hataları

**Hata**: `Invalid address format`

**Çözüm**:
```bash
python validate_config.py
```
Hangi adresin hatalı olduğunu gösterecek.

---

**Hata**: `Network mismatch`

**Çözüm**:
- config.json'da network adını kontrol edin
- Borsadaki network adıyla eşleşmeli

### Transfer Hataları

**Hata**: `Insufficient balance`

**Çözüm**:
- Kaynak borsada yeterli bakiyeniz var mı?
- Fee için ekstra bakiye bırakın

---

**Hata**: `Withdrawal suspended`

**Çözüm**:
- Borsa o coin için withdrawal'ı durdurmuş olabilir
- Blockchain'de bir sorun var mı kontrol edin
- Borsa duyurularını takip edin

---

**Hata**: `Minimum withdrawal not met`

**Çözüm**:
- Her borsanın minimum withdrawal miktarı vardır
- Daha büyük miktar deneyin

## 📈 İleri Düzey Kullanım

### Batch Transfer

Birden fazla coin için otomatik transfer:

```python
# Kendi scriptinizi yazabilirsiniz
import asyncio
from bot import BybitAdapter

async def batch_transfer():
    coins = ["USDT", "BTC", "ETH"]
    for coin in coins:
        # Transfer logic
        pass

asyncio.run(batch_transfer())
```

### Scheduling

Belirli aralıklarla otomatik transfer:

```bash
# Linux/Mac crontab
# Her gün 09:00'da çalıştır
0 9 * * * cd /path/to/cezmi-bot && python bot.py

# Windows Task Scheduler kullanın
```

### Custom Alerts

Transfer başarılı/başarısız olduğunda bildirim:

```python
# bot.py içinde custom notify function ekleyin
def notify_telegram(message):
    # Telegram bot ile bildirim gönder
    pass
```

## 🤝 Katkıda Bulunma

Bu bot kişisel kullanım için geliştirilmiştir. Geliştirmeler için:

1. Fork edin
2. Feature branch oluşturun
3. Commit yapın
4. Pull request açın

## ⚖️ Yasal Uyarı

- Bu bot eğitim ve kişisel kullanım amaçlıdır
- Finansal tavsiye değildir
- Kripto para transferlerinde risk vardır
- Kendi sorumluluğunuzda kullanın
- API key'lerinizin güvenliğinden siz sorumlusunuz

## 📞 Destek

Sorun yaşıyorsanız:

1. 📖 Dokümantasyonu okuyun (README.md, ADRES_GUNCELLEME.md)
2. 🔍 Logları kontrol edin (`withdraw_logs.jsonl`)
3. ✅ Config'i validate edin (`python validate_config.py`)
4. 🐛 Issue açın (detaylı açıklama ile)

## 📝 Changelog

### v1.0 (2025-11-30)
- ✨ İlk release
- ✅ Multi-exchange support (Binance, Bybit, OKX)
- ✅ BTCTurk & Paribu integration
- ✅ GUI interface
- ✅ Address fetcher tool
- ✅ Config validator
- ✅ Comprehensive documentation

## 📜 License

MIT License - Kişisel ve ticari kullanım serbesttir.

---

**⚡ Happy Trading! ⚡**
