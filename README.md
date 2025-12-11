# ERC-20 MEV Arbitrage Bot

Bu repo, ERC-20 ağında (Ethereum ve diğer EVM zincirleri) çalışan, yapay zeka destekli bir MEV arbitraj botu için Python iskeletini içerir. Amaç, Uniswap v2/türevleri gibi havuzlarda oluşan fiyat farklılıklarını tespit edip Flashbots üzerinden güvenli şekilde yayınlayabilecek modüler bir altyapı sunmaktır.

## Özellikler
- `pydantic` tabanlı yapılandırma ve `.env` desteği
- Async `web3` ile RPC + mempool dinleme altyapısı
- Uniswap v2 uyumlu havuzlar için fiyat simülasyonları
- Yapay zeka / ML skorlayıcı için hazırlıklı modül (`scikit-learn` fallback)
- Flashbots bundle gönderimi için temel executor
- Ayrıntılı mimari: `docs/architecture.md`

## Kurulum
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Çevre Değişkenleri
`.env` dosyasına aşağıdakileri ekleyin:
```
MEV_RPC_URL=https://mainnet.infura.io/v3/xxx
MEV_WS_URL=wss://mainnet.infura.io/ws/v3/xxx
MEV_PRIVATE_KEY=0x...
MEV_ACCOUNT_ADDRESS=0x...
```
`MEV_TARGET_PAIRS` gibi kompleks listeler henüz JSON ile desteklenmiyor; bunun yerine `config.py` içindeki varsayılanları düzenleyebilirsiniz.

## Çalıştırma
```bash
python -m mev_bot
```
> Demo amaçlıdır; gerçek arbitraj için havuz adresleri, gaz hesapları ve strateji mantığı genişletilmelidir.

## Yol Haritası
1. `build_candidate_paths` fonksiyonunu gerçek token/pool grafikleriyle doldur.
2. Gerçek mempool olaylarından fırsat üretmek için pending tx analizini uygula.
3. Flashbots bundle'larını imzalayıp hedef bloğa gönderecek mantığı tamamla.
4. `ai.py` içerisindeki scorer'ı gerçek verilerle eğitilmiş bir modele bağla.

Ayrıntılar ve mimari diyagram için `docs/architecture.md` dosyasına bakabilirsiniz.
