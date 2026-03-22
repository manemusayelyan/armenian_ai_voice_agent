from .base_scraper import BaseBankScraper


class PendingBankScraper(BaseBankScraper):
    """Starter scraper used until bank-specific extraction rules are added."""

    file_stem: str = ""

    def start(self) -> None:
        print(f"  [skip] {self.bank_name} does not need a browser until implemented.")
        self.driver = None

    def stop(self) -> None:
        self.driver = None

    def scrape_credits(self) -> list[dict]:
        return self._empty_result("credit")

    def scrape_deposits(self) -> list[dict]:
        return self._empty_result("deposit")

    def scrape_branches(self) -> list[dict]:
        return self._empty_result("branch")

    def _empty_result(self, dataset_name: str) -> list[dict]:
        print(
            f"  [todo] {self.bank_name} {dataset_name} scraping rules are not implemented yet."
        )
        return []
