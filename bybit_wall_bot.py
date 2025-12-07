# -*- coding: utf-8 -*-
"""
BYBIT 14 DK DUVAR BOTU (BybitAdapter İmza + Timestamp Fix)
---------------------------------------------------------
• Her 14 dakikada bir TOKEN/USDT tahtasına 900.000 adet LIMIT SELL emri atar.
• Fiyat: o anki en iyi satış (best ask) fiyatı.
• Emir SPOT piyasaya atılır (category=spot).
• Emir 2 dakika boyunca takip edilir:
    - 2 dk içinde full dolarsa: dokunulmaz.
    - 2 dk sonunda hâlâ açık/kısmi doluysa: emir iptal edilir.
• Bybit API imzalama ve timestamp düzeltme (server_time_offset) senin
  Multi-Exchange Çekim Botu içindeki BybitAdapter ile aynı mantıkta.
"""

import os
import time
import json
import hmac
import hashlib
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, Tuple

import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# =============== AYARLAR ===============
BYBIT_KEY = os.getenv("BYBIT_KEY", "").strip()
BYBIT_SECRET = os.getenv("BYBIT_SECRET", "").strip()
BYBIT_API = "https://api.bybit.com"   # Senin adapter'daki ile aynı

RECV_WINDOW = "60000"
MAX_RETRIES = 3

SYMBOL = "TOKENUSDT"               # Örn: "PEPEUSDT", "DOGEUSDT"
ORDER_SIDE = "Sell"                # "Buy" veya "Sell"
ORDER_QTY = Decimal("900000")      # 900.000 adet
CYCLE_SECONDS = 14 * 60            # 14 dakika
WATCH_SECONDS = 2 * 60             # 2 dakika emir izleme süresi
POLL_INTERVAL = 5                  # 5 saniyede bir emir durumu sorgu

# Tick/step ayarları (coine göre güncelle)
PRICE_TICK_SIZE = Decimal("0.0000001")  # örnek tick size
QTY_STEP_SIZE = Decimal("1")            # örnek step size (tam sayı adım)


# =============== Bybit API (senin adapter'a göre) ===============
class BybitApi:
    def __init__(self, key: str, secret: str, api_url: str):
        self.key = key
        self.secret = secret
        self.api_url = api_url
        self.server_time_offset = 0  # server-local farkı (ms)

    # --- yardımcılar ---
    def _ts(self) -> str:
        """Senin adapter'daki gibi server_time_offset ile düzeltilmiş timestamp (ms)."""
        local_ms = int(time.time() * 1000)
        adjusted_ms = local_ms + self.server_time_offset
        return str(adjusted_ms)

    def _sign(self, payload: str) -> str:
        """HMAC-SHA256 imza (BYBIT_SECRET ile)."""
        return hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def _is_timestamp_error(self, data: dict) -> bool:
        """Senin adapter'daki timestamp hata yakalayıcı."""
        if not isinstance(data, dict):
            return False
        code = data.get("retCode")
        msg = (data.get("retMsg") or "").lower()
        if code == 131002 and "timestamp" in msg:
            return True
        return "timestamp" in msg

    def _cooldown_seconds(self, data: dict) -> int:
        """Rate limit/cooldown için bekleme süresi."""
        if not isinstance(data, dict):
            return 0
        msg = data.get("retMsg") or ""
        if data.get("retCode") == 131001:
            import re
            match = re.search(r"wait at least\s*(\d+)\s*seconds", msg, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) + 1
                except ValueError:
                    pass
        return 0

    async def _sync_time(self, session: aiohttp.ClientSession):
        """
        Senin BybitAdapter'ında olduğu gibi /v5/market/time ile
        server-local saat farkını (ms) bulup self.server_time_offset'e yazar.
        """
        try:
            async with session.get(f"{self.api_url}/v5/market/time") as resp:
                data = await resp.json(content_type=None)
                server_ms = int(data["result"]["timeNano"]) // 1_000_000
                local_ms = int(time.time() * 1000)
                self.server_time_offset = server_ms - local_ms
        except Exception:
            self.server_time_offset = 0

    async def _get_private(self, session: aiohttp.ClientSession, endpoint: str, params: Dict[str, Any]) -> Tuple[dict, int]:
        """
        Senin _get fonksiyonunun sadeleştirilmiş versiyonu (sadece private için).
        GET + imzalama + timestamp fix.
        """
        attempt = 0
        last_response = None

        while attempt < MAX_RETRIES:
            attempt += 1
            ts = self._ts()

            # timestamp & recvWindow query'de
            params_with_meta = dict(params or {})
            params_with_meta["timestamp"] = ts
            params_with_meta["recvWindow"] = RECV_WINDOW

            from urllib.parse import urlencode
            query = urlencode(sorted(params_with_meta.items()))

            sign_payload = ts + self.key + RECV_WINDOW + query
            signature = self._sign(sign_payload)

            headers = {
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            }

            url = f"{self.api_url}{endpoint}"
            if query:
                url += f"?{query}"

            async with session.get(url, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if not isinstance(data, dict):
                    data = {"raw": data}

                last_response = (data, resp.status)

                # Timestamp hatası → time sync
                if attempt < MAX_RETRIES and resp.status == 200 and self._is_timestamp_error(data):
                    await self._sync_time(session)
                    continue

                # Rate limit vs.
                if attempt < MAX_RETRIES:
                    delay = self._cooldown_seconds(data)
                    if delay:
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_get_error"}, 500

    async def _post_private(self, session: aiohttp.ClientSession, endpoint: str, body: Dict[str, Any]) -> Tuple[dict, int]:
        """
        Senin _post fonksiyonunun sadeleştirilmiş versiyonu (private POST için).
        """
        attempt = 0
        last_response = None

        while attempt < MAX_RETRIES:
            attempt += 1
            ts = self._ts()

            body_with_meta = dict(body or {})
            body_with_meta["timestamp"] = ts
            body_with_meta["recvWindow"] = RECV_WINDOW

            body_json = json.dumps(body_with_meta, separators=(",", ":"))

            sign_payload = ts + self.key + RECV_WINDOW + body_json
            signature = self._sign(sign_payload)

            headers = {
                "X-BAPI-API-KEY": self.key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": RECV_WINDOW,
                "Content-Type": "application/json",
            }

            url = f"{self.api_url}{endpoint}"

            async with session.post(url, data=body_json, headers=headers) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"raw": await resp.text()}

                if not isinstance(data, dict):
                    data = {"raw": data}

                last_response = (data, resp.status)

                # Timestamp hatası → time sync
                if attempt < MAX_RETRIES and resp.status == 200 and self._is_timestamp_error(data):
                    await self._sync_time(session)
                    continue

                # Rate limit vs.
                if attempt < MAX_RETRIES:
                    delay = self._cooldown_seconds(data)
                    if delay:
                        await asyncio.sleep(delay)
                        continue

                return data, resp.status

        if last_response is not None:
            return last_response
        return {"retCode": -1, "retMsg": "unhandled_post_error"}, 500

    # ---- DUVAR BOTUNDA KULLANACAĞIMIZ METODLAR ----
    async def get_best_ask(self, session: aiohttp.ClientSession, symbol: str) -> Optional[Decimal]:
        """Public orderbook'tan best ask fiyatını alır."""
        params = {
            "category": "spot",
            "symbol": symbol
        }
        async with session.get(f"{self.api_url}/v5/market/orderbook", params=params) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                print("[X] orderbook parse edilemedi")
                return None

        if str(data.get("retCode")) != "0":
            print(f"[X] orderbook hatası: {data.get('retMsg')}")
            return None

        ob = data.get("result", {})
        asks = ob.get("a") or ob.get("asks")
        if not asks:
            print("[!] Ask listesi boş")
            return None

        # ["fiyat", "miktar"]
        return Decimal(asks[0][0])

    async def create_limit_order(self, session: aiohttp.ClientSession, symbol: str, side: str,
                                 qty: Decimal, price: Decimal) -> Optional[str]:
        """LIMIT emri oluşturup orderId döner."""
        body = {
            "category": "spot",
            "symbol": symbol,
            "side": side,             # "Buy" / "Sell"
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC",
        }
        data, status = await self._post_private(session, "/v5/order/create", body)

        if status != 200 or str(data.get("retCode")) != "0":
            print(f"[X] order/create hata: HTTP={status}, retCode={data.get('retCode')}, msg={data.get('retMsg')}")
            return None

        order_id = data.get("result", {}).get("orderId")
        print(f"[✓] Emir oluşturuldu. orderId={order_id}")
        return order_id

    async def get_order_status(self, session: aiohttp.ClientSession, symbol: str, order_id: str) -> Tuple[Optional[str], Optional[Decimal]]:
        """orderStatus ve cumExecQty döner."""
        params = {
            "category": "spot",
            "symbol": symbol,
            "orderId": order_id,
        }
        data, status = await self._get_private(session, "/v5/order/realtime", params)

        if status != 200 or str(data.get("retCode")) != "0":
            print(f"[X] order/realtime hata: HTTP={status}, retCode={data.get('retCode')}, msg={data.get('retMsg')}")
            return None, None

        lst = data.get("result", {}).get("list", [])
        if not lst:
            print("[!] orderId bulunamadı")
            return None, None

        info = lst[0]
        status_str = info.get("orderStatus")
        cum_exec_qty = Decimal(info.get("cumExecQty", "0"))
        return status_str, cum_exec_qty

    async def cancel_order(self, session: aiohttp.ClientSession, symbol: str, order_id: str) -> bool:
        """Emri iptal eder."""
        body = {
            "category": "spot",
            "symbol": symbol,
            "orderId": order_id,
        }
        data, status = await self._post_private(session, "/v5/order/cancel", body)

        if status != 200 or str(data.get("retCode")) != "0":
            print(f"[X] order/cancel hata: HTTP={status}, retCode={data.get('retCode')}, msg={data.get('retMsg')}")
            return False

        print(f"[✓] Emir iptal edildi. orderId={order_id}")
        return True


# =============== YARDIMCI FONKSİYONLAR ===============
def round_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step == 0:
        return value
    return (value / step).quantize(0, rounding=ROUND_DOWN) * step


# =============== ANA DUVAR LOOP'U ===============
async def wall_loop():
    if not BYBIT_KEY or not BYBIT_SECRET:
        print("[X] BYBIT_KEY veya BYBIT_SECRET tanımlı değil!")
        return

    api = BybitApi(BYBIT_KEY, BYBIT_SECRET, BYBIT_API)

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # İlk başta time sync yapalım (senin adapter'da olduğu gibi)
        await api._sync_time(session)

        print(
            f"BYBIT DUVAR BOTU BAŞLADI\n"
            f"Sembol: {SYMBOL}\n"
            f"Her {CYCLE_SECONDS/60:.0f} dakikada bir {ORDER_QTY} adet {ORDER_SIDE} LIMIT emir.\n"
            f"Emir tahtada max {WATCH_SECONDS/60:.0f} dakika kalır, dolmazsa iptal edilir.\n"
        )

        while True:
            cycle_start = time.time()

            try:
                best_ask = await api.get_best_ask(session, SYMBOL)
                if best_ask is None:
                    print("[!] Best ask alınamadı, 30 sn sonra tekrar denenecek.")
                    await asyncio.sleep(30)
                    continue

                adj_price = round_to_step(best_ask, PRICE_TICK_SIZE)
                adj_qty = round_to_step(ORDER_QTY, QTY_STEP_SIZE)

                print(f"[*] Yeni emir: {SYMBOL} {ORDER_SIDE} {adj_qty} @ {adj_price}")
                order_id = await api.create_limit_order(session, SYMBOL, ORDER_SIDE, adj_qty, adj_price)
                if not order_id:
                    print("[!] Emir oluşturulamadı, 60 sn sonra tekrar denenecek.")
                    await asyncio.sleep(60)
                    continue

                # --- 2 dakika emir izleme ---
                print(f"[i] Emir {WATCH_SECONDS/60:.0f} dakika izlenecek...")
                elapsed_watch = 0
                final_status = None
                final_filled = Decimal("0")

                while elapsed_watch < WATCH_SECONDS:
                    await asyncio.sleep(POLL_INTERVAL)
                    elapsed_watch += POLL_INTERVAL

                    status, filled = await api.get_order_status(session, SYMBOL, order_id)
                    if status is None:
                        print("[!] Emir durumu alınamadı, izlemeden çıkılıyor.")
                        break

                    final_status = status
                    final_filled = filled or Decimal("0")
                    print(f"[STATÜ] orderId={order_id} | status={status} | filled={final_filled}")

                    if status in ("Filled", "Cancelled", "Rejected"):
                        # Emir tamamen dolmuş ya da iptal edilmiş
                        break

                # 2 dk doldu, emir hâlâ açık/kısmi ise iptal
                if final_status not in ("Filled", "Cancelled", "Rejected"):
                    print("[i] 2 dk bitti, emir hâlâ açık görünüyor. İptal ediliyor...")
                    await api.cancel_order(session, SYMBOL, order_id)
                else:
                    print(f"[i] İzleme bitti. Son durum: {final_status}, filled={final_filled}")

            except Exception as e:
                print(f"[ANA LOOP HATASI]: {e}")

            # --- 14 dakikalık periyodu tamamlama ---
            total_elapsed = time.time() - cycle_start
            remaining = CYCLE_SECONDS - total_elapsed
            if remaining > 0:
                print(f"[i] Bir sonraki emre kadar {int(remaining)} sn uyku ({remaining/60:.1f} dk)...")
                await asyncio.sleep(remaining)
            else:
                print("[i] 14 dk zaten dolmuş, direkt yeni döngüye geçiliyor...")


if __name__ == "__main__":
    asyncio.run(wall_loop())
