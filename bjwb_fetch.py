#!/usr/bin/env python3
"""
北京晚报 Fetcher
Downloads all 版面 page images (merged into one PDF) and article text for a given date.

Usage:
    python3 bjwb_fetch.py 20260310
    python3 bjwb_fetch.py 20260310 --output ~/Downloads/bjwb
    python3 bjwb_fetch.py           # defaults to today

Output:
    bjwb_YYYYMMDD/
        bjwb_YYYYMMDD.pdf   all 版面 merged into one PDF
        bjwb_YYYYMMDD.txt   all articles in plain text
"""

import sys
import os
import re
import io
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser


BASE_URL = "https://bjrbdzb.bjd.com.cn/bjwb"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://bjrbdzb.bjd.com.cn/bjwb/",
}


def fetch(url: str, binary: bool = False, encoding: str = "utf-8"):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20) as resp:
            data = resp.read()
            if binary:
                return data
            for enc in (encoding, "gbk", "utf-8", "gb18030"):
                try:
                    return data.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return data.decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"  HTTP {e.code}: {url}")
        return None
    except URLError as e:
        print(f"  URL error ({e.reason}): {url}")
        return None


# ---------------------------------------------------------------------------
# HTML to plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    raw = parser.get_text()
    lines = [ln.rstrip() for ln in raw.splitlines()]
    result = []
    blank = 0
    for ln in lines:
        if ln == "":
            blank += 1
        else:
            blank = 0
        if blank <= 1:
            result.append(ln)
    return "\n".join(result).strip()


# ---------------------------------------------------------------------------
# Parse index page
# ---------------------------------------------------------------------------

def parse_index(html: str, date_str: str) -> List[dict]:
    """
    Parse the mobile index page. Returns list of:
        {
            "page_num": "001",
            "page_title": "头版",
            "img_url": "...",   # full-page thumbnail JPEG
            "articles": [{"title": ..., "url": ..., "id": ...}, ...]
        }
    """
    pages = []

    # Split on each nav-items block boundary
    # Each block starts with <div class="nav-items"> and ends with </div>\n</div>
    # We split by the opening tag and process each chunk
    chunks = re.split(r'<div class="nav-items">', html)

    for chunk in chunks[1:]:  # skip content before first nav-items
        # Page heading + PDF href
        heading_m = re.search(
            r'<div class="nav-panel-heading"\s+pdf_href="([^"]+)">([^<]+)</div>',
            chunk,
        )
        if not heading_m:
            continue
        pdf_rel = heading_m.group(1)   # e.g. ../20260310_001/news-bjwb-00000-...
        page_label = heading_m.group(2).strip()  # e.g. 第1版 头版

        # Extract the page folder name from pdf_rel: ../20260310_001/...
        folder_m = re.search(r'\.\./([\d_]+)/', pdf_rel)
        if not folder_m:
            continue
        folder = folder_m.group(1)     # e.g. 20260310_001
        page_num = folder.split("_")[1]  # e.g. 001

        # Image URL (thumbnail JPEG of full page, same naming as PDF but .jpg)
        img_filename = re.search(r'[^/]+\.pdf', pdf_rel)
        if img_filename:
            img_file = img_filename.group(0).replace(".pdf", ".jpg")
        else:
            img_file = f"news-bjwb-00000-{date_str}-e-{page_num}-300.jpg"

        img_url = (
            f"{BASE_URL}/mobile/{date_str[:4]}/{date_str}/{folder}/{img_file}"
        )

        # Articles
        articles = []
        for art_m in re.finditer(
            r'data-newid="([^"]+)"\s+data-href="([^"]+)">([^<]*)</a>',
            chunk,
        ):
            aid = art_m.group(1)
            rel_href = art_m.group(2)
            title = art_m.group(3).strip()
            if not title:
                continue
            href_clean = rel_href.split("#")[0].lstrip("./")
            art_url = (
                f"{BASE_URL}/mobile/{date_str[:4]}/{date_str}/{href_clean}"
            )
            articles.append({"title": title, "url": art_url, "id": aid})

        pages.append(
            {
                "page_num": page_num,
                "page_title": page_label,
                "img_url": img_url,
                "articles": articles,
            }
        )

    return pages


# ---------------------------------------------------------------------------
# Article text extraction
# ---------------------------------------------------------------------------

def extract_article_text(html: str) -> Tuple[str, str, str, str]:
    """Returns (title, subtitle, author, body_text)."""
    title_m = re.search(r'<font id="main-title"><b>([^<]+)</b>', html)
    subtitle_m = re.search(r'<font id="sub-title">([^<]+)</font>', html)
    author_m = re.search(r'<font id="author">([^<]+)</font>', html)

    title = title_m.group(1).strip() if title_m else ""
    subtitle = subtitle_m.group(1).strip() if subtitle_m else ""
    author = re.sub(r"<[^>]+>", "", author_m.group(1)).strip() if author_m else ""

    body_m = re.search(
        r'<div class="content[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html,
        re.DOTALL,
    )
    body_html = body_m.group(1) if body_m else html
    body = html_to_text(body_html)

    return title, subtitle, author, body


# ---------------------------------------------------------------------------
# PDF generation — fetch all page images and merge into one PDF
# ---------------------------------------------------------------------------

def fetch_page_images(pages: List[dict]) -> List[tuple]:
    """
    Download JPEG for each page. Returns list of (page_info, jpeg_bytes or None).
    Fetches sequentially so progress is visible.
    """
    results = []
    total = len(pages)
    for i, page in enumerate(pages, 1):
        label = f"{page['page_title']} (第{page['page_num']}版)"
        print(f"  [{i}/{total}] {label} ...", end="", flush=True)
        data = fetch(page["img_url"], binary=True)
        if data and data[:2] == b"\xff\xd8":
            print(f" {len(data)//1024} KB")
            results.append((page, data))
        else:
            print(" FAILED")
            results.append((page, None))
        time.sleep(0.3)
    return results


def build_merged_pdf(page_images: List[tuple], dest: Path) -> int:
    """
    Merge all JPEG page images into a single multi-page PDF.
    Returns the number of pages successfully added.
    """
    from PIL import Image
    from fpdf import FPDF

    # Determine a consistent page size from the first valid image
    first_data = next((d for _, d in page_images if d), None)
    if not first_data:
        print("  No page images to merge.")
        return 0

    sample = Image.open(io.BytesIO(first_data))
    w_px, h_px = sample.size
    dpi = 150
    w_pt = w_px / dpi * 72
    h_pt = h_px / dpi * 72

    pdf = FPDF(unit="pt", format=(w_pt, h_pt))

    count = 0
    for page, data in page_images:
        if data is None:
            print(f"  Skipping {page['page_title']} (download failed)")
            continue
        img = Image.open(io.BytesIO(data))
        tmp = io.BytesIO()
        img.save(tmp, format="JPEG", quality=95)
        tmp.seek(0)
        pdf.add_page()
        pdf.image(tmp, x=0, y=0, w=w_pt, h=h_pt)
        count += 1

    pdf.output(str(dest))
    return count


# ---------------------------------------------------------------------------
# Main download logic
# ---------------------------------------------------------------------------

def download_article(article: dict) -> Optional[str]:
    url = article["url"]
    html = fetch(url)
    if not html:
        return None
    title, subtitle, author, body = extract_article_text(html)
    parts = []
    if title:
        parts.append(f"【{title}】")
    if subtitle:
        parts.append(subtitle)
    if author:
        parts.append(f"来源：{author}")
    parts.append("")
    parts.append(body)
    return "\n".join(parts)


def run(date_str: str, output_dir: Optional[str] = None):
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        print(f"Error: invalid date '{date_str}'. Use YYYYMMDD format.")
        sys.exit(1)

    year = date_str[:4]
    out_root = Path(output_dir) if output_dir else Path.cwd() / f"bjwb_{date_str}"
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"\n北京晚报 — {dt.strftime('%Y年%m月%d日')}")
    print(f"Output: {out_root}\n")

    # 1. Fetch index
    index_url = f"{BASE_URL}/mobile/{year}/{date_str}/{date_str}_m.html"
    print(f"Fetching index: {index_url}")
    index_html = fetch(index_url, encoding="gbk")
    if not index_html:
        print("Failed to fetch index page. Check the date or network connection.")
        sys.exit(1)

    pages = parse_index(index_html, date_str)
    if not pages:
        print("No pages found in index. The newspaper may not be published on this date.")
        sys.exit(1)

    print(f"Found {len(pages)} 版面\n")

    # 2. Download all page images and merge into one PDF
    pdf_path = out_root / f"bjwb_{date_str}.pdf"
    if pdf_path.exists():
        print(f"=== PDF already exists, skipping: {pdf_path.name} ===\n")
        page_images = []
    else:
        print(f"=== Downloading {len(pages)} 版面 images ===")
        page_images = fetch_page_images(pages)
        print(f"\nMerging into {pdf_path.name} ...", end="", flush=True)
        n = build_merged_pdf(page_images, pdf_path)
        print(f" {n} pages, {pdf_path.stat().st_size // 1024} KB")

    # 3. Download articles and compile TXT
    print("\n=== Downloading Articles ===")
    txt_lines = [
        f"北京晚报 {dt.strftime('%Y年%m月%d日')}",
        "=" * 60,
        "",
    ]

    total_articles = sum(len(p["articles"]) for p in pages)
    fetched = 0

    for page in pages:
        txt_lines.append(f"\n{'━' * 60}")
        txt_lines.append(f"  {page['page_title']}")
        txt_lines.append(f"{'━' * 60}\n")

        for art in page["articles"]:
            fetched += 1
            print(f"  [{fetched}/{total_articles}] {page['page_title']} | {art['title']}")
            text = download_article(art)
            if text:
                txt_lines.append(text)
                txt_lines.append("\n" + "─" * 40 + "\n")
            time.sleep(0.2)

    # 4. Write TXT
    txt_path = out_root / f"bjwb_{date_str}.txt"
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    print(f"\nArticles saved to: {txt_path}")

    # 5. Summary
    print(f"\n{'=' * 60}")
    print(f"Done!")
    print(f"  PDF:      {pdf_path}")
    print(f"  Articles: {txt_path}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Date range helper
# ---------------------------------------------------------------------------

def date_range(start: str, end: str) -> List[str]:
    """Return list of YYYYMMDD strings from start to end inclusive."""
    from datetime import timedelta
    s = datetime.strptime(start, "%Y%m%d")
    e = datetime.strptime(end, "%Y%m%d")
    if s > e:
        print(f"Error: start date {start} is after end date {end}.")
        sys.exit(1)
    days = []
    cur = s
    while cur <= e:
        days.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return days


def run_range(start: str, end: str, output_dir: Optional[str] = None):
    days = date_range(start, end)
    print(f"\n批量下载：{start} → {end}，共 {len(days)} 天\n")
    failed = []
    for i, date_str in enumerate(days, 1):
        print(f"{'─' * 60}")
        print(f"[{i}/{len(days)}] {date_str}")
        try:
            run(date_str, output_dir)
        except SystemExit:
            failed.append(date_str)
            print(f"  跳过 {date_str}（无法获取或未出版）\n")
    print(f"\n{'=' * 60}")
    print(f"批量完成：{len(days) - len(failed)}/{len(days)} 天成功")
    if failed:
        print(f"  失败/跳过：{', '.join(failed)}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="北京晚报 Fetcher — download page PDFs and all articles for a given date or date range",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 bjwb_fetch.py 20260310
  python3 bjwb_fetch.py 20260310 --output ~/Downloads/bjwb
  python3 bjwb_fetch.py 20260301 20260310
  python3 bjwb_fetch.py 20260301 20260310 --output ~/Downloads/bjwb
  python3 bjwb_fetch.py           # defaults to today
""",
    )
    parser.add_argument(
        "dates",
        nargs="*",
        help="Date in YYYYMMDD format, or two dates for a range (start end). Defaults to today.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory (default: ./bjwb_YYYYMMDD/ per day)",
    )
    args = parser.parse_args()

    if len(args.dates) == 0:
        run(datetime.today().strftime("%Y%m%d"), args.output)
    elif len(args.dates) == 1:
        run(args.dates[0], args.output)
    elif len(args.dates) == 2:
        run_range(args.dates[0], args.dates[1], args.output)
    else:
        parser.error("Provide one date or two dates (start end) for a range.")


if __name__ == "__main__":
    main()
