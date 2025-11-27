# -*- coding: utf-8 -*-
"""
Binance ➜ Paribu Spot-Hedge Botu (marker + withdraw debug + network normalize)
------------------------------------------------------------------------------
• Mevcut akış korunmuştur.
• Çekim başlatıldıysa stdout → TRANSFER_STARTED
• Çekim başlamadı / hata olduysa stdout → NO_TRANSFER
• 1000'li/vadeli isimler işlem/hedge için kullanılır; çekim için gerçek asset (withdraw_coin)
• Ağ adı normalizasyonu: ERC20→ETH, BEP20→BSC, ARB→ARBITRUMONE, OP→OPTIMISM, vb.
• DEBUG_WITHDRAW=1 ise ayrıntılı log dosyası üretir: withdraw_debug_<COIN>_YYYYMMDD.log
"""

from __future__ import annotations
import os, sys, time, hmac, hashlib, requests
from pathlib import Path
from decimal import Decimal, getcontext
from typing import Optional, Any
from datetime import datetime
import json as _json

import telebot
from binance.client import Client
from binance.enums import ORDER_TYPE_LIMIT, SIDE_SELL, TIME_IN_FORCE_GTC
from dotenv import load_dotenv

from coin_bilgileri import coin_bilgi

# ────────────────────────── Ortam ──────────────────────────
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY     = os.getenv("BINANCE_API_KEY")
API_SECRET  = os.getenv("BINANCE_API_SECRET")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID")

TARGET_USDT     = Decimal(os.getenv("TARGET_USDT", "10000"))
LIMIT_PCT       = Decimal(os.getenv("LIMIT_PCT",  "0.5"))   # bilgilendirme amaçlı (limit px hesap)
STRICT_WITHDRAW = os.getenv("STRICT_WITHDRAW_CHECK", "0") == "1"
DEBUG_WITHDRAW  = os.getenv("DEBUG_WITHDRAW", "0") == "1"

client = Client(API_KEY, API_SECRET)
bot    = telebot.TeleBot(TG_TOKEN) if TG_TOKEN else None

getcontext().prec = 28

# Paribu yapılandırma (yatırma açık/kapa kontrolü)
PARIBU_CFG_URL = "https://web.paribu.com/initials/config"

# Örnek isim eşleştirme (Paribu BEAM → Binance BEAMX)
BINANCE_MAP = {"BEAM": "BEAMX"}

# ────────────────────────── Yardımcılar ─────────────────────────
def tg(msg: str) -> None:
    if bot:
        try:
            bot.send_message(CHAT_ID, msg)
        except Exception as e:
            print(f"[TG-HATA] {e}  >>  {msg}")
    else:
        print("[TG]", msg)

def _wlog(coin: str, text: str) -> None:
    """Withdraw tanı için yerel log dosyasına yazar + consola basar."""
    if not DEBUG_WITHDRAW:
        print(f"[WLOG {coin}] {text}", flush=True)
        return
    try:
        fn = BASE_DIR / f"withdraw_debug_{coin}_{datetime.now().strftime('%Y%m%d')}.log"
        with open(fn, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
    except Exception:
        pass
    print(f"[WLOG {coin}] {text}", flush=True)

def _normalize_network_for_binance(net: str) -> str:
    """
    Kullanıcı/Paribu adlarını Binance withdraw ağ kodlarına dönüştürür.
    Örn: ERC20→ETH, BEP20→BSC, ARB→ARBITRUMONE, OP→OPTIMISM, MATIC→POLYGON...
    """
    if not net:
        return net
    n = net.strip().upper().replace(" ", "").replace("-", "")
    alias = {
        "ERC20": "ETH", "ETH": "ETH",
        "BEP20": "BSC", "BSC": "BSC",
        "TRC20": "TRX", "TRX": "TRX",
        "MATIC": "POLYGON", "POLYGON": "POLYGON",
        "AVAXC": "AVAXC", "AVAX": "AVAXC", "AVALANCHEC": "AVAXC",
        "ARB": "ARBITRUMONE", "ARBITRUM": "ARBITRUMONE", "ARBITRUMONE": "ARBITRUMONE",
        "OP": "OPTIMISM", "OPTIMISM": "OPTIMISM",
        "SOL": "SOL",
        "BASE": "BASE", "TON": "TON",
    }
    return alias.get(n, net.upper())

# Binance precision yardımcıları
flt   = lambda s,f,k: Decimal(next(x for x in client.get_symbol_info(s)["filters"] if x["filterType"]==f)[k])
step  = lambda s: flt(s,"LOT_SIZE","stepSize")
tick  = lambda s: flt(s,"PRICE_FILTER","tickSize")
adj   = lambda v,s: (v//s)*s
plain = lambda d: format(d, 'f')
price = lambda s: Decimal(client.get_symbol_ticker(symbol=s)["price"])

# ───────────────────── Paribu depozit kontrol ───────────────────
def paribu_deposit_open(sym: str) -> bool:
    try:
        cfg:dict[str,Any] = requests.get(PARIBU_CFG_URL, timeout=10).json()
        itm = cfg.get(sym.lower())
        return not itm.get("deposit_suspended") if itm else True
    except Exception as e:
        tg(f"❌ Paribu yatırma kontrolü: {e}")
        # Hata varsa güvenli tarafta kal → kapalı say
        return False

# ───────────────────── Binance çekim aç/kapa ─────────────────────
def binance_withdraw_open(sym: str, net: str) -> bool:
    try:
        if DEBUG_WITHDRAW:
            _wlog(sym, f"check_withdraw_open: requested_net='{net}'")

        ts   = str(int(time.time() * 1000))
        sig  = hmac.new(API_SECRET.encode(), f"timestamp={ts}".encode(), hashlib.sha256).hexdigest()
        url  = f"https://api.binance.com/sapi/v1/capital/config/getall?timestamp={ts}&signature={sig}"
        hdr  = {"X-MBX-APIKEY": API_KEY}
        data = requests.get(url, headers=hdr, timeout=10).json()

        if not isinstance(data, list):
            tg(f"⚠️ Binance withdraw API beklenmeyen yanıt: {data}")
            return not STRICT_WITHDRAW

        # Esnek karşılaştırma için normalize
        want_norm = (net or "").upper().replace(" ", "").replace("-", "")
        coin_row = next((a for a in data if isinstance(a, dict) and a.get("coin",""").upper()==sym.upper()), None)
        if DEBUG_WITHDRAW:
            try:
                nets = coin_row.get("networkList", []) if coin_row else []
                _wlog(sym, "binance_getall.networkList=" + _json.dumps(nets, ensure_ascii=False)[:1500])
            except Exception as e:
                _wlog(sym, f"binance_getall parse err: {e}")

        if not coin_row:
            # Coin satırı yoksa, güvenli tarafta: engelleme
            return not STRICT_WITHDRAW

        for n in coin_row.get("networkList", []):
            chain_norm = (n.get("network") or "").upper().replace(" ", "").replace("-", "")
            if DEBUG_WITHDRAW:
                _wlog(sym, f"match_try: want='{want_norm}' vs chain='{chain_norm}' enable={n.get('withdrawEnable')}")
            if want_norm in chain_norm or chain_norm in want_norm:
                if DEBUG_WITHDRAW:
                    _wlog(sym, f"match_net='{n.get('network')}', withdrawEnable={n.get('withdrawEnable')}")
                return bool(n.get("withdrawEnable", True))

        # Ağ eşleşmedi → uyar, ama işlemi tamamen öldürme (STRICT değilse)
        tg(f"⚠️ Binance çekim ağı eşleşmesi bulunamadı ({sym}-{net})")
        return not STRICT_WITHDRAW

    except Exception as e:
        tg(f"⚠️ Binance çekim kontrolü hatası: {e}")
        return not STRICT_WITHDRAW

# ───────────────────────── Spot ALIM takibi ─────────────────────
def spot_place_and_track(sym: str, qty: Decimal, limit_px: Decimal, wait_seconds: int = 8) -> Decimal:
    st = step(sym); tk = tick(sym)
    qty      = (qty // st) * st
    limit_px = (limit_px // tk) * tk
    if qty <= 0:
        return Decimal(0)

    cid = f"spot-{sym}-{int(time.time()*1000)}"
    try:
        client.order_limit_buy(symbol=sym, quantity=plain(qty), price=plain(limit_px),
                               newClientOrderId=cid, recvWindow=60000)
        tg(f"🟢 SPOT BUY {plain(qty)} {sym.replace('USDT','')} @ {plain(limit_px)} (cid:{cid})")
    except Exception as e:
        tg(f"❌ Spot alım hatası: {e}")
        return Decimal(0)

    deadline = time.time() + wait_seconds
    last_exec = Decimal(0)
    while time.time() < deadline:
        time.sleep(1)
        try:
            stt = client.get_order(symbol=sym, origClientOrderId=cid, recvWindow=60000)
            status = stt.get("status", "")
            exec_qty = Decimal(stt.get("executedQty", "0"))
            if exec_qty != last_exec:
                last_exec = exec_qty
                if exec_qty > 0:
                    tg(f"ℹ️ Spot kısmi dolum: {plain(exec_qty)} / {plain(qty)}")
            if status == "FILLED":
                return exec_qty
            if status in ("CANCELED", "REJECTED", "EXPIRED"):
                tg(f"⚠️ Spot emir durumu: {status}")
                return exec_qty
        except Exception as e:
            if "Unknown order" in str(e) or "code=-2011" in str(e):
                try:
                    opens = client.get_open_orders(symbol=sym, recvWindow=60000)
                    if any(o.get("clientOrderId")==cid for o in opens):
                        continue
                    hist = client.get_all_orders(symbol=sym, limit=10, recvWindow=60000)
                    rec  = next((o for o in hist if o.get("clientOrderId")==cid), None)
                    if rec:
                        status = rec.get("status","")
                        exec_qty = Decimal(rec.get("executedQty","0"))
                        if status == "FILLED":
                            return exec_qty
                        if status in ("CANCELED","REJECTED","EXPIRED"):
                            tg(f"⚠️ Spot: {status}")
                            return exec_qty
                except Exception:
                    pass
            else:
                tg(f"❌ Spot izleme hatası: {e}")
                break

    # Süre doldu → iptal & ne kadar dolmuşsa onu dön
    try:
        client.cancel_order(symbol=sym, origClientOrderId=cid, recvWindow=60000)
    except Exception:
        pass
    try:
        stt = client.get_order(symbol=sym, origClientOrderId=cid, recvWindow=60000)
        return Decimal(stt.get("executedQty","0"))
    except Exception:
        try:
            hist = client.get_all_orders(symbol=sym, limit=10, recvWindow=60000)
            rec  = next((o for o in hist if o.get("clientOrderId")==cid), None)
            return Decimal(rec.get("executedQty","0")) if rec else Decimal(0)
        except Exception:
            return Decimal(0)

# ───────────────────────── Futures hedge ─────────────────────────
def fut_step(sym: str) -> Decimal:
    info = client.futures_exchange_info()
    s    = next((x for x in info["symbols"] if x["symbol"] == sym), None)
    if not s:
        return Decimal("1")
    lot  = next(f for f in s["filters"] if f["filterType"] == "LOT_SIZE")
    return Decimal(lot["stepSize"])

def f_tick(sym: str) -> Decimal:
    info = client.futures_exchange_info()
    s    = next(x for x in info["symbols"] if x["symbol"] == sym)
    pf   = next(f for f in s["filters"] if f["filterType"] == "PRICE_FILTER")
    return Decimal(pf["tickSize"])

def hedge_short(fsym: str, coin: str, qty: Decimal,
                wait_max:int=45, replace_every:int=6, bid_offset_ticks:int=1) -> bool:
    step_f = fut_step(fsym)
    qty    = (qty // step_f) * step_f
    if qty <= 0:
        tg("ℹ️ Hedge miktarı 0, atlanıyor")
        return True

    try:
        client.futures_change_margin_type(symbol=fsym, marginType="ISOLATED")
    except Exception:
        pass
    try:
        client.futures_change_leverage(symbol=fsym, leverage=1)
    except Exception:
        pass

    tk = f_tick(fsym)
    def _place_limit():
        bt  = client.futures_orderbook_ticker(symbol=fsym)
        bid = Decimal(bt["bidPrice"])
        px  = bid - tk * bid_offset_ticks
        if px <= 0:
            px = tk
        px = (px // tk) * tk
        cid = f"hedge-{fsym}-{int(time.time()*1000)}"
        od  = client.futures_create_order(symbol=fsym, side=SIDE_SELL, type=ORDER_TYPE_LIMIT,
                                          quantity=plain(qty), price=plain(px),
                                          timeInForce=TIME_IN_FORCE_GTC, newClientOrderId=cid,
                                          recvWindow=60000)
        tg(f"📉 SHORT {plain(qty)} {coin} @ {plain(px)}")
        return cid

    cid = _place_limit()
    started = time.time()
    last_replace = started
    while time.time() - started < wait_max:
        time.sleep(2)
        try:
            st = client.futures_get_order(symbol=fsym, origClientOrderId=cid, recvWindow=60000)
            status = st.get("status","")
            if status == "FILLED":
                return True
            if status in ("CANCELED","REJECTED","EXPIRED"):
                tg(f"❌ Hedge order durumu: {status}")
                return False
        except Exception as e:
            if "Unknown order" in str(e) or "code=-2011" in str(e):
                try:
                    opens = client.futures_get_open_orders(symbol=fsym, recvWindow=60000)
                    if any(o.get("clientOrderId")==cid for o in opens):
                        pass
                    else:
                        hist = client.futures_get_all_orders(symbol=fsym, limit=10, recvWindow=60000)
                        rec  = next((o for o in hist if o.get("clientOrderId")==cid), None)
                        if rec:
                            stt = rec.get("status","")
                            if stt == "FILLED":
                                return True
                            if stt in ("CANCELED","REJECTED","EXPIRED"):
                                tg(f"❌ Hedge: {stt}")
                                return False
                except Exception:
                    pass
            else:
                tg(f"❌ Hedge hatası: {e}")
                return False

        if time.time() - last_replace >= replace_every:
            try:
                client.futures_cancel_order(symbol=fsym, origClientOrderId=cid, recvWindow=60000)
            except Exception:
                pass
            cid = _place_limit()
            last_replace = time.time()

    try:
        client.futures_cancel_order(symbol=fsym, origClientOrderId=cid, recvWindow=60000)
    except Exception:
        pass
    tg("⚠️ Hedge zaman aşımı; limit emri iptal edildi.")
    return False

# ─────────────────────── Withdraw çağrısı ────────────────────────
def withdraw(sym: str, net: str, addr: str, qty: Decimal, memo: Optional[str]):
    try:
        if DEBUG_WITHDRAW:
            _wlog(sym, f"withdraw_params: net='{net}', addr='{addr[:10]}...'")

        p = {"coin": sym, "address": addr, "amount": plain(qty), "network": net}
        if memo and str(memo).upper() != "NONE":
            p["addressTag"] = memo

        if DEBUG_WITHDRAW:
            _wlog(sym, "withdraw_request=" + _json.dumps(p, ensure_ascii=False))

        client.withdraw(**p)

        if DEBUG_WITHDRAW:
            _wlog(sym, "withdraw_response=OK (client.withdraw returned without exception)")

        tg(f"🚀 Transfer {qty} {sym}")
        print("TRANSFER_STARTED", flush=True)  # marker
        return True

    except Exception as e:
        # python-binance özel hata ise kod/mesajı yakala
        try:
            from binance.error import BinanceAPIException
            if isinstance(e, BinanceAPIException):
                _wlog(sym, f"withdraw_error_api: code={getattr(e, 'code', None)} msg={getattr(e, 'message', '')}")
        except Exception:
            pass

        _wlog(sym, f"withdraw_error: {type(e).__name__} | {e}")

        if DEBUG_WITHDRAW:
            # Teşhis için ham SAPI çağrısı (try/catch içinde)
            try:
                ts = str(int(time.time()*1000))
                params = {"coin": sym, "address": addr, "amount": plain(qty), "network": net, "timestamp": ts}
                if memo and str(memo).upper() != "NONE":
                    params["addressTag"] = memo
                sig = hmac.new(API_SECRET.encode(),
                               "&".join([f"{k}={v}" for k,v in params.items()]).encode(),
                               hashlib.sha256).hexdigest()
                url = "https://api.binance.com/sapi/v1/capital/withdraw/apply"
                hdr = {"X-MBX-APIKEY": API_KEY}
                r = requests.post(url, headers=hdr, params={**params, "signature": sig}, timeout=15)
                _wlog(sym, f"sapi_apply_status={r.status_code} body={r.text[:1500]}")
            except Exception as ee:
                _wlog(sym, f"sapi_apply_diag_error: {ee}")

        print("NO_TRANSFER", flush=True)      # marker
        tg(f"❌ Withdraw hata: {type(e).__name__} | {e}")
        return False

# ───────────────────────────── RUN ───────────────────────────────
def run(coin: str) -> bool:
    """
    • İşlem/hedge için 'trade_sym' (fut override varsa onu kullanır)
    • Çekim için 'withdraw_coin' (her zaman gerçek asset: e.g. SHIB, SYN, NEO...)
    """
    info = coin_bilgi.get(coin.upper())
    if not info:
        tg(f"⛔ {coin} coin_bilgileri.py’de yok")
        return False

    fut_override = (info.get("fut") or "").upper().strip()
    trade_sym    = (fut_override or BINANCE_MAP.get(coin.upper(), coin.upper())).upper()
    spot = f"{trade_sym}USDT"
    fut  = f"{trade_sym}USDT"

    # Çekim asset'i: gerçek coin adı; istersen coin_bilgileri.py'de 'withdraw_symbol' ile override
    withdraw_coin = (info.get("withdraw_symbol") or coin).upper()

    net, addr, memo = info["network"], info["address"], info.get("memo")
    binance_net     = _normalize_network_for_binance(net)

    # Çekim / yatırma kontrol (marker ile birlikte)
    if not binance_withdraw_open(withdraw_coin, binance_net):
        tg("❌ Binance çekim kapalı/şüpheli")
        print("NO_TRANSFER", flush=True)
        return False
    if not paribu_deposit_open(coin):
        tg("❌ Paribu yatırma kapalı")
        print("NO_TRANSFER", flush=True)
        return False

    # Hedef miktar → spot alım
    try:
        stp = step(spot)
        tck = tick(spot)
    except Exception as e:
        tg(f"❌ Symbol info hatası: {spot} | {e}")
        return False

    target = adj(TARGET_USDT / price(spot), stp)
    bought = Decimal(0)

    tg(f"💸 {coin} hedef {plain(target)}")
    while bought < target:
        need = (target - bought)
        qty  = (need // stp) * stp
        if qty <= 0:
            break
        try:
            lim = (price(spot) // tck) * tck
        except Exception:
            lim = price(spot)
        filled = spot_place_and_track(spot, qty, lim, wait_seconds=8)
        if filled > 0:
            bought += filled
            tg(f"✅ Spot dolum: +{plain(filled)} (toplam {plain(bought)}/{plain(target)})")
        else:
            tg("⚠️ Spot emir dolmadı, tekrar denenecek…")
            continue

    if bought <= 0:
        return False

    # Vadeli varsa hedge
    try:
        fut_syms = {s["symbol"] for s in client.futures_exchange_info()["symbols"]}
    except Exception:
        fut_syms = set()

    if fut in fut_syms:
        if not hedge_short(fut, coin, bought):
            tg("⚠️ Hedge başarısız, süreç sonlandı")
            return False
    else:
        tg("ℹ️ Bu coinin vadeli paritesi yok; hedge atlandı")

    # Çekim (başarılıysa TRANSFER_STARTED yazar, değilse NO_TRANSFER)
    ok = withdraw(withdraw_coin, binance_net, addr, bought, memo)
    if not ok:
        return False

    return True

# ───────────────────────────── Main ──────────────────────────────
if __name__ == "__main__":
    coin = sys.argv[1].upper() if len(sys.argv) > 1 else "LRC"
    print(f"[{time.strftime('%F %T')}] Başlıyor -> {coin}")
    ok = run(coin)
    print("Sonuç:", "BAŞARILI" if ok else "BAŞARISIZ")
