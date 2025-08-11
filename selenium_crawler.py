# selenium_crawler.py
"""
X(트위터) 게시물의 'Reposts(리포스트/재게시)' 명단을 수집해 JSON으로 저장.
- 로컬/서버/CI(GitHub Actions) 공통 사용
- 크롬 바이너리 자동탐색(CHROME_BIN/GOOGLE_CHROME_BIN 또는 일반 경로)
- Selenium Manager로 드라이버 자동 해결
- CLI 지원: --url, --out, --headless, --max-scroll, --pause

Env (선택): X_USERNAME, X_PASSWORD  # 로그인 필요할 때만 설정
"""

from __future__ import annotations
import os, sys, json, time, argparse
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ========== Chrome binary & driver ==========
COMMON_BINARIES = [
    os.getenv("CHROME_BIN"),
    os.getenv("GOOGLE_CHROME_BIN"),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
]

def find_chrome_binary() -> Optional[str]:
    for path in COMMON_BINARIES:
        if path and os.path.exists(path):
            return path
    return None

def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        # 최신 크롬 헤드리스
        opts.add_argument("--headless=new")
    # CI/컨테이너에서 필수 안정 플래그
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=ko-KR,ko,en-US,en")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    chrome_bin = find_chrome_binary()
    if chrome_bin:
        opts.binary_location = chrome_bin

    # Selenium Manager 드라이버 자동 다운로드
    service = ChromeService()
    driver = webdriver.Chrome(service=service, options=opts)

    # webdriver 탐지 회피
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"}
        )
    except Exception:
        pass
    return driver


# ========== Login & navigation ==========
def login_x(driver: webdriver.Chrome, username: Optional[str], password: Optional[str]):
    if not username or not password:
        return
    w = WebDriverWait(driver, 25)
    driver.get("https://x.com/i/flow/login")

    # 1) 사용자명/이메일
    user_input = w.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
    user_input.clear(); user_input.send_keys(username); user_input.send_keys(Keys.ENTER)

    # 2) 비밀번호
    time.sleep(1.0)
    try:
        pwd = w.until(EC.presence_of_element_located((By.NAME, "password")))
        pwd.clear(); pwd.send_keys(password); pwd.send_keys(Keys.ENTER)
    except Exception:
        # input이 여러 개인 페이지 케이스
        inputs = driver.find_elements(By.TAG_NAME, "input")
        if inputs:
            inputs[-1].clear(); inputs[-1].send_keys(password); inputs[-1].send_keys(Keys.ENTER)

    # 홈 탭 로딩 대기
    w.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="AppTabBar_Home_Link"]')))


def open_retweeters_modal(driver: webdriver.Chrome):
    """트윗 상세 페이지에서 Reposts(리포스트/재게시) 목록 모달을 엽니다."""
    w = WebDriverWait(driver, 20)

    # 1) 눈에 보이는 텍스트 후보
    candidates = driver.find_elements(By.CSS_SELECTOR, 'a[role="link"], div[role="button"], span')
    target = None
    for el in candidates:
        try:
            txt = (el.text or "").strip().lower()
            if txt in ("reposts", "리포스트", "재게시"):
                target = el; break
        except Exception:
            pass

    # 2) 아이콘/카운트 버튼
    if not target:
        # retweet 아이콘 버튼 → 근처 링크 클릭
        for el in driver.find_elements(By.CSS_SELECTOR, '[data-testid="retweet"]'):
            target = el; break

    if not target:
        raise RuntimeError("Reposts button not found (UI may have changed).")

    driver.execute_script("arguments[0].click();", target)

    # 모달 컨테이너 대기
    w.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[role="dialog"]')))
    container = w.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, '[role="dialog"] [data-testid="sheetDialog"], [role="dialog"] div[aria-modal="true"]')
    ))
    return container


def scroll_collect_users(driver: webdriver.Chrome, container, max_scroll=50, pause=0.7) -> List[Dict]:
    """Repost 사용자 셀들을 스크롤하면서 수집"""
    users: List[Dict] = []
    seen = set()
    last_count = -1
    stable_ticks = 0

    for _ in range(max_scroll):
        cells = container.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
        for c in cells:
            try:
                # 핸들(@...), 닉네임, 설명, 팔로우 상태
                handle = ""
                # 기본: 링크에서 추출
                for a in c.find_elements(By.CSS_SELECTOR, 'a[href^="/"]'):
                    href = a.get_attribute("href") or ""
                    if "x.com/" in href and "/status/" not in href and "/i/" not in href:
                        handle = href.split("x.com/")[-1].strip("/")
                        break

                nickname = ""
                try:
                    nickname = c.find_element(By.CSS_SELECTOR, 'div[dir="ltr"] span').text
                except Exception:
                    # fallback
                    nickname = (c.text or "").split("\n")[0]

                desc = ""
                try:
                    desc = c.find_element(By.CSS_SELECTOR, 'div[dir="auto"][lang]').text
                except Exception:
                    pass

                follow_status = "팔로우"
                try:
                    btn_txt = c.find_element(By.CSS_SELECTOR, '[data-testid$="follow"], [data-testid$="unfollow"]').text
                    if ("Following" in btn_txt) or ("언팔로우" in btn_txt):
                        follow_status = "팔로잉"
                except Exception:
                    pass

                if handle and handle not in seen:
                    users.append({
                        "nickname": nickname,
                        "handle": handle.replace("@", ""),
                        "followStatus": follow_status,
                        "description": desc
                    })
                    seen.add(handle)
            except Exception:
                pass

        # 스크롤
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;", container
        )
        time.sleep(pause)

        # 더 이상 증가 없으면 몇 틱 후 종료
        if len(users) == last_count:
            stable_ticks += 1
            if stable_ticks >= 3:
                break
        else:
            last_count = len(users)
            stable_ticks = 0

    return users


# ========== Public API ==========
def collect_retweeters(
    tweet_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = True,
    max_scroll: int = 50,
    pause: float = 0.7,
) -> List[Dict]:
    driver = make_driver(headless=headless)
    try:
        if username and password:
            login_x(driver, username, password)
        driver.get(tweet_url)
        # 트윗 텍스트 로딩 대기
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetText"], article'))
        )
        container = open_retweeters_modal(driver)
        users = scroll_collect_users(driver, container, max_scroll=max_scroll, pause=pause)
        return users
    finally:
        driver.quit()


# ========== CLI ==========
def main():
    p = argparse.ArgumentParser(description="Collect X Reposters to JSON")
    p.add_argument("--url", required=True, help="Tweet URL")
    p.add_argument("--out", default="data/retweeters.json", help="Output JSON path")
    p.add_argument("--headless", default="true", choices=["true","false"])
    p.add_argument("--max-scroll", type=int, default=50)
    p.add_argument("--pause", type=float, default=0.7)
    args = p.parse_args()

    headless = (args.headless.lower() == "true")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    users = collect_retweeters(
        tweet_url=args.url,
        username=os.getenv("X_USERNAME"),
        password=os.getenv("X_PASSWORD"),
        headless=headless,
        max_scroll=args.max_scroll,
        pause=args.pause,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"users": users, "count": len(users)}, f, ensure_ascii=False, indent=2)
    print(f"[OK] saved {len(users)} users → {args.out}")


if __name__ == "__main__":
    sys.exit(main())
