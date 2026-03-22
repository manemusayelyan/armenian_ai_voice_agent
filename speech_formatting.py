import re


ARMENIAN_DIGITS = {
    0: "զրո",
    1: "մեկ",
    2: "երկու",
    3: "երեք",
    4: "չորս",
    5: "հինգ",
    6: "վեց",
    7: "յոթ",
    8: "ութ",
    9: "ինը",
}

ARMENIAN_TEENS = {
    10: "տաս",
    11: "տասնմեկ",
    12: "տասներկու",
    13: "տասներեք",
    14: "տասնչորս",
    15: "տասնհինգ",
    16: "տասնվեց",
    17: "տասնյոթ",
    18: "տասնութ",
    19: "տասնինը",
}

ARMENIAN_TENS = {
    20: "քսան",
    30: "երեսուն",
    40: "քառասուն",
    50: "հիսուն",
    60: "վաթսուն",
    70: "յոթանասուն",
    80: "ութանասուն",
    90: "իննսուն",
}

SCALES = (
    (1_000_000_000, "միլիարդ"),
    (1_000_000, "միլիոն"),
    (1_000, "հազար"),
)

CURRENCY_WORDS = {
    "AMD": "դրամ",
    "USD": "ամերիկյան դոլար",
    "EUR": "եվրո",
    "RUB": "ռուբլի",
    "ՀՀ դրամ": "դրամ",
}

UNIT_WORDS = {
    "ամիս": "ամիս",
    "օր": "օր",
    "տարի": "տարի",
    "տոկոս": "տոկոս",
}

NUMBER_PATTERN = r"\d(?:[\d\s,\.․]*\d)?"


def format_for_armenian_tts(text: str) -> str:
    spoken = text
    spoken = spoken.replace("ACBA", "ԱԿԲԱ")
    spoken = spoken.replace("AEB", "Արմէկոնոմբանկ")
    spoken = spoken.replace("մլն", "միլիոն")
    spoken = spoken.replace("մլրդ", "միլիարդ")
    spoken = spoken.replace("դր.", "դրամ")

    spoken = _replace_slash_numbers(spoken)
    spoken = _replace_percent_ranges(spoken)
    spoken = _replace_currency_amounts(spoken)
    spoken = _replace_number_ranges_with_units(spoken)
    spoken = _replace_plain_percents(spoken)
    spoken = _replace_numbers_with_units(spoken)
    spoken = _replace_standalone_numbers(spoken)
    spoken = _replace_currency_codes(spoken)

    return re.sub(r"\s+", " ", spoken).strip()


def _replace_slash_numbers(text: str) -> str:
    pattern = re.compile(rf"(?P<left>{NUMBER_PATTERN})/(?P<right>{NUMBER_PATTERN})")
    return pattern.sub(
        lambda match: (
            f"{number_to_armenian_address_words(match.group('left'))} կոտորակ "
            f"{number_to_armenian_address_words(match.group('right'))}"
        ),
        text,
    )


def _replace_percent_ranges(text: str) -> str:
    pattern = re.compile(
        rf"(?P<start>{NUMBER_PATTERN})\s*[-–]\s*(?P<end>{NUMBER_PATTERN})\s*%"
    )
    return pattern.sub(
        lambda match: (
            f"{number_to_armenian_words(match.group('start'))}ից "
            f"{number_to_armenian_words(match.group('end'))} տոկոս"
        ),
        text,
    )


def _replace_currency_amounts(text: str) -> str:
    currencies = "|".join(re.escape(code) for code in sorted(CURRENCY_WORDS, key=len, reverse=True))
    pattern = re.compile(rf"(?P<num>{NUMBER_PATTERN})\s*(?P<curr>{currencies})\b")
    return pattern.sub(
        lambda match: (
            f"{number_to_armenian_words(match.group('num'))} "
            f"{CURRENCY_WORDS[match.group('curr')]}"
        ),
        text,
    )


def _replace_number_ranges_with_units(text: str) -> str:
    units = "|".join(re.escape(unit) for unit in UNIT_WORDS if unit != "տոկոս")
    pattern = re.compile(
        rf"(?P<start>{NUMBER_PATTERN})\s*[-–]\s*(?P<end>{NUMBER_PATTERN})\s*(?P<unit>{units})\b"
    )
    return pattern.sub(
        lambda match: (
            f"{number_to_armenian_words(match.group('start'))}ից "
            f"{number_to_armenian_words(match.group('end'))} "
            f"{match.group('unit')}"
        ),
        text,
    )


def _replace_plain_percents(text: str) -> str:
    pattern = re.compile(rf"(?P<num>{NUMBER_PATTERN})\s*%")
    return pattern.sub(
        lambda match: f"{number_to_armenian_words(match.group('num'))} տոկոս",
        text,
    )


def _replace_numbers_with_units(text: str) -> str:
    units = "|".join(re.escape(unit) for unit in UNIT_WORDS.values())
    pattern = re.compile(rf"(?P<num>{NUMBER_PATTERN})\s*(?P<unit>{units})\b")
    return pattern.sub(
        lambda match: (
            f"{number_to_armenian_words(match.group('num'))} "
            f"{match.group('unit')}"
        ),
        text,
    )


def _replace_standalone_numbers(text: str) -> str:
    pattern = re.compile(rf"(?<![\w/])(?P<num>{NUMBER_PATTERN})(?![\w/])")
    return pattern.sub(
        lambda match: number_to_armenian_words(match.group("num")),
        text,
    )


def _replace_currency_codes(text: str) -> str:
    for code, spoken in CURRENCY_WORDS.items():
        text = re.sub(rf"\b{re.escape(code)}\b", spoken, text)
    return text


def number_to_armenian_words(raw_number: str) -> str:
    parsed = _parse_number(raw_number)
    if parsed is None:
        return raw_number

    integer_part, fractional_part = parsed
    integer_words = _int_to_words(integer_part)

    if not fractional_part:
        return integer_words

    fractional_part = fractional_part.rstrip("0")
    if not fractional_part:
        return integer_words

    if len(fractional_part) <= 2:
        fractional_words = _int_to_words(int(fractional_part))
    else:
        fractional_words = " ".join(ARMENIAN_DIGITS[int(digit)] for digit in fractional_part)

    return f"{integer_words} ամբողջ {fractional_words}"


def number_to_armenian_address_words(raw_number: str) -> str:
    parsed = _parse_number(raw_number)
    if parsed is None:
        return raw_number

    integer_part, fractional_part = parsed
    if fractional_part:
        return number_to_armenian_words(raw_number)

    return _int_to_address_words(integer_part)


def _parse_number(raw_number: str) -> tuple[int, str | None] | None:
    cleaned = (
        raw_number.strip()
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("․", ".")
    )
    if not cleaned or "/" in cleaned:
        return None

    if cleaned.isdigit():
        return int(cleaned), None

    if _looks_grouped_integer(cleaned, ".") or _looks_grouped_integer(cleaned, ","):
        return int(cleaned.replace(".", "").replace(",", "")), None

    if "." in cleaned and "," in cleaned:
        decimal_sep = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        integer_part, fractional_part = cleaned.rsplit(decimal_sep, 1)
        integer_part = integer_part.replace(thousands_sep, "")
        if integer_part.isdigit() and fractional_part.isdigit():
            return int(integer_part), fractional_part
        return None

    for separator in (".", ","):
        if separator not in cleaned:
            continue
        left, right = cleaned.split(separator, 1)
        if not left.isdigit() or not right.isdigit():
            return None
        if len(right) == 3 and len(left) >= 1:
            return int(left + right), None
        return int(left), right

    return None


def _looks_grouped_integer(value: str, separator: str) -> bool:
    if separator not in value:
        return False
    parts = value.split(separator)
    if not parts or not parts[0].isdigit():
        return False
    return all(part.isdigit() and len(part) == 3 for part in parts[1:])


def _int_to_words(number: int) -> str:
    if number < 0:
        return f"մինուս {_int_to_words(abs(number))}"
    if number < 10:
        return ARMENIAN_DIGITS[number]
    if number < 20:
        return ARMENIAN_TEENS[number]
    if number < 100:
        tens = (number // 10) * 10
        rest = number % 10
        if rest == 0:
            return ARMENIAN_TENS[tens]
        return f"{ARMENIAN_TENS[tens]} {_int_to_words(rest)}"
    if number < 1_000:
        hundreds = number // 100
        rest = number % 100
        prefix = "հարյուր" if hundreds == 1 else f"{_int_to_words(hundreds)} հարյուր"
        if rest == 0:
            return prefix
        return f"{prefix} {_int_to_words(rest)}"

    for scale_value, scale_word in SCALES:
        if number >= scale_value:
            lead = number // scale_value
            rest = number % scale_value
            if scale_value == 1_000 and lead == 1:
                prefix = scale_word
            else:
                prefix = f"{_int_to_words(lead)} {scale_word}"
            if rest == 0:
                return prefix
            return f"{prefix} {_int_to_words(rest)}"

    return str(number)


def _int_to_address_words(number: int) -> str:
    if 10 < number < 20:
        return f"տասնը {ARMENIAN_DIGITS[number - 10]}"
    if number < 10:
        return ARMENIAN_DIGITS[number]
    if number < 100:
        tens = (number // 10) * 10
        rest = number % 10
        if rest == 0:
            return ARMENIAN_TENS.get(tens, _int_to_words(number))
        return f"{ARMENIAN_TENS.get(tens, _int_to_words(tens))} {_int_to_address_words(rest)}"
    if number < 1_000:
        hundreds = number // 100
        rest = number % 100
        prefix = "հարյուր" if hundreds == 1 else f"{_int_to_words(hundreds)} հարյուր"
        if rest == 0:
            return prefix
        return f"{prefix} {_int_to_address_words(rest)}"

    for scale_value, scale_word in SCALES:
        if number >= scale_value:
            lead = number // scale_value
            rest = number % scale_value
            if scale_value == 1_000 and lead == 1:
                prefix = scale_word
            else:
                prefix = f"{_int_to_words(lead)} {scale_word}"
            if rest == 0:
                return prefix
            return f"{prefix} {_int_to_address_words(rest)}"

    return str(number)
