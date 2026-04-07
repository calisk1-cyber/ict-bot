#!/bin/bash
# ============================================================
#  ICT Bot - VPS Deployment Script
#  Çalıştır: bash deploy.sh
# ============================================================
set -e

BOT_DIR="/root/bot"
LOG_DIR="$BOT_DIR/logs"

echo "=================================================="
echo " 🚀 ICT Bot VPS Deployment Başlatılıyor..."
echo "=================================================="

# 1. Güncelleme ve temel paketler
echo ""
echo "📦 [1/7] Sistem güncelleniyor..."
apt update -y && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl

# 2. Node.js kurulumu (v20 LTS)
if ! command -v node &> /dev/null; then
    echo ""
    echo "📦 [2/7] Node.js kuruluyor..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
else
    echo "✅ [2/7] Node.js zaten kurulu: $(node -v)"
fi

# 3. PM2 kurulumu
if ! command -v pm2 &> /dev/null; then
    echo ""
    echo "📦 [3/7] PM2 kuruluyor..."
    npm install -g pm2
else
    echo "✅ [3/7] PM2 zaten kurulu: $(pm2 -v)"
fi

# 4. Log dizini oluştur
echo ""
echo "📁 [4/7] Log dizini oluşturuluyor: $LOG_DIR"
mkdir -p "$LOG_DIR"

# 5. Python bağımlılıklarını kur
echo ""
echo "🐍 [5/7] Python bağımlılıkları yükleniyor..."
cd "$BOT_DIR"
pip3 install -r requirements.txt

# 6. Node bağımlılıklarını kur
echo ""
echo "⬡  [6/7] Node bağımlılıkları yükleniyor..."
npm install

# 7. PM2 ile botları başlat
echo ""
echo "🤖 [7/7] PM2 ile tüm botlar başlatılıyor..."

# Eski oturumu temizle (varsa)
pm2 delete all 2>/dev/null || true

# Ekosistemi başlat
pm2 start ecosystem.config.js

# Reboot sonrası otomatik başlatma ayarı
echo ""
echo "💾 PM2 startup ayarlanıyor (reboot sonrası otomatik başlar)..."
pm2 startup systemd -u root --hp /root
pm2 save

# Sonuç
echo ""
echo "=================================================="
echo " ✅ DEPLOYMENT TAMAMLANDI!"
echo "=================================================="
echo ""
pm2 status
echo ""
echo "📋 Logları izlemek için:"
echo "   pm2 logs              → tüm botlar"  
echo "   pm2 logs bot4-trader  → sadece trader"
echo "   pm2 monit             → canlı monitoring"
echo ""
echo "🔄 Yeniden başlatmak için:"
echo "   pm2 restart all"
echo "   pm2 restart bot4-trader"
echo ""
