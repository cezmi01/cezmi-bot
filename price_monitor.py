"""
Fiyat izleme ve arbitraj fırsatı tespit modülü
"""
from web3 import Web3
from config import Config
import logging
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Uniswap V2 Router ABI (getAmountsOut için)
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class PriceMonitor:
    """Fiyat izleme ve arbitraj tespiti"""
    
    def __init__(self, blockchain_manager):
        self.blockchain = blockchain_manager
        self.w3 = blockchain_manager.w3
        
    def get_price_from_uniswap_v2(self, token_in: str, token_out: str, amount_in: int) -> Optional[int]:
        """Uniswap V2'den fiyat al"""
        try:
            contract = self.w3.eth.contract(
                address=Config.UNISWAP_V2_ROUTER,
                abi=UNISWAP_V2_ROUTER_ABI
            )
            path = [token_in, token_out]
            amounts = contract.functions.getAmountsOut(amount_in, path).call()
            return amounts[-1]
        except Exception as e:
            logger.error(f"Uniswap V2 fiyat hatası: {e}")
            return None
    
    def get_price_from_sushiswap(self, token_in: str, token_out: str, amount_in: int) -> Optional[int]:
        """Sushiswap'ten fiyat al"""
        try:
            contract = self.w3.eth.contract(
                address=Config.SUSHISWAP_ROUTER,
                abi=UNISWAP_V2_ROUTER_ABI
            )
            path = [token_in, token_out]
            amounts = contract.functions.getAmountsOut(amount_in, path).call()
            return amounts[-1]
        except Exception as e:
            logger.error(f"Sushiswap fiyat hatası: {e}")
            return None
    
    def find_arbitrage_opportunity(
        self, 
        token_in: str, 
        token_out: str, 
        amount_in: int
    ) -> Optional[Dict]:
        """
        Arbitraj fırsatı bul
        
        Returns:
            {
                'buy_dex': 'uniswap_v2',
                'sell_dex': 'sushiswap',
                'amount_in': amount_in,
                'amount_out_buy': amount_out_buy,
                'amount_out_sell': amount_out_sell,
                'profit': profit,
                'profit_percentage': profit_percentage
            } veya None
        """
        # Her iki DEX'ten fiyatları al
        uniswap_price = self.get_price_from_uniswap_v2(token_in, token_out, amount_in)
        sushiswap_price = self.get_price_from_sushiswap(token_in, token_out, amount_in)
        
        if uniswap_price is None or sushiswap_price is None:
            return None
        
        # Arbitraj fırsatı kontrolü
        # Senaryo 1: Uniswap'tan al, Sushiswap'tan sat
        if uniswap_price < sushiswap_price:
            # Uniswap'tan al
            amount_out_buy = uniswap_price
            # Sushiswap'tan sat (ters yön)
            amount_out_sell = self.get_price_from_sushiswap(token_out, token_in, amount_out_buy)
            
            if amount_out_sell and amount_out_sell > amount_in:
                profit = amount_out_sell - amount_in
                profit_percentage = (profit / amount_in) * 100
                
                if profit_percentage >= Config.MIN_PROFIT_PERCENTAGE:
                    return {
                        'buy_dex': 'uniswap_v2',
                        'sell_dex': 'sushiswap',
                        'amount_in': amount_in,
                        'amount_out_buy': amount_out_buy,
                        'amount_out_sell': amount_out_sell,
                        'profit': profit,
                        'profit_percentage': profit_percentage
                    }
        
        # Senaryo 2: Sushiswap'tan al, Uniswap'tan sat
        elif sushiswap_price < uniswap_price:
            # Sushiswap'tan al
            amount_out_buy = sushiswap_price
            # Uniswap'tan sat (ters yön)
            amount_out_sell = self.get_price_from_uniswap_v2(token_out, token_in, amount_out_buy)
            
            if amount_out_sell and amount_out_sell > amount_in:
                profit = amount_out_sell - amount_in
                profit_percentage = (profit / amount_in) * 100
                
                if profit_percentage >= Config.MIN_PROFIT_PERCENTAGE:
                    return {
                        'buy_dex': 'sushiswap',
                        'sell_dex': 'uniswap_v2',
                        'amount_in': amount_in,
                        'amount_out_buy': amount_out_buy,
                        'amount_out_sell': amount_out_sell,
                        'profit': profit,
                        'profit_percentage': profit_percentage
                    }
        
        return None
    
    def calculate_slippage(self, expected_amount: int, actual_amount: int) -> float:
        """Slippage hesapla"""
        if expected_amount == 0:
            return 0
        return abs((expected_amount - actual_amount) / expected_amount) * 100
