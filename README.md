# cezmi-bot

Multi-Exchange Transfer Bot - Paribu & BTCTurk Arbitrage Bot

## Açıklama

Bu bot, Binance, Bybit ve OKX gibi kaynak borsalardan kripto para çekimi yaparak BTCTurk veya Paribu gibi hedef borsalara transfer işlemlerini otomatik olarak gerçekleştirir.

## Özellikler

- **Çoklu Borsa Desteği**: Binance, Bybit, OKX kaynak borsa olarak
- **Hedef Borsalar**: BTCTurk ve Paribu
- **GUI Arayüz**: Tkinter tabanlı kullanıcı dostu arayüz
- **Otomatik Bakiye Kontrolü**: Transfer öncesi bakiye doğrulama
- **Detaylı Loglama**: Tüm işlemlerin kaydı
- **Güvenli Çekim**: Adres ve network doğrulama

## Kurulum

1. Gerekli paketleri yükleyin:
```bash
pip install -r requirements.txt
```

2. `.env.example` dosyasını `.env` olarak kopyalayın ve API anahtarlarınızı ekleyin:
```bash
cp .env.example .env
```

3. `config.json` dosyasını düzenleyin ve hedef borsa adreslerinizi ekleyin.

## Kullanım

Bot'u çalıştırmak için:
```bash
python bot.py
```

GUI arayüzünden:
1. Kaynak borsa seçin (Binance, Bybit, OKX)
2. Hedef borsa seçin (BTCTurk, Paribu)
3. "TRANSFER BAŞLAT" butonuna tıklayın

## Son Değişiklikler

### v1.1 - 2025-11-27
- ✅ **Bug Fix**: `work` fonksiyonundaki tanımsız `symbol` değişkeni hatası düzeltildi
- Tüm `symbol` referansları `base_symbol` ile değiştirildi
- Kod sözdizimi doğrulaması başarıyla tamamlandı

## Güvenlik Uyarıları

⚠️ **DİKKAT**: 
- Yanlış adres girişi coin kaybına yol açabilir
- API anahtarlarınızı güvenli tutun
- `.env` dosyasını asla paylaşmayın
- İlk kullanımda küçük miktarlarla test edin

## Lisans

Bu proje özel kullanım içindir.