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

        fund_available = Decimal(str(data.get("result", {}).get("balance", {}).get("walletBalance", "0"))) if status == 200 else Decimal("0")
        
        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "FUND_BALANCE_CHECK",
            "status": status,
            "fund_available": str(fund_available),
            "required": str(required),
            "needs_transfer": fund_available < required,
            "raw_result": data.get("result") if status == 200 else None,
        })

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
                except:
                    pass
            
            # UTA (Unified Trading Account)
            uta_info = withdrawable.get("UTA", {})
            if uta_info:
                try:
                    result["UTA"] = Decimal(str(uta_info.get("withdrawableAmount", "0")))
                except:
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
            except:
                return Decimal("0")
        
        # ══════════════════════════════════════════════════════════
        # 1. UNIFIED + FUND bakiyelerini PARALEL çek (2 API call)
        # ══════════════════════════════════════════════════════════
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
                    except:
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
                except:
                    pass
        
        write_log({
            "exchange": self.name,
            "note": "QUICK_BALANCE_SCAN",
            "count": len(all_balances),
            "coins": list(all_balances.keys()),
        })
        
        if not all_balances:
            return all_balances
        
        # ══════════════════════════════════════════════════════════
        # 2. Withdrawable miktarları PARALEL çek (batch halinde)
        # ══════════════════════════════════════════════════════════
        BATCH_SIZE = 5  # Aynı anda 5 coin sorgula
        coins_list = list(all_balances.keys())
        
        async def check_withdrawable(sym: str):
            try:
                result = await self.get_withdrawable_amount(session, sym)
                return (sym, result)
            except:
                return (sym, {"FUND": Decimal("0"), "UTA": Decimal("0")})
        
        # Batch'ler halinde paralel çek
        for i in range(0, len(coins_list), BATCH_SIZE):
            batch = coins_list[i:i + BATCH_SIZE]
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
        
        write_log({
            "exchange": self.name,
            "note": "FINAL_WITHDRAWABLE_BALANCES",
            "count": len(all_balances),
            "coins": {k: f"{v['balance']} ({v['account']})" for k, v in all_balances.items()},
        })
        
        return all_balances

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

        # 2. FUND hesabını kontrol et - Birden fazla yöntem dene
        
        # Yöntem 2a: query-account-coins-balance (FUND)
        funding_data, funding_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "FUND", "coin": sym},
        )
        
        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "FUND_API_RAW",
            "status": funding_status,
            "retCode": funding_data.get("retCode") if isinstance(funding_data, dict) else None,
            "result": funding_data.get("result") if isinstance(funding_data, dict) else None,
        })
        
        if funding_status == 200 and funding_data.get("retCode") == 0:
            result = funding_data.get("result", {})
            coins = result.get("balance", [])
            
            # Eğer balance boş ama result'ta coin bilgisi varsa
            if not coins and "coin" in result:
                coins = [result]
            
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
                    
                    # walletBalance varsa ama transferBalance yoksa, walletBalance kullan
                    if fund_available > 0:
                        self._last_balance_account = "FUND"
                        return fund_available
                    elif wallet_balance > 0:
                        self._last_balance_account = "FUND"
                        return wallet_balance
                    break
        
        # Yöntem 2b: Tüm FUND bakiyelerini çek (coin parametresi olmadan)
        all_fund_data, all_fund_status = await self._get(
            session,
            "/v5/asset/transfer/query-account-coins-balance",
            {"accountType": "FUND"},
        )
        
        if all_fund_status == 200 and all_fund_data.get("retCode") == 0:
            coins = all_fund_data.get("result", {}).get("balance", [])
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
                        "note": "FUND_ALL_COINS_CHECK",
                        "transferBalance": str(fund_available),
                        "walletBalance": str(wallet_balance),
                    })
                    
                    if fund_available > 0:
                        self._last_balance_account = "FUND"
                        return fund_available
                    elif wallet_balance > 0:
                        self._last_balance_account = "FUND"
                        return wallet_balance
                    break
        
        # Yöntem 2c: query-asset-info endpoint
        asset_info_data, asset_info_status = await self._get(
            session,
            "/v5/asset/transfer/query-asset-info",
            {"accountType": "FUND", "coin": sym},
        )
        
        if asset_info_status == 200 and asset_info_data.get("retCode") == 0:
            result = asset_info_data.get("result", {})
            # Farklı yapıları kontrol et
            spot_info = result.get("spot", {})
            assets = spot_info.get("assets", [])
            
            # Eğer spot yapısı yoksa, result'ın kendisini kontrol et
            if not assets:
                assets = result.get("assets", [])
            if not assets and isinstance(result.get("list"), list):
                assets = result.get("list", [])
            
            for asset in assets:
                asset_coin = asset.get("coin", asset.get("tokenId", "")).upper()
                if asset_coin == sym:
                    try:
                        free = Decimal(str(asset.get("free", asset.get("availableAmount", "0"))))
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
        
        # 3. Diğer hesap türlerini kontrol et (SPOT, CONTRACT)
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
                            wallet = Decimal(str(coin.get("walletBalance", "0")))
                        except Exception:
                            available = Decimal("0")
                            wallet = Decimal("0")
                        
                        write_log({
                            "exchange": self.name,
                            "symbol": sym,
                            "note": f"{account_type}_BALANCE",
                            "transferBalance": str(available),
                            "walletBalance": str(wallet),
                        })
                        
                        if available > 0:
                            self._last_balance_account = account_type
                            return available
                        elif wallet > 0:
                            self._last_balance_account = account_type
                            return wallet
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
        chain = None
        fee = Decimal("0")
        min_amount = Decimal("0")
        
        want_network = (network or "").strip().upper()
        
        # Önce /v5/asset/coin/query-info endpoint'ini dene
        coin_info_data, coin_info_status = await self._get(
            session,
            "/v5/asset/coin/query-info",
            {"coin": sym},
        )
        
        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "BYBIT_COIN_INFO_RAW",
            "status": coin_info_status,
            "retCode": coin_info_data.get("retCode") if isinstance(coin_info_data, dict) else None,
            "result_keys": list(coin_info_data.get("result", {}).keys()) if isinstance(coin_info_data, dict) else None,
        })
        
        if coin_info_status == 200 and coin_info_data.get("retCode") == 0:
            result = coin_info_data.get("result", {})
            rows = result.get("rows", [])
            
            # Eğer rows boşsa, result direkt coin bilgisi içeriyor olabilir
            if not rows and isinstance(result, dict):
                # Alternatif yapı kontrolü
                if "chains" in result:
                    rows = [{"coin": sym, "chains": result.get("chains", [])}]
                elif "coin" in result:
                    rows = [result]
            
            for row in rows:
                row_coin = row.get("coin", row.get("name", "")).upper()
                if row_coin != sym:
                    continue
                    
                chains = row.get("chains", [])
                
                write_log({
                    "exchange": self.name,
                    "symbol": sym,
                    "note": "BYBIT_CHAINS_AVAILABLE",
                    "chains": [{"chain": c.get("chain"), "chainType": c.get("chainType"), "withdrawFee": c.get("withdrawFee"), "withdrawMin": c.get("withdrawMin")} for c in chains],
                    "requested_network": want_network,
                })
                
                # Chain seçimi
                selected_chain = None
                
                # Adres 0x ile başlıyorsa EVM chain'lerini tercih et
                is_evm_address = address.startswith("0x") if address else False
                
                # EVM chain varyantları (native → EVM mapping)
                EVM_VARIANTS = {
                    "SEI": "SEIEVM",
                    "KAVA": "KAVAEVM", 
                    "CELO": "CELOEVM",
                    "CANTO": "CANTOEVM",
                    "KLAYTN": "KLAYTNEVM",
                }
                
                # Eğer EVM adresi ve native chain isteniyorsa, EVM varyantını tercih et
                if is_evm_address and want_network in EVM_VARIANTS:
                    evm_chain = EVM_VARIANTS[want_network]
                    # Bybit'te EVM chain var mı kontrol et
                    for ch in chains:
                        if ch.get("chain", "").upper() == evm_chain:
                            want_network = evm_chain
                            break
                
                # want_network için olası eşleşmeler (class-level CHAIN_ALIASES kullan)
                possible_matches = self.CHAIN_ALIASES.get(want_network, [want_network])
                
                write_log({
                    "exchange": self.name,
                    "symbol": sym,
                    "note": "CHAIN_MATCHING_DEBUG",
                    "want_network": want_network,
                    "is_evm_address": is_evm_address,
                    "possible_matches": possible_matches,
                    "available_chains": [c.get("chain") for c in chains],
                })
                
                # Withdraw edilebilir chain'leri filtrele
                valid_chains = []
                for ch in chains:
                    withdraw_enable = ch.get("withdrawEnable")
                    if withdraw_enable is None:
                        can_withdraw = True
                    else:
                        can_withdraw = withdraw_enable is True or str(withdraw_enable).lower() in ("true", "1")
                    if can_withdraw:
                        valid_chains.append(ch)
                
                if want_network:
                    # 1. ÖNCE: Tam eşleşme ara (en yüksek öncelik)
                    for ch in valid_chains:
                        chain_name_upper = ch.get("chain", "").upper()
                        chain_type_upper = ch.get("chainType", "").upper()
                        
                        # want_network ile tam eşleşme
                        if chain_name_upper == want_network or chain_type_upper == want_network:
                            selected_chain = ch
                            break
                        
                        # Alias listesinde tam eşleşme
                        for alias in possible_matches:
                            alias_upper = alias.upper()
                            if chain_name_upper == alias_upper or chain_type_upper == alias_upper:
                                selected_chain = ch
                                break
                        if selected_chain:
                            break
                    
                    # 2. SONRA: Tam eşleşme bulunamadıysa kısmi eşleşme dene
                    if not selected_chain:
                        for ch in valid_chains:
                            chain_name_upper = ch.get("chain", "").upper()
                            chain_type_upper = ch.get("chainType", "").upper()
                            
                            for alias in possible_matches:
                                alias_upper = alias.upper()
                                if alias_upper in chain_name_upper or alias_upper in chain_type_upper:
                                    selected_chain = ch
                                    break
                            if selected_chain:
                                break
                            
                            # Chain formatı: COIN-NETWORK
                            if "-" in ch.get("chain", ""):
                                chain_suffix = ch.get("chain", "").split("-")[-1].upper()
                                if chain_suffix == want_network or want_network in chain_suffix:
                                    selected_chain = ch
                                    break
                else:
                    # Network belirtilmemişse ilk withdraw edilebilir chain'i al
                    if valid_chains:
                        selected_chain = valid_chains[0]
                
                if selected_chain:
                    # Bybit API'den dönen chain ve chainType'ı al
                    raw_chain = selected_chain.get("chain", "")
                    chain_type = selected_chain.get("chainType", "")
                    
                    # Manuel çekimde "Ethereum (ERC20)" formatı kullanılıyor
                    # API için chainType'ı kullan (Ethereum, Chiliz Chain, vs.)
                    if chain_type:
                        chain = chain_type
                    else:
                        chain = raw_chain
                    
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "CHAIN_SELECTED",
                        "raw_chain": raw_chain,
                        "chainType": chain_type,
                        "final_chain": chain,
                    })
                    
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
        
        # API'den chain bulunamadıysa, config'deki network'ü kullan
        if not chain:
            # Config'den gelen network varsa onu kullan
            if network:
                chain = self._normalize_chain(sym, network)
                # Fee ve min için varsayılan değerler (API'den alınamadı)
                cfg = self.COINS.get(sym, {"fee": "0.001", "min": "0.01"})
                fee = Decimal(cfg.get("fee", "0.001"))
                min_amount = Decimal(cfg.get("min", "0.01"))
            else:
                # COINS sözlüğünden al
                cfg = self.COINS.get(sym, {"chain": sym, "fee": "0.001", "min": "0.01"})
                chain = self._normalize_chain(sym, cfg.get("chain"))
                fee = Decimal(cfg["fee"])
                min_amount = Decimal(cfg["min"])
            
            write_log({
                "exchange": self.name,
                "symbol": sym,
                "note": "BYBIT_CHAIN_FALLBACK",
                "chain": chain,
                "fee": str(fee),
                "min": str(min_amount),
                "reason": "API returned no valid chain info",
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
            
            # Her coin için FUND bakiyesini kontrol et ve gerekirse transfer yap
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

    # Chain alias'ları - config'deki isim -> Binance'teki isim
    CHAIN_ALIASES = {
        "ETH": "ETH",
        "ERC20": "ETH",
        "BSC": "BSC",
        "BEP20": "BSC",
        "BNB": "BSC",
        "TRC20": "TRX",
        "TRX": "TRX",
        "TRON": "TRX",
        "SOL": "SOL",
        "SOLANA": "SOL",
        "AVAXC": "AVAXC",
        "AVAX": "AVAXC",
        "C-CHAIN": "AVAXC",
        "MATIC": "MATIC",
        "POLYGON": "MATIC",
        "POL": "MATIC",
        "ARB": "ARBITRUM",
        "ARBITRUM": "ARBITRUM",
        "ARBONE": "ARBITRUM",
        "OP": "OPTIMISM",
        "OPTIMISM": "OPTIMISM",
        "BASE": "BASE",
        "CHZ2": "CHZ",
        "CHILIZ": "CHZ",
        "ZKSYNCERA": "ZKSYNC",
        "ZKSYNC": "ZKSYNC",
        "HEDERA": "HBAR",
        "HBAR": "HBAR",
        "NEO": "NEO3",
        "NEO3": "NEO3",
            "DOT": "STATEMINT",      # Polkadot native = STATEMINT on Binance
            "POLKADOT": "STATEMINT",
            "STATEMINT": "STATEMINT",
        "COSMOS": "ATOM",
        "CELESTIA": "TIA",
        "LINEA": "LINEA",
        "SCROLL": "SCROLL",
        "ZETA": "ZETA",
        "MANTLE": "MANTLE",
        "CELO": "CELO",
        "FLOW": "FLOW",
    }

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
        connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
            data, st = await self._req(s, "GET", "/api/v3/account")
            if st != 200:
                raise RuntimeError(f"Binance error: {data}")

    async def get_all_balances(self, session) -> dict:
        """Tüm bakiyeleri tek seferde çek - HIZLI VERSİYON"""
        all_balances = {}
        
        # Spot hesap bakiyeleri
        data, st = await self._req(session, "GET", "/api/v3/account")
        if st != 200:
            write_log({
                "exchange": self.name,
                "note": "BINANCE_BALANCE_ERROR",
                "status": st,
                "data": data,
            })
            return all_balances
        
        for b in data.get("balances", []):
            sym = b.get("asset", "").upper()
            if not sym:
                continue
            try:
                free = Decimal(b.get("free", "0"))
                if free > 0:
                    all_balances[sym] = {"balance": free, "account": "SPOT"}
            except:
                pass
        
        write_log({
            "exchange": self.name,
            "note": "BINANCE_ALL_BALANCES",
            "count": len(all_balances),
            "coins": list(all_balances.keys()),
        })
        
        return all_balances

    async def get_coin_info(self, session, symbol: str) -> dict:
        """Coin için çekim bilgilerini al (fee, min, network status)"""
        data, st = await self._req(session, "GET", "/sapi/v1/capital/config/getall")
        if st != 200:
            return {}
        
        for coin in data:
            if coin.get("coin", "").upper() == symbol.upper():
                return coin
        return {}

    async def get_balance(self, session, symbol: str) -> Decimal:
        data, st = await self._req(session, "GET", "/api/v3/account")
        if st != 200:
            raise RuntimeError(data)
        for b in data.get("balances", []):
            if b.get("asset", "").upper() == symbol.upper():
                return Decimal(b.get("free", "0"))
        return Decimal("0")

    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        sym = symbol.upper()
        
        # Önce coin bilgisini al (fee, min, network durumu)
        coin_info = await self.get_coin_info(session, sym)
        
        # Network alias'ını çözümle
        want_network = (network or "").upper().strip()
        actual_network = self.CHAIN_ALIASES.get(want_network, want_network)
        
        # Coin info'dan doğru network'ü bul
        selected_network = None
        withdraw_fee = Decimal("0")
        withdraw_min = Decimal("0")
        withdraw_enabled = False
        
        if coin_info and coin_info.get("networkList"):
            networks = coin_info.get("networkList", [])
            
            write_log({
                "exchange": self.name,
                "symbol": sym,
                "note": "BINANCE_NETWORKS_AVAILABLE",
                "networks": [{"network": n.get("network"), "withdrawEnable": n.get("withdrawEnable")} for n in networks],
                "requested": want_network,
                "actual_network": actual_network,
            })
            
            # SADECE config'deki ağı kullan - başka fallback YOK
            for net in networks:
                net_name = net.get("network", "").upper()
                if net_name == actual_network or net_name == want_network:
                    selected_network = net.get("network")
                    withdraw_fee = Decimal(str(net.get("withdrawFee", "0")))
                    withdraw_min = Decimal(str(net.get("withdrawMin", "0")))
                    withdraw_enabled = net.get("withdrawEnable", False)
                    write_log({
                        "exchange": self.name,
                        "symbol": sym,
                        "note": "BINANCE_NETWORK_MATCHED",
                        "selected": selected_network,
                        "enabled": withdraw_enabled,
                    })
                    break
            
            # Eşleşme bulunamadıysa hata ver
            if not selected_network:
                return {"error": f"Network {want_network} not found for {sym} on Binance"}, 400
            
            # Çekim kapalıysa hata ver
            if not withdraw_enabled:
                return {"error": f"Withdrawal disabled for {sym} on {selected_network}"}, 400
        else:
            # coin_info yoksa config'deki ağı direkt kullan
            selected_network = actual_network or want_network
        
        # Tam sayı gerektiren coinler
        INTEGER_COINS = {"JUV", "PSG", "BAR", "ACM", "CITY", "ASR", "ATM", "OG", "SANTOS", "LAZIO", "PORTO", "NAV", "NEO"}
        
        # Özel ondalık hassasiyeti gerektiren coinler
        DECIMAL_PRECISION = {
            "ADA": "0.000001",    # 6 decimal
            "XRP": "0.000001",    # 6 decimal
            "DOT": "0.0001",      # 4 decimal
            "ATOM": "0.000001",   # 6 decimal
            "ALGO": "0.000001",   # 6 decimal
            "XLM": "0.0000001",   # 7 decimal
            "HBAR": "0.00000001", # 8 decimal
            "TRX": "0.000001",    # 6 decimal
            "MASK": "0.01",       # 2 decimal
            "GALA": "0.01",       # 2 decimal
            "ENJ": "0.01",        # 2 decimal
            "MANA": "0.01",       # 2 decimal
            "SAND": "0.01",       # 2 decimal
        }
        
        final_amount = amount
        if sym in INTEGER_COINS:
            final_amount = Decimal(int(amount))
            if final_amount <= 0:
                return {"error": f"{sym} requires integer amount, got {amount}"}, 400
        elif sym in DECIMAL_PRECISION:
            step = Decimal(DECIMAL_PRECISION[sym])
            final_amount = amount.quantize(step, rounding=ROUND_DOWN)
        
        # Fee ve min kontrolü
        if withdraw_fee > 0:
            net_amount = final_amount - withdraw_fee
            if net_amount <= 0:
                return {"error": f"Insufficient after fee. Balance: {final_amount}, Fee: {withdraw_fee}"}, 400
            if net_amount < withdraw_min:
                return {"error": f"Below minimum. Amount: {net_amount}, Min: {withdraw_min}"}, 400
        
        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "BINANCE_WITHDRAW_PREP",
            "requested_network": want_network,
            "selected_network": selected_network,
            "withdraw_enabled": withdraw_enabled,
            "fee": str(withdraw_fee),
            "min": str(withdraw_min),
            "original_amount": str(amount),
            "final_amount": str(final_amount),
            "address": address,
        })
        
        params = {"coin": sym, "address": address, "amount": str(final_amount)}
        if selected_network:
            params["network"] = selected_network
        if memo not in (None, "", "null", "None"):
            params["addressTag"] = str(memo)
        
        data, st = await self._req(session, "POST", "/sapi/v1/capital/withdraw/apply", params)
        
        write_log({
            "exchange": self.name,
            "symbol": sym,
            "note": "BINANCE_WITHDRAW_RESPONSE",
            "status": st,
            "response": data,
        })
        
        return data, st


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

    async def get_all_balances(self, session) -> dict:
        """Tüm hesaplardan tüm bakiyeleri tek seferde çek - HIZLI VERSİYON"""
        all_balances = {}
        
        # 1. Trading Account - tüm bakiyeler
        ts1 = self._ts()
        path1 = "/api/v5/account/balance"
        headers1 = self._headers(ts1, self._sign(ts1, "GET", path1))
        
        # 2. Funding Account - tüm bakiyeler
        ts2 = self._ts()
        path2 = "/api/v5/asset/balances"
        headers2 = self._headers(ts2, self._sign(ts2, "GET", path2))
        
        # Paralel çek
        async def fetch_trading():
            async with session.get(f"{self.API}{path1}", headers=headers1) as r:
                return await r.json(content_type=None)
        
        async def fetch_funding():
            async with session.get(f"{self.API}{path2}", headers=headers2) as r:
                return await r.json(content_type=None)
        
        trading_data, funding_data = await asyncio.gather(fetch_trading(), fetch_funding())
        
        # Trading bakiyeleri parse et
        for d in trading_data.get("data", []):
            for c in d.get("details", []):
                sym = c.get("ccy", "").upper()
                if not sym:
                    continue
                try:
                    bal = Decimal(c.get("availBal", "0"))
                    if bal > 0:
                        all_balances[sym] = {"balance": bal, "account": "TRADING"}
                except:
                    pass
        
        # Funding bakiyeleri parse et
        if funding_data.get("code") in ("0", 0):
            for entry in funding_data.get("data", []):
                sym = entry.get("ccy", "").upper()
                if not sym:
                    continue
                try:
                    bal = Decimal(entry.get("availBal", "0"))
                    if bal > 0:
                        if sym not in all_balances:
                            all_balances[sym] = {"balance": bal, "account": "FUNDING"}
                        else:
                            # Her iki hesaptaki toplamı al
                            all_balances[sym]["balance"] += bal
                            all_balances[sym]["account"] = "BOTH"
                except:
                    pass
        
        write_log({
            "exchange": self.name,
            "note": "OKX_ALL_BALANCES",
            "count": len(all_balances),
            "coins": {k: f"{v['balance']} ({v['account']})" for k, v in all_balances.items()},
        })
        
        return all_balances

    async def get_balance(self, session, symbol: str) -> Decimal:
        """Trading + Funding hesaplarından bakiye al"""
        sym = symbol.upper()
        trading_bal = Decimal("0")
        funding_bal = Decimal("0")
        
        # 1. Trading Account bakiyesi
        ts = self._ts()
        path = "/api/v5/account/balance"
        headers = self._headers(ts, self._sign(ts, "GET", path))
        async with session.get(f"{self.API}{path}", headers=headers) as r:
            data = await r.json(content_type=None)
            for d in data.get("data", []):
                for c in d.get("details", []):
                    if c.get("ccy", "").upper() == sym:
                        try:
                            trading_bal = Decimal(c.get("availBal", "0"))
                        except Exception:
                            pass
        
        # 2. Funding Account bakiyesi - TÜM bakiyeleri çek
        ts2 = self._ts()
        path2 = "/api/v5/asset/balances"  # Tüm coinleri çek
        headers2 = self._headers(ts2, self._sign(ts2, "GET", path2))
        async with session.get(f"{self.API}{path2}", headers=headers2) as r2:
            data2 = await r2.json(content_type=None)
            write_log({
                "exchange": self.name,
                "symbol": sym,
                "note": "OKX_FUNDING_RAW_RESPONSE",
                "code": data2.get("code"),
                "data_count": len(data2.get("data", [])),
            })
            if data2.get("code") in ("0", 0):
                for entry in data2.get("data", []):
                    if entry.get("ccy", "").upper() == sym:
                        try:
                            funding_bal = Decimal(entry.get("availBal", "0"))
                            write_log({
                                "exchange": self.name,
                                "symbol": sym,
                                "note": "OKX_FUNDING_COIN_FOUND",
                                "availBal": entry.get("availBal"),
                                "bal": entry.get("bal"),
                                "frozenBal": entry.get("frozenBal"),
                            })
                        except Exception:
                            pass
        
        total_bal = trading_bal + funding_bal
        
        if total_bal > 0:
            write_log({
                "exchange": self.name,
                "symbol": sym,
                "note": "OKX_BALANCE_FOUND",
                "trading": str(trading_bal),
                "funding": str(funding_bal),
                "total": str(total_bal),
            })
        
        return total_bal

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
        
        # OKX chain alias'ları (ETH = ERC20, SOL = Solana, vb.)
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
            "AVAXC": ["C-CHAIN", "AVALANCHE C", "AVALANCHEC", "AVAXC"],  # C-Chain for EVM
            "AVAX": ["C-CHAIN", "AVALANCHE C"],  # Default to C-Chain for 0x addresses
            "BASE": ["BASE"],
            "CHZ2": ["CHILIZ", "CHZ2", "CHZ"],
            "ZKSYNCERA": ["ZKSYNC ERA", "ZKSYNC", "ZKV2", "ZKERA"],
            "HEDERA": ["HBAR", "HEDERA"],
            "ETC": ["ERC20", "ETHEREUM CLASSIC", "ETC"],  # EVM address = use ERC20
            "NEO": ["N3", "NEO", "NEO3"],  # NEO N3 network
            "NEO3": ["N3", "NEO", "NEO3"],
        }
        
        # EVM adresi ise uygun chain'i tercih et
        is_evm_address = address.startswith("0x")
        if is_evm_address:
            sym_upper = symbol.upper()
            if sym_upper == "AVAX":
                want = "AVAXC"
                want_aliases = OKX_CHAIN_ALIASES.get("AVAXC", ["C-CHAIN"])
            elif sym_upper == "ETC":
                # ETC için ERC20 varsa onu kullan (EVM whitelist uyumluluğu)
                want = "ERC20"
                want_aliases = ["ERC20", "ETHEREUM"]
        
        # want için olası eşleşmeler
        want_aliases = OKX_CHAIN_ALIASES.get(want, [want])
        
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
                    chain_suffix = chain_name.split("-", 1)[-1].upper().strip()
                    chain_full_upper = chain_name.upper()
                    # Alias listesiyle eşleştir
                    for alias in want_aliases:
                        alias_upper = alias.upper()
                        # C-CHAIN özel kontrolü
                        if alias_upper in ["C-CHAIN", "C CHAIN", "AVALANCHE C", "AVALANCHEC"]:
                            if "C-CHAIN" in chain_full_upper or "C CHAIN" in chain_full_upper:
                                chain_suffix_matches.append(ch)
                                break
                        elif alias_upper in chain_suffix or chain_suffix in alias_upper or alias_upper in chain_full_upper:
                            chain_suffix_matches.append(ch)
                            break
                
                if chain_display_name and want_raw.lower() == chain_display_name.lower():
                    if not mainnet_match and not exact_match:
                        fallback_match = ch
            else:
                if is_mainnet and not mainnet_match:
                    mainnet_match = ch
                elif not fallback_match:
                    fallback_match = ch
        
        # Öncelik sırası: exact_match > suffix_match > mainnet > fallback
        # (İstenen chain her zaman mainnet'ten öncelikli!)
        if exact_match:
            chain = exact_match.get("chain")
            fee = exact_match.get("minFee", "0")
        elif chain_suffix_matches:
            selected = None
            # Önce EVM adresi için C-Chain ara
            for ch in chain_suffix_matches:
                ch_name = ch.get("chain", "").upper()
                if "C-CHAIN" in ch_name or "C CHAIN" in ch_name:
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
        elif mainnet_match:
            chain = mainnet_match.get("chain")
            fee = mainnet_match.get("minFee", "0")
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

        # Funding'e transfer et (gerekirse)
        try:
            await self._ensure_funding_liquidity(session, symbol, available_amount)
        except RuntimeError as e:
            write_log({
                "exchange": self.name,
                "symbol": symbol.upper(),
                "note": "OKX_TRANSFER_WARNING",
                "error": str(e),
            })
            # Transfer başarısız olsa bile Funding'deki ile devam et

        # Funding'deki GERÇEK bakiyeyi al ve ona göre çek
        ts_check = self._ts()
        path_check = f"/api/v5/asset/balances?ccy={symbol.upper()}"
        h_check = self._headers(ts_check, self._sign(ts_check, "GET", path_check))
        async with session.get(f"{self.API}{path_check}", headers=h_check) as resp:
            data_check = await resp.json(content_type=None)
        
        actual_funding = Decimal("0")
        if data_check.get("code") in ("0", 0):
            for entry in data_check.get("data", []):
                if entry.get("ccy", "").upper() == symbol.upper():
                    try:
                        actual_funding = Decimal(str(entry.get("availBal", "0")))
                    except:
                        pass
                    break
        
        # Gerçek çekim miktarını hesapla
        actual_withdraw = (actual_funding - fee_decimal).quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)
        
        write_log({
            "exchange": self.name,
            "symbol": symbol.upper(),
            "note": "OKX_ACTUAL_FUNDING",
            "actual_funding": str(actual_funding),
            "actual_withdraw": str(actual_withdraw),
            "original_withdraw": str(withdraw_amount),
        })
        
        if actual_withdraw <= 0:
            return {"error": "funding_balance_not_enough_after_fee", "funding": str(actual_funding), "fee": str(fee_decimal)}, 400
        
        # Gerçek miktarı kullan
        withdraw_amount = actual_withdraw

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

        async def get_trading_available() -> Decimal:
            """Trading hesabındaki gerçek available bakiyeyi al"""
            path = "/api/v5/account/balance"
            ts = self._ts()
            headers = self._headers(ts, self._sign(ts, "GET", path))
            async with session.get(f"{self.API}{path}", headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    return Decimal("0")
            
            for d in data.get("data", []):
                for c in d.get("details", []):
                    if c.get("ccy", "").upper() == ccy:
                        try:
                            return Decimal(str(c.get("availBal", "0")))
                        except Exception:
                            return Decimal("0")
            return Decimal("0")

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

        # Küçük farklar için tolerans
        tolerance = max(total_required * Decimal("0.00001"), Decimal("0.0001"))
        
        if funding_available >= (total_required - tolerance):
            return

        # Transfer gerekiyor - önce Trading'de ne var kontrol et
        trading_available = await get_trading_available()
        
        write_log(
            {
                "exchange": self.name,
                "symbol": ccy,
                "note": "OKX_TRADING_AVAILABLE",
                "trading_available": str(trading_available),
                "funding_available": str(funding_available),
                "required": str(total_required),
            }
        )
        
        # Gereken miktar = required - funding'deki
        needed_from_trading = (total_required - funding_available)
        
        # Trading'de yeterli yoksa, mevcut olanı transfer et
        transfer_amount = min(needed_from_trading, trading_available)
        
        if transfer_amount <= Decimal("0.00001"):
            # Transfer gerekmiyor veya Trading'de bakiye yok
            # Funding'deki ile devam et
            write_log({
                "exchange": self.name,
                "symbol": ccy,
                "note": "OKX_NO_TRANSFER_NEEDED",
                "reason": "trading_empty_or_funding_enough",
            })
            return

        transfer_amount = transfer_amount.quantize(self.MIN_DECIMAL_STEP, rounding=ROUND_DOWN)

        # Farklı kaynak hesapları dene (Unified Trading, Spot)
        source_accounts = [
            (self.ACCOUNT_TRADING, "Unified Trading"),
            (self.ACCOUNT_SPOT, "Spot"),
        ]
        
        transfer_success = False
        last_error = None
        
        for from_account, account_name in source_accounts:
            transfer_body = {
                "type": "0",
                "ccy": ccy,
                "amt": str(transfer_amount),
                "from": from_account,
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
                    "from": from_account,
                    "from_name": account_name,
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
                        "from_account": account_name,
                        "response": transfer_data,
                    }
                )

                success_codes = {"0", 0, "00000"}
                if resp.status == 200 and transfer_data.get("code") in success_codes:
                    transfer_success = True
                    break
                else:
                    last_error = f"HTTP {resp.status}, code={transfer_data.get('code')}, msg={transfer_data.get('msg')}"
        
        if not transfer_success:
            raise RuntimeError(f"OKX transfer failed from all accounts: {last_error}")

        # Küçük farklar için tolerans (%0.001 veya 0.0001 coin)
        tolerance = max(total_required * Decimal("0.00001"), Decimal("0.0001"))
        
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
                    "tolerance": str(tolerance),
                }
            )
            # Tolerans ile karşılaştır
            if funding_available >= (total_required - tolerance):
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
    connector = aiohttp.TCPConnector(family=socket.AF_INET)  # Force IPv4
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        
        # ══════════════════════════════════════════════════════════
        # 1. ADIM: Tüm bakiyeleri TEK SEFERDE çek (rate limit koruması)
        # ══════════════════════════════════════════════════════════
        q.put(f"🔍 Tüm bakiyeler kontrol ediliyor...")
        
        # Bybit için özel optimizasyon: tüm bakiyeleri tek seferde çek
        if hasattr(adapter, 'get_all_balances'):
            try:
                all_balances = await adapter.get_all_balances(session)
                q.put(f"📊 Toplam {len(all_balances)} coin'de bakiye bulundu")
                
                # Config'deki coinlerle eşleştir
                results = []
                for coin in coins:
                    symbol = coin["symbol"].upper()
                    if symbol in all_balances:
                        bal = all_balances[symbol]["balance"]
                        account = all_balances[symbol]["account"]
                        q.put(f"  💰 {symbol}: {bal} ({account})")
                        # Adapter'a hangi hesaptan geldiğini bildir
                        adapter._last_balance_account = account
                        results.append((coin, bal))
                    else:
                        results.append((coin, Decimal("0")))
            except Exception as e:
                q.put(f"⚠️ Toplu bakiye hatası: {e}, tek tek deneniyor...")
                # Fallback: eski yöntem
                results = []
                for coin in coins:
                    symbol = coin["symbol"].upper()
                    try:
                        bal = await adapter.get_balance(session, symbol)
                        if bal > 0:
                            q.put(f"  💰 {symbol}: {bal}")
                        results.append((coin, bal))
                    except Exception as e2:
                        results.append((coin, Decimal("0")))
                    await asyncio.sleep(0.1)
        else:
            # Diğer borsalar için eski yöntem (batch)
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
            
            results = []
            total_batches = (len(coins) - 1) // BALANCE_BATCH_SIZE + 1
            
            for i in range(0, len(coins), BALANCE_BATCH_SIZE):
                batch = coins[i:i + BALANCE_BATCH_SIZE]
                batch_num = i // BALANCE_BATCH_SIZE + 1
                
                if batch_num % 5 == 1 or batch_num == total_batches:
                    q.put(f"  📊 Batch {batch_num}/{total_batches} kontrol ediliyor...")
                
                batch_results = await asyncio.gather(*[check_balance(c) for c in batch])
                results.extend(batch_results)
                
                if i + BALANCE_BATCH_SIZE < len(coins):
                    await asyncio.sleep(BALANCE_BATCH_DELAY)
        
        # ══════════════════════════════════════════════════════════
        # 2. ADIM: Sadece bakiyesi > 0 olanları filtrele
        # ══════════════════════════════════════════════════════════
        coins_with_balance_raw = [(coin, bal) for coin, bal in results if bal > 0]
        
        q.put(f"📊 {len(coins_with_balance_raw)} coin'de bakiye bulundu")
        
        # ══════════════════════════════════════════════════════════
        # TOZ FİLTRESİ - Çekilemeyecek küçük bakiyeleri atla
        # ══════════════════════════════════════════════════════════
        # Dinamik eşikler: coin türüne göre minimum değerler
        # Eşik = yaklaşık $5 değerinde coin miktarı
        DUST_THRESHOLDS = {
            # Çok yüksek değerli ($1000+)
            "BTC": Decimal("0.00005"),
            "ETH": Decimal("0.001"),
            "WBTC": Decimal("0.00005"),
            "XAUT": Decimal("0.002"),  # Gold token
            "PAXG": Decimal("0.002"),  # Gold token ~$2500/coin
            # Yüksek değerli ($100-1000)
            "AAVE": Decimal("0.02"),
            "QNT": Decimal("0.05"),   # ~$80-100 per coin
            "DASH": Decimal("0.15"),  # ~$25-30 per coin
            "ETC": Decimal("0.2"),   # ~$18-25 per coin
            "MKR": Decimal("0.002"),
            "COMP": Decimal("0.02"),
            "YFI": Decimal("0.0005"),
            "BNB": Decimal("0.008"),
            "SOL": Decimal("0.025"),
            "BCH": Decimal("0.01"),
            "LTC": Decimal("0.05"),
            # Orta-yüksek değerli ($10-100)
            "AVAX": Decimal("0.1"),
            "DOT": Decimal("0.5"),
            "LINK": Decimal("0.3"),
            "UNI": Decimal("0.5"),
            "ATOM": Decimal("0.5"),
            "APT": Decimal("0.5"),
            "SUI": Decimal("1"),
            "INJ": Decimal("0.2"),
            "TIA": Decimal("0.5"),
            "SEI": Decimal("10"),
            "OP": Decimal("2"),
            "ARB": Decimal("5"),
            "NEAR": Decimal("1"),
            "FTM": Decimal("5"),
            "MATIC": Decimal("10"),
            "POL": Decimal("10"),
            "RENDER": Decimal("0.5"),
            "FET": Decimal("2"),
            "GRT": Decimal("5"),
            "IMX": Decimal("3"),
            "STX": Decimal("2"),
            "APE": Decimal("3"),
            "SAND": Decimal("10"),
            "MANA": Decimal("10"),
            "AXS": Decimal("0.5"),
            "ENS": Decimal("0.2"),
            "LDO": Decimal("2"),
            "CRV": Decimal("5"),
            "SNX": Decimal("2"),
            "AEVO": Decimal("2"),
            "ZRX": Decimal("10"),
            "NMR": Decimal("0.2"),
            "STORJ": Decimal("10"),
            "BAND": Decimal("3"),
            "BAL": Decimal("2"),
            "1INCH": Decimal("15"),
            "SUSHI": Decimal("5"),
            "DYDX": Decimal("3"),
            "ENJ": Decimal("20"),
            "CHZ": Decimal("50"),
            "GALA": Decimal("50"),
            "MASK": Decimal("1"),
            "SKL": Decimal("100"),
            "OMG": Decimal("5"),
            "ZIL": Decimal("200"),
            "ANKR": Decimal("200"),
            "FIL": Decimal("1"),
            "ICP": Decimal("0.5"),
            "HBAR": Decimal("30"),
            "VET": Decimal("150"),
            "XLM": Decimal("30"),
            "XRP": Decimal("5"),
            "ADA": Decimal("10"),
            "DOGE": Decimal("15"),
            "TRX": Decimal("20"),
            "EOS": Decimal("5"),
            "NEO": Decimal("1.0"),  # OKX min withdrawal = 1 NEO
            "KAVA": Decimal("8"),
            "FLOW": Decimal("5"),
            "EGLD": Decimal("0.1"),
            "ALGO": Decimal("20"),
            "THETA": Decimal("3"),
            "XTZ": Decimal("5"),
            "LUNA": Decimal("10"),
            "LUNC": Decimal("10000"),
            "OM": Decimal("5"),
            "PYTH": Decimal("10"),
            "JTO": Decimal("1.5"),
            "JUP": Decimal("5"),
            "WIF": Decimal("0.8"),
            "BONK": Decimal("200000"),
            "PEPE": Decimal("500000"),
            "SHIB": Decimal("500000"),
            "FLOKI": Decimal("50000"),
            "MOVE": Decimal("5"),
            "ME": Decimal("0.3"),
            "PUMP": Decimal("2"),
            "WLFI": Decimal("5"),
            "SAHARA": Decimal("5"),
        }
        DEFAULT_DUST_THRESHOLD = Decimal("5")  # Varsayılan: 5 coin'den az = toz (güvenli)
        
        coins_with_balance = []
        dust_count = 0
        
        for coin, bal in coins_with_balance_raw:
            symbol = coin["symbol"].upper()
            threshold = DUST_THRESHOLDS.get(symbol, DEFAULT_DUST_THRESHOLD)
            
            # Eşiğin altındaki bakiyeleri atla
            if bal < threshold:
                dust_count += 1
                continue
            coins_with_balance.append((coin, bal))
        
        if dust_count > 0:
            q.put(f"🧹 {dust_count} toz bakiye atlandı")
        
        q.put(f"✅ Çekilebilir: {len(coins_with_balance)} coin")
        
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
