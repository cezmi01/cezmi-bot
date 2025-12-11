"""
Blockchain bağlantı ve işlem yönetimi modülü
"""
from web3 import Web3
from eth_account import Account
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BlockchainManager:
    """Blockchain bağlantısı ve işlem yönetimi"""
    
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(Config.RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError("Blockchain'e bağlanılamadı!")
        
        self.account = Account.from_key(Config.PRIVATE_KEY)
        self.address = self.account.address
        logger.info(f"Wallet adresi: {self.address}")
        
    def get_balance(self, token_address=None):
        """ETH veya token bakiyesini al"""
        if token_address is None:
            # ETH bakiyesi
            balance_wei = self.w3.eth.get_balance(self.address)
            return self.w3.from_wei(balance_wei, 'ether')
        else:
            # ERC20 token bakiyesi
            # Basit ERC20 ABI (sadece balanceOf için)
            abi = [{
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }]
            contract = self.w3.eth.contract(address=token_address, abi=abi)
            balance = contract.functions.balanceOf(self.address).call()
            return balance
    
    def get_gas_price(self):
        """Güncel gas fiyatını al"""
        gas_price = self.w3.eth.gas_price
        return self.w3.from_wei(gas_price, 'gwei')
    
    def estimate_gas(self, transaction):
        """İşlem için gas tahmini"""
        try:
            return self.w3.eth.estimate_gas(transaction)
        except Exception as e:
            logger.error(f"Gas tahmini hatası: {e}")
            return Config.GAS_LIMIT
    
    def send_transaction(self, transaction, max_gas_price_gwei=None):
        """İşlem gönder"""
        if max_gas_price_gwei is None:
            max_gas_price_gwei = Config.MAX_GAS_PRICE_GWEI
        
        # Gas fiyatını kontrol et
        current_gas = self.get_gas_price()
        if current_gas > max_gas_price_gwei:
            logger.warning(f"Gas fiyatı çok yüksek: {current_gas} Gwei (max: {max_gas_price_gwei})")
            return None
        
        # Bakiye kontrolü
        balance = self.get_balance()
        if transaction.get('value', 0) > 0:
            estimated_cost = transaction.get('value', 0) + (self.estimate_gas(transaction) * self.w3.to_wei(current_gas, 'gwei'))
            if estimated_cost > self.w3.eth.get_balance(self.address):
                logger.error("Yetersiz bakiye!")
                return None
        
        # Nonce al
        nonce = self.w3.eth.get_transaction_count(self.address)
        
        # İşlemi hazırla
        transaction.update({
            'nonce': nonce,
            'gasPrice': self.w3.to_wei(current_gas, 'gwei'),
            'gas': self.estimate_gas(transaction),
            'chainId': self.w3.eth.chain_id
        })
        
        # İşlemi imzala
        signed_txn = self.account.sign_transaction(transaction)
        
        # İşlemi gönder
        try:
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            logger.info(f"İşlem gönderildi: {tx_hash.hex()}")
            return tx_hash.hex()
        except ValueError as e:
            logger.error(f"İşlem gönderme hatası (ValueError): {e}")
            return None
        except Exception as e:
            logger.error(f"İşlem gönderme hatası: {e}")
            return None
    
    def wait_for_transaction(self, tx_hash, timeout=300):
        """İşlemin onaylanmasını bekle"""
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            if receipt.status == 1:
                logger.info(f"İşlem başarılı: {tx_hash}")
                return True
            else:
                logger.error(f"İşlem başarısız: {tx_hash}")
                return False
        except Exception as e:
            logger.error(f"İşlem bekleme hatası: {e}")
            return False
    
    def get_token_price_from_dex(self, token_in, token_out, amount_in, router_address, router_abi):
        """DEX'ten token fiyatını al (getAmountsOut kullanarak)"""
        try:
            contract = self.w3.eth.contract(address=router_address, abi=router_abi)
            path = [token_in, token_out]
            amounts = contract.functions.getAmountsOut(amount_in, path).call()
            return amounts[-1]  # Son değer çıktı miktarı
        except Exception as e:
            logger.error(f"Fiyat alma hatası ({router_address}): {e}")
            return None
