"""
Uniswap V2 integration
"""

from typing import Tuple, Optional, Dict
from web3 import Web3
from .base_dex import BaseDEX
from .abi import (
    UNISWAP_V2_FACTORY_ABI,
    UNISWAP_V2_ROUTER_ABI,
    UNISWAP_V2_PAIR_ABI
)


class UniswapV2(BaseDEX):
    """Uniswap V2 DEX integration"""
    
    def __init__(self, config, w3: Web3):
        super().__init__(config, w3, "uniswap_v2")
    
    def _load_abis(self):
        """Load Uniswap V2 ABIs"""
        self.factory_abi = UNISWAP_V2_FACTORY_ABI
        self.router_abi = UNISWAP_V2_ROUTER_ABI
        self.pair_abi = UNISWAP_V2_PAIR_ABI
    
    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """Get pair address for two tokens"""
        try:
            pair_address = self.factory.functions.getPair(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b)
            ).call()
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return None
            
            return pair_address
        except Exception as e:
            self.logger.debug(f"Error getting pair address: {e}")
            return None
    
    def get_reserves(self, token_a: str, token_b: str) -> Optional[Tuple[int, int]]:
        """Get reserves for a trading pair"""
        try:
            pair_address = self.get_pair_address(token_a, token_b)
            if not pair_address:
                return None
            
            pair_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(pair_address),
                abi=self.pair_abi
            )
            
            # Get token order
            token0 = pair_contract.functions.token0().call()
            
            # Get reserves
            reserves = pair_contract.functions.getReserves().call()
            reserve0, reserve1, _ = reserves
            
            # Return reserves in correct order
            if token0.lower() == token_a.lower():
                return (reserve0, reserve1)
            else:
                return (reserve1, reserve0)
        
        except Exception as e:
            self.logger.debug(f"Error getting reserves: {e}")
            return None
    
    def get_amount_out(self, amount_in: int, token_in: str, token_out: str) -> int:
        """Get output amount for a swap"""
        try:
            path = [
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out)
            ]
            
            amounts = self.router.functions.getAmountsOut(
                amount_in,
                path
            ).call()
            
            return amounts[-1]
        
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
        deadline: int
    ) -> Dict:
        """Build a swap transaction"""
        path = [
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out)
        ]
        
        # Check if swapping from ETH
        weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH on mainnet
        
        if token_in.lower() == weth_address.lower():
            # Use swapExactETHForTokens
            function = self.router.functions.swapExactETHForTokens(
                min_amount_out,
                path,
                Web3.to_checksum_address(recipient),
                deadline
            )
            
            return {
                "function": function,
                "value": amount_in
            }
        
        elif token_out.lower() == weth_address.lower():
            # Use swapExactTokensForETH
            function = self.router.functions.swapExactTokensForETH(
                amount_in,
                min_amount_out,
                path,
                Web3.to_checksum_address(recipient),
                deadline
            )
            
            return {
                "function": function,
                "value": 0
            }
        
        else:
            # Use swapExactTokensForTokens
            function = self.router.functions.swapExactTokensForTokens(
                amount_in,
                min_amount_out,
                path,
                Web3.to_checksum_address(recipient),
                deadline
            )
            
            return {
                "function": function,
                "value": 0
            }
