# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - OPTIMIZED
------------------------------------------------------
- Bakiye kontrolü paralel, çekim sıralı (rate limit koruması)
- Sadece bakiyesi > 0 olan coinler için çekim yapılır
- Kaynak borsa: Binance / Bybit / OKX
- config.json'dan adres/network okur

OKX strict network mode:
- Config'te `network` verildiyse, OKX'te SADECE o network ile birebir eşleşme (alias/normalize destekli)
  ve `canWd=true` ise çekim yapılır.
- Eşleşme yoksa veya eşleşen ağ `canWd=false` ise çekim iptal edilir (fallback yok).
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
WITHDRAW_DELAY = 0.3
BALANCE_BATCH_SIZE = 10
BALANCE_BATCH_DELAY = 0.5
MIN_BALANCE_USD = 1.0


def write_log(row: dict):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def floor_amount(value: Decimal, step: str = "0.00000001") -> Decimal:
    return value.quantize(Decimal(step), rounding=ROUND_DOWN)


class BaseExchange:
    name = "BASE"

    async def preflight(self):
        raise NotImplementedError

    async def get_balance(self, session, symbol: str) -> Decimal:
        raise NotImplementedError

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        raise NotImplementedError


class BybitAdapter(BaseExchange):
    name = "BYBIT"
    API = "https://api.bybit.com"
    RECV_WINDOW = "60000"
    MAX_RETRIES = 3
    WITHDRAW_MIN_INTERVAL = 0

    COINS = {
        "SOL": {"chain": "SOL", "fee": "0.01", "min": "0.02"},
        "OM": {"chain": "MANTLE", "fee": "1", "min": "2"},
        "USDT": {"chain": "TRC20", "fee": "1", "min": "10"},
        "BTC": {"chain": "BTC", "fee": "0.0005", "min": "0.001"},
        "ETH": {"chain": "ETH", "fee": "0.005", "min": "0.01"},
    }

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
        "SEI": ["SEIEVM", "SEI"],
        "CHZ2": ["CHILIZ", "CHZ2", "CHILIZ2", "CHZ"],
        "CHILIZ": ["CHILIZ", "CHZ2", "CHZ"],
        "FTM": ["FTM", "FANTOM", "OPERA"],
        "FANTOM": ["FTM", "FANTOM"],
        "ONE": ["ONE", "HARMONY"],
        "ATOM": ["ATOM", "COSMOS", "GAIA"],
        "OSMO": ["OSMO", "OSMOSIS"],
        "KAVA": ["KAVAEVM", "KAVA"],
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
        self.server_time_offset = 0
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
        return clean

    async def _sync_time(self, session):
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
        local_ms = int(time.time() * 1000)
        adjusted_ms = local_ms + self.server_time_offset
        return str(adjusted_ms)

    def _sign(self, payload: str) -> str:
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
            match = re.search(r"wait at least\s*(\d+)\s*seconds", msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) + 1
                except ValueError:
                    return 0
        return 0

    async def _get_withdraw_lock(self):
        if self._withdraw_lock is None:
            self._withdraw_lock = asyncio.Lock()
        return self._withdraw_lock

    async def _wait_for_withdraw_slot(self):
        if self.WITHDRAW_MIN_INTERVAL <= 0:
            return
        if self._last_withdraw_request <= 0:
            return
        elapsed = time.monotonic() - self._last_withdraw_request
        if elapsed < self.WITHDRAW_MIN_INTERVAL:
            wait_for = self.WITHDRAW_MIN_INTERVAL - elapsed
            write_log(
                {
                    "exchange": self.name,
                    "note": "withdraw_spacing_wait",
                    "wait_seconds": round(wait_for, 2),
                }
            )
            await asyncio.sleep(wait_for)

    async def _ensure_fund_liquidity(self, session, symbol: str, required: Decimal):
        required = required.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        if required <= 0:
            return

        sym = symbol.upper()

        data, status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coin-balance",
            {"accountType": "FUND", "coin": sym},
        )

        fund_available = (
            Decimal(str(data.get("result", {}).get("balance", {}).get("walletBalance", "0")))
            if status == 200
            else Decimal("0")
        )

        write_log(
            {
                "exchange": self.name,
                "symbol": sym,
                "note": "FUND_BALANCE_CHECK",
                "status": status,
                "fund_available": str(fund_available),
                "required": str(required),
                "needs_transfer": fund_available < required,
                "raw_result": data.get("result") if status == 200 else None,
            }
        )

        if fund_available >= required:
            self._last_balance_account = "FUND"
            return

        transfer_body = {
            "transferId": str(uuid.uuid4()),
            "coin": sym,
            "amount": str(required),
            "fromAccountType": "UNIFIED",
            "toAccountType": "FUND",
        }

        resp, resp_status = await self._post(session, "/v5/asset/transfer/inter-transfer", transfer_body)

        if resp_status != 200 or resp.get("retCode") != 0:
            raise RuntimeError(
                f"Bybit transfer failed: HTTP {resp_status}, retCode={resp.get('retCode')}, retMsg={resp.get('retMsg')}"
            )

        self._last_balance_account = "FUND"
        await asyncio.sleep(0.5)

    async def _get(self, session, endpoint, params=None):
        attempt = 0
        last_response = None
        while attempt < self.MAX_RETRIES:
            attempt += 1
            ts = self._ts()
            params_with_meta = dict(params or {})
            params_with_meta["timestamp"] = ts
            params_with_meta["recvWindow"] = self.RECV_WINDOW
            query = urlencode(sorted(params_with_meta.items()))

            sign_payload = ts + self.key + self.RECV_WINDOW + query
            signature = self._sign(sign_payload)

            headers = {
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": self.RECV_WINDOW,
            }

            url = f"{self.API}{endpoint}" + (f"?{query}" if query else "")

            async with session.get(url, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if not isinstance(data, dict):
                    data = {"raw": data}

                last_response = (data, resp.status)

                if attempt < self.MAX_RETRIES and resp.status == 200 and self._is_timestamp_error(data):
                    await self._sync_time(session)
                    continue

                if attempt < self.MAX_RETRIES:
                    delay = self._cooldown_seconds(data)
                    if delay:
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_get_error"}, 500

    async def _post(self, session, endpoint, body: dict):
        attempt = 0
        last_response = None
        while attempt < self.MAX_RETRIES:
            attempt += 1
            ts = self._ts()
            body_with_meta = dict(body)
            body_with_meta["timestamp"] = ts
            body_with_meta["recvWindow"] = self.RECV_WINDOW

            body_json = json.dumps(body_with_meta, separators=(",", ":"))

            sign_payload = ts + self.key + self.RECV_WINDOW + body_json
            signature = self._sign(sign_payload)

            headers = {
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": self.RECV_WINDOW,
                "Content-Type": "application/json",
            }

            url = f"{self.API}{endpoint}"

            async with session.post(url, data=body_json, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if not isinstance(data, dict):
                    data = {"raw": data}

                last_response = (data, resp.status)

                if attempt < self.MAX_RETRIES and resp.status == 200 and self._is_timestamp_error(data):
                    await self._sync_time(session)
                    continue

                if attempt < self.MAX_RETRIES:
                    delay = self._cooldown_seconds(data)
                    if delay:
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_post_error"}, 500

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
            await self._sync_time(s)
            data, status = await self._get(s, "/v5/user/query-api")
            if status != 200:
                raise RuntimeError(f"Bybit HTTP {status}")
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
            perms = data.get("result", {}).get("permissions", {})
            if "Wallet" not in perms:
                raise RuntimeError(f"Wallet permission missing! Available: {list(perms.keys())}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        # (Bu dosyada kısalık için Bybit'in detaylı balance implementasyonu korunmadı.)
        # Senin mevcut kodunla aynı dosyada kullanıyorsan, kendi BybitAdapter'ını bırak.
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        return {"error": "BybitAdapter stub in this workspace file"}, 501


class BinanceAdapter(BaseExchange):
    name = "BINANCE"
    API = "https://api.binance.com"

    def __init__(self):
        self.key = os.getenv("BINANCE_KEY", "")
        self.secret = os.getenv("BINANCE_SECRET", "")

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        sig = hmac.new(self.secret.encode(), query.encode(), "sha256").hexdigest()
        params["signature"] = sig
        return params

    async def _req(self, session, method, endpoint, params=None):
        params = self._sign(params or {})
        headers = {"X-MBX-APIKEY": self.key}
        async with session.request(method, f"{self.API}{endpoint}", params=params, headers=headers) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {"raw": await r.text()}
            return data, r.status

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
            data, st = await self._req(s, "GET", "/api/v3/account")
            if st != 200:
                raise RuntimeError(f"Binance error: {data}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        data, st = await self._req(session, "GET", "/api/v3/account")
        if st != 200:
            raise RuntimeError(data)
        for b in data.get("balances", []):
            if b.get("asset", "").upper() == symbol.upper():
                return Decimal(b.get("free", "0"))
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        return {"error": "BinanceAdapter stub in this workspace file"}, 501


class OKXAdapter(BaseExchange):
    name = "OKX"
    API = "https://www.okx.com"
    ACCOUNT_FUNDING = "6"
    ACCOUNT_TRADING = "18"
    ACCOUNT_SPOT = "1"
    MIN_DECIMAL_STEP = Decimal("0.00000001")
    TRANSFER_SETTLE_ATTEMPTS = 5
    TRANSFER_SETTLE_DELAY = 1.0

    def __init__(self):
        self.key = os.getenv("OKX_KEY", "")
        self.secret = os.getenv("OKX_SECRET", "")
        self.passphrase = os.getenv("OKX_PASSPHRASE", "")

    def _ts(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(self, ts, method, path, body=""):
        pre = f"{ts}{method.upper()}{path}{body}"
        return base64.b64encode(hmac.new(self.secret.encode(), pre.encode(), "sha256").digest()).decode()

    def _headers(self, ts, sign):
        return {
            "OK-ACCESS-KEY": self.key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _norm_token(value: str) -> str:
        """Upper + strip non-alnum for robust chain matching."""
        return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
            ts = self._ts()
            path = "/api/v5/account/balance"
            headers = self._headers(ts, self._sign(ts, "GET", path))
            async with s.get(f"{self.API}{path}", headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"OKX error: {await r.text()}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        # (Kısaltılmış; senin mevcut kodunla aynı dosyada kullanıyorsan full implementasyonu bırak.)
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        ts = self._ts()
        path = f"/api/v5/asset/currencies?ccy={symbol.upper()}"
        h1 = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=h1) as r1:
            data1 = await r1.json(content_type=None)

        want_raw = (network or "").strip()
        want_norm = self._norm_token(want_raw)

        entries: list[dict] = []
        for item in data1.get("data", []):
            chains_list = item.get("chains")
            if isinstance(chains_list, list) and chains_list:
                entries.extend([c for c in chains_list if isinstance(c, dict)])
            elif isinstance(item, dict):
                entries.append(item)

        write_log(
            {
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_CHAIN_CHECK",
                "network_request": want_raw,
                "entries": [
                    {"chain": e.get("chain"), "name": e.get("name"), "canWd": e.get("canWd")}
                    for e in entries
                    if isinstance(e, dict)
                ],
            }
        )

        def can_withdraw(ch: dict) -> bool:
            return str(ch.get("canWd")).lower() == "true"

        # STRICT: config network verildiyse fallback YOK.
        # Binance'te yaptığınız gibi: eşleşme yoksa çekme.
        if want_raw:
            OKX_CHAIN_ALIASES = {
                "ETH": ["ERC20", "ETH", "ETHEREUM"],
                "ERC20": ["ERC20", "ETH"],
                "SOL": ["SOLANA", "SOL"],
                "SOLANA": ["SOLANA", "SOL"],
                "BSC": ["BEP20", "BSC"],
                "BEP20": ["BEP20", "BSC"],
                "TRC20": ["TRC20", "TRX", "TRON"],
                "TRX": ["TRC20", "TRX"],
                "POLYGON": ["POLYGON", "MATIC"],
                "MATIC": ["POLYGON", "MATIC"],
                "ARBITRUM": ["ARBITRUM", "ARB", "ARBONE"],
                "ARB": ["ARBITRUM", "ARB"],
                "OPTIMISM": ["OPTIMISM", "OP"],
                "OP": ["OPTIMISM", "OP"],
                "AVAXC": ["AVAXC", "C-CHAIN", "AVALANCHE C", "AVALANCHEC"],
                "BASE": ["BASE"],
                # OKX'te "CHZ-Chiliz Chain" gibi gelebiliyor: boşluk vs normalize ediyoruz.
                "CHZ2": ["CHZ2", "CHILIZ2", "CHILIZCHAIN", "CHILIZ", "CHZ"],
                "CHILIZ": ["CHILIZ", "CHILIZCHAIN", "CHZ2", "CHZ"],
                "ZKSYNCERA": ["ZKSYNCERA", "ZKSYNCERA", "ZKSYNC", "ZKV2", "ERA", "ZKSYNCERA"],
                "HEDERA": ["HBAR", "HEDERA"],
                "HBAR": ["HBAR", "HEDERA"],
                "NEO3": ["N3", "NEO3", "NEO"],
            }

            possible = OKX_CHAIN_ALIASES.get(want_norm, None)
            if possible is None:
                possible = [want_raw]
            possible_norm = {self._norm_token(p) for p in possible if p}
            possible_norm.add(want_norm)

            withdrawable_matches: list[dict] = []
            disabled_matches: list[dict] = []

            for ch in entries:
                chain_name = (ch.get("chain") or "").strip()
                if not chain_name:
                    continue
                full_norm = self._norm_token(chain_name)
                suffix_norm = self._norm_token(chain_name.split("-", 1)[-1])

                matched = False
                for tok in possible_norm:
                    if not tok:
                        continue
                    if full_norm == tok or suffix_norm == tok:
                        matched = True
                        break
                    # "CHZ-ERC20" gibi: suffix eşleşmesine ek güvence
                    if full_norm.endswith(tok):
                        matched = True
                        break

                if not matched:
                    continue

                if can_withdraw(ch):
                    withdrawable_matches.append(ch)
                else:
                    disabled_matches.append(ch)

            if not withdrawable_matches:
                # Config’e göre eşleşen chain var ama canWd=false olabilir; bunu ayrı döndürelim.
                reason = "chain_not_found"
                if disabled_matches:
                    reason = "withdraw_disabled_for_requested_chain"

                available_withdrawable = sorted(
                    {
                        (e.get("chain") or "").strip()
                        for e in entries
                        if isinstance(e, dict) and (e.get("chain") or "").strip() and can_withdraw(e)
                    }
                )
                matching_disabled = sorted({(e.get("chain") or "").strip() for e in disabled_matches})

                write_log(
                    {
                        "exchange": self.name,
                        "symbol": symbol.upper(),
                        "note": "OKX_STRICT_CHAIN_BLOCK",
                        "requested_network": want_raw,
                        "reason": reason,
                        "available_withdrawable_chains": available_withdrawable,
                        "matching_but_disabled": matching_disabled,
                    }
                )

                return (
                    {
                        "error": reason,
                        "symbol": symbol.upper(),
                        "requested_network": want_raw,
                        "available_withdrawable_chains": available_withdrawable,
                        "matching_but_disabled": matching_disabled,
                    },
                    400,
                )

            # Birden fazla eşleşme varsa config’e en yakın olanı seç (tam token match öncelikli)
            selected = None
            for ch in withdrawable_matches:
                chain_name = (ch.get("chain") or "").strip()
                full_norm = self._norm_token(chain_name)
                suffix_norm = self._norm_token(chain_name.split("-", 1)[-1])
                if full_norm == want_norm or suffix_norm == want_norm:
                    selected = ch
                    break
            if selected is None:
                selected = withdrawable_matches[0]

            chain = (selected.get("chain") or "").strip()
            fee = selected.get("minFee", "0")
        else:
            # Network belirtilmediyse eski otomatik seçim davranışı (mainnet/fallback) korunabilir.
            # Burada kısalık için mainnet seçiyoruz.
            chain = None
            fee = "0"
            for ch in entries:
                if not can_withdraw(ch):
                    continue
                chain = (ch.get("chain") or "").strip()
                fee = ch.get("minFee", "0")
                if chain:
                    break
            if not chain:
                return {"error": "chain_not_found", "available": data1}, 400

        fee_decimal = Decimal(str(fee or "0"))
        withdraw_amount = (amount - fee_decimal).quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)

        write_log(
            {
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_WITHDRAW_CALC",
                "available_amount": str(amount),
                "fee": str(fee_decimal),
                "withdraw_amount": str(withdraw_amount),
                "selected_chain": chain,
                "requested_network": want_raw,
            }
        )

        if withdraw_amount <= 0:
            return {"error": "amount_not_enough_after_fee"}, 400

        okx_chain = chain
        if "-" not in okx_chain:
            okx_chain = f"{symbol.upper()}-{okx_chain}"
        elif not okx_chain.startswith(symbol.upper() + "-"):
            chain_part = okx_chain.split("-", 1)[-1]
            okx_chain = f"{symbol.upper()}-{chain_part}"

        body = {
            "ccy": symbol.upper(),
            "amt": str(withdraw_amount),
            "dest": "4",
            "toAddr": address if memo in (None, "", "null", "None") else f"{address}:{memo}",
            "chain": okx_chain,
            "fee": str(fee or "0"),
        }

        b = json.dumps(body, separators=(",", ":"))
        ts2 = self._ts()
        path2 = "/api/v5/asset/withdrawal"
        h2 = self._headers(ts2, self._sign(ts2, "POST", path2, b))
        async with session.post(f"{self.API}{path2}", headers=h2, data=b) as r:
            return await r.json(content_type=None), r.status


ADAPTERS = {
    "Binance": BinanceAdapter,
    "Bybit": BybitAdapter,
    "OKX": OKXAdapter,
}

DEPOSIT_EXCHANGES = ["BTCTurk", "Paribu"]


async def run_withdraw_flow(exchange_name: str, target_exchange: str, coins: list[dict], q: Queue):
    adapter = ADAPTERS[exchange_name]()
    q.put(f"📍 Kaynak: {exchange_name}")
    q.put(f"📍 Alıcı: {target_exchange}")

    try:
        await adapter.preflight()
        q.put("✅ Bağlantı OK")
    except Exception as e:
        q.put(f"⛔ Preflight hata: {e}")
        if REQUIRE_STATIC_IP:
            return

    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # Bu workspace dosyasında sadece OKX strict chain mantığı örnekleniyor.
        # Kendi tam bot dosyanı kullanıyorsan burayı ignore edebilirsin.
        q.put("⚠️ Bu workspace dosyası demo amaçlı; kendi tam botunda sadece OKXAdapter.withdraw değişecek.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("850x550")
        self.minsize(750, 450)

        self.queue = Queue()
        self.worker_thread = None

        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        ttk.Label(top, text="Kaynak Borsa:").pack(side=tk.LEFT, padx=(0, 5))
        self.cmb_source = ttk.Combobox(top, values=list(ADAPTERS.keys()), state="readonly", width=10)
        self.cmb_source.current(2)
        self.cmb_source.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(top, text="Alıcı Borsa:").pack(side=tk.LEFT, padx=(0, 5))
        self.cmb_target = ttk.Combobox(top, values=DEPOSIT_EXCHANGES, state="readonly", width=10)
        self.cmb_target.current(0)
        self.cmb_target.pack(side=tk.LEFT, padx=(0, 10))

        self.btn = ttk.Button(top, text="🚀 TRANSFER BAŞLAT", command=self.on_run)
        self.btn.pack(side=tk.LEFT, padx=5)

        self.status = ttk.Label(top, text="Hazır", anchor="w")
        self.status.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.text = tk.Text(self, wrap="word", height=24)
        self.text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.text.configure(state="disabled")

        warn = ttk.Label(self, text="⚠️ Geri alınamaz! Yanlış adres = coin kaybı!", foreground="red")
        warn.pack(side=tk.BOTTOM, pady=5)

        self.after(UI_POLL_MS, self._poll)

    def log(self, msg):
        self.text.configure(state="normal")
        self.text.insert(tk.END, msg + "\n")
        self.text.see(tk.END)
        self.text.configure(state="disabled")

    def on_run(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Bekle", "İşlem devam ediyor")
            return

        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                coins = json.load(f)
        except Exception as e:
            messagebox.showerror("Config Hatası", str(e))
            return

        source_ex = self.cmb_source.get()
        target_ex = self.cmb_target.get()

        self.btn.configure(state="disabled")
        self.status.configure(text="Çalışıyor...")
        self.log("─" * 60)
        self.log(f"📦 {len(coins)} coin yüklendi")
        self.log(f"📍 Kaynak: {source_ex}")
        self.log(f"📍 Alıcı: {target_ex}")
        self.log("─" * 60)

        def runner():
            try:
                asyncio.run(run_withdraw_flow(source_ex, target_ex, coins, self.queue))
            except Exception as e:
                self.queue.put(f"⛔ Fatal: {e}")
            finally:
                self.queue.put("__DONE__")

        self.worker_thread = threading.Thread(target=runner, daemon=True)
        self.worker_thread.start()

    def _poll(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg == "__DONE__":
                    self.log("─" * 60)
                    self.log("✅ İŞLEM TAMAMLANDI")
                    self.log("─" * 60)
                    self.status.configure(text="Tamamlandı")
                    self.btn.configure(state="normal")
                else:
                    self.log(msg)
        except Empty:
            pass
        self.after(UI_POLL_MS, self._poll)


if __name__ == "__main__":
    app = App()
    app.mainloop()

