"""Finite planning estimates only. Never use these helpers to value actual stock."""
from decimal import Decimal, InvalidOperation
import math


def number(value, default=None):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return None
    try:
        exact = Decimal(str(value))
        converted = float(exact)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None
    if not exact.is_finite() or not math.isfinite(converted) or (converted == 0 and exact != 0):
        return None
    return converted


def product(*values):
    result = 1.0
    for value in values:
        value = number(value)
        if value is None:
            return None
        next_value = result * value
        if not math.isfinite(next_value) or (next_value == 0 and result != 0 and value != 0):
            return None
        result = next_value
    return result


def quotient(numerator, denominator):
    numerator, denominator = number(numerator), number(denominator)
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) and not (result == 0 and numerator != 0) else None


def total(values):
    values = [number(value) for value in values]
    if any(value is None for value in values):
        return None
    try:
        result = math.fsum(values)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def money(value, places=2):
    value = number(value)
    return 'Unknown (outside supported calculation range)' if value is None else f'${value:,.{places}f}'


def rounded(value, places=2):
    value = number(value)
    return round(value, places) if value is not None else None
