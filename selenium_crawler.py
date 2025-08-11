# selenium_crawler.py
import os, time
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# Selenium 4.6+ 는 셀레니움 매니저가 드라이버를 자동 설치합니다.
def _make_driver(headless: bool = True):
    opts = Options()
    if headless:
        # 최신 크롬 헤드리스 플래그
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=ko-KR,ko,en-US,en")
    # 봇 차단 회피에 도움 되는 옵션
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    })
    return driver

def _login_x(driver, username: Optional[str], password: Optional[str]):
    # 로그인 필요 시에만 시도 (미입력이면 skip)
    if not username or not password: return
    driver.get("https://x.com/i/flow/login")
    w = WebDriverWait(driver, 20)

    # 1) 사용자명/이메일
    user_input = w.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
    user_input.clear(); user_input.send_keys(username); user_input.send_keys(Keys.ENTER)

    # 2) 비밀번호 (중간에 사용자명 재확인 스텝이 있을 수 있음)
    time.sleep(1)
    inputs = driver.find_elements(By.TAG_NAME, "input")
    if len(inputs) >= 2:
        inputs[-1].clear(); inputs[-1].send_keys(password); inputs[-1].send_keys(Keys.ENTER)
    else:
        pwd = w.until(EC.presence_of_element_located((By.NAME, "password")))
        pwd.clear(); pwd.send_keys(password); pwd.send_keys(Keys.ENTER)

    # 홈 로딩 대기
    w.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="AppTabBar_Home_Link"]')))

def _open_retweeters_modal(driver):
    w = WebDriverWait(driver, 20)
    # 트윗 페이지에서 '리포스트' 버튼을 찾음 (영/한 UI 대응)
    candidates = w.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[role="link"], div[role="button"], span')))
    target = None
    for el in candidates:
        try:
            txt = (el.text or "").strip().lower()
            if txt in ("reposts", "리포스트", "재게시"):  # UI에 따라 다름
                target = el
                break
        except: pass
    if not target:
        # 카운트 배지 클릭 케이스 (data-testid 사용)
        for el in driver.find_elements(By.CSS_SELECTOR, '[data-testid="retweet"]'):
            target = el; break
    if not target:
        raise RuntimeError("Reposts button not found. UI changed?")

    driver.execute_script("arguments[0].click();", target)
    # 모달 등장 대기
    w.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[role="dialog"]')))
    container = w.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[role="dialog"] [data-testid="sheetDialog"]')))
    return container

def _scroll_collect_cells(driver, container, max_scroll=40, pause=0.6):
    users: List[Dict] = []
    seen = set()
    for _ in range(max_scroll):
        cells = container.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')
        for c in cells:
            try:
                # 핸들(@), 닉네임, 설명, 팔로우 버튼 텍스트
                handle = (c.find_element(By.CSS_SELECTOR, 'div span:has(svg[aria-label="Verified account"]) ~ span, a[href^="/"]').text or "").replace("@","").strip()
                if not handle:
                    # 대안: 링크에서 추출
                    links = c.find_elements(By.CSS_SELECTOR, 'a[href^="/"]')
                    for a in links:
                        href=a.get_attribute("href") or ""
                        if "x.com/" in href and "/status/" not in href:
                            handle = href.split("x.com/")[-1].strip("/")
                            break
                nickname = ""
                try:
                    nickname = c.find_element(By.CSS_SELECTOR, 'div[dir="ltr"] span').text
                except:
                    nickname = c.text.split("\n")[0]

                desc = ""
                try:
                    desc = c.find_element(By.CSS_SELECTOR, 'div[dir="auto"][lang]').text
                except: pass

                follow_btn_txt = ""
                try:
                    follow_btn_txt = c.find_element(By.CSS_SELECTOR, '[data-testid$="follow"], [data-testid$="unfollow"]').text
                except: pass
                follow_status = "팔로잉" if ("Following" in follow_btn_txt or "언팔로우" in follow_btn_txt) else "팔로우"

                if handle and handle not in seen:
                    users.append({
                        "nickname": nickname,
                        "handle": handle,
                        "followStatus": follow_status,
                        "description": desc
                    })
                    seen.add(handle)
            except: pass

        # 스크롤 다운
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;", container)
        time.sleep(pause)
        # 더 이상 추가 로딩 없는지 간단 체크
        if len(cells) > 0 and len(cells) == len(container.find_elements(By.CSS_SELECTOR, '[data-testid="UserCell"]')):
            # 두 번 연속 증가 없으면 중단
            pass
    return users

def collect_retweeters(tweet_url: str, username: str = None, password: str = None, headless: bool = True) -> List[Dict]:
    driver = _make_driver(headless=headless)
    try:
        _login_x(driver, username, password)
        driver.get(tweet_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetText"]')))
        container = _open_retweeters_modal(driver)
        users = _scroll_collect_cells(driver, container)
        return users
    finally:
        driver.quit()
