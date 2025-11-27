# -*- coding: utf-8 -*-
"""
PARIBU SATIŞ + SHORT KAPAT (güncel)
-----------------------------------
• Paribu cüzdandaki coini, Binance spot fiyatının %1 ÜSTÜ TL fiyattan LIMIT satışa koyar.
• 5 saniye içinde dolmazsa emri İPTAL eder (retry yok).
• Kısmi/Tam dolum kadar Binance USDT-M short pozisyonunu "reduceOnly MARKET" ile kapatır.
• Futures miktarı stepSize'a aşağı yuvarlanır (precision hatası yok).
• Telegram bilgilendirmeleri gönderir.

Kullanım:
    python paribu_satis_short_kapat.py COIN
Ör:
    python paribu_satis_short_kapat.py SHIB
"""
from __future__ import annotations

import os, sys, hmac, hashlib, time, base64, json
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any

import requests
from binance.client import Client
from dotenv import load_dotenv

# ────────────────────────── Ortam ──────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

PARIBU_API_KEY    = os.getenv("PARIBU_API_KEY")
PARIBU_API_SECRET = os.getenv("PARIBU_API_SECRET")
BINANCE_API_KEY   = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET= os.getenv("BINANCE_API_SECRET")
TG_TOKEN          = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")

if not all([PARIBU_API_KEY, PARIBU_API_SECRET, BINANCE_API_KEY, BINANCE_API_SECRET]):
    print("❌ .env eksik: PARIBU/BINANCE anahtarları zorunlu")
    sys.exit(1)

client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ────────────────────────── Telegram ───────────────────────
def tg(msg: str):
    """
    Telegram ulaşılamazsa asla crash etmez.
    Windows konsolda emoji/UTF-8 basarken çıkacak UnicodeEncodeError’ları da yutar.
    """
    try:
        if not TG_TOKEN or not TG_CHAT_ID:
            try:
                print("[TG]", msg)
            except Exception:
                # Windows cp1254 gibi konsollarda emoji patlamasın
                try:
                    print("[TG]", msg.encode("cp1254", "ignore").decode("cp1254"))
                except Exception:
                    print("[TG]", msg.encode("ascii", "ignore").decode("ascii"))
            return

        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        # kısa timeout + yeniden deneme YOK (bloklamasın)
        requests.post(
            url,
            json={"chat_id": TG_CHAT_ID, "text": msg},
            timeout=6,
        )
    except Exception as e:
        # Konsola güvenli bas
        try:
            print("[TG-HATA]", e, ">>", msg)
        except Exception:
            try:
                print("[TG-HATA]", e, ">>", msg.encode("cp1254", "ignore").decode("cp1254"))
            except Exception:
                print("[TG-HATA]", e, ">>", msg.encode("ascii", "ignore").decode("ascii"))

# ────────────────────────── Paribu API ─────────────────────
P_API = "https://api.paribu.com"
P_TICKER = "https://www.paribu.com/ticker"

def _p_signature(qs:str, body:str)->str:
    sig = hmac.new(PARIBU_API_SECRET.encode("utf-8"),
                   (qs+body).encode("utf-8"),
                   hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")

def p_headers(sig:str, extra:Dict[str,str]|None=None)->Dict[str,str]:
    h = {"Authorization": PARIBU_API_KEY, "X-Signature": sig, "Accept": "*/*"}
    if extra: h.update(extra)
    return h

def paribu_balance()->Dict[str, Decimal]:
    # Dönen yapı: {"BTC": Decimal(...), "ETH": Decimal(...), ...}
    try:
        sig = _p_signature("", "")
        r = requests.get(f"{P_API}/user/assets", headers=p_headers(sig), timeout=10)
        if r.status_code != 200: return {}
        js = r.json()
        out = {}
        for a in js:
            cur = str(a.get("currency","")).upper()
            av  = Decimal(str(a.get("available","0")))
            out[cur] = av
        return out
    except Exception:
        return {}

def paribu_create_limit_sell(pair:str, amount:Decimal, price:Decimal)->Dict[str,Any]:
    body_d = {
        "market": pair.lower(),
        "trade": "sell",
        "type": "limit",
        "amount": float(amount),
        "price": float(price),
        "total": float(amount*price)
    }
    body = json.dumps(body_d, separators=(',',':'))
    sig  = _p_signature("", body)
    try:
        r = requests.post(f"{P_API}/order", data=body,
                          headers=p_headers(sig, {"Content-Type":"application/json"}), timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            txt = r.text
            tg(f"⚠️ Paribu satış HTTP {r.status_code}: {txt[:300]}")
            return {}
    except Exception as e:
        tg(f"❌ Paribu satış hatası: {e}")
        return {}

def paribu_order_status(uid: str) -> dict:
    """
    Paribu emri için mümkün olan alanları döndürür.
    Return:
      {"state": "open|partial|filled|canceled|unknown",
       "remaining": Decimal|None, "executed": Decimal|None}
    """
    sig = _p_signature("", "")
    h   = p_headers(sig, {"Accept": "*/*"})
    paths = [f"/order/{uid}", f"/orders/{uid}", f"/order?uid={uid}"]
    for p in paths:
        try:
            r = requests.get(f"{P_API}{p}", headers=h, timeout=10)
            if r.status_code != 200:
                continue
            d = r.json() or {}
            state = (str(d.get("status") or d.get("state") or d.get("result") or "") or "unknown").lower()
            rem = d.get("remaining")
            exe = d.get("executed") or d.get("filled") or d.get("traded")
            try: rem = Decimal(str(rem)) if rem is not None else None
            except: rem = None
            try: exe = Decimal(str(exe)) if exe is not None else None
            except: exe = None

            # 'remaining' yoksa ama amount varsa hesapla
            if exe is None and rem is not None and d.get("amount") is not None:
                try:
                    amt = Decimal(str(d.get("amount")))
                    exe = (amt - rem) if rem is not None else None
                except: pass

            if rem is not None and rem == 0:
                state = "filled"
            return {"state": state, "remaining": rem, "executed": exe}
        except Exception:
            continue
    return {"state": "unknown", "remaining": None, "executed": None}

def paribu_cancel(uid: str) -> bool:
    """
    Paribu emrini iptal eder (öncelik: toplu iptal endpoint'i).
    Başarı ölçütü:
      - DELETE /orders  + body {"ids":[uid]} → HTTP 200 ve payload.deleted == True  (veya HTTP 200)
      - Fallback: DELETE /order  + body {"uid": uid}
      - Fallback: DELETE /order/{uid}  veya  DELETE /orders/{uid}
    Tüm denemeler ayrıntılı loglanır.
    """
    sig = _p_signature("", "")
    base_h = p_headers(sig, {"Accept": "*/*"})
    json_h = p_headers(sig, {"Content-Type": "application/json"})

    # 1) Ana yol: DELETE /orders   (bulk cancel)   body={"ids":[uid]}
    try:
        url = f"{P_API}/orders"
        r = requests.delete(url, headers=json_h, json={"ids": [uid]}, timeout=10)
        if r.status_code == 200:
            try:
                js = r.json() if r.text else {}
            except Exception:
                js = {}
            # Bazı cevaplarda payload.deleted gelebilir; bazılarında yalnızca 200 OK
            deleted = False
            try:
                deleted = bool(js.get("payload", {}).get("deleted", False))
            except Exception:
                deleted = False
            tg(f"✅ Paribu iptal (bulk) DELETE /orders HTTP 200; deleted={deleted}")
            return True
        else:
            tg(f"⚠️ Paribu iptal (bulk) {url} HTTP {r.status_code} body={r.text[:300]}")
    except Exception as e:
        tg(f"❌ Paribu iptal (bulk) hata: {e}")

    # 2) Fallback: DELETE /order   (tekil)  body={"uid": uid}
    try:
        url = f"{P_API}/order"
        r = requests.delete(url, headers=json_h, json={"uid": uid}, timeout=10)
        if r.status_code == 200:
            try:
                js = r.json() if r.text else {}
            except Exception:
                js = {}
            deleted = False
            try:
                deleted = bool(js.get("payload", {}).get("deleted", False))
            except Exception:
                deleted = False
            tg(f"✅ Paribu iptal (tekil) DELETE /order HTTP 200; deleted={deleted}")
            return True
        else:
            tg(f"⚠️ Paribu iptal (tekil) {url} HTTP {r.status_code} body={r.text[:300]}")
    except Exception as e:
        tg(f"❌ Paribu iptal (tekil) hata: {e}")

    # 3) Fallback: DELETE /order/{uid}  ve  /orders/{uid}
    for path in (f"/order/{uid}", f"/orders/{uid}"):
        try:
            url = f"{P_API}{path}"
            r = requests.delete(url, headers=base_h, timeout=10)
            if r.status_code == 200:
                tg(f"✅ Paribu iptal path DELETE {path} HTTP 200")
                return True
            else:
                tg(f"⚠️ Paribu iptal path {path} HTTP {r.status_code} body={r.text[:300]}")
        except Exception as e:
            tg(f"❌ Paribu iptal path hata ({path}): {e}")

    tg(f"❌ Paribu iptal başarısız (uid={uid})")
    return False


# ───────────────────── Binance Fiyat & Futures ─────────────
def bn_price(symbol:str)->Decimal:
    return Decimal(client.get_symbol_ticker(symbol=symbol)["price"])

def bn_price_usdttry()->Decimal:
    # Önce Binance USDTTRY; olmazsa Paribu USDT_TL 'last'
    try:
        return bn_price("USDTTRY")
    except Exception:
        try:
            j = requests.get(P_TICKER, timeout=5).json()
            return Decimal(str(j["USDT_TL"]["last"]))
        except Exception:
            raise RuntimeError("USDT/TRY fiyatı alınamadı")

def fut_symbol_and_multiplier(coin:str, coin_info:Dict[str,Any])->tuple[str, Decimal]:
    """
    coin_bilgileri.py'deki 'fut' alanını dikkate alır:
    1000SHIB -> sembol: 1000SHIBUSDT, multiplier: 1000
    Yoksa normal: coinUSDT, multiplier: 1
    """
    info = coin_info.get(coin.upper(), {})
    fut  = info.get("fut")
    if fut:
        head = ""
        for ch in fut:
            if ch.isdigit(): head += ch
            else: break
        mult = Decimal(head) if head else Decimal(1)
        return f"{fut}USDT", mult
    return f"{coin.upper()}USDT", Decimal(1)

def fut_step(symbol: str) -> Decimal:
    """
    Futures LOT adımını (stepSize) döndürür. Bulamazsa 1 döner.
    """
    try:
        info = client.futures_exchange_info()
        s = next((x for x in info["symbols"] if x["symbol"] == symbol), None)
        if not s:
            return Decimal("1")
        lot = next(f for f in s["filters"] if f["filterType"] == "LOT_SIZE")
        return Decimal(str(lot["stepSize"]))
    except Exception:
        return Decimal("1")

def fut_market_cover(symbol: str, qty: Decimal) -> bool:
    """
    reduceOnly MARKET BUY ile short kapatır.
    Miktarı futures stepSize'a aşağı yuvarlar; 0 çıkarsa kapatmaz.
    """
    try:
        client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
    except Exception:
        pass
    try:
        client.futures_change_leverage(symbol=symbol, leverage=1)
    except Exception:
        pass

    # ▶️ STEP düzeltmesi (kritik)
    step = fut_step(symbol)
    if step <= 0:
        step = Decimal("1")
    qty = (qty // step) * step  # aşağı yuvarla
    if qty <= 0:
        tg(f"ℹ️ Hedge kapama atlandı: {symbol} qty step'e yuvarlanınca 0 kaldı.")
        return False

    try:
        client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=str(qty),
            reduceOnly="true"
        )
        return True
    except Exception as e:
        tg(f"❌ Hedge kapama hatası: {e}")
        return False

# ⬇️⬇️⬇️ YENİ: Pozisyon okuma (CAP için)
def futures_position(symbol: str) -> Decimal:
    """Pozisyon miktarı (short ise negatif döner)."""
    try:
        data = client.futures_position_information(symbol=symbol)
        if data and isinstance(data, list):
            return Decimal(str(data[0].get("positionAmt", "0")))
    except Exception:
        pass
    return Decimal("0")

# ────────────────────────── Satış akışı ────────────────────
def quantize_price(p:Decimal)->Decimal:
    if p >= 100:  return p.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if p >= 10:   return p.quantize(Decimal("0.001"), rounding=ROUND_DOWN)
    if p >= 1:    return p.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    return p.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

def quantize_amount(a:Decimal)->Decimal:
    return a.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

def run(coin:str)->bool:
    from coin_bilgileri import coin_bilgi

    coin = coin.upper()
    # 1) Paribu bakiyesi (satılacak miktar) + snapshot (YENİ)
    bal = paribu_balance()
    have = bal.get(coin, Decimal("0"))
    if have <= 0:
        tg(f"ℹ️ Paribu'da {coin} bakiyesi yok. Satış atlanıyor.")
        return False
    bal_before = have  # ⬅️ snapshot eklendi

    # 2) Binance spot fiyatı * %1 üstü → TL satış limiti
    fut_sym, mult = fut_symbol_and_multiplier(coin, coin_bilgi)
    try:
        px_usdt = bn_price(fut_sym)  # spotla aynı sembol varsa onu kullanır
    except Exception:
        px_usdt = bn_price(f"{coin}USDT")
    usdttry  = bn_price_usdttry()
    sell_px  = px_usdt * usdttry * Decimal("1.01")
    sell_px  = quantize_price(sell_px)

    # 3) Limit satış emrini gir
    pair = f"{coin}_TL"
    fa   = quantize_amount(have)  # TÜM bakiye için emir
    tg(f"💸 PARIBU SATIŞ {coin}: {fa} @ {sell_px} TL  (Binance spot ×1.01)")
    od = paribu_create_limit_sell(pair, fa, sell_px)
    if not od:
        return False
    if od.get("code") == 1 or od.get("success") is False:
        tg(f"⚠️ Paribu satış reddedildi: {od}")
        return False
    uid = od.get("uid")
    if not uid:
        tg(f"⚠️ Paribu satış yanıtında uid yok: {od}")
        return False

    # 4) 5 sn izle → GERÇEK gerçekleşeni takip et
    t0 = time.time()
    filled_qty = Decimal("0")

    while time.time() - t0 < 5:
        info = paribu_order_status(uid)
        st   = info["state"]
        exe  = info["executed"]
        if exe is not None and exe > filled_qty:
            filled_qty = exe
        if st == "filled":
            break
        time.sleep(1)

    # 5) Süre dolduysa İPTAL (retry yok); sonra tekrar ne kadar gerçekleşmiş bak + snapshot farkı (YENİ)
    post_exec = Decimal("0")
    if time.time() - t0 >= 5:
        ok_cancel = paribu_cancel(uid)
        tg("⏹️ Satış emri 5 sn dolmadı → İPTAL " + ("✅" if ok_cancel else "⚠️ (iptal denemesi başarısız)"))
        post = paribu_order_status(uid)
        exe  = post["executed"]
        if exe is not None and exe > post_exec:
            post_exec = exe
        # Emir hâlâ açık ve gerçekleşme yoksa hedge kapatma YAPMA (güvenli)
        if post["state"] in ("open", "pending") and (exe is None or exe == 0):
            tg("ℹ️ Emir hâlâ açık görünüyor; satış gerçekleşmedi, hedge KAPATILMADI.")
            return True

    # ⬇️ YENİ: İptalden HEMEN SONRA bakiye snapshot → kısmi satış farkı
    bal_after_map = paribu_balance()
    bal_after = bal_after_map.get(coin, Decimal("0"))
    epsilon = Decimal("0.00000001")
    sold_diff = bal_before - bal_after
    if sold_diff < epsilon:
        sold_diff = Decimal("0")

    # Toplam gerçekten satılmış miktar: gözlenen executed’lar ile snapshot farkının maksimumu
    sold_final = max(filled_qty, post_exec, sold_diff)

    # 6) Yalnızca GERÇEKLEŞEN kadar short kapat (CAP + step fix)
    if sold_final > 0:
        close_qty = sold_final / mult   # 1000'li sözleşmeler için ölçek
        # Pozisyon aşımı koruması
        pos_amt = futures_position(fut_sym)  # short ise negatif
        if pos_amt < 0:
            max_cover = abs(pos_amt)
            if close_qty > max_cover:
                close_qty = max_cover
        ok = fut_market_cover(fut_sym, close_qty)
        tg(f"✅ Hedge kapama: {fut_sym} qty={close_qty}" + (" ✅" if ok else " ⚠️"))
    else:
        tg("ℹ️ Satış gerçekleşmedi → hedge kapatma yok")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python paribu_satis_short_kapat.py COIN")
        sys.exit(1)
    coin = sys.argv[1].upper()
    ok = run(coin)
    print("Bitti:", "BAŞARILI" if ok else "BAŞARISIZ")
