# ERC-20 MEV Arbitrage Bot Plan

## 1. Hedefler
- Uniswap v2/v3 ve Sushiswap gibi EVM uyumlu DEX'lerde fiyat farklılıkları yakalamak
- Mempool üzerinden bekleyen işlemleri takip ederek gaz rekabetine uygun hızda paket hazırlamak
- Yapay zeka katmanı ile bulunan fırsatları risk/ödül skoruna göre önceliklendirmek
- Modüler Python kod tabanı ile strateji, veri toplama ve yürütme katmanlarını ayrı tutmak

## 2. Mimari
```
┌────────┐   ┌──────────────┐   ┌───────────┐   ┌───────────┐
│ Config │─▶│ Data Sources  │─▶│ Strategies │─▶│ Executors  │
└────────┘   └──────────────┘   └───────────┘   └───────────┘
                   │                  │               │
                   ▼                  │               ▼
              On-chain RPC        AI Scorer     Flashbots / RPC
```

### Bileşenler
1. **Config** (`config.py`): RPC url, cüzdan, takip edilecek tokenlar, gaz limitleri.
2. **Data Sources** (`providers.py`, `dex_clients.py`):
   - WebSocket RPC ile mempool eventi dinlemek (pendingTransactions)
   - DEX havuzlarından anlık fiyat/likidite çekmek
3. **Strategy** (`strategy.py`, `opportunity.py`):
   - Çift yönlü path araması (TokenA → TokenB → TokenA)
   - Gaz maliyeti + slipaj simülasyonu
   - AI skorlayıcı (örn. geçmiş fırsat datası ile eğitilen XGBoost / sklearn modeli)
4. **Executor** (`executor.py`):
   - Simülasyon sonucu pozitif ise bundle hazırlayıp Flashbots'a gönderir
   - Alternatif olarak direkt RPC üzerinden hızlı yayın
5. **CLI / Bot Runner** (`main.py`): async event loop, loglama, health-check

## 3. Yapay Zeka Katmanı
- Girdi özellikleri: fiyat farkı yüzdesi, likidite, geçmiş blokta benzer fırsatın başarısı, beklenen gaz maliyeti.
- Önerilen yaklaşım: `scikit-learn` GradientBoosting veya hafif bir `xgboost` modeli.
- Model dosyası `models/opportunity_ranker.pkl` şeklinde saklanacak, `ai.py` modülü yüklenecek.
- Eğitim pipeline'ı daha sonra eklenecek; şimdilik mock skorlayıcı kullanılacak.

## 4. Geliştirme Yol Haritası
1. Temel Python projesini kur (`pyproject.toml`, `src/mev_bot`).
2. RPC ve DEX istemcileri için adapterleri yaz.
3. Basit fiyat farkı tespiti + simülasyon.
4. Flashbots bundle gönderimi ve private tx akışı.
5. AI skorlayıcıyı gerçek verilerle eğit ve entegre et.
6. Monitoring ve alerting (Prometheus, Telegram botu).

## 5. Test ve Simülasyon
- Foundry veya Hardhat ile mainnet fork açıp, bilinen arbitraj senaryolarını canlandır.
- Unit test: Dex hesaplama fonksiyonları, gaz tahmini, skorlayıcı.
- Integration test: mock RPC + fake mempool eventleri ile uçtan uca senaryo.

## 6. Operasyonel Notlar
- Private key'leri `.env` veya HashiCorp Vault gibi gizli kasalarda tut.
- RPC sağlayıcısını (örn. Alchemy, Infura) websocket destekli seç.
- Flashbots için `relay.flashbots.net` endpoint'i ve `bundle_signer` anahtarına ihtiyaç var.
- Botu serverless değil çıplak VPS / bare metal üzerinde, düşük latency için Avrupa'da konumlandır.
