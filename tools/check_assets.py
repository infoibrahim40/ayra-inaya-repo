"""Shows which asset images are still missing. Usage: python tools/check_assets.py [characters|locations|props|style]"""
import csv, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
only = sys.argv[1] if len(sys.argv) > 1 else None
have = missing = 0
miss_by = {}
big = []
for r in csv.DictReader(open(ROOT / "assets" / "MANIFEST.csv", encoding="utf-8-sig")):
    if only and r["folder"] != only:
        continue
    p = ROOT / "assets" / r["folder"] / r["filename"]
    if p.exists():
        have += 1
        if p.stat().st_size > 3 * 1024 * 1024:
            big.append(f"{r['folder']}/{r['filename']} ({p.stat().st_size // 1024 // 1024} MB)")
    else:
        missing += 1
        miss_by.setdefault(r["folder"], []).append(r["filename"])
print(f"Have {have}, missing {missing}")
for fo, items in miss_by.items():
    print(f"\n[{fo}] missing {len(items)}")
    for fn in items[:40]:
        print("  -", fn)
    if len(items) > 40:
        print(f"  ... and {len(items) - 40} more")
if big:
    print("\nLarge files (consider shrinking below 2 MB):", *big, sep="\n  - ")
