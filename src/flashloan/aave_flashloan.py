"""
Aave Flashloan integration
"""

import logging
from typing import List, Dict
from web3 import Web3
from eth_account.signers.local import LocalAccount
from ..dex.abi import AAVE_LENDING_POOL_ABI


class AaveFlashloan:
    """
    Aave Flashloan provider
    
    Allows borrowing assets without collateral for a single transaction
    """
    
    def __init__(self, config, w3: Web3, account: LocalAccount):
        """
        Initialize Aave flashloan provider
        
        Args:
            config: Configuration object
            w3: Web3 instance
            account: Account for signing transactions
        """
        self.config = config
        self.w3 = w3
        self.account = account
        self.logger = logging.getLogger("MEVBot.Flashloan.Aave")
        
        # Load configuration
        flashloan_config = config.get("flashloan.providers.aave", {})
        self.enabled = flashloan_config.get("enabled", False)
        self.lending_pool_address = flashloan_config.get("lending_pool")
        self.fee_percentage = flashloan_config.get("fee_percentage", 0.0009)
        
        if not self.enabled:
            self.logger.info("Aave flashloan not enabled")
            return
        
        # Initialize lending pool contract
        if self.lending_pool_address:
            self.lending_pool = w3.eth.contract(
                address=Web3.to_checksum_address(self.lending_pool_address),
                abi=AAVE_LENDING_POOL_ABI
            )
            self.logger.info(f"✓ Aave flashloan initialized (fee: {self.fee_percentage * 100}%)")
        else:
            self.logger.warning("Aave lending pool address not configured")
    
    def calculate_fee(self, amount: int) -> int:
        """
        Calculate flashloan fee
        
        Args:
            amount: Loan amount in wei
            
        Returns:
            Fee amount in wei
        """
        return int(amount * self.fee_percentage)
    
    def calculate_repayment(self, amount: int) -> int:
        """
        Calculate total repayment amount
        
        Args:
            amount: Loan amount in wei
            
        Returns:
            Total repayment (principal + fee)
        """
        return amount + self.calculate_fee(amount)
    
    def build_flashloan_transaction(
        self,
        receiver_address: str,
        assets: List[str],
        amounts: List[int],
        params: bytes = b''
    ) -> Dict:
        """
        Build a flashloan transaction
        
        Args:
            receiver_address: Contract that will receive the loan
            assets: List of asset addresses to borrow
            amounts: List of amounts to borrow
            params: Additional parameters to pass to receiver
            
        Returns:
            Transaction dictionary
        """
        # modes: 0 = no debt, 1 = stable debt, 2 = variable debt
        modes = [0] * len(assets)  # No debt - must repay in same transaction
        
        function = self.lending_pool.functions.flashLoan(
            Web3.to_checksum_address(receiver_address),
            [Web3.to_checksum_address(a) for a in assets],
            amounts,
            modes,
            Web3.to_checksum_address(self.account.address),  # onBehalfOf
            params,
            0  # referralCode
        )
        
        return {
            "function": function,
            "to": self.lending_pool_address
        }
    
    def estimate_profit(
        self,
        loan_amount: int,
        expected_return: int
    ) -> Dict:
        """
        Estimate profit from flashloan arbitrage
        
        Args:
            loan_amount: Flashloan amount
            expected_return: Expected return from the arbitrage
            
        Returns:
            Profit calculation details
        """
        fee = self.calculate_fee(loan_amount)
        repayment = self.calculate_repayment(loan_amount)
        gross_profit = expected_return - loan_amount
        net_profit = expected_return - repayment
        
        return {
            "loan_amount": loan_amount,
            "fee": fee,
            "repayment": repayment,
            "expected_return": expected_return,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "profitable": net_profit > 0
        }
    
    def max_loan_amount(self) -> int:
        """
        Get maximum loan amount configured
        
        Returns:
            Max loan amount in wei
        """
        max_eth = self.config.get("flashloan.max_loan_eth", 1000)
        return Web3.to_wei(max_eth, "ether")
    
    def is_profitable_after_fees(
        self,
        loan_amount: int,
        expected_profit: int
    ) -> bool:
        """
        Check if trade is profitable after flashloan fees
        
        Args:
            loan_amount: Loan amount
            expected_profit: Expected profit before fees
            
        Returns:
            True if profitable after fees
        """
        fee = self.calculate_fee(loan_amount)
        net_profit = expected_profit - fee
        
        return net_profit > 0
