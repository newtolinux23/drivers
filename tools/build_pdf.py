#!/usr/bin/env python3
"""Build handbook.pdf — a half-letter (5.5 x 8.5 in) booklet — from index.html.

Pass 1 renders the PDF and finds the page each chapter starts on.
Pass 2 writes those page numbers into the table of contents (in the PDF
and in index.html, so browser printing shows them too) and renders again.

Usage:  python3 tools/build_pdf.py            (needs: playwright + Chrome, pypdfium2)
"""
import asyncio
import pathlib
import re
import sys

import pypdfium2 as pdfium
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
OUT = ROOT / "handbook.pdf"
CHROME = "/usr/bin/google-chrome"


def chapter_pages(pdf_path):
    doc = pdfium.PdfDocument(str(pdf_path))
    found = {}
    for i in range(len(doc)):
        text = doc[i].get_textpage().get_text_range().upper()
        for m in re.finditer(r"@@(CH-\d\d)@@", text):
            found.setdefault(m.group(1).lower(), i + 1)
    return found, len(doc)


async def render(page, path):
    await page.emulate_media(media="print")
    await page.evaluate("document.fonts.ready")
    await page.pdf(path=str(path), prefer_css_page_size=True, print_background=True)


async def main():
    tmp = ROOT / ".pass1.pdf"
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(HTML.as_uri(), wait_until="load")
        await page.wait_for_timeout(600)

        await page.evaluate("""() => document.querySelectorAll('.chapter').forEach(c => {
            const m = document.createElement('span'); m.className = 'pdf-marker'; m.textContent = '@@' + c.id + '@@';
            c.querySelector('.ch-head').appendChild(m); })""")
        await render(page, tmp)
        pages, total = chapter_pages(tmp)
        tmp.unlink()
        if len(pages) < 19:
            print("warning: found only", sorted(pages), file=sys.stderr)

        await page.evaluate("() => document.querySelectorAll('.pdf-marker').forEach(m => m.remove())")
        await page.evaluate(
            """(pages) => document.querySelectorAll('.toc-print .p').forEach(s => { s.textContent = pages[s.dataset.for] || ''; })""",
            pages,
        )
        await render(page, OUT)
        await browser.close()

    # Keep the page numbers in the source too, so printing from the browser matches.
    src = HTML.read_text(encoding="utf-8")
    src = re.sub(
        r'(<span class="p" data-for="(ch-\d\d)">)[^<]*(</span>)',
        lambda m: f"{m.group(1)}{pages.get(m.group(2), '')}{m.group(3)}",
        src,
    )
    HTML.write_text(src, encoding="utf-8")
    print(f"wrote {OUT.name}: {total} pages; chapters start at", ", ".join(f"{k[3:]}→{v}" for k, v in sorted(pages.items())))


if __name__ == "__main__":
    asyncio.run(main())
