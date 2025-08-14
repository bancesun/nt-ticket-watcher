# monitor.py — 只检查 DATE_TEXT 那一天；任意一场可见"Book"才算可订
import os, re, smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

# -------- 环境变量配置 --------
TARGET_URL    = os.getenv("TARGET_URL", "https://events.nationaltheatre.org.uk/events/92540")
DATE_TEXT     = os.getenv("DATE_TEXT", "Sat 16 August 2025")   # 只看这一天（不需要 TIME_TEXT）
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
EMAIL_FROM    = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_TO      = os.getenv("EMAIL_TO", "")
ALWAYS_NOTIFY = os.getenv("ALWAYS_NOTIFY", "0") == "1"
ARTIFACT_DIR  = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# -------- 发送邮件 --------
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

# --------
