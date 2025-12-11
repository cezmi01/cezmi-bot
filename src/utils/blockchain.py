"""
Blockchain connection and utilities
"""

from web3 import Web3
from web3.middleware import geth_poa_middleware
import logging
from typing import Optional, Dict, Any


class BlockchainConnector:
    """Manages blockchain connections and interactions"""
    
    def __init__(self, config):
        """
        Initialize blockchain connector
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = logging.getLogger("MEVBot.Blockchain")
        
        # Connect to RPC
        rpc_url = config.get_active_rpc()
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Add PoA middleware for BSC and other PoA chains
        active_network = config.get("blockchain.active_network")
        if "bsc" in active_network or "polygon" in active_network:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Verify connection
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {rpc_url}")
        
        self.chain_id = self.w3.eth.chain_id
        self.logger.info(f"✓ Connected to blockchain (Chain ID: {self.chain_id})")
        
        # WebSocket connection for mempool monitoring
        self.ws_provider = None
        try:
            ws_url = config.get_websocket_url()
            self.ws_provider = Web3.WebsocketProvider(ws_url)
            self.w3_ws = Web3(self.ws_provider)
            self.logger.info("✓ WebSocket connection established")
        except Exception as e:
            self.logger.warning(f"WebSocket connection failed: {e}")
            self.w3_ws = None
    
    def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get transaction details
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction data or None
        """
        try:
            return dict(self.w3.eth.get_transaction(tx_hash))
        except Exception as e:
            self.logger.debug(f"Error getting transaction {tx_hash}: {e}")
            return None
    
    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get transaction receipt
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction receipt or None
        """
        try:
            return dict(self.w3.eth.get_transaction_receipt(tx_hash))
        except Exception as e:
            self.logger.debug(f"Error getting receipt {tx_hash}: {e}")
            return None
    
    def get_gas_price(self) -> int:
        """
        Get current gas price in wei
        
        Returns:
            Gas price in wei
        """
        return self.w3.eth.gas_price
    
    def get_block(self, block_number: str = "latest") -> Dict[str, Any]:
        """
        Get block data
        
        Args:
            block_number: Block number or "latest"
            
        Returns:
            Block data
        """
        return dict(self.w3.eth.get_block(block_number, full_transactions=True))
    
    def send_transaction(self, transaction: Dict) -> str:
        """
        Send a transaction
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            Transaction hash
        """
        tx_hash = self.w3.eth.send_raw_transaction(transaction["rawTransaction"])
        return self.w3.to_hex(tx_hash)
    
    def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> Dict:
        """
        Wait for transaction receipt
        
        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds
            
        Returns:
            Transaction receipt
        """
        return dict(self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout))
    
    def estimate_gas(self, transaction: Dict) -> int:
        """
        Estimate gas for transaction
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            Estimated gas
        """
        return self.w3.eth.estimate_gas(transaction)
    
    def call_contract(self, contract_address: str, abi: list, function_name: str, *args):
        """
        Call a contract function (read-only)
        
        Args:
            contract_address: Contract address
            abi: Contract ABI
            function_name: Function to call
            *args: Function arguments
            
        Returns:
            Function result
        """
        contract = self.w3.eth.contract(address=contract_address, abi=abi)
        function = getattr(contract.functions, function_name)
        return function(*args).call()
    
    def get_balance(self, address: str) -> int:
        """
        Get ETH balance
        
        Args:
            address: Wallet address
            
        Returns:
            Balance in wei
        """
        return self.w3.eth.get_balance(address)
    
    def is_contract(self, address: str) -> bool:
        """
        Check if address is a contract
        
        Args:
            address: Address to check
            
        Returns:
            True if contract, False otherwise
        """
        code = self.w3.eth.get_code(address)
        return len(code) > 0
