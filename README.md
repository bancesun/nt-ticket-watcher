# README.md
# =============================
"""
NT Ticket Watcher — National Theatre (Aug 16) email alerts

What it does
------------
Checks the National Theatre event page for a specific performance (e.g. Sat 16 August 2025, 7:30 pm). If the status shows a "Book tickets" button (instead of "Sold out"), it sends you an email.

Quick start (local)
-------------------
1) Install Python 3.10+ and Node deps for Playwright runtime.

2) Create a virtualenv and install deps:

   pip install -r requirements.txt
   playwright install --with-deps chromium

3) Set environment variables (example for Gmail w/ app password):

   export TARGET_URL='https://events.nationaltheatre.org.uk/events/92540#_gl=1*1bxvg7u*_gcl_au*NjkwMDY5NzYyLjE3NTM2MzM0NzU.'
   export DATE_TEXT='Sat 16 August 2025'
   export TIME_TEXT='7:30 pm'
   export SMTP_HOST='smtp.gmail.com'
   export SMTP_PORT='587'
   export SMTP_USER='your@gmail.com'
   export SMTP_PASS='your-app-password'
   export EMAIL_FROM='your@gmail.com'
   export EMAIL_TO='you@example.com'

   # optional
   export ALWAYS_NOTIFY='0'

4) Run once:

   python monitor.py

5) Schedule it:
   - Linux/macOS: add a crontab entry to run every 5 minutes:
       */5 * * * * /usr/bin/env -S bash -lc 'cd /path/to/repo && python monitor.py >> watcher.log 2>&1'
   - Or use the provided GitHub Actions workflow.

GitHub Actions setup
--------------------
- Fork or push these files to a private repo.
- In repo Settings → Secrets and variables → Actions, add the env vars above as secrets.
- The workflow runs every 5 minutes and emails you when available.

How the selector works
----------------------
- The script searches the page for the block containing the exact date text (e.g., "Sat 16 August 2025").
- Inside that block it finds the row containing the time (e.g., "7:30 pm").
- If a "Book tickets" button/link is present in that row, status = available. If text includes "Sold out", status = sold out.

Troubleshooting
---------------
- If you get 'unknown: date not found' or 'unknown: time not found', view-source may differ. Update DATE_TEXT/TIME_TEXT to match the site, or increase the Playwright wait (page.wait_for_timeout).
- If email isn't arriving, test SMTP creds with a simple script. Many providers require an app password.
- If the site uses anti-bot measures, consider slowing the browser (page.slowMo), adding a user agent, or running less frequently.

Extending
---------
- Watch multiple times: run check_status for multiple TIME_TEXT values.
- Send to Telegram/Slack/Discord instead of email.
- Persist last-known status to skip duplicate emails.
"""