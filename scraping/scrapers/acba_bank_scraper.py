import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .pending_bank_scraper import PendingBankScraper


class AcbaBankScraper(PendingBankScraper):
    bank_name = "ACBA Bank"
    base_url = "https://www.acba.am"
    file_stem = "acba_bank"

    LOANS_URL = "/hy/individuals/loans"
    LOAN_PATH_PREFIX = "/hy/individuals/loans/"
    DEPOSITS_URL = "/hy/individuals/save-and-invest/deposits"
    DEPOSIT_PATH_PREFIX = "/hy/individuals/save-and-invest/deposits/"
    EXCLUDED_LOAN_PATHS = {
        "/hy/individuals/loans/e-signatures",
    }
    CONDITIONS_TAB_MARKERS = (
        "Տրամադրման պայմաններ",
        "Պայմաններ",
    )
    DEPOSIT_RATE_TAB_MARKERS = (
        "Գործող տոկոսադրույք",
    )
    GENERIC_BREADCRUMBS = {
        "Գլխավոր",
        "Անհատներ",
        "Ստանալ վարկ",
    }

    BRANCHES_URL = "/hy/about-bank/Branches-and-ATMs"
    BRANCH_CARD_SELECTOR = ".fb_branches .fb_branch"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    def scrape_credits(self) -> list[dict]:
        url = self.resolve_url(self.LOANS_URL)
        html = self._fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        detail_urls = self._extract_loan_urls(soup)
        credits = []
        seen = set()

        for detail_url in detail_urls:
            product = self._extract_loan_product(detail_url)
            if not product:
                continue

            source_url = product.get("source_url", detail_url)
            if source_url in seen:
                continue

            seen.add(source_url)
            credits.append(product)

        return credits

    def scrape_deposits(self) -> list[dict]:
        url = self.resolve_url(self.DEPOSITS_URL)
        html = self._fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        detail_urls = self._extract_deposit_urls(soup)
        deposits = []
        seen = set()

        for detail_url in detail_urls:
            product = self._extract_deposit_product(detail_url)
            if not product:
                continue

            source_url = product.get("source_url", detail_url)
            if source_url in seen:
                continue

            seen.add(source_url)
            deposits.append(product)

        return deposits

    def scrape_branches(self) -> list[dict]:
        url = self.resolve_url(self.BRANCHES_URL)
        html = self._fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        return self._extract_branch_cards(soup)

    def _fetch_html(self, url: str) -> str:
        print(f"  [fetch] {url}")
        try:
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(request, timeout=20) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(encoding, errors="replace")
        except Exception as exc:
            print(f"  [!] Failed to fetch {url}: {exc}")
            return ""

    def _extract_loan_urls(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        seen = set()

        for link in soup.select("a[href]"):
            href = (link.get("href") or "").strip()
            if not href:
                continue

            url = self.resolve_url(href)
            path = urlparse(url).path.rstrip("/")
            if not path.startswith(self.LOAN_PATH_PREFIX):
                continue
            if path in self.EXCLUDED_LOAN_PATHS:
                continue
            canonical_url = self.resolve_url(path)
            if canonical_url in seen:
                continue

            seen.add(canonical_url)
            urls.append(canonical_url)

        return urls

    def _extract_loan_product(self, url: str) -> dict:
        path = urlparse(url).path.rstrip("/")
        if path in self.EXCLUDED_LOAN_PATHS:
            return {}

        html = self._fetch_html(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        if not self._is_loan_product_page(soup):
            return {}

        title = self._extract_loan_title(soup, url)
        if not title or "ստորագրում" in title.lower():
            return {}

        details_parts = []
        intro = self._clean_text(
            soup.select_one(".product__right__text-forHeight").get_text(" ", strip=True)
            if soup.select_one(".product__right__text-forHeight")
            else ""
        )
        if intro:
            details_parts.append(intro)
        details_parts.extend(self._extract_loan_feature_lines(soup))

        product = {
            "type": title,
            "source_url": url,
            "details": self._join_unique_parts(details_parts, max_length=2500),
            "rates_table": self._extract_loan_conditions(soup),
        }

        parent_type = self._extract_loan_parent_type(soup, title)
        if parent_type:
            product["parent_type"] = parent_type

        return product

    def _is_loan_product_page(self, soup: BeautifulSoup) -> bool:
        if not soup.select_one(".template_head__title"):
            return False

        return bool(
            soup.select_one(".product__head")
            or soup.select_one(".product__bus_cart__item-c")
            or soup.select_one(".tabs__tpl1__bodys__item")
        )

    def _extract_loan_title(self, soup: BeautifulSoup, url: str) -> str:
        title = self._clean_text(
            soup.select_one(".template_head__title").get_text(" ", strip=True)
            if soup.select_one(".template_head__title")
            else ""
        )
        if title:
            return title

        page_title = self._clean_text(
            soup.title.get_text(" ", strip=True).replace("| Acba.am", "")
            if soup.title
            else ""
        )
        if page_title:
            return page_title

        path = urlparse(url).path.rstrip("/").split("/")[-1]
        return path.replace("-", " ").strip()

    def _extract_loan_parent_type(self, soup: BeautifulSoup, title: str) -> str:
        breadcrumbs = [
            self._clean_text(item.get_text(" ", strip=True))
            for item in soup.select(".page_path__list-item")
            if self._clean_text(item.get_text(" ", strip=True))
        ]
        breadcrumbs = [
            item for item in breadcrumbs if item not in self.GENERIC_BREADCRUMBS
        ]
        if breadcrumbs and breadcrumbs[-1] == title:
            breadcrumbs = breadcrumbs[:-1]
        if not breadcrumbs:
            return ""

        parent_type = breadcrumbs[-1]
        return "" if parent_type == title else parent_type

    def _extract_loan_feature_lines(self, soup: BeautifulSoup) -> list[str]:
        lines = []
        seen = set()

        for card in soup.select(".product__bus_cart__item-c"):
            title = self._clean_text(
                card.select_one(".product__bus_cart__item-c__title").get_text(" ", strip=True)
                if card.select_one(".product__bus_cart__item-c__title")
                else ""
            )
            if not title:
                continue

            values = []
            subtitle = self._clean_text(
                card.select_one(".product__bus_cart__item-c__sub_title").get_text(" ", strip=True)
                if card.select_one(".product__bus_cart__item-c__sub_title")
                else ""
            )
            detail = self._clean_text(
                card.select_one(".wizGuide__text").get_text(" ", strip=True)
                if card.select_one(".wizGuide__text")
                else ""
            )

            if subtitle:
                values.append(subtitle)
            if detail:
                values.append(detail)

            line = title
            if values:
                line = f"{title}: {self._join_unique_parts(values, max_length=500)}"

            if line in seen:
                continue

            seen.add(line)
            lines.append(line)

        return lines

    def _extract_loan_conditions(self, soup: BeautifulSoup) -> str:
        tabs = [
            self._clean_text(tab.get_text(" ", strip=True))
            for tab in soup.select(".tabs__tpl1__tabs__item")
        ]
        bodies = soup.select(".tabs__tpl1__bodys > .tabs__tpl1__bodys__item")

        for index, label in enumerate(tabs):
            if not any(marker in label for marker in self.CONDITIONS_TAB_MARKERS):
                continue
            if index >= len(bodies):
                continue

            formatted = self._format_conditions_body(bodies[index])
            if not formatted:
                continue

            if self._has_data_table(bodies[index]):
                return formatted

            extra_sections = []
            for extra_index, extra_label in enumerate(tabs):
                if extra_index == index or extra_index >= len(bodies):
                    continue
                if not self._has_data_table(bodies[extra_index]):
                    continue

                extra_formatted = self._format_conditions_body(bodies[extra_index])
                if not extra_formatted:
                    continue

                if extra_label and extra_label != "Հատուկ առաջարկ":
                    extra_sections.append(f"{extra_label}\n{extra_formatted}")
                else:
                    extra_sections.append(extra_formatted)

            if extra_sections:
                return "\n\n".join(extra_sections)

            return formatted

        fallback_body = soup.select_one(".tabs__tpl1__bodys__item")
        if fallback_body:
            return self._format_conditions_body(fallback_body)

        return ""

    def _extract_deposit_urls(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        seen = set()

        for link in soup.select("a[href]"):
            href = (link.get("href") or "").strip()
            if not href:
                continue

            url = self.resolve_url(href)
            path = urlparse(url).path.rstrip("/")
            if not path.startswith(self.DEPOSIT_PATH_PREFIX):
                continue
            if path == self.DEPOSITS_URL:
                continue
            canonical_url = self.resolve_url(path)
            if canonical_url in seen:
                continue

            seen.add(canonical_url)
            urls.append(canonical_url)

        return urls

    def _extract_deposit_product(self, url: str) -> dict:
        html = self._fetch_html(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        if not self._is_deposit_product_page(soup):
            return {}

        title = self._extract_loan_title(soup, url)
        if not title:
            return {}

        details_parts = []
        intro = self._clean_text(
            soup.select_one(".product__right__text-forHeight").get_text(" ", strip=True)
            if soup.select_one(".product__right__text-forHeight")
            else ""
        )
        if intro:
            details_parts.append(intro)
        details_parts.extend(self._extract_loan_feature_lines(soup))

        return {
            "type": title,
            "source_url": url,
            "details": self._join_unique_parts(details_parts, max_length=2500),
            "rates_table": self._extract_deposit_rates_table(soup),
        }

    def _is_deposit_product_page(self, soup: BeautifulSoup) -> bool:
        if not soup.select_one(".template_head__title"):
            return False

        return bool(
            soup.select_one(".product__head")
            or soup.select_one(".product__bus_cart__item-c")
            or soup.select_one(".tabs__tpl1__bodys__item")
        )

    def _extract_deposit_rates_table(self, soup: BeautifulSoup) -> str:
        tabs = [
            self._clean_text(tab.get_text(" ", strip=True))
            for tab in soup.select(".tabs__tpl1__tabs__item")
        ]
        bodies = soup.select(".tabs__tpl1__bodys > .tabs__tpl1__bodys__item")

        for index, label in enumerate(tabs):
            if not any(marker in label for marker in self.DEPOSIT_RATE_TAB_MARKERS):
                continue
            if index >= len(bodies):
                continue

            formatted = self._format_conditions_body(bodies[index])
            if formatted:
                return formatted

        for body in bodies:
            if body.select("table"):
                formatted = self._format_conditions_body(body)
                if formatted:
                    return formatted

        return ""

    def _has_data_table(self, container) -> bool:
        return any(not table.find("table") for table in container.find_all("table"))

    def _format_conditions_body(self, body) -> str:
        root = body.select_one(".txt__tpl1") or body
        blocks = []
        seen = set()
        tag_names = ["table", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]

        for element in root.find_all(tag_names, recursive=True):
            if element.name == "table":
                if element.find("table"):
                    continue
                formatted = self._format_html_table(element)
                self._append_unique_block(blocks, seen, formatted)
                continue

            if self._is_inside_leaf_table(element):
                continue
            if element.name == "li" and element.find_parent("li"):
                continue

            text = self._extract_block_text(element)
            self._append_unique_block(blocks, seen, text)

        return "\n".join(blocks)

    def _is_inside_leaf_table(self, element) -> bool:
        parent_table = element.find_parent("table")
        if not parent_table:
            return False
        return not parent_table.find("table")

    def _append_unique_block(self, blocks: list[str], seen: set[str], value: str) -> None:
        cleaned = self._normalize_block(value)
        if not cleaned or cleaned in seen:
            return

        seen.add(cleaned)
        blocks.append(cleaned)

    def _normalize_block(self, value: str) -> str:
        lines = [
            self._clean_text(line)
            for line in (value or "").splitlines()
        ]
        return "\n".join(line for line in lines if line)

    def _extract_block_text(self, element) -> str:
        temp = BeautifulSoup(str(element), "html.parser")
        for br in temp.find_all("br"):
            br.replace_with(" __BR__ ")

        text = temp.get_text(" ", strip=True)
        text = re.sub(r"\s*__BR__\s*", "\n", text)
        return text

    def _format_html_table(self, table) -> str:
        rows = []

        for row in table.select("tr"):
            cells = []
            for cell in row.select("th, td"):
                value = self._clean_table_cell_text(cell.get_text(" ", strip=True))
                if value:
                    cells.append(value)

            if cells:
                rows.append(" | ".join(cells))

        multi_header_rows = self._format_multi_header_table_rows(table)
        if multi_header_rows:
            return "\n".join(multi_header_rows)

        structured_rows = self._format_structured_table_rows(table)
        if structured_rows:
            return "\n".join(structured_rows)

        return "\n".join(rows)

    def _format_multi_header_table_rows(self, table) -> list[str]:
        raw_rows = self._extract_raw_table_rows(table)
        if len(raw_rows) < 3:
            return []

        first_row = raw_rows[0]
        if not any(cell["rowspan"] > 1 or cell["colspan"] > 1 for cell in first_row):
            return []

        expanded_rows = self._expand_table_rows(raw_rows)
        if len(expanded_rows) < 3:
            return []

        header_rows = expanded_rows[:2]
        data_rows = expanded_rows[2:]
        formatted_rows = []

        for row in data_rows:
            pairs = []
            for index, value in enumerate(row):
                value = self._clean_text(value)
                if not value:
                    continue

                header_parts = []
                for header_row in header_rows:
                    if index >= len(header_row):
                        continue

                    header = self._clean_text(header_row[index])
                    if header and header not in header_parts:
                        header_parts.append(header)

                header = " ".join(header_parts)
                if header and header != value:
                    pairs.append(f"{header} {value}")
                else:
                    pairs.append(value)

            if pairs:
                formatted_rows.append(" | ".join(pairs))

        return formatted_rows

    def _extract_raw_table_rows(self, table) -> list[list[dict]]:
        rows = []

        for row in table.select("tr"):
            cells = []
            for cell in row.select("th, td"):
                text = self._clean_table_cell_text(cell.get_text(" ", strip=True))
                if not text:
                    continue

                cells.append(
                    {
                        "text": text,
                        "rowspan": int(cell.get("rowspan") or 1),
                        "colspan": int(cell.get("colspan") or 1),
                    }
                )

            if cells:
                rows.append(cells)

        return rows

    def _expand_table_rows(self, raw_rows: list[list[dict]]) -> list[list[str]]:
        grid = []
        active_rowspans = {}

        for raw_row in raw_rows:
            row = []
            col_index = 0

            while col_index in active_rowspans:
                value, remaining = active_rowspans[col_index]
                row.append(value)
                if remaining <= 1:
                    del active_rowspans[col_index]
                else:
                    active_rowspans[col_index] = (value, remaining - 1)
                col_index += 1

            for cell in raw_row:
                while col_index in active_rowspans:
                    value, remaining = active_rowspans[col_index]
                    row.append(value)
                    if remaining <= 1:
                        del active_rowspans[col_index]
                    else:
                        active_rowspans[col_index] = (value, remaining - 1)
                    col_index += 1

                for offset in range(cell["colspan"]):
                    row.append(cell["text"])
                    if cell["rowspan"] > 1:
                        active_rowspans[col_index + offset] = (
                            cell["text"],
                            cell["rowspan"] - 1,
                        )
                col_index += cell["colspan"]

            while col_index in active_rowspans:
                value, remaining = active_rowspans[col_index]
                row.append(value)
                if remaining <= 1:
                    del active_rowspans[col_index]
                else:
                    active_rowspans[col_index] = (value, remaining - 1)
                col_index += 1

            grid.append(row)

        return grid

    def _format_structured_table_rows(self, table) -> list[str]:
        rows = []

        for row in table.select("tr"):
            cells = []
            for cell in row.select("th, td"):
                value = self._clean_table_cell_text(cell.get_text(" ", strip=True))
                if value:
                    cells.append(value)
            if cells:
                rows.append(cells)

        if len(rows) < 2:
            return []

        headers = rows[0]
        if len(headers) < 2:
            return []
        if any(re.search(r"\d", header) for header in headers):
            return []

        formatted_rows = []
        for row in rows[1:]:
            pairs = []
            for index, value in enumerate(row):
                if not value:
                    continue
                header = headers[index] if index < len(headers) else ""
                if header:
                    pairs.append(f"{header} {value}")
                else:
                    pairs.append(value)

            if pairs:
                formatted_rows.append(" | ".join(pairs))

        return formatted_rows

    def _join_unique_parts(self, parts: list[str], max_length: int = 2500) -> str:
        unique_parts = []
        seen = set()
        current_length = 0

        for part in parts:
            cleaned = self._clean_text(part)
            if not cleaned or cleaned in seen:
                continue

            extra_length = len(cleaned) if not unique_parts else len(cleaned) + 3
            if current_length + extra_length > max_length:
                break

            seen.add(cleaned)
            unique_parts.append(cleaned)
            current_length += extra_length

        return " | ".join(unique_parts)

    def _extract_branch_cards(self, soup: BeautifulSoup) -> list[dict]:
        branches = []
        seen = set()

        for card in soup.select(self.BRANCH_CARD_SELECTOR):
            name = self._clean_text(
                card.select_one(".fb_branch__head__title").get_text(" ", strip=True)
                if card.select_one(".fb_branch__head__title")
                else ""
            )
            place = self._clean_text(
                card.select_one(".fb_branch__place").get_text(" ", strip=True)
                if card.select_one(".fb_branch__place")
                else ""
            )

            items = [
                self._clean_text(item.get_text(" ", strip=True))
                for item in card.select(".fb_branch__list .fb_branch__list__item")
                if self._clean_text(item.get_text(" ", strip=True))
            ]
            if not name or not items:
                continue

            address_line = items[0]
            hours = " | ".join(items[1:])
            address = self._compose_address(place, address_line)

            branch = {
                "name": name,
                "address": address,
                "hours": hours,
                "raw_text": self._build_branch_raw_text(
                    name=name,
                    address=address,
                    hours=hours,
                ),
            }

            key = (name, address)
            if key in seen:
                continue

            seen.add(key)
            branches.append(branch)

        return branches

    def _compose_address(self, place: str, address_line: str) -> str:
        if not place:
            return address_line

        normalized_place = self._normalize_for_match(place)
        normalized_address = self._normalize_for_match(address_line)
        if normalized_place and normalized_place in normalized_address:
            return address_line

        return self._clean_text(f"{place}, {address_line}")

    def _normalize_for_match(self, text: str) -> str:
        cleaned = self._clean_text(text).lower()
        cleaned = cleaned.replace("ք.", "").replace("գ.", "").replace("գ․", "")
        return cleaned.strip(" ,")

    def _clean_table_cell_text(self, text: str) -> str:
        cleaned = self._clean_text(text)
        compact = cleaned.replace(" ", "")
        if "%" in cleaned and re.fullmatch(r"[-\d.,%]+", compact):
            return compact
        return cleaned

    def _clean_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text or "").strip().strip("|")
        cleaned = re.sub(r"\s+([։՝,;:!?])", r"\1", cleaned)
        return cleaned

    def _build_branch_raw_text(
        self,
        name: str,
        address: str,
        hours: str,
    ) -> str:
        parts = [name]
        if address:
            parts.extend(["Հասցե", address])
        if hours:
            parts.extend(["Աշխատաժամեր", hours])
        return " | ".join(parts)
