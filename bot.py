# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - OPTIMIZED
------------------------------------------------------
- Bakiye kontrolü paralel, çekim sıralı (rate limit koruması)
- Sadece bakiyesi > 0 olan coinler için çekim yapılır
- Kaynak borsa: Binance / Bybit / OKX
- config.json'dan adres/network okur

OKX FIX (STRICT NETWORK):
- OKX tarafında config’te network verilmişse, SADECE o network ile eşleşiyorsa çekim yapar.
- Eşleşme yoksa veya eşleşen ağ canWd=false ise çekim yapmaz (fallback yok).
"""

import os
import re
import json
import hmac
import time
import base64
import asyncio
import logging
import threading
import hashlib
import uuid
import socket
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from queue import Queue, Empty
from urllib.parse import urlencode

import tkinter as tk
from tkinter import ttk, messagebox

import aiohttp
from dotenv import load_dotenv

APP_TITLE = "Multi-Exchange Transfer Botu"
CONFIG_PATH = Path("config.json")
LOG_PATH = Path("withdraw_logs.jsonl")

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

UI_POLL_MS = 100
REQUIRE_STATIC_IP = False
WITHDRAW_DELAY = 0.3  # Çekimler arası bekleme süresi (saniye)
BALANCE_BATCH_SIZE = 10  # Bakiye kontrolü batch boyutu
BALANCE_BATCH_DELAY = 0.5  # Batch'ler arası bekleme (saniye)
MIN_BALANCE_USD = 1.0  # Minimum bakiye eşiği (USD karşılığı tahmini - toz filtresi)


def write_log(row: dict):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def floor_amount(value: Decimal, step: str = "0.00000001") -> Decimal:
    return value.quantize(Decimal(step), rounding=ROUND_DOWN)


# ═══════════════════════════════════════════════════════════════
#                         BASE ADAPTER
# ═══════════════════════════════════════════════════════════════
class BaseExchange:
    name = "BASE"

    async def preflight(self):
        raise NotImplementedError

    async def get_balance(self, session, symbol: str) -> Decimal:
        raise NotImplementedError

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        raise NotImplementedError


 
 
# ═══════════════════════════════════════════════════════════════
#                         BYBIT ADAPTER (FIX)
# ═══════════════════════════════════════════════════════════════
class BybitAdapter(BaseExchange):
    name = "BYBIT"
    API = "https://api.bybit.com"
    RECV_WINDOW = "60000"
    MAX_RETRIES = 3
    WITHDRAW_MIN_INTERVAL = 0
 
    # Coin konfigürasyonu (fee ve chain bilgileri)
    COINS = {
        "SOL": {"chain": "SOL", "fee": "0.01", "min": "0.02"},
        "OM": {"chain": "MANTLE", "fee": "1", "min": "2"},
        "USDT": {"chain": "TRC20", "fee": "1", "min": "10"},
        "BTC": {"chain": "BTC", "fee": "0.0005", "min": "0.001"},
        "ETH": {"chain": "ETH", "fee": "0.005", "min": "0.01"},
    }
 
    # Chain alias'ları - config'deki isim -> Bybit'teki olası isimler
    CHAIN_ALIASES = {
        "AVAXC": ["CAVAX", "AVAXC", "C-CHAIN", "AVAX-C"],
        "AVAX": ["CAVAX", "XAVAX"],
        "BSC": ["BSC", "BEP20", "BNB"],
        "ETH": ["ETH", "ERC20", "ETHEREUM"],
        "ERC20": ["ETH", "ERC20"],
        "TRC20": ["TRC20", "TRX", "TRON"],
        "TRX": ["TRC20", "TRX"],
        "MATIC": ["MATIC", "POLYGON", "POL"],
        "POLYGON": ["MATIC", "POLYGON", "POL"],
        "ARB": ["ARB", "ARBONE", "ARBITRUM"],
        "ARBITRUM": ["ARB", "ARBONE", "ARBITRUM"],
        "OP": ["OP", "OPTIMISM"],
        "OPTIMISM": ["OP", "OPTIMISM"],
        "SOL": ["SOL", "SOLANA"],
        "SEIEVM": ["SEIEVM", "SEI-EVM"],
        "SEI": ["SEIEVM", "SEI"],  # EVM öncelikli (çoğu borsa EVM kullanıyor)
        "CHZ2": ["CHILIZ", "CHZ2", "CHILIZ2", "CHZ"],
        "CHILIZ": ["CHILIZ", "CHZ2", "CHZ"],
        "FTM": ["FTM", "FANTOM", "OPERA"],
        "FANTOM": ["FTM", "FANTOM"],
        "ONE": ["ONE", "HARMONY"],
        "ATOM": ["ATOM", "COSMOS", "GAIA"],
        "OSMO": ["OSMO", "OSMOSIS"],
        "KAVA": ["KAVAEVM", "KAVA"],  # EVM öncelikli
        "CELO": ["CELO"],
        "NEAR": ["NEAR"],
        "ALGO": ["ALGO", "ALGORAND"],
        "XLM": ["XLM", "STELLAR"],
        "XRP": ["XRP", "RIPPLE"],
        "ADA": ["ADA", "CARDANO"],
        "DOT": ["DOT", "POLKADOT"],
        "LUNA": ["LUNA", "TERRA", "TERRA2"],
        "INJ": ["INJ", "INJECTIVE"],
        "SUI": ["SUI"],
        "APT": ["APT", "APTOS"],
        "TON": ["TON"],
        "MANTLE": ["MANTLE", "MNT"],
        "BASE": ["BASE"],
        "LINEA": ["LINEA"],
        "ZKSYNC": ["ZKV2", "ZKSYNC", "ZKSYNCERA", "ERA"],
        "ZKSYNCERA": ["ZKV2", "ZKSYNCERA", "ZKSYNC", "ERA"],
        "ZKV2": ["ZKV2", "ZKSYNCERA"],
        "HEDERA": ["HBAR", "HEDERA"],
        "HBAR": ["HBAR", "HEDERA"],
    }
 
    def __init__(self):
        self.key = os.getenv("BYBIT_KEY", "").strip()
        self.secret = os.getenv("BYBIT_SECRET", "").strip()
        self.server_time_offset = 0  # Server ile local time farkı
        self._withdraw_lock = None
        self._last_withdraw_request = 0.0
        self._last_balance_account = None
 
    def _normalize_chain(self, symbol: str, chain: str | None) -> str:
        sym = symbol.upper()
        value = (chain or "").strip()
        if not value:
            return sym
        alias_map = {
            "eth": "ERC20",
            "erc20": "ERC20",
            "eth-erc20": "ERC20",
            "ethereum": "ERC20",
            "ethereum mainnet": "ERC20",
            "ethereum (erc20)": "ERC20",
            "arbitrum": "ARBITRUM",
            "arb": "ARBITRUM",
            "arbitrum one": "ARBITRUM",
            "optimism": "OPTIMISM",
            "op": "OPTIMISM",
            "base": "BASE",
            "polygon": "POLYGON",
            "polygon (matic)": "POLYGON",
            "matic": "POLYGON",
            "bsc": "BSC",
            "bnb smart chain": "BSC",
            "bep20": "BSC",
            "linea": "LINEA",
            "zksync": "ZKSYNCERA",
            "zksyncera": "ZKSYNCERA",
            "mantle": "MANTLE",
            "avaxc": "AVAXC",
            "avax": "AVAXC",
        }
        key = value.lower()
        if key in alias_map:
            return alias_map[key]
        if "-" in value:
            return value.upper().replace(" ", "")
        if "(" in value and ")" in value:
            inner = value[value.find("(") + 1 : value.rfind(")")]
            if inner.strip():
                return self._normalize_chain(symbol, inner.strip())
        upper_val = value.upper().strip()
        if upper_val == sym:
            return sym
        clean = re.sub(r"[^A-Z0-9]", "", upper_val)
        if not clean:
            return sym
        # Chain ismini olduğu gibi döndür (COIN- prefix'i ekleme)
        return clean
 
    async def _sync_time(self, session):
        """Server time'ı al ve offset hesapla"""
        try:
            async with session.get(f"{self.API}/v5/market/time") as resp:
                data = await resp.json()
                server_ms = int(data["result"]["timeNano"]) // 1_000_000
                local_ms = int(time.time() * 1000)
                self.server_time_offset = server_ms - local_ms
                write_log(
                    {
                        "exchange": self.name,
                        "note": "time_sync",
                        "server_ms": server_ms,
                        "local_ms": local_ms,
                        "offset_ms": self.server_time_offset,
                    }
                )
        except Exception:
            self.server_time_offset = 0
 
    def _ts(self) -> str:
        """Timestamp (server time ile senkronize)"""
        local_ms = int(time.time() * 1000)
        adjusted_ms = local_ms + self.server_time_offset
        return str(adjusted_ms)
 
    def _sign(self, payload: str) -> str:
        """HMAC-SHA256 signature"""
        return hmac.new(self.secret.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
 
    def _is_timestamp_error(self, data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        code = data.get("retCode")
        msg = (data.get("retMsg") or "").lower()
        if code == 131002 and "timestamp" in msg:
            return True
        return "timestamp" in msg
 
    def _cooldown_seconds(self, data: dict) -> int:
        if not isinstance(data, dict):
            return 0
        msg = data.get("retMsg") or ""
        if data.get("retCode") == 131001:
            match = re.search(r"wait at least\\s*(\\d+)\\s*seconds", msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) + 1
                except ValueError:
                    pass
        return 0

