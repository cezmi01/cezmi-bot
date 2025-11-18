# Multi-Exchange Çekim Botu

Multi-exchange çoklu coin çekim botu. Binance, Bybit ve OKX borsalarından coin çekimi yapabilir.

## Özellikler

- ✅ **Bybit**: Timestamp sorunu tamamen çözüldü
- ✅ **Binance**: Tam destek
- ✅ **OKX**: Tam destek
- ✅ GUI arayüzü
- ✅ Otomatik bakiye kontrolü
- ✅ Otomatik transfer (UNIFIED → FUND)
- ✅ Detaylı log kaydı

## Kurulum

1. Bağımlılıkları yükleyin:
```bash
pip install -r requirements.txt
```

2. `.env` dosyası oluşturun:
```bash
cp .env.example .env
```

3. `.env` dosyasına API anahtarlarınızı ekleyin:
```
BYBIT_KEY=your_key
BYBIT_SECRET=your_secret
BINANCE_KEY=your_key
BINANCE_SECRET=your_secret
OKX_KEY=your_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
```

4. `config.json` dosyasını düzenleyin:
```json
[
  {
    "symbol": "USDT",
    "network": "TRC20",
    "address": "YOUR_ADDRESS_HERE",
    "memo": null
  }
]
```

## Kullanım

```bash
python bot.py
```

GUI açıldıktan sonra:
1. Kaynak borsayı seçin
2. "🚀 TÜM COİNLERİ ÇEK" butonuna tıklayın

## Loglar

Tüm işlemler `withdraw_logs.jsonl` dosyasına kaydedilir.

## Uyarı

⚠️ **Geri alınamaz! Yanlış adres = coin kaybı!**