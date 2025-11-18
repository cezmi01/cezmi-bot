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

3. `.env` dosyasına **kaynak borsa** API anahtarlarınızı ekleyin:
```
# Kaynak borsalar (en az birini doldurun)
BYBIT_KEY=your_key
BYBIT_SECRET=your_secret
BINANCE_KEY=your_key
BINANCE_SECRET=your_secret
OKX_KEY=your_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
```

**Not**: BTC Turk ve Paribu için API key gerekmez - adresler manuel olarak config.json'da belirtilir.

4. `config.json` dosyasını düzenleyin - **her coin için hem BTC Turk hem Paribu deposit adreslerini** ekleyin:
```json
[
  {
    "symbol": "USDT",
    "network": "TRC20",
    "btcturk": {
      "address": "BTCTURK_USDT_ADRESINIZ_BURAYA",
      "memo": null
    },
    "paribu": {
      "address": "PARIBU_USDT_ADRESINIZ_BURAYA",
      "memo": null
    }
  },
  {
    "symbol": "BTC",
    "network": "BTC",
    "btcturk": {
      "address": "BTCTURK_BTC_ADRESINIZ_BURAYA",
      "memo": null
    },
    "paribu": {
      "address": "PARIBU_BTC_ADRESINIZ_BURAYA",
      "memo": null
    }
  }
]
```

**Önemli**: 
- Her coin için **hem `btcturk` hem `paribu`** bölümlerini doldurun
- `address`: İlgili borsadan aldığınız deposit adresi
- `network`: Coin'in network'ü (TRC20, BTC, ETH, vb.)
- `memo`: Eğer coin memo/tag gerektiriyorsa (örn: XRP, XLM), aksi halde `null`
- GUI'de seçtiğiniz alıcı borsaya göre ilgili adres otomatik kullanılır

## Kullanım

```bash
python bot.py
```

GUI açıldıktan sonra:
1. **Kaynak borsa** seçin (Binance, Bybit veya OKX)
2. **Alıcı borsa** seçin (BTC Turk veya Paribu)
3. "🚀 TRANSFER BAŞLAT" butonuna tıklayın

Bot otomatik olarak:
- Config'deki deposit adresini kullanır
- Kaynak borsadan bakiyeyi kontrol eder
- Transfer işlemini başlatır

## Loglar

Tüm işlemler `withdraw_logs.jsonl` dosyasına kaydedilir.

## Uyarı

⚠️ **Geri alınamaz! Yanlış adres = coin kaybı!**