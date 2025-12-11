"""
dYdX Flashloan integration
"""

import logging
from typing import Dict
from web3 import Web3
from eth_account.signers.local import LocalAccount
from ..dex.abi import DYDX_SOLO_MARGIN_ABI


class DydxFlashloan:
    """
    dYdX Flashloan provider
    
    dYdX offers flashloans with lower fees than Aave
    """
    
    def __init__(self, config, w3: Web3, account: LocalAccount):
        """
        Initialize dYdX flashloan provider
        
        Args:
            config: Configuration object
            w3: Web3 instance
            account: Account for signing transactions
        """
        self.config = config
        self.w3 = w3
        self.account = account
        self.logger = logging.getLogger("MEVBot.Flashloan.dYdX")
        
        # Load configuration
        flashloan_config = config.get("flashloan.providers.dydx", {})
        self.enabled = flashloan_config.get("enabled", False)
        self.solo_margin_address = flashloan_config.get("solo_margin")
        self.fee_percentage = flashloan_config.get("fee_percentage", 0.0002)
        
        if not self.enabled:
            self.logger.info("dYdX flashloan not enabled")
            return
        
        # Initialize solo margin contract
        if self.solo_margin_address:
            self.solo_margin = w3.eth.contract(
                address=Web3.to_checksum_address(self.solo_margin_address),
                abi=DYDX_SOLO_MARGIN_ABI
            )
            self.logger.info(f"✓ dYdX flashloan initialized (fee: {self.fee_percentage * 100}%)")
        else:
            self.logger.warning("dYdX solo margin address not configured")
    
    def calculate_fee(self, amount: int) -> int:
        """
        Calculate flashloan fee
        
        dYdX has lower fees than Aave
        
        Args:
            amount: Loan amount in wei
            
        Returns:
            Fee amount in wei (often just 2 wei!)
        """
        # dYdX charges a flat 2 wei fee, not a percentage
        # But we use percentage for configuration consistency
        return max(int(amount * self.fee_percentage), 2)
    
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
        token_address: str,
        amount: int,
        data: bytes = b''
    ) -> Dict:
        """
        Build a dYdX flashloan transaction
        
        Note: dYdX uses a different structure than Aave
        
        Args:
            token_address: Token to borrow
            amount: Amount to borrow
            data: Calldata for the operation
            
        Returns:
            Transaction dictionary
        """
        # dYdX uses "actions" - Withdraw, Call, Deposit
        # This is more complex than Aave and requires a separate contract
        
        self.logger.warning("dYdX flashloan requires custom receiver contract")
        self.logger.warning("Implementation requires building actions array")
        
        return {
            "function": None,
            "to": self.solo_margin_address,
            "note": "Requires custom implementation"
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
            "profitable": net_profit > 0,
            "provider": "dYdX"
        }
    
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
