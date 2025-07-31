# API Documentation

## Base URL
All API endpoints are assumed to be under the base URL:
`https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main`

---

### 1. Retrieve Arabic Chapters
**Endpoint:** `/ar/chapters`  
**Method:** GET  
**Description:** Fetches details of Quran chapters in Arabic.  
**Response JSON Example:**
```json
[
  { 
    "serial_number": 1, 
    "name": "الفاتحة", 
    "transliteration": "Al Faatiha", 
    "revelation_order": null, 
    "revelation_place": "meccan", 
    "ayah_count": 7, 
    "juz_start": 1 
  },
  ...
]
```
**Source:** [Arabic Chapters](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/ar/chapters.json)

---

### 2. Retrieve English Reciters
**Endpoint:** `/en/reciters`  
**Method:** GET  
**Description:** Fetches a list of Quran reciters with their audio URLs in English.  
**Response JSON Example:**
```json
[
  { 
    "name": "Abdul Basit Abdul Samad", 
    "short_code": "ABSAMAD", 
    "audio_url": "https://everyayah.com/data/AbdulSamad_64kbps_QuranExplorer.Com/" 
  },
  ...
]
```
**Source:** [English Reciters](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/en/reciters.json)

---

### 3. Retrieve English Chapters
**Endpoint:** `/en/chapters`  
**Method:** GET  
**Description:** Fetches details of Quran chapters in English.  
**Response JSON Example:**
```json
[
  { 
    "serial_number": 1, 
    "name": "The Opening", 
    "transliteration": "Al Faatiha", 
    "revelation_order": 5, 
    "revelation_place": "meccan", 
    "ayah_count": 7, 
    "juz_start": 1 
  },
  ...
]
```
**Source:** [English Chapters](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/en/chapters.json)

---

### 4. Retrieve Word-by-Word Translation (English)
**Endpoint:** `/en/wbw/61`  
**Method:** GET  
**Description:** Retrieves word-by-word translation of Chapter 61 in English.  
**Response JSON Example:**
```json
[
  { 
      "chapter": 61,
      "verse": 1,
      "juz": 28,
      "hizb": 220,
      "manzil": 7,
      "ruku": 484,
      "word_number_in_verse": 1,
      "language_code": "en",
      "text": "Glorifies",
      "root_word": "سَبَّحَ",
      "global_word_sequence_number": 71108,
      "global_verse_sequence_number": 5164
  },
  ...
]
```
**Source:** [English WBW](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/en/wbw/61_en.json)

---

### 5. Retrieve Bengali Reciters
**Endpoint:** `/bn/reciters`  
**Method:** GET  
**Description:** Fetches a list of Quran reciters with their audio URLs in Bengali.  
**Response JSON Example:**
```json
[
  { 
    "name": "আবদুল বাসিত আবদুল সামাদ", 
    "short_code": "ABSAMAD", 
    "audio_url": "https://everyayah.com/data/AbdulSamad_64kbps_QuranExplorer.Com/" 
  },
  ...
]
```
**Source:** [Bengali Reciters](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/bn/reciters.json)

---

### 6. Retrieve Bengali Chapters
**Endpoint:** `/bn/chapters`  
**Method:** GET  
**Description:** Fetches details of Quran chapters in Bengali.  
**Response JSON Example:**
```json
[
  { 
    "serial_number": 1, 
    "name": "সূচনা", 
    "transliteration": "আল ফাতিহা", 
    "revelation_order": 5, 
    "revelation_place": "মক্কা", 
    "ayah_count": 7, 
    "juz_start": 1 
  },
  ...
]
```
**Source:** [Bengali Chapters](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/bn/chapters.json)

---

### 7. Retrieve Word-by-Word Translation (Bengali)
**Endpoint:** `/bn/wbw/61`  
**Method:** GET  
**Description:** Retrieves word-by-word translation of Chapter 61 in Bengali.  
**Response JSON Example:**
```json
[
  { 
    "chapter": 61, 
    "verse": 1, 
    "juz": 28, 
    "text": "তসবীহ করে", 
    "root_word": "سَبَّحَ", 
    ...
  },
  ...
]
```
**Source:** [Bengali WBW](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/bn/wbw/61_bn.json)

---

### 8. Retrieve Quran Translators
**Endpoint:** `/common/translators`  
**Method:** GET  
**Description:** Fetches a list of Quran translators.  
**Response JSON Example:**
```json
[
  { 
    "name": "The Clear Quran (Mustafa Khattab)", 
    "bio": "The Clear Quran (Mustafa Khattab)", 
    "code": "khattab",
    "language_code": "en"
  },
  ...
]
```
**Source:** [Translators](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/common/translators.json)

---

### 9. Retrieve Haleem Translation
**Endpoint:** `/common/haleem`  
**Method:** GET  
**Description:** Fetches verses of the Quran translated by Abdel Haleem.  
**Response JSON Example:**
```json
[
  { 
    "global_verse_sequence_number": 1, 
    "chapter": 1, 
    "verse": 1, 
    "text": "In the name of God, the Lord of Mercy, the Giver of Mercy!" 
  },
  ...
]
```
**Source:** [Haleem Translation](https://raw.githubusercontent.com/shaf-ioioi/qrn_test/refs/heads/main/common/haleem.json)
