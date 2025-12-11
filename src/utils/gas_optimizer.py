"""
Gas price optimization for MEV transactions
"""

import logging
from typing import Dict
from web3 import Web3


class GasOptimizer:
    """Optimizes gas prices for MEV transactions"""
    
    def __init__(self, config, w3: Web3):
        """
        Initialize gas optimizer
        
        Args:
            config: Configuration object
            w3: Web3 instance
        """
        self.config = config
        self.w3 = w3
        self.logger = logging.getLogger("MEVBot.GasOptimizer")
        
        self.priority = config.get("gas.priority", "normal")
        self.max_gas_price = Web3.to_wei(config.get("gas.max_gas_price_gwei", 500), "gwei")
        self.custom_multiplier = config.get("gas.custom_gas_multiplier", 1.15)
    
    def get_optimal_gas_price(self, urgency: str = None) -> int:
        """
        Get optimal gas price based on current network conditions
        
        Args:
            urgency: Override priority (conservative, normal, aggressive)
            
        Returns:
            Gas price in wei
        """
        priority = urgency or self.priority
        
        # Get current base gas price
        current_gas = self.w3.eth.gas_price
        
        # Apply multiplier based on priority
        multipliers = {
            "conservative": 1.05,
            "normal": 1.15,
            "aggressive": 1.3,
            "custom": self.custom_multiplier
        }
        
        multiplier = multipliers.get(priority, 1.15)
        optimal_gas = int(current_gas * multiplier)
        
        # Cap at maximum
        if optimal_gas > self.max_gas_price:
            self.logger.warning(f"Gas price {Web3.from_wei(optimal_gas, 'gwei')} Gwei exceeds max")
            optimal_gas = self.max_gas_price
        
        self.logger.debug(f"Optimal gas: {Web3.from_wei(optimal_gas, 'gwei')} Gwei (priority: {priority})")
        
        return optimal_gas
    
    def get_frontrun_gas_price(self, target_tx_gas_price: int) -> int:
        """
        Calculate gas price to front-run a transaction
        
        Args:
            target_tx_gas_price: Target transaction's gas price
            
        Returns:
            Front-running gas price in wei
        """
        # Front-run with 10-20% higher gas
        multiplier = self.config.get("strategies.frontrun.gas_price_multiplier", 1.2)
        frontrun_gas = int(target_tx_gas_price * multiplier)
        
        # Ensure it's within limits
        if frontrun_gas > self.max_gas_price:
            self.logger.warning("Front-run gas price exceeds maximum")
            return None
        
        return frontrun_gas
    
    def get_eip1559_params(self) -> Dict[str, int]:
        """
        Get EIP-1559 transaction parameters
        
        Returns:
            Dictionary with maxFeePerGas and maxPriorityFeePerGas
        """
        try:
            # Get latest block
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            # Calculate priority fee
            max_priority_fee = Web3.to_wei(
                self.config.get("gas.max_priority_fee_gwei", 3),
                "gwei"
            )
            
            # Calculate max fee
            max_fee_per_gas = base_fee * 2 + max_priority_fee
            
            # Cap at configured maximum
            max_configured = Web3.to_wei(
                self.config.get("gas.max_fee_per_gas_gwei", 100),
                "gwei"
            )
            
            if max_fee_per_gas > max_configured:
                max_fee_per_gas = max_configured
            
            return {
                "maxFeePerGas": max_fee_per_gas,
                "maxPriorityFeePerGas": max_priority_fee
            }
        
        except Exception as e:
            self.logger.warning(f"EIP-1559 not supported: {e}")
            return {}
    
    def estimate_transaction_cost(self, gas_limit: int, gas_price: int = None) -> int:
        """
        Estimate total transaction cost
        
        Args:
            gas_limit: Gas limit
            gas_price: Gas price (uses optimal if not provided)
            
        Returns:
            Total cost in wei
        """
        if gas_price is None:
            gas_price = self.get_optimal_gas_price()
        
        return gas_limit * gas_price
    
    def is_profitable(self, expected_profit: int, gas_limit: int, gas_price: int = None) -> bool:
        """
        Check if transaction is profitable after gas costs
        
        Args:
            expected_profit: Expected profit in wei
            gas_limit: Gas limit
            gas_price: Gas price (uses optimal if not provided)
            
        Returns:
            True if profitable
        """
        tx_cost = self.estimate_transaction_cost(gas_limit, gas_price)
        net_profit = expected_profit - tx_cost
        
        self.logger.debug(f"Expected profit: {Web3.from_wei(expected_profit, 'ether')} ETH")
        self.logger.debug(f"Transaction cost: {Web3.from_wei(tx_cost, 'ether')} ETH")
        self.logger.debug(f"Net profit: {Web3.from_wei(net_profit, 'ether')} ETH")
        
        return net_profit > 0
