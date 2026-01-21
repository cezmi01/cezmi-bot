# upbit-telegram-notifier

Telegram bot that notifies you when Upbit opens deposits for a target token.
It uses the Upbit "Get Deposit/Withdrawal Service Status" endpoint and a
Telegram bot to send alerts.

## Requirements

- Node.js 18+
- Upbit Open API access key and secret key
- Telegram bot token and chat ID

## Setup

```bash
npm install
cp .env.example .env
```

Fill in `.env` with your credentials and target token.

## Run

```bash
npm start
```

## Configuration

Key environment variables:

- `TARGET_CURRENCY`: token symbol (example: `NAP`)
- `TARGET_NET_TYPES`: optional comma separated network types (example: `ETH,SOL`)
- `UPBIT_REGION`: `sg`, `id`, or `th` (default: `sg`)
- `POLL_INTERVAL_MS`: polling interval in milliseconds
- `NOTIFY_ON_START`: send a message on first run if deposits are already open
- `NOTIFY_ON_CLOSE`: send a message when deposits close

## Notes

Upbit states that the service status API is not real time and can be delayed
by several minutes. Use it for notifications, not for time sensitive actions.