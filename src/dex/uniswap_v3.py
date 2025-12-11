"""
Uniswap V3 integration
"""

from typing import Optional, Dict
from web3 import Web3
from .base_dex import BaseDEX
from .abi import UNISWAP_V3_QUOTER_ABI, UNISWAP_V3_ROUTER_ABI


class UniswapV3(BaseDEX):
    """Uniswap V3 DEX integration"""
    
    def __init__(self, config, w3: Web3):
        super().__init__(config, w3, "uniswap_v3")
        
        # Load quoter contract
        quoter_address = config.get("dex.uniswap_v3.quoter")
        if quoter_address:
            self.quoter = w3.eth.contract(
                address=Web3.to_checksum_address(quoter_address),
                abi=UNISWAP_V3_QUOTER_ABI
            )
    
    def _load_abis(self):
        """Load Uniswap V3 ABIs"""
        self.factory_abi = []  # V3 factory not used in same way
        self.router_abi = UNISWAP_V3_ROUTER_ABI
        self.quoter_abi = UNISWAP_V3_QUOTER_ABI
    
    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """V3 uses pools, not pairs - returns None"""
        # V3 has multiple pools per pair with different fees
        return None
    
    def get_reserves(self, token_a: str, token_b: str):
        """V3 doesn't use simple reserves - returns None"""
        # V3 uses concentrated liquidity model
        return None
    
    def get_amount_out(
        self,
        amount_in: int,
        token_in: str,
        token_out: str,
        fee: int = 3000  # 0.3% default
    ) -> int:
        """Get output amount for a swap"""
        try:
            amount_out = self.quoter.functions.quoteExactInputSingle(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                fee,
                amount_in,
                0  # sqrtPriceLimitX96 = 0 means no price limit
            ).call()
            
            return amount_out
        
        except Exception as e:
            self.logger.debug(f"Error getting amount out: {e}")
            return 0
    
    def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        recipient: str,
        deadline: int,
        fee: int = 3000
    ) -> Dict:
        """Build a swap transaction for V3"""
        params = {
            "tokenIn": Web3.to_checksum_address(token_in),
            "tokenOut": Web3.to_checksum_address(token_out),
            "fee": fee,
            "recipient": Web3.to_checksum_address(recipient),
            "deadline": deadline,
            "amountIn": amount_in,
            "amountOutMinimum": min_amount_out,
            "sqrtPriceLimitX96": 0
        }
        
        function = self.router.functions.exactInputSingle(params)
        
        return {
            "function": function,
            "value": 0
        }
