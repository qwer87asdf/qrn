#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description="Export verses table to JSON")
    p.add_argument("db_path", help="Path to SQLite .db file")
    p.add_argument("-o", "--out", default="verses.json", help="Output JSON file (default: verses.json)")
    args = p.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: DB file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"Error opening DB: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate table/columns exist
    try:
        cur = conn.execute("PRAGMA table_info(verses)")
        cols = {row["name"] for row in cur.fetchall()}
        required = {"sura", "ayah", "text"}
        if not required.issubset(cols):
            missing = ", ".join(sorted(required - cols))
            print(f"Error: verses table missing required columns: {missing}", file=sys.stderr)
            sys.exit(1)
    except sqlite3.Error as e:
        print(f"Error inspecting DB schema: {e}", file=sys.stderr)
        sys.exit(1)

    # Pull and sort rows (chapter then verse)
    try:
        cur = conn.execute("""
            SELECT sura AS chapter, ayah AS verse, text
            FROM verses
            ORDER BY CAST(sura AS INTEGER), CAST(ayah AS INTEGER)
        """)
        rows = cur.fetchall()
    except sqlite3.Error as e:
        print(f"Error reading verses: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    # Build JSON list
    out_list = []
    gvsn = 1
    for r in rows:
        chapter = int(r["chapter"])
        verse = int(r["verse"])
        text = r["text"] if r["text"] is not None else ""

        # Preserve any <sup foot_note=...>...</sup> exactly as-is.
        # Footnotes array is intentionally empty per your requirement.
        out_list.append({
            "global_verse_sequence_number": gvsn,
            "chapter": chapter,
            "verse": verse,
            "text": text.strip(),
            "footnotes": []
        })
        gvsn += 1

    # Write JSON
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out_list, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(out_list)} verses -> {out_path}")

if __name__ == "__main__":
    main()
