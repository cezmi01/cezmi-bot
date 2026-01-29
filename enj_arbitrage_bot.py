#!/usr/bin/env python3
import datetime as dt
import os
import sys
import time
from typing import Any, Iterable, Optional

import requests

BINANCE_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"
DEFAULT_PARIBU_ENDPOINTS = (
    "https://www.paribu.com/ticker",
    "https://paribu.com/ticker",
    "https://api.paribu.com/ticker",
)
PARIBU_PRICE_FIELDS = ("last", "last_price", "lastPrice", "price", "close")


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(
            f"[config] {name}={raw!r} invalid, using {default}",
            file=sys.stderr,
        )
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def format_price(value: float, decimals: int = 8) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def extract_price_from_entry(entry: dict[str, Any]) -> Optional[float]:
    for field in PARIBU_PRICE_FIELDS:
        if field in entry:
            try:
                return float(entry[field])
            except (TypeError, ValueError):
                continue
    return None


def extract_paribu_price(data: Any, symbol: str) -> Optional[float]:
    symbol_upper = symbol.upper()
    if isinstance(data, dict):
        if symbol_upper in data and isinstance(data[symbol_upper], dict):
            price = extract_price_from_entry(data[symbol_upper])
            if price is not None:
                return price
        for key, entry in data.items():
            if isinstance(key, str) and key.upper() == symbol_upper and isinstance(entry, dict):
                price = extract_price_from_entry(entry)
                if price is not None:
                    return price
        for nested_key in ("data", "result", "ticker"):
            if nested_key in data:
                price = extract_paribu_price(data[nested_key], symbol)
                if price is not None:
                    return price
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol_field = item.get("symbol") or item.get("pair") or item.get("market")
            if isinstance(symbol_field, str) and symbol_field.upper() == symbol_upper:
                price = extract_price_from_entry(item)
                if price is not None:
                    return price
    return None


def fetch_binance_price(session: requests.Session, symbol: str) -> float:
    response = session.get(
        BINANCE_ENDPOINT,
        params={"symbol": symbol},
        timeout=5,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return float(data["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unexpected Binance response: {data}") from exc


def fetch_paribu_price(
    session: requests.Session,
    symbol: str,
    endpoints: Iterable[str],
) -> float:
    last_error: Optional[Exception] = None
    for endpoint in endpoints:
        try:
            response = session.get(endpoint, timeout=5)
            response.raise_for_status()
            data = response.json()
            price = extract_paribu_price(data, symbol)
            if price is not None:
                return price
            raise ValueError(f"Symbol {symbol} not found in response from {endpoint}")
        except Exception as exc:  # noqa: BLE001 - we want to try all endpoints
            last_error = exc
    raise RuntimeError(
        f"Paribu price fetch failed for {symbol}. Last error: {last_error}"
    )


def send_telegram_message(
    session: requests.Session,
    token: str,
    chat_id: str,
    message: str,
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = session.post(
        url,
        json={"chat_id": chat_id, "text": message},
        timeout=5,
    )
    response.raise_for_status()


def main() -> None:
    binance_symbol = os.getenv("BINANCE_SYMBOL", "ENJUSDT")
    paribu_symbol = os.getenv("PARIBU_SYMBOL", "ENJ_USDT")
    paribu_urls_raw = os.getenv("PARIBU_URLS") or os.getenv("PARIBU_URL") or ""
    paribu_urls = [
        item.strip()
        for item in paribu_urls_raw.split(",")
        if item.strip()
    ] or list(DEFAULT_PARIBU_ENDPOINTS)

    poll_interval = env_float("POLL_INTERVAL_SECONDS", 1.0)
    threshold_percent = env_float("THRESHOLD_PERCENT", 4.0)
    alert_every_tick = env_bool("ALERT_EVERY_TICK", False)

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_enabled = bool(telegram_token and telegram_chat_id)

    if not telegram_enabled:
        print(
            "[config] Telegram disabled. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.",
            file=sys.stderr,
        )

    print(
        "ENJ arbitraj botu basladi. Binance=%s Paribu=%s esik=%.2f%%"
        % (binance_symbol, paribu_symbol, threshold_percent),
        flush=True,
    )

    session = requests.Session()
    session.headers.update({"User-Agent": "enj-arbitrage-bot/1.0"})

    was_above_threshold = False

    while True:
        started_at = time.monotonic()
        timestamp = dt.datetime.now().isoformat(timespec="seconds")
        try:
            binance_price = fetch_binance_price(session, binance_symbol)
            paribu_price = fetch_paribu_price(session, paribu_symbol, paribu_urls)
            diff_percent = ((binance_price - paribu_price) / paribu_price) * 100
            abs_diff = abs(diff_percent)

            print(
                f"{timestamp} | Binance {binance_symbol}: {format_price(binance_price)} "
                f"| Paribu {paribu_symbol}: {format_price(paribu_price)} "
                f"| Fark: {diff_percent:+.2f}%",
                flush=True,
            )

            should_alert = abs_diff >= threshold_percent and (
                alert_every_tick or not was_above_threshold
            )
            if abs_diff >= threshold_percent:
                was_above_threshold = True
            else:
                was_above_threshold = False

            if should_alert and telegram_enabled:
                message = (
                    f"ENJ arbitraj: Binance {binance_symbol} {format_price(binance_price)} | "
                    f"Paribu {paribu_symbol} {format_price(paribu_price)} | "
                    f"Fark {diff_percent:+.2f}%"
                )
                send_telegram_message(session, telegram_token, telegram_chat_id, message)
        except Exception as exc:  # noqa: BLE001 - runtime issues should not stop the loop
            print(f"{timestamp} | Hata: {exc}", file=sys.stderr)

        elapsed = time.monotonic() - started_at
        sleep_for = poll_interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
