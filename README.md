# cezmi-bot

Paribu manuel emir araci (Windows .exe) icin basit GUI.

## Gereksinimler
- Python 3.10+ (Windows)
- requirements.txt

## Kurulum
```bash
python3 -m pip install -r requirements.txt
```

## Calistirma
```bash
python3 manual_bot.py
```

## Ayarlar
Ayarlar tabinda Paribu API key/secret girin.

Alternatif:
- PARIBU_API_KEY
- PARIBU_API_SECRET

## Binance fiyat
Market girisi `ada_tl` ise once coin adi cikartilir (ADA) ve Binance
`exchangeInfo` uzerinden eslestirilir. Uygun sembol bulunursa otomatik
guncellenir (ornegin `ADAUSDT`).

## Emir gonderme
- Market, Islem (Al/Sat)
- 6 sutun: Fiyat / Miktar / Tekrar / Aralik (ms)
- Tekrar: `0 = suresiz`, `>0 = tekrar sayisi`
- Stop: yeni emir gonderimini durdurur, acik emirleri iptal etmez.

## Manuel Satis Listesi
- Sadece bu botun gonderdigi emirler
- Kismi ve tam gerceklesenler listelenir
- Loglar `logs/YYYY-MM-DD.jsonl`
- 24 saat sonra otomatik silinir

## EXE build
```bash
python3 -m PyInstaller --onefile --noconsole --name paribu-manuel-bot manual_bot.py
```