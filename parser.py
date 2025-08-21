#!/usr/bin/env python3
import json
import os
import time
from typing import Dict, Any, List, Optional

import requests

BASE_URL = "https://api.qurancdn.com/api/qdc/verses/by_chapter/{chapter}"
OUTPUT_DIR = "./en/wbw"
LANG_CODE = "en"               # word-by-word translation language
TRANSLATION_ID = 161           # Taisirul Quran (as in your sample)
MUSHAF_ID = 7                  # Script/layout profile
RECITER_ID = 7                 # Not strictly needed, but matches your calls
PER_PAGE = 50                  # Larger page size to minimize pagination
REQUEST_TIMEOUT = 20
RETRY_COUNT = 3
RETRY_BACKOFF_SEC = 1.5

# We’ll request these fields explicitly to ensure they’re present.
VERSE_FIELDS = [
    "id",
    "verse_number",
    "chapter_id",
    "juz_number",
    "hizb_number",
    "rub_el_hizb_number",
    "manzil_number",
    "ruku_number",
]
WORD_FIELDS = [
    "id",
    "position",
    "verse_key",
    "verse_id",
    "location",
    "page_number",
    "line_number",
    "char_type_name",
    "text_uthmani",
    "text_imlaei_simple",
    "text_indopak",
    "qpc_uthmani_hafs",
    "text",
]

def fetch_page(chapter: int, page: int) -> Dict[str, Any]:
    """Fetch a single page of verses for a chapter with retries."""
    params = {
        "words": "true",
        "per_page": PER_PAGE,
        "page": page,
        "mushaf": MUSHAF_ID,
        "reciter": RECITER_ID,
        "translations": TRANSLATION_ID,
        "word_translation_language": LANG_CODE,
        "fields": ",".join(VERSE_FIELDS),
        "word_fields": ",".join(WORD_FIELDS),
        "translation_fields": "resource_name,language_id",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(
                BASE_URL.format(chapter=chapter),
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "PythonRequests/2.x"},
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 502, 503, 504):
                # transient; back off and retry
                time.sleep(RETRY_BACKOFF_SEC * attempt)
            else:
                resp.raise_for_status()
        except Exception as e:
            last_exc = e
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    # If we got here, we failed all retries:
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Failed to fetch chapter {chapter}, page {page}")

def ensure_output_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def build_entry(verse: Dict[str, Any], word: Dict[str, Any],
                global_word_seq: int) -> Optional[Dict[str, Any]]:
    """Build one output record for a word. Skip verse-end markers."""
    # Skip non-word tokens (e.g., ayah-end glyphs)
    if word.get("char_type_name") != "word":
        return None

    # Use QPC Hafs glyph if present; fallback to text_uthmani
    root_word = (
        word.get("text")
        or word.get("qpc_uthmani_hafs")
        or word.get("text_uthmani")
        or word.get("text_imlaei_simple")
        or word.get("text_indopak")
        or ""
    )

    # Translation text (Bangla) — in the wbw object
    translation_obj = word.get("translation") or {}
    text_bn = translation_obj.get("text", "")

    entry = {
        "chapter": verse.get("chapter_id"),
        "verse": verse.get("verse_number"),
        "juz": verse.get("juz_number"),
        # Your sample’s “hizb” value is actually rub_el_hizb_number (e.g., 240)
        "hizb": verse.get("rub_el_hizb_number"),
        "manzil": verse.get("manzil_number"),
        "ruku": verse.get("ruku_number"),
        "word_number_in_verse": word.get("position"),
        "language_code": LANG_CODE,
        "text": text_bn,
        "root_word": root_word,
        # Global counters/ids
        "global_word_sequence_number": global_word_seq,
        "global_verse_sequence_number": verse.get("id"),
    }
    return entry

def process_chapter(chapter: int, global_counter_start: int) -> int:
    """Fetch all pages for a chapter, write chapter_{n}.json, return new global counter."""
    output: List[Dict[str, Any]] = []
    page = 1
    global_word_seq = global_counter_start

    while True:
        data = fetch_page(chapter, page)
        verses = data.get("verses") or []
        pagination = data.get("pagination") or {}
        next_page = pagination.get("next_page")

        for verse in verses:
            words = verse.get("words") or []
            for w in words:
                entry = build_entry(verse, w, global_word_seq + 1)
                if entry is not None:
                    global_word_seq += 1
                    output.append(entry)

        if not next_page:
            break
        page = next_page

    # Write this chapter’s JSON
    ensure_output_dir(OUTPUT_DIR)
    out_path = os.path.join(OUTPUT_DIR, f"{chapter}_en.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} with {len(output)} records.")
    return global_word_seq

def main():
    global_word_seq = 0  # We’ll count from 1 as we add words
    for chapter in range(1, 115):  # 1..114 inclusive
        global_word_seq = process_chapter(chapter, global_word_seq)

    print(f"Done. Final global_word_sequence_number = {global_word_seq}")

if __name__ == "__main__":
    main()