# Katkıda Bulunma Rehberi

Cezmi MEV Bot projesine katkıda bulunmak istediğiniz için teşekkürler! 🎉

## Katkı Yapma Yolları

### 1. Bug Raporları

Bug buldunuz mu? Lütfen şunları ekleyin:

- Bug'ın detaylı açıklaması
- Tekrar üretme adımları
- Beklenen davranış vs gerçek davranış
- Log çıktıları (private key'leri temizleyin!)
- Sistem bilgileri (OS, Python versiyonu)

### 2. Feature Önerileri

Yeni özellik önerisi:

- Özelliğin detaylı açıklaması
- Use case'ler
- Olası implementasyon yaklaşımı
- Alternatif çözümler

### 3. Code Katkıları

#### Başlamadan Önce

1. Issue açın veya mevcut bir issue'ya yorum yapın
2. Fork edin ve branch oluşturun
3. Development ortamını kurun

```bash
git clone https://github.com/YOUR_USERNAME/cezmi-bot.git
cd cezmi-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dev dependencies
```

#### Code Standards

**Python Style Guide:**
- PEP 8 kurallarına uyun
- Type hints kullanın
- Docstring'leri ekleyin

**Örnek:**

```python
def calculate_profit(
    amount_in: int,
    amount_out: int,
    gas_cost: int
) -> int:
    """
    Calculate net profit after gas costs
    
    Args:
        amount_in: Input amount in wei
        amount_out: Output amount in wei
        gas_cost: Gas cost in wei
        
    Returns:
        Net profit in wei
    """
    return amount_out - amount_in - gas_cost
```

#### Testing

Tüm yeni özellikler test edilmeli:

```bash
# Testleri çalıştır
pytest tests/

# Coverage ile
pytest --cov=src tests/

# Specific test
pytest tests/test_arbitrage.py -v
```

#### Commit Messages

Clear, descriptive commit messages:

```
Add sandwich attack slippage protection

- Implement configurable slippage threshold
- Add price impact calculation
- Update tests for new functionality
- Update documentation
```

### 4. Dokümantasyon

Dokümantasyon her zaman gelişebilir:

- README güncellemeleri
- Code comment'leri
- Tutorial'lar
- Örnekler

## Pull Request Süreci

### 1. Branch Oluşturma

```bash
git checkout -b feature/your-feature-name
# veya
git checkout -b fix/bug-description
```

### 2. Değişiklikleri Yapın

- Clear, focused commits
- Test ekleyin/güncelleyin
- Dokümantasyonu güncelleyin

### 3. Test Edin

```bash
# Linting
flake8 src/
black src/ --check

# Type checking
mypy src/

# Tests
pytest tests/ -v
```

### 4. Pull Request Açın

- Descriptive title
- Detaylı açıklama
- Related issues'a referans
- Screenshots (varsa)

**PR Template:**

```markdown
## Değişiklik Özeti
Kısa açıklama

## Değişiklik Tipi
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Test
Test etme yöntemlerini açıklayın

## Checklist
- [ ] Code PEP 8 uyumlu
- [ ] Tests eklendi/güncellendi
- [ ] Dokümantasyon güncellendi
- [ ] Tüm testler geçiyor
```

## Development Setup

### Gerekli Araçlar

```bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt`:
```
pytest>=7.4.3
pytest-asyncio>=0.21.1
pytest-cov>=4.1.0
black>=23.12.0
flake8>=6.1.0
mypy>=1.7.1
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Code Review Süreci

PR'lar şunlar için review edilir:

1. **Functionality**: Çalışıyor mu?
2. **Code Quality**: Temiz, okunabilir mi?
3. **Testing**: Yeterli test var mı?
4. **Documentation**: Dokümante edilmiş mi?
5. **Security**: Güvenli mi?

## Güvenlik

### Güvenlik Açıkları

Güvenlik açığı buldunuz mu?

**LÜTFEN public issue AÇMAYIN!**

Bunun yerine:
- Email: security@cezmibot.com
- Private vulnerability report

### Güvenlik Best Practices

- Private key'leri asla commit etmeyin
- Sensitive data'yı loglamayın
- Input validation yapın
- Rate limiting kullanın

## Stil Rehberi

### Python

```python
# Good
def calculate_profit(amount: int, fee: float) -> int:
    """Calculate profit after fees"""
    return int(amount * (1 - fee))

# Bad
def calc(x, y):
    return x * (1 - y)
```

### Logging

```python
# Good
self.logger.info(f"Trade executed: {tx_hash}")
self.logger.debug(f"Reserves: {reserve_in}/{reserve_out}")

# Bad
print("Trade done")
```

### Error Handling

```python
# Good
try:
    result = execute_trade()
except InsufficientFundsError as e:
    self.logger.error(f"Insufficient funds: {e}")
    return None
except Exception as e:
    self.logger.error(f"Unexpected error: {e}", exc_info=True)
    raise

# Bad
try:
    execute_trade()
except:
    pass
```

## Öncelikli Alanlar

Şu alanlarda katkılara özellikle ihtiyacımız var:

- [ ] Flashbots entegrasyonu
- [ ] Multi-chain desteği
- [ ] Machine learning modelleri
- [ ] Web dashboard
- [ ] Performance optimizasyonları
- [ ] Daha fazla test coverage

## Topluluk

### İletişim

- GitHub Discussions
- Discord (yakında)
- Twitter: [@cezmibot](https://twitter.com/cezmibot)

### Code of Conduct

- Saygılı olun
- Yapıcı eleştiri
- Yeni başlayanları destekleyin
- Inclusive ortam

## Lisans

Katkılarınız projenin lisansı (MIT) altında yayınlanacaktır.

## Sorular?

Sorularınız için:
- GitHub Discussions
- Issue açın
- Email: contribute@cezmibot.com

---

**Teşekkürler! 🙏**

Katkılarınız MEV Bot'u daha iyi hale getirir!
