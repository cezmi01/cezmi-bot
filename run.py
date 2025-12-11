#!/usr/bin/env python3
"""
MEV Bot Entry Point
"""

import sys
import asyncio
from src.mev_bot import MEVBot


def print_banner():
    """Print welcome banner"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║              🤖 CEZMI MEV BOT 🤖                         ║
    ║                                                           ║
    ║  Maximum Extractable Value Bot                           ║
    ║  Ethereum & EVM Blockchain Trading Bot                   ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    
    ⚠️  UYARI: Bu bot gerçek para ile çalışır!
    📖 Dokümantasyonu okuyun: README.md
    🧪 Önce testnet'te test edin
    💰 Küçük miktarlarla başlayın
    
    """
    print(banner)


def print_disclaimer():
    """Print disclaimer"""
    disclaimer = """
    ═══════════════════════════════════════════════════════════
    SORUMLULUK REDDİ
    ═══════════════════════════════════════════════════════════
    
    Bu yazılım EĞİTİM AMAÇLIDIR.
    
    MEV stratejileri:
    - Mali kayba yol açabilir
    - Etik sorunlar içerebilir  
    - Yasal riskler taşıyabilir
    
    Kullanımdan doğacak kayıplardan yazarlar sorumlu değildir.
    
    ═══════════════════════════════════════════════════════════
    
    Devam etmek için 'KABUL EDIYORUM' yazın: """
    
    confirmation = input(disclaimer)
    
    if confirmation.strip().upper() != "KABUL EDIYORUM":
        print("\n❌ Kullanım şartları kabul edilmedi. Çıkış yapılıyor...\n")
        sys.exit(0)


async def main():
    """Main entry point"""
    try:
        # Print banner
        print_banner()
        
        # Show disclaimer and get confirmation
        print_disclaimer()
        
        print("\n✓ Kullanım şartları kabul edildi\n")
        
        # Initialize bot
        print("Bot başlatılıyor...\n")
        bot = MEVBot()
        
        # Show wallet balance
        balance = bot.get_balance_eth()
        print(f"💰 Cüzdan bakiyesi: {balance:.4f} ETH\n")
        
        if balance < 0.1:
            print("⚠️  UYARI: Düşük bakiye! En az 0.1 ETH olması önerilir.\n")
        
        # Start bot
        await bot.start()
    
    except KeyboardInterrupt:
        print("\n\n👋 Bot kullanıcı tarafından durduruldu\n")
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGüle güle! 👋\n")
        sys.exit(0)
