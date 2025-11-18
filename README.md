# Multi-Exchange Transfer Botu

Multi-exchange çoklu coin transfer botu. Binance, Bybit ve OKX borsalarından BTC Turk ve Paribu'ya otomatik coin transferi yapar.

## Özellikler

- ✅ **Kaynak Borsalar**: Binance, Bybit, OKX
- ✅ **Alıcı Borsalar**: BTC Turk, Paribu
- ✅ **Bybit**: Timestamp sorunu tamamen çözüldü
- ✅ GUI arayüzü
- ✅ Otomatik deposit adresi alma
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
# Kaynak borsalar (en az birini doldurun)
BYBIT_KEY=your_key
BYBIT_SECRET=your_secret
BINANCE_KEY=your_key
BINANCE_SECRET=your_secret
OKX_KEY=your_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase

# Alıcı borsalar (en az birini doldurun)
BTCTURK_KEY=your_key
BTCTURK_SECRET=your_secret
PARIBU_KEY=your_key
PARIBU_SECRET=your_secret
```

4. `config.json` dosyasını düzenleyin (transfer edilecek coinleri listeleyin):
```json
[
  {
    "symbol": "USDT",
    "network": "TRC20"
  },
  {
    "symbol": "BTC",
    "network": "BTC"
  }
]
```

**Not**: Artık `address` ve `memo` alanlarına gerek yok - bunlar alıcı borsadan otomatik alınır.

## Kullanım

```bash
python bot.py
```

GUI açıldıktan sonra:
1. **Kaynak borsa** seçin (Binance, Bybit veya OKX)
2. **Alıcı borsa** seçin (BTC Turk veya Paribu)
3. "🚀 TRANSFER BAŞLAT" butonuna tıklayın

Bot otomatik olarak:
- Alıcı borsadan deposit adresini alır
- Kaynak borsadan bakiyeyi kontrol eder
- Transfer işlemini başlatır

## Loglar

Tüm işlemler `withdraw_logs.jsonl` dosyasına kaydedilir.

## Uyarı

⚠️ **Geri alınamaz! Yanlış adres = coin kaybı!**