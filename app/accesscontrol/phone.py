"""Normalisatie van telefoonnummers naar E.164 (+32470123456)."""
import re

import phonenumbers

DEFAULT_REGION = "BE"


class PhoneError(ValueError):
    pass


def normalize(raw: str | None, region: str = DEFAULT_REGION) -> str | None:
    """Geeft E.164 terug, None voor leeg, PhoneError voor ongeldig.

    Aanvaardt: +32 470 12 34 56, 0032470123456, 0470/12.34.56, 32470123456 (zoals de RTU logt).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.endswith(".0") and s[:-2].isdigit():   # Excel maakt soms een getal van het nummer
        s = s[:-2]
    if not s:
        return None
    s = re.sub(r"[\s./()\-]", "", s)
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.isdigit() and not s.startswith("0") and len(s) >= 10:
        s = "+" + s                              # landcode zonder + (RTU-formaat)
    if not re.fullmatch(r"\+?\d{6,16}", s):
        raise PhoneError(f"ongeldig telefoonnummer: {raw!r}")
    try:
        num = phonenumbers.parse(s, region)
    except phonenumbers.NumberParseException as e:
        raise PhoneError(f"ongeldig telefoonnummer: {raw!r}") from e
    if not phonenumbers.is_possible_number(num):
        raise PhoneError(f"ongeldig telefoonnummer: {raw!r}")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
