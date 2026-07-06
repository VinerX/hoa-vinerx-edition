#!/usr/bin/env python3
"""
scrape.py — download Warcraft character/topic art from warcraft.wiki.gg.

Uses the MediaWiki API (legal, stable, no HTML scraping). For each name it
grabs the page's lead image at original resolution. Feed the results straight
into convert.py.

Usage:
    python scrape.py "Anduin Wrynn" "Jaina Proudmoore" --out raw/
    python scrape.py --file names.txt --out raw/          # one name per line
    python scrape.py "Genn Greymane" --all --out raw/     # every image on page

Then:
    python convert.py leader raw/ --out out/leaders

Notes:
- Default grabs only the single lead (infobox) image per page — usually the
  clean character portrait. Use --all to pull every image on the page and pick
  by hand (good for fan art / alt poses).
- Files land in <out>/ named after the wiki file. Nothing is auto-cropped;
  convert.py does the resizing.
- Respect the wiki: this sends a descriptive User-Agent and sleeps between
  requests. Downloaded art belongs to Blizzard/its artists — personal mod use.
"""
import argparse
import os
import sys
import time
from urllib.parse import unquote

import requests

API = "https://warcraft.wiki.gg/api.php"
UA = "HOA-portrait-pipeline/1.0 (personal HOI4 mod tooling; contact vinerx2000@gmail.com)"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


def api(params):
    params = {**params, "format": "json"}
    r = SESSION.get(API, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_title(name):
    """Return the best-matching page title, or None."""
    j = api({"action": "query", "list": "search", "srsearch": name,
             "srlimit": 1, "srnamespace": 0})
    hits = j.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def lead_image_url(title):
    """Original-resolution URL of the page's lead (infobox) image."""
    j = api({"action": "query", "titles": title, "prop": "pageimages",
             "piprop": "original"})
    pages = j.get("query", {}).get("pages", {})
    for p in pages.values():
        orig = p.get("original")
        if orig:
            return orig["source"]
    return None


def all_image_urls(title):
    """URLs of every image used on the page (skips ui/icon clutter)."""
    j = api({"action": "query", "titles": title, "prop": "images",
             "imlimit": 50})
    pages = j.get("query", {}).get("pages", {})
    titles = []
    for p in pages.values():
        for im in p.get("images", []):
            t = im["title"]
            low = t.lower()
            if any(k in low for k in ("icon", "logo", "ability_", "inv_",
                                      "achievement", ".svg", "ui-", "spell_")):
                continue
            titles.append(t)
    if not titles:
        return []
    urls = []
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        j = api({"action": "query", "titles": "|".join(chunk),
                 "prop": "imageinfo", "iiprop": "url"})
        for p in j.get("query", {}).get("pages", {}).values():
            info = p.get("imageinfo")
            if info:
                urls.append(info[0]["url"])
    return urls


def download(url, out_dir):
    fn = unquote(url.split("/")[-1].split("?")[0])
    dst = os.path.join(out_dir, fn)
    r = SESSION.get(url, timeout=60)
    r.raise_for_status()
    with open(dst, "wb") as f:
        f.write(r.content)
    return dst


def main():
    ap = argparse.ArgumentParser(description="Scrape Warcraft art from warcraft.wiki.gg")
    ap.add_argument("names", nargs="*", help="character/topic names")
    ap.add_argument("--file", help="text file, one name per line")
    ap.add_argument("--out", default="raw", help="output dir (default: raw)")
    ap.add_argument("--all", action="store_true",
                    help="download every image on the page, not just the lead")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between pages")
    args = ap.parse_args()

    names = list(args.names)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            names += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not names:
        sys.exit("give at least one name, or --file names.txt")

    os.makedirs(args.out, exist_ok=True)
    got = 0
    for name in names:
        try:
            title = resolve_title(name)
            if not title:
                print(f"  ?? no page for '{name}'", file=sys.stderr)
                continue
            urls = all_image_urls(title) if args.all else [lead_image_url(title)]
            urls = [u for u in urls if u]
            if not urls:
                print(f"  ?? no image on '{title}'", file=sys.stderr)
                continue
            for u in urls:
                dst = download(u, args.out)
                print(f"  {name}  [{title}]  ->  {os.path.basename(dst)}")
                got += 1
        except Exception as e:
            print(f"  !! {name}: {e}", file=sys.stderr)
        time.sleep(args.delay)

    print(f"\nDone: {got} image(s) -> {args.out}")


if __name__ == "__main__":
    main()
