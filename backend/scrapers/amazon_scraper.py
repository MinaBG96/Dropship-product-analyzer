from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time


def scrape_amazon(product_name):

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    search_url = f"https://www.amazon.com/s?k={product_name.replace(' ', '+')}"
    driver.get(search_url)

    time.sleep(3)

    products = []

    items = driver.find_elements(By.CSS_SELECTOR, "div.s-main-slot div[data-component-type='s-search-result']")

    for item in items[:20]:  # أول 20 منتج

        try:
            title = item.find_element(By.CSS_SELECTOR, "h2 span").text
        except:
            title = None

        try:
            price = item.find_element(By.CSS_SELECTOR, ".a-price-whole").text
        except:
            price = None

        try:
            rating = item.find_element(By.CSS_SELECTOR, ".a-icon-alt").text.split(" ")[0]
        except:
            rating = None

        try:
            reviews = item.find_element(By.CSS_SELECTOR, ".a-size-base").text
        except:
            reviews = None

        try:
            link = item.find_element(By.CSS_SELECTOR, "h2 a").get_attribute("href")
        except:
            link = None

        products.append({
            "title": title,
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "link": link,
            "source": "amazon"
        })

    driver.quit()

    return products