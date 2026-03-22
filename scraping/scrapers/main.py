"""
Armenian Bank Data Scraper
==========================
Scrapes credits, deposits, and branch data from:
  - Fast Bank       (fastbank.am)
  - ACBA Bank       (acba.am)
  - Armeconombank   (aeb.am)

Uses Selenium (headless Chrome) - handles JS-rendered pages.

Output:
  data/loans/*.json
  data/deposits/*.json
  data/branches/*.json
  data/bank_context.txt   <-- this is what the LLM agent loads

Usage:
  python main.py
  python main.py --bank fast      # run only Fastbank
"""

import sys
from pathlib import Path
from scrapers import (
    FastbankScraper,
    AcbaBankScraper,
    ArmeconombankScraper,
    build_context_string,
    save_context,
)

SCRAPING_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SCRAPING_DIR.parent
DATA_DIR = SCRAPING_DIR / "data"
BANK_CONTEXT_OUTPUTS = (
    DATA_DIR / "bank_context.txt",
    PROJECT_ROOT / "bank_data" / "bank_context.txt",
)

ALL_SCRAPERS = {
    "fast": FastbankScraper(),
    "acba": AcbaBankScraper(),
    "armeconombank": ArmeconombankScraper(),
}


def configure_console_encoding():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def has_scraped_content(data: dict) -> bool:
    return any(data.get(key) for key in ("credits", "deposits", "branches"))


def main():
    configure_console_encoding()

    # Allow running a single bank: python main.py --bank fast
    if "--bank" in sys.argv:
        idx = sys.argv.index("--bank")
        if idx + 1 >= len(sys.argv):
            print("Missing value for '--bank'. Choose from: fast, acba, armeconombank")
            sys.exit(1)
        key = sys.argv[idx + 1].lower()
        if key not in ALL_SCRAPERS:
            print(f"Unknown bank '{key}'. Choose from: {list(ALL_SCRAPERS.keys())}")
            sys.exit(1)
        scrapers = {key: ALL_SCRAPERS[key]}
    else:
        scrapers = ALL_SCRAPERS

    print("\n[START] Armenian Bank Scraper Starting...\n")
    successful_scrapes = 0

    for key, scraper in scrapers.items():
        try:
            data = scraper.scrape_all()
            if not has_scraped_content(data):
                print(
                    f"[WARN] {scraper.bank_name}: scrape returned no products or branches; "
                    "keeping existing saved data."
                )
                continue
            scraper.save(data, output_dir=str(DATA_DIR))
            successful_scrapes += 1
        except Exception as e:
            print(f"[ERROR] Failed scraping {scraper.bank_name}: {e}")

    if successful_scrapes == 0:
        print("\n[WARN] No bank data was scraped, skipping context build.")
        return

    print("\n[BUILD] Building LLM context string...")
    try:
        context = build_context_string(data_dir=str(DATA_DIR))
        for output_path in BANK_CONTEXT_OUTPUTS:
            save_context(context, output_path=str(output_path))
        print("\n[OK] Done! bank_context.txt is ready for the agent.")
    except Exception as e:
        print(f"[ERROR] Failed building context: {e}")


if __name__ == "__main__":
    main()
