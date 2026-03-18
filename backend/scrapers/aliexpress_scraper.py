from playwright.sync_api import sync_playwright
import time
import re


def scrape_aliexpress(product_name):

    results = []

    search_url = f"https://www.aliexpress.com/wholesale?SearchText={product_name}"

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Opening AliExpress...")

        page.goto(search_url)

        # انتظار تحميل الصفحة
        page.wait_for_load_state("networkidle")

        # scroll لتحميل المنتجات
        for _ in range(12):
            page.mouse.wheel(0, 7000)
            time.sleep(2)

        # التقاط روابط المنتجات
        product_links = page.query_selector_all("a[href*='/item/']")

        print("Products detected:", len(product_links))

        seen = set()

        for link in product_links:

            try:

                href = link.get_attribute("href")

                if not href:
                    continue

                if href in seen:
                    continue

                seen.add(href)

                full_text = link.inner_text()

                if not full_text.strip():
                    continue

                # استخراج السعر
                price_match = re.search(r'(EGP|US \$|\$)\s?[\d,.]+', full_text)
                price = price_match.group() if price_match else None

                # استخراج التقييم
                rating_match = re.search(r'\b[0-5]\.[0-9]\b', full_text)
                rating = rating_match.group() if rating_match else None

                # استخراج عدد الطلبات
                orders_match = re.search(r'(\d+[\+]?|\d+,\d+)\s*(sold|مباعة)', full_text)
                orders = orders_match.group() if orders_match else None

                results.append({
                    "title": full_text.split("\n")[0],
                    "price": price,
                    "rating": rating,
                    "orders": orders,
                    "link": "https:" + href if href.startswith("//") else href,
                    "source": "aliexpress"
                })

                if len(results) >= 100:
                    break

            except Exception as e:
                print("Error:", e)
                continue

        browser.close()

    print("Products found:", len(results))

    return results