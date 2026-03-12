import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.crawler import load_config, crawl

if __name__ == "__main__":
    cfg = load_config()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    kw = args[0] if args else "điện thoại"
    load_date = args[1] if len(args) > 1 else None
    demo = "--demo" in sys.argv
    crawl(cfg, kw, load_date, demo=demo)
