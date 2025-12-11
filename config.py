"""
MEV Bot Konfigürasyon Dosyası
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Bot konfigürasyon ayarları"""
    
    # Blockchain Provider
    RPC_URL = os.getenv("RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY")
    
    # Wallet
    PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
    
    # Gas Ayarları
    MAX_GAS_PRICE_GWEI = float(os.getenv("MAX_GAS_PRICE_GWEI", "100"))
    GAS_LIMIT = int(os.getenv("GAS_LIMIT", "300000"))
    
    # Arbitraj Ayarları
    MIN_PROFIT_PERCENTAGE = float(os.getenv("MIN_PROFIT_PERCENTAGE", "0.5"))
    SLIPPAGE_TOLERANCE = float(os.getenv("SLIPPAGE_TOLERANCE", "0.5"))
    
    # DEX Router Adresleri (Ethereum Mainnet)
    UNISWAP_V2_ROUTER = os.getenv("UNISWAP_V2_ROUTER", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
    UNISWAP_V3_ROUTER = os.getenv("UNISWAP_V3_ROUTER", "0xE592427A0AEce92De3Edee1F18E0157C05861564")
    SUSHISWAP_ROUTER = os.getenv("SUSHISWAP_ROUTER", "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F")
    
    # İzleme Ayarları
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "1"))
    MAX_POSITION_SIZE_ETH = float(os.getenv("MAX_POSITION_SIZE_ETH", "1.0"))
    
    # Token Adresleri (Örnek - USDC, WETH)
    USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    
    @classmethod
    def validate(cls):
        """Konfigürasyonu doğrula"""
        if not cls.PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY .env dosyasında tanımlanmalı!")
        if not cls.RPC_URL or "YOUR_API_KEY" in cls.RPC_URL:
            raise ValueError("Geçerli bir RPC_URL .env dosyasında tanımlanmalı!")
        return True
