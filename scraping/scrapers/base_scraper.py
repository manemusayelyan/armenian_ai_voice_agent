import time
import json
import os
import re
from datetime import date
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


def build_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver. Works on Windows 11 without manual setup."""
    cache_root = os.path.join(os.getcwd(), ".cache")
    os.makedirs(os.path.join(cache_root, "selenium"), exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", cache_root)
    os.environ.setdefault("SE_CACHE_PATH", os.path.join(cache_root, "selenium"))

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=hy")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    # Try Selenium's built-in driver resolution first so local browser setups
    # can work without downloading a separate driver package.
    try:
        return webdriver.Chrome(options=options)
    except Exception:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)


class BaseBankScraper:
    """
    Base class for all Armenian bank scrapers using Selenium.
    Selenium handles JavaScript-rendered pages that requests cannot.
    Each bank subclass overrides scrape_credits(), scrape_deposits(), scrape_branches().
    """

    bank_name: str = ""
    base_url: str = ""
    file_stem: str = ""
    PRODUCT_LINE_DROP_MARKERS = (
        "տեղեկացեք մանրամասն",
        "հնարավոր լրացուցիչ վճարումների չափի մասին",
        "վարկային սակագներ",
        "վարկային սակագների նախկին պայմաններ",
        "վարկի ձևակերպումն իրականացվում է",
        "որոշման և տրամադրման ժամանակահատվածը",
        "կոնտակտային տվյալներ",
        "հեռախոսահամար",
        "էլ հասցե",
        "instagram",
    )
    PRODUCT_STATUS_MARKERS = (
        "գործում է մինչև",
        "դադարեցվել է",
        "դադարեցված է",
        "դիմումների ընդունումը դադարեցված է",
    )
    PRODUCT_LEGAL_MARKERS = (
        "օրենքի շրջանակում",
        "որոշմամբ հաստատված",
        "լուծարման գործընթացում",
        "սուբսիդ",
        "հանձնման-ընդունման ակտ",
    )
    PRODUCT_PROMO_PREFIXES = (
        "ստացե",
        "օգտվե",
        "ձևակերպե",
        "այժմ հերթը քոնն է",
    )

    PRODUCT_LINE_DROP_MARKERS = (
        "տեղեկացեք մանրամասն",
        "հնարավոր լրացուցիչ վճարումների չափի մասին",
        "վարկային սակագներ",
        "վարկային սակագների նախկին պայմաններ",
        "կոնտակտային տվյալներ",
        "հեռախոսահամար",
        "էլ հասցե",
        "instagram",
        "facebook",
        "youtube",
        "telegram",
    )
    PRODUCT_LABEL_DROP_MARKERS = (
        "վարկի ձևակերպ",
        "որոշման և տրամադրման ժամանակահատված",
        "տրամադրման ժամանակահատված",
        "տույժ",
        "քաղվածքի տրամադրում",
        "կանխիկացման վճար",
        "հայտի ուսումնասիրության վճար",
        "նախահաստատման վճար",
        "ապահովագրություն",
        "անշարժ գույքի գնահատ",
        "գրավի ձևակերպման հետ կապված ծախս",
        "կոնտակտ",
        "հեռախոս",
        "էլ հասցե",
    )
    PRODUCT_STATUS_MARKERS = (
        "գործում է մինչև",
        "դադարեց",
        "դիմումների ընդունումը դադարեց",
    )
    PRODUCT_KEEP_MARKERS = (
        "նպատակ",
        "տեսակ",
        "արժույթ",
        "գումար",
        "տոկոս",
        "եկամտաբեր",
        "ժամկետ",
        "տևող",
        "մարման",
        "մարումների",
        "հաճախական",
        "ապահով",
        "գրավ",
        "կանխավճար",
        "տրամադրման եղանակ",
        "վարկ / գրավ",
        "վարկ/գրավ",
        "քարտի տեսակ",
        "արտոնյալ ժամկետ",
        "համալրում",
        "կապիտալ",
        "բոնուս",
        "տոկոսագումարի վճարում",
        "վաղաժամկետ վերադարձ",
        "վաղաժամկետ դադարեց",
        "վարկառու",
        "համավարկառու",
        "երաշխավոր",
        "առավելագույն",
        "նվազագույն",
        "գործակց",
    )

    def __init__(self):
        self.driver = None

    def resolve_url(self, path_or_url: str) -> str:
        """Return an absolute URL for a relative path or passthrough URL."""
        return urljoin(self.base_url.rstrip("/") + "/", path_or_url)

    def start(self):
        """Start the browser. Called once per bank."""
        print(f"  [browser] Starting Chrome...")
        self.driver = build_driver()

    def stop(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_page(self, url: str, wait_seconds: int = 3) -> BeautifulSoup | None:
        """
        Navigate to a URL, wait for JS to render, return BeautifulSoup.
        wait_seconds: time to let JS finish rendering after page load.
        """
        try:
            print(f"  [fetch] {url}")
            self.driver.get(url)
            time.sleep(wait_seconds)
            return BeautifulSoup(self.driver.page_source, "html.parser")
        except Exception as e:
            print(f"  [!] Failed to fetch {url}: {e}")
            return None

    def get_text(self, soup: BeautifulSoup, selector: str) -> str:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    def extract_tables(self, soup: BeautifulSoup) -> list[str]:
        """Extract all tables as formatted strings."""
        tables = []
        for table in soup.select("table"):
            rows = []
            for row in table.select("tr"):
                cells = [td.get_text(strip=True) for td in row.select("td, th")]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                tables.append("\n".join(rows))
        return tables

    def combine_tables(self, tables: list[str]) -> str:
        """Join all extracted tables while removing exact duplicates."""
        unique_tables = []
        seen = set()

        for table in tables:
            normalized = table.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_tables.append(normalized)

        return "\n\n".join(unique_tables)

    def extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content from a page."""
        selectors = [
            "main p", ".content p", "article p", "section p",
            ".text p", ".product-info p", ".loan-info p", ".deposit-info p"
        ]
        content = []
        for sel in selectors:
            content = soup.select(sel)
            if content:
                break
        if not content:
            # Fallback: grab all text from main container
            container = soup.select_one("main, .content, article, .container")
            if container:
                return container.get_text(separator=" | ", strip=True)[:2000]
        return " | ".join(
            el.get_text(strip=True) for el in content if el.get_text(strip=True)
        )[:2000]

    def extract_page_title(self, soup: BeautifulSoup, fallback_url: str = "") -> str:
        """Extract the most likely page title from a product or listing page."""
        return (
            self.get_text(soup, "h1")
            or self.get_text(soup, ".page-title")
            or self.get_text(soup, ".hero-title")
            or self.get_text(soup, ".product-name")
            or urlparse(fallback_url).path.rstrip("/").split("/")[-1].replace("-", " ").title()
        )

    def extract_click_target(self, element) -> str:
        """Best-effort extraction of a navigation target from cards, links, or onclick handlers."""
        for attr in ("href", "data-href", "data-url", "data-link"):
            target = element.get(attr)
            if target:
                return target

        nested_link = element.select_one("a[href]")
        if nested_link and nested_link.get("href"):
            return nested_link["href"]

        onclick = element.get("onclick", "")
        if onclick:
            patterns = [
                r"""(?:window\.)?open\(\s*['"]([^'"]+)['"]""",
                r"""(?:window\.|document\.)?location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""",
                r"""(?:window\.|document\.)?location(?:\.assign|\.replace)?\(\s*['"]([^'"]+)['"]""",
            ]
            for pattern in patterns:
                match = re.search(pattern, onclick, flags=re.IGNORECASE)
                if match:
                    return match.group(1)

        return ""

    def discover_child_page_urls(
        self,
        soup: BeautifulSoup,
        page_url: str,
        link_keywords: tuple[str, ...] = (),
    ) -> list[str]:
        """
        Discover related child pages from clickable cards or links on a listing page.
        This lets us follow JS-driven product cards without hardcoding every child URL.
        """
        page_url = self.resolve_url(page_url)
        page_parts = urlparse(page_url)
        page_path = page_parts.path.rstrip("/")
        seen = set()
        child_urls = []
        selectors = [
            "a[href]",
            "[data-href]",
            "[data-url]",
            "[data-link]",
            "[onclick]",
        ]

        for element in soup.select(", ".join(selectors)):
            raw_target = self.extract_click_target(element)
            if not raw_target:
                continue
            if raw_target.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            candidate_url = urljoin(page_url, raw_target)
            candidate_parts = urlparse(candidate_url)
            candidate_path = candidate_parts.path.rstrip("/")
            if not candidate_path or candidate_path == page_path:
                continue
            if candidate_parts.netloc and candidate_parts.netloc != page_parts.netloc:
                continue
            if candidate_path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".zip")):
                continue

            combined_text = f"{candidate_url} {element.get_text(' ', strip=True)}".lower()
            is_child_path = bool(page_path) and candidate_path.startswith(page_path + "/")
            matches_keywords = any(keyword.lower() in combined_text for keyword in link_keywords)

            if not is_child_path and not matches_keywords:
                continue
            if candidate_url in seen:
                continue

            seen.add(candidate_url)
            child_urls.append(candidate_url)

        return child_urls

    def scrape_product_pages(
        self,
        paths: list[str],
        extract_product,
        link_keywords: tuple[str, ...] = (),
        include_listing_page: bool = False,
    ) -> list[dict]:
        """
        Scrape product pages directly and, when a page is a listing page, also
        discover and visit related child product pages.
        """
        results = []
        seen_urls = set()

        for path in paths:
            page_url = self.resolve_url(path)
            soup = self.get_page(page_url, wait_seconds=4)
            if not soup:
                continue

            child_urls = self.discover_child_page_urls(
                soup=soup,
                page_url=page_url,
                link_keywords=link_keywords,
            )
            parent_type = self.extract_page_title(soup, fallback_url=page_url)

            should_include_page = include_listing_page or not child_urls
            if should_include_page and page_url not in seen_urls:
                product = extract_product(page_url, soup=soup)
                if product:
                    source_url = product.get("source_url", page_url)
                    if source_url not in seen_urls:
                        seen_urls.add(source_url)
                        results.append(product)

            for child_url in child_urls:
                if child_url in seen_urls:
                    continue
                product = extract_product(child_url)
                if not product:
                    continue
                if parent_type:
                    product.setdefault("parent_type", parent_type)

                source_url = product.get("source_url", child_url)
                if source_url in seen_urls:
                    continue

                seen_urls.add(source_url)
                results.append(product)

        return results

    def scrape_credits(self) -> list[dict]:
        raise NotImplementedError

    def scrape_deposits(self) -> list[dict]:
        raise NotImplementedError

    def scrape_branches(self) -> list[dict]:
        raise NotImplementedError

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _strip_product_status(self, text: str) -> str:
        cleaned = self._clean_text(text)
        status_pattern = re.compile(
            r"\s*\((?:[^)]*?(?:Գործում է մինչև|Դադարեցվել է|դադարեցված է|Դիմումների ընդունումը դադարեցված է)[^)]*)\)\s*",
            flags=re.IGNORECASE,
        )
        return self._clean_text(status_pattern.sub(" ", cleaned))

    def _split_details_lines(self, text: str) -> list[str]:
        return [
            self._clean_text(part)
            for part in re.split(r"\s*\|\s*|\n+", text or "")
            if self._clean_text(part)
        ]

    def _split_rates_lines(self, text: str) -> list[str]:
        return [
            self._clean_text(line)
            for line in (text or "").splitlines()
            if self._clean_text(line)
        ]

    def _is_table_header_line(self, line: str) -> bool:
        if "|" not in line or any(char.isdigit() for char in line):
            return False

        normalized = line.casefold()
        header_markers = (
            "արժույթ",
            "տոկոսադրույք",
            "գումար",
            "ժամկետ",
            "եկամտաբերություն",
            "քարտի տեսակը",
            "քարտատեսակ",
        )
        return sum(marker in normalized for marker in header_markers) >= 2

    def _should_drop_product_line(self, line: str, field_name: str) -> bool:
        if not line:
            return True

        normalized = line.casefold()
        if re.search(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", line, flags=re.IGNORECASE):
            return True

        if any(marker in normalized for marker in self.PRODUCT_LINE_DROP_MARKERS):
            return True

        if any(marker in normalized for marker in self.PRODUCT_STATUS_MARKERS):
            return True

        if (
            len(line) > 350
            and any(marker in normalized for marker in self.PRODUCT_LEGAL_MARKERS)
        ):
            return True

        if (
            field_name == "rates_table"
            and self._is_table_header_line(line)
        ):
            return True

        if (
            field_name == "details"
            and ":" not in line
            and "|" not in line
            and not any(char.isdigit() for char in line)
            and any(normalized.startswith(prefix) for prefix in self.PRODUCT_PROMO_PREFIXES)
        ):
            return True

        return False

    def _strip_product_status(self, text: str) -> str:
        cleaned = self._clean_text(text)
        status_pattern = re.compile(
            r"\s*\((?:[^)]*?(?:Գործում է մինչև|Դադարեց[^)]*|Դիմումների ընդունումը դադարեց[^)]*)[^)]*)\)\s*",
            flags=re.IGNORECASE,
        )
        return self._clean_text(status_pattern.sub(" ", cleaned))

    def _split_details_lines(self, text: str) -> list[str]:
        return [
            self._clean_text(part)
            for part in re.split(r"\s*\|\s*|\n+|[•●▪·]+|\s{2,}", text or "")
            if self._clean_text(part)
        ]

    def _looks_like_row_label(self, text: str) -> bool:
        cleaned = self._clean_text(text)
        if not cleaned or len(cleaned) > 80:
            return False
        if not re.search(r"[A-Za-zԱ-Ֆա-ֆ]", cleaned):
            return False
        if any(char.isdigit() for char in cleaned):
            return False
        return True

    def _split_product_line(self, line: str) -> tuple[str, str]:
        for separator in ("|", ":"):
            if separator not in line:
                continue
            left, right = line.split(separator, 1)
            left = self._clean_text(left)
            right = self._clean_text(right)
            if self._looks_like_row_label(left):
                return left, right
        return "", self._clean_text(line)

    def _has_financial_signal(self, text: str) -> bool:
        normalized = (text or "").casefold()
        return bool(
            any(char.isdigit() for char in text)
            or "%" in text
            or any(
                marker in normalized
                for marker in (
                    "դրամ",
                    "amd",
                    "usd",
                    "eur",
                    "rub",
                    "ամիս",
                    "օր",
                    "տարի",
                    "տոկոս",
                    "եկամտաբեր",
                )
            )
        )

    def _has_structured_fact_signal(self, text: str) -> bool:
        label, _ = self._split_product_line(text)
        if label:
            return True

        normalized = (text or "").casefold()
        fact_markers = (
            "արժույթ",
            "գումար",
            "ժամկետ",
            "տևող",
            "տոկոս",
            "եկամտաբեր",
            "դրամ",
            "dollar",
            "usd",
            "eur",
            "rub",
            "ամիս",
            "տարի",
            "գրավ",
            "ապահով",
            "կանխավճար",
            "մարում",
            "վճար",
            "բոնուս",
            "նպատակ",
        )
        return "%" in text or any(marker in normalized for marker in fact_markers)

    def _is_promotional_detail_line(self, text: str) -> bool:
        normalized = (text or "").casefold()
        promo_markers = (
            "ձևակերպ",
            "ստաց",
            "օգտվ",
            "հարմար",
            "արագ",
            "ավելին",
            "online",
            "digital",
            "տեսնել ավելին",
        )
        if ":" in text or "|" in text:
            return False
        if self._has_structured_fact_signal(text):
            return False
        return any(marker in normalized for marker in promo_markers)

    def _should_drop_product_line(self, line: str, field_name: str) -> bool:
        if not line:
            return True

        normalized = line.casefold()
        label, value = self._split_product_line(line)
        label_normalized = label.casefold()

        if re.search(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", line, flags=re.IGNORECASE):
            return True

        if any(marker in normalized for marker in self.PRODUCT_LINE_DROP_MARKERS):
            return True

        if label and any(marker in label_normalized for marker in self.PRODUCT_LABEL_DROP_MARKERS):
            return True

        if any(marker in normalized for marker in self.PRODUCT_STATUS_MARKERS):
            return True

        if (
            len(line) > 350
            and any(marker in normalized for marker in self.PRODUCT_LEGAL_MARKERS)
        ):
            return True

        if field_name == "rates_table" and self._is_table_header_line(line):
            return True

        if (
            field_name == "details"
            and ":" not in line
            and "|" not in line
            and not any(char.isdigit() for char in line)
            and any(normalized.startswith(prefix) for prefix in self.PRODUCT_PROMO_PREFIXES)
        ):
            return True

        if field_name == "details" and self._is_promotional_detail_line(line):
            return True

        if (
            field_name == "details"
            and len(line) > 180
            and not self._has_financial_signal(line)
            and not any(marker in normalized for marker in self.PRODUCT_KEEP_MARKERS)
        ):
            return True

        if (
            field_name == "details"
            and not label
            and any(char.isdigit() for char in line)
            and not self._has_structured_fact_signal(line)
            and not any(marker in normalized for marker in self.PRODUCT_KEEP_MARKERS)
        ):
            return True

        if (
            field_name == "details"
            and len(line) > 100
            and not self._has_structured_fact_signal(line)
            and not any(marker in normalized for marker in self.PRODUCT_KEEP_MARKERS)
        ):
            return True

        if field_name == "rates_table":
            if label:
                if (
                    not any(marker in label_normalized for marker in self.PRODUCT_KEEP_MARKERS)
                    and not self._has_financial_signal(value)
                ):
                    return True
                if (
                    len(value) > 220
                    and not any(marker in label_normalized for marker in self.PRODUCT_KEEP_MARKERS)
                ):
                    return True
            elif (
                len(line) > 160
                and not self._has_financial_signal(line)
                and not any(marker in normalized for marker in self.PRODUCT_KEEP_MARKERS)
            ):
                return True

        return False

    def _normalize_product_lines(self, lines: list[str], field_name: str) -> list[str]:
        normalized_lines = []
        seen = set()

        for raw_line in lines:
            line = self._strip_product_status(raw_line)
            if self._should_drop_product_line(line, field_name):
                continue

            key = line.casefold()
            if key in seen:
                continue

            seen.add(key)
            normalized_lines.append(line)

        return normalized_lines

    def _normalize_products(self, products: list[dict]) -> list[dict]:
        normalized_products = []
        seen = set()

        for product in products or []:
            product_type = self._strip_product_status(product.get("type", ""))
            parent_type = self._strip_product_status(product.get("parent_type", ""))
            details_lines = self._normalize_product_lines(
                self._split_details_lines(product.get("details", "")),
                field_name="details",
            )
            rates_lines = self._normalize_product_lines(
                self._split_rates_lines(product.get("rates_table", "")),
                field_name="rates_table",
            )

            if rates_lines:
                rate_keys = {line.casefold() for line in rates_lines}
                details_lines = [
                    line
                    for line in details_lines
                    if line.casefold() not in rate_keys
                ]

            if not product_type:
                continue

            normalized_product = {
                "type": product_type,
                "source_url": product.get("source_url", ""),
                "details": " | ".join(details_lines),
                "rates_table": "\n".join(rates_lines),
            }
            if parent_type:
                normalized_product["parent_type"] = parent_type

            key = (
                normalized_product["type"],
                normalized_product.get("parent_type", ""),
                normalized_product["details"],
                normalized_product["rates_table"],
            )
            if key in seen:
                continue

            seen.add(key)
            normalized_products.append(normalized_product)

        return normalized_products

    def _normalize_branch_address(self, address: str) -> str:
        cleaned = self._clean_text(address)
        cleaned = re.sub(r"^\s*\d{4}\s*,\s*", "", cleaned)
        cleaned = re.sub(r"^\s*ՀՀ\s*,?\s*", "", cleaned)
        cleaned = re.sub(r"^\s*\d{4}\s*,\s*", "", cleaned)
        cleaned = re.sub(r"^\s*[^,]+ մարզ,\s*", "", cleaned)
        cleaned = re.sub(r"^\s*համայնք\s+[^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"(^|,\s*)(?:ք|գ|քաղաք|գյուղ)[\.\u2024]?\s*",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r",\s*,+", ", ", cleaned)
        return self._clean_text(cleaned.strip(" ,"))

    def _normalize_branches(self, branches: list[dict]) -> list[dict]:
        """
        Keep branch datasets compact and retrieval-friendly.
        Only preserve the branch name and address in persisted output.
        """
        normalized = []
        seen = set()

        for branch in branches or []:
            name = self._clean_text(branch.get("name", ""))
            address = self._normalize_branch_address(branch.get("address", ""))
            if not name or not address:
                continue

            key = (name, address)
            if key in seen:
                continue

            seen.add(key)
            normalized.append(
                {
                    "name": name,
                    "address": address,
                }
            )

        return normalized

    def scrape_all(self) -> dict:
        print(f"\n{'='*50}")
        print(f"Scraping: {self.bank_name}")
        print(f"{'='*50}")

        self.start()
        try:
            print("  >> Credits...")
            credits = self._normalize_products(self.scrape_credits())
            print(f"     Found {len(credits)} credit product(s)")

            print("  >> Deposits...")
            deposits = self._normalize_products(self.scrape_deposits())
            print(f"     Found {len(deposits)} deposit product(s)")

            print("  >> Branches...")
            branches = self.scrape_branches()
            branches = self._normalize_branches(branches)
            print(f"     Found {len(branches)} branch(es)")
        finally:
            self.stop()

        return {
            "bank": self.bank_name,
            "url": self.base_url,
            "scraped_at": str(date.today()),
            "credits": credits,
            "deposits": deposits,
            "branches": branches,
        }

    def save(self, data: dict, output_dir: str = "data") -> str:
        os.makedirs(output_dir, exist_ok=True)
        file_stem = self.file_stem or self.bank_name.lower().replace(" ", "_")

        self._save_subset(
            output_dir=output_dir,
            subdir="loans",
            filename=f"{file_stem}_loans.json",
            key="credits",
            data=data,
        )
        self._save_subset(
            output_dir=output_dir,
            subdir="deposits",
            filename=f"{file_stem}_deposits.json",
            key="deposits",
            data=data,
        )
        self._save_subset(
            output_dir=output_dir,
            subdir="branches",
            filename=f"{file_stem}_branches.json",
            key="branches",
            data=data,
        )
        return output_dir

    def _save_subset(
        self,
        output_dir: str,
        subdir: str,
        filename: str,
        key: str,
        data: dict,
    ) -> str:
        target_dir = os.path.join(output_dir, subdir)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "bank": self.bank_name,
                    "url": self.base_url,
                    "scraped_at": data.get("scraped_at", ""),
                    key: data.get(key, []),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(f"  >> Saved {key} to {target_path}")
        return target_path
