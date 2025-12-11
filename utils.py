"""
Yardımcı fonksiyonlar
"""
from web3 import Web3
import logging

logger = logging.getLogger(__name__)

def wei_to_ether(wei_amount: int) -> float:
    """Wei'yi Ether'e çevir"""
    return Web3.from_wei(wei_amount, 'ether')

def ether_to_wei(ether_amount: float) -> int:
    """Ether'i Wei'ye çevir"""
    return Web3.to_wei(ether_amount, 'ether')

def format_percentage(value: float, decimals: int = 2) -> str:
    """Yüzde değerini formatla"""
    return f"{value:.{decimals}f}%"

def calculate_profit_percentage(amount_in: int, amount_out: int) -> float:
    """Kar yüzdesini hesapla"""
    if amount_in == 0:
        return 0.0
    return ((amount_out - amount_in) / amount_in) * 100

def validate_address(address: str) -> bool:
    """Ethereum adresini doğrula"""
    try:
        return Web3.is_address(address) and Web3.is_checksum_address(address)
    except:
        return False

def to_checksum_address(address: str) -> str:
    """Adresi checksum formatına çevir"""
    return Web3.to_checksum_address(address)
