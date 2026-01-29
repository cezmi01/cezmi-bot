# cezmi-bot

## ENJ arbitraj botu (Paribu <-> Binance)

Bu repo, Paribu ve Binance spot fiyatlari arasindaki farki izler. Fark
yuzde 4 ve uzerine cikarsa Telegram bildirimi atar ve her saniye terminale
anlik fiyatlari ve farki yazar.

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
- `PARIBU_SYMBOL` (varsayilan: `ENJ_USDT`)
- `PARIBU_URLS` (virgulle ayrilmis, istege bagli)
- `THRESHOLD_PERCENT` (varsayilan: `4`)
- `POLL_INTERVAL_SECONDS` (varsayilan: `1`)
- `ALERT_EVERY_TICK` (`true` yaparsaniz her dongude bildirim atar)

Not: Telegram icin `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` set edilmezse
bildirim gonderilmez, sadece terminale yazar.