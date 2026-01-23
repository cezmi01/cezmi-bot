from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_UP


def to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def decimal_places(step: Decimal) -> int:
    exponent = step.normalize().as_tuple().exponent
    return max(-exponent, 0)


def round_down(value: Decimal, step: Decimal) -> Decimal:
    value = to_decimal(value)
    step = to_decimal(step)
    if step == 0:
        return value
    factor = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return factor * step


def round_up(value: Decimal, step: Decimal) -> Decimal:
    value = to_decimal(value)
    step = to_decimal(step)
    if step == 0:
        return value
    factor = (value / step).to_integral_value(rounding=ROUND_UP)
    return factor * step


def format_decimal(value: Decimal, step: Decimal) -> str:
    value = to_decimal(value)
    places = decimal_places(step)
    quant = Decimal("1").scaleb(-places)
    return f"{value.quantize(quant):.{places}f}"


def clamp_min(value: Decimal, minimum: Decimal) -> Decimal:
    value = to_decimal(value)
    minimum = to_decimal(minimum)
    return value if value >= minimum else minimum
