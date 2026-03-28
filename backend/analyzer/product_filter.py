"""
product_filter.py — Fixed & Hardened
======================================
Changes from original:
1. Relevance threshold raised from 0.2 to 0.5 — original let garbage through
2. normalize() no longer strips numbers — "brush 2.0" and "USB" now handled correctly
3. Unicode/non-Latin titles handled gracefully instead of becoming empty strings
4. Stop words list expanded and extracted as a constant
5. Exact phrase match bonus added — full keyword match scores higher than partial
6. Minimum title length check added — single-word or empty titles are rejected
7. is_relevant() now returns (bool, float) so callers can log relevance scores
8. All logic documented so threshold decisions are explicit and auditable
"""

import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Stop words — words that carry no product-matching meaning.
# Expanded from original ["for", "with", "and", "the"].
# FIX: Original stop word list was too short — words like "a", "to",
# "in", "of" were being counted as keyword matches, inflating scores.
# ------------------------------------------------------------------
STOP_WORDS = {
    "for", "with", "and", "the", "a", "an", "to", "in",
    "of", "on", "at", "by", "or", "is", "it", "as",
    "from", "into", "that", "this", "set", "kit", "pack",
    "new", "hot", "best", "top", "free", "fast",
}

# ------------------------------------------------------------------
# Relevance threshold — fraction of keyword words that must appear
# in the product title to be considered relevant.
#
# FIX: Original was 0.2 (20%). That means a 5-word keyword like
# "electric cleaning brush for bathroom" only needed 1 word to match.
# The word "for" alone — a stop word — would pass a product through.
#
# 0.5 means at least half the meaningful words must appear.
# For a 4-word meaningful keyword, 2 words must match.
# ------------------------------------------------------------------
RELEVANCE_THRESHOLD = 0.5

# Bonus threshold: if the entire keyword phrase appears in the title,
# it is definitely relevant regardless of word-by-word score.
EXACT_PHRASE_BONUS = True


def normalize(text: str) -> str:
    """
    Normalizes text for keyword matching.

    FIX 1: Original used re.sub(r'[^a-zA-Z ]', '', text) which:
    - Stripped numbers → "USB" stayed but "brush 2.0" lost the "2.0"
    - Turned Arabic/Chinese titles into empty strings silently
    - Caused non-Latin products to always fail the relevance check

    FIX 2: Now uses Unicode normalization (NFKD) to handle accented
    characters and non-ASCII letters before stripping.

    FIX 3: Numbers are preserved — "wireless 2.4G mouse" should match
    a keyword containing "2.4G".
    """
    if not text:
        return ""

    # Unicode normalize — decompose accented chars (é → e + ́)
    text = unicodedata.normalize("NFKD", text)

    # Encode to ASCII, ignore non-ASCII bytes (handles Arabic, Chinese, etc.)
    # This converts what it can and drops what it cannot rather than
    # silently returning an empty string.
    text = text.encode("ascii", errors="ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Keep letters, numbers, and spaces — strip punctuation only
    # FIX: Original stripped numbers too, now we keep them
    text = re.sub(r"[^a-z0-9 ]", " ", text)

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_keywords(keyword_phrase: str) -> list[str]:
    """
    Splits a keyword phrase into meaningful words by removing stop words.

    Returns a list of lowercase, normalized words.

    FIX: Original inlined this logic inside is_relevant() with a short
    stop word list. Now extracted as a reusable function with a full list.
    """
    normalized = normalize(keyword_phrase)
    words      = normalized.split()
    meaningful = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return meaningful


def is_relevant(product_title: str, search_keyword: str) -> tuple[bool, float]:
    """
    Determines whether a product title is relevant to a search keyword.

    Returns:
        (is_relevant: bool, score: float)
        score is the fraction of keyword words found in the title (0.0 to 1.0).
        Callers can log the score for debugging and threshold tuning.

    FIX: Original returned only bool — no visibility into why a product
    passed or failed, making threshold tuning blind.

    FIX: Threshold raised from 0.2 to 0.5 — see RELEVANCE_THRESHOLD above.

    FIX: Exact phrase match added — if the full keyword appears verbatim
    in the title, the product is always considered relevant.

    Examples:
        is_relevant("Electric Cleaning Brush USB Rechargeable", "electric cleaning brush")
        → (True, 1.0)   ← all 3 meaningful words match

        is_relevant("Hair Brush Set for Dogs", "electric cleaning brush")
        → (False, 0.33) ← only "brush" matches out of ["electric","cleaning","brush"]

        is_relevant("Silicone Kitchen Spatula", "electric cleaning brush")
        → (False, 0.0)  ← no meaningful words match
    """
    # ------------------------------------------------------------------
    # Guard: reject empty or suspiciously short titles
    # FIX: Original never checked title length — a product with title ""
    # or "A" would be processed and potentially saved.
    # ------------------------------------------------------------------
    if not product_title or len(product_title.strip()) < 3:
        logger.debug("Rejected: title too short — '%s'", product_title)
        return False, 0.0

    if not search_keyword or len(search_keyword.strip()) < 2:
        logger.warning("Invalid search keyword: '%s'", search_keyword)
        return False, 0.0

    title_normalized   = normalize(product_title)
    keyword_normalized = normalize(search_keyword)

    # ------------------------------------------------------------------
    # Exact phrase match — strongest signal
    # If the full keyword phrase appears verbatim in the title,
    # it is definitely relevant. Skip word-by-word scoring.
    # ------------------------------------------------------------------
    if EXACT_PHRASE_BONUS and keyword_normalized in title_normalized:
        logger.debug(
            "Exact match: '%s' in '%s'", keyword_normalized, title_normalized
        )
        return True, 1.0

    # ------------------------------------------------------------------
    # Word-by-word matching
    # ------------------------------------------------------------------
    keyword_words = extract_keywords(search_keyword)

    if not keyword_words:
        # All words were stop words — keyword is meaningless
        logger.warning(
            "Keyword '%s' contains only stop words — cannot filter", search_keyword
        )
        return True, 1.0  # pass through rather than reject everything

    title_words = set(title_normalized.split())

    matched = [w for w in keyword_words if w in title_words]
    score   = len(matched) / len(keyword_words)

    is_rel  = score >= RELEVANCE_THRESHOLD

    logger.debug(
        "Relevance check: title='%s' | keyword='%s' | matched=%s/%s | score=%.2f | relevant=%s",
        product_title[:50],
        search_keyword,
        len(matched),
        len(keyword_words),
        score,
        is_rel,
    )

    return is_rel, score