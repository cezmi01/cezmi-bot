"""
Arbitrage strategy - exploits price differences between DEXes
"""

import asyncio
from typing import Optional, Dict, List
from web3 import Web3
from eth_account.signers.local import LocalAccount
import time

from .base_strategy import BaseStrategy
from ..dex.uniswap_v2 import UniswapV2
from ..dex.sushiswap import Sushiswap
from ..dex.pancakeswap import Pancakeswap
from ..utils.profit_calculator import ProfitCalculator
from ..utils.gas_optimizer import GasOptimizer


class ArbitrageStrategy(BaseStrategy):
    """
    Arbitrage strategy
    
    Finds and exploits price differences between different DEXes
    """
    
    def __init__(self, config, w3: Web3, account: LocalAccount):
        super().__init__(config, w3, account, "Arbitrage")
        
        # Initialize DEXes
        self.dexes = {
            "uniswap_v2": UniswapV2(config, w3),
            "sushiswap": Sushiswap(config, w3),
        }
        
        # Add PancakeSwap for BSC
        if "bsc" in config.get("blockchain.active_network", ""):
            self.dexes["pancakeswap"] = Pancakeswap(config, w3)
        
        # Initialize utilities
        self.profit_calculator = ProfitCalculator(config, w3)
        self.gas_optimizer = GasOptimizer(config, w3)
        
        # Get DEX pairs to monitor
        self.dex_pairs = self.strategy_config.get("dex_pairs", [])
        
        # Cache for prices
        self.price_cache = {}
        self.cache_ttl = 2  # seconds
        
        self.logger.info(f"Monitoring {len(self.dex_pairs)} DEX pairs for arbitrage")
    
    async def analyze(self, tx_hash: str, tx_data: Dict) -> Optional[Dict]:
        """
        Analyze transaction for arbitrage opportunities
        
        This looks for swaps and checks if there's a profitable arbitrage
        """
        try:
            # Decode transaction to see if it's a swap
            swap_info = self._decode_swap_transaction(tx_data)
            if not swap_info:
                return None
            
            token_in = swap_info["token_in"]
            token_out = swap_info["token_out"]
            amount_in = swap_info["amount_in"]
            dex_used = swap_info["dex"]
            
            # Find arbitrage opportunity on other DEXes
            opportunity = await self._find_arbitrage(
                token_in,
                token_out,
                amount_in,
                exclude_dex=dex_used
            )
            
            return opportunity
        
        except Exception as e:
            self.logger.debug(f"Error analyzing for arbitrage: {e}")
            return None
    
    def _decode_swap_transaction(self, tx_data: Dict) -> Optional[Dict]:
        """
        Decode transaction to extract swap information
        
        Args:
            tx_data: Transaction data
            
        Returns:
            Swap information or None
        """
        try:
            # Check if transaction is to a known DEX router
            to_address = tx_data.get("to", "").lower()
            
            dex_name = None
            for name, dex in self.dexes.items():
                if to_address == dex.router_address.lower():
                    dex_name = name
                    break
            
            if not dex_name:
                return None
            
            # Try to decode input data
            input_data = tx_data.get("input", "0x")
            
            # Check function selector (first 4 bytes)
            function_selector = input_data[:10]
            
            # swapExactTokensForTokens: 0x38ed1739
            # swapExactETHForTokens: 0x7ff36ab5
            # swapExactTokensForETH: 0x18cbafe5
            
            if function_selector in ["0x38ed1739", "0x7ff36ab5", "0x18cbafe5"]:
                # This is a swap transaction
                # In production, properly decode the transaction data
                # For now, return placeholder
                return {
                    "dex": dex_name,
                    "token_in": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                    "token_out": "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
                    "amount_in": tx_data.get("value", 0) or Web3.to_wei(1, "ether")
                }
            
            return None
        
        except Exception as e:
            self.logger.debug(f"Error decoding swap: {e}")
            return None
    
    async def _find_arbitrage(
        self,
        token_a: str,
        token_b: str,
        amount: int,
        exclude_dex: str = None
    ) -> Optional[Dict]:
        """
        Find arbitrage opportunity between DEXes
        
        Args:
            token_a: Token A address
            token_b: Token B address
            amount: Amount to trade
            exclude_dex: DEX to exclude from search
            
        Returns:
            Arbitrage opportunity or None
        """
        try:
            # Get prices from all DEXes
            prices = {}
            for dex_name, dex in self.dexes.items():
                if dex_name == exclude_dex:
                    continue
                
                try:
                    # Get amount out for this DEX
                    amount_out = dex.get_amount_out(amount, token_a, token_b)
                    if amount_out > 0:
                        prices[dex_name] = amount_out
                except Exception as e:
                    self.logger.debug(f"Error getting price from {dex_name}: {e}")
            
            if len(prices) < 2:
                return None
            
            # Find best buy and sell DEXes
            buy_dex = min(prices.keys(), key=lambda x: prices[x])  # Lowest price = best buy
            sell_dex = max(prices.keys(), key=lambda x: prices[x])  # Highest price = best sell
            
            # Calculate profit
            buy_amount_out = prices[buy_dex]
            sell_amount_out = prices[sell_dex]
            
            gross_profit = sell_amount_out - amount
            
            # Estimate gas costs
            gas_limit = 300000  # Approximate for arbitrage
            gas_price = self.gas_optimizer.get_optimal_gas_price("aggressive")
            gas_cost = gas_limit * gas_price
            
            # Check if profitable
            if not self.is_profitable(gross_profit, gas_cost):
                return None
            
            self.logger.info(f"Arbitrage opportunity found: {token_a[:8]}.../{token_b[:8]}...")
            self.logger.info(f"Buy on {buy_dex}, sell on {sell_dex}")
            self.logger.info(f"Expected profit: {Web3.from_wei(gross_profit - gas_cost, 'ether')} ETH")
            
            return {
                "type": "arbitrage",
                "token_a": token_a,
                "token_b": token_b,
                "amount": amount,
                "buy_dex": buy_dex,
                "sell_dex": sell_dex,
                "buy_amount_out": buy_amount_out,
                "sell_amount_out": sell_amount_out,
                "profit": gross_profit,
                "gas_cost": gas_cost,
                "net_profit": gross_profit - gas_cost
            }
        
        except Exception as e:
            self.logger.debug(f"Error finding arbitrage: {e}")
            return None
    
    async def execute(self, opportunity: Dict) -> Dict:
        """
        Execute arbitrage opportunity
        
        Args:
            opportunity: Opportunity details
            
        Returns:
            Execution result
        """
        try:
            token_a = opportunity["token_a"]
            token_b = opportunity["token_b"]
            amount = opportunity["amount"]
            buy_dex_name = opportunity["buy_dex"]
            sell_dex_name = opportunity["sell_dex"]
            
            buy_dex = self.dexes[buy_dex_name]
            sell_dex = self.dexes[sell_dex_name]
            
            # Step 1: Buy on cheaper DEX
            deadline = int(time.time()) + 300  # 5 minutes
            min_amount_out = int(opportunity["buy_amount_out"] * 0.99)  # 1% slippage
            
            buy_tx = buy_dex.build_swap_transaction(
                token_a,
                token_b,
                amount,
                min_amount_out,
                self.account.address,
                deadline
            )
            
            # Build transaction
            gas_price = self.gas_optimizer.get_optimal_gas_price("aggressive")
            
            transaction = {
                "from": self.account.address,
                "to": buy_dex.router_address,
                "value": buy_tx.get("value", 0),
                "gas": 250000,
                "gasPrice": gas_price,
                "data": buy_tx["function"]._encode_transaction_data()
            }
            
            # Sign and send
            signed_tx = self.build_and_sign_transaction(transaction)
            tx_hash = self.send_transaction(signed_tx)
            
            self.logger.info(f"Arbitrage buy transaction sent: {tx_hash}")
            
            # Wait for confirmation
            receipt = self.wait_for_receipt(tx_hash, timeout=60)
            
            if receipt["status"] == 1:
                # Transaction successful
                gas_used = receipt["gasUsed"]
                gas_spent = gas_used * gas_price
                
                # In production, would execute sell transaction here
                # For now, return result
                
                return {
                    "success": True,
                    "tx_hash": tx_hash,
                    "actual_profit": opportunity["net_profit"],
                    "gas_spent": gas_spent
                }
            else:
                return {
                    "success": False,
                    "error": "Transaction reverted",
                    "tx_hash": tx_hash
                }
        
        except Exception as e:
            self.logger.error(f"Error executing arbitrage: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def scan_pairs(self) -> List[Dict]:
        """
        Actively scan configured pairs for arbitrage opportunities
        
        Returns:
            List of opportunities found
        """
        opportunities = []
        
        for pair in self.dex_pairs:
            if len(pair) < 2:
                continue
            
            dex_a_name = pair[0]
            dex_b_name = pair[1]
            
            # Check common trading pairs
            # WETH/DAI, WETH/USDC, etc.
            weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
            dai = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
            
            amount = Web3.to_wei(1, "ether")
            
            opportunity = await self._find_arbitrage(weth, dai, amount)
            if opportunity:
                opportunities.append(opportunity)
        
        return opportunities
