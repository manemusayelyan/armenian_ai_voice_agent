import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from .base_scraper import BaseBankScraper


class FastbankScraper(BaseBankScraper):
    bank_name = "Fast Bank"
    base_url = "https://www.fastbank.am"
    file_stem = "fast_bank"
    COMPACT_LOAN_FACT_LIMIT = 5
    COMPACT_LOAN_DETAIL_WINDOW = 16
    COMPACT_LOAN_LABEL_MARKERS = (
        "տոկոս",
        "գումար",
        "ժամկետ",
        "կանխավճար",
        "տույժ",
        "տրամադրում",
        "մարման",
        "արժույթ",
        "նպատակ",
        "ապահով",
        "գրավի",
        "գրավով",
        "վճար",
        "interest",
        "amount",
        "term",
        "down payment",
        "penalty",
        "currency",
        "purpose",
        "repayment",
        "collateral",
    )
    COMPACT_LOAN_VALUE_MARKERS = (
        "amd",
        "usd",
        "eur",
        "rub",
        "%",
        "դրամ",
        "ամիս",
        "օր",
        "տարի",
        "չի կիրառվում",
        "չի պահանջվում",
        "առկա չէ",
        "անվճար",
        "րոպե",
    )
    COMPACT_LOAN_NOISE_MARKERS = (
        "տեսնել ավելին",
        "see more",
        "apply online",
        "loan calculator",
        "պայմաններ",
        "terms",
        "documents",
        "փաստաթղթեր",
    )
    COMPACT_DEPOSIT_FACT_LIMIT = 4
    COMPACT_DEPOSIT_DETAIL_WINDOW = 12
    COMPACT_DEPOSIT_LABEL_MARKERS = (
        "եկամտաբեր",
        "ժամկետ",
        "գումար",
        "արժույթ",
        "term",
        "amount",
        "currency",
        "yield",
        "interest",
    )
    COMPACT_DEPOSIT_VALUE_MARKERS = (
        "amd",
        "usd",
        "eur",
        "rub",
        "%",
        "դրամ",
        "օր",
        "ամիս",
        "տարի",
    )
    COMPACT_DEPOSIT_NOISE_MARKERS = (
        "տեսնել ավելին",
        "see more",
        "monthly",
        "ամսական",
        "մտածի",
        "ձևակերպ",
        "խնայող",
    )
    DETAIL_PHRASES_TO_REMOVE = (
        "Քո նոր բնակարանը սպասում է քեզ",
        "Ձեռք բեր, կառուցիր և վերանորոգիր քո բնակարանը Ֆասթ Բանկի հետ",
        "Ձեռք բեր քո բնակարանը Ֆասթ Բանկի հետ",
        "Ստացիր արագ ֆինանսավորում՝ առանց գրավի",
        "Տեսնել ավելին",
    )
    TERMS_START_MARKERS = (
        "Պայմաններ",
        "Terms",
    )
    TERMS_SKIP_LINES = {
        "սակագներ",
        "tariffs",
        "Image: Պայմաններ",
        "Image: Terms",
    }
    TERMS_END_MARKERS = (
        "Վարկային հաշվիչ",
        "Loan calculator",
        "Փաստաթղթեր",
        "Documents",
        "See more",
        "Դիմիր օնլայն",
        "Apply online",
    )
    TERMS_LABEL_MARKERS = (
        "վարկի",
        "տոկոսադրույք",
        "արդյունավետ",
        "ապահով",
        "տույժ",
        "վճար",
        "նպատակ",
        "արժույթ",
        "գումար",
        "ժամկետ",
        "մարման",
        "գրավ",
        "ապահովագր",
        "վարկառու",
        "համավարկառու",
        "երաշխավոր",
        "ռեզիդենտ",
        "նվազագույն",
        "առավելագույն",
        "կանխավճար",
        "հանձնաժողով",
        "սուբսիդ",
        "գնահատ",
        "հաճախորդ",
        "loan",
        "interest",
        "effective",
        "security",
        "penalty",
        "commission",
        "purpose",
        "currency",
        "amount",
        "term",
        "repayment",
        "collateral",
        "insurance",
        "borrower",
        "guarantor",
        "residency",
        "down payment",
        "grace period",
    )

    LOANS_URL = "/hy/individual/loans"
    LOAN_CATEGORY_HINTS = [
        {
            "label": "Հիփոթեքային վարկ",
            "markers": ("Հիփոթեքային", "mortgage"),
        },
        {
            "label": "Գրավով վարկ",
            "markers": ("Գրավով", "collateral"),
        },
        {
            "label": "Անգրավ վարկ",
            "markers": ("Անգրավ", "non-collateral", "unsecured"),
        },
    ]

    DEPOSIT_URLS = [
        "/hy/individual/deposits",
    ]

    BRANCHES_URL = "/hy/branches"
    MAP_CONTROL_TEXT = {
        "→",
        "↑",
        "↓",
        "+",
        "-",
        "Home",
        "End",
        "Page Up",
        "Page Down",
        "Move right",
        "Move up",
        "Move down",
        "Zoom in",
        "Zoom out",
        "Jump left by 75%",
        "Jump right by 75%",
        "Jump up by 75%",
        "Jump down by 75%",
    }
    GENERIC_BRANCH_TEXT = {
        "Հասցե",
        "Մասնաճյուղեր և բանկոմատներ",
        "Մասնաճյուղեր",
        "Բանկոմատներ",
        "Բանկ",
        "Fspace",
    }
    FOOTER_START_MARKERS = (
        "Թարմացվել է",
        "Օգտակար հղումներ",
        "Հետադարձ կապ",
        "Միացե՛ք մեզ սոցիալական ցանցերում",
        "Բոլոր իրավունքները պաշտպանված են",
    )

    def _extract_product(self, path_or_url: str, soup=None) -> dict:
        url = self.resolve_url(path_or_url)
        if soup is None:
            soup = self.get_page(url, wait_seconds=3)
        if not soup:
            return {}

        name = self.extract_page_title(soup, fallback_url=url)
        detail_parts = self._clean_detail_parts(name, self.extract_content(soup))
        details = " | ".join(detail_parts)
        rates_table = self._extract_terms_table(soup, product_name=name)
        if not rates_table:
            tables = self.extract_tables(soup)
            rates_table = self.combine_tables(tables)
        if not rates_table:
            rates_table = self._build_fallback_rates_table(detail_parts)

        return {
            "type": name,
            "source_url": url,
            "details": details,
            "rates_table": rates_table,
        }

    def _extract_loan_product(self, path_or_url: str, soup=None) -> dict:
        url = self.resolve_url(path_or_url)
        if soup is None:
            soup = self.get_page(url, wait_seconds=3)
        if not soup:
            return {}

        name = self.extract_page_title(soup, fallback_url=url)
        details = self._build_compact_loan_details(
            product_name=name,
            raw_details=self.extract_content(soup),
            soup=soup,
        )

        return {
            "type": name,
            "source_url": url,
            "details": details,
            "rates_table": "",
        }

    def scrape_credits(self) -> list[dict]:
        loans_url = self.resolve_url(self.LOANS_URL)
        soup = self.get_page(loans_url, wait_seconds=4)
        if not soup:
            return []

        category_pages = self._discover_loan_category_pages(soup, loans_url)
        results = []
        seen_urls = set()

        for _, category_url in category_pages:
            category_soup = self.get_page(category_url, wait_seconds=4)
            if not category_soup:
                continue

            category_title = self.extract_page_title(category_soup, fallback_url=category_url)
            child_urls = self.discover_child_page_urls(
                soup=category_soup,
                page_url=category_url,
            )

            # If a category page has no child cards, treat the category page itself as the product.
            if not child_urls:
                product = self._extract_loan_product(category_url, soup=category_soup)
                if product:
                    source_url = product.get("source_url", category_url)
                    if source_url not in seen_urls:
                        seen_urls.add(source_url)
                        results.append(product)
                continue

            for child_url in child_urls:
                if child_url in seen_urls:
                    continue
                product = self._extract_loan_product(child_url)
                if not product:
                    continue

                product["parent_type"] = category_title
                source_url = product.get("source_url", child_url)
                if source_url in seen_urls:
                    continue

                seen_urls.add(source_url)
                results.append(product)

        return results

    def _build_compact_loan_details(
        self,
        product_name: str,
        raw_details: str,
        soup: BeautifulSoup,
    ) -> str:
        detail_parts = self._split_loan_detail_parts(product_name, raw_details)
        lines = []
        fact_count = 0

        summary = self._extract_loan_summary(detail_parts)
        if summary:
            lines.append(f"Նկարագրություն: {summary}")

        seen_labels = set()
        for label, value in self._extract_loan_fact_pairs(detail_parts):
            label_key = label.casefold()
            if label_key in seen_labels:
                continue

            seen_labels.add(label_key)
            lines.append(f"{label}: {value}")
            fact_count += 1
            if fact_count >= self.COMPACT_LOAN_FACT_LIMIT:
                break

        if fact_count < self.COMPACT_LOAN_FACT_LIMIT:
            for label, value in self._extract_loan_fact_pairs_from_terms(
                soup,
                product_name=product_name,
            ):
                label_key = label.casefold()
                if label_key in seen_labels:
                    continue

                seen_labels.add(label_key)
                lines.append(f"{label}: {value}")
                fact_count += 1
                if fact_count >= self.COMPACT_LOAN_FACT_LIMIT:
                    break

        if not lines and detail_parts:
            lines.append(f"Նկարագրություն: {detail_parts[0]}")

        return "\n".join(lines)

    def _split_loan_detail_parts(self, product_name: str, details: str) -> list[str]:
        parts = []
        seen = set()
        product_name_key = product_name.casefold()

        for raw_part in details.split("|"):
            part = " ".join(raw_part.split()).strip()
            if not part:
                continue
            if part.casefold() == product_name_key:
                continue
            if self._is_loan_noise_part(part):
                continue

            key = part.casefold()
            if key in seen:
                continue

            seen.add(key)
            parts.append(part)

        return parts

    def _is_loan_noise_part(self, text: str) -> bool:
        normalized = text.casefold()
        if not normalized:
            return True
        if normalized.startswith("image:"):
            return True
        return any(marker in normalized for marker in self.COMPACT_LOAN_NOISE_MARKERS)

    def _extract_loan_summary(self, detail_parts: list[str]) -> str:
        for part in detail_parts:
            if self._looks_like_compact_loan_label(part, ""):
                break
            if self._looks_like_compact_loan_value(part):
                continue
            if len(part) < 15 or len(part) > 120:
                continue
            if len(part.split()) < 3:
                continue
            return part

        return ""

    def _extract_loan_fact_pairs(self, detail_parts: list[str]) -> list[tuple[str, str]]:
        pairs = []
        index = 0
        compact_parts = detail_parts[:self.COMPACT_LOAN_DETAIL_WINDOW]

        while index + 1 < len(compact_parts):
            label = compact_parts[index].strip(" *!•-:").strip()
            value = compact_parts[index + 1].strip()

            if self._looks_like_compact_loan_label(label, value):
                pairs.append((label, value))
                index += 2
                continue

            index += 1

        return pairs

    def _extract_loan_fact_pairs_from_terms(
        self,
        soup: BeautifulSoup,
        product_name: str,
    ) -> list[tuple[str, str]]:
        lines = self._extract_terms_lines(soup, product_name=product_name)
        if not lines:
            return []

        pairs = []
        seen = set()
        current_label = ""
        current_values = []

        for line in lines:
            if self._is_terms_label(line):
                if current_label and current_values:
                    label = current_label.strip(" *!•-:").strip()
                    value = " ".join(current_values).strip()
                    if self._looks_like_compact_loan_label(label, value):
                        label_key = label.casefold()
                        if label_key not in seen:
                            seen.add(label_key)
                            pairs.append((label, value))

                current_label = line
                current_values = []
                continue

            if current_label:
                current_values.append(line)

        if current_label and current_values:
            label = current_label.strip(" *!•-:").strip()
            value = " ".join(current_values).strip()
            if self._looks_like_compact_loan_label(label, value):
                label_key = label.casefold()
                if label_key not in seen:
                    pairs.append((label, value))

        return pairs

    def _looks_like_compact_loan_label(self, label: str, value: str) -> bool:
        cleaned_label = label.strip(" *!•-:").strip()
        normalized_label = cleaned_label.casefold()
        if not cleaned_label or len(cleaned_label) > 80:
            return False
        if any(char.isdigit() for char in cleaned_label):
            return False
        if not any(marker in normalized_label for marker in self.COMPACT_LOAN_LABEL_MARKERS):
            return False
        if value and not self._looks_like_compact_loan_value(value):
            return False
        return True

    def _looks_like_compact_loan_value(self, value: str) -> bool:
        normalized = value.casefold()
        if not value or len(value) > 160:
            return False
        if self._has_financial_signal(value):
            return True
        return any(marker in normalized for marker in self.COMPACT_LOAN_VALUE_MARKERS)

    def _extract_deposit_product(self, path_or_url: str, soup=None) -> dict:
        url = self.resolve_url(path_or_url)
        if soup is None:
            soup = self.get_page(url, wait_seconds=3)
        if not soup:
            return {}

        name = self.extract_page_title(soup, fallback_url=url)
        details = self._build_compact_deposit_details(
            product_name=name,
            raw_details=self.extract_content(soup),
        )

        return {
            "type": name,
            "source_url": url,
            "details": details,
            "rates_table": "",
        }

    def scrape_deposits(self) -> list[dict]:
        return self.scrape_product_pages(
            paths=self.DEPOSIT_URLS,
            extract_product=self._extract_deposit_product,
            link_keywords=("deposit", "deposits", "saving", "term"),
        )

    def _build_compact_deposit_details(
        self,
        product_name: str,
        raw_details: str,
    ) -> str:
        detail_parts = self._split_deposit_detail_parts(product_name, raw_details)
        lines = []
        seen_labels = set()

        for label, value in self._extract_deposit_fact_pairs(detail_parts):
            label_key = label.casefold()
            if label_key in seen_labels:
                continue

            seen_labels.add(label_key)
            lines.append(f"{label}: {value}")
            if len(lines) >= self.COMPACT_DEPOSIT_FACT_LIMIT:
                break

        return "\n".join(lines)

    def _split_deposit_detail_parts(self, product_name: str, details: str) -> list[str]:
        parts = []
        seen = set()
        product_name_key = product_name.casefold()

        for raw_part in details.split("|"):
            part = " ".join(raw_part.split()).strip()
            if not part:
                continue
            if part.casefold() == product_name_key:
                continue
            if self._is_deposit_noise_part(part):
                continue

            key = part.casefold()
            if key in seen:
                continue

            seen.add(key)
            parts.append(part)

        return parts

    def _is_deposit_noise_part(self, text: str) -> bool:
        normalized = text.casefold()
        if not normalized:
            return True
        if normalized.startswith("image:"):
            return True
        return any(marker in normalized for marker in self.COMPACT_DEPOSIT_NOISE_MARKERS)

    def _extract_deposit_fact_pairs(self, detail_parts: list[str]) -> list[tuple[str, str]]:
        pairs = []
        index = 0
        compact_parts = detail_parts[:self.COMPACT_DEPOSIT_DETAIL_WINDOW]

        while index + 1 < len(compact_parts):
            first = compact_parts[index].strip(" *!•-:").strip()
            second = compact_parts[index + 1].strip(" *!•-:").strip()

            if (
                self._looks_like_compact_deposit_value(first)
                and self._looks_like_compact_deposit_label(second)
            ):
                pairs.append((second, first))
                index += 2
                continue

            if (
                self._looks_like_compact_deposit_label(first)
                and self._looks_like_compact_deposit_value(second)
            ):
                pairs.append((first, second))
                index += 2
                continue

            index += 1

        return pairs

    def _looks_like_compact_deposit_label(self, label: str) -> bool:
        cleaned_label = label.strip(" *!•-:").strip()
        normalized_label = cleaned_label.casefold()
        if not cleaned_label or len(cleaned_label) > 80:
            return False
        if any(char.isdigit() for char in cleaned_label):
            return False
        return any(marker in normalized_label for marker in self.COMPACT_DEPOSIT_LABEL_MARKERS)

    def _looks_like_compact_deposit_value(self, value: str) -> bool:
        normalized = value.casefold()
        if not value or len(value) > 120:
            return False
        if self._has_financial_signal(value):
            return True
        return any(marker in normalized for marker in self.COMPACT_DEPOSIT_VALUE_MARKERS)

    def _discover_loan_category_pages(self, soup, page_url: str) -> list[tuple[str, str]]:
        page_parts = urlparse(page_url)
        found = []
        seen_urls = set()
        selectors = "a[href], [data-href], [data-url], [data-link], [onclick]"

        for category in self.LOAN_CATEGORY_HINTS:
            for element in soup.select(selectors):
                text = element.get_text(" ", strip=True)
                raw_target = self.extract_click_target(element)
                if not raw_target:
                    continue

                candidate_url = urljoin(page_url, raw_target)
                candidate_parts = urlparse(candidate_url)
                if candidate_parts.netloc and candidate_parts.netloc != page_parts.netloc:
                    continue

                haystack = f"{text} {candidate_url}".lower()
                if not any(marker.lower() in haystack for marker in category["markers"]):
                    continue
                if candidate_url in seen_urls:
                    continue

                seen_urls.add(candidate_url)
                found.append((category["label"], candidate_url))
                break

        return found

    def _clean_detail_parts(self, product_name: str, details: str) -> list[str]:
        parts = [part.strip() for part in details.split("|")]
        cleaned_parts = []
        seen = set()
        phrases_to_remove = set(self.DETAIL_PHRASES_TO_REMOVE) | {product_name}

        for part in parts:
            if not part or part in phrases_to_remove:
                continue
            if part in seen:
                continue
            seen.add(part)
            cleaned_parts.append(part)

        return cleaned_parts

    def _build_fallback_rates_table(self, detail_parts: list[str]) -> str:
        if len(detail_parts) < 2:
            return ""

        rows = []
        index = 0
        while index < len(detail_parts):
            left = detail_parts[index]
            right = detail_parts[index + 1] if index + 1 < len(detail_parts) else ""
            if right:
                rows.append(f"{left} | {right}")
            else:
                rows.append(left)
            index += 2

        return "\n".join(rows)

    def _extract_terms_table(self, soup: BeautifulSoup, product_name: str) -> str:
        lines = self._extract_terms_lines(soup, product_name=product_name)
        if not lines:
            return ""

        rows = []
        current_label = None
        current_values = []

        for line in lines:
            if self._is_terms_label(line):
                if current_label and current_values:
                    rows.append(f"{current_label} | {' '.join(current_values)}")
                current_label = line
                current_values = []
            elif current_label:
                current_values.append(line)

        if current_label and current_values:
            rows.append(f"{current_label} | {' '.join(current_values)}")

        unique_rows = []
        seen = set()
        for row in rows:
            normalized = row.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_rows.append(normalized)

        return "\n".join(unique_rows)

    def _extract_terms_lines(self, soup: BeautifulSoup, product_name: str) -> list[str]:
        raw_lines = soup.get_text("\n", strip=True).splitlines()
        lines = []
        started = False

        for raw_line in raw_lines:
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue

            if not started:
                if any(marker.lower() == line.lower() for marker in self.TERMS_START_MARKERS):
                    started = True
                continue

            if any(marker.lower() in line.lower() for marker in self.TERMS_END_MARKERS):
                break

            if line in self.TERMS_SKIP_LINES:
                continue
            if line.startswith("Image:"):
                continue
            if line == product_name:
                continue
            if line in self.DETAIL_PHRASES_TO_REMOVE:
                continue

            lines.append(line)

        return lines

    def _is_terms_label(self, line: str) -> bool:
        cleaned = line.strip(" *!•-").strip()
        normalized = cleaned.lower()
        if not normalized:
            return False

        if any(marker in normalized for marker in self.TERMS_LABEL_MARKERS):
            return True

        if len(cleaned) > 90:
            return False
        if any(char.isdigit() for char in cleaned):
            return False

        words = cleaned.split()
        return 1 <= len(words) <= 8 and cleaned.endswith(("ը", "ը/", "ութուն", "ություն"))

    def scrape_branches(self) -> list[dict]:
        url = self.resolve_url(self.BRANCHES_URL)
        soup = self.get_page(url, wait_seconds=4)
        if not soup or not self.driver:
            return []

        self._activate_branches_view()
        self._expand_branch_dropdowns()

        expanded_soup = BeautifulSoup(self.driver.page_source, "html.parser")
        card_branches = self._extract_branch_cards(expanded_soup)
        text_branches = self._extract_branch_records_from_page(expanded_soup)
        branches = text_branches if len(text_branches) >= len(card_branches) else card_branches
        if branches:
            return branches

        # Table fallback
        for row in expanded_soup.select("table tr")[1:]:
            cells = [td.get_text(strip=True) for td in row.select("td")]
            if cells and cells[0] and not self._is_map_control(cells[0]):
                branches.append({
                    "name": cells[0],
                    "address": cells[1] if len(cells) > 1 else "",
                    "phone": cells[2] if len(cells) > 2 else "",
                    "hours": cells[3] if len(cells) > 3 else "",
                })

        return branches

    def _activate_branches_view(self) -> None:
        selectors = [
            "//*[self::button or self::a or self::div][contains(normalize-space(.), 'Մասնաճյուղեր')]",
            "//*[self::button or self::a or self::div][contains(normalize-space(.), 'Branches')]",
        ]
        for selector in selectors:
            for element in self.driver.find_elements(By.XPATH, selector):
                try:
                    if not element.is_displayed():
                        continue
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(1)
                    return
                except Exception:
                    continue

    def _expand_branch_dropdowns(self) -> None:
        selectors = [
            "[aria-expanded='false']",
            "[class*='accordion'] button",
            "[class*='accordion'] [role='button']",
            "[class*='branch'] button",
            "[class*='location'] button",
            "[class*='office'] button",
            "[class*='branch'] [role='button']",
            "[class*='location'] [role='button']",
            "[class*='office'] [role='button']",
        ]
        seen = set()

        for selector in selectors:
            for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if not element.is_displayed():
                        continue

                    label = " ".join(
                        value
                        for value in [
                            element.text.strip(),
                            (element.get_attribute("aria-label") or "").strip(),
                            (element.get_attribute("title") or "").strip(),
                        ]
                        if value
                    )
                    if self._is_map_control(label):
                        continue

                    element_id = element.id
                    if element_id in seen:
                        continue
                    seen.add(element_id)

                    aria_expanded = (element.get_attribute("aria-expanded") or "").lower()
                    if aria_expanded == "true":
                        continue

                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        element,
                    )
                    self.driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.3)
                except Exception:
                    continue

    def _extract_branch_cards(self, soup: BeautifulSoup) -> list[dict]:
        branches = []
        seen = set()
        selectors = [
            ".branch-item",
            ".branch-card",
            ".office-item",
            ".office",
            ".location-item",
            "[class*='accordion']",
            "[class*='branch']",
            "[class*='office']",
            "[class*='location']",
            "article",
            "section",
            "li",
            "div",
        ]

        for selector in selectors:
            for item in soup.select(selector):
                block_text = item.get_text("\n", strip=True)
                if len(block_text) < 30:
                    continue
                if "Հասց" not in block_text and "Հեռ" not in block_text and "Phone" not in block_text:
                    continue
                if block_text.count("Հասցե") > 1 or block_text.count("Հեռ") > 1:
                    continue

                branch = self._parse_branch_block(block_text)
                if not branch:
                    continue

                key = (branch.get("name", ""), branch.get("address", ""))
                if key in seen:
                    continue

                seen.add(key)
                branches.append(branch)

        return branches

    def _parse_branch_block(self, block_text: str) -> dict:
        lines = [line.strip() for line in block_text.splitlines() if line.strip()]
        if len(lines) < 4:
            return {}

        name = self._extract_branch_name(lines)
        if not name or self._is_map_control(name) or self._is_branch_label(name):
            return {}

        address = self._extract_labeled_value(lines, ("հասց", "address"))
        phone = self._extract_labeled_value(lines, ("հեռ", "phone", "tel"))
        hours = self._extract_labeled_value(
            lines,
            ("ժամ", "սպասարկ", "hours", "working", "schedule"),
        )

        if not address and not phone:
            return {}

        return {
            "name": name,
            "address": address,
            "phone": phone,
            "hours": hours,
            "raw_text": self._build_branch_raw_text(name, address, phone, hours),
        }

    def _extract_branch_records_from_page(self, soup: BeautifulSoup) -> list[dict]:
        lines = self._normalize_page_lines(soup.get_text("\n", strip=True).splitlines())
        branches = []
        current = None
        index = 0

        while index < len(lines):
            line = lines[index]
            if self._is_footer_line(line):
                break

            if self._is_branch_title_candidate(lines, index):
                if current and (current.get("address") or current.get("phone")):
                    current["raw_text"] = self._build_branch_raw_text(
                        current.get("name", ""),
                        current.get("address", ""),
                        current.get("phone", ""),
                        current.get("hours", ""),
                    )
                    branches.append(current)
                current = {
                    "name": line,
                    "address": "",
                    "phone": "",
                    "hours": "",
                    "raw_text": line,
                }
                index += 1
                continue

            if current:
                if self._is_address_label(line):
                    value = self._next_data_line(lines, index + 1)
                    if value:
                        current["address"] = value
                elif self._is_phone_label(line):
                    value = self._next_data_line(lines, index + 1)
                    if value:
                        current["phone"] = value
                elif self._is_hours_label(line):
                    value = self._next_data_line(lines, index + 1)
                    if value:
                        current["hours"] = value

                if line not in current["raw_text"]:
                    current["raw_text"] += f" | {line}"

            index += 1

        if current and (current.get("address") or current.get("phone")):
            current["raw_text"] = self._build_branch_raw_text(
                current.get("name", ""),
                current.get("address", ""),
                current.get("phone", ""),
                current.get("hours", ""),
            )
            branches.append(current)

        deduped = []
        seen = set()
        for branch in branches:
            key = (branch.get("name", ""), branch.get("address", ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(branch)

        return deduped

    def _extract_branch_name(self, lines: list[str]) -> str:
        for index, line in enumerate(lines):
            if not self._is_address_label(line):
                continue

            for previous_line in reversed(lines[:index]):
                if self._is_map_control(previous_line) or self._is_branch_label(previous_line):
                    continue
                return previous_line
            return ""

        first_line = lines[0]
        if self._is_map_control(first_line) or self._is_branch_label(first_line):
            return ""
        return first_line

    def _extract_labeled_value(self, lines: list[str], labels: tuple[str, ...]) -> str:
        for index, line in enumerate(lines):
            normalized = line.lower()
            if not any(label in normalized for label in labels):
                continue

            if ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    return value

            for next_line in lines[index + 1:]:
                next_normalized = next_line.lower()
                if any(label in next_normalized for label in labels):
                    continue
                if self._is_map_control(next_line) or self._is_branch_label(next_line):
                    continue
                return next_line

        return ""

    def _normalize_page_lines(self, lines: list[str]) -> list[str]:
        normalized_lines = []
        for line in lines:
            cleaned = " ".join(line.split()).strip()
            if not cleaned:
                continue
            if self._is_map_control(cleaned):
                continue
            normalized_lines.append(cleaned)
        return normalized_lines

    def _is_branch_title_candidate(self, lines: list[str], index: int) -> bool:
        line = lines[index]
        if self._is_map_control(line) or self._is_branch_label(line):
            return False
        if line in self.GENERIC_BRANCH_TEXT:
            return False

        lookahead = lines[index + 1:index + 4]
        return any(self._is_address_label(candidate) for candidate in lookahead)

    def _next_data_line(self, lines: list[str], start_index: int) -> str:
        for line in lines[start_index:]:
            if self._is_map_control(line) or self._is_branch_label(line):
                continue
            return line
        return ""

    def _is_address_label(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip(" `:։.-").lower()
        return ("հասց" in normalized or "address" in normalized) and "էլ" not in normalized and "email" not in normalized

    def _is_phone_label(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip(" `:։.-").lower()
        return any(marker in normalized for marker in ("հեռ", "phone", "tel"))

    def _is_hours_label(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip(" `:։.-").lower()
        return any(marker in normalized for marker in ("ժամ", "սպասարկ", "hours", "working", "schedule"))

    def _is_branch_label(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip(" `:։.-").lower()
        if not normalized:
            return True
        if text in self.GENERIC_BRANCH_TEXT:
            return True
        label_markers = (
            "հասց",
            "հեռ",
            "կառավար",
            "հաճախորդ",
            "phone",
            "address",
            "hours",
            "schedule",
            "email",
            "էլ",
        )
        return any(marker in normalized for marker in label_markers)

    def _is_map_control(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip()
        return normalized in self.MAP_CONTROL_TEXT

    def _is_footer_line(self, text: str) -> bool:
        normalized = " ".join(text.split()).strip()
        return any(marker in normalized for marker in self.FOOTER_START_MARKERS)

    def _build_branch_raw_text(self, name: str, address: str, phone: str, hours: str) -> str:
        parts = [name]
        if address:
            parts.extend(["Հասցե", address])
        if phone:
            parts.extend(["Հեռ.՝", phone])
        if hours:
            parts.extend(["Հաճախորդների սպասարկում ՝", hours])
        return " | ".join(part for part in parts if part)
