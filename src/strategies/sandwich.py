"""
Sandwich attack strategy
"""

from typing import Optional, Dict
from web3 import Web3
from eth_account.signers.local import LocalAccount
import time

from .base_strategy import BaseStrategy
from ..dex.uniswap_v2 import UniswapV2
from ..dex.sushiswap import Sushiswap
from ..utils.profit_calculator import ProfitCalculator
from ..utils.gas_optimizer import GasOptimizer


class SandwichStrategy(BaseStrategy):
    """
    Sandwich attack strategy
    
    Detects large pending swaps and sandwiches them:
    1. Front-run: Buy before the victim's trade
    2. Victim's trade executes (pushes price up)
    3. Back-run: Sell after the victim's trade
    """
    
    def __init__(self, config, w3: Web3, account: LocalAccount):
        super().__init__(config, w3, account, "Sandwich")
        
        # Initialize DEXes
        self.dexes = {
            "uniswap_v2": UniswapV2(config, w3),
            "sushiswap": Sushiswap(config, w3),
        }
        
        # Initialize utilities
        self.profit_calculator = ProfitCalculator(config, w3)
        self.gas_optimizer = GasOptimizer(config, w3)
        
        # Strategy parameters
        self.slippage_threshold = self.strategy_config.get("slippage_threshold", 0.05)
        self.max_position_size_eth = self.strategy_config.get("max_position_size_eth", 50)
        self.target_dexes = self.strategy_config.get("target_dexes", ["uniswap_v2"])
        
        self.logger.info(f"Sandwich strategy targeting: {', '.join(self.target_dexes)}")
    
    async def analyze(self, tx_hash: str, tx_data: Dict) -> Optional[Dict]:
        """
        Analyze transaction for sandwich opportunity
        
        Looks for large swaps that will cause significant price impact
        """
        try:
            # Decode the swap transaction
            swap_info = self._decode_swap(tx_data)
            if not swap_info:
                return None
            
            dex_name = swap_info["dex"]
            token_in = swap_info["token_in"]
            token_out = swap_info["token_out"]
            amount_in = swap_info["amount_in"]
            
            # Check if DEX is in our target list
            if dex_name not in self.target_dexes:
                return None
            
            # Check if trade size is significant enough
            min_trade_size = Web3.to_wei(1, "ether")  # 1 ETH minimum
            if amount_in < min_trade_size:
                return None
            
            # Get DEX instance
            dex = self.dexes.get(dex_name)
            if not dex:
                return None
            
            # Calculate price impact
            reserves = dex.get_reserves(token_in, token_out)
            if not reserves:
                return None
            
            reserve_in, reserve_out = reserves
            
            price_impact = self.profit_calculator.calculate_price_impact(
                amount_in,
                reserve_in,
                reserve_out
            )
            
            # Check if price impact is high enough to sandwich
            if price_impact < self.slippage_threshold:
                return None
            
            # Calculate optimal sandwich amounts
            frontrun_amount = self._calculate_frontrun_amount(
                amount_in,
                reserve_in,
                reserve_out,
                price_impact
            )
            
            if frontrun_amount == 0:
                return None
            
            # Estimate profit
            profit = self._estimate_sandwich_profit(
                frontrun_amount,
                amount_in,
                reserve_in,
                reserve_out,
                dex
            )
            
            # Calculate gas costs (2 transactions: frontrun + backrun)
            victim_gas_price = tx_data.get("gasPrice", 0)
            frontrun_gas_price = self.gas_optimizer.get_frontrun_gas_price(victim_gas_price)
            
            if not frontrun_gas_price:
                return None
            
            gas_cost = (200000 + 200000) * frontrun_gas_price  # Approximate gas for both txs
            
            # Check profitability
            if not self.is_profitable(profit, gas_cost):
                return None
            
            self.logger.info(f"Sandwich opportunity found!")
            self.logger.info(f"Victim trade: {Web3.from_wei(amount_in, 'ether')} ETH")
            self.logger.info(f"Price impact: {price_impact * 100:.2f}%")
            self.logger.info(f"Expected profit: {Web3.from_wei(profit - gas_cost, 'ether')} ETH")
            
            return {
                "type": "sandwich",
                "victim_tx_hash": tx_hash,
                "victim_gas_price": victim_gas_price,
                "dex": dex_name,
                "token_in": token_in,
                "token_out": token_out,
                "victim_amount": amount_in,
                "frontrun_amount": frontrun_amount,
                "frontrun_gas_price": frontrun_gas_price,
                "price_impact": price_impact,
                "profit": profit,
                "gas_cost": gas_cost,
                "net_profit": profit - gas_cost
            }
        
        except Exception as e:
            self.logger.debug(f"Error analyzing for sandwich: {e}")
            return None
    
    def _decode_swap(self, tx_data: Dict) -> Optional[Dict]:
        """Decode swap transaction"""
        try:
            to_address = tx_data.get("to", "").lower()
            
            # Identify DEX
            dex_name = None
            for name, dex in self.dexes.items():
                if to_address == dex.router_address.lower():
                    dex_name = name
                    break
            
            if not dex_name:
                return None
            
            # Extract swap details from transaction
            # In production, properly decode the transaction input
            input_data = tx_data.get("input", "0x")
            function_selector = input_data[:10]
            
            # Check if it's a swap function
            swap_selectors = ["0x38ed1739", "0x7ff36ab5", "0x18cbafe5"]
            if function_selector not in swap_selectors:
                return None
            
            # Placeholder values - in production, decode properly
            return {
                "dex": dex_name,
                "token_in": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                "token_out": "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
                "amount_in": tx_data.get("value", 0) or Web3.to_wei(5, "ether")
            }
        
        except Exception as e:
            self.logger.debug(f"Error decoding swap: {e}")
            return None
    
    def _calculate_frontrun_amount(
        self,
        victim_amount: int,
        reserve_in: int,
        reserve_out: int,
        price_impact: float
    ) -> int:
        """
        Calculate optimal front-run amount
        
        Args:
            victim_amount: Victim's trade amount
            reserve_in: Input token reserve
            reserve_out: Output token reserve
            price_impact: Victim's price impact
            
        Returns:
            Optimal front-run amount
        """
        # Use a fraction of victim's amount based on price impact
        # Higher impact = larger front-run
        multiplier = min(price_impact * 10, 1.0)  # Cap at 1.0
        frontrun_amount = int(victim_amount * multiplier * 0.5)  # Use 50% of calculated
        
        # Cap at max position size
        max_amount = Web3.to_wei(self.max_position_size_eth, "ether")
        frontrun_amount = min(frontrun_amount, max_amount)
        
        # Minimum amount
        min_amount = Web3.to_wei(0.1, "ether")
        if frontrun_amount < min_amount:
            return 0
        
        return frontrun_amount
    
    def _estimate_sandwich_profit(
        self,
        frontrun_amount: int,
        victim_amount: int,
        reserve_in: int,
        reserve_out: int,
        dex
    ) -> int:
        """
        Estimate profit from sandwich attack
        
        Args:
            frontrun_amount: Our front-run amount
            victim_amount: Victim's amount
            reserve_in: Input reserve
            reserve_out: Output reserve
            dex: DEX instance
            
        Returns:
            Estimated profit in wei
        """
        # Step 1: Our front-run buy
        tokens_bought = self.profit_calculator.calculate_swap_output(
            frontrun_amount,
            reserve_in,
            reserve_out,
            dex.fee
        )
        
        # Update reserves
        new_reserve_in = reserve_in + frontrun_amount
        new_reserve_out = reserve_out - tokens_bought
        
        # Step 2: Victim's trade (pushes price up)
        victim_tokens = self.profit_calculator.calculate_swap_output(
            victim_amount,
            new_reserve_in,
            new_reserve_out,
            dex.fee
        )
        
        # Update reserves again
        final_reserve_in = new_reserve_in + victim_amount
        final_reserve_out = new_reserve_out - victim_tokens
        
        # Step 3: Our back-run sell
        eth_received = self.profit_calculator.calculate_swap_output(
            tokens_bought,
            final_reserve_out,
            final_reserve_in,
            dex.fee
        )
        
        # Calculate profit
        profit = eth_received - frontrun_amount
        
        return max(0, profit)
    
    async def execute(self, opportunity: Dict) -> Dict:
        """
        Execute sandwich attack
        
        This requires precise timing and typically uses Flashbots or similar
        to ensure transaction ordering
        """
        try:
            # In production, this would:
            # 1. Build front-run transaction with higher gas
            # 2. Submit to Flashbots bundle with victim tx
            # 3. Build back-run transaction
            # 4. Submit entire bundle atomically
            
            self.logger.info("Executing sandwich attack...")
            
            # For demonstration, we'll just log the opportunity
            # Real implementation requires Flashbots integration
            
            self.logger.warning("Sandwich execution requires Flashbots integration")
            self.logger.warning("This is a demonstration - not executing on-chain")
            
            return {
                "success": False,
                "error": "Flashbots integration required for sandwich attacks",
                "simulated_profit": opportunity["net_profit"]
            }
        
        except Exception as e:
            self.logger.error(f"Error executing sandwich: {e}")
            return {
                "success": False,
                "error": str(e)
            }
