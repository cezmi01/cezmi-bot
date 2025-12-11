"""
Back-running strategy
"""

from typing import Optional, Dict
from web3 import Web3
from eth_account.signers.local import LocalAccount

from .base_strategy import BaseStrategy
from ..dex.uniswap_v2 import UniswapV2
from ..utils.gas_optimizer import GasOptimizer
from ..utils.profit_calculator import ProfitCalculator


class BackrunStrategy(BaseStrategy):
    """
    Back-running strategy
    
    Monitors for large transactions and immediately executes
    a transaction after them to profit from price changes
    """
    
    def __init__(self, config, w3: Web3, account: LocalAccount):
        super().__init__(config, w3, account, "Backrun")
        
        # Initialize DEX
        self.uniswap = UniswapV2(config, w3)
        
        # Initialize utilities
        self.gas_optimizer = GasOptimizer(config, w3)
        self.profit_calculator = ProfitCalculator(config, w3)
        
        # Strategy parameters
        self.monitor_large_swaps = self.strategy_config.get("monitor_large_swaps", True)
        self.min_swap_size_eth = self.strategy_config.get("min_swap_size_eth", 10)
        
        self.logger.info("Back-run strategy initialized")
    
    async def analyze(self, tx_hash: str, tx_data: Dict) -> Optional[Dict]:
        """
        Analyze transaction for back-running opportunity
        
        Looks for large swaps that create temporary price discrepancies
        """
        try:
            # Check if it's a swap on Uniswap
            to_address = tx_data.get("to", "").lower()
            if to_address != self.uniswap.router_address.lower():
                return None
            
            # Decode swap
            input_data = tx_data.get("input", "0x")
            function_selector = input_data[:10]
            
            # Check if it's a swap
            if function_selector not in ["0x38ed1739", "0x7ff36ab5", "0x18cbafe5"]:
                return None
            
            value = tx_data.get("value", 0)
            
            # Check if swap is large enough
            min_value = Web3.to_wei(self.min_swap_size_eth, "ether")
            if value < min_value:
                return None
            
            # After a large swap, prices might be temporarily favorable
            # We can back-run to profit from the price movement
            
            # Estimate opportunity
            # In production: simulate the victim's trade and calculate
            # the optimal back-run trade
            
            estimated_profit = int(value * 0.01)  # 1% of trade size
            
            gas_price = tx_data.get("gasPrice", 0)
            our_gas_price = int(gas_price * 1.1)  # Slightly higher to execute right after
            gas_cost = 200000 * our_gas_price
            
            if not self.is_profitable(estimated_profit, gas_cost):
                return None
            
            self.logger.info(f"Back-run opportunity found!")
            self.logger.info(f"Large swap: {Web3.from_wei(value, 'ether')} ETH")
            
            return {
                "type": "backrun",
                "target_tx_hash": tx_hash,
                "swap_size": value,
                "gas_price": our_gas_price,
                "profit": estimated_profit,
                "gas_cost": gas_cost,
                "net_profit": estimated_profit - gas_cost
            }
        
        except Exception as e:
            self.logger.debug(f"Error analyzing for back-run: {e}")
            return None
    
    async def execute(self, opportunity: Dict) -> Dict:
        """
        Execute back-run
        
        Submit our transaction to execute immediately after target transaction
        """
        try:
            self.logger.info("Executing back-run...")
            
            # In production:
            # 1. Wait for target transaction to be included in block
            # 2. Immediately submit our transaction
            # 3. Or use Flashbots to bundle both transactions
            
            self.logger.warning("Back-run execution is demonstration only")
            
            return {
                "success": False,
                "error": "Back-running requires precise timing and block monitoring",
                "simulated_profit": opportunity["net_profit"]
            }
        
        except Exception as e:
            self.logger.error(f"Error executing back-run: {e}")
            return {
                "success": False,
                "error": str(e)
            }
