import requests


ACCESS_TOKEN = "EAAZCaSy5BjJkBQ0rOto5ZA0oJyZC9cQZCpakQqv7cPZBOM2tO3uSWDjnXFXc0PComG4sE8ZBdyWpOkD48gnMKNlkYCNlgip6EMAhfZCxg5An6YBAwDDRrlbtvIBVCtnN1BQZBeFkaW5awP1VwE0mvG8AhmoZAEneFaV5EqF9X6XZCPHfFSZAQqd7yMYoZBluaQPqvsarkPLFQVv9pqcT7QUrXVRZCazapB3NkVsMphtWhF0aZCLvDojxnmyAHwZBGZCxIQJhIy2jGvUwJgp0DPDqdUS52Hf9eLbJwAZDZD"


def search_facebook_ads(keyword):

    url = "https://graph.facebook.com/v18.0/ads_archive"

    params = {
    "search_terms": keyword,
    "ad_type": "ALL",
    "ad_reached_countries": ["US"],  # بدل SA
    "fields": "ad_creative_body,ad_snapshot_url,page_name",
    "limit": 50,
    "access_token": ACCESS_TOKEN
    }

    response = requests.get(url, params=params)

    data = response.json()

    ads = []

    for ad in data.get("data", []):

        ads.append({
            "title": ad.get("ad_creative_body"),
            "page": ad.get("page_name"),
            "start_date": ad.get("ad_delivery_start_time"),
            "link": ad.get("ad_snapshot_url"),
            "source": "facebook"
        })

    return ads