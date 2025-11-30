#!/bin/bash
# Cezmi Bot Launcher Script
# Bu script bot'u doğru Python versiyonu ile çalıştırır

set -e

echo "🤖 Cezmi Bot başlatılıyor..."
echo ""

# Python versiyonunu tespit et
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌ Python bulunamadı! Lütfen Python 3.8+ yükleyin."
    exit 1
fi

echo "📍 Python: $PYTHON ($($PYTHON --version))"
echo ""

# Dependencies kontrolü
echo "🔍 Dependencies kontrol ediliyor..."
if ! $PYTHON -c "import aiohttp" &> /dev/null; then
    echo "⚠️  aiohttp yüklü değil!"
    echo "🔧 Yükleniyor..."
    $PYTHON -m pip install -r requirements.txt
fi

if ! $PYTHON -c "import dotenv" &> /dev/null; then
    echo "⚠️  python-dotenv yüklü değil!"
    echo "🔧 Yükleniyor..."
    $PYTHON -m pip install -r requirements.txt
fi

echo "✅ Dependencies OK"
echo ""

# .env kontrolü
if [ ! -f .env ]; then
    echo "⚠️  .env dosyası bulunamadı!"
    echo "💡 .env.example'ı .env olarak kopyalayın ve API key'lerinizi girin:"
    echo "   cp .env.example .env"
    echo "   nano .env  # veya vim, code, vb."
    echo ""
    read -p "Devam etmek istiyor musunuz? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Config kontrolü
if [ ! -f config.json ]; then
    echo "❌ config.json bulunamadı!"
    exit 1
fi

echo "🔍 Config validation..."
if $PYTHON validate_config.py; then
    echo ""
    echo "✅ Tüm kontroller tamamlandı!"
    echo ""
else
    echo ""
    echo "⚠️  Config'te bazı sorunlar var!"
    echo "💡 Adresleri güncellemek için:"
    echo "   $PYTHON address_fetcher.py manual"
    echo ""
    read -p "Yine de devam etmek istiyor musunuz? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 Bot başlatılıyor..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

$PYTHON bot.py

echo ""
echo "👋 Bot kapatıldı."
