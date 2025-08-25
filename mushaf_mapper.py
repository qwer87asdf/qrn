#!/usr/bin/env python3
import os
import re
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any

from flask import Flask, send_from_directory, jsonify, request, abort, Response

# ----------------------------
# Config / CLI
# ----------------------------
parser = argparse.ArgumentParser(description="Interactive Mushaf Line Mapper")
parser.add_argument("--data-dir", required=True, help="Directory containing per-chapter word files like 1_bn.json")
parser.add_argument("--lang", default="bn", help="Language code suffix used in filenames, e.g. bn or en (default: bn)")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=5000)
parser.add_argument("--save-dir", default="./mappings", help="Where to save server-side snapshots")
args = parser.parse_args()

DATA_DIR = os.path.abspath(args.data_dir)
LANG = args.lang
SAVE_DIR = os.path.abspath(args.save_dir)

os.makedirs(SAVE_DIR, exist_ok=True)

# ----------------------------
# Load available chapters
# ----------------------------
chapter_files: Dict[int, str] = {}
fname_re = re.compile(r"^(\d+)_([A-Za-z0-9]+)\.json$")

for fn in os.listdir(DATA_DIR):
    m = fname_re.match(fn)
    if not m:
        continue
    ch = int(m.group(1))
    suffix = m.group(2)
    if suffix.lower() == LANG.lower():
        chapter_files[ch] = fn

if not chapter_files:
    raise SystemExit(f"No chapter files found in {DATA_DIR} for lang '{LANG}'. "
                     f"Expected files like '1_{LANG}.json'")

available_chapters = sorted(chapter_files.keys())

# ----------------------------
# Flask App
# ----------------------------
app = Flask(__name__, static_folder=None)

INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Mushaf Line Mapper</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 16px; }
    header { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
    select, input, button { padding: 6px 10px; font-size: 14px; }
    .controls { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin: 8px 0 16px; }
    .quran { border: 1px solid #ddd; border-radius: 10px; padding: 12px; max-height: 60vh; overflow:auto; }
    .verse { margin: 10px 0; }
    .vkey { color:#666; font-size:12px; margin-right:6px; }
    .word { cursor: pointer; padding: 2px 4px; border-radius: 6px; display:inline-block; margin:2px 1px; }
    .word:hover { background: #eef6ff; }
    .selected-first { background: #d1fae5 !important; outline: 2px solid #10b981; }
    .selected-last  { background: #fde68a !important; outline: 2px solid #f59e0b; }
    .toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin: 12px 0; }
    table { width:100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border:1px solid #eee; padding:6px 8px; font-size:13px; text-align:left; white-space:nowrap; }
    th { background:#fafafa; position: sticky; top:0; }
    .grow { flex: 1; }
    .muted { color:#666; font-size:12px; }
    .pill { background:#f3f4f6; padding:2px 8px; border-radius:999px; font-size:12px; }
    .sticky-top { position: sticky; top: 0; background: white; z-index: 2; padding-bottom: 8px; }
    .danger { color:#b91c1c; }
    .ok { color:#065f46; }
  </style>
</head>
<body>
  <div class="sticky-top">
    <header>
      <div><strong>Mushaf Line Mapper</strong> <span class="muted">— click a word to set First/Last</span></div>
      <div class="pill">Language: <strong id="lang-pill"></strong></div>
      <div class="pill">Chapters: <strong id="count-pill"></strong></div>
    </header>

    <div class="controls">
      <label>Chapter:
        <select id="chapter-select"></select>
      </label>

      <label>Page:
        <input id="page-input" type="number" min="1" value="1" style="width:80px"/>
      </label>

      <label>Line:
        <input id="line-input" type="number" min="1" value="1" style="width:80px"/>
      </label>

      <label>Line Type:
        <select id="linetype-select">
          <option value="ayah">ayah</option>
          <option value="bismillah">bismillah</option>
          <option value="surah_name">surah_name</option>
        </select>
      </label>

      <button id="prev-ch">◀ Prev chapter</button>
      <button id="next-ch">Next chapter ▶</button>

      <span class="grow"></span>

      <button id="save-server">💾 Save Server</button>
      <button id="load-server">📂 Load Server</button>
      <button id="export">⬇ Export JSON</button>
      <button id="clear">🧹 Clear</button>
    </div>

    <div class="toolbar">
      <div>First: <span id="first-pill" class="pill muted">—</span></div>
      <div>Last: <span id="last-pill" class="pill muted">—</span></div>
      <button id="set-first">Set First (manual)</button>
      <button id="set-last">Set Last (manual)</button>
      <button id="add-line">➕ Add Line</button>
      <button id="undo">↩ Undo</button>
      <span class="grow"></span>
      <div id="status" class="muted"></div>
    </div>
  </div>

  <div id="quran" class="quran" aria-live="polite"></div>

  <h3>Line Mappings</h3>
  <div style="max-height: 30vh; overflow:auto;">
    <table id="lines-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Page</th>
          <th>Line</th>
          <th>Type</th>
          <th>Chapter</th>
          <th>First</th>
          <th>Last</th>
          <th>Verse (first)</th>
          <th>Verse (last)</th>
        </tr>
      </thead>
      <tbody id="lines-body"></tbody>
    </table>
  </div>

<script>
const LANG = "{{lang}}";
const chapters = {{chapters|tojson}};

const state = {
  currentChapter: chapters[0],
  words: [],           // current chapter words
  first: null,         // {g, ch, v, pos}
  last: null,          // {g, ch, v, pos}
  lines: []            // collected lines
};

function $(id){ return document.getElementById(id); }
function status(msg, cls="muted"){ const el = $("status"); el.className = cls; el.textContent = msg; }

function wordLabel(w){
  return `g#${w.global_word_sequence_number} ${w.chapter}:${w.verse}:${w.word_number_in_verse}`;
}

function renderWords(){
  const q = $("quran");
  q.innerHTML = "";
  let currentVerseKey = null;
  let verseDiv = null;

  state.words.forEach(w=>{
    const vkey = `${w.chapter}:${w.verse}`;
    if (vkey !== currentVerseKey){
      currentVerseKey = vkey;
      verseDiv = document.createElement("div");
      verseDiv.className = "verse";
      const vk = document.createElement("span");
      vk.className = "vkey";
      vk.textContent = vkey;
      verseDiv.appendChild(vk);
      q.appendChild(verseDiv);
    }

    const span = document.createElement("span");
    span.className = "word";
    span.textContent = w.root_word || w.text || "";
    span.title = wordLabel(w);
    span.dataset.g = w.global_word_sequence_number;
    span.dataset.ch = w.chapter;
    span.dataset.v = w.verse;
    span.dataset.pos = w.word_number_in_verse;

    span.addEventListener("click", ()=>{
      // toggle logic: first then last
      if (!state.first){
        state.first = {
          g: +span.dataset.g,
          ch: +span.dataset.ch,
          v: +span.dataset.v,
          pos: +span.dataset.pos
        };
      } else if (!state.last){
        state.last = {
          g: +span.dataset.g,
          ch: +span.dataset.ch,
          v: +span.dataset.v,
          pos: +span.dataset.pos
        };
      } else {
        // reset to new first
        state.first = {
          g: +span.dataset.g,
          ch: +span.dataset.ch,
          v: +span.dataset.v,
          pos: +span.dataset.pos
        };
        state.last = null;
      }
      updateSelectionHighlights();
      updateFirstLastPills();
    });

    verseDiv.appendChild(span);
  });

  updateSelectionHighlights();
}

function clearHighlights(){
  document.querySelectorAll(".word").forEach(el=>{
    el.classList.remove("selected-first","selected-last");
  });
}
function updateSelectionHighlights(){
  clearHighlights();
  if (state.first){
    const el = document.querySelector(`.word[data-g="${state.first.g}"]`);
    if (el) el.classList.add("selected-first");
  }
  if (state.last){
    const el = document.querySelector(`.word[data-g="${state.last.g}"]`);
    if (el) el.classList.add("selected-last");
  }
}
function updateFirstLastPills(){
  $("first-pill").textContent = state.first ? `${state.first.ch}:${state.first.v}:${state.first.pos} (g#${state.first.g})` : "—";
  $("last-pill").textContent  = state.last  ? `${state.last.ch}:${state.last.v}:${state.last.pos} (g#${state.last.g})`  : "—";
}

async function loadChapter(ch){
  status("Loading chapter "+ch+" …");
  const res = await fetch(`/chapter/${ch}`);
  if (!res.ok){ status("Failed to load chapter "+ch, "danger"); return; }
  state.words = await res.json();
  state.currentChapter = ch;
  $("chapter-select").value = String(ch);
  renderWords();
  status(`Loaded chapter ${ch} — ${state.words.length} words`, "ok");
}

function addLine(){
  const page  = +$("page-input").value || 0;
  const line  = +$("line-input").value || 0;
  const ltype = $("linetype-select").value;

  if (!state.first || !state.last){
    status("Pick First and Last word by clicking on words.", "danger");
    return;
  }
  const firstG = Math.min(state.first.g, state.last.g);
  const lastG  = Math.max(state.first.g, state.last.g);

  // find verses for table display
  const idxFirst = state.words.findIndex(w=>w.global_word_sequence_number===firstG);
  const idxLast  = state.words.findIndex(w=>w.global_word_sequence_number===lastG);

  const firstVerse = idxFirst>=0 ? `${state.words[idxFirst].chapter}:${state.words[idxFirst].verse}` : "";
  const lastVerse  = idxLast>=0  ? `${state.words[idxLast].chapter}:${state.words[idxLast].verse}`  : "";

  const row = {
    page_number: page,
    line_number: line,
    line_type: ltype,             // "surah_name" | "bismillah" | "ayah"
    first_word_number: firstG,    // global_word_sequence_number
    last_word_number: lastG,
    chapter_number: state.currentChapter
  };
  state.lines.push(row);
  appendRow(row, state.lines.length, firstVerse, lastVerse);

  // auto advance line number
  $("line-input").value = String(line+1);

  // reset selection
  state.first = null; state.last = null;
  updateSelectionHighlights(); updateFirstLastPills();
  status("Line added.", "ok");
}

function appendRow(row, idx, firstVerse, lastVerse){
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>${idx}</td>
    <td>${row.page_number}</td>
    <td>${row.line_number}</td>
    <td>${row.line_type}</td>
    <td>${row.chapter_number}</td>
    <td>${row.first_word_number}</td>
    <td>${row.last_word_number}</td>
    <td>${firstVerse}</td>
    <td>${lastVerse}</td>
  `;
  $("lines-body").appendChild(tr);
}

function rebuildTable(){
  $("lines-body").innerHTML = "";
  state.lines.forEach((row, i)=>{
    // try to show verses
    const f = state.words.find(w=>w.global_word_sequence_number===row.first_word_number);
    const l = state.words.find(w=>w.global_word_sequence_number===row.last_word_number);
    appendRow(row, i+1, f?`${f.chapter}:${f.verse}`:"", l?`${l.chapter}:${l.verse}`:"");
  });
}

$("add-line").addEventListener("click", addLine);
$("undo").addEventListener("click", ()=>{
  if (state.lines.length>0){
    state.lines.pop();
    rebuildTable();
    status("Removed last line.", "ok");
  }
});
$("clear").addEventListener("click", ()=>{
  state.lines = [];
  rebuildTable();
  status("Cleared all lines.", "ok");
});
$("export").addEventListener("click", ()=>{
  const payload = JSON.stringify(state.lines, null, 2);
  const blob = new Blob([payload], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "line_mappings.json";
  a.click();
});
$("save-server").addEventListener("click", async ()=>{
  const r = await fetch("/save", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(state.lines)});
  if (r.ok){ const j = await r.json(); status("Saved: "+j.filename, "ok"); } else { status("Save failed", "danger"); }
});
$("load-server").addEventListener("click", async ()=>{
  const r = await fetch("/load");
  if (!r.ok){ status("Load failed", "danger"); return; }
  const j = await r.json();
  state.lines = j.lines || [];
  rebuildTable();
  status("Loaded server snapshot.", "ok");
});

$("set-first").addEventListener("click", ()=>{
  const g = prompt("Enter global word number (First):");
  if (!g) return;
  const w = state.words.find(w=>w.global_word_sequence_number===+g);
  if (!w){ status("No word with that global number in this chapter view.", "danger"); return; }
  state.first = { g:+g, ch:w.chapter, v:w.verse, pos:w.word_number_in_verse };
  updateSelectionHighlights(); updateFirstLastPills();
});
$("set-last").addEventListener("click", ()=>{
  const g = prompt("Enter global word number (Last):");
  if (!g) return;
  const w = state.words.find(w=>w.global_word_sequence_number===+g);
  if (!w){ status("No word with that global number in this chapter view.", "danger"); return; }
  state.last = { g:+g, ch:w.chapter, v:w.verse, pos:w.word_number_in_verse };
  updateSelectionHighlights(); updateFirstLastPills();
});

$("prev-ch").addEventListener("click", ()=>{
  const idx = chapters.indexOf(state.currentChapter);
  if (idx>0) loadChapter(chapters[idx-1]);
});
$("next-ch").addEventListener("click", ()=>{
  const idx = chapters.indexOf(state.currentChapter);
  if (idx>=0 && idx<chapters.length-1) loadChapter(chapters[idx+1]);
});

(function init(){
  $("lang-pill").textContent = LANG;
  $("count-pill").textContent = chapters.length;

  const sel = $("chapter-select");
  chapters.forEach(ch=>{
    const opt = document.createElement("option");
    opt.value = String(ch);
    opt.textContent = String(ch);
    sel.appendChild(opt);
  });
  sel.addEventListener("change", ()=>loadChapter(+sel.value));
  loadChapter(chapters[0]);
})();
</script>
</body>
</html>
"""

# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def index():
    return Response(
        INDEX_HTML.replace("{{lang}}", LANG).replace("{{chapters|tojson}}", json.dumps(available_chapters)),
        mimetype="text/html"
    )

@app.get("/chapter/<int:ch>")
def get_chapter(ch: int):
    if ch not in chapter_files:
        abort(404)
    fp = os.path.join(DATA_DIR, chapter_files[ch])
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Basic sanity: expect list of words with required fields
    required = {"chapter","verse","word_number_in_verse","global_word_sequence_number"}
    filtered: List[Dict[str, Any]] = []
    for w in data:
        if not required.issubset(w.keys()):
            # skip malformed
            continue
        filtered.append({
            "chapter": w["chapter"],
            "verse": w["verse"],
            "word_number_in_verse": w["word_number_in_verse"],
            "text": w.get("text"),
            "root_word": w.get("root_word") or w.get("text"),
            "global_word_sequence_number": w["global_word_sequence_number"],
            "global_verse_sequence_number": w.get("global_verse_sequence_number")
        })
    return jsonify(filtered)

@app.post("/save")
def save_lines():
    try:
        lines = request.get_json(force=True)
        if not isinstance(lines, list):
            return jsonify({"error":"payload must be list"}), 400
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"line_mappings_{ts}.json"
        fp = os.path.join(SAVE_DIR, fname)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(lines, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True, "filename": fname})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/load")
def load_latest():
    # load latest saved file if exists
    files = [f for f in os.listdir(SAVE_DIR) if f.startswith("line_mappings_") and f.endswith(".json")]
    if not files:
        return jsonify({"lines": []})
    files.sort(reverse=True)
    fp = os.path.join(SAVE_DIR, files[0])
    with open(fp, "r", encoding="utf-8") as f:
        lines = json.load(f)
    return jsonify({"lines": lines, "filename": files[0]})

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    print(f"Data dir: {DATA_DIR}")
    print(f"Chapters found ({LANG}): {len(available_chapters)}")
    app.run(host=args.host, port=args.port, debug=True)
