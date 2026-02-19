import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE_URL = "https://afj.org"
# All nominees
NOMINEES_URL = "https://afj.org/nominees/"
OUTPUT_DIR = Path("candidates")
# Trump 1
# NOMINEES_URL = "https://afj.org/nominees/?court=8&administration=525"
# OUTPUT_DIR = Path("candidates-trump1")
# Trump 2
# NOMINEES_URL = "https://afj.org/nominees/?court=8&administration=527"
# OUTPUT_DIR = Path("candidates-trump2")


def slugify_name(url: str) -> str:
    """Extract the nominee slug from their profile URL, e.g. 'katie-lane'."""
    # URL is like https://afj.org/nominee/katie-lane/
    match = re.search(r"/nominee/([^/]+)/?$", url)
    if match:
        return match.group(1)
    # fallback: use last non-empty path segment
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else "unknown"


def html_to_text(html: str) -> str:
    """Convert the body1 div HTML to clean plain text."""
    soup = BeautifulSoup(html, "html.parser")
    lines = []

    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            continue
        tag_name = tag.name.lower()
        if tag_name.startswith("h"):
            # section header — no indentation, preceded by a blank line
            if lines:
                lines.append("")
            lines.append(text)
        else:
            lines.append(text)
        lines.append("")  # blank line after each block

    # strip trailing blank lines
    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines)


def collect_all_nominee_links(page) -> list[str]:
    """Load the nominees listing page, clicking 'Load More' until exhausted,
    then return all unique nominee profile URLs."""
    print(f"Navigating to {NOMINEES_URL}")
    page.goto(NOMINEES_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    links: set[str] = set()

    while True:
        # collect current card links
        anchors = page.query_selector_all("a.overlink1.card8-link")
        for anchor in anchors:
            href = anchor.get_attribute("href")
            if href:
                full = href if href.startswith("http") else BASE_URL + href
                links.add(full)

        print(f"  Found {len(links)} nominee links so far...")

        # look for "Load More" button
        load_more = page.query_selector("a[more]")
        if not load_more:
            print("  No 'Load More' button found — all nominees loaded.")
            break

        # check it's visible
        if not load_more.is_visible():
            print("  'Load More' button not visible — done.")
            break

        print("  Clicking 'Load More'...")
        load_more.click()
        # wait for new cards to appear (network + render)
        page.wait_for_timeout(2500)

    return sorted(links)


def scrape_nominee(page, url: str) -> str | None:
    """Visit a nominee profile URL and return the extracted plain text, or None on failure."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        # the content div has classes: body1 -contain -xw:5
        # use a broad selector and narrow by first matching class
        el = page.query_selector("div.body1")
        if not el:
            print(f"    WARNING: Could not find .body1 div on {url}")
            return None

        html = el.inner_html()
        return html_to_text(html)

    except Exception as e:
        print(f"    ERROR scraping {url}: {e}")
        return None


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        all_links = collect_all_nominee_links(page)
        print(f"\nTotal nominees to scrape: {len(all_links)}\n")
        for i, url in enumerate(all_links, 1):
            slug = slugify_name(url)
            out_path = OUTPUT_DIR / f"{slug}.txt"

            if out_path.exists():
                print(f"[{i}/{len(all_links)}] Skipping {slug} (already saved)")
                continue

            print(f"[{i}/{len(all_links)}] Scraping: {url}")
            text = scrape_nominee(page, url)

            if text:
                out_path.write_text(text, encoding="utf-8")
                print(f"    Saved → {out_path}")
            else:
                print(f"    No content saved for {slug}")
            time.sleep(0.5)

        browser.close()

    print(f"\nDone. Files saved in ./{OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
