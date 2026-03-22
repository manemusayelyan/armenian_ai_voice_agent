from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


SECTION_LABELS = {
    "[ՎԱՐԿԵՐ]": "վարկեր",
    "[ԱՎԱՆԴՆԵՐ]": "ավանդներ",
    "[ՄԱՍՆԱՃՅՈՒՂԵՐ]": "մասնաճյուղեր",
}

SECTION_HINTS = {
    "վարկեր": {
        "վարկ",
        "վարկեր",
        "վարկային",
        "հիփոթեք",
        "հիփոթեքային",
        "օվերդրաֆտ",
        "քարտ",
        "քարտային",
        "գիծ",
        "գծեր",
        "loan",
        "credit",
    },
    "ավանդներ": {
        "ավանդ",
        "ավանդներ",
        "ժամկետային",
        "դեպոզիտ",
        "deposit",
        "deposits",
    },
    "մասնաճյուղեր": {
        "մասնաճյուղ",
        "մասնաճյուղեր",
        "հասցե",
        "հասցեն",
        "որտեղ",
        "գտնվում",
        "գտնվելու",
        "location",
        "address",
        "branch",
        "branches",
    },
}

BANK_ALIASES = {
    "ԱԿԲԱ Բանկ": {"ակբա", "acba", "acba bank"},
    "Արմէկոնոմբանկ": {
        "արմէկոնոմբանկ",
        "արմէկոնոմ",
        "armeconombank",
        "aeb",
    },
    "Ֆասթ Բանկ": {"ֆասթ", "fast", "fast bank", "fastbank"},
}

STOPWORDS = {
    "է",
    "էլ",
    "եմ",
    "ես",
    "ու",
    "և",
    "թե",
    "որ",
    "որը",
    "մասին",
    "ինչ",
    "ինչը",
    "ինչպես",
    "կա",
    "կամ",
    "մի",
    "մենք",
    "դուք",
    "իսկ",
    "պետք",
    "կարող",
    "please",
    "tell",
    "me",
}

FIELD_HINTS = {
    "rate": {
        "տոկոս",
        "տոկոսադրույք",
        "անվանական",
        "արդյունավետ",
        "եկամտաբերություն",
        "եկամտաբեր",
        "interest",
        "rate",
        "apr",
        "bonus",
        "բոնուս",
    },
    "amount": {
        "գումար",
        "նվազագույն",
        "առավելագույն",
        "մինչև",
        "from",
        "to",
        "amount",
        "sum",
        "limit",
    },
    "term": {
        "ժամկետ",
        "տևողություն",
        "ամիս",
        "տարի",
        "term",
        "duration",
    },
    "currency": {
        "արժույթ",
        "արժույթներ",
        "դրամ",
        "դոլար",
        "եվրո",
        "ռուբլի",
        "amd",
        "usd",
        "eur",
        "rub",
        "currency",
    },
    "collateral": {
        "գրավ",
        "ապահովվածություն",
        "ապահովում",
        "կանխավճար",
        "collateral",
        "security",
        "down payment",
    },
    "repayment": {
        "մարում",
        "մարումներ",
        "վճար",
        "հաճախականություն",
        "repayment",
        "payment",
        "schedule",
    },
    "address": {
        "հասցե",
        "հասցեն",
        "որտեղ",
        "գտնվում",
        "գտնվելու",
        "location",
        "address",
        "branch",
        "branches",
        "մասնաճյուղ",
        "մասնաճյուղեր",
    },
}

PRODUCT_PREFIXES = ("Վարկ:", "Ավանդ:")
CATEGORY_PREFIX = "Տեսակ:"
KEY_FACTS_HEADER = "Հիմնական փաստեր:"
RATE_OPTIONS_HEADER = "Տոկոսադրույքների տարբերակներ:"
NOTES_HEADER = "Նշումներ:"
AVAILABLE_OPTIONS_HEADER = "Հասանելի տարբերակներ:"
BRANCH_SECTION = "մասնաճյուղեր"
ARMENIAN_TOKEN_SUFFIXES = (
    "ներում",
    "ներից",
    "ներին",
    "ներով",
    "ներինը",
    "ների",
    "ները",
    "երում",
    "երին",
    "երումը",
    "ությամբ",
    "ության",
    "ությամբ",
    "ումով",
    "ումով",
    "ում",
    "ին",
    "ից",
    "ով",
    "ը",
    "ն",
)
QUERY_SYNONYMS = {
    "ուսման": ("ուսանողական", "ուսում"),
    "ուսանողական": ("ուսման", "ուսում"),
    "ուսում": ("ուսման", "ուսանողական"),
}


@dataclass(frozen=True)
class KnowledgeChunk:
    bank: str
    section: str
    title: str
    text: str
    kind: str = "entry"
    label: str = ""
    tags: tuple[str, ...] = ()
    normalized_bank: str = field(init=False, repr=False)
    normalized_section: str = field(init=False, repr=False)
    normalized_title: str = field(init=False, repr=False)
    normalized_text: str = field(init=False, repr=False)
    normalized_label: str = field(init=False, repr=False)
    normalized_tags: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_bank", normalize_text(self.bank))
        object.__setattr__(self, "normalized_section", normalize_text(self.section))
        object.__setattr__(self, "normalized_title", normalize_text(self.title))
        object.__setattr__(self, "normalized_text", normalize_text(self.text))
        object.__setattr__(self, "normalized_label", normalize_text(self.label))
        object.__setattr__(
            self,
            "normalized_tags",
            tuple(sorted({normalize_text(tag) for tag in self.tags if tag})),
        )


def load_bank_context(path: str | Path) -> str:
    context_path = Path(path)
    if not context_path.exists():
        raise FileNotFoundError(
            f"Missing bank context file: {context_path}. "
            "Run the scraper merger first so the voice agent has knowledge to use."
        )

    return context_path.read_text(encoding="utf-8")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("եւ", "և")
    text = re.sub(r"[^\w\s%]", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split() if token]


def query_tokens(text: str) -> list[str]:
    expanded = []
    seen = set()

    for token in tokenize(text):
        stemmed = _stem_token(token)
        variants = [token, stemmed]
        variants.extend(QUERY_SYNONYMS.get(token, ()))
        variants.extend(QUERY_SYNONYMS.get(stemmed, ()))
        for variant in variants:
            if not variant or variant in seen:
                continue
            seen.add(variant)
            expanded.append(variant)

    return expanded


def detect_requested_section(query_tokens: list[str]) -> str | None:
    token_set = set(query_tokens)
    for section, hints in SECTION_HINTS.items():
        if token_set & hints:
            return section
    return None


def detect_requested_bank(query_normalized: str) -> str | None:
    for bank, aliases in BANK_ALIASES.items():
        if any(alias in query_normalized for alias in aliases):
            return bank
    return None


def detect_requested_fields(query_tokens: list[str], query_normalized: str) -> set[str]:
    token_set = set(query_tokens)
    requested_fields = set()

    for field, hints in FIELD_HINTS.items():
        normalized_hints = {normalize_text(hint) for hint in hints}
        if token_set & normalized_hints:
            requested_fields.add(field)
            continue
        if any(hint in query_normalized for hint in normalized_hints if hint):
            requested_fields.add(field)

    return requested_fields


def extract_bank_name(block: str) -> str | None:
    match = re.search(r"ԲԱՆԿ:\s*(.+)", block)
    return match.group(1).strip() if match else None


def detect_section_label(line: str) -> str | None:
    stripped = line.strip()
    if stripped in SECTION_LABELS:
        return SECTION_LABELS[stripped]
    return None


def build_knowledge_chunks(context: str) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    section_titles: dict[tuple[str, str], list[str]] = defaultdict(list)
    current_bank = ""
    current_section = ""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", context) if block.strip()]

    for block in blocks:
        maybe_bank = extract_bank_name(block)
        if maybe_bank:
            current_bank = maybe_bank
            current_section = ""
            continue

        first_line = block.splitlines()[0].strip()
        detected_section = detect_section_label(first_line)
        if detected_section:
            current_section = detected_section
            if current_section == BRANCH_SECTION:
                inline_branch_lines = [
                    line.rstrip()
                    for line in block.splitlines()[1:]
                    if line.strip()
                ]
                if inline_branch_lines:
                    chunks.extend(_build_branch_chunks(current_bank, current_section, inline_branch_lines))
            continue

        if not current_bank or not current_section:
            continue

        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        if current_section == BRANCH_SECTION:
            chunks.extend(_build_branch_chunks(current_bank, current_section, lines))
            continue

        product_title = _extract_product_title(lines)
        if not product_title:
            continue

        section_titles[(current_bank, current_section)].append(product_title)
        chunks.extend(
            _build_product_chunks(
                bank=current_bank,
                section=current_section,
                title=product_title,
                lines=lines,
            )
        )

    for (bank, section), titles in section_titles.items():
        unique_titles = _unique_preserve_order(titles)
        if not unique_titles:
            continue
        summary_lines = "\n".join(f"- {title}" for title in unique_titles)
        chunks.append(
            KnowledgeChunk(
                bank=bank,
                section=section,
                title=f"{bank} {section}",
                text=f"{AVAILABLE_OPTIONS_HEADER}\n{summary_lines}",
                kind="summary",
                tags=(section, "summary"),
            )
        )

    return chunks


def score_chunk(query: str, chunk: KnowledgeChunk) -> int:
    query_normalized = normalize_text(query)
    base_query_tokens = [token for token in tokenize(query) if token not in STOPWORDS]
    active_query_tokens = [token for token in query_tokens(query) if token not in STOPWORDS]
    if not active_query_tokens:
        return 0

    requested_section = detect_requested_section(active_query_tokens)
    requested_bank = detect_requested_bank(query_normalized)
    requested_fields = detect_requested_fields(active_query_tokens, query_normalized)
    score = 0

    for token in active_query_tokens:
        if token in chunk.normalized_title:
            score += 12
        if token in chunk.normalized_label:
            score += 12
        if token in chunk.normalized_bank:
            score += 10
        if token in chunk.normalized_section:
            score += 8

        hits = chunk.normalized_text.count(token)
        if hits:
            score += min(hits, 5) * 3

    title_tokens = {token for token in tokenize(chunk.title) if token not in STOPWORDS}
    query_token_set = set(active_query_tokens)
    title_overlap = query_token_set.intersection(title_tokens)
    if title_overlap:
        score += len(title_overlap) * 6
        score += int(18 * len(title_overlap) / max(len(title_tokens), 1))
    if chunk.normalized_title and chunk.normalized_title in query_normalized:
        score += 18

    if requested_section and chunk.section == requested_section:
        score += 18

    if requested_bank and chunk.bank == requested_bank:
        score += 24

    if requested_fields:
        overlap = requested_fields.intersection(chunk.normalized_tags)
        if overlap:
            score += 14 * len(overlap)
            if chunk.kind in {"fact", "rate", "branch", "category"}:
                score += 8

    kind_bonus = {
        "summary": 10 if requested_section and len(base_query_tokens) <= 3 and not requested_fields else 2,
        "category": 12,
        "fact": 16,
        "rate": 16,
        "branch": 18,
        "entry": 8,
    }
    score += kind_bonus.get(chunk.kind, 0)

    if requested_section == BRANCH_SECTION and chunk.kind == "branch":
        score += 18
    if "հասցե" in query_normalized and chunk.kind == "branch":
        score += 12
    if "տոկոս" in query_normalized and chunk.kind == "rate":
        score += 10

    return score


def retrieve_relevant_chunks(query: str, chunks: list[KnowledgeChunk], limit: int = 6) -> list[KnowledgeChunk]:
    query_normalized = normalize_text(query)
    base_query_tokens = [token for token in tokenize(query) if token not in STOPWORDS]
    active_query_tokens = [token for token in query_tokens(query) if token not in STOPWORDS]
    requested_section = detect_requested_section(active_query_tokens)
    requested_bank = detect_requested_bank(query_normalized)
    requested_fields = detect_requested_fields(active_query_tokens, query_normalized)
    broad_section_request = (
        requested_section is not None
        and requested_bank is None
        and not requested_fields
        and len(base_query_tokens) <= 3
    )
    broad_bank_section_request = (
        requested_section is not None
        and requested_bank is not None
        and not requested_fields
        and len(base_query_tokens) <= 4
    )

    ranked = [(score_chunk(query, chunk), chunk) for chunk in chunks]
    ranked = [(score, chunk) for score, chunk in ranked if score > 0]
    if not ranked:
        return []

    grouped_ranked: dict[tuple[str, str, str], list[tuple[int, KnowledgeChunk]]] = defaultdict(list)
    exact_title_groups: set[tuple[str, str, str]] = set()
    title_focused_groups: set[tuple[str, str, str]] = set()

    for score, chunk in ranked:
        key = _group_key(chunk)
        grouped_ranked[key].append((score, chunk))
        if chunk.normalized_title and _query_contains_title(query_normalized, chunk.normalized_title):
            exact_title_groups.add(key)
        if chunk.kind != "summary" and _title_overlap_count(chunk, active_query_tokens) >= 2:
            title_focused_groups.add(key)

    candidate_keys = list(grouped_ranked.keys())
    exact_non_summary = [
        key for key in candidate_keys
        if key in exact_title_groups and not _group_is_summary(grouped_ranked[key])
    ]
    broad_section_request = broad_section_request and not exact_non_summary and not title_focused_groups
    broad_bank_section_request = (
        broad_bank_section_request
        and not exact_non_summary
        and not title_focused_groups
    )
    if exact_non_summary and not broad_bank_section_request:
        candidate_keys = exact_non_summary
    elif title_focused_groups:
        focused_keys = [key for key in candidate_keys if key in title_focused_groups]
        if focused_keys:
            candidate_keys = focused_keys

    if requested_bank and requested_section:
        matching_bank_section = [
            key for key in candidate_keys
            if key[0] == requested_bank and key[1] == requested_section
        ]
        if matching_bank_section:
            candidate_keys = matching_bank_section
    elif requested_section == BRANCH_SECTION:
        matching_branches = [
            key for key in candidate_keys
            if key[1] == BRANCH_SECTION
        ]
        if matching_branches:
            candidate_keys = matching_branches
    elif requested_section:
        matching_section = [
            key for key in candidate_keys
            if key[1] == requested_section
        ]
        if matching_section:
            candidate_keys = matching_section

    if requested_bank:
        matching_bank = [key for key in candidate_keys if key[0] == requested_bank]
        if matching_bank:
            non_matching_bank = [key for key in candidate_keys if key[0] != requested_bank]
            candidate_keys = matching_bank + non_matching_bank

    strong_title_keys: set[tuple[str, str, str]] = set()
    if requested_bank and not broad_bank_section_request:
        max_title_overlap = max(
            (_group_title_overlap(grouped_ranked[key], active_query_tokens) for key in candidate_keys),
            default=0,
        )
        if max_title_overlap >= 2:
            strong_title_keys = {
                key
                for key in candidate_keys
                if _group_title_overlap(grouped_ranked[key], active_query_tokens) == max_title_overlap
            }
            if strong_title_keys:
                candidate_keys = [key for key in candidate_keys if key in strong_title_keys]

    ranked_groups = [
        (
            _score_group(
                query_normalized=query_normalized,
                active_query_tokens=active_query_tokens,
                requested_bank=requested_bank,
                requested_section=requested_section,
                requested_fields=requested_fields,
                ranked_group=grouped_ranked[key],
            ),
            key,
        )
        for key in candidate_keys
    ]
    ranked_groups = [(score, key) for score, key in ranked_groups if score > 0]
    ranked_groups.sort(
        key=lambda item: (
            item[0],
            _group_kind_priority(grouped_ranked[item[1]], broad_section_request or broad_bank_section_request),
        ),
        reverse=True,
    )

    results: list[KnowledgeChunk] = []
    seen_chunks: set[tuple[str, str, str, str]] = set()

    if broad_section_request or broad_bank_section_request:
        summary_target = 1 if requested_bank else min(limit, 3)
        for _, key in ranked_groups:
            ranked_group = grouped_ranked[key]
            if not _group_is_summary(ranked_group):
                continue
            if requested_section and key[1] != requested_section:
                continue
            if requested_bank and key[0] != requested_bank:
                continue
            for chunk in _select_group_chunks(
                ranked_group=ranked_group,
                active_query_tokens=active_query_tokens,
                requested_fields=requested_fields,
                exact_title_group=key in exact_title_groups or key in strong_title_keys,
            ):
                chunk_key = (chunk.bank, chunk.section, chunk.title, chunk.text)
                if chunk_key in seen_chunks:
                    continue
                results.append(chunk)
                seen_chunks.add(chunk_key)
            if len(results) >= summary_target:
                break

        if results:
            return results

    for _, key in ranked_groups:
        ranked_group = grouped_ranked[key]
        if (broad_section_request or broad_bank_section_request) and _group_is_summary(ranked_group):
            continue

        for chunk in _select_group_chunks(
            ranked_group=ranked_group,
            active_query_tokens=active_query_tokens,
            requested_fields=requested_fields,
            exact_title_group=key in exact_title_groups or key in strong_title_keys,
        ):
            chunk_key = (chunk.bank, chunk.section, chunk.title, chunk.text)
            if chunk_key in seen_chunks:
                continue
            results.append(chunk)
            seen_chunks.add(chunk_key)
            if len(results) >= limit:
                return results

    return results


def snippet_for_query(chunk: KnowledgeChunk, query: str, max_chars: int = 900) -> str:
    if chunk.kind == "summary":
        return chunk.text

    if len(chunk.text) <= max_chars:
        return chunk.text

    active_query_tokens = [token for token in query_tokens(query) if token not in STOPWORDS]
    lines = [line.rstrip() for line in chunk.text.splitlines() if line.strip()]
    if not lines:
        return chunk.text[:max_chars]

    keep_indexes = {0}
    scored_lines: list[tuple[int, int]] = []

    for index, line in enumerate(lines):
        normalized_line = normalize_text(line)
        score = 0
        for token in active_query_tokens:
            if token in normalized_line:
                score += 4 + normalized_line.count(token)
        if score > 0:
            scored_lines.append((score, index))

    for _, index in sorted(scored_lines, reverse=True)[:6]:
        for neighbor in range(max(0, index - 1), min(len(lines), index + 2)):
            keep_indexes.add(neighbor)

    selected_lines = [lines[index] for index in sorted(keep_indexes)]
    snippet = "\n".join(selected_lines).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
    return snippet + ("\n..." if snippet != chunk.text and len(snippet) < len(chunk.text) else "")


def format_retrieved_context(query: str, retrieved: list[KnowledgeChunk]) -> str:
    if not retrieved:
        return (
            "Relevant bank context for this user turn was not found.\n"
            "If the user asks for a banking fact, say in Armenian that you do not have that information."
        )

    groups: dict[tuple[str, str, str], list[KnowledgeChunk]] = defaultdict(list)
    group_order: list[tuple[str, str, str]] = []

    for chunk in retrieved:
        key = (chunk.bank, chunk.section, chunk.title)
        if key not in groups:
            group_order.append(key)
        groups[key].append(chunk)

    parts = [
        "Relevant bank context for this user turn is below.",
        "Use only these snippets for factual answers.",
        "If these snippets are insufficient, say in Armenian that you do not have that information.",
        "",
        f"Retrieval query: {query}",
        "",
    ]

    kind_order = {"summary": 0, "category": 1, "fact": 2, "rate": 3, "branch": 4, "entry": 5}

    for index, key in enumerate(group_order, start=1):
        bank, section, title = key
        parts.append(f"[{index}] Bank: {bank} | Section: {section} | Title: {title}")

        seen_lines = set()
        sorted_group = sorted(groups[key], key=lambda item: kind_order.get(item.kind, 99))
        has_specific_chunks = any(
            chunk.kind in {"category", "fact", "rate", "branch"}
            for chunk in sorted_group
        )

        for chunk in sorted_group:
            if has_specific_chunks and chunk.kind == "entry":
                continue
            for raw_line in snippet_for_query(chunk, query).splitlines():
                line = raw_line.strip()
                if not line or line in seen_lines:
                    continue
                seen_lines.add(line)
                parts.append(line)
        parts.append("")

    return "\n".join(parts).strip()


def _group_key(chunk: KnowledgeChunk) -> tuple[str, str, str]:
    return (chunk.bank, chunk.section, chunk.title)


def _group_is_summary(ranked_group: list[tuple[int, KnowledgeChunk]]) -> bool:
    return bool(ranked_group) and all(chunk.kind == "summary" for _, chunk in ranked_group)


def _group_kind_priority(
    ranked_group: list[tuple[int, KnowledgeChunk]],
    summary_friendly: bool,
) -> int:
    chunks = [chunk for _, chunk in ranked_group]
    if _group_is_summary(ranked_group):
        return 40 if summary_friendly else 8
    if any(chunk.kind == "branch" for chunk in chunks):
        return 38
    if any(chunk.kind == "fact" for chunk in chunks):
        return 34
    if any(chunk.kind == "rate" for chunk in chunks):
        return 32
    if any(chunk.kind == "category" for chunk in chunks):
        return 26
    if any(chunk.kind == "entry" for chunk in chunks):
        return 14
    return 0


def _score_group(
    query_normalized: str,
    active_query_tokens: list[str],
    requested_bank: str | None,
    requested_section: str | None,
    requested_fields: set[str],
    ranked_group: list[tuple[int, KnowledgeChunk]],
) -> int:
    if not ranked_group:
        return 0

    scores = [score for score, _ in ranked_group]
    chunks = [chunk for _, chunk in ranked_group]
    score = max(scores)
    score += min(len(scores), 5) * 3

    title_overlap = max(
        (_title_overlap_count(chunk, active_query_tokens) for chunk in chunks),
        default=0,
    )
    if title_overlap:
        score += title_overlap * 10

    if any(
        chunk.normalized_title and _query_contains_title(query_normalized, chunk.normalized_title)
        for chunk in chunks
    ):
        score += 40

    if any(chunk.kind in {"category", "fact", "rate", "branch"} for chunk in chunks):
        score += 10

    if requested_bank and any(chunk.bank == requested_bank for chunk in chunks):
        score += 12
    if requested_section and any(chunk.section == requested_section for chunk in chunks):
        score += 10
    if requested_fields and any(requested_fields.intersection(chunk.normalized_tags) for chunk in chunks):
        score += 16

    if _group_is_summary(ranked_group):
        if requested_fields:
            score -= 24
        elif not requested_section:
            score -= 8

    return score


def _group_title_overlap(
    ranked_group: list[tuple[int, KnowledgeChunk]],
    active_query_tokens: list[str],
) -> int:
    return max(
        (_title_overlap_count(chunk, active_query_tokens) for _, chunk in ranked_group),
        default=0,
    )


def _select_group_chunks(
    ranked_group: list[tuple[int, KnowledgeChunk]],
    active_query_tokens: list[str],
    requested_fields: set[str],
    exact_title_group: bool,
) -> list[KnowledgeChunk]:
    if not ranked_group:
        return []

    ordered_group = sorted(ranked_group, key=lambda item: item[0], reverse=True)
    chunks = [chunk for _, chunk in ordered_group]
    section = chunks[0].section

    if _group_is_summary(ranked_group):
        return [ordered_group[0][1]]

    if normalize_text(section) == normalize_text(BRANCH_SECTION):
        return [ordered_group[0][1]]

    category_chunks = [chunk for _, chunk in ordered_group if chunk.kind == "category"]
    specific_items = [
        (score, chunk)
        for score, chunk in ordered_group
        if chunk.kind in {"fact", "rate", "branch"}
    ]
    if not specific_items:
        entry_chunk = next((chunk for _, chunk in ordered_group if chunk.kind == "entry"), None)
        return [entry_chunk] if entry_chunk else [ordered_group[0][1]]

    selected: list[KnowledgeChunk] = []
    seen_texts: set[str] = set()
    seen_labels: set[str] = set()
    group_limit = _group_selection_limit(section, requested_fields, exact_title_group)

    def add_chunk(chunk: KnowledgeChunk) -> bool:
        text_key = chunk.normalized_text
        label_key = chunk.normalized_label
        if text_key in seen_texts:
            return False
        if label_key and label_key in seen_labels:
            return False
        selected.append(chunk)
        seen_texts.add(text_key)
        if label_key:
            seen_labels.add(label_key)
        return True

    if category_chunks:
        add_chunk(category_chunks[0])
        if len(selected) >= group_limit:
            return selected[:group_limit]

    ordered_specific = [
        chunk
        for _, chunk in sorted(
            specific_items,
            key=lambda item: _rank_group_chunk(
                chunk=item[1],
                base_score=item[0],
                active_query_tokens=active_query_tokens,
                requested_fields=requested_fields,
            ),
            reverse=True,
        )
    ]

    preferred_fields = _preferred_fields_for_section(section)
    if requested_fields:
        preferred_fields = tuple(
            field for field in preferred_fields if field in requested_fields
        ) or preferred_fields

    for field in preferred_fields:
        candidate = _best_field_chunk(
            ordered_specific=ordered_specific,
            field=field,
            seen_texts=seen_texts,
            seen_labels=seen_labels,
        )
        if candidate and add_chunk(candidate) and len(selected) >= group_limit:
            return selected[:group_limit]

    for chunk in ordered_specific:
        if add_chunk(chunk) and len(selected) >= group_limit:
            break

    if not selected:
        entry_chunk = next((chunk for _, chunk in ordered_group if chunk.kind == "entry"), None)
        if entry_chunk:
            selected.append(entry_chunk)

    return selected[:group_limit]


def _group_selection_limit(
    section: str,
    requested_fields: set[str],
    exact_title_group: bool,
) -> int:
    normalized_section = normalize_text(section)
    if normalized_section == normalize_text(BRANCH_SECTION):
        return 1
    if requested_fields:
        return 4
    if exact_title_group:
        return 5
    if "վարկ" in normalized_section or "loan" in normalized_section or "credit" in normalized_section:
        return 4
    if "ավանդ" in normalized_section or "deposit" in normalized_section:
        return 4
    return 3


def _preferred_fields_for_section(section: str) -> tuple[str, ...]:
    normalized_section = normalize_text(section)
    if normalized_section == normalize_text(BRANCH_SECTION):
        return ("address",)
    if "ավանդ" in normalized_section or "deposit" in normalized_section:
        return ("rate", "term", "amount", "currency")
    if "վարկ" in normalized_section or "loan" in normalized_section or "credit" in normalized_section:
        return ("rate", "amount", "term", "collateral", "currency", "repayment")
    return ("rate", "amount", "term", "currency", "address", "collateral", "repayment")


def _best_field_chunk(
    ordered_specific: list[KnowledgeChunk],
    field: str,
    seen_texts: set[str],
    seen_labels: set[str],
) -> KnowledgeChunk | None:
    candidates = [
        chunk
        for chunk in ordered_specific
        if field in chunk.normalized_tags
        and chunk.normalized_text not in seen_texts
        and (not chunk.normalized_label or chunk.normalized_label not in seen_labels)
    ]
    if not candidates:
        return None

    compact_candidates = [chunk for chunk in candidates if _is_compact_chunk(chunk)]
    if compact_candidates:
        candidates = compact_candidates

    return max(candidates, key=lambda chunk: _field_candidate_score(chunk, field))


def _rank_group_chunk(
    chunk: KnowledgeChunk,
    base_score: int,
    active_query_tokens: list[str],
    requested_fields: set[str],
) -> int:
    score = base_score
    kind_bonus = {
        "branch": 160,
        "fact": 130,
        "rate": 124,
        "category": 110,
        "entry": 20,
    }
    score += kind_bonus.get(chunk.kind, 0)

    if requested_fields:
        overlap = requested_fields.intersection(chunk.normalized_tags)
        score += 90 * len(overlap)
        if not overlap and chunk.kind in {"fact", "rate"}:
            score -= 18
    else:
        preferred_fields = _preferred_fields_for_section(chunk.section)
        primary_field = _primary_field_for_chunk(chunk, preferred_fields)
        if primary_field:
            score += max(0, 52 - preferred_fields.index(primary_field) * 8)

    for token in active_query_tokens:
        if token in chunk.normalized_label:
            score += 16
        if token in chunk.normalized_text:
            score += 4

    if _is_compact_chunk(chunk):
        score += 18
    else:
        score -= 18

    if not chunk.normalized_label and chunk.kind in {"fact", "rate"}:
        score -= 8
    if len(chunk.text) > 260:
        score -= 20
    if chunk.text.count("|") >= 3:
        score -= min(chunk.text.count("|"), 5) * 4

    return score


def _primary_field_for_chunk(
    chunk: KnowledgeChunk,
    preferred_fields: tuple[str, ...],
) -> str | None:
    for field in preferred_fields:
        if field in chunk.normalized_tags:
            return field
    return None


def _is_compact_chunk(chunk: KnowledgeChunk) -> bool:
    if chunk.kind in {"summary", "branch", "category"}:
        return True
    if len(chunk.text) > 220:
        return False
    if chunk.text.count("|") > 2:
        return False
    if chunk.label and len(chunk.label) > 70:
        return False
    return True


def _field_candidate_score(chunk: KnowledgeChunk, field: str) -> int:
    normalized_label = chunk.normalized_label
    normalized_text = chunk.normalized_text
    normalized_section = chunk.normalized_section
    field_hints = {normalize_text(hint) for hint in FIELD_HINTS.get(field, ())}
    repayment_hints = {normalize_text(hint) for hint in FIELD_HINTS.get("repayment", ())}
    section_tag = normalized_section
    extra_tags = [
        tag for tag in chunk.normalized_tags
        if tag not in {section_tag, field}
    ]

    score = 0
    if any(hint and normalized_label.startswith(hint) for hint in field_hints):
        score += 80
    if any(hint and hint in normalized_label for hint in field_hints):
        score += 50
    if any(hint and hint in normalized_text for hint in field_hints):
        score += 20

    if _is_compact_chunk(chunk):
        score += 18

    score -= len(extra_tags) * 6
    if field != "repayment" and any(hint and hint in normalized_label for hint in repayment_hints):
        score -= 24
    if field != "repayment" and "repayment" in extra_tags:
        score -= 16
    if not normalized_label:
        score -= 10
    if len(chunk.text) > 180:
        score -= 16

    if field == "amount":
        score += _amount_field_preference_score(
            normalized_section=normalized_section,
            normalized_label=normalized_label,
            normalized_text=normalized_text,
        )

    return score


def _amount_field_preference_score(
    normalized_section: str,
    normalized_label: str,
    normalized_text: str,
) -> int:
    loan_section = (
        "վարկ" in normalized_section
        or "loan" in normalized_section
        or "credit" in normalized_section
    )
    deposit_section = "ավանդ" in normalized_section or "deposit" in normalized_section

    score = 0
    if loan_section:
        if "առավելագույն" in normalized_label or "մաքսիմալ" in normalized_label:
            score += 64
        if "մինչև" in normalized_text:
            score += 36
        if "վարկի գումար" in normalized_label or "վարկի գումար" in normalized_text:
            score += 34
        if "տրամադրման գումար" in normalized_label:
            score += 12
        if "նվազագույն" in normalized_label:
            score -= 36
    elif deposit_section:
        if "նվազագույն" in normalized_label:
            score += 52
        if "առավելագույն" in normalized_label or "մաքսիմալ" in normalized_label:
            score -= 24
    else:
        if "առավելագույն" in normalized_label or "մաքսիմալ" in normalized_label:
            score += 20
        if "նվազագույն" in normalized_label:
            score += 8

    return score


def _build_branch_chunks(bank: str, section: str, lines: list[str]) -> list[KnowledgeChunk]:
    chunks = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        branch_text = line[1:].strip()
        branch_name = branch_text.split(":", 1)[0].strip() if ":" in branch_text else branch_text
        chunks.append(
            KnowledgeChunk(
                bank=bank,
                section=section,
                title=branch_name,
                text=branch_text,
                kind="branch",
                label="հասցե",
                tags=("address", "branch"),
            )
        )

    return chunks


def _build_product_chunks(bank: str, section: str, title: str, lines: list[str]) -> list[KnowledgeChunk]:
    chunks = [
        KnowledgeChunk(
            bank=bank,
            section=section,
            title=title,
            text="\n".join(lines),
            kind="entry",
            tags=_infer_tags(text="\n".join(lines), section=section, label=""),
        )
    ]

    current_header = ""

    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(CATEGORY_PREFIX):
            text = line
            label = CATEGORY_PREFIX.rstrip(":")
            chunks.append(
                KnowledgeChunk(
                    bank=bank,
                    section=section,
                    title=title,
                    text=text,
                    kind="category",
                    label=label,
                    tags=_infer_tags(text=text, section=section, label=label),
                )
            )
            continue

        if line.endswith(":") and not line.startswith("-"):
            current_header = line
            continue

        if not line.startswith("-"):
            continue

        item_text = line[2:].strip()
        if not item_text:
            continue

        kind = "fact"
        if current_header == RATE_OPTIONS_HEADER:
            kind = "rate"
        elif current_header == NOTES_HEADER:
            kind = "entry"

        label = item_text.split(":", 1)[0].strip() if ":" in item_text else ""
        chunks.append(
            KnowledgeChunk(
                bank=bank,
                section=section,
                title=title,
                text=item_text,
                kind=kind,
                label=label,
                tags=_infer_tags(text=item_text, section=section, label=label),
            )
        )

    return chunks


def _extract_product_title(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        for prefix in PRODUCT_PREFIXES:
            if stripped.startswith(prefix):
                return stripped.split(":", 1)[1].strip()
    return ""


def _infer_tags(text: str, section: str, label: str) -> tuple[str, ...]:
    normalized_text = normalize_text(text)
    normalized_label = normalize_text(label)
    tags = {normalize_text(section)}

    for field, hints in FIELD_HINTS.items():
        normalized_hints = {normalize_text(hint) for hint in hints}
        if any(hint and (hint in normalized_text or hint in normalized_label) for hint in normalized_hints):
            tags.add(field)

    if normalize_text(section) == BRANCH_SECTION:
        tags.update({"address", "branch"})

    return tuple(sorted(tags))


def _unique_preserve_order(values: list[str]) -> list[str]:
    unique_values = []
    seen = set()

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)

    return unique_values


def _stem_token(token: str) -> str:
    for suffix in ARMENIAN_TOKEN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _title_overlap_count(chunk: KnowledgeChunk, active_query_tokens: list[str]) -> int:
    title_tokens = {
        token
        for token in query_tokens(chunk.title)
        if token not in STOPWORDS
    }
    return len(set(active_query_tokens).intersection(title_tokens))


def _query_contains_title(query_normalized: str, title_normalized: str) -> bool:
    return f" {title_normalized} " in f" {query_normalized} "
