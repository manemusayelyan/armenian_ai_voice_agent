import json
import re
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .pending_bank_scraper import PendingBankScraper


class ArmeconombankScraper(PendingBankScraper):
    bank_name = "Armeconombank"
    base_url = "https://www.aeb.am"
    file_stem = "armeconombank"

    LOANS_URL = "/hy/individual/loans"
    LOAN_CARD_SELECTOR = ".loans-listing .cardInfo-block.__listing-item"
    DEPOSITS_URL = "/hy/individual/deposits"
    DEPOSIT_CARD_SELECTOR = ".deposits-listing .cardInfo-block.__listing-item"
    BRANCHES_URL = "/hy/branch-service-network"
    BRANCH_CARD_SELECTOR = "#branches-point-list .point-item"
    BRANCH_POINTS_PATTERN = re.compile(
        r"window\.branchPoints\s*=\s*(\[[\s\S]*?\]);"
    )
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
        loan_entries = self._extract_loan_urls(soup)
        credits = []
        seen = set()

        for entry in loan_entries:
            detail_url = entry["url"]
            if detail_url in seen:
                continue

            product = self._extract_loan_product(
                url=detail_url,
                parent_type=entry.get("parent_type", ""),
            )
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
            if detail_url in seen:
                continue

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
        script_branches = self._extract_branch_points_from_script(html)
        script_by_name = {branch["name"]: branch for branch in script_branches}
        card_branches = self._extract_sidebar_branch_cards(
            soup=soup,
            script_by_name=script_by_name,
        )

        return card_branches or script_branches

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

    def _extract_loan_urls(self, soup: BeautifulSoup) -> list[dict]:
        entries = []
        seen = set()
        tab_labels = {
            link.get("href", "").lstrip("#"): self._clean_text(link.get_text(" ", strip=True))
            for link in soup.select("#loans-description-navbar a[href^='#']")
            if link.get("href")
        }

        for pane in soup.select(".loans-listing .tab-pane"):
            parent_type = tab_labels.get(pane.get("id", ""), "")
            for link in pane.select(".cardInfo-actions a[href]"):
                href = self.resolve_url(link.get("href", ""))
                if not href or "/hy/individual/loans/" not in href:
                    continue
                if href in seen:
                    continue

                seen.add(href)
                entries.append(
                    {
                        "url": href,
                        "parent_type": parent_type,
                    }
                )

        return entries

    def _extract_loan_product(self, url: str, parent_type: str = "") -> dict:
        html = self._fetch_html(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        title_element = soup.select_one("h1.page-title")
        name = self._clean_text(title_element.get_text(" ", strip=True) if title_element else "")
        if not name:
            return {}

        hero_details = soup.select_one(".position-relative.cardInfo-block .cardInfo-details")
        intro = self._clean_text(
            hero_details.select_one(":scope > .mb-3").get_text(" ", strip=True)
            if hero_details and hero_details.select_one(":scope > .mb-3")
            else ""
        )

        details_parts = []
        if intro:
            details_parts.append(intro)
        details_parts.extend(self._extract_info_box_lines(soup))

        product = {
            "type": name,
            "source_url": url,
            "details": self._join_unique_parts(details_parts, max_length=2000),
            "rates_table": self._extract_first_loan_table(soup),
        }

        if parent_type:
            product["parent_type"] = parent_type

        return product

    def _extract_first_loan_table(self, soup: BeautifulSoup) -> str:
        first_item = soup.select_one("#conditions-tab #card-conditions-info .accordion-item")
        if not first_item:
            return ""

        body = first_item.select_one(".accordion-body")
        if not body:
            return ""

        rows = []

        for row in body.find_all("div", class_="accordion-card-row", recursive=False):
            classes = row.get("class", [])
            if "row" not in classes:
                continue

            label_container = row.select_one(".accordion-label")
            value_container = self._find_loan_value_container(row)

            label = self._clean_text(
                label_container.get_text(" ", strip=True) if label_container else ""
            )
            value = self._extract_loan_value(value_container)
            note = self._extract_loan_row_note(row)

            parts = []
            if value:
                parts.append(value)
            if note:
                parts.append(f"Նշում - {note}")

            if label and parts:
                rows.append(f"{label} | {' | '.join(parts)}")
            elif label:
                rows.append(label)
            elif parts:
                rows.append(" | ".join(parts))

        return "\n".join(row for row in rows if row)

    def _find_loan_value_container(self, row):
        for child in row.find_all("div", recursive=False):
            classes = child.get("class", [])
            if "accordion-label" in classes:
                continue
            return child
        return None

    def _extract_loan_row_note(self, row) -> str:
        next_sibling = row.find_next_sibling()
        if not next_sibling or next_sibling.name != "div":
            return ""
        if "collapse" not in next_sibling.get("class", []):
            return ""
        return self._clean_text(next_sibling.get_text(" ", strip=True))

    def _extract_loan_value(self, container) -> str:
        if container is None:
            return ""

        description_list = container.select_one("dl.description-list")
        if description_list:
            return self._extract_description_list_value(description_list)

        parts = []
        pending_prefix = ""

        for child in container.children:
            if not getattr(child, "name", None):
                continue

            if child.name in {"ul", "ol"}:
                items = [
                    self._clean_text(item.get_text(" ", strip=True))
                    for item in child.find_all("li", recursive=False)
                    if self._clean_text(item.get_text(" ", strip=True))
                ]
                if not items:
                    continue

                joined_items = "; ".join(items)
                if pending_prefix:
                    parts.append(f"{pending_prefix} {joined_items}".strip())
                    pending_prefix = ""
                else:
                    parts.append(joined_items)
                continue

            text = self._clean_text(child.get_text(" ", strip=True))
            if not text:
                continue

            has_list_after = any(
                getattr(sibling, "name", None) in {"ul", "ol"}
                for sibling in child.next_siblings
                if getattr(sibling, "name", None)
            )

            if has_list_after:
                pending_prefix = text
            else:
                if pending_prefix:
                    parts.append(f"{pending_prefix} {text}".strip())
                    pending_prefix = ""
                else:
                    parts.append(text)

        if pending_prefix:
            parts.append(pending_prefix)

        return " | ".join(part for part in parts if part)

    def _extract_description_list_value(self, description_list) -> str:
        parts = []
        current_term = ""

        for child in description_list.find_all(["dt", "dd"], recursive=False):
            text = self._clean_text(child.get_text(" ", strip=True))
            if child.name == "dt":
                current_term = text
                continue

            if not text:
                continue

            if current_term:
                parts.append(f"{current_term} - {text}")
                current_term = ""
            else:
                parts.append(text)

        if current_term:
            parts.append(current_term)

        return " | ".join(part for part in parts if part)

    def _extract_deposit_urls(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        seen = set()

        for link in soup.select(f"{self.DEPOSIT_CARD_SELECTOR} .cardInfo-actions a[href]"):
            href = self.resolve_url(link.get("href", ""))
            if not href or "/hy/individual/deposit/" not in href:
                continue
            if href in seen:
                continue

            seen.add(href)
            urls.append(href)

        return urls

    def _extract_deposit_product(self, url: str) -> dict:
        html = self._fetch_html(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        name = self._clean_text(
            soup.select_one("h1.page-title").get_text(" ", strip=True)
            if soup.select_one("h1.page-title")
            else ""
        )
        if not name:
            return {}

        hero_details = soup.select_one(".position-relative.cardInfo-block .cardInfo-details")
        intro = self._clean_text(
            hero_details.select_one(":scope > .mb-3").get_text(" ", strip=True)
            if hero_details and hero_details.select_one(":scope > .mb-3")
            else ""
        )

        details_parts = []
        if intro:
            details_parts.append(intro)
        details_parts.extend(self._extract_info_box_lines(soup))
        details_parts.extend(self._extract_pre_nav_text_lines(soup))

        return {
            "type": name,
            "source_url": url,
            "details": self._join_unique_parts(details_parts, max_length=2500),
            "rates_table": self._extract_deposit_rates_table(soup),
        }

    def _extract_info_box_lines(self, soup: BeautifulSoup) -> list[str]:
        lines = []
        seen = set()

        for box in soup.select(".position-relative.cardInfo-block .info-box-row .info-box"):
            value = self._clean_text(
                box.select_one(".info-box-title").get_text(" ", strip=True)
                if box.select_one(".info-box-title")
                else ""
            )
            label = self._clean_text(
                box.select_one("small").get_text(" ", strip=True)
                if box.select_one("small")
                else ""
            )

            line = ""
            if label and value:
                line = f"{label}: {value}"
            else:
                line = value or label

            if not line or line in seen:
                continue

            seen.add(line)
            lines.append(line)

        return lines

    def _extract_pre_nav_text_lines(self, soup: BeautifulSoup) -> list[str]:
        lines = []
        seen = set()
        container = soup.select_one(".position-relative.cardInfo-block .card-body.rich-editor-content")
        if not container:
            return lines

        for element in container.select("p, li"):
            text = self._clean_text(element.get_text(" ", strip=True))
            if not text or text in seen:
                continue

            seen.add(text)
            lines.append(text)

        return lines

    def _extract_deposit_rates_table(self, soup: BeautifulSoup) -> str:
        conditions_tab = soup.select_one("#conditions-tab")
        if not conditions_tab:
            return self._extract_inline_deposit_table(soup)

        sections = []
        pending_heading = ""

        for child in conditions_tab.children:
            if not getattr(child, "name", None):
                continue

            classes = child.get("class", [])
            text = self._clean_text(child.get_text(" ", strip=True))

            if child.name in {"h2", "h3", "h4", "h5"} or any(
                cls in {"h2", "h3", "h4", "h5"} for cls in classes
            ):
                pending_heading = text
                continue

            if child.name == "div" and "tab-content" in classes and "mb-5" in classes:
                section = self._format_interest_matrix_block(
                    block=child,
                    heading=pending_heading,
                )
                if section:
                    sections.append(section)
                pending_heading = ""

        if sections:
            return "\n\n".join(section for section in sections if section)

        return self._extract_inline_deposit_table(soup)

    def _format_interest_matrix_block(self, block, heading: str) -> str:
        parts = []
        if heading:
            parts.append(heading)

        panes = block.find_all("div", class_="tab-pane", recursive=False)
        include_currency = len(panes) > 1

        for pane in panes:
            pane_text = self._format_interest_matrix_pane(
                pane,
                include_currency=include_currency,
            )
            if pane_text:
                parts.append(pane_text)

        return "\n".join(parts).strip()

    def _format_interest_matrix_pane(self, pane, include_currency: bool) -> str:
        lines = []
        pane_id = pane.get("id", "")
        currency = self._extract_currency_from_pane_id(pane_id)
        if include_currency and currency:
            lines.append(currency)

        header = pane.select_one(".content-row.text-primary")
        columns = []
        subtitle = ""
        if header:
            columns = [
                self._clean_text(column.get_text(" ", strip=True))
                for column in header.select(".col b")
                if self._clean_text(column.get_text(" ", strip=True))
            ]
            subtitle = self._clean_text(
                header.select_one("span.small").get_text(" ", strip=True)
                if header.select_one("span.small")
                else ""
            )
        row_definitions = []

        for row in pane.find_all("div", recursive=False):
            classes = row.get("class", [])
            if "content-row" not in classes or "collapsable" not in classes:
                continue

            label = self._clean_text(
                row.select_one("label").get_text(" ", strip=True)
                if row.select_one("label")
                else row.get_text(" ", strip=True)
            )
            value_block = row.find_next_sibling(
                lambda tag: tag.name == "div" and "collapse" in tag.get("class", [])
            )
            values = []
            if value_block:
                for column in value_block.select(".row > .col"):
                    value = self._clean_text(column.get_text(" ", strip=True))
                    if value:
                        values.append(value)

            if label or values:
                row_definitions.append((label, values))

        if columns and row_definitions:
            column_count = max(
                len(columns),
                max((len(values) for _, values in row_definitions), default=0),
            )
            for index in range(column_count):
                term = columns[index] if index < len(columns) else ""
                row_parts = [term] if term else []

                for label, values in row_definitions:
                    if index >= len(values):
                        continue

                    value = values[index]
                    if not value:
                        continue

                    if label:
                        row_parts.append(f"{label} - {value}")
                    else:
                        row_parts.append(value)

                if row_parts:
                    lines.append(" | ".join(row_parts))
        else:
            if columns:
                lines.append(" | ".join(columns))
            if subtitle:
                lines.append(subtitle)
            for label, values in row_definitions:
                row_parts = [label] + values if label else values
                if row_parts:
                    lines.append(" | ".join(row_parts))

        return "\n".join(line for line in lines if line)

    def _extract_currency_from_pane_id(self, pane_id: str) -> str:
        code = pane_id.split("-", 1)[0].upper()
        if code in {"AMD", "USD", "EUR", "RUB"}:
            return code
        return code if code else ""

    def _extract_inline_deposit_table(self, soup: BeautifulSoup) -> str:
        tables = []
        seen = set()

        for table in soup.select(".rich-editor-content table"):
            formatted = self._format_html_table(table)
            if not formatted or formatted in seen:
                continue

            seen.add(formatted)
            tables.append(formatted)

        return "\n\n".join(tables)

    def _format_html_table(self, table) -> str:
        rows = []

        for row in table.select("tr"):
            cells = []
            for cell in row.select("th, td"):
                value = self._clean_text(cell.get_text(" ", strip=True))
                if value:
                    cells.append(value)

            if cells:
                rows.append(" | ".join(cells))

        return "\n".join(rows)

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

    def _extract_sidebar_branch_cards(
        self,
        soup: BeautifulSoup,
        script_by_name: dict[str, dict],
    ) -> list[dict]:
        branches = []
        seen = set()

        for item in soup.select(self.BRANCH_CARD_SELECTOR):
            name_element = item.select_one(".point-name")
            name = self._clean_text(name_element.get_text(" ", strip=True) if name_element else "")
            if not name:
                continue

            hours_parts = []
            address = ""
            phone = ""

            for detail in item.select(".point-detail"):
                icon = detail.select_one("i")
                icon_classes = " ".join(icon.get("class", [])) if icon else ""

                if "icon-time" in icon_classes:
                    hours_text = self._extract_hours_from_detail(detail)
                    if hours_text:
                        hours_parts.append(hours_text)
                elif "icon-location" in icon_classes:
                    address_text = detail.select_one("span")
                    address = self._clean_text(
                        address_text.get_text(" ", strip=True) if address_text else detail.get_text(" ", strip=True)
                    )
                elif "icon-phone-ring" in icon_classes:
                    phone = self._clean_text(detail.get_text(" ", strip=True))

            script_branch = script_by_name.get(name)
            if script_branch:
                address = address or script_branch.get("address", "")
                phone = phone or script_branch.get("phone", "")
                if not hours_parts and script_branch.get("hours"):
                    hours_parts = script_branch["hours"].split(" | ")

            if not address and not phone:
                continue

            hours = " | ".join(hours_parts)
            branch = {
                "name": name,
                "address": address,
                "phone": phone,
                "hours": hours,
                "raw_text": self._build_branch_raw_text(name, address, phone, hours),
            }

            key = (name, address, phone)
            if key in seen:
                continue

            seen.add(key)
            branches.append(branch)

        return branches

    def _extract_hours_from_detail(self, detail) -> str:
        parts = []

        for span in detail.select("span"):
            if "open-badge" in span.get("class", []):
                continue

            value = self._normalize_hours_text(span.get_text(" ", strip=True))
            if value:
                parts.append(value)

        return " | ".join(parts)

    def _extract_branch_points_from_script(self, html: str) -> list[dict]:
        match = self.BRANCH_POINTS_PATTERN.search(html)
        if not match:
            return []

        try:
            branch_points = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        branches = []
        seen = set()

        for point in branch_points:
            if not point.get("BranchCode") or not point.get("PhoneNumber"):
                continue

            name = self._clean_text(point.get("Name", ""))
            address = self._clean_text(point.get("Address", ""))
            phone = self._clean_text(point.get("PhoneNumber", ""))
            hours = self._format_combined_working_hours(
                point.get("CombinedWorkingHours") or []
            )

            if not name:
                continue

            key = (name, address, phone)
            if key in seen:
                continue

            seen.add(key)
            branches.append(
                {
                    "name": name,
                    "address": address,
                    "phone": phone,
                    "hours": hours,
                    "raw_text": self._build_branch_raw_text(
                        name,
                        address,
                        phone,
                        hours,
                    ),
                }
            )

        return branches

    def _format_combined_working_hours(self, working_hours: list[dict]) -> str:
        parts = []

        for entry in working_hours:
            days = self._clean_text(entry.get("Days", ""))
            start = (entry.get("WorkTimeFrom") or "")[:5]
            end = (entry.get("WorkTimeTo") or "")[:5]

            if start and end and days:
                parts.append(f"{start}-{end} - {days}")
            elif days:
                parts.append(days)

        return " | ".join(parts)

    def _normalize_hours_text(self, text: str) -> str:
        normalized = self._clean_text(text)
        match = re.match(r"^(\d{2}:\d{2})\s+(\d{2}:\d{2})(.*)$", normalized)
        if not match:
            return normalized

        return f"{match.group(1)}-{match.group(2)}{match.group(3)}"

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _build_branch_raw_text(
        self,
        name: str,
        address: str,
        phone: str,
        hours: str,
    ) -> str:
        parts = [name]
        if address:
            parts.extend(["Հասցե", address])
        if phone:
            parts.extend(["Հեռ․", phone])
        if hours:
            parts.extend(["Աշխատաժամեր", hours])
        return " | ".join(parts)
