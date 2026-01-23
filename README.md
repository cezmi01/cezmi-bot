# cezmi-bot

Paribu order book kademe problemini Binance Futures hedge ile
avantaja ceviren otomatik bot. Bot, Binance fiyati TL'ye cevirip
1% kar esigi uzerindeki ilk 3 alis ve ilk 3 satis seviyesinde
limit emirlerini tutar. Paribu'da alis gerceklesince Binance Futures
cross 5x short acar, satis gerceklesince hedge'i kapatir.

> Not: Paribu API endpoint ve imza ayarlari ornek olarak gelmistir.
> Kendi Paribu API dokumaniniza gore `config.json` dosyasini guncelleyin.

## Ozellikler
- Her iki tarafta 3 kademe limit emir tutma
- Binance Futures + Binance USDT/TRY fiyatina gore TL referans
- %1 kar esigi altina inince en yakin kademeyi ileri kaydirma
- Kismi dolumlari hedge etme
- GUI (Tkinter) ve headless calisma
- Dry-run modu

## Kurulum
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` olusturun:
```bash
PARIBU_API_KEY=...
PARIBU_API_SECRET=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

`config.json` dosyasinda Paribu endpointlerini ve parite
eslesmelerini guncelleyin. `clientOrderId` desteklenmiyorsa
`manage_all_orders=true` yapabilirsiniz (bot tum acik emirleri yonetir).
Ornek:
```json
{
  "pairs": [
    {
      "name": "LINEA/TRY",
      "paribu_symbol": "LINEA_TL",
      "binance_futures_symbol": "LINEAUSDT",
      "tick_size": "0.01",
      "qty_step": "0.1",
      "min_qty": "1"
    }
  ]
}
```

## Calistirma (GUI)
```bash
python app.py
```

GUI'de:
- Parite secin
- Emir miktarini girin (coin bazinda)
- Kar yuzdesi (varsayilan 1)
- Polling suresi
- Leverage (varsayilan 5)
- Dry-run isaretleyin (onerilir)

## Calistirma (Headless)
```bash
python app.py --headless --pair "LINEA/TRY" --order-qty 100 --profit-pct 1 --poll-interval 2
```

## Windows EXE olusturma
EXE sadece Windows'ta build edilmelidir:
```powershell
pip install pyinstaller
pyinstaller --onefile --windowed app.py
```
`dist/app.exe` dosyasini kullanabilirsiniz.

## Uyari
Bu proje yatirim tavsiyesi degildir. Gercek para ile calistirmadan
once `dry-run` ile test edin ve Paribu/Binance limitlerini dogrulayin.