# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - BYBIT FIX
-----------------------------------------------------
- Bybit timestamp sorunu tamamen çözüldü
- Kaynak borsa: Binance / Bybit / OKX / Gate / Bitget
- config.json'dan adres/network okur
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
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from queue import Queue, Empty
from urllib.parse import urlencode

import tkinter as tk
from tkinter import ttk, messagebox

import aiohttp
from dotenv import load_dotenv

APP_TITLE = "Multi-Exchange Çekim Botu"
CONFIG_PATH = Path("config.json")
LOG_PATH = Path("withdraw_logs.jsonl")

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

UI_POLL_MS = 100
REQUIRE_STATIC_IP = False


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
            "erc20": f"{sym}-ERC20",
            "eth-erc20": f"{sym}-ERC20",
            "ethereum": f"{sym}-ERC20",
            "ethereum mainnet": f"{sym}-ERC20",
            "ethereum (erc20)": f"{sym}-ERC20",
            "arbitrum": f"{sym}-ARBITRUM",
            "arbitrum one": f"{sym}-ARBITRUM",
            "polygon": f"{sym}-POLYGON",
            "polygon (matic)": f"{sym}-POLYGON",
            "matic": f"{sym}-POLYGON",
            "bsc": f"{sym}-BSC",
            "bnb smart chain": f"{sym}-BSC",
            "bep20": f"{sym}-BSC",
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
        return f"{sym}-{clean}"

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
            match = re.search(r"wait at least\s*(\d+)\s*seconds", msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) + 1
                except ValueError:
                    pass
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
        """Ensure Funding account holds enough balance to cover withdrawal (amount + fee)."""
        required = required.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        if required <= 0:
            return

        sym = symbol.upper()

        data, status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coin-balance",
            {"accountType": "FUND", "coin": sym},
        )

        fund_available = Decimal(str(data.get("result", {}).get("availableToWithdraw", "0"))) if status == 200 else Decimal("0")

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

        write_log(
            {
                "exchange": self.name,
                "symbol": sym,
                "action": "TRANSFER_PREP",
                "required": str(required),
                "fund_available": str(fund_available),
                "from": "UNIFIED",
                "to": "FUND",
            }
        )

        resp, resp_status = await self._post(session, "/v5/asset/transfer/inter-transfer", transfer_body)

        if resp_status != 200 or resp.get("retCode") != 0:
            raise RuntimeError(
                f"Bybit transfer failed: HTTP {resp_status}, retCode={resp.get('retCode')}, retMsg={resp.get('retMsg')}"
            )

        self._last_balance_account = "FUND"
        write_log(
            {
                "exchange": self.name,
                "symbol": sym,
                "action": "TRANSFER_OK",
                "transferId": resp.get("result", {}).get("transferId"),
                "amount": str(required),
            }
        )

    async def _get(self, session, endpoint, params=None):
        """GET request"""
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
                        write_log(
                            {
                                "exchange": self.name,
                                "note": "cooldown_wait",
                                "endpoint": endpoint,
                                "delay_seconds": delay,
                            }
                        )
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_get_error"}, 500

    async def _post(self, session, endpoint, body: dict):
        """POST request"""
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

            write_log(
                {
                    "exchange": self.name,
                    "action": "POST",
                    "endpoint": endpoint,
                    "timestamp": ts,
                    "body": body_with_meta,
                }
            )

            async with session.post(url, data=body_json, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if not isinstance(data, dict):
                    data = {"raw": data}

                write_log(
                    {
                        "exchange": self.name,
                        "action": "POST_RESPONSE",
                        "endpoint": endpoint,
                        "http_status": resp.status,
                        "retCode": data.get("retCode"),
                        "retMsg": data.get("retMsg"),
                        "server_time": data.get("time"),
                        "sent_timestamp": ts,
                    }
                )

                last_response = (data, resp.status)

                if attempt < self.MAX_RETRIES and resp.status == 200 and self._is_timestamp_error(data):
                    await self._sync_time(session)
                    continue

                if attempt < self.MAX_RETRIES:
                    delay = self._cooldown_seconds(data)
                    if delay:
                        write_log(
                            {
                                "exchange": self.name,
                                "action": "POST_COOLDOWN_WAIT",
                                "endpoint": endpoint,
                                "delay_seconds": delay,
                            }
                        )
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_post_error"}, 500

    async def preflight(self):
        """Connection & permission check"""
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            await self._sync_time(s)

            data, status = await self._get(s, "/v5/user/query-api")

            write_log(
                {
                    "exchange": self.name,
                    "note": "preflight",
                    "status": status,
                    "retCode": data.get("retCode"),
                    "retMsg": data.get("retMsg"),
                }
            )

            if status != 200:
                raise RuntimeError(f"Bybit HTTP {status}")

            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit error: {data.get('retMsg')}")

            perms = data.get("result", {}).get("permissions", {})
            if "Wallet" not in perms:
                raise RuntimeError(f"Wallet permission missing! Available: {list(perms.keys())}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        """Get balance from UNIFIED account"""
        sym = symbol.upper()

        balance_data, balance_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "UNIFIED", "coin": sym},
        )

        unified_available = Decimal("0")
        if balance_status == 200 and balance_data.get("retCode") == 0:
            coins = balance_data.get("result", {}).get("balance", [])
            for coin in coins:
                if coin.get("coin", "").upper() == sym:
                    try:
                        unified_available = Decimal(str(coin.get("transferBalance", "0")))
                    except Exception:
                        unified_available = Decimal("0")
                    write_log(
                        {
                            "exchange": self.name,
                            "symbol": sym,
                            "note": "UNIFIED_BALANCE",
                            "transferBalance": str(unified_available),
                        }
                    )
                    break

        if unified_available > 0:
            self._last_balance_account = "UNIFIED"
            return unified_available

        funding_data, funding_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "FUND", "coin": sym},
        )
        if funding_status == 200 and funding_data.get("retCode") == 0:
            coins = funding_data.get("result", {}).get("balance", [])
            for coin in coins:
                if coin.get("coin", "").upper() == sym:
                    fund_available = Decimal(str(coin.get("transferBalance", "0")))
                    if fund_available > 0:
                        self._last_balance_account = "FUND"
                        write_log(
                            {
                                "exchange": self.name,
                                "symbol": sym,
                                "balance": str(fund_available),
                                "account": "FUND",
                                "source": "transferBalance",
                            }
                        )
                        return fund_available
                    break

        self._last_balance_account = None
        write_log({"exchange": self.name, "symbol": sym, "note": "NO_BALANCE"})

        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        """Withdraw coins"""
        sym = symbol.upper()

        cfg = self.COINS.get(sym, {"chain": None, "fee": "0.001", "min": "0.01"})
        chain = self._normalize_chain(sym, network or cfg.get("chain"))
        fee = Decimal(cfg["fee"])
        min_amount = Decimal(cfg["min"])

        final_amount = amount - fee

        write_log(
            {
                "exchange": self.name,
                "symbol": sym,
                "note": "withdraw_calc",
                "balance": str(amount),
                "fee": str(fee),
                "final_amount": str(final_amount),
                "chain": chain,
                "threshold": str(min_amount),
            }
        )

        if final_amount < min_amount:
            return (
                {
                    "retCode": -1,
                    "retMsg": f"Insufficient. Balance: {amount}, Fee: {fee}, Min: {min_amount}",
                },
                400,
            )

        body = {
            "coin": sym,
            "chain": chain,
            "address": address,
            "amount": str(final_amount),
        }

        if memo not in (None, "", "null", "None"):
            body["tag"] = str(memo)

        total_required = amount

        lock = await self._get_withdraw_lock()
        async with lock:
            await self._wait_for_withdraw_slot()
            await self._ensure_fund_liquidity(session, sym, total_required)
            try:
                return await self._post(session, "/v5/asset/withdraw/create", body)
            finally:
                self._last_withdraw_request = time.monotonic()


# ═══════════════════════════════════════════════════════════════
#                         BINANCE ADAPTER
# ═══════════════════════════════════════════════════════════════
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
        async with session.request(
            method, f"{self.API}{endpoint}", params=params, headers=headers
        ) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {"raw": await r.text()}
            return data, r.status

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
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
        params = {"coin": symbol.upper(), "address": address, "amount": str(amount)}
        if network:
            params["network"] = network
        if memo not in (None, "", "null", "None"):
            params["addressTag"] = str(memo)
        return await self._req(session, "POST", "/sapi/v1/capital/withdraw/apply", params)


# ═══════════════════════════════════════════════════════════════
#                         OKX ADAPTER
# ═══════════════════════════════════════════════════════════════
class OKXAdapter(BaseExchange):
    name = "OKX"
    API = "https://www.okx.com"
    ACCOUNT_FUNDING = "6"
    ACCOUNT_TRADING = "18"
    MIN_DECIMAL_STEP = Decimal("0.00000001")

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

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            ts = self._ts()
            path = "/api/v5/account/balance"
            headers = self._headers(ts, self._sign(ts, "GET", path))
            async with s.get(f"{self.API}{path}", headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"OKX error: {await r.text()}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        ts = self._ts()
        path = "/api/v5/account/balance"
        headers = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=headers) as r:
            data = await r.json(content_type=None)
            bal = Decimal("0")
            for d in data.get("data", []):
                for c in d.get("details", []):
                    if c.get("ccy", "").upper() == symbol.upper():
                        try:
                            bal += Decimal(c.get("availBal", "0"))
                        except Exception:
                            pass
            return bal

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        ts = self._ts()
        path = f"/api/v5/asset/currencies?ccy={symbol.upper()}"
        h1 = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=h1) as r1:
            data1 = await r1.json(content_type=None)

        chain, fee = None, "0"
        want_raw = (network or "").strip()
        want = want_raw.upper()
        fallback = None
        entries = []
        for item in data1.get("data", []):
            chains_list = item.get("chains")
            if isinstance(chains_list, list) and chains_list:
                entries.extend(chains_list)
            else:
                entries.append(item)

        write_log(
            {
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_CHAIN_CHECK",
                "network_request": want_raw,
                "entries": [e.get("chain") for e in entries],
            }
        )

        for ch in entries:
            can_wd = str(ch.get("canWd")).lower() == "true"
            if not can_wd:
                continue
            chain_name = ch.get("chain", "")
            if not chain_name:
                continue
            chain_upper = chain_name.upper()
            cleaned_chain = chain_upper.replace(" ", "").replace("-", "")
            if want:
                normalized_want = want.replace(" ", "").replace("-", "")
                if normalized_want in cleaned_chain or cleaned_chain in normalized_want:
                    chain = chain_name
                    fee = ch.get("minFee", "0")
                    write_log(
                        {
                            "exchange": self.name,
                            "symbol": symbol.upper(),
                            "note": "OKX_CHAIN_MATCH",
                            "selected_chain": chain,
                            "match": normalized_want,
                        }
                    )
                    break
                if want_raw and want_raw.lower() == str(ch.get("name", "")).lower():
                    chain = chain_name
                    fee = ch.get("minFee", "0")
                    write_log(
                        {
                            "exchange": self.name,
                            "symbol": symbol.upper(),
                            "note": "OKX_CHAIN_NAME_MATCH",
                            "selected_chain": chain,
                            "match_name": want_raw,
                        }
                    )
                    break
            else:
                chain = chain_name
                fee = ch.get("minFee", "0")
                write_log(
                    {
                        "exchange": self.name,
                        "symbol": symbol.upper(),
                        "note": "OKX_CHAIN_FALLBACK_FIRST",
                        "selected_chain": chain,
                    }
                )
                break
            if fallback is None:
                fallback = ch

        if not chain and fallback:
            chain = fallback.get("chain")
            fee = fallback.get("minFee", "0")

        if not chain:
            return {"error": "chain_not_found", "available": data1}, 400

        fee_decimal = Decimal(str(fee or "0"))
        available_amount = amount
        withdraw_amount = (available_amount - fee_decimal).quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)

        write_log(
            {
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_WITHDRAW_CALC",
                "available_amount": str(available_amount),
                "fee": str(fee_decimal),
                "withdraw_amount": str(withdraw_amount),
            }
        )

        if withdraw_amount <= 0:
            return {"error": "amount_not_enough_after_fee"}, 400

        await self._ensure_funding_liquidity(session, symbol, available_amount)

        body = {
            "ccy": symbol.upper(),
            "amt": str(withdraw_amount),
            "dest": "4",
            "toAddr": address if memo in (None, "", "null", "None") else f"{address}:{memo}",
            "chain": chain,
            "fee": fee,
        }
        b = json.dumps(body, separators=(",", ":"))
        ts2 = self._ts()
        path2 = "/api/v5/asset/withdrawal"
        h2 = self._headers(ts2, self._sign(ts2, "POST", path2, b))
        async with session.post(f"{self.API}{path2}", headers=h2, data=b) as r:
            return await r.json(content_type=None), r.status

    async def _ensure_funding_liquidity(self, session, symbol: str, required_amount: Decimal):
        total_required = required_amount
        if total_required <= 0:
            return

        total_required = total_required.quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)
        ccy = symbol.upper()

        # Query current funding balance
        path_balance = f"/api/v5/asset/balances?ccy={ccy}"
        ts_balance = self._ts()
        h_balance = self._headers(ts_balance, self._sign(ts_balance, "GET", path_balance))
        funding_available = Decimal("0")
        async with session.get(f"{self.API}{path_balance}", headers=h_balance) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {"raw": await resp.text()}

        if isinstance(data, dict) and data.get("code") in ("0", 0):
            for entry in data.get("data", []):
                if entry.get("ccy", "").upper() == ccy:
                    try:
                        funding_available = Decimal(str(entry.get("availBal", "0")))
                    except Exception:
                        funding_available = Decimal("0")
                    break

        write_log(
            {
                "exchange": self.name,
                "symbol": ccy,
                "note": "OKX_FUNDING_BALANCE",
                "funding_available": str(funding_available),
                "required": str(total_required),
            }
        )

        if funding_available >= total_required:
            return

        transfer_amount = (total_required - funding_available)
        if transfer_amount <= 0:
            return

        transfer_amount = transfer_amount.quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)

        transfer_body = {
            "type": "0",
            "ccy": ccy,
            "amt": str(transfer_amount),
            "from": self.ACCOUNT_TRADING,
            "to": self.ACCOUNT_FUNDING,
        }

        ts_transfer = self._ts()
        path_transfer = "/api/v5/asset/transfer"
        body_json = json.dumps(transfer_body, separators=(",", ":"))
        headers_transfer = self._headers(ts_transfer, self._sign(ts_transfer, "POST", path_transfer, body_json))

        write_log(
            {
                "exchange": self.name,
                "symbol": ccy,
                "note": "OKX_TRANSFER_INIT",
                "amount": transfer_body["amt"],
                "from": self.ACCOUNT_TRADING,
                "to": self.ACCOUNT_FUNDING,
            }
        )

        async with session.post(f"{self.API}{path_transfer}", headers=headers_transfer, data=body_json) as resp:
            try:
                transfer_data = await resp.json(content_type=None)
            except Exception:
                transfer_data = {"raw": await resp.text()}

        write_log(
            {
                "exchange": self.name,
                "symbol": ccy,
                "note": "OKX_TRANSFER_RESPONSE",
                "status": resp.status,
                "response": transfer_data,
            }
        )

        success_codes = {"0", 0, "00000"}
        if not (resp.status == 200 and transfer_data.get("code") in success_codes):
            raise RuntimeError(
                f"OKX transfer failed: HTTP {resp.status}, code={transfer_data.get('code')}, msg={transfer_data.get('msg')}"
            )


# ═══════════════════════════════════════════════════════════════
#                         GATE ADAPTER
# ═══════════════════════════════════════════════════════════════
class GateAdapter(BaseExchange):
    name = "GATE"
    API = "https://api.gateio.ws/api/v4"

    def __init__(self):
        self.key = os.getenv("GATE_KEY", "")
        self.secret = os.getenv("GATE_SECRET", "")

    def _sign(self, ts, method, path, query="", body=""):
        hashed = hashlib.sha512(body.encode()).hexdigest()
        s = "\n".join([method.upper(), path, query or "", hashed, ts])
        return hmac.new(self.secret.encode(), s.encode(), "sha512").hexdigest()

    def _headers(self, ts, sign):
        return {"KEY": self.key, "SIGN": sign, "Timestamp": ts, "Content-Type": "application/json"}

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            ts = str(int(time.time()))
            path = "/spot/accounts"
            h = self._headers(ts, self._sign(ts, "GET", path))
            async with s.get(f"{self.API}{path}", headers=h) as r:
                if r.status != 200:
                    raise RuntimeError(f"Gate error: {await r.text()}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        ts = str(int(time.time()))
        path = "/spot/accounts"
        h = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=h) as r:
            data = await r.json(content_type=None)
            bal = Decimal("0")
            for a in data:
                if a.get("currency", "").upper() == symbol.upper():
                    try:
                        bal += Decimal(a.get("available", "0"))
                    except Exception:
                        pass
            return bal

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        body = {"currency": symbol.upper(), "amount": str(amount), "address": address}
        if network:
            body["chain"] = network
        if memo not in (None, "", "null", "None"):
            body["memo"] = str(memo)
        b = json.dumps(body, separators=(",", ":"))
        ts = str(int(time.time()))
        path = "/wallet/withdrawals"
        h = self._headers(ts, self._sign(ts, "POST", path, "", b))
        async with session.post(f"{self.API}{path}", headers=h, data=b) as r:
            return await r.json(content_type=None), r.status


# ═══════════════════════════════════════════════════════════════
#                         BITGET ADAPTER
# ═══════════════════════════════════════════════════════════════
class BitgetAdapter(BaseExchange):
    name = "BITGET"
    API = "https://api.bitget.com"

    def __init__(self):
        self.key = os.getenv("BITGET_KEY", "")
        self.secret = os.getenv("BITGET_SECRET", "")
        self.passphrase = os.getenv("BITGET_PASSPHRASE", "")

    def _sign(self, ts, method, path, body=""):
        pre = f"{ts}{method.upper()}{path}{body}"
        return base64.b64encode(hmac.new(self.secret.encode(), pre.encode(), "sha256").digest()).decode()

    def _headers(self, ts, sign):
        return {
            "ACCESS-KEY": self.key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            ts = str(int(time.time() * 1000))
            path = "/api/v2/account/all-account-balance"
            h = self._headers(ts, self._sign(ts, "GET", path))
            async with s.get(f"{self.API}{path}", headers=h) as r:
                if r.status != 200:
                    raise RuntimeError(f"Bitget error: {await r.text()}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        ts = str(int(time.time() * 1000))
        path = "/api/v2/account/all-account-balance"
        h = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=h) as r:
            data = await r.json(content_type=None)
            bal = Decimal("0")
            for item in data.get("data", []):
                if item.get("coin", "").upper() == symbol.upper():
                    try:
                        bal += Decimal(item.get("available", "0"))
                    except Exception:
                        pass
            return bal

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        body = {
            "coin": symbol.upper(),
            "transferType": "on_chain",
            "address": address,
            "size": str(amount),
        }
        if network:
            body["chain"] = network
        if memo not in (None, "", "null", "None"):
            body["memo"] = str(memo)
        b = json.dumps(body, separators=(",", ":"))
        ts = str(int(time.time() * 1000))
        path = "/api/v2/spot/wallet/withdrawal"
        h = self._headers(ts, self._sign(ts, "POST", path, b))
        async with session.post(f"{self.API}{path}", headers=h, data=b) as r:
            return await r.json(content_type=None), r.status


# ═══════════════════════════════════════════════════════════════
#                         ADAPTERS REGISTRY
# ═══════════════════════════════════════════════════════════════
ADAPTERS = {
    "Binance": BinanceAdapter,
    "Bybit": BybitAdapter,
    "OKX": OKXAdapter,
    "Gate": GateAdapter,
    "Bitget": BitgetAdapter,
}


# ═══════════════════════════════════════════════════════════════
#                         WITHDRAW FLOW
# ═══════════════════════════════════════════════════════════════
async def run_withdraw_flow(exchange_name: str, coins: list[dict], q: Queue):
    adapter = ADAPTERS[exchange_name]()
    q.put(f"📍 Kaynak: {exchange_name}")

    try:
        await adapter.preflight()
        q.put("✅ Bağlantı OK")
    except Exception as e:
        q.put(f"⛔ Preflight hata: {e}")
        if REQUIRE_STATIC_IP:
            return

    async def work(coin: dict):
        symbol = coin["symbol"].upper()
        network = coin.get("network", "")
        address = coin["address"]
        memo = coin.get("memo")

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            try:
                bal = await adapter.get_balance(s, symbol)
                q.put(f"{symbol}: Bakiye = {bal}")
            except Exception as e:
                q.put(f"{symbol}: ❌ Bakiye hatası: {e}")
                return

            if bal <= 0:
                q.put(f"{symbol}: ⚪ Atlandı (bakiye 0)")
                return

            amt = floor_amount(bal)
            q.put(f"{symbol}: 🚀 Çekim başlatılıyor... ({amt})")

            try:
                data, status = await adapter.withdraw(s, symbol, network, address, memo, amt)

                if isinstance(data, dict):
                    ret_code = data.get("retCode", data.get("code"))
                    ret_msg = data.get("retMsg") or data.get("msg") or data.get("message", "")

                    success = False

                    if ret_code in (0, "0", "success"):
                        success = True
                    elif ret_code is None and status in (200, 201, 202):
                        if data.get("success") is True:
                            success = True
                        elif any(key in data for key in ("id", "withdrawId", "applyId", "data", "result")):
                            success = True

                    if success:
                        q.put(f"{symbol}: ✅ BAŞARILI")
                        write_log(
                            {
                                "exchange": adapter.name,
                                "symbol": symbol,
                                "status": "success",
                                "amount": str(amt),
                                "response": data,
                            }
                        )
                    else:
                        q.put(f"{symbol}: ❌ HATA - {ret_msg or json.dumps(data)} (code: {ret_code})")
                        write_log(
                            {
                                "exchange": adapter.name,
                                "symbol": symbol,
                                "status": "error",
                                "retCode": ret_code,
                                "retMsg": ret_msg,
                                "response": data,
                            }
                        )
                else:
                    ok = status in (200, 201)
                    q.put(f"{symbol}: {'✅' if ok else '❌'} HTTP {status}")
                    write_log(
                        {
                            "exchange": adapter.name,
                            "symbol": symbol,
                            "status": "success" if ok else "error",
                            "http_status": status,
                            "response": data,
                        }
                    )

            except Exception as e:
                q.put(f"{symbol}: ❌ Exception: {e}")
                write_log(
                    {
                        "exchange": adapter.name,
                        "symbol": symbol,
                        "status": "exception",
                        "error": str(e),
                    }
                )

    await asyncio.gather(*[work(c) for c in coins])


# ═══════════════════════════════════════════════════════════════
#                         GUI
# ═══════════════════════════════════════════════════════════════
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
        self.cmb = ttk.Combobox(top, values=list(ADAPTERS.keys()), state="readonly", width=10)
        self.cmb.current(1)
        self.cmb.pack(side=tk.LEFT, padx=(0, 10))

        self.btn = ttk.Button(top, text="🚀 TÜM COİNLERİ ÇEK", command=self.on_run)
        self.btn.pack(side=tk.LEFT, padx=5)

        self.status = ttk.Label(top, text="Hazır", anchor="w")
        self.status.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.text = tk.Text(self, wrap="word", height=24)
        self.text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.text.configure(state="disabled")

        warn = ttk.Label(
            self, text="⚠️ Geri alınamaz! Yanlış adres = coin kaybı!", foreground="red"
        )
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

        ex = self.cmb.get()
        self.btn.configure(state="disabled")
        self.status.configure(text="Çalışıyor...")
        self.log("─" * 60)
        self.log(f"📦 {len(coins)} coin yüklendi")
        self.log(f"📍 Kaynak: {ex}")
        self.log("─" * 60)

        def runner():
            try:
                asyncio.run(run_withdraw_flow(ex, coins, self.queue))
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
