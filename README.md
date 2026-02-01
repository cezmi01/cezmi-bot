# cezmi-bot

Binance ve Bybit yatırma/çekme durumlarını izleyen Telegram botu.

## Kurulum

```bash
pip install -r requirements.txt
python bot.py
```

## .env

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BYBIT_API_KEY=...
BYBIT_API_SECRET=...

COIN=RED
POLL_SEC=30
ENABLE_BINANCE=1
ENABLE_BYBIT=1
```