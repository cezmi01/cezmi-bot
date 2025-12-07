# Bybit Wall Bot

Bybit SPOT piyasasında otomatik duvar (wall) oluşturan trading botu.

## Özellikler

- **14 Dakikalık Döngü**: Her 14 dakikada bir otomatik limit emri
- **Akıllı Fiyatlandırma**: O anki en iyi satış (best ask) fiyatından emir
- **Otomatik İzleme**: 2 dakika boyunca emir durumunu takip eder
- **Akıllı İptal**: Dolmayan emirler otomatik iptal edilir
- **Timestamp Senkronizasyonu**: Bybit sunucu saati ile otomatik senkronizasyon
- **Retry Mekanizması**: Başarısız istekler için otomatik yeniden deneme
- **Rate Limit Yönetimi**: API limitlerini akıllıca yönetir

## Nasıl Çalışır?

1. Bot her 14 dakikada bir belirlenen TOKEN/USDT paritesinde limit satış emri açar
2. Emir miktarı: 900.000 adet (ayarlanabilir)
3. Emir fiyatı: O anki en iyi satış (best ask) fiyatı
4. Emir 2 dakika boyunca izlenir:
   - Tamamen dolarsa → Hiçbir işlem yapılmaz
   - Kısmi veya açık kalırsa → Otomatik iptal edilir
5. Döngü 14 dakikada bir tekrarlanır

## Kurulum

### 1. Gereksinimleri Yükle

```bash
pip install -r requirements.txt
```

### 2. API Anahtarlarını Ayarla

`.env.example` dosyasını `.env` olarak kopyalayın:

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyerek Bybit API anahtarlarınızı ekleyin:

```env
BYBIT_KEY=your_actual_api_key
BYBIT_SECRET=your_actual_api_secret
```

### 3. Bot Ayarlarını Yapılandır

`bybit_wall_bot.py` dosyasındaki bu ayarları kendi ihtiyaçlarınıza göre düzenleyin:

```python
SYMBOL = "TOKENUSDT"               # İşlem yapılacak parite
ORDER_SIDE = "Sell"                # "Buy" veya "Sell"
ORDER_QTY = Decimal("900000")      # Emir miktarı
CYCLE_SECONDS = 14 * 60            # Döngü süresi (saniye)
WATCH_SECONDS = 2 * 60             # İzleme süresi (saniye)

# Önemli: Coin'e özgü tick/step size'ları güncelleyin
PRICE_TICK_SIZE = Decimal("0.0000001")
QTY_STEP_SIZE = Decimal("1")
```

### 4. Botu Çalıştır

```bash
python bybit_wall_bot.py
```

## API İzinleri

Bybit API anahtarınızın şu izinlere sahip olması gerekir:

- ✅ Spot Trading
- ✅ Read
- ✅ Trade

## Güvenlik Uyarıları

⚠️ **ÖNEMLİ UYARILAR**:

1. **API Anahtarları**: `.env` dosyasını asla paylaşmayın veya git'e yüklemeyin
2. **Test Modu**: İlk çalıştırmada küçük miktarlarla test edin
3. **IP Whitelist**: API anahtarınızı belirli IP'lerle sınırlayın
4. **İzinler**: API anahtarınıza sadece gerekli izinleri verin (withdrawal izni vermeyin)
5. **Fonlar**: Bot'un kullanacağı miktardan fazla bakiye tutmayın

## Teknik Detaylar

### Timestamp Senkronizasyonu

Bot, Bybit'in timestamp hata kodlarını (131002) otomatik algılar ve sunucu saati ile senkronize olur. Bu sayede yerel sistem saatinden bağımsız çalışır.

### Retry Mekanizması

- Maksimum 3 deneme
- Rate limit hatalarında otomatik bekleme
- Timestamp hatalarında otomatik senkronizasyon

### Emir İzleme

- 5 saniyede bir emir durumu kontrolü
- Status takibi: `Filled`, `Cancelled`, `Rejected`, `PartiallyFilled`
- İzleme süresi sonunda açık emirleri iptal

## Sorun Giderme

### "BYBIT_KEY veya BYBIT_SECRET tanımlı değil!" Hatası
- `.env` dosyasının mevcut olduğundan emin olun
- API anahtarlarının doğru girildiğini kontrol edin

### "orderbook parse edilemedi" Hatası
- İnternet bağlantınızı kontrol edin
- SYMBOL değişkeninin doğru formatta olduğunu kontrol edin (örn: "PEPEUSDT")

### Timestamp Hataları
- Bot otomatik olarak düzeltir, ancak sistem saatinizin çok yanlış olmamasına dikkat edin

## Lisans

MIT

## Yasal Uyarı

Bu bot eğitim amaçlıdır. Kullanımından doğacak tüm mali kayıplardan kullanıcı sorumludur. Kripto para ticareti yüksek risk içerir.
