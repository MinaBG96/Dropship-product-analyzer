from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

from database.db import ads_collection  # 🔥 مهم


def scrape_facebook_ads(keyword):

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&q={keyword}"

    driver.get(url)

    time.sleep(10)  # ⏳ wait for ads to load - adjust as needed

    ads = []

    elements = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")

    print("Found elements:", len(elements))  # 👈 Debug

    for el in elements[:10]:

        try:
            text = el.text
        except:
            text = None

        ad_data = {
            "keyword": keyword,
            "title": text,
            "source": "facebook"
        }

        ads.append(ad_data)

        # 🔥 تخزين مباشر في DB
        try:
            ads_collection.insert_one(ad_data)
        except:
            pass

    driver.quit()

    print("Saved ads:", len(ads))

    return ads