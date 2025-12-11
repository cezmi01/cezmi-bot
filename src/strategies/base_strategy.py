"""
Base strategy interface
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from web3 import Web3
from eth_account.signers.local import LocalAccount
import logging


class BaseStrategy(ABC):
    """Base class for all MEV strategies"""
    
    def __init__(self, config, w3: Web3, account: LocalAccount, name: str):
        """
        Initialize base strategy
        
        Args:
            config: Configuration object
            w3: Web3 instance
            account: Account for signing transactions
            name: Strategy name
        """
        self.config = config
        self.w3 = w3
        self.account = account
        self.name = name
        self.logger = logging.getLogger(f"MEVBot.Strategy.{name}")
        
        # Load strategy configuration
        self.strategy_config = config.get(f"strategies.{name.lower()}", {})
        self.min_profit_wei = self.strategy_config.get("min_profit_wei", 0)
        self.max_gas_price_gwei = self.strategy_config.get("max_gas_price_gwei", 300)
        
        self.logger.info(f"{name} strategy initialized")
    
    @abstractmethod
    async def analyze(self, tx_hash: str, tx_data: Dict) -> Optional[Dict]:
        """
        Analyze a transaction for opportunities
        
        Args:
            tx_hash: Transaction hash
            tx_data: Transaction data
            
        Returns:
            Opportunity details or None
        """
        pass
    
    @abstractmethod
    async def execute(self, opportunity: Dict) -> Dict:
        """
        Execute an opportunity
        
        Args:
            opportunity: Opportunity details
            
        Returns:
            Execution result
        """
        pass
    
    def is_profitable(self, expected_profit: int, gas_cost: int) -> bool:
        """
        Check if opportunity is profitable
        
        Args:
            expected_profit: Expected profit in wei
            gas_cost: Gas cost in wei
            
        Returns:
            True if profitable
        """
        net_profit = expected_profit - gas_cost
        return net_profit >= self.min_profit_wei
    
    def build_and_sign_transaction(self, transaction: Dict) -> Dict:
        """
        Build and sign a transaction
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            Signed transaction
        """
        # Add nonce
        if "nonce" not in transaction:
            transaction["nonce"] = self.w3.eth.get_transaction_count(self.account.address)
        
        # Add chain ID
        if "chainId" not in transaction:
            transaction["chainId"] = self.w3.eth.chain_id
        
        # Sign transaction
        signed_tx = self.account.sign_transaction(transaction)
        
        return signed_tx
    
    def send_transaction(self, signed_tx) -> str:
        """
        Send a signed transaction
        
        Args:
            signed_tx: Signed transaction
            
        Returns:
            Transaction hash
        """
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return self.w3.to_hex(tx_hash)
    
    def wait_for_receipt(self, tx_hash: str, timeout: int = 60) -> Dict:
        """
        Wait for transaction receipt
        
        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds
            
        Returns:
            Transaction receipt
        """
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return dict(receipt)
