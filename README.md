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
      "symbol": "USDT",
      "network": "TRC20",
      "address": "BTCTURK_USDT_TRC20_ADRESINIZ_BURAYA",
      "memo": null
    },
    "paribu": {
      "symbol": "USDT",
      "network": "TRC20",
      "address": "PARIBU_USDT_TRC20_ADRESINIZ_BURAYA",
      "memo": null
    }
  },
  {
    "symbol": "USDT",
    "network": "ERC20",
    "btcturk": {
      "symbol": "USDT",
      "network": "ERC20",
      "address": "BTCTURK_USDT_ERC20_ADRESINIZ_BURAYA",
      "memo": null
    },
    "paribu": {
      "symbol": "USDT",
      "network": "ERC20",
      "address": "PARIBU_USDT_ERC20_ADRESINIZ_BURAYA",
      "memo": null
    }
  },
  {
    "symbol": "BTC",
    "network": "BTC",
    "btcturk": {
      "symbol": "BTC",
      "network": "BTC",
      "address": "BTCTURK_BTC_ADRESINIZ_BURAYA",
      "memo": null
    },
    "paribu": {
      "symbol": "BTC",
      "network": "BTC",
      "address": "PARIBU_BTC_ADRESINIZ_BURAYA",
      "memo": null
    }
  }
]
```

**Önemli**: 
- Her coin için **hem `btcturk` hem `paribu`** bölümlerini doldurun
- **Her borsa için ayrı `symbol` ve `network` belirtebilirsiniz** (Paribu'da coin ismi farklı olabilir)
- `symbol`: İlgili borsada coin'in adı (Paribu'da farklı olabilir)
- `network`: İlgili borsada coin'in network'ü (Paribu'da farklı olabilir)
- `address`: İlgili borsadan aldığınız deposit adresi
- `memo`: Eğer coin memo/tag gerektiriyorsa (örn: XRP, XLM), aksi halde `null`
- GUI'de seçtiğiniz alıcı borsaya göre ilgili coin, network ve adres otomatik kullanılır
- Aynı coin için farklı network'lerde farklı entry'ler oluşturabilirsiniz (örn: USDT TRC20 ve USDT ERC20)

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