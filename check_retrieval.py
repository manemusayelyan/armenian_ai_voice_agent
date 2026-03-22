import argparse
import sys
from pathlib import Path

from bank_knowledge import (
    build_knowledge_chunks,
    format_retrieved_context,
    load_bank_context,
    retrieve_relevant_chunks,
)


PROJECT_ROOT = Path(__file__).parent
DEFAULT_CONTEXT_PATH = PROJECT_ROOT / "bank_data" / "bank_context.txt"
DEFAULT_DATA_DIR = PROJECT_ROOT / "scraping" / "data"
DEFAULT_QUERIES = [
    "ԱԿԲԱ սպառողական վարկ",
    "Ֆասթ բանկ ավանդներ",
    "Արմէկոնոմբանկ հասցե Երևանում",
    "որ բանկում կա ուսման վարկ",
]


def rebuild_context_from_saved_data() -> None:
    from scraping.scrapers import build_context_string, save_context

    outputs = (
        PROJECT_ROOT / "scraping" / "data" / "bank_context.txt",
        PROJECT_ROOT / "bank_data" / "bank_context.txt",
    )

    context = build_context_string(data_dir=str(DEFAULT_DATA_DIR))
    for output_path in outputs:
        save_context(context, output_path=str(output_path))


def configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="Inspect retrieval snippets for Armenian bank questions."
    )
    parser.add_argument(
        "queries",
        nargs="*",
        help="Questions to test. If omitted, a default sample set is used.",
    )
    parser.add_argument(
        "--context-path",
        default=str(DEFAULT_CONTEXT_PATH),
        help="Path to bank_context.txt",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Maximum retrieved chunks per query.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild bank_context.txt from the saved JSON datasets before testing.",
    )
    args = parser.parse_args()

    if args.rebuild:
        rebuild_context_from_saved_data()

    context_path = Path(args.context_path)
    context = load_bank_context(context_path)
    chunks = build_knowledge_chunks(context)
    queries = args.queries or DEFAULT_QUERIES

    print(f"Context: {context_path}")
    print(f"Chunks: {len(chunks)}")

    for index, query in enumerate(queries, start=1):
        retrieved = retrieve_relevant_chunks(query, chunks, limit=args.limit)
        print("\n" + "=" * 80)
        print(f"Query {index}: {query}")
        print("-" * 80)
        print(format_retrieved_context(query, retrieved))


if __name__ == "__main__":
    main()
