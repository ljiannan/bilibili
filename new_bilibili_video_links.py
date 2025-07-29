from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

def load_netscape_cookies(driver, cookie_file):
    if not os.path.exists(cookie_file):
        print(f"Cookie文件不存在: {cookie_file}")
        return False
    with open(cookie_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith('#') or not line.strip():
            continue
        parts = line.strip().split('\t')
        if len(parts) < 7:
            continue
        domain, http_only, path, secure, expiry, name, value = parts[:7]
        cookie_dict = {
            'domain': domain,
            'name': name,
            'value': value,
            'path': path,
            'secure': secure.lower() == 'true',
        }
        if expiry and expiry != '0':
            try:
                cookie_dict['expiry'] = int(expiry)
            except:
                pass
        try:
            driver.add_cookie(cookie_dict)
        except Exception as e:
            print(f"添加cookie失败: {e}")
    print("已加载Netscape格式cookie")
    return True

def get_all_upload_video_links(cookie_file, up_url):
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument('--headless=new')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--window-size=1920,1080')
    service = Service(r"D:\chromedriver-win32\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)
    all_links = set()
    try:
        driver.get(up_url)
        time.sleep(5)
        load_netscape_cookies(driver, cookie_file)
        driver.refresh()
        time.sleep(5)
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.upload-video-card a.bili-cover-card"))
        )
        page_btns = driver.find_elements(By.CSS_SELECTOR, "button.vui_pagenation--btn-num")
        page_nums = [int(btn.text) for btn in page_btns if btn.text.isdigit()]
        max_page = max(page_nums) if page_nums else 1
        for page in range(1, max_page + 1):
            print(f"正在处理第{page}页...")
            if page > 1:
                page_btns = driver.find_elements(By.CSS_SELECTOR, "button.vui_pagenation--btn-num")
                for btn in page_btns:
                    if btn.text == str(page):
                        driver.execute_script("arguments[0].scrollIntoView();", btn)
                        btn.click()
                        break
                time.sleep(2)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.upload-video-card a.bili-cover-card"))
                )
            video_elements = driver.find_elements(By.CSS_SELECTOR, "div.upload-video-card a.bili-cover-card")
            found_this_page = 0
            for elem in video_elements:
                link = elem.get_attribute("href")
                if link and "/video/BV" in link:
                    bv = link.split("/video/")[-1].split("?")[0]
                    video_url = f"https://www.bilibili.com/video/{bv}"
                    all_links.add(video_url)
                    found_this_page += 1
            print(f"本页提取到 {found_this_page} 个视频链接。")
        print(f"共提取到 {len(all_links)} 个视频链接。")
        with open("upload_video_links.txt", "w", encoding="utf-8") as f:
            for url in all_links:
                f.write(url + "\n")
        print("所有链接已保存到 upload_video_links.txt")
    finally:
        driver.quit()

if __name__ == "__main__":
    UP_URL = "https://space.bilibili.com/1420982/upload/video"
    COOKIE_FILE = r"C:\\Users\\Dell\\Desktop\\bilibili.txt"
    get_all_upload_video_links(COOKIE_FILE, UP_URL)
