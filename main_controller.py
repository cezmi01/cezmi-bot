# -*- coding: utf-8 -*-
"""
MAIN CONTROLLER – Binance→Hedge→Transfer → (opsiyonel) Paribu Satış & Short Kapat
---------------------------------------------------------------------------------
• Uygun coinleri ticker_karsilastir.get_uygun_coinler() ile bulur.
• Her uygun coin için binance_spot_hedge.py'yi tetikler (spot+hedge+transfer).
• AUTO_SELL=1 ise: Paribu bakiyesinde coin'in gelmesini bekler ve
  paribu_satis_short_kapat.py'yi çağırır (Binance spot fiyatının %1 üstü – 5sn dolmazsa iptal).
• Telegram bildirimleri opsiyonel (TELEGRAM_BOT_TOKEN/CHAT_ID).
• /start–/stop kontrolü için controller_state.json (telegram_control.py ile uyumlu).

ENV değişkenleri (önerilen):
COOLDOWN_MINUTES=10
LOOP_SLEEP_SEC=5
AUTO_SELL=0                   # 0/1
SELL_WAIT_MAX_SEC=900         # Paribu'ya geliş için azami bekleme
SELL_POLL_SEC=15
MIN_ARRIVAL_RATIO=0.98        # beklenenin %98'i geldiyse "geldi" say
USE_TELEGRAM_CONTROL=1        # controller_state.json dosyasını dinle
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=1452905980
PARIBU_API_KEY=xxx            # AUTO_SELL=1 ise gerekli
PARIBU_API_SECRET=xxx
"""

from __future__ import annotations
import os, sys, time, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
import hmac, hashlib, base64
import requests
from dotenv import load_dotenv

# ───────────────────────────── Setup ─────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

from ticker_karsilastir import get_uygun_coinler  # mevcut dosyan
HEDGE_SCRIPT = BASE_DIR / "binance_spot_hedge.py"
SELL_SCRIPT  = BASE_DIR / "paribu_satis_short_kapat.py"

# ENV
def _get_int(k, d):
    try:
        return int(os.getenv(k, d))
    except:
        return d

def _get_float(k, d):
    try:
        return float(os.getenv(k, d))
    except:
        return d

COOLDOWN_MINUTES    = _get_int("COOLDOWN_MINUTES", 10)
LOOP_SLEEP_SEC      = _get_int("LOOP_SLEEP_SEC", 5)
AUTO_SELL           = _get_int("AUTO_SELL", 0) == 1
SELL_WAIT_MAX_SEC   = _get_int("SELL_WAIT_MAX_SEC", 900)
SELL_POLL_SEC       = _get_int("SELL_POLL_SEC", 15)
MIN_ARRIVAL_RATIO   = Decimal(str(_get_float("MIN_ARRIVAL_RATIO", 0.98)))
USE_TG_CONTROL      = _get_int("USE_TELEGRAM_CONTROL", 1) == 1
STATE_FILE          = str(BASE_DIR / "controller_state.json")

TG_TOKEN            = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID          = os.getenv("TELEGRAM_CHAT_ID")

PARIBU_API_KEY      = os.getenv("PARIBU_API_KEY")
PARIBU_API_SECRET   = os.getenv("PARIBU_API_SECRET")

# ───────────────────────── Telegram helper ───────────────────────
def tg(msg: str):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[TG]", msg)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": msg},
            timeout=10,
        )
    except Exception as e:
        print("[TG-HATA]", e, ">>", msg)

# ───────────────────── Controller state (start/stop) ─────────────
def is_enabled() -> bool:
    if not USE_TG_CONTROL:
        return True
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("enabled", True))
    except Exception:
        pass
    return True

# ─────────────────────── Paribu balance helpers ──────────────────
P_API = "https://api.paribu.com"

def _p_signature(qs: str, body: str) -> str:
    sig = hmac.new(
        (PARIBU_API_SECRET or "").encode("utf-8"),
        (qs + body).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")

def _p_headers(sig: str, extra: dict | None = None) -> dict:
    h = {"Authorization": PARIBU_API_KEY or "", "X-Signature": sig, "Accept": "*/*"}
    if extra:
        h.update(extra)
    return h

def paribu_balance_map() -> dict[str, Decimal]:
    """
    {"BTC": Decimal(...), "ETH": Decimal(...), ...}
    AUTO_SELL=1 ise PARIBU API anahtarları gerekli.
    """
    if not (PARIBU_API_KEY and PARIBU_API_SECRET):
        return {}
    try:
        sig = _p_signature("", "")
        r = requests.get(f"{P_API}/user/assets", headers=_p_headers(sig), timeout=15)
        if r.status_code != 200:
            return {}
        js = r.json()
        out = {}
        for a in js:
            cur = str(a.get("currency", "")).upper()
            av = Decimal(str(a.get("available", "0")))
            out[cur] = av
        return out
    except Exception:
        return {}

# ───────────────────────── Hedge trigger ─────────────────────────
def run_subprocess(script: Path, args: list[str]) -> tuple[int, str, str]:
    """
    script'i alt süreçte çalıştırır, stdout/stderr döner.
    """
    try:
        p = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=None,
            check=False,
        )
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", f"{e}"

# ───────────────────────── Auto-sell watcher ─────────────────────
def wait_and_autosell(coin: str) -> None:
    """
    AUTO_SELL=1 ise çağrılır:
    - Başlangıç Paribu bakiyesini alır
    - SELL_WAIT_MAX_SEC boyunca coin bakiyesinin (start + TARGET*ratio) seviyesine çıkmasını bekler
    - Gelirse paribu_satis_short_kapat.py coin çağrılır
    NOT: HEDGE script'i, satın alınan net miktarı dışarı yazmıyor; bu yüzden
    burada "artış oldu mu?" mantığıyla bakıyoruz. Minimum artış eşiği olarak
    MIN_ARRIVAL_RATIO * (elde edilen varsayılan miktar) yerine, pratik bir yaklaşım:
    → Bakiyede en az %1'lik artış gör (çok küçük dust artışlarını yoksay).
    """
    if not (PARIBU_API_KEY and PARIBU_API_SECRET):
        tg(f"ℹ️ AUTO_SELL aktif ama Paribu API anahtarları yok; satış tetiklenmedi ({coin}).")
        return

    start_balances = paribu_balance_map()
    start_amt = start_balances.get(coin.upper(), Decimal("0"))
    min_delta = (start_amt * Decimal("0.01")) + Decimal("0.00000001")  # en az %1 artış (dust filtre)

    tg(f"⏳ {coin} Paribu’ya geliş bekleniyor (max {SELL_WAIT_MAX_SEC}s)…")
    waited = 0
    while waited < SELL_WAIT_MAX_SEC:
        time.sleep(SELL_POLL_SEC)
        waited += SELL_POLL_SEC
        cur = paribu_balance_map().get(coin.upper(), Decimal("0"))
        if cur - start_amt >= min_delta:
            tg(f"✅ {coin} geldi: {cur} (başlangıç {start_amt}) → satış tetikleniyor")
            rc, out, err = run_subprocess(SELL_SCRIPT, [coin.upper()])
            if out:
                print(f"[SELL-OUT {coin}]\n{out}")
            if err:
                print(f"[SELL-ERR {coin}]\n{err}")
            if rc == 0:
                tg(f"💰 {coin} satış/hedge-kapat komutu gönderildi.")
            else:
                tg(f"❌ {coin} satış komutu hata kodu: {rc}")
            return

    tg(f"⚠️ {coin} Paribu’ya beklenen sürede ulaşmadı; satış tetiklenmedi.")

# ───────────────────────────── Main loop ──────────────────────────
def main():
    print("Main Controller başladı – Ctrl+C ile durdurabilirsiniz.")
    tg("🟢 Main Controller başladı")

    cooldown = timedelta(minutes=COOLDOWN_MINUTES)
    last_run: dict[str, datetime] = {}
    in_progress: set[str] = set()

    while True:
        try:
            # /stop ile dur-kalk
            if not is_enabled():
                time.sleep(3)
                continue

            uygunlar = get_uygun_coinler() or []
            now = datetime.now()
            print(f"{now:%H:%M:%S} – Uygun: {uygunlar}", flush=True)

            for sym in uygunlar:
                sym = sym.upper()
                if sym in in_progress:
                    continue
                if sym in last_run and now - last_run[sym] < cooldown:
                    continue

                print(f">> {sym}: hedge/transfer tetikleniyor…", flush=True)
                tg(f"▶️ {sym}: hedge/transfer başlatılıyor")

                in_progress.add(sym)
                rc, out, err = run_subprocess(HEDGE_SCRIPT, [sym])

                if out:
                    print(f"[HEDGE-OUT {sym}]\n{out}")
                if err:
                    print(f"[HEDGE-ERR {sym}]\n{err}")

                # Marker: transfer gerçekten başlatıldı mı?
                transfer_started = ("TRANSFER_STARTED" in (out or "")) and ("NO_TRANSFER" not in (out or ""))

                if rc == 0 and transfer_started:
                    tg(f"✅ {sym}: hedge/transfer tamamlandı (çekim başlatıldı)")
                    if AUTO_SELL:
                        try:
                            wait_and_autosell(sym)
                        except Exception as e:
                            tg(f"❌ AUTO_SELL hata: {e}")
                elif rc == 0 and not transfer_started:
                    tg(f"ℹ️ {sym}: Hedge tamamlandı ama çekim BAŞLAMADI — AUTO_SELL atlandı.")
                else:
                    tg(f"❌ {sym}: hedge/transfer komutu hata kodu {rc}")

                last_run[sym] = datetime.now()
                in_progress.discard(sym)

            time.sleep(LOOP_SLEEP_SEC)

        except KeyboardInterrupt:
            tg("⏹️ Main Controller durduruldu (KeyboardInterrupt)")
            print("\nDurduruldu.")
            break
        except Exception as e:
            print(f"[main_loop HATA] {e}", flush=True)
            time.sleep(LOOP_SLEEP_SEC)

if __name__ == "__main__":
    main()
