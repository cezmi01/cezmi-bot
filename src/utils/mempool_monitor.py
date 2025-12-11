"""
Mempool monitoring for detecting pending transactions
"""

import asyncio
import logging
from typing import Callable, Dict, Optional
from web3 import Web3
from hexbytes import HexBytes


class MempoolMonitor:
    """Monitors the mempool for pending transactions"""
    
    def __init__(self, config, w3: Web3, blockchain):
        """
        Initialize mempool monitor
        
        Args:
            config: Configuration object
            w3: Web3 instance
            blockchain: BlockchainConnector instance
        """
        self.config = config
        self.w3 = w3
        self.blockchain = blockchain
        self.logger = logging.getLogger("MEVBot.Mempool")
        
        self.running = False
        self.callback = None
        self.seen_txs = set()
        
        # Performance tracking
        self.tx_count = 0
        self.start_time = None
    
    async def start(self, callback: Callable):
        """
        Start monitoring mempool
        
        Args:
            callback: Async function to call for each new transaction
        """
        self.callback = callback
        self.running = True
        self.start_time = asyncio.get_event_loop().time()
        
        self.logger.info("Starting mempool monitoring...")
        
        if self.blockchain.w3_ws:
            # Use WebSocket for real-time monitoring
            await self._monitor_websocket()
        else:
            # Fallback to polling
            await self._monitor_polling()
    
    async def _monitor_websocket(self):
        """Monitor mempool using WebSocket subscription"""
        try:
            # Subscribe to pending transactions
            pending_filter = await self.blockchain.w3_ws.eth.filter('pending')
            
            self.logger.info("✓ Subscribed to pending transactions via WebSocket")
            
            while self.running:
                try:
                    # Get new pending transaction hashes
                    new_entries = await pending_filter.get_new_entries()
                    
                    for tx_hash in new_entries:
                        if not self.running:
                            break
                        
                        tx_hash_hex = tx_hash.hex() if isinstance(tx_hash, HexBytes) else tx_hash
                        
                        # Skip if already seen
                        if tx_hash_hex in self.seen_txs:
                            continue
                        
                        self.seen_txs.add(tx_hash_hex)
                        self.tx_count += 1
                        
                        # Get transaction details
                        tx_data = await self._get_transaction_data(tx_hash_hex)
                        
                        if tx_data and self.callback:
                            # Call the callback asynchronously
                            asyncio.create_task(self.callback(tx_hash_hex, tx_data))
                        
                        # Log progress every 100 transactions
                        if self.tx_count % 100 == 0:
                            elapsed = asyncio.get_event_loop().time() - self.start_time
                            rate = self.tx_count / elapsed if elapsed > 0 else 0
                            self.logger.debug(f"Processed {self.tx_count} txs ({rate:.1f} tx/s)")
                    
                    # Small delay to prevent overwhelming the system
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    self.logger.error(f"Error in WebSocket loop: {e}")
                    await asyncio.sleep(1)
        
        except Exception as e:
            self.logger.error(f"Failed to setup WebSocket monitoring: {e}")
            self.logger.info("Falling back to polling mode...")
            await self._monitor_polling()
    
    async def _monitor_polling(self):
        """Monitor mempool using polling (fallback method)"""
        self.logger.info("Starting mempool monitoring via polling...")
        
        while self.running:
            try:
                # Get pending transactions from the txpool
                # Note: This requires a full node with txpool API enabled
                pending_block = self.w3.eth.get_block('pending', full_transactions=True)
                
                for tx in pending_block.transactions:
                    if not self.running:
                        break
                    
                    tx_hash = tx.hash.hex() if hasattr(tx, 'hash') else tx['hash'].hex()
                    
                    if tx_hash in self.seen_txs:
                        continue
                    
                    self.seen_txs.add(tx_hash)
                    self.tx_count += 1
                    
                    # Convert transaction to dict
                    tx_data = dict(tx) if hasattr(tx, '__iter__') else tx
                    
                    if self.callback:
                        asyncio.create_task(self.callback(tx_hash, tx_data))
                
                # Cleanup old seen transactions (keep last 10000)
                if len(self.seen_txs) > 10000:
                    self.seen_txs = set(list(self.seen_txs)[-5000:])
                
                await asyncio.sleep(1)  # Poll every second
            
            except Exception as e:
                self.logger.debug(f"Polling error: {e}")
                await asyncio.sleep(2)
    
    async def _get_transaction_data(self, tx_hash: str) -> Optional[Dict]:
        """
        Get transaction data from hash
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction data or None
        """
        try:
            # Try to get transaction
            tx = self.blockchain.get_transaction(tx_hash)
            if tx:
                return tx
            
            # If WebSocket, try the WebSocket connection
            if self.blockchain.w3_ws:
                tx = dict(self.blockchain.w3_ws.eth.get_transaction(tx_hash))
                return tx
            
            return None
        
        except Exception as e:
            self.logger.debug(f"Could not get tx data for {tx_hash}: {e}")
            return None
    
    async def stop(self):
        """Stop monitoring mempool"""
        self.running = False
        self.logger.info(f"Mempool monitor stopped. Processed {self.tx_count} transactions")
