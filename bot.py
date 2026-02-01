# -*- coding: utf-8 -*-
"""
Binance + Bybit Yatırma/Çekme İzleme Botu
----------------------------------------
• İlk çalıştırmada, ilgili coinin mevcut durum özetini Telegram'a yollar.
• Sonrasında sadece bir değişiklik olduğunda bildirim gönderir.
• Binance imzalı endpoint: /sapi/v1/capital/config/getall
• Bybit imzalı endpoint: /v5/asset/coin/query-info
• Durumlar ayrı state dosyalarında saklanır.

Gereken .env:
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
[Binance]
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
[Bybit]
BYBIT_API_KEY=...
BYBIT_API_SECRET=...

[opsiyonel]
COIN=RED
BINANCE_COIN=RED
BYBIT_COIN=RED
POLL_SEC=30
BINANCE_STATE_FILE=red_binance_dw_state.json
BYBIT_STATE_FILE=red_bybit_dw_state.json
BINANCE_RECV_WINDOW=60000
BYBIT_RECV_WINDOW=5000
BINANCE_BASE_URL=https://api.binance.com
BYBIT_BASE_URL=https://api.bybit.com
ENABLE_BINANCE=1
ENABLE_BYBIT=1
HTTP_TIMEOUT=15
"""

from __future__ import annotations

import os
import time
import hmac
import hashlib
import json
import logging
from typing import Dict, Any, Tuple
from urllib.parse import urlencode
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def env_bool(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    if value is None:
        return default not in ("0", "false", "no", "off", "n")
    return value.strip().lower() not in ("0", "false", "no", "off", "n")


# ─────────────────────────── ENV
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "").strip()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()

COIN = os.getenv("COIN", "RED").strip().upper()
BINANCE_COIN = os.getenv("BINANCE_COIN", COIN).strip().upper()
BYBIT_COIN = os.getenv("BYBIT_COIN", COIN).strip().upper()

POLL_SEC = int(os.getenv("POLL_SEC", "30"))
BINANCE_STATE_FILE = os.getenv(
    "BINANCE_STATE_FILE",
    os.getenv("STATE_FILE", f"{BINANCE_COIN.lower()}_binance_dw_state.json"),
)
BYBIT_STATE_FILE = os.getenv(
    "BYBIT_STATE_FILE",
    f"{BYBIT_COIN.lower()}_bybit_dw_state.json",
)

BINANCE_RECV_WINDOW = int(
    os.getenv("BINANCE_RECV_WINDOW", os.getenv("RECV_WINDOW", "60000"))
)
BYBIT_RECV_WINDOW = int(os.getenv("BYBIT_RECV_WINDOW", "5000"))

BINANCE_BASE_URL = os.getenv(
    "BINANCE_BASE_URL",
    os.getenv("BASE_URL", "https://api.binance.com"),
).rstrip("/")
BYBIT_BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com").rstrip("/")

TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))

BINANCE_ENABLED = env_bool("ENABLE_BINANCE", "1")
BYBIT_ENABLED = env_bool("ENABLE_BYBIT", "1")

if BINANCE_ENABLED:
    assert BINANCE_API_KEY and BINANCE_API_SECRET, "BINANCE_API_KEY/SECRET zorunlu."
if BYBIT_ENABLED and not (BYBIT_API_KEY and BYBIT_API_SECRET):
    logging.warning("BYBIT_API_KEY/SECRET eksik. Bybit izleme kapatıldı.")
    BYBIT_ENABLED = False

assert TG_TOKEN and TG_CHAT, "TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID zorunlu."

if not (BINANCE_ENABLED or BYBIT_ENABLED):
    raise SystemExit("En az bir borsa etkin olmalı (ENABLE_BINANCE/ENABLE_BYBIT).")

binance_session = requests.Session()
if BINANCE_API_KEY:
    binance_session.headers.update({"X-MBX-APIKEY": BINANCE_API_KEY})

bybit_session = requests.Session()

# Sunucu zamanı ile yerel saat farkını düzeltmek için (ms)
_binance_time_offset_ms = 0
_bybit_time_offset_ms = 0


def get_binance_server_time_offset_ms() -> int:
    try:
        r = binance_session.get(f"{BINANCE_BASE_URL}/api/v3/time", timeout=TIMEOUT)
        r.raise_for_status()
        server_ms = int(r.json()["serverTime"])
        local_ms = int(time.time() * 1000)
        return server_ms - local_ms
    except Exception as e:
        logging.warning(f"Binance sunucu zamanı alınamadı: {e}")
        return 0


def get_bybit_server_time_offset_ms() -> int:
    try:
        r = bybit_session.get(f"{BYBIT_BASE_URL}/v5/market/time", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        result = data.get("result", {}) if isinstance(data, dict) else {}
        time_second = result.get("timeSecond")
        if time_second is None:
            return 0
        server_ms = int(float(time_second)) * 1000
        local_ms = int(time.time() * 1000)
        return server_ms - local_ms
    except Exception as e:
        logging.warning(f"Bybit sunucu zamanı alınamadı: {e}")
        return 0


def sign_binance(query: Dict[str, Any]) -> str:
    qs = urlencode(query, doseq=True)
    sig = hmac.new(
        BINANCE_API_SECRET.encode("utf-8"),
        qs.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{qs}&signature={sig}"


def sapi_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    global _binance_time_offset_ms
    if params is None:
        params = {}
    ts = int(time.time() * 1000) + _binance_time_offset_ms
    params.update({"timestamp": ts, "recvWindow": BINANCE_RECV_WINDOW})
    url = f"{BINANCE_BASE_URL}{path}?{sign_binance(params)}"
    r = binance_session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def bybit_headers_and_query(params: Dict[str, Any]) -> Tuple[Dict[str, str], str]:
    global _bybit_time_offset_ms
    timestamp = str(int(time.time() * 1000) + _bybit_time_offset_ms)
    recv_window = str(BYBIT_RECV_WINDOW)
    qs = urlencode(sorted(params.items())) if params else ""
    payload = f"{timestamp}{BYBIT_API_KEY}{recv_window}{qs}"
    signature = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-SIGN": signature,
        "X-BAPI-SIGN-TYPE": "2",
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    return headers, qs


def bybit_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    if params is None:
        params = {}
    headers, qs = bybit_headers_and_query(params)
    url = f"{BYBIT_BASE_URL}{path}"
    if qs:
        url = f"{url}?{qs}"
    r = bybit_session.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    ret_code = data.get("retCode")
    if str(ret_code) != "0":
        raise RuntimeError(f"Bybit hata: {data.get('retMsg')} (retCode={ret_code})")
    return data


def fetch_binance_asset_config(coin: str) -> Dict[str, Any] | None:
    """/sapi/v1/capital/config/getall -> listedeki ilgili coin kaydını döndürür"""
    data = sapi_get("/sapi/v1/capital/config/getall")
    for asset in data:
        if (asset.get("coin") or "").upper() == coin.upper():
            return asset
    return None


def fetch_bybit_asset_config(coin: str) -> Dict[str, Any] | None:
    """/v5/asset/coin/query-info -> ilgili coin kaydını döndürür"""
    data = bybit_get("/v5/asset/coin/query-info", {"coin": coin})
    rows = data.get("result", {}).get("rows", [])
    for asset in rows:
        if (asset.get("coin") or "").upper() == coin.upper():
            return asset
    return None


def extract_state_binance(asset: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        "asset": asset.get("coin", ""),
        "depositAllEnable": bool(asset.get("depositAllEnable", False)),
        "withdrawAllEnable": bool(asset.get("withdrawAllEnable", False)),
        "networks": {},
    }
    for n in asset.get("networkList", []):
        name = n.get("network", "") or n.get("name", "")
        if not name:
            continue
        state["networks"][name] = {
            "depositEnable": bool(n.get("depositEnable", False)),
            "withdrawEnable": bool(n.get("withdrawEnable", False)),
        }
    return state


def parse_status(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return int(value) == 1
    text = str(value).strip().lower()
    return text in ("1", "true", "enabled", "enable", "on", "yes", "y")


def extract_state_bybit(asset: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        "asset": asset.get("coin", ""),
        "depositAllEnable": False,
        "withdrawAllEnable": False,
        "networks": {},
    }
    chains = asset.get("chains") or asset.get("chain") or asset.get("chainList") or []
    if isinstance(chains, dict):
        chains = [chains]

    for n in chains:
        name = n.get("chainType") or n.get("chain") or n.get("network") or n.get("name")
        if not name:
            continue
        deposit_raw = n.get("depositEnable", n.get("depositStatus"))
        withdraw_raw = n.get("withdrawEnable", n.get("withdrawStatus"))
        state["networks"][name] = {
            "depositEnable": parse_status(deposit_raw),
            "withdrawEnable": parse_status(withdraw_raw),
        }

    if state["networks"]:
        state["depositAllEnable"] = any(
            n["depositEnable"] for n in state["networks"].values()
        )
        state["withdrawAllEnable"] = any(
            n["withdrawEnable"] for n in state["networks"].values()
        )
    else:
        state["depositAllEnable"] = parse_status(
            asset.get("depositEnable", asset.get("depositStatus"))
        )
        state["withdrawAllEnable"] = parse_status(
            asset.get("withdrawEnable", asset.get("withdrawStatus"))
        )
    return state


def load_state(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(path: str, data: Dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def bool_emoji(v: bool) -> str:
    return "✅ Açık" if v else "⛔ Kapalı"


def format_overview(
    state: Dict[str, Any], exchange_label: str, default_coin: str
) -> str:
    lines = []
    asset = state.get("asset", default_coin)
    lines.append(f"🔔 *{asset} — {exchange_label} Yatırma/Çekme Durumu*")
    lines.append(f"• Genel Yatırma: {bool_emoji(state.get('depositAllEnable', False))}")
    lines.append(f"• Genel Çekme : {bool_emoji(state.get('withdrawAllEnable', False))}")
    if state.get("networks"):
        lines.append("")
        lines.append("*Ağ Bazında:*")
        for net, v in sorted(state["networks"].items()):
            lines.append(
                f"— {net}: Yatırma {bool_emoji(v['depositEnable'])} | Çekme {bool_emoji(v['withdrawEnable'])}"
            )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"\n🕒 {ts}")
    return "\n".join(lines)


def diff_states(
    old: Dict[str, Any] | None,
    new: Dict[str, Any],
    exchange_label: str,
    default_coin: str,
) -> Tuple[bool, str]:
    if not old:
        return True, format_overview(new, exchange_label, default_coin)

    changes = []

    if old.get("depositAllEnable") != new.get("depositAllEnable"):
        changes.append(
            f"• Genel Yatırma: {bool_emoji(old.get('depositAllEnable', False))} → *{bool_emoji(new.get('depositAllEnable', False))}*"
        )

    if old.get("withdrawAllEnable") != new.get("withdrawAllEnable"):
        changes.append(
            f"• Genel Çekme : {bool_emoji(old.get('withdrawAllEnable', False))} → *{bool_emoji(new.get('withdrawAllEnable', False))}*"
        )

    old_nets = old.get("networks", {})
    new_nets = new.get("networks", {})
    nets = set(old_nets.keys()) | set(new_nets.keys())
    for net in sorted(nets):
        o = old_nets.get(net, {})
        n = new_nets.get(net, {})
        if not o and n:
            changes.append(
                f"— {net}: *Yeni ağ eklendi.* Yatırma {bool_emoji(n.get('depositEnable', False))}, Çekme {bool_emoji(n.get('withdrawEnable', False))}"
            )
            continue
        if o and not n:
            changes.append(
                f"— {net}: *Ağ kaldırıldı.* (Önceden: Yatırma {bool_emoji(o.get('depositEnable', False))}, Çekme {bool_emoji(o.get('withdrawEnable', False))})"
            )
            continue

        if o.get("depositEnable") != n.get("depositEnable"):
            changes.append(
                f"— {net} Yatırma: {bool_emoji(o.get('depositEnable', False))} → *{bool_emoji(n.get('depositEnable', False))}*"
            )
        if o.get("withdrawEnable") != n.get("withdrawEnable"):
            changes.append(
                f"— {net} Çekme : {bool_emoji(o.get('withdrawEnable', False))} → *{bool_emoji(n.get('withdrawEnable', False))}*"
            )

    if not changes:
        return False, ""

    header = f"🔄 *{new.get('asset', default_coin)} — {exchange_label} Durum Değişikliği*"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = "\n".join(changes)
    return True, f"{header}\n{body}\n\n🕒 {ts}"


def send_telegram(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=TIMEOUT,
        )
        if not resp.ok:
            logging.warning(
                f"Telegram gönderim hatası: {resp.status_code} {resp.text}"
            )
    except Exception as e:
        logging.warning(f"Telegram hata: {e}")


def check_binance(
    last_state: Dict[str, Any] | None, next_allowed_at: float
) -> Tuple[Dict[str, Any] | None, float]:
    if time.time() < next_allowed_at:
        return last_state, next_allowed_at

    try:
        asset = fetch_binance_asset_config(BINANCE_COIN)
        if not asset:
            msg = (
                f"⚠️ {BINANCE_COIN} için varlık bilgisi bulunamadı. "
                "(Binance desteklemiyor olabilir)"
            )
            logging.warning(msg)
            send_telegram(msg)
            return last_state, time.time() + max(POLL_SEC, 60)

        current_state = extract_state_binance(asset)
        changed, message = diff_states(
            last_state, current_state, "Binance", BINANCE_COIN
        )
        if changed and message:
            send_telegram(message)
            save_state(BINANCE_STATE_FILE, current_state)
            last_state = current_state
    except requests.HTTPError as e:
        logging.warning(f"Binance HTTP hata: {e}")
        return last_state, time.time() + 10
    except Exception as e:
        logging.warning(f"Binance hata: {e}")
        return last_state, time.time() + 10

    return last_state, next_allowed_at


def check_bybit(
    last_state: Dict[str, Any] | None, next_allowed_at: float
) -> Tuple[Dict[str, Any] | None, float]:
    if time.time() < next_allowed_at:
        return last_state, next_allowed_at

    try:
        asset = fetch_bybit_asset_config(BYBIT_COIN)
        if not asset:
            msg = (
                f"⚠️ {BYBIT_COIN} için varlık bilgisi bulunamadı. "
                "(Bybit desteklemiyor olabilir)"
            )
            logging.warning(msg)
            send_telegram(msg)
            return last_state, time.time() + max(POLL_SEC, 60)

        current_state = extract_state_bybit(asset)
        changed, message = diff_states(
            last_state, current_state, "Bybit", BYBIT_COIN
        )
        if changed and message:
            send_telegram(message)
            save_state(BYBIT_STATE_FILE, current_state)
            last_state = current_state
    except requests.HTTPError as e:
        logging.warning(f"Bybit HTTP hata: {e}")
        return last_state, time.time() + 10
    except Exception as e:
        logging.warning(f"Bybit hata: {e}")
        return last_state, time.time() + 10

    return last_state, next_allowed_at


def main() -> None:
    global _binance_time_offset_ms, _bybit_time_offset_ms

    if BINANCE_ENABLED:
        logging.info(
            "Binance izleniyor | coin: %s | periyot: %ss | state: %s",
            BINANCE_COIN,
            POLL_SEC,
            BINANCE_STATE_FILE,
        )
        _binance_time_offset_ms = get_binance_server_time_offset_ms()
    if BYBIT_ENABLED:
        logging.info(
            "Bybit izleniyor   | coin: %s | periyot: %ss | state: %s",
            BYBIT_COIN,
            POLL_SEC,
            BYBIT_STATE_FILE,
        )
        _bybit_time_offset_ms = get_bybit_server_time_offset_ms()

    binance_state = load_state(BINANCE_STATE_FILE) if BINANCE_ENABLED else None
    bybit_state = load_state(BYBIT_STATE_FILE) if BYBIT_ENABLED else None

    next_allowed = {"binance": 0.0, "bybit": 0.0}

    while True:
        if BINANCE_ENABLED:
            binance_state, next_allowed["binance"] = check_binance(
                binance_state, next_allowed["binance"]
            )
        if BYBIT_ENABLED:
            bybit_state, next_allowed["bybit"] = check_bybit(
                bybit_state, next_allowed["bybit"]
            )

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Durduruldu.")
