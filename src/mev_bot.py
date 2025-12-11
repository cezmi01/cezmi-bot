"""
Main MEV Bot orchestrator
"""

import asyncio
import logging
from typing import Dict, List, Optional
from web3 import Web3
from eth_account import Account
import time

from .config import Config
from .utils.logger import setup_logger
from .utils.blockchain import BlockchainConnector
from .utils.mempool_monitor import MempoolMonitor
from .strategies.arbitrage import ArbitrageStrategy
from .strategies.sandwich import SandwichStrategy
from .strategies.frontrun import FrontrunStrategy
from .strategies.backrun import BackrunStrategy
from .utils.gas_optimizer import GasOptimizer
from .utils.profit_calculator import ProfitCalculator


class MEVBot:
    """
    Main MEV Bot orchestrator
    
    Coordinates all MEV strategies and manages execution
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MEV Bot
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = Config(config_path)
        self.config.validate()
        
        # Setup logging
        self.logger = setup_logger(
            log_level=self.config.get("monitoring.log_level", "INFO"),
            log_to_file=self.config.get("monitoring.log_to_file", True)
        )
        
        self.logger.info("=" * 60)
        self.logger.info("MEV Bot Starting...")
        self.logger.info("=" * 60)
        
        # Initialize blockchain connection
        self.blockchain = BlockchainConnector(self.config)
        self.w3 = self.blockchain.w3
        
        # Initialize wallet
        private_key = self.config.get("wallet.private_key")
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.config.set("wallet.address", self.address)
        
        self.logger.info(f"Wallet Address: {self.address}")
        
        # Initialize utilities
        self.gas_optimizer = GasOptimizer(self.config, self.w3)
        self.profit_calculator = ProfitCalculator(self.config, self.w3)
        
        # Initialize strategies
        self.strategies: Dict[str, any] = {}
        self._initialize_strategies()
        
        # Initialize mempool monitor
        self.mempool_monitor = MempoolMonitor(
            self.config,
            self.w3,
            self.blockchain
        )
        
        # Bot state
        self.running = False
        self.stats = {
            "transactions_analyzed": 0,
            "opportunities_found": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_profit_wei": 0,
            "total_gas_spent_wei": 0
        }
        
        self.logger.info("✓ MEV Bot initialized successfully")
    
    def _initialize_strategies(self):
        """Initialize all enabled strategies"""
        if self.config.is_strategy_enabled("arbitrage"):
            self.strategies["arbitrage"] = ArbitrageStrategy(
                self.config, self.w3, self.account
            )
            self.logger.info("✓ Arbitrage strategy enabled")
        
        if self.config.is_strategy_enabled("sandwich"):
            self.strategies["sandwich"] = SandwichStrategy(
                self.config, self.w3, self.account
            )
            self.logger.info("✓ Sandwich strategy enabled")
        
        if self.config.is_strategy_enabled("frontrun"):
            self.strategies["frontrun"] = FrontrunStrategy(
                self.config, self.w3, self.account
            )
            self.logger.info("✓ Front-run strategy enabled")
        
        if self.config.is_strategy_enabled("backrun"):
            self.strategies["backrun"] = BackrunStrategy(
                self.config, self.w3, self.account
            )
            self.logger.info("✓ Back-run strategy enabled")
    
    async def start(self):
        """Start the MEV bot"""
        self.running = True
        self.logger.info("\n🚀 MEV Bot is now running and monitoring mempool...")
        self.logger.info("Press Ctrl+C to stop\n")
        
        try:
            # Start mempool monitoring
            await self.mempool_monitor.start(self._on_pending_transaction)
        except KeyboardInterrupt:
            self.logger.info("\n⏹ Shutting down MEV Bot...")
            await self.stop()
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
            await self.stop()
    
    async def _on_pending_transaction(self, tx_hash: str, tx_data: Dict):
        """
        Callback for new pending transactions
        
        Args:
            tx_hash: Transaction hash
            tx_data: Transaction data
        """
        self.stats["transactions_analyzed"] += 1
        
        try:
            # Analyze transaction for MEV opportunities
            opportunities = await self._analyze_transaction(tx_hash, tx_data)
            
            if opportunities:
                self.stats["opportunities_found"] += len(opportunities)
                
                # Execute most profitable opportunity
                best_opportunity = max(opportunities, key=lambda x: x.get("profit", 0))
                await self._execute_opportunity(best_opportunity)
        
        except Exception as e:
            self.logger.error(f"Error processing transaction {tx_hash}: {e}")
    
    async def _analyze_transaction(self, tx_hash: str, tx_data: Dict) -> List[Dict]:
        """
        Analyze transaction for MEV opportunities across all strategies
        
        Args:
            tx_hash: Transaction hash
            tx_data: Transaction data
            
        Returns:
            List of opportunities found
        """
        opportunities = []
        
        # Run each strategy's analysis
        for strategy_name, strategy in self.strategies.items():
            try:
                opportunity = await strategy.analyze(tx_hash, tx_data)
                if opportunity:
                    opportunity["strategy"] = strategy_name
                    opportunities.append(opportunity)
            except Exception as e:
                self.logger.debug(f"Strategy {strategy_name} error: {e}")
        
        return opportunities
    
    async def _execute_opportunity(self, opportunity: Dict):
        """
        Execute a detected MEV opportunity
        
        Args:
            opportunity: Opportunity details
        """
        strategy_name = opportunity["strategy"]
        strategy = self.strategies[strategy_name]
        
        self.logger.info(f"\n💰 Executing {strategy_name} opportunity")
        self.logger.info(f"Expected profit: {Web3.from_wei(opportunity['profit'], 'ether')} ETH")
        
        try:
            # Execute the opportunity
            result = await strategy.execute(opportunity)
            
            if result["success"]:
                self.stats["successful_trades"] += 1
                self.stats["total_profit_wei"] += result["actual_profit"]
                self.stats["total_gas_spent_wei"] += result["gas_spent"]
                
                net_profit = result["actual_profit"] - result["gas_spent"]
                
                self.logger.info(f"✓ Trade successful!")
                self.logger.info(f"Profit: {Web3.from_wei(result['actual_profit'], 'ether')} ETH")
                self.logger.info(f"Gas spent: {Web3.from_wei(result['gas_spent'], 'ether')} ETH")
                self.logger.info(f"Net profit: {Web3.from_wei(net_profit, 'ether')} ETH")
                self.logger.info(f"TX: {result['tx_hash']}")
            else:
                self.stats["failed_trades"] += 1
                self.logger.warning(f"✗ Trade failed: {result.get('error', 'Unknown error')}")
        
        except Exception as e:
            self.stats["failed_trades"] += 1
            self.logger.error(f"Error executing opportunity: {e}", exc_info=True)
    
    async def stop(self):
        """Stop the MEV bot"""
        self.running = False
        await self.mempool_monitor.stop()
        
        # Print final statistics
        self.logger.info("\n" + "=" * 60)
        self.logger.info("MEV Bot Statistics")
        self.logger.info("=" * 60)
        self.logger.info(f"Transactions analyzed: {self.stats['transactions_analyzed']}")
        self.logger.info(f"Opportunities found: {self.stats['opportunities_found']}")
        self.logger.info(f"Successful trades: {self.stats['successful_trades']}")
        self.logger.info(f"Failed trades: {self.stats['failed_trades']}")
        self.logger.info(f"Total profit: {Web3.from_wei(self.stats['total_profit_wei'], 'ether')} ETH")
        self.logger.info(f"Total gas spent: {Web3.from_wei(self.stats['total_gas_spent_wei'], 'ether')} ETH")
        
        net_profit = self.stats['total_profit_wei'] - self.stats['total_gas_spent_wei']
        self.logger.info(f"Net profit: {Web3.from_wei(net_profit, 'ether')} ETH")
        self.logger.info("=" * 60)
    
    def get_balance(self) -> int:
        """Get current wallet balance in wei"""
        return self.w3.eth.get_balance(self.address)
    
    def get_balance_eth(self) -> float:
        """Get current wallet balance in ETH"""
        return Web3.from_wei(self.get_balance(), 'ether')


def main():
    """Main entry point"""
    bot = MEVBot()
    
    try:
        # Run the bot
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")


if __name__ == "__main__":
    main()
