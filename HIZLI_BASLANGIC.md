# 🚀 Hızlı Başlangıç Rehberi

## 5 Dakikada MEV Bot'u Çalıştırın!

### 1. Gerekli Hesapları Oluşturun

#### Alchemy Hesabı (ÜCRETSİZ)
1. [Alchemy.com](https://www.alchemy.com/) adresine gidin
2. Ücretsiz hesap oluşturun
3. "Create App" butonuna tıklayın
4. Ethereum Mainnet seçin
5. API Key ve WebSocket URL'i kopyalayın

### 2. Kurulum

```bash
# Repository'yi klonlayın
git clone <repository-url>
cd cezmi-bot

# Virtual environment oluşturun
python -m venv venv
source venv/bin/activate  # Mac/Linux
# veya
venv\Scripts\activate  # Windows

# Bağımlılıkları yükleyin
pip install -r requirements.txt
```

### 3. Konfigürasyon

#### Yöntem 1: .env dosyası (ÖNERİLEN)

```bash
# .env.example dosyasını kopyalayın
cp .env.example .env

# .env dosyasını düzenleyin
nano .env  # veya favori editörünüz
```

`.env` dosyasına ekleyin:

```bash
PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
WEBSOCKET_URL=wss://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
```

#### Yöntem 2: config.yaml dosyasını düzenleyin

```bash
nano config/config.yaml
```

Aşağıdaki kısımları güncelleyin:

```yaml
blockchain:
  ethereum:
    mainnet: "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
  websocket_url: "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"

wallet:
  private_key: "YOUR_PRIVATE_KEY"
```

### 4. Strateji Ayarları

İlk denemede sadece **arbitraj** stratejisini aktif edin:

```yaml
strategies:
  arbitrage:
    enabled: true
    min_profit_wei: 50000000000000000  # 0.05 ETH
  
  sandwich:
    enabled: false  # Sonra aktif edebilirsiniz
  
  frontrun:
    enabled: false
```

### 5. Bot'u Başlatın!

```bash
python run.py
```

### 6. İlk Çalıştırma

Bot başladığında:
1. Kullanım şartlarını okuyun
2. "KABUL EDIYORUM" yazın
3. Bot mempool'u izlemeye başlayacak

### Örnek Çıktı

```
╔═══════════════════════════════════════════════════════════╗
║              🤖 CEZMI MEV BOT 🤖                         ║
╚═══════════════════════════════════════════════════════════╝

✓ Configuration loaded
✓ Connected to blockchain (Chain ID: 1)
✓ WebSocket connection established
Wallet Address: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
💰 Cüzdan bakiyesi: 1.2500 ETH

🚀 MEV Bot is now running and monitoring mempool...
```

## ⚡ Hızlı İpuçları

### Test İçin Testnet Kullanın

```yaml
blockchain:
  active_network: "ethereum.goerli"
  ethereum:
    goerli: "https://eth-goerli.g.alchemy.com/v2/YOUR_KEY"
```

Goerli testnet ETH için:
- [Goerli Faucet](https://goerlifaucet.com/)
- [Alchemy Goerli Faucet](https://www.alchemy.com/faucets/ethereum-goerli)

### Minimum Bakiye

- **Testnet**: 0.1 ETH (ücretsiz faucet'lerden alın)
- **Mainnet**: En az 1 ETH (gas için)

### Güvenlik Kontrol Listesi

- [ ] Private key'i `.env` dosyasında saklıyorum
- [ ] `.gitignore` dosyası mevcut
- [ ] Önce testnet'te test ettim
- [ ] Küçük miktar ile başlıyorum
- [ ] Risk limitlerini ayarladım

## 🔧 Sorun Giderme

### "Connection Error"

```bash
# RPC URL'inizin doğru olduğundan emin olun
curl -X POST https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### "Invalid Private Key"

Private key formatı:
- `0x` ile başlamalı
- 66 karakter uzunluğunda (0x + 64 hex karakter)
- Örnek: `0x1234567890abcdef...`

### "Insufficient Funds"

Cüzdanınızda yeterli ETH olduğundan emin olun:
- Gas ücretleri için
- Trading için

### "No Opportunities Found"

Normal! MEV fırsatları nadir olabilir:
- Arbitraj için daha fazla DEX pair ekleyin
- Gas ayarlarını optimize edin
- Farklı saatlerde deneyin

## 📊 İlk 24 Saat

### Beklentiler

**Gerçekçi beklentiler:**
- İlk gün: Fırsatları öğrenin
- Muhtemelen kayıp: Gas ücretleri yüksek
- Sabırlı olun: Optimize edin

**Hedefler:**
1. ✅ Bot stabil çalışıyor
2. ✅ Fırsatlar tespit ediliyor
3. ✅ İşlemler başarılı
4. ✅ Kar/zarar takip ediliyor

### Monitoring

```bash
# Logları takip edin
tail -f logs/mev_bot_YYYYMMDD.log

# Gerçek zamanlı istatistikler
# Bot çalışırken Ctrl+C ile durdurun
```

## 🎯 Optimizasyon

### Gas Stratejisi

Rekabetçi ortam için:

```yaml
gas:
  priority: "aggressive"
  max_gas_price_gwei: 300
```

### Arbitraj İçin

```yaml
strategies:
  arbitrage:
    min_profit_wei: 30000000000000000  # 0.03 ETH
    dex_pairs:
      - ["uniswap_v2", "sushiswap"]
      - ["uniswap_v3", "uniswap_v2"]
```

## 💡 Pro İpuçları

1. **Node Kalitesi**: Premium RPC = Daha iyi latency
2. **Gas Timing**: Düşük trafik saatleri = Daha ucuz gas
3. **Çoklu Strateji**: Farklı stratejiler = Daha fazla fırsat
4. **Risk Yönetimi**: Stop loss ayarlayın
5. **İzleme**: Logları takip edin

## 📞 Yardım

Sorun mu yaşıyorsunuz?

1. `logs/` klasöründeki log dosyalarını kontrol edin
2. GitHub Issues'da arayın
3. Yeni issue açın
4. Discord'da sorun (yakında)

## 🎓 Sonraki Adımlar

1. ✅ Bot çalışıyor
2. 📖 Stratejileri öğrenin
3. 🧪 Testnet'te optimize edin
4. 💰 Küçük miktarlarla başlayın
5. 📈 Ölçeklendirin

## ⚠️ Hatırlatma

- Bu EĞİTİM AMAÇLIDIR
- Risk yönetimi yapın
- Kaybedebileceğiniz kadar yatırım yapın
- Sorumlu trading yapın

---

**Başarılar! 🚀**

Sorularınız için: README.md dosyasına bakın
