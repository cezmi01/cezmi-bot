# cezmi-bot

Paribu auto-sell botu icin ornek calisma dosyalari.

## Kurulum

1. Sanal ortam olusturun:
   - Linux/macOS: `python -m venv .venv && source .venv/bin/activate`
   - Windows: `python -m venv .venv && .venv\\Scripts\\activate`
2. Kutuphaneleri yukleyin:
   - `python -m pip install -r requirements.txt`
3. `.env` dosyasini olusturun ve anahtarlari ekleyin:
   - `PARIBU_API_KEY=...`
   - `PARIBU_API_SECRET=...`
   - `BINANCE_API_KEY=...`
   - `BINANCE_API_SECRET=...`
   - `TELEGRAM_BOT_TOKEN=...`
   - `TELEGRAM_CHAT_ID=...`

## Calistirma

```bash
python bot.py
```