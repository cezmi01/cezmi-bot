from __future__ import annotations

import logging
import time
from decimal import Decimal, getcontext
from typing import Dict

from ticker_karsilastir import (
    binance_ask_prices,   # {"BEAM": 0.0059, ...}
    btcturk_bid_prices,   # {"BEAM": 0.25, ...}
    usdt_try,             # float
)
from coin_bilgileri import coin_bilgi                     # sabit coin listesi
from spot_hedge_transfer import spot_alim_hedge_transfer  # Binance işlemleri
from btcturk_satis_short_kapat import satis_ve_short_kapat  # Satış modülü
from spot_hedge_transfer import send_telegram             # Bildirim fonksiyonu

# ─────────────────────────── GENEL AYARLAR ───────────────────────────
getcontext().prec = 28
ARBITRAJ_THRESHOLD = Decimal("0.02")     # %2
COOLDOWN_SECONDS   = 600                  # 10 dk
TICK_INTERVAL      = 3                    # saniye
COOLDOWN_MINUTES   = COOLDOWN_SECONDS // 60

_SUCCESS_STRINGS = {"ok", "success", "true", "done", "1"}

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

# ─────────────────────────── İŞLEM YARDIMCILARI ─────────────────────

def _coerce_success_flag(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _SUCCESS_STRINGS
    return bool(value)


def _normalize_spot_result(result: object) -> tuple[bool, str]:
    if isinstance(result, tuple) and len(result) >= 2:
        success, reason = result[0], result[1]
        return bool(success), str(reason or "").strip()

    if isinstance(result, dict):
        success = (
            result.get("success")
            or result.get("ok")
            or result.get("status")
        )
        reason = result.get("reason") or result.get("error") or ""
        return _coerce_success_flag(success), str(reason).strip()

    if isinstance(result, str):
        normalized = result.strip()
        if normalized.lower() in _SUCCESS_STRINGS:
            return True, ""
        return False, normalized

    return bool(result), ""


def _run_spot_flow(coin: str) -> tuple[bool, str]:
    try:
        outcome = spot_alim_hedge_transfer(coin)
    except Exception as exc:  # pylint: disable=broad-except
        return False, str(exc)
    return _normalize_spot_result(outcome)


def _should_apply_failure_cooldown(reason: str) -> bool:
    if not reason:
        return False
    text = reason.lower()
    no_balance = (
        ("bakiye" in text and ("yok" in text or "yetersiz" in text))
        or ("insufficient" in text and ("balance" in text or "funds" in text))
    )
    pair_issue = any(keyword in text for keyword in ("parite", "pair", "symbol"))
    return no_balance or pair_issue


def _apply_failure_cooldown(coin: str, reason: str) -> None:
    last_buy_ts[coin] = time.time()
    pretty_reason = reason or "sebep unspecified"
    log(
        f"⏸️ {coin}: hata nedeniyle {COOLDOWN_MINUTES} dk cooldown "
        f"(neden: {pretty_reason})"
    )

# ─────────────────────────── ANA DÖNGÜ ──────────────────────────────

def arbitrage_cycle() -> None:
    try:
        bin_tl = get_binance_prices()
        btc_tl = get_btcturk_prices()
    except Exception as exc:  # pylint: disable=broad-except
        log(f"⚠️  Fiyat verisi çekilemedi: {exc} – {TICK_INTERVAL}s sonra tekrar")
        return

    now = time.time()
    log("—— Karşılaştırma —————————————")

    for coin in coin_bilgi:  # ["BTC", "ETH", ...]
        # 1) Bekleyen satış/short kapama
        if coin in pending_sale:
            if satis_ve_short_kapat(coin):
                pending_sale.remove(coin)
                log(f"✅ {coin}: satış + short kapama tamamlandı")
            # aksi hâlde sonraki döngüde tekrar denenir

        # 2) Arbitraj kontrolü
        b_px = bin_tl.get(coin)
        t_px = btc_tl.get(coin)
        if b_px is None or t_px is None:
            continue

        pct_diff = (t_px - b_px) / b_px
        log(
            f"{coin:<5} Binance ask {b_px:>12,.2f} ₺ | "
            f"BTCTurk bid {t_px:>12,.2f} ₺ | Fark %{pct_diff * 100:+.2f}"
        )

        if pct_diff >= ARBITRAJ_THRESHOLD and now - last_buy_ts.get(coin, 0) >= COOLDOWN_SECONDS:
            log(f"🚀 {coin}: fark %{pct_diff * 100:.2f} – işlem akışı başlatılıyor")
            success, fail_reason = _run_spot_flow(coin)
            if success:
                last_buy_ts[coin] = time.time()
                pending_sale.add(coin)
            else:
                suffix = f" ({fail_reason})" if fail_reason else ""
                log(f"❌ {coin}: Binance tarafı başarısız{suffix}")
                send_telegram(f"❌ {coin}: Binance alım / transfer hatası{suffix}")
                if _should_apply_failure_cooldown(fail_reason):
                    _apply_failure_cooldown(coin, fail_reason)

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
