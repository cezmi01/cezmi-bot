# -*- coding: utf-8 -*-
"""
PARIBU ↔ BINANCE — Ticker Karşılaştırma (+ OB ≥ 20.000 TL koşulu)
-----------------------------------------------------------------
• get_uygun_coinler()
    ↳ Binance-Paribu fiyat farkını hesaplar
    ↳ Fark ≥ %2 VE Paribu orderbook'ta **best bid TL ≥ 20.000** ise coin’i listeye ekler
    ↳ Aynı coin için 10 dk cooldown vardır.

• Debug modu: dosyayı doğrudan çalıştır (python ticker_karsilastir.py)
    ↳ Her 10 sn’de coinlerin farkı + best bid TL + uygun liste basılır.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List

import requests

# ───────────── İzlenecek coin listesi ─────────────
SYMBOLS: List[str] = [
    "AAVE","ADA","AIXBT","ALGO","BCH","ANKR","APE","API3","APT","ARB","ARKM","BEAM",
    "ATOM","AVAX","AXL","AXS","BAND","BAT","BLUR","COW","BONK","COMP",
    "CRV","DYDX","CTSI","ZIL","DOGE","DOT","EIGEN","ENA","ENS","ETH","ETHFI","SUI",
    "FET","FIL","FLOKI","ICP","GALA","GLM","GOAT","GRT","XAI","HOT","IMX",
    "INJ","IO","JASMY","JTO","JUP","KAITO","MANTA","VET","LINK","LDO","LPT",
    "LRC","LTC","MAGIC","MANA","MEME","MKR","MOVE","NMR","VANRY","CHZ","ZRX",
    "OXT","ME","OGN","TNSR","T","NEO","OP","ONDO","ONT","JOE","PEPE","PNUT",
    "POL","PENGU","PYTH","QNT","ILV","RLC","W","WIF","WLD","XLM","XRP","XTZ",
    "IOTA","RENDER","S","SAND","SHIB","SKL","SOL","SPELL","STX","STRK","STORJ",
    "THETA","TLM","SNX","TIA","TON","TRUMP","TRX","UMA","UNI","MINA","VIRTUAL","ZK",
    "ZRO","TURBO","SYN","LAYER","MASK","1INCH","A","AEVO","ALICE","ALT","BERA","DYM",
    "MORPHO","PENDLE","RAY","RDNT","RVN","SEI","STG","SAHARA","2Z","SUPER","AVNT","BIO",
    "SKY","LINEA","WLFI","PUMP","SPK","ZKC","NEAR","TAO","FF"
]

# ───────────── Sabitler ─────────────
PARIBU_TICKER_URL   = "https://web.paribu.com/ticker"
PARIBU_ORDERBOOK_URL = "https://web.paribu.com/market/{symbol}_tl/orderbook"
BINANCE_TICKER_URL  = "https://api.binance.com/api/v3/ticker/price"

THRESHOLD = 0.02            # %2
BUY_TL_LIMIT = 50000.0      # best bid TL eşiği
BINANCE_SYMBOL_MAP: Dict[str, str] = {"BEAM": "BEAMXUSDT"}

_last_triggered: Dict[str, datetime] = {}

# ───────────── Yardımcılar ─────────────

def _usdt_try(prices: Dict[str, float]) -> float:
    """USDT/TRY kuru; USDTTRY yoksa TRYUSDT tersini kullan."""
    if (val := prices.get("USDTTRY")):
        return val
    if (val := prices.get("TRYUSDT")):
        return 1.0 / val if val else 0.0
    raise RuntimeError("USDT/TRY kuru alınamadı")

def _paribu_top_buy_tl(sym: str) -> float:
    """
    Paribu orderbook'tan **best bid** kademesinin TL karşılığını döndürür.
    API: https://web.paribu.com/market/{sym}_tl/orderbook
    Yapı: {"payload":{"buy": {"78.50":"120.0", ..., "80.46":"854.295"}}}
          En iyi alıcı **en alttaki** (fiyatı en yüksek) kademedir.
    """
    try:
        url = PARIBU_ORDERBOOK_URL.format(symbol=sym.lower())
        j = requests.get(url, timeout=10).json()
        buy = j.get("payload", {}).get("buy", {})
        if not isinstance(buy, dict) or not buy:
            return 0.0

        # en yüksek fiyatlı (best bid) kademeyi bul
        best_price: Decimal | None = None
        best_qty: Decimal = Decimal("0")

        for p_str, q_str in buy.items():
            try:
                p = Decimal(str(p_str))      # fiyat string → Decimal
                q = Decimal(str(q_str))      # adet string → Decimal
            except Exception:
                continue
            if best_price is None or p > best_price:
                best_price = p
                best_qty = q

        if best_price is None:
            return 0.0
        return float(best_price * best_qty)   # TL karşılığı
    except Exception as e:
        print(f"[orderbook HATA {sym}] {e}", flush=True)
        return 0.0

# ───────────── Ana Fonksiyon ─────────────

def get_uygun_coinler() -> List[str]:
    """%2’den büyük fark ve best bid TL ≥ 20.000 olan coin listesini verir."""
    uygun: List[str] = []
    try:
        # Binance fiyatları + USDT kuru
        b_prices = {d["symbol"]: float(d["price"])
                    for d in requests.get(BINANCE_TICKER_URL, timeout=10).json()}
        usdt_try = _usdt_try(b_prices)

        p_data = requests.get(PARIBU_TICKER_URL, timeout=10).json()
        now = datetime.now()

        for key, pdata in p_data.items():
            sym = key[:-3].upper()            # "ADA_TL" -> "ADA"
            if sym not in SYMBOLS:
                continue
            if sym in _last_triggered and now - _last_triggered[sym] < timedelta(minutes=10):
                continue

            paribu_bid = float(pdata.get("highestBid", 0) or 0)
            b_sym      = BINANCE_SYMBOL_MAP.get(sym, f"{sym}USDT")
            b_tl       = b_prices.get(b_sym, 0.0) * usdt_try
            if not b_tl:
                continue

            fark = (paribu_bid - b_tl) / b_tl
            if fark >= THRESHOLD:
                top_buy_tl = _paribu_top_buy_tl(sym)
                if top_buy_tl >= BUY_TL_LIMIT:
                    uygun.append(sym)
                    _last_triggered[sym] = now
                # limit altı ise ekleme yok (cooldown yazmıyoruz)

    except Exception as err:
        print("[get_uygun_coinler HATA]", err, flush=True)

    return uygun

# ───────────── Debug Modu ─────────────
if __name__ == "__main__":
    while True:
        try:
            b_prices = {d["symbol"]: float(d["price"])
                        for d in requests.get(BINANCE_TICKER_URL, timeout=10).json()}
            usdt_try = _usdt_try(b_prices)
            p_data   = requests.get(PARIBU_TICKER_URL, timeout=10).json()

            print("\n──── Yeni Döngü ────", datetime.now().strftime("%H:%M:%S"))
            uygun_dbg: List[str] = []

            for key, pdata in p_data.items():
                sym = key[:-3].upper()
                if sym not in SYMBOLS:
                    continue

                paribu_bid = float(pdata.get("highestBid", 0) or 0)
                b_sym      = BINANCE_SYMBOL_MAP.get(sym, f"{sym}USDT")
                b_tl       = b_prices.get(b_sym, 0.0) * usdt_try
                if not b_tl:
                    continue

                fark = (paribu_bid - b_tl) / b_tl

                # yalnız fark eşiğini geçenler için OB çek → API yükünü azalt
                ob_tl = _paribu_top_buy_tl(sym) if fark >= THRESHOLD else 0.0

                print(f"{sym:<6} Bn:{b_tl:>10.2f}₺ | Pb(hBid):{paribu_bid:>10.2f}₺ | "
                      f"Δ%:{fark*100:+.2f} | Ob(best):{ob_tl:>10.2f} TL")

                if fark >= THRESHOLD:
                    if ob_tl >= BUY_TL_LIMIT:
                        uygun_dbg.append(sym)
                    else:
                        print(f"↳ SKIP {sym}: best bid TL {ob_tl:,.0f} < {BUY_TL_LIMIT:,.0f}")

            print("Uygun coinler →", uygun_dbg, flush=True)

        except Exception as dbg_err:
            print("[DEBUG döngü hatası]", dbg_err, flush=True)
        time.sleep(10)
