"""Bounded exact catalog inputs; these limits are not business price ceilings."""
from decimal import Decimal, InvalidOperation
import re
from typing import Annotated

from pydantic import BeforeValidator, Field

LIMITS = {'integerDigits': 512, 'decimalPlaces': 512, 'coefficientDigits': 1024, 'inputCharacters': 2048}
MESSAGE = 'Enter a non-negative finite catalog decimal with at most 512 integer digits, 512 decimal places and 1024 coefficient digits (2048 input characters).'
PATTERN = re.compile(r'^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$', re.ASCII)


def checked_catalog_decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(MESSAGE)
    text = str(value).strip()
    if len(text) > LIMITS['inputCharacters'] or not PATTERN.fullmatch(text):
        raise ValueError(MESSAGE)
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(MESSAGE) from error
    if not number.is_finite():
        raise ValueError(MESSAGE)
    digits = number.as_tuple()
    # Inspect compact decimal metadata; never expand an untrusted exponent.
    integer_digits = max(number.adjusted() + 1, 0) if number else 0
    if (len(digits.digits) > LIMITS['coefficientDigits']
            or digits.exponent > LIMITS['integerDigits']
            or max(-digits.exponent, 0) > LIMITS['decimalPlaces']
            or integer_digits > LIMITS['integerDigits']):
        raise ValueError(MESSAGE)
    return number


# The explicit finite check above avoids Pydantic's generic math.isfinite
# validator, which can round-trip an annotated Decimal through a float.
CatalogDecimal = Annotated[Decimal, BeforeValidator(checked_catalog_decimal), Field(ge=0)]


def catalog_text(value):
    """Display fixed notation while retaining scale, including zero's scale.

    Apply only at the catalog API boundary, never to stored profile snapshots.
    """
    if value is None:
        return None
    return format(value, 'f') if isinstance(value, Decimal) else str(value)
