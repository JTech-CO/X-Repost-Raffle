from __future__ import annotations
import os, time, argparse, json
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

COMMON_BINARIES = [
    os.getenv("CHROME_BIN"),
    os.getenv("GOOGLE_CHROME_BIN"),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
]

def _find_chrome() -> str | None:
    for p in COMMON_BINARIES:
        if p and os.path.exists(p):
            return p
    return None

def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,1100")
    opts.add_argument("--lang=en-US,en,ko-KR,ko")
    
    # 보기 전용 크롤링
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    binpath = _find_chrome()
    if binpath: opts.binary_location = binpath
    return webdriver.Chrome(service=ChromeService(), options=opts)

def _wait_retweets_timeline(driver: webdriver.Chrome) -> None:
    
    # 타임라인/유저셀 등장까지 대기
    w = WebDriverWait(driver, 25)
    try:
        w.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR,
             '[aria-label*="Retweets"],[aria-label*="리포스트"],[role="region"] [data-testid="UserCell"], main [data-testid="UserCell"]')
        ))
    except Exception:
        # 페이지 전환/리디렉션 대기
        time.sleep(2)

def _collect_users_from_page(driver: webdriver.Chrome, max_scroll=60, pause=0.7) -> List[Dict]:
    users: List[Dict] = []
    seen = set()
    last_len = -1
    stable = 0

    for _ in range(max_scroll):
        cells = driver.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
        for c in cells:
            try:
                # 핸들
                handle = ""
                for a in c.find_elements(By.CSS_SELECTOR, 'a[href^="/"]'):
                    href = a.get_attribute("href") or ""
                    if "x.com/" in href and "/status/" not in href and "/i/" not in href:
                        handle = href.split("x.com/")[-1].strip("/")
                        break
                if not handle:
                    continue

                nickname = ""
                try:
                    nickname = c.find_element(By.CSS_SELECTOR, 'div[dir="ltr"] span').text
                except Exception:
                    nickname = (c.text or "").split("\n")[0]
                desc = ""
                try:
                    desc = c.find_element(By.CSS_SELECTOR, 'div[dir="auto"][lang]').text
                except Exception:
                    pass

                follow_status = "팔로우"

                if handle not in seen:
                    users.append({
                        "nickname": nickname,
                        "handle": handle.replace("@", ""),
                        "followStatus": follow_status,
                        "description": desc
                    })
                    seen.add(handle)
            except Exception:
                pass

        # 스크롤 다운
        driver.execute_script("window.scrollBy(0, document.documentElement.clientHeight);")
        time.sleep(pause)

        if len(users) == last_len:
            stable += 1
            if stable >= 3: break
        else:
            last_len = len(users); stable = 0

    return users

def collect_retweeters(tweet_url: str, headless: bool = True,
                       max_scroll: int = 60, pause: float = 0.7) -> List[Dict]:
    """로그인 없이 /retweets 페이지를 열어 재게시자 수집"""
    # 트윗 URL 정규화
    u = tweet_url.strip()
    if not u:
        return []
    if not u.startswith("http"):
        u = "https://" + u
    if not u.endswith("/retweets"):
        u = u.rstrip("/") + "/retweets"

    driver = make_driver(headless=headless)
    try:
        driver.get(u)
        _wait_retweets_timeline(driver)
        users = _collect_users_from_page(driver, max_scroll=max_scroll, pause=pause)
        return users
    finally:
        driver.quit()

# --- CLI ---
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="data/retweeters.json")
    ap.add_argument("--headless", default="true", choices=["true","false"])
    ap.add_argument("--max-scroll", type=int, default=60)
    ap.add_argument("--pause", type=float, default=0.7)
    args = ap.parse_args()
    users = collect_retweeters(args.url, headless=(args.headless=="true"),
                               max_scroll=args.max_scroll, pause=args.pause)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"users": users, "count": len(users)}, f, ensure_ascii=False, indent=2)
    print(f"[OK] saved {len(users)} users → {args.out}")
