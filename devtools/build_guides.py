"""Build the PDF guides in ``docs/pdf/``: user guide, beamline staff guide and the gold-frame report, in English,
Chinese and French.

Each ``docs/<GUIDE>_<lang>.md`` is turned into HTML by pandoc (GitHub flavour,
so the section links work as on GitHub), styled for A4 print and printed to
PDF by headless Chromium through Playwright, with page numbers and a bookmark
outline. Internal links are checked: a link to a missing section stops the
build.

Nothing here is part of the program; run it by hand after editing a guide or
re-taking the screenshots (``devtools/guide_screenshots.py``).

Needs:  pandoc, and ``pip install playwright`` with a Chromium it can use
        (``playwright install chromium``, or set ``CHROMIUM`` to a Chrome or
        Chromium executable).

Usage:  python devtools/build_guides.py [user|staff|gold] [en|zh|fr] ...   (default: all)
"""

from __future__ import annotations

import html
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DOCS = HERE / "docs"
OUT = DOCS / "pdf"

GUIDES = {
    "user": ("USER_GUIDE", "QuickAlignment_user_guide", {
        "en": "QuickAlignment — User Guide",
        "zh": "QuickAlignment 用户指南",
        "fr": "QuickAlignment — Guide de l'utilisateur",
    }),
    "staff": ("STAFF_GUIDE", "QuickAlignment_staff_guide", {
        "en": "QuickAlignment — Beamline Staff Guide",
        "zh": "QuickAlignment 线站人员指南",
        "fr": "QuickAlignment — Guide du personnel de la ligne",
    }),
    "gold": ("GOLD_FRAME_REPORT", "GoldFrame_calibration_report", {
        "en": "Gold-frame calibration — Report",
        "zh": "金框标定 — 报告",
        "fr": "Étalonnage par le cadre en or — Rapport",
    }),
}
HTML_LANG = {"en": "en", "zh": "zh-CN", "fr": "fr"}

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
html { font-family: "DejaVu Sans", "Noto Sans", "Helvetica Neue", Arial,
       "WenQuanYi Zen Hei", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
       font-size: 9.6pt; line-height: 1.5; color: #1d2330; }
body { margin: 0; }
h1 { font-size: 22pt; line-height: 1.2; margin: 0 0 2mm; color: #16365f;
     border-bottom: 2.5px solid #2f6db3; padding-bottom: 3mm; }
h1 + p { color: #50607a; margin-top: 0; }
h2 { font-size: 14.5pt; color: #16365f; margin: 7mm 0 2.5mm;
     border-bottom: 1px solid #c9d6e8; padding-bottom: 1mm; break-after: avoid; }
h3 { font-size: 11.5pt; color: #2f6db3; margin: 5mm 0 2mm; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #2f6db3; text-decoration: none; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.6pt;
       background: #eef2f8; padding: 0.5px 3px; border-radius: 2px; }
pre { background: #f3f6fb; border: 1px solid #d9e2ef; border-radius: 3px;
      padding: 2mm 3mm; break-inside: avoid; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
hr { border: 0; border-top: 1px solid #d9e2ef; margin: 5mm 0; }
img { display: block; max-width: 100%; max-height: 120mm; margin: 2mm auto;
      border: 1px solid #d0d7e2; break-inside: avoid; }
p:has(> img:only-child) { break-inside: avoid; text-align: center; }
table { border-collapse: collapse; width: 100%; margin: 2.5mm 0; font-size: 8.8pt; }
th, td { border: 1px solid #cdd6e3; padding: 1.2mm 2mm; vertical-align: top; text-align: left; }
th { background: #e8eef7; }
tr { break-inside: avoid; }
img.small { max-width: 62%; }
img.tiny { max-width: 38%; }
h2#contents + ol, h2#目录 + ol, h2#sommaire + ol { columns: 2; column-gap: 8mm; }
"""

FOOTER = ("<div style='width:100%;font-size:7.5px;color:#7a8597;font-family:DejaVu Sans,sans-serif;"
          "padding:0 15mm;display:flex;justify-content:space-between'><span>{title}</span>"
          "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")


def _png_width(path: Path) -> int:
    with open(path, "rb") as f:
        return struct.unpack(">II", f.read(24)[16:24])[0]


def _small_images(body: str) -> str:
    """Narrow screenshots (dialogs) are not blown up to the full page width."""
    def mark(match):
        tag, src = match.group(0), match.group(1)
        try:
            width = _png_width(DOCS / src)
        except (OSError, struct.error):
            return tag
        if width >= 1100:
            return tag
        return tag.replace("<img ", f'<img class="{"tiny" if width < 600 else "small"}" ', 1)
    return re.sub(r'<img [^>]*src="(images/[^"]+)"[^>]*>', mark, body)


def to_html(guide: str, lang: str) -> str:
    stem, _, titles = GUIDES[guide]
    source = DOCS / f"{stem}_{lang}.md"
    body = subprocess.run(["pandoc", "-f", "gfm", "-t", "html5", str(source)],
                          check=True, capture_output=True, text=True).stdout
    ids = set(re.findall(r'id="([^"]+)"', body))
    broken = [html.unescape(h) for h in re.findall(r'href="#([^"]+)"', body) if h not in ids]
    if broken:
        raise SystemExit(f"{source.name}: links to missing sections: {broken}")
    missing = [s for s in re.findall(r'src="(images/[^"]+)"', body) if not (DOCS / s).exists()]
    if missing:
        raise SystemExit(f"{source.name}: missing images: {missing}")
    body = _small_images(body).replace('src="images/', 'src="../images/')
    return (f"<!doctype html><html lang='{HTML_LANG[lang]}'><head><meta charset='utf-8'>"
            f"<title>{titles[lang]}</title><style>{CSS}</style></head><body>{body}</body></html>")


def build(guides, langs) -> list[Path]:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    launch = {"executable_path": os.environ["CHROMIUM"]} if os.environ.get("CHROMIUM") else {}
    written = []
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        for guide in guides:
            _, name, titles = GUIDES[guide]
            for lang in langs:
                html_path = OUT / f"_build_{guide}_{lang}.html"  # beside the PDFs: relative image paths resolve
                html_path.write_text(to_html(guide, lang), encoding="utf-8")
                try:
                    page.goto(html_path.as_uri(), wait_until="networkidle")
                    pdf = OUT / f"{name}_{lang}.pdf"
                    page.pdf(path=str(pdf), format="A4", print_background=True, prefer_css_page_size=True,
                             outline=True, tagged=True, display_header_footer=True,
                             header_template="<div></div>", footer_template=FOOTER.format(title=titles[lang]))
                    written.append(pdf)
                finally:
                    html_path.unlink()
        browser.close()
    return written


if __name__ == "__main__":
    args = sys.argv[1:]
    guides = [a for a in args if a in GUIDES] or list(GUIDES)
    langs = [a for a in args if a in HTML_LANG] or list(HTML_LANG)
    for path in build(guides, langs):
        print(path.relative_to(HERE))
