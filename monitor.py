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

# -------- 工具函数 --------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _date_candidates(date_text: str):
    """为 heading 匹配生成一些等价写法（Sat 16 August 2025 / 16 August 2025 / 16 Aug 2025 等）。"""
    s = date_text.strip()
    cands = [s]
    # 去掉星期前缀
    m = re.search(r"\d", s)
    if m:
        cands.append(s[m.start():])
    # 月份全名/缩写
    months = {"January":"Jan","February":"Feb","March":"Mar","April":"Apr","May":"May","June":"Jun",
              "July":"Jul","August":"Aug","September":"Sep","October":"Oct","November":"Nov","December":"Dec"}
    for full, short in months.items():
        if full in s:
            cands.append(s.replace(full, short))
            if m:
                cands.append(s[m.start():].replace(full, short))
            break
    # 星期全称/简称互换
    weekdays = {"Monday":"Mon","Tuesday":"Tue","Wednesday":"Wed","Thursday":"Thu","Friday":"Fri","Saturday":"Sat","Sunday":"Sun"}
    for full, short in weekdays.items():
        if s.startswith(full + " "):
            cands.append(s.replace(full + " ", short + " ", 1)); break
        if s.startswith(short + " "):
            cands.append(s.replace(short + " ", full + " ", 1)); break
    # 去重保序
    seen, out = set(), []
    for x in cands:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def _accept_banners_and_expand(page):
    # 接 Cookie/Consent
    for pat in [r"Accept", r"Agree", r"OK", r"I understand"]:
        try:
            btn = page.get_by_role("button", name=re.compile(pat, re.I))
            if btn.is_visible():
                btn.click(); page.wait_for_timeout(300); break
        except Exception:
            pass
    # 展开"更多场次"
    for pat in [r"Show all", r"Show more", r"Load more", r"See more", r"More dates", r"Show.*performances"]:
        try:
            btn = page.get_by_role("button", name=re.compile(pat, re.I))
            if btn.is_visible():
                btn.click(); page.wait_for_timeout(500)
        except Exception:
            pass
    # 等待 & 下拉触发懒加载
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(600)

def _find_date_heading(page, date_text: str):
    """优先精确匹配"日期标题"（ARIA role=heading），避免误选包住多天的大容器。"""
    for cand in _date_candidates(date_text):
        # 优先整行匹配（^...$），失败再放宽为包含匹配
        h_exact = page.get_by_role("heading", name=re.compile(rf"^{re.escape(cand)}$", re.I))
        if h_exact.count() > 0 and h_exact.first.is_visible():
            return h_exact.first
        h_contains = page.get_by_role("heading", name=re.compile(re.escape(cand), re.I))
        if h_contains.count() > 0 and h_contains.first.is_visible():
            return h_contains.first
    return None

def _nearest_list_after_heading(heading):
    """
    从该日期的 heading 出发，选取"紧邻的、承载场次按钮的容器"。
    只看 heading 之后第一个包含按钮/链接的兄弟容器，避免跨到下一天。
    """
    # 选取最近的后续兄弟元素（div/section/ul/ol）里含有按钮或链接的那个
    loc = heading.locator(
        "xpath=following-sibling::*[self::div or self::section or self::ul or self::ol]"
        "[.//button or .//a][1]"
    )
    return loc if loc.count() > 0 else None

def _any_visible(locator, max_scan: int = 50) -> bool:
    """避免 Playwright 严格模式报错：逐个 nth(i).is_visible() 检测。"""
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

def _status_from_list_area(list_area) -> str:
    # 只在该日期的"场次容器"中判定
    book_btns  = list_area.get_by_role("button", name=re.compile(r"Book\s*(tickets|now)?", re.I))
    book_links = list_area.locator("a:has-text('Book tickets'), a:has-text('Book now')")
    if _any_visible(book_btns) or _any_visible(book_links):
        return "available"

    sold = list_area.get_by_text(re.compile(r"\bSold\s*out\b", re.I))
    if _any_visible(sold):
        return "sold out"

    return "unknown"

def _save_artifacts(page, tag: str):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    page.screenshot(path=str(ARTIFACT_DIR / f"{tag}_{ts}.png"), full_page=True)
    with open(ARTIFACT_DIR / f"{tag}_{ts}.html", "w", encoding="utf-8") as f:
        f.write(page.content())

# -------- 主流程 --------
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(TARGET_URL, wait_until="domcontentloaded")

        _accept_banners_and_expand(page)

        heading = _find_date_heading(page, DATE_TEXT)
        if not heading:
            status = "unknown: date heading not found"
            _save_artifacts(page, "date_heading_not_found")
        else:
            list_area = _nearest_list_after_heading(heading)
            if not list_area:
                status = "unknown: list area not found"
                _save_artifacts(page, "list_area_not_found")
            else:
                status = _status_from_list_area(list_area)
                if status == "unknown":
                    _save_artifacts(page, "unknown_status")

        ctx.close(); browser.close()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{now}] {DATE_TEXT}: {status}")

    # 默认只在 available 时发邮件；设置 ALWAYS_NOTIFY=1 则在 sold out 时也发
    if status == "available" or (ALWAYS_NOTIFY and status != "unknown"):
        subject = f"NT tickets {status.upper()}: {DATE_TEXT}"
        body = f"Status: {status}\nURL: {TARGET_URL}\nUTC: {now}\n"
        send_email(subject, body)

if __name__ == "__main__":
    main()
