"""
Configuration management for MEV Bot
"""

import os
import yaml
from typing import Dict, Any
from pathlib import Path


class Config:
    """Configuration loader and manager"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration
        
        Args:
            config_path: Path to config file, defaults to config/config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()
        self.override_from_env()
    
    def load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            print(f"✓ Configuration loaded from {self.config_path}")
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
    
    def override_from_env(self):
        """Override config values from environment variables"""
        # Critical settings that should come from environment
        if os.getenv("PRIVATE_KEY"):
            self.config["wallet"]["private_key"] = os.getenv("PRIVATE_KEY")
        
        if os.getenv("RPC_URL"):
            network = self.config["blockchain"]["active_network"]
            chain, net = network.split(".")
            self.config["blockchain"][chain][net] = os.getenv("RPC_URL")
        
        if os.getenv("WEBSOCKET_URL"):
            self.config["blockchain"]["websocket_url"] = os.getenv("WEBSOCKET_URL")
    
    def get(self, key_path: str, default=None):
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Path to config value (e.g., "blockchain.ethereum.mainnet")
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key_path.split(".")
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any):
        """
        Set configuration value using dot notation
        
        Args:
            key_path: Path to config value (e.g., "strategies.arbitrage.enabled")
            value: Value to set
        """
        keys = key_path.split(".")
        config = self.config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
    
    def get_active_rpc(self) -> str:
        """Get the active RPC URL based on configuration"""
        network = self.get("blockchain.active_network")
        if not network:
            raise ValueError("No active network configured")
        
        chain, net = network.split(".")
        rpc_url = self.get(f"blockchain.{chain}.{net}")
        
        if not rpc_url or "YOUR_API_KEY" in rpc_url:
            raise ValueError(f"Invalid or placeholder RPC URL for {network}")
        
        return rpc_url
    
    def get_websocket_url(self) -> str:
        """Get WebSocket URL for mempool monitoring"""
        ws_url = self.get("blockchain.websocket_url")
        
        if not ws_url or "YOUR_API_KEY" in ws_url:
            raise ValueError("Invalid or placeholder WebSocket URL")
        
        return ws_url
    
    def is_strategy_enabled(self, strategy: str) -> bool:
        """Check if a strategy is enabled"""
        return self.get(f"strategies.{strategy}.enabled", False)
    
    def validate(self) -> bool:
        """
        Validate configuration
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        # Check critical settings
        if self.get("wallet.private_key") == "YOUR_PRIVATE_KEY_HERE":
            raise ValueError("Private key not configured! Set it in config.yaml or PRIVATE_KEY env variable")
        
        # Check RPC URL
        try:
            self.get_active_rpc()
        except ValueError as e:
            raise ValueError(f"RPC configuration error: {e}")
        
        # Check at least one strategy is enabled
        strategies = ["arbitrage", "sandwich", "frontrun", "backrun"]
        if not any(self.is_strategy_enabled(s) for s in strategies):
            raise ValueError("No strategies enabled! Enable at least one strategy.")
        
        print("✓ Configuration validated successfully")
        return True
    
    def __repr__(self):
        return f"Config(path={self.config_path})"
