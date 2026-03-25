#!/bin/bash

# Ubuntu Sunucu Hazırlık Scripti
echo "🚀 Sunucu kurulumu başlatılıyor..."

# 1. Güncellemeler ve Temel Paketler
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nodejs npm git

# 2. Node.js Güncelleme (Son stable versiyon için)
sudo npm install -g n
sudo n stable
hash -r

# 3. PM2 Kurulumu
sudo npm install -g pm2

# 4. Bağımlılıkları Kur
echo "📦 Bağımlılıklar yükleniyor..."
pip3 install -r requirements.txt
npm install

echo "✅ Kurulum tamamlandı!"
echo "-----------------------------------"
echo "Botu başlatmak için şu komutu çalıştırın:"
echo "pm2 start ecosystem.config.js"
echo "-----------------------------------"
echo "Logları izlemek için: pm2 logs"
