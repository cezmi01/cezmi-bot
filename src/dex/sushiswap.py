"""
Sushiswap integration (Uniswap V2 fork)
"""

from web3 import Web3
from .uniswap_v2 import UniswapV2


class Sushiswap(UniswapV2):
    """Sushiswap DEX integration (Uniswap V2 compatible)"""
    
    def __init__(self, config, w3: Web3):
        # Initialize with base class but override name
        self.config = config
        self.w3 = w3
        self.name = "sushiswap"
        
        # Call BaseDEX init directly
        from .base_dex import BaseDEX
        BaseDEX.__init__(self, config, w3, "sushiswap")
