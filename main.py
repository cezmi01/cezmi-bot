"""
MEV Bot Ana Çalıştırma Dosyası
"""
import sys
import logging
from web3 import Web3
from mev_bot import MEVBot
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Ana fonksiyon"""
    try:
        logger.info("=" * 50)
        logger.info("MEV Bot Başlatılıyor...")
        logger.info("=" * 50)
        
        # Bot'u başlat
        bot = MEVBot()
        
        # Örnek: WETH -> USDC arbitrajı için izleme
        # Miktar: 0.1 ETH (wei cinsinden)
        amount_in_wei = Web3.to_wei(0.1, 'ether')
        
        logger.info(f"İzleme başlatılıyor: WETH -> USDC")
        logger.info(f"Başlangıç miktarı: 0.1 ETH")
        logger.info(f"Minimum kar: %{Config.MIN_PROFIT_PERCENTAGE}")
        logger.info("=" * 50)
        
        # Bot'u çalıştır
        bot.monitor_and_trade(
            token_in=Config.WETH_ADDRESS,
            token_out=Config.USDC_ADDRESS,
            amount_in=amount_in_wei
        )
        
    except KeyboardInterrupt:
        logger.info("\nBot kullanıcı tarafından durduruldu.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Kritik hata: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
