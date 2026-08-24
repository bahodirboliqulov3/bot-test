#!/bin/bash
# ====================================================================
# Telegram Test Platform — 1-Click Server Deployment Script
# Supports: Ubuntu 20.04 / 22.04 / 24.04 LTS & Debian 11 / 12
# ====================================================================

set -e

echo '🚀 [1/4] Server paketlari yangilanmoqda...'
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git ufw tzdata

echo '⏱ [2/4] Toshkent vaqt zonasi sozlanmoqda (Asia/Tashkent)...'
sudo timedatectl set-timezone Asia/Tashkent

echo '🐳 [3/4] Docker va Docker Compose o‘rnatilmoqda...'
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker 
    rm -f get-docker.sh
fi

if ! command -v docker-compose &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin docker-compose || true
fi

echo '📁 [4/4] Papkalar va ruxsatlar tayyorlanmoqda...'
mkdir -p storage/certificates storage/exports storage/uploads storage/logs storage/data
chmod -R 777 storage

echo '🚀 Bot konteynerlari ishga tushirilmoqda...'
docker compose down || true
docker compose up -d --build

echo ''
echo '===================================================================='
echo '🎉 TABRIKLAYMIZ! BOT SERVERDA 24/7 REJIMDA ISHGA TUSHDI!'
echo '===================================================================='
echo '📊 Konteynerlar holati:    docker compose ps'
echo '📜 Jonli loglarni ko‘rish: docker compose logs -f bot'
echo '🔄 Qayta ishga tushirish:  docker compose restart bot'
echo '🛑 To‘xtatish:             docker compose down'
echo '===================================================================='