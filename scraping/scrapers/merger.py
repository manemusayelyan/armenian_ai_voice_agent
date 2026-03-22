import json
import os
import glob
import re
import sys


URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[\w.+\-\u2024]+@[\w-]+(?:[.\u2024][\w-]+)+\b", re.IGNORECASE)
BANK_NAME_MAP = {
    "ACBA Bank": "ԱԿԲԱ Բանկ",
    "Armeconombank": "Արմէկոնոմբանկ",
    "Fast Bank": "Ֆասթ Բանկ",
}
CHANNEL_MARKER_PATTERN = re.compile(
    r"(?i)\b(?:acba\s*digital|AEB\s*(?:MOBILE/ONLINE|ONLINE/MOBILE|Mobile|ONLINE|online|MOBILE)|Telcell)\b"
)
DATE_PATTERN = re.compile(r"\d{1,2}[./․]\d{1,2}[./․]\d{2,4}")
CARD_BRAND_PATTERN = re.compile(
    r"(?i)\b(?:Visa|MasterCard|American Express|ArCa|ARMEC(?:['’]s)?)\b"
)
CARD_ONLY_WORD_PATTERN = re.compile(
    r"(?i)\b(?:visa|mastercard|american|express|arca|armec(?:['’]s)?|blue|gold|classic|standard|signature|cashback|guru|travel|uefa|champions|league|barerar|transfer|maestro)\b"
)
CURRENCY_REPLACEMENTS = (
    (re.compile(r"(?i)(?<![A-Za-zԱ-Ֆա-ֆ])AMD(?![A-Za-zԱ-Ֆա-ֆ])"), "ՀՀ դրամ"),
    (re.compile(r"(?i)(?<![A-Za-zԱ-Ֆա-ֆ])USD(?![A-Za-zԱ-Ֆա-ֆ])"), "ԱՄՆ դոլար"),
    (re.compile(r"(?i)(?<![A-Za-zԱ-Ֆա-ֆ])EUR(?![A-Za-zԱ-Ֆա-ֆ])"), "եվրո"),
    (re.compile(r"(?i)(?<![A-Za-zԱ-Ֆա-ֆ])EURO(?![A-Za-zԱ-Ֆա-ֆ])"), "եվրո"),
    (re.compile(r"(?i)(?<![A-Za-zԱ-Ֆա-ֆ])RUB(?![A-Za-zԱ-Ֆա-ֆ])"), "ռուբլի"),
)
TEXT_REPLACEMENTS = (
    (re.compile(r"(?i)\bAKNթարթ\b"), "Ակնթարթ"),
    (re.compile(r"Դավթաշեն I թաղամաս"), "Դավթաշեն առաջին թաղամաս"),
    (re.compile(r"(?i)/LTV/"), ""),
    (re.compile(r"(?i)\(LTV\)"), ""),
    (re.compile(r"(?i)\bLTV\b"), ""),
    (re.compile(r"(?i)\bArca\s+Credit\b"), "Արկա Կրեդիտ"),
    (re.compile(r"(?i)\bSUNLAND\s+BAGREVAND\b"), "Սանլենդ Բագրևանդ"),
    (re.compile(r"(?i)\bGuru\s+Travel\b"), "Գուրու Թրեվլ"),
    (re.compile(r"(?i)\bGuru\b"), "Գուրու"),
    (re.compile(r"(?i)\bTravel\b"), "Թրեվլ"),
    (re.compile(r"(?i)\b5G\b"), "5Ջի"),
)
CHANNEL_REPLACEMENTS = (
    (
        re.compile(
            r"(?i)\bAEB\s*(?:MOBILE/ONLINE|ONLINE/MOBILE|Mobile\s*/\s*AEB\s*online|Mobile\s*և\s*AEB\s*online|Mobile|ONLINE|online|MOBILE)\b(?:\s+համակարգ(?:երով|ով|ում))?"
        ),
        "առցանց",
    ),
    (
        re.compile(r"(?i)\bacba\s*digital(?:-\w+)?\b(?:\s+համակարգ(?:ով|ում))?"),
        "առցանց",
    ),
    (
        re.compile(r"(?i)\bTelcell\b(?:\s+մոբայլ\s+հավելված(?:ում|ով)?)?"),
        "առցանց",
    ),
    (
        re.compile(r"(?i)\bAEB\b"),
        "առցանց",
    ),
    (
        re.compile(r"(?i)\bմոբայլ\s+հավելված(?:ում|ով)?\b"),
        "",
    ),
)
TITLE_CHANNEL_PATTERN = re.compile(
    r"(?i)\b(?:acba\s*digital|AEB\s*(?:MOBILE/ONLINE|ONLINE/MOBILE|Mobile|ONLINE|online|MOBILE))\b(?:\s+համակարգ(?:երով|ով))?\s*"
)


def _sanitize_line(text: str) -> str:
    text = (text or "").replace("\xa0", " ").replace("\r", " ")
    text = URL_PATTERN.sub("", text)
    text = EMAIL_PATTERN.sub("", text)
    for pattern, replacement in TEXT_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = text.replace("*", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" |")


def _should_drop_noise_line(text: str) -> bool:
    normalized = (text or "").casefold()
    noise_markers = (
        "https://",
        "http://",
        "www.",
        "website",
        "source",
        "էլ. հասցե",
        "էլ․ հասցե",
        "email",
        "e-mail",
        "կայք",
    )
    return any(marker in normalized for marker in noise_markers)


def _has_numeric_signal(text: str) -> bool:
    normalized = (text or "").casefold()
    return bool(
        any(char.isdigit() for char in text)
        or "%" in text
        or any(
            marker in normalized
            for marker in ("դրամ", "amd", "usd", "eur", "rub", "ամիս", "օր", "տոկոս", "ժամկետ")
        )
    )


def _normalize_channel_noise(text: str) -> str:
    cleaned = text or ""
    for pattern, replacement in CHANNEL_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = re.sub(r"\((?:[^()]*առցանց[^()]*)\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-–—]\s*առցանց\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bառցանց\s*[:\-]\s*(?=\d)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bառցանց\b\s*(?=%|\d)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?i)\bառցանց\b(?:\s+և\s+\bառցանց\b)+", "առցանց", cleaned)
    cleaned = re.sub(r"(?i)\bառցանց\b(?:\s+\bառցանց\b)+", "առցանց", cleaned)
    return _sanitize_line(cleaned)


def _localize_currencies(text: str) -> str:
    cleaned = text or ""
    for pattern, replacement in CURRENCY_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"(\d)(ՀՀ դրամ|ԱՄՆ դոլար|եվրո|ռուբլի)\b", r"\1 \2", cleaned)
    cleaned = re.sub(r"\b(ՀՀ դրամ|ԱՄՆ դոլար|եվրո|ռուբլի)\s+(ՀՀ դրամ|ԱՄՆ դոլար|եվրո|ռուբլի)\b", r"\1", cleaned)
    return _sanitize_line(cleaned)


def _sanitize_heading(text: str) -> str:
    cleaned = TITLE_CHANNEL_PATTERN.sub("", text or "")
    cleaned = re.sub(r"(?i)^AEB\s+", "", cleaned)
    cleaned = _localize_currencies(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _sanitize_line(cleaned.strip(" -:"))


def _is_brand_only_segment(text: str) -> bool:
    cleaned = _sanitize_line(text)
    if not cleaned or not CARD_BRAND_PATTERN.search(cleaned):
        return False
    stripped = CARD_ONLY_WORD_PATTERN.sub(" ", cleaned)
    stripped = re.sub(r"[0-9%.,/()'’:+\-]", " ", stripped)
    stripped = re.sub(r"\b(?:ՀՀ|դրամ)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return not stripped


def _strip_card_brand_prefix(segment: str) -> str:
    cleaned = _sanitize_line(segment)
    if not cleaned:
        return ""
    if re.match(r"(?i)^(?:Visa|MasterCard|American Express|ArCa)\b.+?\s[-–—]\s", cleaned):
        cleaned = re.sub(
            r"(?i)^(?:Visa|MasterCard|American Express|ArCa)\b.+?\s[-–—]\s*",
            "",
            cleaned,
            count=1,
        )
    return _sanitize_line(cleaned)


def _should_drop_context_line(text: str) -> bool:
    normalized = (text or "").casefold()
    has_channel = bool(CHANNEL_MARKER_PATTERN.search(text)) or "առցանց" in normalized
    if has_channel and (
        normalized.startswith(("ձևակերպեք", "ստացի", "ստացիր", "օգտվե", "դիմի՛ր"))
        or "գործում են հետևյալ տոկոսադրույքները" in normalized
        or "համակարգով տրամադրվող վարկեր" in normalized
        or "դիմումը ներկայացնելու պահին" in normalized
        or DATE_PATTERN.search(text)
    ):
        return True
    if re.match(r"(?i)^(?:Visa|MasterCard|American Express|ArCa)\b", text) and _has_numeric_signal(text):
        return True
    return False


def _normalize_context_line(text: str) -> str:
    line = _sanitize_line(text)
    if not line or _should_drop_noise_line(line):
        return ""

    line = _normalize_channel_noise(line)
    line = _localize_currencies(line)
    line = re.sub(
        r"(?i)American Express\s+[A-Za-z0-9'’\-/ ]+(?=\s+քարտ(?:երով|երի|ով)?)",
        "որոշ",
        line,
    )
    if not line or _should_drop_context_line(line):
        return ""

    raw_segments = [_sanitize_line(part) for part in line.split("|")]
    segments = []
    for segment in raw_segments:
        if not segment:
            continue
        segments.append(segment)

    if not segments:
        return ""

    first_segment = segments[0]
    first_normalized = first_segment.casefold()

    if first_normalized.startswith("քարտատեսակ "):
        segments[0] = "Քարտատեսակ"
    elif first_normalized.startswith("քարտի տեսակը "):
        segments[0] = "Քարտի տեսակը"

    if len(segments) == 1 and re.match(r"(?i)^(?:Visa|MasterCard|American Express|ArCa)\b", segments[0]):
        return ""

    cleaned_segments = []
    seen = set()
    for index, segment in enumerate(segments):
        current = segment
        if index > 0:
            current = _strip_card_brand_prefix(current)
        current = _sanitize_line(current)
        if not current:
            continue
        if index > 0 and _is_brand_only_segment(current):
            continue

        key = current.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned_segments.append(current)

    if not cleaned_segments:
        return ""

    if cleaned_segments[0] in {"Քարտի տեսակը", "Քարտատեսակ"}:
        tail = cleaned_segments[1:]
        if not tail:
            return ""
        if not any(_has_numeric_signal(segment) for segment in tail):
            return ""

    return " | ".join(cleaned_segments)


def _sanitize_paragraph(text: str) -> str:
    text = (text or "").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"\s+\|\s+", "\n", text)

    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = _normalize_context_line(raw_line)
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)

    return "\n".join(lines)


def _sanitize_block(text: str) -> str:
    text = (text or "").replace("\r", "\n").replace("\xa0", " ")

    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = _normalize_context_line(raw_line)
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)

    return "\n".join(lines)


def _indent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


def _safe_console_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(text).encode(encoding, errors="backslashreplace").decode(
        encoding,
        errors="replace",
    )


def _localize_bank_name(bank_name: str) -> str:
    bank_name = _sanitize_line(bank_name)
    return BANK_NAME_MAP.get(bank_name, bank_name)


def build_context_string(data_dir: str = "data") -> str:
    """
    Load scraped bank datasets and merge them into one plain-text string
    suitable for injection into an LLM system prompt.
    """
    banks = load_bank_data(data_dir=data_dir)
    if not banks:
        raise FileNotFoundError(f"No scraped bank JSON files found in {data_dir}/")

    sections = []

    for bank in banks:
        lines = []
        lines.append(f"{'='*60}")
        lines.append(f"ԲԱՆԿ: {_localize_bank_name(bank.get('bank', 'Անհայտ'))}")
        lines.append(f"{'='*60}")

        # --- Credits ---
        lines.append("\n[ՎԱՐԿԵՐ]")
        if bank.get("credits"):
            for c in bank["credits"]:
                lines.append(f"\n  Վարկ: {_sanitize_heading(c.get('type', 'Անհայտ'))}")
                if c.get("parent_type"):
                    lines.append(f"  {_sanitize_heading(c['parent_type'])}")
                details = _sanitize_paragraph(c.get("details", ""))
                if details:
                    lines.append("  Մանրամասներ:")
                    lines.append(_indent_block(details))
                rates_table = _sanitize_block(c.get("rates_table", ""))
                if rates_table:
                    lines.append("  Տոկոսադրույքների աղյուսակ:")
                    lines.append(_indent_block(rates_table))
        else:
            lines.append("  Վարկերի տվյալներ չեն գտնվել։")

        # --- Deposits ---
        lines.append("\n[ԱՎԱՆԴՆԵՐ]")
        if bank.get("deposits"):
            for d in bank["deposits"]:
                lines.append(f"\n  Ավանդ: {_sanitize_heading(d.get('type', 'Անհայտ'))}")
                if d.get("parent_type"):
                    lines.append(f"  {_sanitize_heading(d['parent_type'])}")
                details = _sanitize_paragraph(d.get("details", ""))
                if details:
                    lines.append("  Մանրամասներ:")
                    lines.append(_indent_block(details))
                rates_table = _sanitize_block(d.get("rates_table", ""))
                if rates_table:
                    lines.append("  Տոկոսադրույքների աղյուսակ:")
                    lines.append(_indent_block(rates_table))
        else:
            lines.append("  Ավանդների տվյալներ չեն գտնվել։")

        # --- Branches ---
        lines.append("\n[ՄԱՍՆԱՃՅՈՒՂԵՐ]")
        if bank.get("branches"):
            for b in bank["branches"]:
                name = _sanitize_line(b.get("name", "Անհայտ"))
                address = _sanitize_line(b.get("address", ""))
                if address:
                    lines.append(f"  - {name}: {address}")
                else:
                    lines.append(f"  - {name}")
        else:
            lines.append("  Մասնաճյուղերի տվյալներ չեն գտնվել։")

        sections.append("\n".join(lines))

    full_context = "\n\n".join(sections)
    return full_context


def load_bank_data(data_dir: str = "data") -> list[dict]:
    """
    Load bank data from split dataset files.
    Falls back to the legacy top-level bank JSON files when needed.
    """
    banks = _load_split_bank_data(data_dir=data_dir)
    if banks:
        return banks
    return _load_legacy_bank_data(data_dir=data_dir)


def _load_split_bank_data(data_dir: str) -> list[dict]:
    subdir_configs = (
        ("loans", "credits"),
        ("deposits", "deposits"),
        ("branches", "branches"),
    )
    banks_by_key = {}

    for subdir, dataset_key in subdir_configs:
        pattern = os.path.join(data_dir, subdir, "*.json")
        for filepath in sorted(glob.glob(pattern)):
            with open(filepath, "r", encoding="utf-8") as f:
                payload = json.load(f)

            bank_name = payload.get("bank", "").strip()
            bank_url = payload.get("url", "").strip()
            if not bank_name:
                continue

            bank_key = _normalize_bank_key(bank_name)
            bank = banks_by_key.setdefault(
                bank_key,
                {
                    "bank": bank_name,
                    "url": bank_url,
                    "scraped_at": payload.get("scraped_at", ""),
                    "credits": [],
                    "deposits": [],
                    "branches": [],
                },
            )

            if bank_url and not bank.get("url"):
                bank["url"] = bank_url
            bank["scraped_at"] = _latest_date(
                bank.get("scraped_at", ""),
                payload.get("scraped_at", ""),
            )
            bank[dataset_key] = payload.get(dataset_key, [])

    return sorted(banks_by_key.values(), key=lambda bank: _normalize_bank_key(bank["bank"]))


def _load_legacy_bank_data(data_dir: str) -> list[dict]:
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    banks = []

    for filepath in sorted(json_files):
        with open(filepath, "r", encoding="utf-8") as f:
            banks.append(json.load(f))

    return banks


def _normalize_bank_key(bank_name: str) -> str:
    return " ".join(bank_name.lower().split())


def _latest_date(current_value: str, candidate_value: str) -> str:
    current_value = (current_value or "").strip()
    candidate_value = (candidate_value or "").strip()
    if not current_value:
        return candidate_value
    if not candidate_value:
        return current_value
    return max(current_value, candidate_value)


def save_context(context: str, output_path: str = "data/bank_context.txt") -> None:
    """Save the merged context string to a text file."""
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(context)
    size_kb = len(context.encode("utf-8")) / 1024
    print(f"\n[+] Context saved to: {_safe_console_text(output_path)}")
    print(f"[+] Total size: {size_kb:.1f} KB")
    print(f"[+] Total characters: {len(context):,}")


def load_context(path: str = "data/bank_context.txt") -> str:
    """Load the pre-built context string (used by the agent at runtime)."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
