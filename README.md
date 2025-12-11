# 🤖 Cezmi MEV Bot

Profesyonel bir MEV (Maximum Extractable Value) bot'u - Ethereum ve EVM uyumlu blockchain'lerde arbitraj, sandwich attacks ve front-running stratejileri ile kar elde edin.

## ⚠️ Önemli Uyarılar

- **RİSK**: MEV botları karmaşıktır ve sermaye kaybına yol açabilir
- **ETİK**: Bazı MEV stratejileri tartışmalıdır ve kullanıcılara zarar verebilir
- **YASAL**: Bulunduğunuz ülkenin yasalarını kontrol edin
- **GÜVENLİK**: Private key'lerinizi asla paylaşmayın veya commit etmeyin
- **TEST**: Önce testnet'te test edin, küçük miktarlarla başlayın

## 🚀 Özellikler

### MEV Stratejileri

1. **Arbitraj**
   - Farklı DEX'ler arasında fiyat farklarını tespit eder
   - Uniswap V2, Uniswap V3, Sushiswap, PancakeSwap desteği
   - Optimal trade miktarı hesaplama
   - Karlılık analizi (gas maliyetleri dahil)

2. **Sandwich Attacks**
   - Büyük işlemleri tespit eder
   - Front-run ve back-run ile kar elde eder
   - Fiyat etkisi hesaplama
   - Slippage koruması

3. **Front-Running**
   - Mempool'daki karlı işlemleri tespit eder
   - Daha yüksek gas ile öncelik alır
   - Hedef fonksiyon filtreleme

4. **Back-Running**
   - Büyük işlemlerden sonra fiyat değişimlerinden yararlanır
   - Zamanlama optimizasyonu

### Teknik Özellikler

- ⚡ **Gerçek Zamanlı Mempool İzleme**: WebSocket ile anlık işlem takibi
- 🔄 **Çoklu DEX Entegrasyonu**: Uniswap, Sushiswap, PancakeSwap
- 💰 **Flashloan Desteği**: Aave ve dYdX entegrasyonu
- ⛽ **Gas Optimizasyonu**: Dinamik gas fiyatlandırma
- 📊 **Kar Hesaplama**: Detaylı karlılık analizi
- 🔐 **Güvenli**: Private key yönetimi
- 📝 **Loglama**: Detaylı işlem kayıtları
- 🎯 **Konfigüre Edilebilir**: YAML bazlı ayarlar

## 📋 Gereksinimler

- Python 3.9+
- Ethereum node erişimi (Alchemy, Infura, veya kendi node'unuz)
- WebSocket desteği (mempool izleme için)
- ETH (gas ücretleri için)

## 🛠️ Kurulum

### 1. Repository'yi klonlayın

```bash
git clone https://github.com/your-username/cezmi-bot.git
cd cezmi-bot
```

### 2. Virtual environment oluşturun

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# veya
venv\Scripts\activate  # Windows
```

### 3. Bağımlılıkları yükleyin

```bash
pip install -r requirements.txt
```

### 4. Konfigürasyonu ayarlayın

`config/config.yaml` dosyasını düzenleyin:

```yaml
# RPC endpoint'inizi ekleyin
blockchain:
  ethereum:
    mainnet: "https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY"
  websocket_url: "wss://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY"

# Private key'inizi ekleyin (ASLA GIT'E EKLEMEYİN!)
wallet:
  private_key: "YOUR_PRIVATE_KEY"

# Stratejileri aktif edin
strategies:
  arbitrage:
    enabled: true
    min_profit_wei: 50000000000000000  # 0.05 ETH
  
  sandwich:
    enabled: false  # Dikkatli kullanın!
  
  frontrun:
    enabled: false  # Dikkatli kullanın!
```

### 5. Çevresel değişkenler (Önerilen)

Private key'i config dosyasına yazmak yerine:

```bash
export PRIVATE_KEY="your_private_key"
export RPC_URL="your_rpc_url"
export WEBSOCKET_URL="your_websocket_url"
```

## 🎮 Kullanım

### Botu başlatın

```bash
python -m src.mev_bot
```

veya

```bash
python run.py
```

### Test modunda çalıştırın

```bash
# Önce testnet ayarlarını yapın
python -m src.mev_bot --network goerli
```

## 📊 Örnek Çıktı

```
============================================================
MEV Bot Starting...
============================================================
✓ Configuration loaded from config/config.yaml
✓ Connected to blockchain (Chain ID: 1)
✓ WebSocket connection established
Wallet Address: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
✓ Arbitrage strategy enabled
✓ MEV Bot initialized successfully

🚀 MEV Bot is now running and monitoring mempool...
Press Ctrl+C to stop

2024-12-11 10:23:45 | INFO     | Processed 100 txs (45.2 tx/s)

💰 Executing arbitrage opportunity
Expected profit: 0.08 ETH
✓ Trade successful!
Profit: 0.085 ETH
Gas spent: 0.012 ETH
Net profit: 0.073 ETH
TX: 0x1234...5678
```

## 📁 Proje Yapısı

```
cezmi-bot/
├── config/
│   └── config.yaml          # Ana konfigürasyon
├── src/
│   ├── __init__.py
│   ├── mev_bot.py          # Ana bot orchestrator
│   ├── config.py           # Konfigürasyon yönetimi
│   ├── dex/                # DEX entegrasyonları
│   │   ├── base_dex.py
│   │   ├── uniswap_v2.py
│   │   ├── uniswap_v3.py
│   │   ├── sushiswap.py
│   │   └── pancakeswap.py
│   ├── strategies/         # MEV stratejileri
│   │   ├── base_strategy.py
│   │   ├── arbitrage.py
│   │   ├── sandwich.py
│   │   ├── frontrun.py
│   │   └── backrun.py
│   ├── flashloan/          # Flashloan sağlayıcıları
│   │   ├── aave_flashloan.py
│   │   └── dydx_flashloan.py
│   └── utils/              # Yardımcı modüller
│       ├── logger.py
│       ├── blockchain.py
│       ├── mempool_monitor.py
│       ├── gas_optimizer.py
│       └── profit_calculator.py
├── logs/                   # Log dosyaları
├── tests/                  # Test dosyaları
├── requirements.txt        # Python bağımlılıkları
├── README.md              # Dokümantasyon
└── run.py                 # Ana başlatma scripti
```

## ⚙️ Konfigürasyon

### Minimum Kar Ayarları

```yaml
strategies:
  arbitrage:
    min_profit_wei: 50000000000000000  # 0.05 ETH
  sandwich:
    min_profit_wei: 100000000000000000  # 0.1 ETH
```

### Gas Stratejisi

```yaml
gas:
  priority: "aggressive"  # conservative, normal, aggressive
  max_gas_price_gwei: 500
```

### Risk Yönetimi

```yaml
risk:
  max_position_size_eth: 100
  max_slippage: 0.03  # 3%
  stop_loss_percentage: 0.1
  daily_loss_limit_eth: 5
```

## 🔒 Güvenlik

### Private Key Yönetimi

**ASLA** private key'inizi:
- Git repository'ye eklemeyin
- Koda hard-code etmeyin
- Başkalarıyla paylaşmayın

Güvenli saklama yöntemleri:
1. Çevresel değişkenler (önerilen)
2. `.env` dosyası (`.gitignore`'a ekleyin)
3. Hardware wallet entegrasyonu
4. Encrypted key store

### Güvenlik Kontrol Listesi

- [ ] Private key güvenli bir şekilde saklanıyor
- [ ] `.gitignore` dosyası yapılandırıldı
- [ ] Testnet'te test edildi
- [ ] Küçük miktarlarla başlandı
- [ ] Risk limitleri ayarlandı
- [ ] Monitoring aktif

## 📈 Performans İpuçları

1. **Node Seçimi**
   - Kendi full node'unuzu çalıştırın (en iyi)
   - Premium RPC sağlayıcı kullanın (Alchemy, Infura)
   - WebSocket bağlantısı gerekli

2. **Gas Optimizasyonu**
   - Gas fiyatlarını gerçek zamanlı izleyin
   - Aggressive gas stratejisi kullanın
   - EIP-1559 desteği

3. **Latency**
   - Bot'u node'a yakın sunucuda çalıştırın
   - WebSocket bağlantısı kullanın
   - Gereksiz hesaplamaları önleyin

4. **Stratejiler**
   - Arbitraj: En güvenli, daha düşük kar
   - Sandwich: Yüksek kar, tartışmalı
   - Front-running: Rekabetçi, yüksek gas

## 🧪 Test

```bash
# Test suite'i çalıştır
pytest tests/

# Specific test
pytest tests/test_arbitrage.py

# Coverage ile
pytest --cov=src tests/
```

## 📚 Kaynaklar

### MEV Hakkında
- [Flashbots Documentation](https://docs.flashbots.net/)
- [Ethereum.org MEV](https://ethereum.org/en/developers/docs/mev/)
- [MEV-Boost](https://boost.flashbots.net/)

### DEX Documentation
- [Uniswap V2](https://docs.uniswap.org/contracts/v2/overview)
- [Uniswap V3](https://docs.uniswap.org/contracts/v3/overview)
- [Sushiswap](https://dev.sushi.com/)

### Flashloans
- [Aave Flashloans](https://docs.aave.com/developers/guides/flash-loans)
- [dYdX](https://docs.dydx.exchange/)

## 🤝 Katkıda Bulunma

Katkılar memnuniyetle karşılanır! Lütfen:

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing`)
3. Commit edin (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing`)
5. Pull Request açın

## 📄 Lisans

MIT License - Detaylar için `LICENSE` dosyasına bakın

## ⚖️ Sorumluluk Reddi

Bu yazılım EĞİTİM AMAÇLIDIR. MEV stratejileri:
- Mali kayba yol açabilir
- Etik sorunlar içerebilir
- Yasal riskler taşıyabilir

Kullanımdan doğacak kayıplardan yazarlar sorumlu değildir.

## 📞 Destek

Sorularınız için:
- GitHub Issues
- Discord: [Yakında]
- Twitter: [@cezmibot](https://twitter.com/cezmibot)

## 🎯 Roadmap

- [x] Temel arbitraj stratejisi
- [x] Sandwich attacks
- [x] Flashloan entegrasyonu
- [ ] Flashbots entegrasyonu
- [ ] Machine learning fiyat tahmini
- [ ] Multi-chain desteği
- [ ] Web dashboard
- [ ] Telegram bot entegrasyonu
- [ ] Advanced risk yönetimi

## 🙏 Teşekkürler

- Ethereum Foundation
- Flashbots Team
- Uniswap Team
- Açık kaynak topluluğu

---

**Made with ❤️ by Cezmi Bot Team**

**İyi şanslar ve sorumlu trading! 🚀**
