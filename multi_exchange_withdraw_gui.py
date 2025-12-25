# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - OPTIMIZED
------------------------------------------------------
- Bakiye kontrolü paralel, çekim sıralı (rate limit koruması)
- Sadece bakiyesi > 0 olan coinler için çekim yapılır
- Kaynak borsa: Binance / Bybit / OKX
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
        code = data.get("retCode")
        if data.get("retCode") == 131001:
            match = re.search(r"wait at least\s*(\d+)\s*seconds", msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) + 1
                except ValueError:
                    pass

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
        """Get balance from all account types (UNIFIED, FUND, SPOT, CONTRACT)"""
        sym = symbol.upper()
        
        # 1. Önce UNIFIED hesabı kontrol et
        balance_data, balance_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "UNIFIED", "coin": sym},
        )

        if balance_status == 200 and balance_data.get("retCode") == 0:
            coins = balance_data.get("result", {}).get("balance", [])
            for coin in coins:
                if coin.get("coin", "").upper() == sym:
                    try:
                        unified_available = Decimal(str(coin.get("transferBalance", "0")))
                    except Exception:
                        unified_available = Decimal("0")
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "UNIFIED_BALANCE",
                        "transferBalance": str(unified_available),
                    })
                    if unified_available > 0:
                        self._last_balance_account = "UNIFIED"
                        return unified_available
                    break

        # 2. FUND hesabını kontrol et (iki farklı endpoint dene)
        # Endpoint 1: query-account-coins-balance
        funding_data, funding_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "FUND", "coin": sym},
        )
        
        if funding_status == 200 and funding_data.get("retCode") == 0:
            coins = funding_data.get("result", {}).get("balance", [])
            for coin in coins:
                if coin.get("coin", "").upper() == sym:
                    try:
                        fund_available = Decimal(str(coin.get("transferBalance", "0")))
                        wallet_balance = Decimal(str(coin.get("walletBalance", "0")))
                    except Exception:
                        fund_available = Decimal("0")
                        wallet_balance = Decimal("0")
                    
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "FUND_BALANCE_CHECK",
                        "transferBalance": str(fund_available),
                        "walletBalance": str(wallet_balance),
                    })
                    
                    if fund_available > 0:
                        self._last_balance_account = "FUND"
                        return fund_available
                    break
        
        # 3. Alternatif endpoint: /v5/asset/coin/query-info (tüm coinler)
        all_coins_data, all_coins_status = await self._get(
            session,
            "/v5/asset/transfer/query-asset-info",
            {"accountType": "FUND", "coin": sym},
        )
        
        if all_coins_status == 200 and all_coins_data.get("retCode") == 0:
            spot_info = all_coins_data.get("result", {}).get("spot", {})
            assets = spot_info.get("assets", [])
            for asset in assets:
                if asset.get("coin", "").upper() == sym:
                    try:
                        free = Decimal(str(asset.get("free", "0")))
                    except Exception:
                        free = Decimal("0")
                    
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "FUND_ASSET_INFO",
                        "free": str(free),
                    })
                    
                    if free > 0:
                        self._last_balance_account = "FUND"
                        return free
                    break
        
        # 4. Diğer hesap türlerini kontrol et (SPOT, CONTRACT)
        for account_type in ["SPOT", "CONTRACT"]:
            other_data, other_status = await self._get(
                session,
                "/v5/asset/transfer/query-account-coins-balance",
                {"accountType": account_type, "coin": sym},
            )
            
            if other_status == 200 and other_data.get("retCode") == 0:
                coins = other_data.get("result", {}).get("balance", [])
                for coin in coins:
                    if coin.get("coin", "").upper() == sym:
                        try:
                            available = Decimal(str(coin.get("transferBalance", "0")))
                        except Exception:
                            available = Decimal("0")
                        
                        write_log({
                            "exchange": self.name,
                            "symbol": sym,
                            "note": f"{account_type}_BALANCE",
                            "transferBalance": str(available),
                        })
                        
                        if available > 0:
                            self._last_balance_account = account_type
                            return available
                        break

        self._last_balance_account = None
        write_log({"exchange": self.name, "symbol": sym, "note": "NO_BALANCE_ALL_ACCOUNTS"})

        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        """Withdraw coins - dynamically fetches chain and fee info from Bybit API"""
        sym = symbol.upper()
        
        # ══════════════════════════════════════════════════════════
        # 1. Bybit API'den coin bilgilerini çek (chain, fee, min)
        # ══════════════════════════════════════════════════════════
        coin_info_data, coin_info_status = await self._get(
            session,
            "/v5/asset/coin/query-info",
            {"coin": sym},
        )
        
        chain = None
        fee = Decimal("0")
        min_amount = Decimal("0")
        
        want_network = (network or "").strip().upper()
        
        if coin_info_status == 200 and coin_info_data.get("retCode") == 0:
            rows = coin_info_data.get("result", {}).get("rows", [])
            
            for row in rows:
                if row.get("coin", "").upper() != sym:
                    continue
                    
                chains = row.get("chains", [])
                
                write_log({
                    "exchange": self.name,
                    "symbol": sym,
                    "note": "BYBIT_CHAINS_AVAILABLE",
                    "chains": [{"chain": c.get("chain"), "chainType": c.get("chainType")} for c in chains],
                    "requested_network": want_network,
                })
                
                # Chain seçimi
                selected_chain = None
                
                for ch in chains:
                    chain_name = ch.get("chain", "")
                    chain_type = ch.get("chainType", "")
                    can_withdraw = str(ch.get("withdrawEnable", "")).lower() == "true"
                    
                    if not can_withdraw:
                        continue
                    
                    # Eğer network belirtilmişse, eşleşeni bul
                    if want_network:
                        # Tam eşleşme
                        if chain_name.upper() == want_network or chain_type.upper() == want_network:
                            selected_chain = ch
                            break
                        # Chain içinde network adı geçiyor mu
                        if want_network in chain_name.upper() or want_network in chain_type.upper():
                            selected_chain = ch
                            break
                    else:
                        # Network belirtilmemişse ilk withdraw edilebilir chain'i al
                        if selected_chain is None:
                            selected_chain = ch
                
                if selected_chain:
                    chain = selected_chain.get("chain", "")
                    try:
                        fee = Decimal(str(selected_chain.get("withdrawFee", "0")))
                    except:
                        fee = Decimal("0")
                    try:
                        min_amount = Decimal(str(selected_chain.get("withdrawMin", "0")))
                    except:
                        min_amount = Decimal("0")
                    
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "BYBIT_CHAIN_SELECTED",
                        "chain": chain,
                        "fee": str(fee),
                        "min": str(min_amount),
                    })
                break
        
        # API'den chain bulunamadıysa, config'den veya varsayılan kullan
        if not chain:
            cfg = self.COINS.get(sym, {"chain": None, "fee": "0.001", "min": "0.01"})
            chain = self._normalize_chain(sym, network or cfg.get("chain"))
            fee = Decimal(cfg["fee"])
            min_amount = Decimal(cfg["min"])
            
            write_log({
                "exchange": self.name,
                "symbol": sym,
                "note": "BYBIT_CHAIN_FALLBACK",
                "chain": chain,
                "fee": str(fee),
                "min": str(min_amount),
            })

        # ══════════════════════════════════════════════════════════
        # 2. Çekim miktarını hesapla
        # ══════════════════════════════════════════════════════════
        final_amount = (amount - fee).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "withdraw_calc",
            "balance": str(amount),
            "fee": str(fee),
            "final_amount": str(final_amount),
            "chain": chain,
            "min_amount": str(min_amount),
        })

        if final_amount < min_amount:
            return (
                {
                    "retCode": -1,
                    "retMsg": f"Insufficient. Balance: {amount}, Fee: {fee}, Final: {final_amount}, Min: {min_amount}",
                },
                400,
            )

        if final_amount <= 0:
            return (
                {
                    "retCode": -1,
                    "retMsg": f"Amount after fee is zero or negative. Balance: {amount}, Fee: {fee}",
                },
                400,
            )

        # ══════════════════════════════════════════════════════════
        # 3. Çekim isteği gönder
        # ══════════════════════════════════════════════════════════
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
            
            # Eğer bakiye zaten FUND'da ise transfer yapmaya gerek yok
            if self._last_balance_account != "FUND":
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
        
        force_chain = None
        if want_raw:
            for item in data1.get("data", []):
                chains_list = item.get("chains", [])
                if isinstance(chains_list, list):
                    for ch in chains_list:
                        chain_name = ch.get("chain", "")
                        if chain_name.upper() == want or chain_name == want_raw:
                            if str(ch.get("canWd")).lower() == "true":
                                force_chain = chain_name
                                fee = ch.get("minFee", "0")
                                write_log(
                                    {
                                        "exchange": self.name,
                                        "symbol": symbol.upper(),
                                        "note": "OKX_FORCE_CHAIN",
                                        "chain": force_chain,
                                        "requested": want_raw,
                                    }
                                )
                                break
                    if force_chain:
                        break

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
                "entries": [{"chain": e.get("chain"), "name": e.get("name"), "canWd": e.get("canWd")} for e in entries],
            }
        )

        mainnet_match = None
        exact_match = None
        chain_suffix_matches = []
        fallback_match = None
        
        for ch in entries:
            can_wd = str(ch.get("canWd")).lower() == "true"
            if not can_wd:
                continue
            chain_name = ch.get("chain", "")
            chain_display_name = ch.get("name", "")
            is_mainnet = ch.get("mainNet", False)
            if not chain_name:
                continue
            
            chain_upper = chain_name.upper()
            
            if want:
                if is_mainnet:
                    if not mainnet_match:
                        mainnet_match = ch
                        write_log(
                            {
                                "exchange": self.name,
                                "symbol": symbol.upper(),
                                "note": "OKX_CHAIN_MAINNET_MATCH",
                                "selected_chain": chain_name,
                                "requested": want_raw,
                            }
                        )
                
                if chain_upper == want:
                    if not mainnet_match:
                        exact_match = ch
                        write_log(
                            {
                                "exchange": self.name,
                                "symbol": symbol.upper(),
                                "note": "OKX_CHAIN_EXACT_MATCH",
                                "selected_chain": chain_name,
                                "requested": want_raw,
                            }
                        )
                
                if "-" in chain_name:
                    chain_suffix = chain_name.split("-")[-1].upper().strip()
                    if chain_suffix == want or want in chain_suffix or chain_suffix in want:
                        chain_suffix_matches.append(ch)
                
                if chain_display_name and want_raw.lower() == chain_display_name.lower():
                    if not mainnet_match and not exact_match:
                        fallback_match = ch
            else:
                if is_mainnet and not mainnet_match:
                    mainnet_match = ch
                elif not fallback_match:
                    fallback_match = ch
        
        if mainnet_match:
            chain = mainnet_match.get("chain")
            fee = mainnet_match.get("minFee", "0")
        elif exact_match:
            chain = exact_match.get("chain")
            fee = exact_match.get("minFee", "0")
        elif chain_suffix_matches:
            selected = None
            for ch in chain_suffix_matches:
                if ch.get("mainNet", False):
                    selected = ch
                    break
            if not selected:
                selected = chain_suffix_matches[0]
            chain = selected.get("chain")
            fee = selected.get("minFee", "0")
            write_log(
                {
                    "exchange": self.name,
                    "symbol": symbol.upper(),
                    "note": "OKX_CHAIN_SUFFIX_MATCH",
                    "selected_chain": chain,
                    "requested": want_raw,
                }
            )
        elif fallback_match:
            chain = fallback_match.get("chain")
            fee = fallback_match.get("minFee", "0")
            write_log(
                {
                    "exchange": self.name,
                    "symbol": symbol.upper(),
                    "note": "OKX_CHAIN_FALLBACK",
                    "selected_chain": chain,
                }
            )

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

        okx_chain = chain
        if "-" not in chain:
            okx_chain = f"{symbol.upper()}-{chain}"
        elif not chain.startswith(symbol.upper() + "-"):
            chain_part = chain.split("-", 1)[-1] if "-" in chain else chain
            okx_chain = f"{symbol.upper()}-{chain_part}"
        
        body = {
            "ccy": symbol.upper(),
            "amt": str(withdraw_amount),
            "dest": "4",
            "toAddr": address if memo in (None, "", "null", "None") else f"{address}:{memo}",
            "chain": okx_chain,
            "fee": fee,
        }
        
        write_log(
            {
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_WITHDRAW_BODY",
                "original_chain": chain,
                "okx_chain": okx_chain,
                "body": body,
            }
        )
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

        async def get_funding_available() -> Decimal:
            path_balance = f"/api/v5/asset/balances?ccy={ccy}"
            ts_balance = self._ts()
            h_balance = self._headers(ts_balance, self._sign(ts_balance, "GET", path_balance))
            async with session.get(f"{self.API}{path_balance}", headers=h_balance) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

            available = Decimal("0")
            if isinstance(data, dict) and data.get("code") in ("0", 0):
                for entry in data.get("data", []):
                    if entry.get("ccy", "").upper() == ccy:
                        try:
                            available = Decimal(str(entry.get("availBal", "0")))
                        except Exception:
                            available = Decimal("0")
                        break
            return available

        funding_available = await get_funding_available()

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

        for attempt in range(self.TRANSFER_SETTLE_ATTEMPTS):
            if attempt > 0:
                await asyncio.sleep(self.TRANSFER_SETTLE_DELAY)
            funding_available = await get_funding_available()
            write_log(
                {
                    "exchange": self.name,
                    "symbol": ccy,
                    "note": "OKX_FUNDING_BALANCE_RECHECK",
                    "attempt": attempt + 1,
                    "funding_available": str(funding_available),
                    "required": str(total_required),
                }
            )
            if funding_available >= total_required:
                return

        raise RuntimeError(
            f"OKX funding transfer did not settle in time (required {total_required}, available {funding_available})"
        )


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
    async with aiohttp.ClientSession(timeout=timeout) as session:
        
        # ══════════════════════════════════════════════════════════
        # 1. ADIM: Bakiyeleri BATCH halinde kontrol et (rate limit koruması)
        # ══════════════════════════════════════════════════════════
        q.put(f"🔍 {len(coins)} coin için bakiye kontrol ediliyor (batch: {BALANCE_BATCH_SIZE})...")
        
        async def check_balance(coin: dict):
            symbol = coin["symbol"].upper()
            try:
                bal = await adapter.get_balance(session, symbol)
                if bal > 0:
                    q.put(f"  💰 {symbol}: {bal}")
                return (coin, bal)
            except Exception as e:
                q.put(f"{symbol}: ⚠️ Bakiye hatası: {e}")
                return (coin, Decimal("0"))
        
        # Batch halinde bakiye kontrolü
        results = []
        total_batches = (len(coins) - 1) // BALANCE_BATCH_SIZE + 1
        
        for i in range(0, len(coins), BALANCE_BATCH_SIZE):
            batch = coins[i:i + BALANCE_BATCH_SIZE]
            batch_num = i // BALANCE_BATCH_SIZE + 1
            
            # Her 5 batch'te bir ilerleme göster
            if batch_num % 5 == 1 or batch_num == total_batches:
                q.put(f"  📊 Batch {batch_num}/{total_batches} kontrol ediliyor...")
            
            batch_results = await asyncio.gather(*[check_balance(c) for c in batch])
            results.extend(batch_results)
            
            # Son batch değilse bekle
            if i + BALANCE_BATCH_SIZE < len(coins):
                await asyncio.sleep(BALANCE_BATCH_DELAY)
        
        # ══════════════════════════════════════════════════════════
        # 2. ADIM: Sadece bakiyesi > 0 olanları filtrele
        # ══════════════════════════════════════════════════════════
        coins_with_balance = [(coin, bal) for coin, bal in results if bal > 0]
        
        q.put(f"✅ Bakiye taraması tamamlandı: {len(coins_with_balance)} coin'de bakiye var")
        
        if not coins_with_balance:
            q.put("⚪ Çekilecek bakiye yok")
            return
        
        # ══════════════════════════════════════════════════════════
        # 3. ADIM: Sadece bakiyesi olanlar için SIRALI çekim yap
        # ══════════════════════════════════════════════════════════
        q.put("─" * 40)
        q.put("🚀 Çekim işlemleri başlıyor...")
        
        async def withdraw_coin(coin: dict, bal: Decimal):
            symbol = coin["symbol"].upper()
            network = coin.get("network", "")
            
            target_key = target_exchange.lower()
            target_info = coin.get(target_key, {})
            
            if not target_info:
                q.put(f"{symbol}: ❌ Config'de {target_exchange} bilgisi bulunamadı")
                return
            
            target_symbol = target_info.get("symbol", symbol).upper()
            target_network = target_info.get("network", network)
            address = target_info.get("address", "").strip()
            memo = target_info.get("memo")
            
            okx_chain = target_info.get("okx_chain")
            if exchange_name == "OKX" and okx_chain:
                target_network = okx_chain
            
            if not address:
                q.put(f"{symbol}: ❌ Config'de {target_exchange} adresi boş")
                return

            amt = floor_amount(bal)
            q.put(f"{symbol}: 🚀 Çekim: {amt}")
            
            if exchange_name == "OKX" and okx_chain:
                q.put(f"{symbol}: 📍 OKX Chain: {okx_chain}")

            try:
                data, status = await adapter.withdraw(session, target_symbol, target_network, address, memo, amt)

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
                        write_log({
                            "exchange": adapter.name,
                            "symbol": symbol,
                            "status": "success",
                            "amount": str(amt),
                            "response": data,
                        })
                    else:
                        q.put(f"{symbol}: ❌ HATA - {ret_msg or json.dumps(data)} (code: {ret_code})")
                        write_log({
                            "exchange": adapter.name,
                            "symbol": symbol,
                            "status": "error",
                            "retCode": ret_code,
                            "retMsg": ret_msg,
                            "response": data,
                        })
                else:
                    ok = status in (200, 201)
                    q.put(f"{symbol}: {'✅' if ok else '❌'} HTTP {status}")
                    write_log({
                        "exchange": adapter.name,
                        "symbol": symbol,
                        "status": "success" if ok else "error",
                        "http_status": status,
                        "response": data,
                    })

            except Exception as e:
                q.put(f"{symbol}: ❌ Exception: {e}")
                write_log({
                    "exchange": adapter.name,
                    "symbol": symbol,
                    "status": "exception",
                    "error": str(e),
                })

        # Çekimleri sıralı yap (rate limit koruması)
        for coin, bal in coins_with_balance:
            await withdraw_coin(coin, bal)
            await asyncio.sleep(WITHDRAW_DELAY)  # Çekimler arası bekleme


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
        self.cmb_source.current(1)
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

        source_ex = self.cmb_source.get()
        target_ex = self.cmb_target.get()
        
        if not source_ex:
            messagebox.showerror("Hata", "Kaynak borsa seçiniz")
            return
            
        if not target_ex:
            messagebox.showerror("Hata", "Alıcı borsa seçiniz")
            return

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
