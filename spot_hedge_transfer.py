# ──────────────────────────────────────────────────────────────────────────────
#  spot_hedge_transfer.py   –  BEAM ↔ BEAMX tam sürüm (alias + çekim düzeltildi)
# ──────────────────────────────────────────────────────────────────────────────
"""
Binance spot tarafında sembolü **BEAMX**, BTCTurk tarafında **BEAM** olan
coin akışı için alias eklendi.

• `bin_coin = info.get("fut", coin).upper()` → BEAM → BEAMX  
  - Spot/Futures çifti : `bin_coin + "USDT"`  (BEAMXUSDT)  
  - Çekim (withdraw)   : `coin=bin_coin` (BEAMX)  
• BTCTurk yatırma kontrolü orijinal `coin` kodunu kullanır (BEAM).  
• Diğer coinlerde `fut` alanı yoksa eski davranış korunur.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import time
from decimal import Decimal
from typing import Dict, Optional

import requests
import telebot
from binance.client import Client
from binance.enums import ORDER_TYPE_LIMIT, SIDE_SELL, TIME_IN_FORCE_GTC
from dotenv import load_dotenv

from coin_bilgileri import coin_bilgi  # 113‑coin tablo

# ─────────────────────────── API / BOT kurulumu ─────────────────────────────
load_dotenv()
api_key: str           = os.getenv("BINANCE_API_KEY", "")
api_secret: str        = os.getenv("BINANCE_API_SECRET", "")
telegram_token: str    = os.getenv("TELEGRAM_BOT_TOKEN", "")
telegram_chat_id: str  = os.getenv("TELEGRAM_CHAT_ID", "")

client = Client(api_key, api_secret)
client.RECV_WINDOW = 60_000
bot     = telebot.TeleBot(telegram_token)

TARGET_USDT   = 10_000       # her coin için harcanacak USDT
LIMIT_PERCENT = float("0.5")   # %0.5 → float

# ─────────────────────────── Telegram ────────────────────────────

def send_telegram(msg: str) -> None:
    try:
        bot.send_message(telegram_chat_id, msg)
    except Exception:
        print("Telegram mesajı gönderilemedi →", msg)

# ╭──────────────────────── Binance yardımcıları ─────────────────────────╮

def get_price(symbol: str) -> float:
    return float(client.get_symbol_ticker(symbol=symbol)["price"])


def get_futures_price(symbol: str) -> float:
    """Vadeli piyasa fiyatını al"""
    return float(client.futures_symbol_ticker(symbol=symbol)["price"])


def _precision(info: Dict, ftype: str, key: str) -> int:
    flt = next(f for f in info["filters"] if f["filterType"] == ftype)
    return int(round(-math.log10(float(flt[key]))))


def get_quantity_precision(symbol: str) -> int:
    return _precision(client.get_symbol_info(symbol), "LOT_SIZE", "stepSize")


def get_price_precision(symbol: str) -> int:
    return _precision(client.get_symbol_info(symbol), "PRICE_FILTER", "tickSize")


def round_quantity(symbol: str, qty: float) -> float:
    return round(qty, get_quantity_precision(symbol))


def round_price(symbol: str, price: float) -> float:
    return round(price, get_price_precision(symbol))


def wait_order_fill(order_id: int, symbol: str, timeout: int = 5) -> float:
    for _ in range(timeout):
        time.sleep(1)
        order = client.get_order(symbol=symbol, orderId=order_id)
        if order["status"] == "FILLED":
            return float(order["executedQty"])
    client.cancel_order(symbol=symbol, orderId=order_id)
    return float(order["executedQty"])


def send_spot_order(symbol: str, quantity: float, price: float):
    try:
        return client.order_limit_buy(symbol=symbol, quantity=quantity, price=str(price))
    except Exception as e:
        send_telegram(f"❌ Spot alım hatası: {e}")
        return None

# ─── Futures LOT_SIZE yuvarlama ────────────────────────────────────────────

def get_futures_qty_precision(symbol: str) -> int:
    info = client.futures_exchange_info()
    sym  = next(s for s in info["symbols"] if s["symbol"] == symbol)
    lot  = next(f for f in sym["filters"] if f["filterType"] == "LOT_SIZE")
    return int(round(-math.log10(float(lot["stepSize"]))))


def round_futures_qty(symbol: str, qty: float) -> float:
    return round(qty, get_futures_qty_precision(symbol))

# ──────────────────── Short-hedge (güncellenmiş) ────────────────────
def send_short_order_with_retry(symbol: str, coin: str, qty: float) -> None:
    """
    • qty  → LOT_SIZE adımına (futures_step) aşağı yuvarlanır, doğru hassasiyetle yazılır
    • hedge_price → PRICE_FILTER tickSize'a aşağı yuvarlanır
    • VADELİ PİYASA FİYATI kullanılır (spot değil!)
    """
    # hassasiyetler
    qty_prec   = get_futures_qty_precision(symbol)
    price_prec = get_price_precision(symbol)

    qty  = round_futures_qty(symbol, qty)                  # Decimal
    qstr = f"{qty:.{qty_prec}f}"                          # '0.001' vb.

    retries = 0
    while retries < 15:
        try:
            # isolated 1× kaldıraç ayarları (hata verse de akışı durdurmaz)
            try:
                client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
            except Exception:
                pass
            try:
                client.futures_change_leverage(symbol=symbol, leverage=1)
            except Exception:
                pass

            # ---- LIMIT hedge emri ------------------------------------
            # VADELİ piyasa fiyatını al (SPOT DEĞİL!)
            mkt = get_futures_price(symbol)  # ← DEĞİŞİKLİK: futures fiyatı
            target_price = mkt * (1 - float(LIMIT_PERCENT) / 100.0)

            # round_price(symbol, price)  → ilk argüman SEMBOL olmak zorunda
            hpx  = round_price(symbol, target_price)
            pstr = f"{hpx:.{price_prec}f}"

            order = client.futures_create_order(
                symbol      = symbol,
                side        = SIDE_SELL,
                type        = ORDER_TYPE_LIMIT,
                quantity    = qstr,
                price       = pstr,
                timeInForce = TIME_IN_FORCE_GTC,
            )

            send_telegram(f"📉 SHORT EMRİ: {qstr} {coin} @ {pstr} (vadeli fiyat: {mkt})")

            time.sleep(5)
            st = client.futures_get_order(symbol=symbol, orderId=order["orderId"])
            if st["status"] == "FILLED":
                return                                # ✔️ başarı

            client.futures_cancel_order(symbol=symbol, orderId=order["orderId"])
            send_telegram("🔁 Short emri dolmadı, yeniden deneniyor…")
            retries += 1

        except Exception as e:
            send_telegram(f"❌ Short hedge hatası: {e}")
            break




# ╭──────────────────────── Çekim / yatırma kontrolleri ──────────────────╮
def is_withdraw_open(bin_coin: str, network: str) -> bool:
    """
    Binance'te çekim açık mı?
    • Ağ adı startswith() karşılaştırmasıyla (ETH ↔ ETHEREUM vb.) bakılır.
    • API beklenmedik bir nesne (dict / str) döndürürse **açık** kabul edilir
      ki bot durmasın.
    """
    try:
        ts  = str(int(time.time() * 1000))
        qs  = f"timestamp={ts}"
        sig = hmac.new(api_secret.encode(), qs.encode(),
                       hashlib.sha256).hexdigest()
        url = (
            "https://api.binance.com/sapi/v1/capital/config/getall"
            f"?{qs}&signature={sig}"
        )
        hdr = {"X-MBX-APIKEY": api_key}

        assets: Any = requests.get(url, headers=hdr, timeout=10).json()

        # Yanıt liste değilse (limit/hata)  →  çekim açık varsay
        if not isinstance(assets, list):
            return True

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if asset.get("coin", "").upper() != bin_coin.upper():
                continue

            for net in asset.get("networkList", []):
                try:
                    chain = (net.get("network") or "").upper()
                    if chain.startswith(network.upper()):
                        # withdrawEnable anahtarı eksikse bile True kabul et
                        return bool(net.get("withdrawEnable", True))
                except Exception:
                    # tek ağ kaydı bozuksa diğerlerine bak
                    continue

        # Coin/ağ kaydı yok → açık say
        return True

    except Exception as err:
        send_telegram(f"❌ Binance çekim kontrolü: {err}")
        return True        # bağ/JSON hatasında da açık say
# ╰────────────────────────────────────────────────────────────────────────╯



# --- BTCTurk yatırma açık mı? ----------------------------------------------
def is_btcturk_deposit_open(coin: str) -> bool:
    """
    BTCTurk'te yatırma (deposit) açık mı?
    • SOL ağındaki coin'ler BTCTurk'te 'SPL...' önekiyle listelenir.
    """
    try:
        coin_u  = coin.upper()
        search  = [coin_u]

        info = coin_bilgi.get(coin_u, {})
        if info.get("network", "").upper() == "SOL":
            search.insert(0, f"SPL{coin_u}")            # önce SPL…

        r = requests.get(
                "https://api.btcturk.com/api/v2/server/exchangeinfo",
                timeout=5).json()
        blocks = r["data"].get("currencyOperationBlocks", [])

        for sym in search:
            blk = next((b for b in blocks if b["currencySymbol"] == sym), None)
            if blk and blk.get("depositDisabled") is False:
                return True          # açık
            if blk:                  # blok var ama kapalı
                return False

        return True                  # hiç blok yok → varsayılan açık

    except Exception as err:                             # noqa: BLE001
        send_telegram(f"❌ BTCTurk yatırma kontrol hatası: {err}")
        return False


# ───────────────────────── Transfer Fonksiyonu ─────────────────────────

def send_withdrawal(bin_coin: str, network: str, address: str, quantity: float, memo: Optional[str] = None):
    try:
        params = {
            "coin":    bin_coin,
            "address": address,
            "amount":  quantity,
            "network": network,
        }
        if memo and memo.upper() != "NONE":
            params["addressTag"] = memo
        client.withdraw(**params)
        send_telegram(f"🚀 {bin_coin} transferi yapıldı: {quantity} ({network})")
    except Exception as e:
        send_telegram(f"❌ Transfer hatası: {e}")

# ╭──────────────────────── Ana Akış ─────────────────────────────────────╮

def spot_alim_hedge_transfer(coin: str) -> bool:
    """Binance spot al – Binance futures short hedge – BTCTurk'e transfer.

    • Binance tarafında `bin_coin` (alias'lı) kullanılır → BEAMX
    • BTCTurk kontrollerinde orijinal `coin` kullanılır → BEAM
    """
    info = coin_bilgi.get(coin.upper())
    if not info:
        send_telegram(f"⛔ {coin}: coin_bilgileri.py içinde tanımlı değil")
        return False

    # Binance tarafı için alias'lı sembol
    bin_coin = info.get("fut", coin).upper()          # BEAM → BEAMX, diğerleri değişmez

    symbol  = f"{bin_coin}USDT"   # Spot çifti (ör. BEAMXUSDT)
    fut_sym = symbol              # Futures çifti aynı

    network = info["network"]
    address = info["address"]
    memo    = info["memo"]

    # —— Ön kontroller ——
    if not is_withdraw_open(bin_coin, network):        # ← alias'lı!
        send_telegram(f"❌ Binance çekim kapalı: {bin_coin}/{network}")
        return False

    if not is_btcturk_deposit_open(coin):              # BTCTurk BEAM yatırma açık mı?
        send_telegram(f"❌ BTCTurk yatırma kapalı: {coin}")
        return False

    # —— Spot alım ——
    try:
        spot_price = get_price(symbol)
    except Exception as exc:
        send_telegram(f"❌ Fiyat alınamadı {symbol}: {exc}")
        return False

    target_qty   = round_quantity(symbol, TARGET_USDT / spot_price)
    filled_total = 0.0
    send_telegram(f"💸 {coin} alımı başlıyor → hedef {target_qty} (fiyat {spot_price})")

    while filled_total < target_qty:
        cur_price   = get_price(symbol)
        order_qty   = round_quantity(symbol, target_qty - filled_total)
        order_price = round_price(symbol, cur_price)
        order       = send_spot_order(symbol, order_qty, order_price)
        if not order:
            break
        filled      = wait_order_fill(order["orderId"], symbol)
        filled_total = round(filled_total + filled, 8)
        if filled:
            send_telegram(f"✅ ALIM TAMAMLANDI: {filled} {coin}")
        else:
            send_telegram("⚠️ Emir dolmadı, yeniden deneniyor…")

    if not filled_total:
        return False

    # —— Short hedge ——
    send_short_order_with_retry(fut_sym, coin, filled_total)

    # —— Transfer ——
    send_withdrawal(bin_coin, network, address, filled_total, memo)
    return True

# ╰────────────────────────────────────────────────────────────────────────╯

if __name__ == "__main__":
    # Hızlı test: tek seferde LRC süreci
    spot_alim_hedge_transfer("LRC")
