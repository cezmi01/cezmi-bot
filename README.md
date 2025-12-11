# MEV Bot - Kripto Para Arbitraj Botu

Ethereum blockchain üzerinde DEX'ler (Uniswap, Sushiswap) arasında arbitraj fırsatlarını tespit eden ve otomatik işlem yapan MEV (Maximal Extractable Value) botu.

## 🚀 Özellikler

- **Arbitraj Tespiti**: Uniswap V2 ve Sushiswap arasında fiyat farklarını tespit eder
- **Otomatik İşlem**: Kar getiren fırsatları otomatik olarak gerçekleştirir
- **Gas Yönetimi**: Akıllı gas fiyatı kontrolü ve optimizasyonu
- **Slippage Koruması**: Slippage toleransı ile korumalı işlemler
- **Güvenlik**: Private key güvenliği ve hata yönetimi

## 📋 Gereksinimler

- Python 3.8+
- Ethereum RPC endpoint (Alchemy, Infura vb.)
- Ethereum wallet private key
- Test için ETH bakiyesi (testnet veya mainnet)

## 🔧 Kurulum

1. **Repository'yi klonlayın:**
```bash
git clone <repo-url>
cd mev-bot
```

2. **Bağımlılıkları yükleyin:**
```bash
pip install -r requirements.txt
```

3. **Konfigürasyon dosyasını oluşturun:**
```bash
cp .env.example .env
```

4. **`.env` dosyasını düzenleyin:**
```env
RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY
PRIVATE_KEY=your_private_key_here
MAX_GAS_PRICE_GWEI=100
MIN_PROFIT_PERCENTAGE=0.5
```

## ⚠️ ÖNEMLİ GÜVENLİK UYARILARI

1. **Private Key Güvenliği:**
   - `.env` dosyasını asla git'e commit etmeyin
   - Private key'inizi kimseyle paylaşmayın
   - Test için küçük miktarlarla başlayın

2. **Testnet Kullanımı:**
   - İlk testlerinizi testnet üzerinde yapın (Goerli, Sepolia)
   - Mainnet'e geçmeden önce kodları iyice test edin

3. **Risk Yönetimi:**
   - Maksimum pozisyon büyüklüğünü ayarlayın
   - Gas fiyatı limitlerini belirleyin
   - Minimum kar yüzdesini dikkatli seçin

## 🎯 Kullanım

### Temel Kullanım

```bash
python main.py
```

### Özelleştirme

`config.py` veya `.env` dosyasından ayarları değiştirebilirsiniz:

- `MIN_PROFIT_PERCENTAGE`: Minimum kar yüzdesi (%)
- `SLIPPAGE_TOLERANCE`: Slippage toleransı (%)
- `MAX_POSITION_SIZE_ETH`: Maksimum pozisyon büyüklüğü (ETH)
- `POLL_INTERVAL`: Fiyat kontrol aralığı (saniye)

## 📁 Proje Yapısı

```
mev-bot/
├── main.py              # Ana çalıştırma dosyası
├── mev_bot.py           # MEV bot ana modülü
├── blockchain.py         # Blockchain bağlantı ve işlem yönetimi
├── price_monitor.py      # Fiyat izleme ve arbitraj tespiti
├── config.py             # Konfigürasyon yönetimi
├── utils.py              # Yardımcı fonksiyonlar
├── requirements.txt      # Python bağımlılıkları
├── .env.example          # Örnek environment dosyası
└── README.md             # Bu dosya
```

## 🔍 Nasıl Çalışır?

1. **Fiyat İzleme**: Bot sürekli olarak Uniswap V2 ve Sushiswap'tan token fiyatlarını kontrol eder
2. **Fırsat Tespiti**: İki DEX arasında fiyat farkı bulduğunda arbitraj fırsatını hesaplar
3. **Kar Kontrolü**: Fırsatın minimum kar yüzdesini karşılayıp karşılamadığını kontrol eder
4. **İşlem Gerçekleştirme**: Koşullar uygunsa arbitraj işlemini gerçekleştirir

## ⚡ Gelişmiş Özellikler (Gelecek)

- [ ] Flash loan entegrasyonu
- [ ] Uniswap V3 desteği
- [ ] Mempool izleme ve front-running koruması
- [ ] Çoklu token çifti desteği
- [ ] WebSocket ile gerçek zamanlı fiyat güncellemeleri
- [ ] Veritabanı ile işlem geçmişi kaydı
- [ ] Telegram/Discord bildirimleri

## 🐛 Bilinen Sınırlamalar

- Şu anda basit bir arbitraj örneği (flash loan gerektirir)
- Sadece Uniswap V2 ve Sushiswap desteği
- Tek token çifti izleme (WETH/USDC)

## 📝 Lisans

Bu proje eğitim amaçlıdır. Gerçek para ile kullanmadan önce kapsamlı testler yapın.

## ⚠️ Sorumluluk Reddi

Bu bot eğitim ve araştırma amaçlıdır. Kullanımından doğacak kayıplardan geliştiriciler sorumlu değildir. Kripto para ticareti risklidir, sadece kaybetmeyi göze alabileceğiniz parayla işlem yapın.