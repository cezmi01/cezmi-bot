# Changelog

Projedeki tüm önemli değişiklikler bu dosyada belgelenecektir.

## [Unreleased]

### Planlanıyor
- [ ] CLI modu (GUI olmadan komut satırından kullanım)
- [ ] Telegram bot entegrasyonu (bildirimler için)
- [ ] Web dashboard (tarayıcı üzerinden yönetim)
- [ ] Otomatik arbitraj (fiyat farkı olduğunda otomatik transfer)
- [ ] Multi-language support (English, etc.)
- [ ] Rate limit optimizasyonu
- [ ] Advanced retry logic with exponential backoff
- [ ] Transaction history viewer

## [1.0.0] - 2025-11-30

### ✨ Yeni Özellikler

#### Bot Core
- 🎉 İlk public release
- ✅ Multi-exchange support: Binance, Bybit, OKX, Gate.io, Bitget
- ✅ Hedef borsa support: BTCTurk, Paribu
- ✅ GUI (tkinter) ile kullanıcı dostu arayüz
- ✅ Async işlemler (aiohttp) ile hızlı transfer
- ✅ Otomatik network seçimi
- ✅ Fee optimizasyonu (düşük fee'li networkler öncelikli)
- ✅ JSONL formatında detaylı loglama
- ✅ Rate limiting ve retry logic

#### Exchange Adaptörler

**Bybit**
- ✅ Timestamp sync fix (server time ile senkronizasyon)
- ✅ FUND account liquidity check
- ✅ Otomatik UNIFIED → FUND transfer
- ✅ Chain normalization (farklı network adı formatları)
- ✅ Withdrawal rate limiting
- ✅ Multiple balance field support
- ✅ Cooldown detection ve otomatik retry

**Binance**
- ✅ Spot wallet integration
- ✅ Network detection ve validation
- ✅ Withdrawal API v3

**OKX**
- ✅ Chain selection logic
- ✅ Withdrawal fee calculation
- ✅ Trading account → Funding account transfer
- ✅ Passphrase authentication

**Gate.io & Bitget**
- ✅ Basic withdrawal support
- ⚠️ Limited testing (use with caution)

#### Yardımcı Araçlar

**address_fetcher.py**
- ✅ BTCTurk API entegrasyonu
- ✅ Paribu API entegrasyonu
- ✅ Otomatik deposit address çekme
- ✅ Manuel address girme modu
- ✅ Interactive CLI
- ✅ Rate limiting

**validate_config.py**
- ✅ Address format validation
  - Ethereum/ERC20 (0x... 42 char)
  - Bitcoin (1/3/bc1... 26-35 char)
  - TRC20 (T... 34 char)
- ✅ Placeholder detection
- ✅ Duplicate entry detection
- ✅ Colored output ile görsel rapor
- ✅ Exit code support (CI/CD için)

#### Dokümantasyon

**README.md**
- ✅ Kapsamlı kurulum rehberi
- ✅ Detaylı kullanım örnekleri
- ✅ Güvenlik best practices
- ✅ Troubleshooting guide
- ✅ FAQ section
- ✅ API reference

**ADRES_GUNCELLEME.md**
- ✅ Deposit address yönetim rehberi
- ✅ 3 farklı güncelleme yöntemi
- ✅ Network uyum kontrolü
- ✅ Güvenlik uyarıları
- ✅ Sorun giderme

**QUICKSTART.md**
- ✅ 5 dakikalık hızlı başlangıç
- ✅ Step-by-step checklist
- ✅ Sık yapılan hatalar ve çözümleri
- ✅ Örnek kullanım senaryoları
- ✅ Pro tips

**CHANGELOG.md**
- ✅ Versiyon takibi (bu dosya)

#### Konfigürasyon

**config.json**
- ✅ Çoklu coin support (USDT, BTC, ETH, vs.)
- ✅ Çoklu network support (TRC20, ERC20, BTC, vs.)
- ✅ BTCTurk ve Paribu için ayrı address yönetimi
- ✅ Memo/tag support (XRP, EOS gibi coinler için)
- ✅ JSON schema validation ready

**.env & .env.example**
- ✅ Tüm desteklenen exchange'ler için template
- ✅ Güvenlik notları
- ✅ Opsiyonel API key'ler açıkça belirtilmiş

**.gitignore**
- ✅ Sensitive files (.env, logs)
- ✅ Python artifacts (__pycache__, *.pyc)
- ✅ IDE config files
- ✅ OS files (.DS_Store)

#### Testing & Validation

- ✅ Config validation script
- ✅ Address format validation
- ✅ JSON syntax validation
- ✅ Manual testing for major exchanges

### 🐛 Bug Fixes

**Bybit**
- 🔧 Timestamp error fix (server time offset)
- 🔧 Balance field name variations handled
- 🔧 Chain normalization for different formats
- 🔧 Rate limit cooldown detection
- 🔧 Multiple retry with timestamp resync

**Network Handling**
- 🔧 Network name mapping (ERC20 vs ETH vs Ethereum)
- 🔧 Chain alias resolution
- 🔧 Fee structure parsing

**GUI**
- 🔧 Thread-safe queue for UI updates
- 🔧 Progress feedback during transfers
- 🔧 Error message display

### 📝 Değişiklikler

**Code Organization**
- 📦 Modular adapter pattern
- 📦 Base class for exchange adaptors
- 📦 Separation of concerns (API, UI, config)

**Error Handling**
- ⚡ Comprehensive try-catch blocks
- ⚡ Detailed error messages
- ⚡ Logging for debugging

**Performance**
- ⚡ Async/await pattern
- ⚡ Connection pooling (aiohttp)
- ⚡ Rate limiting to prevent API bans

### ⚠️ Deprecations

Yok (ilk release)

### 🗑️ Removed

Yok (ilk release)

### 🔒 Security

- ✅ API key .env dosyasında (not in code)
- ✅ .gitignore ile sensitive files korunuyor
- ✅ Dokümantasyonda security best practices
- ⚠️ API key'lerin minimal permission ile kullanılması önerilir
- ⚠️ Withdrawal whitelist kullanımı önerilir
- ⚠️ IP whitelist kullanımı önerilir

### 📊 Performance

- Bybit: ~1-2 saniye (timestamp sync dahil)
- Binance: ~1 saniye
- OKX: ~1-2 saniye
- Network transfer süreleri:
  - TRC20: 1-5 dakika
  - ERC20: 5-30 dakika (gas price'a bağlı)
  - BTC: 10-60 dakika (confirmation sayısına bağlı)

### 🧪 Tested Configurations

- ✅ Python 3.8, 3.9, 3.10, 3.11
- ✅ Linux (Ubuntu 20.04, 22.04)
- ✅ macOS (Monterey, Ventura)
- ⚠️ Windows (basic testing, should work)
- ✅ Bybit API (comprehensive)
- ⚠️ Binance API (basic testing)
- ⚠️ OKX API (basic testing)
- ⚠️ Gate/Bitget (minimal testing)

### 📈 Statistics

- **Lines of Code**: ~1,200 (bot.py + helpers)
- **Documentation**: ~2,000 lines (all .md files)
- **Supported Exchanges**: 5 (source) + 2 (destination)
- **Supported Coins**: Unlimited (config based)
- **Supported Networks**: Unlimited (config based)

### 🙏 Credits

- Exchange APIs: Bybit, Binance, OKX, Gate.io, Bitget
- Turkish Exchanges: BTCTurk, Paribu
- Libraries: aiohttp, python-dotenv, tkinter
- Community: Stack Overflow, GitHub

---

## Notlar

### Versiyon Numaralandırma

Bu proje [Semantic Versioning](https://semver.org/) kullanır:

- **MAJOR**: API değişiklikleri (backward incompatible)
- **MINOR**: Yeni özellikler (backward compatible)
- **PATCH**: Bug fix'ler (backward compatible)

### Kategoriler

- `✨ Yeni Özellikler` - Added: yeni özellikler
- `📝 Değişiklikler` - Changed: mevcut özelliklerde değişiklik
- `🗑️ Removed` - Removed: kaldırılan özellikler
- `🐛 Bug Fixes` - Fixed: düzeltilen bug'lar
- `⚠️ Deprecations` - Deprecated: yakında kaldırılacak özellikler
- `🔒 Security` - Security: güvenlik ile ilgili değişiklikler

### Tarih Formatı

YYYY-MM-DD (ISO 8601)

---

**Son Güncelleme**: 2025-11-30
