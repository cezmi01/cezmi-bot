"""
Profit calculation utilities
"""

import logging
from typing import List, Tuple, Dict
from web3 import Web3


class ProfitCalculator:
    """Calculates potential profits for MEV opportunities"""
    
    def __init__(self, config, w3: Web3):
        """
        Initialize profit calculator
        
        Args:
            config: Configuration object
            w3: Web3 instance
        """
        self.config = config
        self.w3 = w3
        self.logger = logging.getLogger("MEVBot.ProfitCalc")
    
    def calculate_arbitrage_profit(
        self,
        buy_price: int,
        sell_price: int,
        amount: int,
        buy_fee: float = 0.003,
        sell_fee: float = 0.003
    ) -> int:
        """
        Calculate arbitrage profit
        
        Args:
            buy_price: Buy price per token in wei
            sell_price: Sell price per token in wei
            amount: Amount of tokens
            buy_fee: Buy DEX fee (default 0.3%)
            sell_fee: Sell DEX fee (default 0.3%)
            
        Returns:
            Net profit in wei
        """
        # Calculate costs
        buy_cost = buy_price * amount
        buy_cost_with_fee = buy_cost * (1 + buy_fee)
        
        # Calculate revenue
        sell_revenue = sell_price * amount
        sell_revenue_after_fee = sell_revenue * (1 - sell_fee)
        
        # Net profit
        profit = int(sell_revenue_after_fee - buy_cost_with_fee)
        
        return profit
    
    def calculate_sandwich_profit(
        self,
        victim_trade_size: int,
        price_impact: float,
        frontrun_amount: int,
        pool_liquidity: int,
        fee: float = 0.003
    ) -> int:
        """
        Calculate sandwich attack profit
        
        Args:
            victim_trade_size: Victim's trade size in wei
            price_impact: Expected price impact (0-1)
            frontrun_amount: Our front-run amount in wei
            pool_liquidity: Pool liquidity
            fee: DEX fee
            
        Returns:
            Estimated profit in wei
        """
        # Simplified profit calculation
        # In reality, this would use actual pool math (constant product formula)
        
        # Price increase from victim trade
        price_increase = price_impact
        
        # Our profit from the price increase
        profit = int(frontrun_amount * price_increase * (1 - fee * 2))
        
        return profit
    
    def calculate_swap_output(
        self,
        amount_in: int,
        reserve_in: int,
        reserve_out: int,
        fee: float = 0.003
    ) -> int:
        """
        Calculate output amount for a swap (Uniswap V2 formula)
        
        Args:
            amount_in: Input amount
            reserve_in: Input token reserve
            reserve_out: Output token reserve
            fee: DEX fee
            
        Returns:
            Output amount
        """
        if reserve_in == 0 or reserve_out == 0:
            return 0
        
        # Apply fee
        amount_in_with_fee = amount_in * (1 - fee)
        
        # Constant product formula: x * y = k
        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in + amount_in_with_fee
        
        amount_out = int(numerator / denominator)
        
        return amount_out
    
    def calculate_price_impact(
        self,
        amount_in: int,
        reserve_in: int,
        reserve_out: int
    ) -> float:
        """
        Calculate price impact of a trade
        
        Args:
            amount_in: Input amount
            reserve_in: Input token reserve
            reserve_out: Output token reserve
            
        Returns:
            Price impact as percentage (0-1)
        """
        if reserve_in == 0:
            return 1.0
        
        # Price before trade
        price_before = reserve_out / reserve_in
        
        # Reserves after trade
        new_reserve_in = reserve_in + amount_in
        amount_out = self.calculate_swap_output(amount_in, reserve_in, reserve_out)
        new_reserve_out = reserve_out - amount_out
        
        # Price after trade
        if new_reserve_in == 0:
            return 1.0
        
        price_after = new_reserve_out / new_reserve_in
        
        # Calculate impact
        impact = abs(price_after - price_before) / price_before
        
        return impact
    
    def calculate_optimal_arbitrage_amount(
        self,
        reserve_a_in: int,
        reserve_a_out: int,
        reserve_b_in: int,
        reserve_b_out: int,
        max_amount: int = None
    ) -> Tuple[int, int]:
        """
        Calculate optimal amount for arbitrage
        
        Args:
            reserve_a_in: DEX A input reserve
            reserve_a_out: DEX A output reserve
            reserve_b_in: DEX B input reserve
            reserve_b_out: DEX B output reserve
            max_amount: Maximum amount to trade
            
        Returns:
            Tuple of (optimal_amount, expected_profit)
        """
        # Binary search for optimal amount
        min_amount = Web3.to_wei(0.01, 'ether')  # Start with 0.01 ETH
        max_amount = max_amount or Web3.to_wei(100, 'ether')
        
        best_amount = 0
        best_profit = 0
        
        for _ in range(20):  # 20 iterations
            mid_amount = (min_amount + max_amount) // 2
            
            # Calculate profit at this amount
            amount_out_a = self.calculate_swap_output(mid_amount, reserve_a_in, reserve_a_out)
            amount_out_b = self.calculate_swap_output(amount_out_a, reserve_b_in, reserve_b_out)
            
            profit = amount_out_b - mid_amount
            
            if profit > best_profit:
                best_profit = profit
                best_amount = mid_amount
            
            # Adjust search range
            if profit > 0:
                min_amount = mid_amount
            else:
                max_amount = mid_amount
        
        return best_amount, best_profit
    
    def simulate_flashloan_arbitrage(
        self,
        loan_amount: int,
        dex_a_reserves: Tuple[int, int],
        dex_b_reserves: Tuple[int, int],
        flashloan_fee: float = 0.0009
    ) -> Dict:
        """
        Simulate flashloan arbitrage profit
        
        Args:
            loan_amount: Flashloan amount
            dex_a_reserves: (reserve_in, reserve_out) for DEX A
            dex_b_reserves: (reserve_in, reserve_out) for DEX B
            flashloan_fee: Flashloan fee percentage
            
        Returns:
            Dictionary with simulation results
        """
        # Step 1: Buy on DEX A
        amount_out_a = self.calculate_swap_output(
            loan_amount,
            dex_a_reserves[0],
            dex_a_reserves[1]
        )
        
        # Step 2: Sell on DEX B
        amount_out_b = self.calculate_swap_output(
            amount_out_a,
            dex_b_reserves[0],
            dex_b_reserves[1]
        )
        
        # Calculate flashloan repayment
        loan_repayment = int(loan_amount * (1 + flashloan_fee))
        
        # Net profit
        profit = amount_out_b - loan_repayment
        
        return {
            "loan_amount": loan_amount,
            "bought_on_dex_a": amount_out_a,
            "sold_on_dex_b": amount_out_b,
            "loan_repayment": loan_repayment,
            "gross_profit": amount_out_b - loan_amount,
            "flashloan_cost": loan_repayment - loan_amount,
            "net_profit": profit,
            "profitable": profit > 0
        }
