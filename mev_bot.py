"""
MEV Bot Ana Modülü
"""
import time
import logging
from web3 import Web3
from blockchain import BlockchainManager
from price_monitor import PriceMonitor
from config import Config
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Uniswap V2 Router ABI (swap için)
UNISWAP_V2_SWAP_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

class MEVBot:
    """MEV Bot Ana Sınıfı"""
    
    def __init__(self):
        logger.info("MEV Bot başlatılıyor...")
        Config.validate()
        
        self.blockchain = BlockchainManager()
        self.price_monitor = PriceMonitor(self.blockchain)
        self.w3 = self.blockchain.w3
        self.running = False
        
        logger.info("MEV Bot hazır!")
    
    def get_router_address(self, dex_name: str) -> str:
        """DEX router adresini al"""
        routers = {
            'uniswap_v2': Config.UNISWAP_V2_ROUTER,
            'sushiswap': Config.SUSHISWAP_ROUTER
        }
        return routers.get(dex_name.lower())
    
    def execute_arbitrage(self, opportunity: dict) -> bool:
        """Arbitraj fırsatını gerçekleştir"""
        try:
            logger.info(f"Arbitraj fırsatı bulundu! Kar: %{opportunity['profit_percentage']:.2f}")
            
            # Pozisyon büyüklüğünü kontrol et
            amount_in_eth = self.w3.from_wei(opportunity['amount_in'], 'ether')
            if amount_in_eth > Config.MAX_POSITION_SIZE_ETH:
                logger.warning(f"Pozisyon çok büyük: {amount_in_eth} ETH (max: {Config.MAX_POSITION_SIZE_ETH})")
                return False
            
            # Bakiye kontrolü
            balance = self.blockchain.get_balance()
            if amount_in_eth > balance:
                logger.warning(f"Yetersiz bakiye: {balance} ETH (gerekli: {amount_in_eth})")
                return False
            
            # Gas fiyatı kontrolü
            gas_price = self.blockchain.get_gas_price()
            if gas_price > Config.MAX_GAS_PRICE_GWEI:
                logger.warning(f"Gas fiyatı çok yüksek: {gas_price} Gwei")
                return False
            
            # Slippage toleransı ile minimum çıktı hesapla
            slippage_multiplier = 1 - (Config.SLIPPAGE_TOLERANCE / 100)
            amount_out_min = int(opportunity['amount_out_sell'] * slippage_multiplier)
            
            buy_dex = opportunity['buy_dex']
            sell_dex = opportunity['sell_dex']
            
            # İlk swap: Token A -> Token B (buy_dex'te)
            buy_router = self.get_router_address(buy_dex)
            buy_contract = self.w3.eth.contract(address=buy_router, abi=UNISWAP_V2_SWAP_ABI)
            
            # İkinci swap: Token B -> Token A (sell_dex'te)
            sell_router = self.get_router_address(sell_dex)
            sell_contract = self.w3.eth.contract(address=sell_router, abi=UNISWAP_V2_SWAP_ABI)
            
            # Token adresleri (örnek: WETH ve USDC)
            token_in = Config.WETH_ADDRESS
            token_out = Config.USDC_ADDRESS
            
            deadline = int(time.time()) + 300  # 5 dakika
            
            # İlk swap işlemi
            path1 = [token_in, token_out]
            tx1 = buy_contract.functions.swapExactTokensForTokens(
                opportunity['amount_in'],
                int(opportunity['amount_out_buy'] * slippage_multiplier),
                path1,
                self.blockchain.address,
                deadline
            ).build_transaction({
                'from': self.blockchain.address,
                'value': 0,
                'gas': Config.GAS_LIMIT
            })
            
            # İkinci swap işlemi (burada gerçek uygulamada flash loan veya önceki işlemin sonucunu beklemek gerekir)
            # Basit versiyon için sadece ilk swap'ı gösteriyoruz
            logger.warning("NOT: Bu basit bir örnek. Gerçek arbitraj için flash loan veya iki aşamalı swap gerekir.")
            
            tx_hash = self.blockchain.send_transaction(tx1)
            if tx_hash:
                logger.info(f"İlk swap gönderildi: {tx_hash}")
                # İşlemin onaylanmasını bekle
                if self.blockchain.wait_for_transaction(tx_hash):
                    logger.info("Arbitraj işlemi tamamlandı!")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Arbitraj işlemi hatası: {e}")
            return False
    
    def monitor_and_trade(self, token_in: str, token_out: str, amount_in: int):
        """Fiyatları izle ve arbitraj fırsatlarını yakala"""
        self.running = True
        logger.info(f"İzleme başlatıldı: {token_in} -> {token_out}")
        
        while self.running:
            try:
                # Arbitraj fırsatı ara
                opportunity = self.price_monitor.find_arbitrage_opportunity(
                    token_in, token_out, amount_in
                )
                
                if opportunity:
                    logger.info(f"Arbitraj fırsatı: {opportunity}")
                    # Fırsatı gerçekleştir
                    self.execute_arbitrage(opportunity)
                else:
                    logger.debug("Arbitraj fırsatı bulunamadı")
                
                # Bekle
                time.sleep(Config.POLL_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Bot durduruluyor...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"İzleme hatası: {e}")
                time.sleep(Config.POLL_INTERVAL)
    
    def stop(self):
        """Botu durdur"""
        self.running = False
        logger.info("Bot durduruldu")
