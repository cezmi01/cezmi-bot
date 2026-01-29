# cezmi-bot

## ENJ arbitraj botu (Paribu <-> Binance)

Bu repo, Paribu (TL) ve Binance (USDT) spot fiyatlari arasindaki farki izler.
Binance ENJ/USDT fiyatini USDT/TRY ile carpip TL'ye cevirir. Fark yuzde 4 ve
uzerine cikarsa Telegram bildirimi atar ve fark her yuzde 1 degisimde tekrar
bildirim gonderir. Her saniye terminale anlik fiyatlari ve farki yazar.

### Kurulum

```bash
python -m pip install -r requirements.txt
```

### Calistirma

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."

python enj_arbitrage_bot.py
```

### Ortam Degiskenleri

- `BINANCE_SYMBOL` (varsayilan: `ENJUSDT`)
- `BINANCE_FX_SYMBOL` (varsayilan: `USDTTRY`)
- `PARIBU_SYMBOL` (varsayilan: `ENJ_TL`)
- `PARIBU_URLS` (virgulle ayrilmis, istege bagli)
- `THRESHOLD_PERCENT` (varsayilan: `4`)
- `POLL_INTERVAL_SECONDS` (varsayilan: `1`)

Not: Telegram icin `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` set edilmezse
bildirim gonderilmez, sadece terminale yazar.