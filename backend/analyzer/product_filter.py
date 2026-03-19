import re


def normalize(text):
    if not text:
        return ""

    text = text.lower()

    # حذف أي أرقام أو رموز زي -1
    text = re.sub(r'[^a-zA-Z ]', '', text)

    return text.strip()


def is_relevant(product_title, search_keyword):

    title = normalize(product_title)
    keyword = normalize(search_keyword)

    keyword_words = keyword.split()

    # نحذف كلمات مش مهمة
    stop_words = ["for", "with", "and", "the"]

    keyword_words = [w for w in keyword_words if w not in stop_words]

    score = 0

    for word in keyword_words:
        if word in title:
            score += 1

    # ⚠️ بدل 60% نخليها 40% علشان المرونة
    relevance_ratio = score / len(keyword_words) if keyword_words else 0

    return relevance_ratio >= 0.2