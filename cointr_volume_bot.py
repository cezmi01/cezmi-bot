# -*- coding: utf-8 -*-
"""
CoinTR TRY Hacim Alarm Botu (10M TL altı filtre + boş symbol fix)
-----------------------------------------------------------------
- CoinTR'deki TÜM TRY spot pariteleri için:
    * 24h TRY hacmi (quoteVolume) 10.000.000 TL'nin ALTINDA olanları seçer.
    * Bu paritelerde 1m ve 15m mum hacmini takip eder.
    * Hacim, bir önceki muma göre artarsa Telegram'a bildirim gönderir.
    * Aynı mum için birden fazla alarm göndermez.
- Rate limit (429) yememek için:
    * Mum istekleri SIRAYLA atılır, her sembol arası küçük bekleme vardır.
- 40019 "Parameter symbol cannot be empty" almamak için:
    * Boş / None semboller hiçbir aşamada işlenmez.
"""

import os
import asyncio
import time
from decimal import Decimal
from typing import Dict, Tuple, List, Any

import aiohttp
from dotenv import load_dotenv
from telegram import Bot

# .env yükle
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINTR_BASE_URL = os.getenv("COINTR_BASE_URL", "https://api.cointr.com")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise SystemExit("❌ TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID .env içinde tanımlı değil!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

DAILY_QUOTE_VOL_LIMIT = Decimal("10000000")  # 10 milyon TRY

# (symbol, interval_label) -> last_ts
last_alerted_candle: Dict[Tuple[str, str], int] = {}


# ─────────────────────────────────────────
# Genel HTTP helper (rate-limit friendly)
# ─────────────────────────────────────────

async def fetch_json(session: aiohttp.ClientSession, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Basit GET + JSON helper.
    - 429 (Too Many Requests) gelirse retry yapmaz, boş döner.
    - Diğer hatalarda az sayıda retry yapar.
    """
    for attempt in range(3):
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                text = await resp.text()

                # Rate limit
                if resp.status == 429:
                    print(f"HTTP 429 (Too Many Requests): {url} -> {text[:200]}")
                    return {}

                if resp.status != 200:
                    print(f"HTTP {resp.status} Hatası: {url} -> {text[:200]}")
                    await asyncio.sleep(1)
                    continue

                try:
                    return await resp.json()
                except Exception as e:
                    print(f"[fetch_json] JSON parse hatası: {e} -> {text[:200]}")
                    await asyncio.sleep(1)
                    continue

        except Exception as e:
            print(f"[fetch_json] İstek hatası (attempt {attempt+1}/3): {e}")
            await asyncio.sleep(1)

    return {}


# ─────────────────────────────────────────
# CoinTR: TRY sembollerini çek
# ─────────────────────────────────────────

async def get_try_symbols(session: aiohttp.ClientSession) -> List[str]:
    """
    /api/v2/spot/public/symbols
    quoteCoin'i TRY olan, status'u 'online' olan ve symbol alanı BOŞ OLMAYAN pariteleri çeker.
    """
    url = f"{COINTR_BASE_URL}/api/v2/spot/public/symbols"
    data = await fetch_json(session, url)

    symbols: List[str] = []
    rows = data.get("data") or []

    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        quote = (row.get("quoteCoin") or "").strip()
        status = (row.get("status") or "").strip()

        # symbol boşsa direkt atla
        if not symbol:
            continue

        if quote == "TRY" and status == "online":
            symbols.append(symbol)

    print(f"Toplam TRY paritesi (online, boş olmayan symbol): {len(symbols)}")
    return symbols


# ─────────────────────────────────────────
# CoinTR: 24h ticker verisi (hacim filtresi için)
# ─────────────────────────────────────────

async def get_24h_tickers(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """
    /api/v2/spot/market/tickers
    Tüm spot paritelerin 24h ticker verisini çeker.
    Dönüş: {symbol: ticker_dict}
    """
    url = f"{COINTR_BASE_URL}/api/v2/spot/market/tickers"
    data = await fetch_json(session, url)

    tickers_by_symbol: Dict[str, Dict[str, Any]] = {}
    rows = data.get("data") or []

    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue
        tickers_by_symbol[symbol] = row

    print(f"Ticker verisi gelen sembol sayısı: {len(tickers_by_symbol)}")
    return tickers_by_symbol


def parse_decimal(raw: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal(default)


# ─────────────────────────────────────────
# CoinTR: Candlestick (mum) verisi
# ─────────────────────────────────────────

async def get_klines(
    session: aiohttp.ClientSession,
    symbol: str,
    granularity: str,
    limit: int = 2
) -> List[List[str]]:
    """
    GET /api/v2/spot/market/candles
    Response: [ [ts, open, high, low, close, baseVol, quoteVol, usdtVol], ... ]
    ts = index[0], hacim (base) = index[5]
    """
    symbol = (symbol or "").strip()
    if not symbol:
        # Buraya geldiğinde asla boş sembolle API'ye istek atma
        print(f"[get_klines] Boş sembol, istek atılmadı. granularity={granularity}")
        return []

    url = f"{COINTR_BASE_URL}/api/v2/spot/market/candles"
    params = {
        "symbol": symbol,
        "granularity": granularity,
        "limit": str(limit)
    }

    data = await fetch_json(session, url, params=params)
    candles = data.get("data") or []

    if not candles:
        return []

    try:
        candles = sorted(candles, key=lambda c: int(c[0]))
    except Exception:
        pass

    return candles[-limit:]


# ─────────────────────────────────────────
# Telegram helper
# ─────────────────────────────────────────

async def send_telegram_message(text: str) -> None:
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, bot.send_message, TELEGRAM_CHAT_ID, text
        )
        print(f"[TG] Gönderildi: {text.splitlines()[0][:50]}...")
    except Exception as e:
        print(f"[TG] Mesaj gönderilemedi: {e}")


# ─────────────────────────────────────────
# Hacim kontrol mantığı
# ─────────────────────────────────────────

async def check_symbol_volume(
    session: aiohttp.ClientSession,
    symbol: str,
    interval_label: str,
    granularity: str
):
    """
    Tek bir sembol için:
    - 1m veya 15m mumlarını çeker (limit=2)
    - Son mumun hacmi, bir önceki mumdan yüksekse alarm yollar.
    """
    global last_alerted_candle

    symbol = (symbol or "").strip()
    if not symbol:
        # Güvenlik: Boş sembolle asla işlem yapma
        print(f"[check_symbol_volume] Boş sembol, atlanıyor. interval={interval_label}")
        return

    candles = await get_klines(session, symbol, granularity, limit=2)
    if len(candles) < 2:
        return

    prev_candle = candles[-2]
    last_candle = candles[-1]

    try:
        last_ts = int(last_candle[0])
        prev_vol = parse_decimal(prev_candle[5])
        last_vol = parse_decimal(last_candle[5])
    except Exception as e:
        print(f"[{symbol} {interval_label}] Candle parse hatası: {e} -> {prev_candle} / {last_candle}")
        return

    key = (symbol, interval_label)

    # Aynı mum için tekrar alarm atmayı engelle
    if last_alerted_candle.get(key) == last_ts:
        return

    # Hacim artışı varsa
    if last_vol > prev_vol and prev_vol > 0:
        try:
            ratio = (last_vol / prev_vol).quantize(Decimal("0.01"))
        except Exception:
            ratio = Decimal("0")

        text = (
            f"📈 CoinTR Hacim Artışı ({interval_label})\n"
            f"Sembol: {symbol}\n"
            f"Önceki Hacim: {prev_vol}\n"
            f"Son Hacim: {last_vol}\n"
            f"Artış Oranı: x{ratio}"
        )
        await send_telegram_message(text)
        last_alerted_candle[key] = last_ts


# ─────────────────────────────────────────
# Ana döngü
# ─────────────────────────────────────────

async def volume_watcher():
    async with aiohttp.ClientSession() as session:
        # 1) TRY paritelerini çek
        all_try_symbols = await get_try_symbols(session)
        if not all_try_symbols:
            print("❌ Hiç TRY paritesi bulunamadı. API değişmiş ya da erişilemiyor olabilir.")
            return

        # 2) 24h ticker verisini çek
        tickers = await get_24h_tickers(session)
        if not tickers:
            print("❌ Ticker verisi alınamadı, hacim filtresi yapılamıyor.")
            return

        # 3) 24h TRY hacmi 10M TL'nin ALTINDA olan TRY paritelerini filtrele
        filtered_symbols: List[str] = []
        for sym in all_try_symbols:
            sym = (sym or "").strip()
            if not sym:
                continue

            t = tickers.get(sym)
            if not t:
                continue

            quote_vol = parse_decimal(t.get("quoteVolume", "0"))
            if quote_vol < DAILY_QUOTE_VOL_LIMIT:
                filtered_symbols.append(sym)

        print(f"Filtreli semboller (24h TRY hacmi < {DAILY_QUOTE_VOL_LIMIT}): {len(filtered_symbols)}")
        print(filtered_symbols)

        if not filtered_symbols:
            print("⚠ 10M TL altında hacmi olan TRY paritesi yok, bot izleyecek sembol bulamadı.")
            return

        await send_telegram_message(
            f"✅ CoinTR TRY Hacim Alarm Botu Başladı.\n"
            f"Filtre: 24h TRY hacmi < {DAILY_QUOTE_VOL_LIMIT}₺\n"
            f"İzlenen sembol sayısı: {len(filtered_symbols)}"
        )

        last_1m_check = 0
        last_15m_check = 0

        # Her sembol arası bekleme (rate limit için)
        per_symbol_sleep = 0.2  # saniye

        while True:
            now = int(time.time())
            do_1m = False
            do_15m = False

            if now - last_1m_check >= 60:
                last_1m_check = now
                do_1m = True
                print("⏱ 1m mumlar kontrol ediliyor...")

            if now - last_15m_check >= 900:
                last_15m_check = now
                do_15m = True
                print("⏱ 15m mumlar kontrol ediliyor...")

            if not (do_1m or do_15m):
                await asyncio.sleep(1)
                continue

            # Sembolleri SIRAYLA tara (async task yağmuru yok)
            for sym in filtered_symbols:
                sym = (sym or "").strip()
                if not sym:
                    continue

                if do_1m:
                    await check_symbol_volume(session, sym, "1m", "1min")
                if do_15m:
                    await check_symbol_volume(session, sym, "15m", "15min")

                # Her sembol arasında kısa uyku -> rate limit dostu
                await asyncio.sleep(per_symbol_sleep)

            await asyncio.sleep(1)


# ─────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(volume_watcher())
    except KeyboardInterrupt:
        print("👋 Çıkılıyor...")
