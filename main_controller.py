# main_controller.py
# Python 3.10+
"""Arbitraj ana döngüsü (v1.2)
--------------------------------
Binance ⇄ BTCTurk veya Paribu fiyat farkını izler
• Fark ≥ %THRESHOLD → Binance spot alım + hedge + transfer
• Coin hedef borsa cüzdana düştüğünde satış + short‑kapatma

Fiyat verileri **ticker_karsilastir.py** üzerinden gelir;
Paribu fiyatları için doğrudan API çağrısı yapılır.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal, getcontext
from typing import Dict

import requests

from ticker_karsilastir import (
    binance_ask_prices,   # {"BEAM": 0.0059, ...}
    btcturk_bid_prices,   # {"BEAM": 0.25, ...}
    usdt_try,             # float
)

# Paribu fiyatları için import kontrolü (opsiyonel)
try:
    from ticker_karsilastir import paribu_bid_prices
except ImportError:
    paribu_bid_prices = None
from coin_bilgileri import coin_bilgi                     # sabit coin listesi
from spot_hedge_transfer import spot_alim_hedge_transfer  # Binance işlemleri
from btcturk_satis_short_kapat import satis_ve_short_kapat  # Satış modülü
from spot_hedge_transfer import send_telegram             # Bildirim fonksiyonu

# ─────────────────────────── GENEL AYARLAR ───────────────────────────
getcontext().prec = 28
ARBITRAJ_THRESHOLD = Decimal("0.02")     # %2
COOLDOWN_SECONDS   = 600                  # 10 dk
TICK_INTERVAL      = 3                    # saniye
TARGET_EXCHANGE    = "BTCTurk"            # "BTCTurk" veya "Paribu"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__).info

# ─────────────────────────── DURUM TAKİBİ ───────────────────────────
last_buy_ts: Dict[str, float] = {}
pending_sale: set[str] = set()

# ─────────────────────────── FİYAT YARDIMCILARI ─────────────────────

def get_binance_prices() -> Dict[str, Decimal]:
    """ticker_karsilastir.ask → TL fiyat dict"""
    asks = binance_ask_prices()            # coin: ask USDT
    fx   = Decimal(usdt_try())             # USDTTRY
    return {c: Decimal(p) * fx for c, p in asks.items()}


def get_btcturk_prices() -> Dict[str, Decimal]:
    """ticker_karsilastir.bid → Decimal dict"""
    bids = btcturk_bid_prices()
    return {c: Decimal(p) for c, p in bids.items()}


def get_paribu_prices() -> Dict[str, Decimal]:
    """Paribu bid fiyatlarını alır (TL cinsinden)"""
    if paribu_bid_prices:
        bids = paribu_bid_prices()
        return {c: Decimal(p) for c, p in bids.items()}
    
    # Fallback: Paribu API'sinden direkt al
    try:
        r = requests.get("https://www.paribu.com/ticker", timeout=5)
        if r.status_code == 200:
            ticker_data = r.json()
            prices = {}
            for key, value in ticker_data.get("data", {}).items():
                if "_TRY" in key:
                    coin = key.replace("_TRY", "").upper()
                    # Paribu'da bid fiyatı genellikle 'last' veya 'highestBid' alanında
                    bid_price = value.get("highestBid") or value.get("last")
                    if bid_price:
                        prices[coin] = Decimal(str(bid_price))
            return prices
    except Exception as exc:
        log(f"⚠️  Paribu fiyat verisi çekilemedi: {exc}")
    
    return {}

# ─────────────────────────── ANA DÖNGÜ ──────────────────────────────

def arbitrage_cycle() -> None:
    try:
        bin_tl = get_binance_prices()
        if TARGET_EXCHANGE.lower() == "paribu":
            target_tl = get_paribu_prices()
            exchange_name = "Paribu"
        else:
            target_tl = get_btcturk_prices()
            exchange_name = "BTCTurk"
    except Exception as exc:  # pylint: disable=broad-except
        log(f"⚠️  Fiyat verisi çekilemedi: {exc} – {TICK_INTERVAL}s sonra tekrar")
        return

    now = time.time()
    log(f"—— Karşılaştırma ({exchange_name}) —————————————")

    for coin in coin_bilgi:  # ["BTC", "ETH", ...]
        # 1) Bekleyen satış/short kapama
        if coin in pending_sale:
            if satis_ve_short_kapat(coin):
                pending_sale.remove(coin)
                log(f"✅ {coin}: satış + short kapama tamamlandı")
            # aksi hâlde sonraki döngüde tekrar denenir

        # 2) Arbitraj kontrolü
        b_px = bin_tl.get(coin)
        t_px = target_tl.get(coin)
        if b_px is None or t_px is None:
            continue

        pct_diff = (t_px - b_px) / b_px
        log(
            f"{coin:<5} Binance ask {b_px:>12,.2f} ₺ | "
            f"{exchange_name} bid {t_px:>12,.2f} ₺ | Fark %{pct_diff * 100:+.2f}"
        )

        if pct_diff >= ARBITRAJ_THRESHOLD and now - last_buy_ts.get(coin, 0) >= COOLDOWN_SECONDS:
            log(f"🚀 {coin}: fark %{pct_diff * 100:.2f} – işlem akışı başlatılıyor ({exchange_name})")
            if spot_alim_hedge_transfer(coin, TARGET_EXCHANGE):
                last_buy_ts[coin] = now
                pending_sale.add(coin)
            else:
                log(f"❌ {coin}: Binance tarafı başarısız")
                send_telegram(f"❌ {coin}: Binance alım / transfer hatası ({exchange_name})")
                last_buy_ts[coin] = now  # Başarısız durumda da cooldown başlat

# ─────────────────────────── ÇALIŞTIRICI ────────────────────────────

def main() -> None:
    log("Arbitraj döngüsü başlıyor … Ctrl+C ile durdurabilirsiniz")
    try:
        while True:
            arbitrage_cycle()
            time.sleep(TICK_INTERVAL)
    except KeyboardInterrupt:
        log("⏹️  Manuel durdurma — çıkılıyor")
        send_telegram("Arbitraj botu manuel olarak durduruldu")


if __name__ == "__main__":
    main()
