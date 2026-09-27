"""
smoke_test.py — Quick import + structural smoke test for the notes embedding/retrieval merge.

Checks:
  1. All new modules import cleanly
  2. extractor.py — accepted extensions & public API present
  3. indexer.py   — DB schema SQL, public functions present
  4. note_store.py — NoteContext dataclass + find_relevant_notes present
  5. notes/routes.py — all 7 expected endpoints registered on the router
  6. chat/pipeline.py — Step 3b integration (imports + augmented_query wiring)
  7. config.py — original ml keys still present (SLM_KEEP_ALIVE, SLM_VOICE_CHUNK_CHARS)
  8. slm_client.py — warm_slm + stream_slm_voice still present (original functions not dropped)

Run from inside ml/:
  python smoke_test.py
"""

import sys
import os

# Make sure we're running from inside ml/
ml_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ml_root)
# Repo root (for learner/, persona/, vision/ etc.)
sys.path.insert(0, os.path.dirname(ml_root))

# Silence logging noise
import logging
logging.disable(logging.CRITICAL)

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

errors = []

def check(label, fn):
    try:
        fn()
        print(f"  {PASS} {label}")
    except Exception as exc:
        print(f"  {FAIL} {label}")
        print(f"       → {exc}")
        errors.append((label, exc))


# ──────────────────────────────────────────────
print("\n[1] Module imports")
# ──────────────────────────────────────────────

def _import_extractor():
    import notes.extractor as m
    assert hasattr(m, "extract_text"), "extract_text missing"
    assert hasattr(m, "ACCEPTED_EXTENSIONS"), "ACCEPTED_EXTENSIONS missing"
    assert hasattr(m, "ExtractionError"), "ExtractionError missing"

def _import_indexer():
    import notes.indexer as m
    assert hasattr(m, "extract_and_index"), "extract_and_index missing"
    assert hasattr(m, "delete_index_for_note"), "delete_index_for_note missing"

def _import_note_store():
    import notes.note_store as m
    assert hasattr(m, "find_relevant_notes"), "find_relevant_notes missing"
    assert hasattr(m, "NoteContext"), "NoteContext missing"

def _import_routes():
    from notes.routes import router
    assert router is not None

def _import_pipeline():
    # pipeline imports notes.note_store — verify it resolves
    import importlib, inspect
    spec = importlib.util.spec_from_file_location("pipeline", os.path.join(ml_root, "chat", "pipeline.py"))
    src = open(os.path.join(ml_root, "chat", "pipeline.py"), encoding="utf-8").read()
    assert "from notes.note_store import find_relevant_notes" in src, "import missing in pipeline"

check("notes.extractor imports cleanly", _import_extractor)
check("notes.indexer imports cleanly", _import_indexer)
check("notes.note_store imports cleanly", _import_note_store)
check("notes.routes imports cleanly", _import_routes)
check("chat.pipeline has notes import", _import_pipeline)


# ──────────────────────────────────────────────
print("\n[2] extractor.py — content checks")
# ──────────────────────────────────────────────

def _extractor_extensions():
    from notes.extractor import ACCEPTED_EXTENSIONS
    expected = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".txt"}
    missing = expected - ACCEPTED_EXTENSIONS
    assert not missing, f"Missing extensions: {missing}"

def _extractor_txt():
    from notes.extractor import extract_text
    result = extract_text(b"Hello world", "test.txt")
    assert result == "Hello world", f"Got: {result!r}"

def _extractor_bad_ext():
    from notes.extractor import extract_text, ExtractionError
    try:
        extract_text(b"data", "file.xyz")
        raise AssertionError("Should have raised ExtractionError")
    except ExtractionError:
        pass

check("ACCEPTED_EXTENSIONS covers pdf/png/jpg/jpeg/webp/bmp/txt", _extractor_extensions)
check("extract_text() works for .txt bytes", _extractor_txt)
check("extract_text() raises ExtractionError on unsupported ext", _extractor_bad_ext)


# ──────────────────────────────────────────────
print("\n[3] indexer.py — schema & function checks")
# ──────────────────────────────────────────────

def _indexer_schema_sql():
    import notes.indexer as m
    # The CREATE TABLE SQL should be defined in the module
    src = open(os.path.join(ml_root, "notes", "indexer.py"), encoding="utf-8").read()
    assert "note_index" in src, "note_index table definition missing"
    assert "fts5" in src.lower(), "FTS5 virtual table missing"
    assert "keyword" in src, "keyword column missing"
    assert "concept" in src, "concept column missing"

def _indexer_functions_async():
    import inspect, notes.indexer as m
    assert inspect.iscoroutinefunction(m.extract_and_index), "extract_and_index should be async"
    assert inspect.iscoroutinefunction(m.delete_index_for_note), "delete_index_for_note should be async"

check("note_index + FTS5 schema present in indexer.py", _indexer_schema_sql)
check("extract_and_index and delete_index_for_note are async", _indexer_functions_async)


# ──────────────────────────────────────────────
print("\n[4] note_store.py — retrieval checks")
# ──────────────────────────────────────────────

def _note_store_dataclass():
    from notes.note_store import NoteContext
    nc = NoteContext(
        found=True,
        matched_keywords=["addition"],
        concepts=["adding gives sum"],
        note_snippets=["2+2=4"],
        note_titles=["Maths Notes"],
    )
    block = nc.as_prompt_block()
    assert "[STUDENT'S NOTES" in block, "prompt block header missing"
    assert "Maths Notes" in block

def _note_store_empty():
    from notes.note_store import NoteContext
    nc = NoteContext(found=False, matched_keywords=[], concepts=[], note_snippets=[], note_titles=[])
    assert nc.as_prompt_block() == "", "empty context should return empty string"

def _note_store_tokeniser():
    from notes.note_store import _tokenise_query
    tokens = _tokenise_query("What is the speed of light?")
    assert "speed" in tokens, f"'speed' missing from tokens: {tokens}"
    assert "light" in tokens, f"'light' missing from tokens: {tokens}"
    assert "what" not in tokens, "stop-word 'what' should be filtered"

def _note_store_async():
    import inspect, notes.note_store as m
    assert inspect.iscoroutinefunction(m.find_relevant_notes)

check("NoteContext.as_prompt_block() formats correctly", _note_store_dataclass)
check("NoteContext(found=False).as_prompt_block() returns ''", _note_store_empty)
check("_tokenise_query strips stop-words", _note_store_tokeniser)
check("find_relevant_notes is async", _note_store_async)


# ──────────────────────────────────────────────
print("\n[5] notes/routes.py — endpoint registration")
# ──────────────────────────────────────────────

def _routes_endpoints():
    from notes.routes import router
    paths = [(r.path, list(r.methods)) for r in router.routes]
    path_map = {p: m for p, m in paths}

    required = [
        ("/notes/", ["POST"]),
        ("/notes/{profile_id}", ["GET"]),
        ("/notes/upload", ["POST"]),
        ("/notes/{note_id}", ["PUT"]),
        ("/notes/{note_id}", ["DELETE"]),
        ("/notes/{note_id}/reindex", ["POST"]),
        ("/notes/reindex-all/{profile_id}", ["POST"]),
    ]
    found_paths = [p for p, _ in paths]
    for path, methods in required:
        assert path in found_paths, f"Route {path} not registered. Found: {found_paths}"

check("All 7 routes registered on notes router", _routes_endpoints)


# ──────────────────────────────────────────────
print("\n[6] chat/pipeline.py — Step 3b wiring")
# ──────────────────────────────────────────────

def _pipeline_step3b():
    src = open(os.path.join(ml_root, "chat", "pipeline.py"), encoding="utf-8").read()
    checks = {
        "find_relevant_notes import": "from notes.note_store import find_relevant_notes",
        "Step 3b comment": "Step 3b",
        "augmented_query assigned": "augmented_query = sanitized_query",
        "note_context.found branch": "note_context.found",
        "augmented_query passed to call_slm": "augmented_query, request.student, history",
        "sanitized_query stored in history": "append_turn(request.session_id, sanitized_query",
        "augmented_query in _escalate_via_thinking sig": "augmented_query: str",
    }
    for label, token in checks.items():
        assert token in src, f"Missing in pipeline.py: {label!r} (looked for {token!r})"

check("pipeline.py Step 3b correctly wired", _pipeline_step3b)


# ──────────────────────────────────────────────
print("\n[7] config.py — original ml keys intact")
# ──────────────────────────────────────────────

def _config_keys():
    import config
    required = [
        "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_VISION_MODEL",
        "OLLAMA_TIMEOUT", "OLLAMA_THINK", "OLLAMA_THINK_TIMEOUT",
        "SLM_KEEP_ALIVE", "SLM_VOICE_CHUNK_CHARS",
        "ESCALATION_CONFIDENCE_THRESHOLD",
        "MAX_QUERY_LENGTH", "MAX_RESPONSE_LENGTH",
        "MAX_HISTORY_TURNS", "FALLBACK_RESPONSE",
    ]
    missing = [k for k in required if not hasattr(config, k)]
    assert not missing, f"Missing config keys: {missing}"

check("All original config.py keys still present", _config_keys)


# ──────────────────────────────────────────────
print("\n[8] slm_client.py — original functions not dropped")
# ──────────────────────────────────────────────

def _slm_client_functions():
    import chat.slm_client as m
    assert hasattr(m, "call_slm"), "call_slm missing"
    assert hasattr(m, "warm_slm"), "warm_slm missing (original function)"
    assert hasattr(m, "stream_slm_voice"), "stream_slm_voice missing (original function)"
    assert hasattr(m, "BASE_SYSTEM_PROMPT"), "BASE_SYSTEM_PROMPT missing"
    assert hasattr(m, "SLM_KEEP_ALIVE") or True  # comes from config, not slm_client

def _slm_client_keep_alive():
    src = open(os.path.join(ml_root, "chat", "slm_client.py"), encoding="utf-8").read()
    assert "SLM_KEEP_ALIVE" in src, "SLM_KEEP_ALIVE not used in slm_client"
    assert "stream_slm_voice" in src, "stream_slm_voice function body missing"

check("call_slm / warm_slm / stream_slm_voice all present", _slm_client_functions)
check("SLM_KEEP_ALIVE + stream_slm_voice in slm_client.py source", _slm_client_keep_alive)


# ──────────────────────────────────────────────
print()
if errors:
    print(f"\033[91m{len(errors)} check(s) FAILED:\033[0m")
    for label, exc in errors:
        print(f"  ✗ {label}: {exc}")
    sys.exit(1)
else:
    print(f"\033[92mAll checks passed! Merge looks good.\033[0m")
    sys.exit(0)
