# monitor.py — ONLY checks DATE_TEXT (whole day). Any visible "Book" in that date's region => available.
import os, re, smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

# -------- Config via environment --------
TARGET_URL    = os.getenv("TARGET_URL", "https://events.nationaltheatre.org.uk/events/92540")
DATE_TEXT     = os.getenv("DATE_TEXT", "Sat 16 August 2025")   # only this date; no TIME_TEXT needed
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
EMAIL_FROM    = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_TO      = os.getenv("EMAIL_TO", "")
ALWAYS_NOTIFY = os.getenv("ALWAYS_NOTIFY", "0") == "1"
ARTIFACT_DIR  = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# -------- Email --------
def send_email(subject: str, body: str) -> None:
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and EMAIL_TO):
        print("[WARN] Email not configured. Skipping send.\n" + body)
        return
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg["Date"]    = formatdate(localtime=True)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, [e.strip() for e in EMAIL_TO.split(",") if e.strip()], msg.as_string())

# -------- Helpers --------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _date_candidates(date_text: str):
    """Generate robust variants: 'Sat 16 August 2025' -> '16 August 2025', 'Sat 16 Aug 2025', etc."""
    s = date_text.strip()
    cands = [s]
    # strip weekday
    m = re.search(r"\d", s)
    if m:
        cands.append(s[m.start():])
    # month short form
    months = {"January":"Jan","February":"Feb","March":"Mar","April":"Apr","May":"May","June":"Jun",
              "July":"Jul","August":"Aug","September":"Sep","October":"Oct","November":"Nov","December":"Dec"}
    for full, short in months.items():
        if full in s:
            cands.append(s.replace(full, short))
            if m:
                cands.append(s[m.start():].replace(full, short))
            break
    # weekday full/short swap
    weekdays = {"Monday":"Mon","Tuesday":"Tue","Wednesday":"Wed","Thursday":"Thu","Friday":"Fri","Saturday":"Sat","Sunday":"Sun"}
    for full, short in weekdays.items():
        if s.startswith(full + " "):
            cands.append(s.replace(full + " ", short + " ", 1)); break
        if s.startswith(short + " "):
            cands.append(s.replace(short + " ", full + " ", 1)); break
    # dedupe
    seen, out = set(), []
    for x in cands:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def _accept_banners_and_expand(page):
    # Cookie/consent
    for pat in [r"Accept", r"Agree", r"OK", r"I understand"]:
        try:
            btn = page.get_by_role("button", name=re.compile(pat, re.I))
            if btn.is_visible():
                btn.click(); page.wait_for_timeout(300); break
        except Exception:
            pass
    # Show more
    for pat in [r"Show all", r"Show more", r"Load more", r"See more", r"More dates", r"Show.*performances"]:
        try:
            btn = page.get_by_role("button", name=re.compile(pat, re.I))
            if btn.is_visible():
                btn.click(); page.wait_for_timeout(500)
        except Exception:
            pass
    # Wait & force lazy content
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(600)

def _any_visible(locator, max_scan: int = 60) -> bool:
    """Return True if any of the first N matches are visible (avoids strict-mode)."""
    try:
        n = min(locator.count(), max_scan)
    except Exception:
        n = 0
    for i in range(n):
        try:
            if locator.nth(i).is_visible():
                return True
        except Exception:
            pass
    return False

def _find_date_region(page, date_text: str):
    """
    Find a robust 'region' (section/div) that represents ONLY the requested date.
    Strategy:
      1) Try a real heading (role=heading, exact or contains).
         If found, take its nearest ancestor <section>/<div> as the region.
      2) Else, find a node that contains the date text, then take its nearest ancestor section/div.
    """
    for cand in _date_candidates(date_text):
        # 1) Prefer headings
        h_exact = page.get_by_role("heading", name=re.compile(rf"^{re.escape(cand)}$", re.I))
        if h_exact.count() > 0 and h_exact.first.is_visible():
            region = h_exact.first.locator("xpath=ancestor::*[self::section or self::div][1]")
            if region.count() > 0:
                return region
        h_contains = page.get_by_role("heading", name=re.compile(re.escape(cand), re.I))
        if h_contains.count() > 0 and h_contains.first.is_visible():
            region = h_contains.first.locator("xpath=ancestor::*[self::section or self::div][1]")
            if region.count() > 0:
                return region

        # 2) Generic text match → nearest meaningful container
        node = page.get_by_text(re.compile(re.escape(cand), re.I)).first
        try:
            node_found = (node.count() > 0 and node.is_visible())
        except Exception:
            node_found = False
        if node_found:
            region = node.locator("xpath=ancestor::*[self::section or self::div][1]")
            if region.count() > 0:
                return region
    return None

def _status_from_region(region) -> str:
    # Any visible "Book" inside region -> available
    book_btns  = region.get_by_role("button", name=re.compile(r"Book\s*(tickets|now)?", re.I))
    book_links = region.locator("a:has-text('Book tickets'), a:has-text('Book now')")
    if _any_visible(book_btns) or _any_visible(book_links):
        return "available"

    # Any visible 'Sold out' inside region (and no Book) -> sold out
    sold = region.get_by_text(re.compile(r"\bSold\s*out\b", re.I))
    if _any_visible(sold):
        return "sold out"

    return "unknown"

def _save_artifacts(page, tag: str):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    page.screenshot(path=str(ARTIFACT_DIR / f"{tag}_{ts}.png"), full_page=True)
    with open(ARTIFACT_DIR / f"{tag}_{ts}.html", "w", encoding="utf-8") as f:
        f.write(page.content())

# -------- Main --------
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(TARGET_URL, wait_until="domcontentloaded")

        _accept_banners_and_expand(page)

        region = _find_date_region(page, DATE_TEXT)
        if not region:
            status = "unknown: date region not found"
            _save_artifacts(page, "date_region_not_found")
        else:
            status = _status_from_region(region)
            if status == "unknown":
                _save_artifacts(page, "unknown_status")

        ctx.close(); browser.close()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{now}] {DATE_TEXT}: {status}")

    if status == "available" or (ALWAYS_NOTIFY and status != "unknown"):
        subject = f"NT tickets {status.upper()}: {DATE_TEXT}"
        body = f"Status: {status}\nURL: {TARGET_URL}\nUTC: {now}\n"
        send_email(subject, body)

if __name__ == "__main__":
    main()
