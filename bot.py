# -*- coding: utf-8 -*-
"""
PARIBU DINAMIK SATIŞ (SMART FOLLOWER)
-------------------------------------
Binance fiyatını saniye saniye takip eder.
Binance yükselirse -> Paribu satış emrini yukarı çeker.
Binance düşerse -> Fiyatı günceller (Trailing).
Telegram butonları ile ayarlar anlık değişir.
"""
import os
import time
import json
import hmac
import hashlib
import base64
import logging
import threading
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from binance.client import Client
from dotenv import load_dotenv
import requests

load_dotenv()

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


# --- HTTP Session with Retries ---
def create_retry_session(total_retries=5, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504)):
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        read=total_retries,
        connect=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'])
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


# Global HTTP session for Telegram and misc calls
http_session = create_retry_session()


# --- Activity watchdog ---
global_last_activity = time.time()


def touch_activity():
    global global_last_activity
    global_last_activity = time.time()


def _watchdog_worker(timeout_seconds=300):
    while True:
        try:
            now = time.time()
            age = now - global_last_activity
            if age > timeout_seconds:
                logging.error(f"Watchdog: no activity for {age:.0f}s — exiting to allow restart")
                # Force exit so supervisor restarts process
                os._exit(1)
            time.sleep(10)
        except Exception:
            logging.exception("Watchdog thread error")
            time.sleep(10)

# --- AYARLAR ---
PARIBU_API_KEY = os.getenv("PARIBU_API_KEY")
PARIBU_SECRET = os.getenv("PARIBU_API_SECRET")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- ENV DEBUG ---
print("-" * 30)
print("ENV KONTROL:")
print(f"Paribu Key: {'VAR' if PARIBU_API_KEY else 'YOK'}")
print(f"Paribu Secret: {'VAR' if PARIBU_SECRET else 'YOK'}")
print(f"Telegram Token: {'VAR' if TELEGRAM_BOT_TOKEN else 'YOK'}")
print(f"Telegram Chat ID: {'VAR' if TELEGRAM_CHAT_ID else 'YOK'}")
print("-" * 30)

# Binance Client
b_client = Client(BINANCE_API_KEY, BINANCE_SECRET)


# --- PARIBU API FONKSİYONLARI ---
class ParibuClient:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.paribu.com"
        self.session = requests.Session()  # Connection reuse için

    def _generate_signature(self, body_json=""):
        """
        Paribu İmza Oluşturma
        Sadece Query + Body imzalanıyor. Timestamp veya API Key imzaya girmiyor.
        """
        request_body = body_json if body_json else ""
        data_to_sign = request_body  # Query şimdilik yok

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            data_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()

        return base64.b64encode(signature).decode('utf-8')

    def _get_headers(self, body_json=""):
        """API headers oluşturma"""
        signature = self._generate_signature(body_json)

        return {
            "Authorization": self.api_key,
            "X-Signature": signature,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36"
        }

    def get_balance(self):
        """Bakiye sorgulama (/user/assets)"""
        try:
            # GET isteklerinde body yoktur
            headers = self._get_headers(body_json="")
            response = self.session.get(
                f"{self.base_url}/user/assets",
                headers=headers,
                timeout=3
            )
            return response.json()
        except Exception as e:
            print(f"Bakiye sorgulama hatası: {e}")
            return None

    def create_order(self, market, side, amount, price):
        """Limit emir oluşturma (/order)"""
        try:
            # Datayı oluştur
            data_dict = {
                "market": market,
                "trade": side if side in ["buy", "sell"] else "sell",
                "type": "limit",
                "amount": float(amount),
                "price": float(price)
            }

            # JSON string (Minified Format ŞART!)
            body_json = json.dumps(data_dict, separators=(",", ":"))
            headers = self._get_headers(body_json=body_json)

            response = self.session.post(
                f"{self.base_url}/order",
                headers=headers,
                data=body_json,
                timeout=3
            )

            return response.json()

        except Exception:
            return None

    def cancel_order(self, order_id):
        """Emir İptal Etme (DELETE /order/{id})"""
        try:
            # DELETE isteğinde body genelde olmaz ama headers lazım
            headers = self._get_headers()
            logging.info(f"İptal isteği: {order_id}")

            # Endpoint: /order/{id} - session ile ve timeout kullan
            resp = self.session.delete(
                f"{self.base_url}/order/{order_id}",
                headers=headers,
                timeout=5
            )

            if resp.status_code == 200:
                logging.info("Emir iptal edildi.")
                return True
            if resp.status_code in [400, 404, 422]:
                logging.info("Emir zaten yok (400/404/422).")
                return True
            logging.warning(f"İptal başarısız (Kod {resp.status_code}): {resp.text}")
            return False

        except Exception:
            logging.exception("İptal hatası")
            return False

    def get_order_status(self, order_id):
        """Emir durumu sorgulama"""
        try:
            headers = self._get_headers()
            response = self.session.get(
                f"{self.base_url}/api/v1/order/{order_id}",
                headers=headers,
                timeout=5
            )
            return response.json()
        except Exception:
            logging.exception("Emir durumu sorgulama hatası")
            return None

    def get_coin_balance(self, symbol):
        """Spesifik coin bakiyesini döner"""
        # Endpointleri sırasıyla dene
        endpoints = ["/user/assets", "/user/balances", "/api/v1/user/balances"]

        for endpoint in endpoints:
            try:
                headers = self._get_headers()
                response = requests.get(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        continue

                    items = []
                    # Farklı yanıt formatlarını normalize et
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        # payload veya data altında olabilir
                        items = data.get("payload", data.get("data", []))
                        # Bazı endpointlerde direkt dict {"BTC": {...}} dönebilir
                        if not items and "BTC" in data:  # Örnek kontrol
                            items = [{"symbol": k, "available": v.get("available", 0)} for k, v in data.items()]

                    # Listeyi tara ve sembolü bul
                    if isinstance(items, list):
                        for item in items:
                            s = item.get("symbol", item.get("currency", "")).upper()
                            if s == symbol:
                                av = item.get("available", 0)
                                return float(av)

                    # Eğer sözlükse ve direkt erişim varsa (Eski yöntem yedek)
                    if isinstance(items, dict) and symbol in items:
                        return float(items[symbol].get("available", 0))

            except Exception as e:
                print(f"Bakiye hata ({endpoint}): {e}")
                continue

        return 0.0

    def get_all_balances(self):
        """Tüm sıfır olmayan bakiyeleri döner (Otomatik tespit için)"""
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.base_url}/user/assets",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                balances = {}

                items = data if isinstance(data, list) else data.get("data", data.get("payload", []))

                for item in items:
                    symbol = item.get("symbol", item.get("currency", "")).upper()
                    available = float(item.get("available", 0))

                    # Sadece sıfır olmayan ve TL/USDT dışındakileri al
                    if available > 0.0001 and symbol not in ["TL", "USDT", "TRY"]:
                        balances[symbol] = available

                return balances
            return {}
        except Exception as e:
            print(f"Tüm bakiye hatası: {e}")
            return {}


# Paribu client oluştur
paribu_client = ParibuClient(PARIBU_API_KEY, PARIBU_SECRET) if PARIBU_API_KEY and PARIBU_SECRET else None


def get_settings():
    if os.path.exists("bot_settings.json"):
        with open("bot_settings.json", "r") as f:
            return json.load(f)
    return {}


def save_settings(settings):
    with open("bot_settings.json", "w") as f:
        json.dump(settings, f)


# USDT/TRY kuru önbelleği (her seferinde çekmemek için)
_usdt_rate_cache = {"rate": 36.5, "timestamp": 0}


def get_binance_price_tl(symbol):
    """Binance fiyatını TL cinsinden döner (Hızlandırılmış)"""
    global _usdt_rate_cache
    try:
        if not b_client:
            return None

        # Coin fiyatını çek
        ticker = b_client.get_symbol_ticker(symbol=f"{symbol.upper()}USDT")
        price_usdt = float(ticker['price'])

        # USDT/TRY kurunu önbellekten al (60 saniyede bir güncelle)
        current_time = time.time()
        if current_time - _usdt_rate_cache["timestamp"] > 60:
            try:
                usdt_try = b_client.get_symbol_ticker(symbol="USDTTRY")
                _usdt_rate_cache["rate"] = float(usdt_try['price'])
                _usdt_rate_cache["timestamp"] = current_time
            except Exception:
                pass  # Eski kuru kullan

        return price_usdt * _usdt_rate_cache["rate"]
    except Exception:
        return None


def get_reply_keyboard():
    """Basitleştirilmiş Kalıcı Klavye"""
    return {
        "keyboard": [
            ["🔍 OTOMATİK TAKİP"],
            ["⚙️ KAR AYARI", "📊 DURUM"],
            ["⛔ DURDUR"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }


# --- TELEGRAM FONKSİYONU ---
def send_telegram(message, reply_markup=None):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip('"').strip("'")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip('"').strip("'")

        if not token or not chat_id:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        # Eğer özel markup yoksa ve mesaj 'genel' bir mesajsa, kalıcı klavyeyi ekle
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        else:
            # Varsayılan olarak kalıcı klavyeyi gönder
            payload["reply_markup"] = json.dumps(get_reply_keyboard())

        # Timeout 5s
        requests.post(url, data=payload, timeout=5)
    except Exception:
        pass


# --- OTOMATİK DEPOSIT TAKİP MODU (TURBO) ---
def auto_watcher_mode():
    """
    TURBO MOD: Maksimum hız için optimize edilmiş cüzdan tarayıcı.
    0.1 saniyede bir tarama, önbellekli fiyatlar, minimum gecikme.
    """
    global global_last_update_id

    print("\n" + "=" * 50)
    print("⚡ TURBO TAKİP MODU BAŞLADI ⚡")
    print("=" * 50)

    send_telegram("⚡ <b>TURBO TAKİP AKTİF!</b>\n\n0.1 saniyede bir tarama yapılıyor.\nYeni coin geldiğinde ANINDA satış girilecek.")

    paribu_client = ParibuClient(PARIBU_API_KEY, PARIBU_SECRET)

    # Mevcut bakiyeleri kaydet
    known_balances = paribu_client.get_all_balances()
    print(f"📋 {len(known_balances)} coin kaydedildi")

    # TÜM FİYATLARI BAŞTA ÇEK (HIZLI MOD!)
    print("⚡ Tüm Paribu fiyatları yükleniyor...")
    price_cache = {}
    try:
        resp = requests.get("https://www.paribu.com/ticker", timeout=3)
        ticker_data = resp.json()
        for pair, data in ticker_data.items():
            if pair.endswith("_TL"):
                sym = pair.replace("_TL", "")
                price_cache[sym] = {
                    "last": float(data.get("last", 0)),
                    "bid": float(data.get("highestBid", 0))
                }
        print(f"✅ {len(price_cache)} coin fiyatı RAM'e yüklendi")
    except Exception:
        print("⚠️ Fiyat önbelleği yüklenemedi, Binance kullanılacak")

    last_price_update = time.time()

    scan_count = 0
    last_telegram_check = 0
    sleep_time = 0.02  # ULTRA: 20ms (saniyede 50 tarama)

    while True:
        try:
            current_time = time.time()

            # Telegram kontrolü (hız için azaltıldı)
            if current_time - last_telegram_check > 2:
                last_telegram_check = current_time
                try:
                    updates = get_telegram_updates(offset=global_last_update_id, timeout=0)
                    for update in updates:
                        global_last_update_id = update["update_id"] + 1
                        if "message" in update and "text" in update["message"]:
                            if update["message"]["text"] in ["⛔ DURDUR", "/dur"]:
                                send_telegram("🛑 <b>Turbo Takip Durduruldu.</b>")
                                return
                        if "callback_query" in update:
                            if update["callback_query"]["data"] == "stop_watcher":
                                return
                except Exception:
                    pass

            # Fiyat önbelleğini güncelle (10 saniyede bir - güncel fiyat için!)
            if current_time - last_price_update > 10:
                try:
                    resp = requests.get("https://www.paribu.com/ticker", timeout=3)
                    ticker_data = resp.json()
                    for pair, data in ticker_data.items():
                        if pair.endswith("_TL"):
                            sym = pair.replace("_TL", "")
                            price_cache[sym] = {
                                "last": float(data.get("last", 0)),
                                "bid": float(data.get("highestBid", 0))
                            }
                    last_price_update = current_time
                except Exception:
                    pass

            # Ayarları oku
            settings = get_settings()
            profit_pct = settings.get("profit_percent", 2.0)

            # Bakiyeleri çek (ANA TARAMA)
            try:
                current_balances = paribu_client.get_all_balances()
                scan_count += 1

                # Rate limit düzeltme
                if sleep_time > 0.02:
                    sleep_time = max(0.02, sleep_time * 0.9)
            except Exception:
                # API hatası - bir sonraki taramayı bekle
                current_balances = known_balances

            # Yeni deposit kontrolü
            for symbol, current_amount in current_balances.items():
                previous_amount = known_balances.get(symbol, 0)

                if current_amount > previous_amount + 0.0001:
                    new_amount = current_amount - previous_amount

                    # ANINDA EMİR (HİÇ BEKLEMEDEN!)
                    print(f"\n⚡ {symbol}")

                    # Fiyat verisini al
                    market_data = price_cache.get(symbol)

                    if market_data:
                        # Eğer %0 seçiliyse direkt en iyi alışa (highestBid) sat
                        if profit_pct == 0:
                            target = market_data["bid"]
                            if target == 0:
                                target = market_data["last"]  # Bid yoksa son fiyata dön
                        else:
                            # Normal kar marjı
                            target = market_data["last"] * (1 + profit_pct / 100)

                        price_str = f"{target:.8f}" if target < 1 else f"{target:.2f}"

                        # EMİR GİR (ANLIK!)
                        result = paribu_client.create_order(
                            f"{symbol.lower()}_tl", "sell", new_amount, price_str
                        )

                        if result and ("uid" in result or "id" in result or
                                       ("data" in result and ("uid" in result["data"] or "id" in result["data"]))):
                            send_telegram(
                                f"✅ <b>SATIŞ GİRİLDİ!</b>\n\n"
                                f"Coin: <b>{symbol}</b>\n"
                                f"Miktar: <b>{new_amount}</b>\n"
                                f"Fiyat: <b>{price_str} TL</b> (+%{profit_pct})"
                            )
                        else:
                            err = result.get("message", "?") if result else "API Hatası"
                            send_telegram(f"❌ {symbol}: {err}")
                    else:
                        # Fiyat önbellekte yoksa acil Binance çek
                        binance_p = get_binance_price_tl(symbol)
                        if binance_p:
                            target = binance_p * (1 + profit_pct / 100)
                            price_str = f"{target:.8f}" if target < 1 else f"{target:.2f}"
                            result = paribu_client.create_order(
                                f"{symbol.lower()}_tl", "sell", new_amount, price_str
                            )
                            if result and ("uid" in result or "id" in result):
                                send_telegram(f"✅ <b>{symbol}</b> satıldı (Binance fiyatı)")
                        else:
                            send_telegram(f"⚠️ {symbol} fiyatı bulunamadı!")

                    known_balances[symbol] = current_amount

            # Durum göstergesi (sessiz)
            if scan_count % 100 == 0:
                print(f"\r⚡ Tarama #{scan_count} ({sleep_time * 1000:.0f}ms)", end="", flush=True)

            time.sleep(sleep_time)  # Dinamik hız

        except requests.exceptions.HTTPError as e:
            # Rate limit hatası (429) yakalandı
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                sleep_time = min(1.0, sleep_time * 2)  # Hızı yarıya düşür
                print(f"\n⚠️ Rate limit! Yavaşlatıldı: {sleep_time * 1000:.0f}ms")
                time.sleep(2)
        except KeyboardInterrupt:
            return
        except Exception:
            time.sleep(1)


def get_paribu_ticker_price(symbol):
    """Binance'de olmayan coinler için Paribu Ticker Fiyatı"""
    try:
        url = "https://www.paribu.com/ticker"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        pair = f"{symbol.upper()}_TL"

        if pair in data:
            return {
                "last": float(data[pair].get("last", 0)),
                "bid": float(data[pair].get("highestBid", 0)),
                "ask": float(data[pair].get("lowestAsk", 0))
            }
        return None
    except Exception as e:
        print(f"Paribu Ticker Hatası: {e}")
        return None


global_last_update_id = None


def get_telegram_updates(offset=None, timeout=5):
    """Telegram güncellemelerini çeker"""
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip('"').strip("'")
        if not token:
            return []

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {"timeout": timeout, "offset": offset}
        resp = requests.get(url, params=params, timeout=timeout + 5)
        data = resp.json()

        if "result" in data:
            return data["result"]
        return []
    except Exception:
        return []


def wait_for_telegram_command():
    """Sadece Telegram komutlarını bekler (Reply Keyboard ile)"""
    global global_last_update_id

    print("\n📩 Telegram bekleniyor...")

    while True:
        try:
            updates = get_telegram_updates(offset=global_last_update_id)
            for update in updates:
                global_last_update_id = update["update_id"] + 1

                if "message" in update and "text" in update["message"]:
                    text = update["message"]["text"].strip()

                    if text == "🔍 OTOMATİK TAKİP":
                        send_telegram("🔍 <b>Turbo Takip Başlatılıyor...</b>\n\nBu modda sadece yeni gelen coinler satılır.")
                        return "__AUTO_WATCHER__"

                    if text == "⚙️ KAR AYARI":
                        profit_kb = {
                            "keyboard": [
                                ["%1", "%2", "%3"],
                                ["%5", "%10", "%0"],
                                ["🔙 ANA MENÜ"]
                            ],
                            "resize_keyboard": True
                        }
                        send_telegram("⚙️ <b>Kar Oranını Seçiniz:</b>", reply_markup=profit_kb)
                        continue

                    if text in ["%1", "%2", "%3", "%5", "%10", "%0", "%20"]:
                        try:
                            pct = float(text.replace("%", ""))
                            s = get_settings()
                            s["profit_percent"] = pct
                            save_settings(s)
                            send_telegram(f"✅ Kar oranı <b>%{int(pct)}</b> olarak ayarlandı.", reply_markup=get_reply_keyboard())
                        except Exception:
                            pass
                        continue

                    if text == "🔙 ANA MENÜ":
                        send_telegram("🔙 Ana Menüye Dönüldü.", reply_markup=get_reply_keyboard())
                        continue

                    if text == "📊 DURUM":
                        s = get_settings()
                        is_enabled = s.get("enabled", True)
                        status_icon = "🟢" if is_enabled else "🔴"
                        profit = s.get("profit_percent", 2.0)

                        msg = (
                            "📊 <b>BOT DURUMU</b>\n\n"
                            f"Durum: {status_icon} <b>{'AKTİF' if is_enabled else 'PASİF'}</b>\n"
                            "------------------\n"
                            f"🎯 Hedef Kar: <b>%{profit}</b>\n"
                        )
                        send_telegram(msg)
                        continue

                    if text == "⛔ DURDUR":
                        send_telegram("🛑 <b>İşlem Durduruldu (Ana Menüde).</b>")
                        continue

            time.sleep(0.1)

        except KeyboardInterrupt:
            return None
        except Exception as e:
            print(f"Tg Error: {e}")
            time.sleep(1)


def main():
    print("=" * 60)
    print("PARIBU OTO-SATIS BOTU")
    print("=" * 60)

    if not os.path.exists("bot_settings.json"):
        save_settings({"enabled": True, "profit_percent": 2.0, "dynamic_threshold": 0.01})

    global PARIBU_API_KEY, PARIBU_SECRET
    if PARIBU_API_KEY:
        PARIBU_API_KEY = PARIBU_API_KEY.strip('"').strip("'")
    if PARIBU_SECRET:
        PARIBU_SECRET = PARIBU_SECRET.strip('"').strip("'")

    # Açılış mesajı gönder
    print("🚀 Telegram açılış mesajı gönderiliyor...")
    send_telegram("🚀 <b>BOT BAŞLATILDI</b>\n\nKomutlarınız bekleniyor.", reply_markup=get_reply_keyboard())

    while True:
        try:
            # Ana döngü sadece Telegram komutu bekler
            command = wait_for_telegram_command()

            if command == "__AUTO_WATCHER__":
                auto_watcher_mode()
                print("\n🔄 Otomatik takip bitti. Menüye dönülüyor...")
                # Bitince (kullanıcı durdurursa) tekrar loop başına (Telegram bekleme)
                continue

        except KeyboardInterrupt:
            print("\n👋 Güle güle!")
            break
        except Exception as e:
            print(f"Ana döngü hatası: {e}")
            time.sleep(5)


def _heartbeat_worker(interval=60):
    while True:
        try:
            logging.info("heartbeat: bot is alive")
            time.sleep(interval)
        except Exception:
            logging.exception("Heartbeat thread hata")
            time.sleep(interval)


def start_heartbeat(interval=60):
    t = threading.Thread(target=_heartbeat_worker, args=(interval,), daemon=True)
    t.start()


def run_with_supervisor():
    start_heartbeat(60)
    backoff = 1
    while True:
        try:
            logging.info("Supervisor: starting main()")
            main()
            logging.info("main() exited normally")
            backoff = 1
        except KeyboardInterrupt:
            logging.info("Supervisor: KeyboardInterrupt received, exiting")
            break
        except Exception:
            logging.exception("Supervisor: main crashed")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    run_with_supervisor()
