# cezmi-bot

API'den veri çeken ve adresleri kaydeden bot.

## Kurulum

```bash
pip install -r requirements.txt
```

## Kullanım

### Temel Kullanım

```bash
python bot.py
```

### Ortam Değişkenleri ile

```bash
export API_URL="https://api.example.com/addresses"
python bot.py
```

## Yapılandırma

Bot'u kullanmak için `bot.py` dosyasındaki `main()` fonksiyonunda API URL'ini ve parametreleri ayarlayın.

## Özellikler

- ✅ API'den veri çekme
- ✅ Adres çıkarma ve kaydetme
- ✅ Duplikasyon kontrolü
- ✅ JSON formatında kayıt
- ✅ Hata yönetimi

## Dosyalar

- `bot.py` - Ana bot kodu
- `addresses.json` - Kaydedilen adresler (otomatik oluşturulur)
- `requirements.txt` - Python bağımlılıkları