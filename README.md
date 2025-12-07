# Bybit Wall Bot

BYBIT 14 DK DUVAR BOTU - Otomatik limit emir botu

## Özellikler

- Her 14 dakikada bir TOKEN/USDT tahtasına 900.000 adet LIMIT SELL emri atar
- Fiyat: o anki en iyi satış (best ask) fiyatı
- Emir SPOT piyasaya atılır (category=spot)
- Emir 2 dakika boyunca takip edilir:
  - 2 dk içinde full dolarsa: dokunulmaz
  - 2 dk sonunda hâlâ açık/kısmi doluysa: emir iptal edilir
- Bybit API imzalama ve timestamp düzeltme (server_time_offset) ile güvenli bağlantı

## Kurulum

1. Gerekli paketleri yükleyin:
```bash
pip install -r requirements.txt
```

2. `.env` dosyası oluşturun:
```bash
cp .env.example .env
```

3. `.env` dosyasını düzenleyip Bybit API bilgilerinizi girin:
```
BYBIT_KEY=your_bybit_api_key_here
BYBIT_SECRET=your_bybit_api_secret_here
```

## Yapılandırma

Bot ayarlarını `bybit_wall_bot.py` dosyasındaki sabitlerden değiştirebilirsiniz:

```python
SYMBOL = "TOKENUSDT"               # Örn: "PEPEUSDT", "DOGEUSDT"
ORDER_SIDE = "Sell"                # "Buy" veya "Sell"
ORDER_QTY = Decimal("900000")      # 900.000 adet
CYCLE_SECONDS = 14 * 60            # 14 dakika
WATCH_SECONDS = 2 * 60             # 2 dakika emir izleme süresi
POLL_INTERVAL = 5                  # 5 saniyede bir emir durumu sorgu

# Tick/step ayarları (coine göre güncelle)
PRICE_TICK_SIZE = Decimal("0.0000001")  # örnek tick size
QTY_STEP_SIZE = Decimal("1")            # örnek step size (tam sayı adım)
```

## Kullanım

Botu çalıştırmak için:

```bash
python bybit_wall_bot.py
```

## Güvenlik Uyarısı

⚠️ **ÖNEMLİ**: Bu bot gerçek para ile işlem yapar. Kullanmadan önce:
- Test ortamında deneyin
- API anahtarlarınızın sadece spot trading izinleri olduğundan emin olun
- Riskleri anladığınızdan emin olun
- `.env` dosyasını asla git'e commit etmeyin

## Notlar

- Bot sürekli çalışır ve her 14 dakikada bir yeni emir atar
- Emirler 2 dakika içinde dolmazsa otomatik iptal edilir
- Timestamp hataları otomatik olarak düzeltilir
- Rate limit durumlarında otomatik bekleme yapılır
