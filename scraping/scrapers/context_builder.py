import re

from .merger import (
    _localize_bank_name,
    _sanitize_block,
    _sanitize_heading,
    _sanitize_line,
    _sanitize_paragraph,
    load_bank_data,
    load_context,
    save_context,
)


FACT_PRIORITY_LABELS = (
    "Արժույթ",
    "Արժույթներ",
    "Նվազագույն գումար",
    "Առավելագույն գումար",
    "Գումար",
    "Ժամկետ",
    "Տևողություն",
    "Տոկոսադրույք",
    "Տարեկան անվանական տոկոսադրույք",
    "Տարեկան արդյունավետ տոկոսադրույք",
    "Տարեկան տոկոսային եկամտաբերություն",
    "Բոնուս",
    "Ապահովվածություն",
    "Գրավ",
    "Կանխավճար",
    "Մարման ձև",
    "Մարումներ",
    "Վճարման հաճախականություն",
    "Նպատակ",
)

RATE_MARKERS = (
    "%",
    "տոկոս",
    "տոկոսադրույք",
    "եկամտաբեր",
    "բոնուս",
    "դրամ",
    "դոլար",
    "եվրո",
    "ռուբլի",
    "ամիս",
    "տարի",
)

NOTE_MARKERS = (
    "գործում է",
    "առցանց",
    "մասնաճյուղ",
    "առանց գրավ",
    "գրավով",
    "բանկի միջոցով",
)


def _normalize_casefold(text: str) -> str:
    return _sanitize_line(text).casefold()


def _split_sanitized_lines(text: str, *, paragraph: bool) -> list[str]:
    sanitized = _sanitize_paragraph(text) if paragraph else _sanitize_block(text)
    return [line.strip() for line in sanitized.splitlines() if line.strip()]


def _extract_label_value(line: str) -> tuple[str, str]:
    separator = ""
    for candidate in (":", "՝"):
        if candidate in line:
            separator = candidate
            break
    if not separator:
        return "", ""

    label, value = line.split(separator, 1)
    label = re.sub(r"^\d+\.\s*", "", label.strip())
    label = _sanitize_heading(label).strip(" :")
    value = _sanitize_line(value)
    if not label or not value or len(label) > 60:
        return "", ""

    return label, value


def _fact_priority(label: str) -> int:
    normalized_label = _normalize_casefold(label)
    for index, candidate in enumerate(FACT_PRIORITY_LABELS):
        if _normalize_casefold(candidate) in normalized_label:
            return index
    return len(FACT_PRIORITY_LABELS) + 1


def _extract_key_facts(product: dict) -> list[str]:
    facts = []
    seen_labels = set()
    seen_lines = set()

    for source_line in _split_sanitized_lines(product.get("details", ""), paragraph=True):
        label, value = _extract_label_value(source_line)
        if not label or not value:
            continue

        normalized_line = _normalize_casefold(f"{label}: {value}")
        normalized_label = _normalize_casefold(label)
        if normalized_line in seen_lines or normalized_label in seen_labels:
            continue

        seen_lines.add(normalized_line)
        seen_labels.add(normalized_label)
        facts.append(f"{label}: {value}")

    for source_line in _split_sanitized_lines(product.get("rates_table", ""), paragraph=False):
        label, value = _extract_label_value(source_line)
        if not label or not value:
            continue
        if _fact_priority(label) > len(FACT_PRIORITY_LABELS):
            continue

        normalized_line = _normalize_casefold(f"{label}: {value}")
        normalized_label = _normalize_casefold(label)
        if normalized_line in seen_lines or normalized_label in seen_labels:
            continue

        seen_lines.add(normalized_line)
        seen_labels.add(normalized_label)
        facts.append(f"{label}: {value}")

    facts.sort(key=lambda item: (_fact_priority(item.split(":", 1)[0]), len(item)))
    return facts[:8]


def _is_rate_option_line(line: str) -> bool:
    normalized = _normalize_casefold(line)
    if not normalized:
        return False
    if normalized.endswith("պայմաններ") or normalized.endswith("տարբերակներ"):
        return False
    return any(marker in normalized for marker in RATE_MARKERS)


def _extract_rate_options(product: dict) -> list[str]:
    rate_lines = []
    seen = set()

    for source_line in _split_sanitized_lines(product.get("rates_table", ""), paragraph=False):
        line = _sanitize_line(source_line)
        if not line or not _is_rate_option_line(line):
            continue

        normalized = _normalize_casefold(line)
        if normalized in seen:
            continue

        seen.add(normalized)
        rate_lines.append(line)

    return rate_lines[:8]


def _extract_notes(product: dict, facts: list[str], rate_options: list[str]) -> list[str]:
    notes = []
    seen = {_normalize_casefold(item) for item in facts + rate_options}

    for source_line in _split_sanitized_lines(product.get("details", ""), paragraph=True):
        line = _sanitize_line(source_line)
        if not line:
            continue

        normalized = _normalize_casefold(line)
        if normalized in seen:
            continue

        label, _ = _extract_label_value(line)
        if label:
            continue
        if not any(marker in normalized for marker in NOTE_MARKERS):
            continue

        seen.add(normalized)
        notes.append(line)

    return notes[:2]


def _build_product_block(product: dict, singular_label: str) -> list[str]:
    title = _sanitize_heading(product.get("type", "Անհայտ"))
    lines = [f"  {singular_label}: {title}"]

    parent_type = _sanitize_heading(product.get("parent_type", ""))
    if parent_type:
        lines.append(f"  Տեսակ: {parent_type}")

    facts = _extract_key_facts(product)
    rate_options = _extract_rate_options(product)
    notes = _extract_notes(product, facts=facts, rate_options=rate_options)

    if facts:
        lines.append("  Հիմնական փաստեր:")
        lines.extend(f"  - {fact}" for fact in facts)

    if rate_options:
        lines.append("  Տոկոսադրույքների տարբերակներ:")
        lines.extend(f"  - {line}" for line in rate_options)

    if notes:
        lines.append("  Նշումներ:")
        lines.extend(f"  - {line}" for line in notes)

    if not facts and not rate_options and not notes:
        lines.append("  - Մանրամասներ չեն գտնվել։")

    return lines


def _append_product_section(
    lines: list[str],
    section_label: str,
    singular_label: str,
    products: list[dict],
    empty_text: str,
) -> None:
    lines.append(f"\n[{section_label}]")

    if not products:
        lines.append(f"  {empty_text}")
        return

    product_titles = []
    seen_titles = set()
    for product in products:
        title = _sanitize_heading(product.get("type", "Անհայտ"))
        normalized_title = _normalize_casefold(title)
        if not title or normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)
        product_titles.append(title)

    if product_titles:
        lines.append("  Հասանելի տարբերակներ:")
        lines.extend(f"  - {title}" for title in product_titles)

    for product in products:
        lines.append("")
        lines.extend(_build_product_block(product, singular_label))


def build_context_string(data_dir: str = "data") -> str:
    """
    Load scraped bank datasets and merge them into one plain-text string
    suitable for injection into an LLM prompt and easier runtime retrieval.
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

        _append_product_section(
            lines=lines,
            section_label="ՎԱՐԿԵՐ",
            singular_label="Վարկ",
            products=bank.get("credits", []),
            empty_text="Վարկերի տվյալներ չեն գտնվել։",
        )

        _append_product_section(
            lines=lines,
            section_label="ԱՎԱՆԴՆԵՐ",
            singular_label="Ավանդ",
            products=bank.get("deposits", []),
            empty_text="Ավանդների տվյալներ չեն գտնվել։",
        )

        lines.append("\n[ՄԱՍՆԱՃՅՈՒՂԵՐ]")
        if bank.get("branches"):
            for branch in bank["branches"]:
                name = _sanitize_line(branch.get("name", "Անհայտ"))
                address = _sanitize_line(branch.get("address", ""))
                if address:
                    lines.append(f"  - {name}: {address}")
                else:
                    lines.append(f"  - {name}")
        else:
            lines.append("  Մասնաճյուղերի տվյալներ չեն գտնվել։")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)
