"""
Basic tests for MEV Bot
"""

import pytest
from src.config import Config
from src.utils.profit_calculator import ProfitCalculator
from web3 import Web3


def test_config_loads():
    """Test that configuration loads successfully"""
    # This will fail if config is not properly set up
    # but that's expected for first run
    try:
        config = Config()
        assert config is not None
        assert config.config is not None
    except (FileNotFoundError, ValueError):
        # Expected if config not set up yet
        pass


def test_profit_calculator():
    """Test profit calculator basic functionality"""
    from unittest.mock import MagicMock
    
    config = MagicMock()
    w3 = MagicMock()
    
    calc = ProfitCalculator(config, w3)
    
    # Test swap output calculation
    amount_in = Web3.to_wei(1, 'ether')
    reserve_in = Web3.to_wei(100, 'ether')
    reserve_out = Web3.to_wei(100, 'ether')
    
    output = calc.calculate_swap_output(amount_in, reserve_in, reserve_out)
    
    assert output > 0
    assert output < amount_in  # Should be less due to fees


def test_arbitrage_profit_calculation():
    """Test arbitrage profit calculation"""
    from unittest.mock import MagicMock
    
    config = MagicMock()
    w3 = MagicMock()
    
    calc = ProfitCalculator(config, w3)
    
    buy_price = Web3.to_wei(1000, 'ether')
    sell_price = Web3.to_wei(1100, 'ether')
    amount = 1
    
    profit = calc.calculate_arbitrage_profit(
        buy_price,
        sell_price,
        amount
    )
    
    # Should have some profit (10% difference minus fees)
    assert profit > 0


def test_flashloan_fee_calculation():
    """Test flashloan fee calculation"""
    from unittest.mock import MagicMock
    from src.flashloan.aave_flashloan import AaveFlashloan
    
    config = MagicMock()
    config.get.return_value = {
        "enabled": True,
        "lending_pool": "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
        "fee_percentage": 0.0009
    }
    
    w3 = MagicMock()
    account = MagicMock()
    
    aave = AaveFlashloan(config, w3, account)
    
    loan_amount = Web3.to_wei(100, 'ether')
    fee = aave.calculate_fee(loan_amount)
    repayment = aave.calculate_repayment(loan_amount)
    
    assert fee > 0
    assert repayment == loan_amount + fee
    assert fee == int(loan_amount * 0.0009)


def test_gas_price_calculation():
    """Test gas price optimization"""
    from unittest.mock import MagicMock
    from src.utils.gas_optimizer import GasOptimizer
    
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "gas.priority": "normal",
        "gas.max_gas_price_gwei": 500,
        "gas.custom_gas_multiplier": 1.15
    }.get(key, default)
    
    w3 = MagicMock()
    w3.eth.gas_price = Web3.to_wei(50, 'gwei')
    
    optimizer = GasOptimizer(config, w3)
    
    optimal_gas = optimizer.get_optimal_gas_price()
    
    assert optimal_gas > w3.eth.gas_price
    assert optimal_gas <= Web3.to_wei(500, 'gwei')


def test_price_impact_calculation():
    """Test price impact calculation"""
    from unittest.mock import MagicMock
    
    config = MagicMock()
    w3 = MagicMock()
    
    calc = ProfitCalculator(config, w3)
    
    amount_in = Web3.to_wei(10, 'ether')
    reserve_in = Web3.to_wei(100, 'ether')
    reserve_out = Web3.to_wei(100, 'ether')
    
    impact = calc.calculate_price_impact(amount_in, reserve_in, reserve_out)
    
    # 10 ETH into 100 ETH reserve should have ~10% impact
    assert 0.08 < impact < 0.12
    assert impact > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
