# 📑 Cezmi Bot - Dokümantasyon İndeksi

Bot'unuz için hazırlanmış tüm dokümantasyon ve araçların rehberi.

## 🚀 Hızlı Başlangıç

Yeni kullanıcı mısınız? Buradan başlayın:

1. **[QUICKSTART.md](QUICKSTART.md)** ⚡
   - 5 dakikada kurulum
   - Adım adım rehber
   - İlk transfer checklist

2. **[STATUS.md](STATUS.md)** 🚦
   - Projenin mevcut durumu
   - Neyin hazır, neyin eksik olduğu
   - Deployment checklist

3. **[README.md](README.md)** 📘
   - Detaylı dokümantasyon
   - Tüm özellikler
   - Troubleshooting

## 📚 Dokümantasyon Dosyaları

### Temel Dokümantasyon

#### **README.md** (11 KB)
> Ana proje dokümantasyonu - HER ŞEY burada

**İçerik**:
- ✅ Özellikler ve gereksinimler
- ✅ Kurulum rehberi (3 yöntem)
- ✅ Kullanım örnekleri
- ✅ Konfigürasyon rehberi
- ✅ Güvenlik best practices
- ✅ Loglama ve monitoring
- ✅ Sorun giderme
- ✅ İleri düzey kullanım
- ✅ FAQ

**Kimler İçin**: Herkes - en kapsamlı kaynak

---

#### **QUICKSTART.md** (7 KB)
> 5 dakikalık express kurulum rehberi

**İçerik**:
- ⚡ Hızlı kurulum (5 adım)
- ✅ İlk transfer checklist
- ❌ Sık yapılan hatalar ve çözümleri
- 🎯 Örnek kullanım senaryoları (3 adet)
- 💡 Pro tips (network, timing, güvenlik)
- 🛠️ Troubleshooting komutları
- ✅ Başarılı kurulum kontrolü

**Kimler İçin**: Yeni başlayanlar, hızlı kurulum isteyenler

---

#### **ADRES_GUNCELLEME.md** (4 KB)
> Deposit adresi yönetim rehberi

**İçerik**:
- 🔄 3 farklı güncelleme yöntemi
  1. Otomatik (API ile)
  2. Manuel (interaktif CLI)
  3. Doğrudan config.json düzenleme
- 🌐 Network uyum rehberi (TRC20, ERC20, BTC)
- ⚠️ Kritik güvenlik uyarıları
- 🔌 API endpoint bilgileri
- 🐛 Sorun giderme

**Kimler İçin**: Address yapılandırması yapacaklar (ZORUNLU)

---

#### **STATUS.md** (9 KB)
> Projenin mevcut durum raporu

**İçerik**:
- 🚦 Hazırlık durumu (bot %80, dok %100)
- ✅ Tamamlanan bileşenler
- ⚠️ Eksik/bekleyen bileşenler
- 📊 Detaylı metrikler (1,768 satır kod!)
- 🎯 Deployment checklist
- 💡 Öneriler
- ✅ Final checklist

**Kimler İçin**: Projenin durumunu görmek isteyenler

---

#### **SUMMARY.md** (9 KB)
> Proje özeti - ne yaptık?

**İçerik**:
- 🎯 Ne yaptık? (özet)
- ✅ Tamamlanan işler (10+ madde)
- 📦 Dosya yapısı
- 📊 İstatistikler
- 🔮 Gelecek iyileştirmeler
- 🎉 Sonuç ve sonraki adımlar

**Kimler İçin**: Projeye overview isteyenler

---

#### **CHANGELOG.md** (6 KB)
> Versiyon geçmişi ve değişiklikler

**İçerik**:
- 📝 v1.0.0 release notes (ŞU AN)
- ✨ Yeni özellikler
- 🐛 Bug fixes
- 📈 Performance
- 🧪 Test coverage
- 🔒 Security
- 🔮 Gelecek planlar (v1.1, v1.2, v2.0)

**Kimler İçin**: Versiyonları takip edenler, changelog arşivi

---

#### **INDEX.md** (Bu Dosya)
> Tüm dokümantasyonun rehberi

**Kimler İçin**: Nerede ne olduğunu görmek isteyenler

---

## 🤖 Bot Dosyaları

### **bot.py** (45 KB - Ana Program)
> Multi-exchange transfer bot (GUI ile)

**Özellikler**:
- 🔌 5 kaynak exchange: Binance, Bybit, OKX, Gate, Bitget
- 🎯 2 hedef exchange: BTCTurk, Paribu
- 🖥️ GUI (tkinter)
- ⚡ Async transfer (aiohttp)
- 💰 Fee optimization
- 🔄 Rate limiting
- 📝 Detaylı loglama (withdraw_logs.jsonl)

**Çalıştırma**:
```bash
python3 bot.py
# veya
./run.sh
```

---

### **config.json** (1.4 KB)
> Deposit adresleri konfigürasyonu

**Yapı**:
```json
[
  {
    "symbol": "USDT",
    "network": "TRC20",
    "btcturk": { "address": "...", "memo": null },
    "paribu": { "address": "...", "memo": null }
  }
]
```

**Durum**:
- ✅ ETH: Adresler dolu
- ❌ USDT (TRC20, ERC20): Placeholder
- ❌ BTC: Placeholder

**Güncelleme**:
```bash
python3 address_fetcher.py manual
```

---

### **requirements.txt** (36 bytes)
> Python dependencies

**İçerik**:
```
aiohttp>=3.9.0
python-dotenv>=1.0.0
```

**Yükleme**:
```bash
pip install -r requirements.txt
```

---

## 🛠️ Yardımcı Araçlar

### **address_fetcher.py** (11 KB)
> Deposit adresi yönetim aracı

**2 Mod**:
1. **Otomatik**: BTCTurk ve Paribu API'den çeker
2. **Manuel**: İnteraktif CLI ile girdi alır

**Kullanım**:
```bash
# Otomatik (API gerekli)
python3 address_fetcher.py

# Manuel (API gerekmez)
python3 address_fetcher.py manual
```

**Ne Yapar**:
- Mevcut config.json'ı okur
- Eksik adresleri tespit eder
- API'den çeker veya kullanıcıdan sorar
- config.json'ı günceller
- Mevcut adreslere dokunmaz

---

### **validate_config.py** (8 KB)
> Config doğrulama aracı

**Kontroller**:
- ✅ Address format (ETH: 0x..., BTC: 1/3/bc1..., TRC20: T...)
- ✅ Placeholder detection
- ✅ Duplicate kontrolü
- ✅ JSON syntax

**Kullanım**:
```bash
python3 validate_config.py
```

**Çıktı**:
- Renkli rapor (✅/❌)
- Detaylı hata mesajları
- Exit code (0=OK, 1=Error)

---

### **run.sh** (2 KB)
> Bot launcher script

**Özellikler**:
- Python version detection (python3/python)
- Dependency check (auto-install)
- .env kontrolü
- Config validation
- Pre-flight checks

**Kullanım**:
```bash
chmod +x run.sh
./run.sh
```

**Avantajlar**:
- Tek komutla her şey kontrol edilir
- Kullanıcı dostu mesajlar
- Hataları önceden yakalar

---

## 🔧 Konfigürasyon Dosyaları

### **.env.example** (720 bytes)
> Environment variables template

**İçerik**:
```bash
# Bybit
BYBIT_KEY=...
BYBIT_SECRET=...

# Binance
BINANCE_KEY=...
BINANCE_SECRET=...

# OKX
OKX_KEY=...
OKX_SECRET=...
OKX_PASSPHRASE=...

# BTCTurk (opsiyonel - address_fetcher için)
BTCTURK_KEY=...
BTCTURK_SECRET=...

# Paribu (opsiyonel)
PARIBU_KEY=...
PARIBU_SECRET=...
```

**Setup**:
```bash
cp .env.example .env
nano .env  # API keys gir
```

---

### **.gitignore** (346 bytes)
> Git ignore rules

**Korunan Dosyalar**:
- `.env` (API keys)
- `withdraw_logs.jsonl` (logs)
- `__pycache__/` (Python cache)
- IDE config files
- OS files (.DS_Store)

---

## 🗺️ Kullanım Akışı

### Yeni Kullanıcı İçin Okuma Sırası

```
1. STATUS.md          → Projenin durumunu gör
2. QUICKSTART.md      → 5 dakikada kur
3. ADRES_GUNCELLEME.md → Adresleri ekle
4. İlk transfer yap   → Test et
5. README.md          → Detaylı öğren
```

### Problem Yaşıyorsanız

```
1. validate_config.py → Config kontrol et
2. QUICKSTART.md      → Sık hatalar bölümü
3. README.md          → Troubleshooting
4. Logs kontrol et    → withdraw_logs.jsonl
5. STATUS.md          → Known issues
```

### İleri Düzey Kullanım

```
1. README.md          → Advanced usage
2. bot.py             → Source code oku
3. CHANGELOG.md       → Yeni özellikler
4. Kendi scriptini yaz → Otomation
```

---

## 📊 Dosya Özeti

| Kategori | Dosyalar | Toplam Boyut |
|----------|----------|--------------|
| 🤖 **Bot** | 3 dosya | ~46 KB |
| 🛠️ **Araçlar** | 3 dosya | ~21 KB |
| 📚 **Dokümantasyon** | 6 dosya | ~47 KB |
| 🔧 **Konfigürasyon** | 2 dosya | ~1 KB |
| **TOPLAM** | **14 dosya** | **~115 KB** |

### Kod İstatistikleri

```
Python Kod        : 1,768 satır
Dokümantasyon     : 1,699 satır
Konfigürasyon     :   136 satır
───────────────────────────────
TOPLAM PROJE      : 3,603 satır
```

---

## 🎯 Hangi Dosyayı Okumalıyım?

### "Bot'u hemen çalıştırmak istiyorum"
→ **QUICKSTART.md**

### "Neyin hazır olduğunu görmek istiyorum"
→ **STATUS.md**

### "Adresleri nasıl ekleyeceğimi öğrenmek istiyorum"
→ **ADRES_GUNCELLEME.md**

### "Her şeyi detaylı öğrenmek istiyorum"
→ **README.md**

### "Sorun yaşıyorum, çözmek istiyorum"
→ **README.md** (Troubleshooting bölümü)

### "Proje hakkında özet bilgi istiyorum"
→ **SUMMARY.md**

### "Versiyonları ve değişiklikleri görmek istiyorum"
→ **CHANGELOG.md**

### "Nereye bakacağımı bilmiyorum"
→ **INDEX.md** (bu dosya! 👋)

---

## 🔗 Quick Links

### Temel Komutlar
```bash
# Bot'u başlat
./run.sh

# Config'i doğrula
python3 validate_config.py

# Adresleri güncelle
python3 address_fetcher.py manual

# Logları izle
tail -f withdraw_logs.jsonl

# Help
python3 bot.py --help  # (şimdilik GUI açar)
```

### Önemli Bölümler
- [Kurulum](README.md#-kurulum)
- [Güvenlik](README.md#-güvenlik)
- [Troubleshooting](README.md#-sorun-giderme)
- [İlk Transfer Checklist](QUICKSTART.md#-i̇lk-transfer-checklist)
- [Address Güncelleme](ADRES_GUNCELLEME.md#yöntem-1-otomatik-api-ile-çekme)
- [Deployment Checklist](STATUS.md#-deployment-checklist)

---

## ✅ Son Kontrol

Bot'u kullanmaya başlamadan önce:

```bash
# 1. Tüm dosyalar mevcut mu?
ls bot.py config.json requirements.txt address_fetcher.py validate_config.py

# 2. Dependencies yüklü mü?
python3 -c "import aiohttp, dotenv" && echo "✅"

# 3. Config valid mi?
python3 validate_config.py

# 4. .env hazır mı?
test -f .env && echo "✅" || echo "❌ Create .env"

# 5. Tümü OK ise
./run.sh
```

---

## 🎓 Öğrenme Yolu

### Level 1: Başlangıç (15 dakika)
1. STATUS.md → Durumu gör
2. QUICKSTART.md → Kur
3. İlk transfer → Test et

### Level 2: Kullanıcı (30 dakika)
1. README.md → Detaylı öğren
2. ADRES_GUNCELLEME.md → Address yönetimi
3. Troubleshooting → Sorun çözme

### Level 3: İleri Düzey (1-2 saat)
1. bot.py source code → Nasıl çalıştığını anla
2. CHANGELOG.md → Tüm features
3. Custom automation → Kendi scriptlerini yaz

---

## 📞 Yardım

Tüm dokümantasyonu okudunuz ve hala sorun mu var?

1. **Validation**: `python3 validate_config.py`
2. **Logs**: `tail -50 withdraw_logs.jsonl`
3. **Test**: Küçük miktarla test edin
4. **Dokümantasyon**: README.md'yi tekrar okuyun
5. **Support**: Issue açın (detaylı açıklama ile)

---

## 🎉 Başarılar!

Artık bot'unuzun tüm dokümantasyonuna hakimsiniz. 

**Sonraki adım**: Adresleri ekleyin ve ilk transferi yapın!

```bash
python3 address_fetcher.py manual
python3 validate_config.py
./run.sh
```

**Happy Trading! 🚀**

---

**Son Güncelleme**: 2025-11-30  
**Dokümantasyon Versiyonu**: 1.0.0  
**Bot Versiyonu**: 1.0.0
