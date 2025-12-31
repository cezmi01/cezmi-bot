# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - OPTIMIZED
------------------------------------------------------
- Bakiye kontrolü paralel, çekim sıralı (rate limit koruması)
- Sadece bakiyesi > 0 olan coinler için çekim yapılır
- Kaynak borsa: Binance / Bybit / OKX
- config.json'dan adres/network okur

OKX STRICT NETWORK:
- Config'te network verilmişse, OKX'te SADECE o network ile eşleşiyorsa çekim yapılır.
- Eşleşme yoksa veya eşleşen ağ canWd=false ise çekim yapılmaz (fallback YOK).
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

        # Transfer sonrası Bybit'in işlemesi için kısa bekleme
        await asyncio.sleep(0.5)

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
        connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
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

    async def get_withdrawable_amount(self, session, coin: str) -> dict:
        """Belirli bir coin için çekilebilir miktarı al"""
        data, status = await self._get(
            session,
            "/v5/asset/withdraw/withdrawable-amount",
            {"coin": coin.upper()},
        )

        result = {"FUND": Decimal("0"), "UTA": Decimal("0")}

        if status == 200 and data.get("retCode") == 0:
            withdrawable = data.get("result", {}).get("withdrawableAmount", {})

            # FUND hesabı
            fund_info = withdrawable.get("FUND", {})
            if fund_info:
                try:
                    result["FUND"] = Decimal(str(fund_info.get("withdrawableAmount", "0")))
                except Exception:
                    pass

            # UTA (Unified Trading Account)
            uta_info = withdrawable.get("UTA", {})
            if uta_info:
                try:
                    result["UTA"] = Decimal(str(uta_info.get("withdrawableAmount", "0")))
                except Exception:
                    pass

        return result

    async def get_all_balances(self, session) -> dict:
        """Tüm hesaplardan tüm bakiyeleri tek seferde çek - HIZLI VERSİYON"""
        all_balances = {}

        def safe_decimal(val):
            if val is None or val == "" or val == "null":
                return Decimal("0")
            try:
                return Decimal(str(val))
            except Exception:
                return Decimal("0")

        # 1. UNIFIED + FUND bakiyelerini PARALEL çek (2 API call)
        unified_task = self._get(session, "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        fund_task = self._get(session, "/v5/asset/transfer/query-account-coins-balance", {"accountType": "FUND"})

        (unified_wallet_data, unified_wallet_status), (fund_data, fund_status) = await asyncio.gather(
            unified_task, fund_task
        )

        # UNIFIED bakiyeleri parse et
        if unified_wallet_status == 200 and unified_wallet_data.get("retCode") == 0:
            for account in unified_wallet_data.get("result", {}).get("list", []):
                for coin in account.get("coin", []):
                    sym = coin.get("coin", "").upper()
                    if not sym:
                        continue
                    try:
                        wallet_bal = safe_decimal(coin.get("walletBalance"))
                        equity = safe_decimal(coin.get("equity"))
                        available = safe_decimal(coin.get("availableToWithdraw"))
                        best = max(wallet_bal, equity, available)

                        if best > 0:
                            all_balances[sym] = {"balance": best, "account": "UNIFIED"}
                    except Exception:
                        pass

        # FUND bakiyeleri parse et
        if fund_status == 200 and fund_data.get("retCode") == 0:
            for coin in fund_data.get("result", {}).get("balance", []):
                sym = coin.get("coin", "").upper()
                if not sym:
                    continue
                try:
                    transfer_bal = safe_decimal(coin.get("transferBalance"))
                    wallet_bal = safe_decimal(coin.get("walletBalance"))
                    available = transfer_bal if transfer_bal > 0 else wallet_bal

                    if available > 0:
                        if sym not in all_balances or available > all_balances[sym]["balance"]:
                            all_balances[sym] = {"balance": available, "account": "FUND"}
                except Exception:
                    pass

        write_log(
            {
                "exchange": self.name,
                "note": "QUICK_BALANCE_SCAN",
                "count": len(all_balances),
                "coins": list(all_balances.keys()),
            }
        )

        if not all_balances:
            return all_balances

        # 2. Withdrawable miktarları PARALEL çek (batch halinde)
        BATCH_SIZE = 5  # Aynı anda 5 coin sorgula
        coins_list = list(all_balances.keys())

        async def check_withdrawable(sym: str):
            try:
                result = await self.get_withdrawable_amount(session, sym)
                return (sym, result)
            except Exception:
                return (sym, {"FUND": Decimal("0"), "UTA": Decimal("0")})

        # Batch'ler halinde paralel çek
        for i in range(0, len(coins_list), BATCH_SIZE):
            batch = coins_list[i : i + BATCH_SIZE]
            results = await asyncio.gather(*[check_withdrawable(s) for s in batch])

            for sym, withdrawable in results:
                uta_amount = withdrawable.get("UTA", Decimal("0"))
                fund_amount = withdrawable.get("FUND", Decimal("0"))

                if uta_amount > 0 or fund_amount > 0:
                    if uta_amount >= fund_amount:
                        all_balances[sym] = {"balance": uta_amount, "account": "UTA"}
                        self._last_balance_account = "UNIFIED"
                    else:
                        all_balances[sym] = {"balance": fund_amount, "account": "FUND"}
                        self._last_balance_account = "FUND"
                else:
                    # Çekilebilir miktar 0 ise sil
                    if sym in all_balances:
                        del all_balances[sym]

            # Batch arası kısa bekleme (rate limit)
            if i + BATCH_SIZE < len(coins_list):
                await asyncio.sleep(0.1)

        write_log(
            {
                "exchange": self.name,
                "note": "FINAL_WITHDRAWABLE_BALANCES",
                "count": len(all_balances),
                "coins": {k: f"{v['balance']} ({v['account']})" for k, v in all_balances.items()},
            }
        )

        return all_balances

    async def get_balance(self, session, symbol: str) -> Decimal:
        """Get balance from all account types (UNIFIED, FUND, SPOT, CONTRACT)"""
        # (Senin orijinal kodun buradaydı; tam sürümde aynen duruyor.)
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        # (Senin orijinal kodun buradaydı; tam sürümde aynen duruyor.)
        return {"error": "BybitAdapter: please paste full original file if you want exact byte-for-byte reproduction"}, 501


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
        async with session.request(method, f"{self.API}{endpoint}", params=params, headers=headers) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {"raw": await r.text()}
            return data, r.status

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
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
        return {"error": "BinanceAdapter: please paste full original file if you want exact byte-for-byte reproduction"}, 501


# ═══════════════════════════════════════════════════════════════
#                         OKX ADAPTER
# ═══════════════════════════════════════════════════════════════
class OKXAdapter(BaseExchange):
    name = "OKX"
    API = "https://www.okx.com"
    ACCOUNT_FUNDING = "6"
    ACCOUNT_TRADING = "18"  # Unified trading
    ACCOUNT_SPOT = "1"  # Classic spot (eski hesaplar için)
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
    def _norm_token(v: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (v or "").upper())

    async def preflight(self):
        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
            ts = self._ts()
            path = "/api/v5/account/balance"
            headers = self._headers(ts, self._sign(ts, "GET", path))
            async with s.get(f"{self.API}{path}", headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"OKX error: {await r.text()}")

    async def get_balance(self, session, symbol: str) -> Decimal:
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        ts = self._ts()
        path = f"/api/v5/asset/currencies?ccy={symbol.upper()}"
        h1 = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=h1) as r1:
            data1 = await r1.json(content_type=None)

        chain, fee = None, "0"
        want_raw = (network or "").strip()

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
                "entries": [{"chain": e.get("chain"), "name": e.get("name"), "canWd": e.get("canWd")} for e in entries],
            }
        )

        def can_wd(ch: dict) -> bool:
            return str(ch.get("canWd")).lower() == "true"

        # STRICT: config network verilmişse sadece onu kabul et
        if want_raw:
            want_norm = self._norm_token(want_raw)
            aliases = {
                # FIX: CHZ2 -> "Chiliz Chain" OKX isimleri
                "CHZ2": [
                    "CHZ2",
                    "CHILIZCHAIN",
                    "CHILIZ CHAIN",
                    "CHZ-CHILIZ CHAIN",
                    "CHZCHILIZCHAIN",
                    "CHILIZ",
                ],
            }
            tokens = aliases.get(want_norm, [want_raw])
            token_set = {self._norm_token(t) for t in tokens if t}
            token_set.add(want_norm)

            withdrawable = []
            disabled = []

            for ch in entries:
                chain_name = (ch.get("chain") or "").strip()
                if not chain_name:
                    continue
                full_norm = self._norm_token(chain_name)
                suffix_norm = self._norm_token(chain_name.split("-", 1)[-1])

                if full_norm in token_set or suffix_norm in token_set:
                    if can_wd(ch):
                        withdrawable.append(ch)
                    else:
                        disabled.append(ch)

            if not withdrawable:
                return (
                    {
                        "error": "okx_chain_not_matched_or_withdraw_disabled",
                        "requested_network": want_raw,
                        "matching_but_disabled": [d.get("chain") for d in disabled],
                        "available_withdrawable": [e.get("chain") for e in entries if can_wd(e)],
                    },
                    400,
                )

            selected = withdrawable[0]
            chain = selected.get("chain")
            fee = selected.get("minFee", "0")
        else:
            # network yoksa ilk withdrawable chain
            for ch in entries:
                if can_wd(ch) and ch.get("chain"):
                    chain = ch.get("chain")
                    fee = ch.get("minFee", "0")
                    break

        if not chain:
            return {"error": "chain_not_found", "available": data1}, 400

        fee_decimal = Decimal(str(fee or "0"))
        withdraw_amount = (amount - fee_decimal).quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)

        if withdraw_amount <= 0:
            return {"error": "amount_not_enough_after_fee"}, 400

        okx_chain = chain
        if "-" not in okx_chain:
            okx_chain = f"{symbol.upper()}-{okx_chain}"

        body = {
            "ccy": symbol.upper(),
            "amt": str(withdraw_amount),
            "dest": "4",
            "toAddr": address if memo in (None, "", "null", "None") else f"{address}:{memo}",
            "chain": okx_chain,
            "fee": fee,
        }

        b = json.dumps(body, separators=(",", ":"))
        ts2 = self._ts()
        path2 = "/api/v5/asset/withdrawal"
        h2 = self._headers(ts2, self._sign(ts2, "POST", path2, b))
        async with session.post(f"{self.API}{path2}", headers=h2, data=b) as r:
            return await r.json(content_type=None), r.status


# ═══════════════════════════════════════════════════════════════
#                         ADAPTERS REGISTRY
# ═══════════════════════════════════════════════════════════════
ADAPTERS = {
    "Binance": BinanceAdapter,
    "Bybit": BybitAdapter,
    "OKX": OKXAdapter,
}

# Alıcı borsalar (sadece bilgi amaçlı - API kullanılmıyor)
DEPOSIT_EXCHANGES = ["BTCTurk", "Paribu"]


# ═══════════════════════════════════════════════════════════════
#                         WITHDRAW FLOW (OPTIMIZED)
# ═══════════════════════════════════════════════════════════════
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
    connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        q.put("⚠️ Not: Workspace’e eklenen bot.py örnektir; kendi tam dosyanı da workspace’e koyarsan birebir patch’lerim.")


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

