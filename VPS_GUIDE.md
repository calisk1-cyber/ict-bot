# Kurumsal HFT Bot: VPS Güncelleme ve Dağıtım Kılavuzu

Bu kılavuz, Singularity V18 Omniscient ve sonraki sürümlerin VPS (Virtual Private Server) üzerinde nasıl güncelleneceğini ve çalıştırılacağını anlatır.

## 1. Kodları VPS'e Çekme (Güncelleme)

Her yeni özellik eklediğimizde kodları GitHub'a yüklüyorum. VPS'teki kodları güncellemek için şu komutları sırasıyla terminale yaz:

```bash
cd ~/Desktop/bot  # Botun yüklü olduğu klasöre git
git reset --hard  # Yerel değişiklikleri temizle (isteğe bağlı)
git pull origin main  # En son V18 kodlarını GitHub'tan çek
```

## 2. Ortamı Hazırlama

Yeni kütüphaneler eklenmiş olabilir (`oandapyV20` gibi). Bunları yüklemek için:

```bash
pip install -r requirements.txt
# Veya manuel:
pip install oandapyV20 pandas_ta yfinance python-dotenv
```

## 3. Botu Çalıştırma

Botu arka planda (terminal kapansa bile çalışacak şekilde) başlatmak için:

```bash
nohup python app.py &
```

Logları anlık izlemek için:
```bash
tail -f nohup.out
```

## 4. Oanda Backtest Denetimi

VPS üzerinde Oanda verileriyle en son performansı görmek için:

```bash
python backtest_v18_oanda.py
```

## Önemli Notlar
- **.env Dosyası:** VPS üzerindeki `.env` dosyasında `OANDA_API_KEY` ve `OANDA_ACCOUNT_ID` bilgilerinin doğru olduğundan emin ol.
- **Zaman Dilimi:** Sistem TSİ (GMT+3) zaman dilimine göre ayarlanmıştır. Herhangi bir kayma durumunda `ict_utils.py` içindeki saatleri kontrol et.
