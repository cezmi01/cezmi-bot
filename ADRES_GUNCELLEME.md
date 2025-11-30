# Deposit Adresi Güncelleme Rehberi

## Genel Bakış

Bot'un doğru çalışması için `config.json` dosyasında BTCTurk ve Paribu deposit adreslerinin olması gerekiyor.

## Mevcut Durum

```json
✓ ETH: Adresler girilmiş
✗ USDT (TRC20): Adresler eksik
✗ USDT (ERC20): Adresler eksik
✗ BTC: Adresler eksik
```

## Yöntem 1: Otomatik API ile Çekme

### Gereksinimler
1. `.env` dosyasına API anahtarlarını ekleyin:
```bash
# BTCTurk API
BTCTURK_KEY=your_btcturk_api_key
BTCTURK_SECRET=your_btcturk_secret_key

# Paribu API
PARIBU_KEY=your_paribu_api_key
PARIBU_SECRET=your_paribu_secret_key
```

### Çalıştırma
```bash
python address_fetcher.py
```

Script otomatik olarak:
- BTCTurk'ten deposit adreslerini çeker
- Paribu'dan deposit adreslerini çeker
- `config.json` dosyasını günceller

## Yöntem 2: Manuel Güncelleme

API anahtarları yoksa veya manuel girmek isterseniz:

```bash
python address_fetcher.py manual
```

Bu mod interaktif olarak her coin için address sorar.

## Yöntem 3: Doğrudan config.json Düzenleme

1. BTCTurk ve Paribu hesabınıza giriş yapın
2. Her coin için deposit address oluşturun:
   - USDT (TRC20)
   - USDT (ERC20)
   - BTC (Bitcoin Network)
   
3. `config.json` dosyasını açın ve adresleri girin:

```json
{
  "symbol": "USDT",
  "network": "TRC20",
  "btcturk": {
    "symbol": "USDT",
    "network": "TRC20",
    "address": "BURAYA_BTCTURK_USDT_TRC20_ADRESI",
    "memo": null
  },
  "paribu": {
    "symbol": "USDT",
    "network": "TRC20",
    "address": "BURAYA_PARIBU_USDT_TRC20_ADRESI",
    "memo": null
  }
}
```

## Önemli Notlar

### Network Uyumu
- **TRC20**: Tron network (genelde düşük fee)
- **ERC20**: Ethereum network (yüksek fee)
- **BTC**: Bitcoin native network

⚠️ **DİKKAT**: Network'ü yanlış seçerseniz paranız kaybolabilir! 
- TRC20 adresi sadece TRC20 transferi için
- ERC20 adresi sadece ERC20 transferi için
- BTC adresi sadece Bitcoin network için

### Address Doğrulama

Adresleri girdikten sonra doğrulamak için:

```bash
python -c "import json; config = json.load(open('config.json')); 
for item in config: 
    print(f\"{item['symbol']} ({item['network']}): BTCTurk={item['btcturk']['address'][:10]}... Paribu={item['paribu']['address'][:10]}...\")"
```

## API Endpoint Notları

### BTCTurk API
- Base URL: `https://api.btcturk.com`
- Deposit Address: `/api/v1/users/crypto/deposit/address/{CURRENCY}`
- Dokümantasyon: https://docs.btcturk.com/

### Paribu API
- Base URL: `https://www.paribu.com/api`
- Deposit Address: `/v1/deposit/address/{CURRENCY}`
- Not: Paribu API endpoint'leri resmi dökümantasyona göre değişebilir

## Sorun Giderme

### API Bağlantı Hatası
- API anahtarlarınızın doğru olduğundan emin olun
- IP whitelist kontrolü yapın (BTCTurk ve Paribu'da API için IP kısıtlaması olabilir)
- API iznlerini kontrol edin (deposit address okuma yetkisi olmalı)

### Address Eksik Hatası
- Manuel olarak exchange'den deposit address oluşturun
- Bazı coinler için address oluşturulması birkaç saniye sürebilir

### Network Hatası
- config.json'daki network adının exchange'deki ile eşleştiğinden emin olun
- Bazı exchange'ler farklı network isimleri kullanır (örn: "TRON" vs "TRC20")

## Güvenlik

⚠️ **ÖNEMLİ GÜVENLİK NOTLARI**:

1. **API Anahtarları**: 
   - `.env` dosyasını asla paylaşmayın
   - `.env` dosyası `.gitignore`'da olmalı
   - API anahtarlarına sadece gerekli izinleri verin (withdrawal DEĞİL!)

2. **Deposit Adresleri**:
   - Adresleri çift kontrol edin
   - Test için önce küçük miktar gönderin
   - Network'ü doğru seçin

3. **Config Backup**:
   ```bash
   cp config.json config.json.backup
   ```

## Sonraki Adımlar

Adresler güncellendikten sonra:

1. Config'i doğrulayın:
   ```bash
   python -c "import json; json.load(open('config.json'))" && echo "✓ Config valid"
   ```

2. Bot'u test modunda çalıştırın:
   ```bash
   python bot.py
   ```

3. Küçük miktarlarla test edin

## Yardım

Sorun yaşarsanız:
1. Log dosyasını kontrol edin: `withdraw_logs.jsonl`
2. API response'ları inceleyin
3. Exchange support ile iletişime geçin
