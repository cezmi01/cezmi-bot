"""
Base DEX interface
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict
from web3 import Web3
import logging


class BaseDEX(ABC):
    """Base class for all DEX integrations"""
    
    def __init__(self, config, w3: Web3, name: str):
        """
        Initialize base DEX
        
        Args:
            config: Configuration object
            w3: Web3 instance
            name: DEX name
        """
        self.config = config
        self.w3 = w3
        self.name = name
        self.logger = logging.getLogger(f"MEVBot.DEX.{name}")
        
        # Load DEX configuration
        dex_config = config.get(f"dex.{name.lower()}", {})
        self.factory_address = dex_config.get("factory")
        self.router_address = dex_config.get("router")
        self.fee = dex_config.get("fee", 0.003)
        
        # Load ABIs
        self._load_abis()
        
        # Initialize contracts
        if self.factory_address:
            self.factory = w3.eth.contract(
                address=Web3.to_checksum_address(self.factory_address),
                abi=self.factory_abi
            )
        
        if self.router_address:
            self.router = w3.eth.contract(
                address=Web3.to_checksum_address(self.router_address),
                abi=self.router_abi
            )
    
    @abstractmethod
    def _load_abis(self):
        """Load contract ABIs"""
        pass
    
    @abstractmethod
    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """
        Get pair address for two tokens
        
        Args:
            token_a: Token A address
            token_b: Token B address
            
        Returns:
            Pair address or None
        """
        pass
    
    @abstractmethod
    def get_reserves(self, token_a: str, token_b: str) -> Optional[Tuple[int, int]]:
        """
        Get reserves for a trading pair
        
        Args:
            token_a: Token A address
            token_b: Token B address
            
        Returns:
            Tuple of (reserve_a, reserve_b) or None
        """
        pass
    
    @abstractmethod
    def get_amount_out(self, amount_in: int, token_in: str, token_out: str) -> int:
        """
        Get output amount for a swap
        
        Args:
            amount_in: Input amount
            token_in: Input token address
            token_out: Output token address
            
        Returns:
            Output amount
        """
        pass
    
    @abstractmethod
    def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        recipient: str,
        deadline: int
    ) -> Dict:
        """
        Build a swap transaction
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount
            min_amount_out: Minimum output amount
            recipient: Recipient address
            deadline: Transaction deadline
            
        Returns:
            Transaction dictionary
        """
        pass
    
    def get_price(self, token_a: str, token_b: str) -> Optional[float]:
        """
        Get price of token_a in terms of token_b
        
        Args:
            token_a: Token A address
            token_b: Token B address
            
        Returns:
            Price or None
        """
        reserves = self.get_reserves(token_a, token_b)
        if not reserves:
            return None
        
        reserve_a, reserve_b = reserves
        if reserve_a == 0:
            return None
        
        return reserve_b / reserve_a
    
    def calculate_price_impact(
        self,
        amount_in: int,
        token_in: str,
        token_out: str
    ) -> float:
        """
        Calculate price impact of a trade
        
        Args:
            amount_in: Input amount
            token_in: Input token address
            token_out: Output token address
            
        Returns:
            Price impact percentage (0-1)
        """
        reserves = self.get_reserves(token_in, token_out)
        if not reserves:
            return 1.0
        
        reserve_in, reserve_out = reserves
        
        if reserve_in == 0:
            return 1.0
        
        impact = amount_in / (reserve_in + amount_in)
        return impact
    
    def is_pair_exists(self, token_a: str, token_b: str) -> bool:
        """
        Check if trading pair exists
        
        Args:
            token_a: Token A address
            token_b: Token B address
            
        Returns:
            True if pair exists
        """
        pair_address = self.get_pair_address(token_a, token_b)
        return pair_address is not None and pair_address != "0x0000000000000000000000000000000000000000"
