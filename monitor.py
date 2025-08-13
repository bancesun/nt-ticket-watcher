import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from playwright.sync_api import sync_playwright
from datetime import datetime
import re

TARGET_URL = os.getenv(
    "TARGET_URL",
    "https://events.nationaltheatre.org.uk/events/92540#_gl=1*1bxvg7u*_gcl_au*NjkwMDY5NzYyLjE3NTM2MzM0NzU."
)
DATE_TEXT = os.getenv("DATE_TEXT", "Sat 16 August 2025")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_TO = os.getenv("EMAIL_TO")
ALWAYS_NOTIFY = os.getenv("ALWAYS_NOTIFY", "0") == "1"


def send_email(subject: str, body: str):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and EMAIL_TO):
        print("[WARN] Email not configured. Skipping send.\n" + body)
        return
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Date"] = formatdate(localtime=True)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, EMAIL_TO.split(","), msg.as_string())


def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def check_status(page) -> str:
    # Find the container for the given date
    date_block = page.locator(f"section:has-text('{DATE_TEXT}'), div:has-text('{DATE_TEXT}')").first
    if date_block.count() == 0:
        return "unknown: date not found"

    # Within that date block, find any performance rows
    rows = date_block.locator("li, div").all()
    for row in rows:
        if row.get_by_text(re.compile(r"Sold\\s*out", re.I)).is_visible():
            continue
        if row.get_by_role("button", name=re.compile(r"Book", re.I)).is_visible() \
           or row.locator("a:has-text('Book')").first.is_visible():
            return "available"
    return "sold out"


def fetch_and_check() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        status = check_status(page)
        context.close()
        browser.close()
        return status


def main():
    status = fetch_and_check()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{now}] {DATE_TEXT}: {status}")
    if status == "available" or (ALWAYS_NOTIFY and status != "unknown"):
        subject = f"NT tickets {status.upper()}: {DATE_TEXT}"
        body = f"The slot appears to be {status} for {DATE_TEXT}.\n\nURL: {TARGET_URL}\nTime (UTC): {now}\n"
        send_email(subject, body)


if __name__ == "__main__":
    main()
