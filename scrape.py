import json
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

# Path to save output
OUTPUT_FILE = "visa_fees.json"

def setup_driver():
    chrome_options = Options()
    headless_env = os.environ.get("HEADLESS", "0").lower() in ("1", "true", "yes")
    if headless_env:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    else:
        chrome_options.add_argument("--window-size=1600,1200")

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    ua = os.environ.get("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.90 Safari/537.36")
    chrome_options.add_argument(f"--user-agent={ua}")
    chrome_options.add_argument("--lang=en-US")

    def finalize_driver(d):
        try:
            d.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        except Exception:
            pass

    try:
        driver = webdriver.Chrome(options=chrome_options)
        finalize_driver(driver)
        return driver
    except Exception as e:
        print("Selenium Manager failed, falling back to webdriver_manager:", e)
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        if chromedriver_path:
            print("Using chromedriver from CHROMEDRIVER_PATH:", chromedriver_path)
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            finalize_driver(driver)
            return driver

        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            finalize_driver(driver)
            return driver
        except Exception as e2:
            print("webdriver_manager failed to download a compatible chromedriver:", e2)
            print("Download a chromedriver matching your Chrome from https://chromedriver.chromium.org/downloads")
            raise

def parse_fees(html):
    soup = BeautifulSoup(html, "html.parser")
    data = []

    table = soup.find("table")
    if not table:
        return data

  
    thead = table.find("thead")
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all("th")]
        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    else:
        first_row = table.find("tr")
        headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"]) ]
        rows = table.find_all("tr")[1:]

    for row in rows:
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cols:
            continue
        record = dict(zip(headers, cols))
        data.append(record)

    return data

def main():
    url = "https://immi.homeaffairs.gov.au/visas/getting-a-visa/fees-and-charges/current-visa-pricing#"
    driver = setup_driver()
    driver.get(url)
    # Pagination loop: collect data from each page 
    all_data = []
    seen = set()
    page_num = 1
    max_pages = 20

    def find_and_click_next(d):
        xpaths = [
            "//a[@rel='next']",
            "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
            "//a[contains(@class,'next')]",
            "//a[contains(@aria-label,'Next')]",
            "//button[contains(@aria-label,'Next')]",
        ]
        for xp in xpaths:
            try:
                elems = d.find_elements(By.XPATH, xp)
            except Exception:
                elems = []
            for el in elems:
                try:
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        return True
                except Exception:
                    continue
        return False

    try:
        while page_num <= max_pages:
            try:
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            except Exception:
                time.sleep(3)

            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            time.sleep(1)

            html = driver.page_source
            try:
                with open(f"page_{page_num}.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass

            page_rows = parse_fees(html)
            added = 0
            for r in page_rows:
                key = json.dumps(r, sort_keys=True, ensure_ascii=False)
                if key not in seen:
                    seen.add(key)
                    all_data.append(r)
                    added += 1

            print(f"Page {page_num}: found {len(page_rows)} rows, {added} new")

            moved = find_and_click_next(driver)
            if not moved:
                break
            page_num += 1
            time.sleep(1.5)
        driver.quit()
    except Exception as e:
        driver.quit()
        print("Error during pagination:", e)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4, ensure_ascii=False)

    print(f"✨ Scraped {len(all_data)} rows from {page_num} pages")
    print(f"📦 Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
