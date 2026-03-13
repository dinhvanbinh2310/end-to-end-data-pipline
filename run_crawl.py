import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent / "src" / "scraper-services"))

from tiki_scraper import scrape_tiki

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo = "--demo" in sys.argv

    kw = args[0] if args else "áo thun nam"
    pages = int(args[1]) if len(args) > 1 else (2 if demo else 17)
    output_dir = str(Path(__file__).parent / "data")

    print(f"[*] Keyword: '{kw}' | Pages: {pages} | Demo: {demo}")
    scrape_tiki(kw, pages, output_dir)