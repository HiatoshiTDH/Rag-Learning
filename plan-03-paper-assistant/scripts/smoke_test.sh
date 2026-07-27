#!/usr/bin/env bash
# Full smoke test — run from the plan-03-paper-assistant directory:
#   ./scripts/smoke_test.sh
# Automates steps 1-6 of TEST_AT_HOME.md as far as possible, printing PASS/FAIL per item.
# Steps that spend API money only run with the flag: RUN_LIVE=1 ./scripts/smoke_test.sh

set -u
cd "$(dirname "$0")/.."

PASS=0; FAIL=0; WARN=0
ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "== 1. Offline tests (no docker/keys needed) =="
if EMBED_BACKEND=fake RERANK_BACKEND=fake python -m pytest tests/ -q >/tmp/smoke_pytest.log 2>&1; then
  ok "pytest: $(tail -1 /tmp/smoke_pytest.log)"
else
  fail "pytest failed — see /tmp/smoke_pytest.log. Stopping here."
  exit 1
fi

echo "== 2. Services =="
if curl -sf -m 5 http://localhost:8070/api/isalive >/dev/null 2>&1; then
  ok "GROBID (8070) alive"
else
  fail "GROBID not responding — docker compose up -d then wait ~60s"
fi
if curl -sf -m 5 http://localhost:6333/healthz >/dev/null 2>&1; then
  ok "Qdrant server (6333) alive"
else
  warn "Qdrant server not running — embedded mode (data/qdrant) will be used, still OK"
fi

echo "== 3. Configuration =="
if [ -f .env ]; then
  ok ".env exists"
  grep -q "ANTHROPIC_API_KEY=sk" .env && ok "ANTHROPIC_API_KEY filled in" || warn "ANTHROPIC_API_KEY not filled in — the ask step will fail"
  if grep -qE "^EMBED_BACKEND=fake" .env; then
    warn "EMBED_BACKEND=fake — the pipeline runs but search is semantically meaningless"
  elif grep -q "VOYAGE_API_KEY=pa" .env; then
    ok "VOYAGE_API_KEY filled in"
  else
    warn "VOYAGE_API_KEY not filled in (or set EMBED_BACKEND=fake to try things out)"
  fi
else
  fail ".env missing — cp .env.example .env then fill in the keys"
fi

echo "== 4. Seed papers =="
SEED_COUNT=$(grep -vE '^\s*(#|$)' data/seed_papers.txt 2>/dev/null | wc -l | tr -d ' ')
if [ "$SEED_COUNT" -gt 0 ]; then
  ok "seed_papers.txt has $SEED_COUNT ids"
else
  warn "seed_papers.txt is empty — add 2-3 arXiv ids and re-run to test ingest"
fi

if [ "${RUN_LIVE:-0}" != "1" ]; then
  echo
  echo "== Live steps (ingest + ask, which call APIs) skipped =="
  echo "   Full run:  RUN_LIVE=1 ./scripts/smoke_test.sh"
else
  echo "== 5. Live ingest =="
  if [ "$SEED_COUNT" -gt 0 ] && python -m src.cli ingest; then
    ok "ingest finished"
    python -m src.cli list
    echo "== 5b. Idempotency =="
    BEFORE=$(python -c "from src.index import load_chunks; print(len(load_chunks()))")
    python -m src.cli ingest >/dev/null 2>&1
    AFTER=$(python -c "from src.index import load_chunks; print(len(load_chunks()))")
    [ "$BEFORE" = "$AFTER" ] && ok "second ingest did not duplicate ($AFTER chunks)" || fail "duplicates! $BEFORE -> $AFTER"
  else
    fail "ingest failed or seed list empty"
  fi

  echo "== 6. Live ask (1 question, costs a few cents) =="
  FIRST_ID=$(grep -vE '^\s*(#|$)' data/seed_papers.txt | head -1 | awk '{print $1}')
  if python -m src.cli ask "What problem does paper $FIRST_ID solve? Summarize in 3 sentences." --no-expand; then
    ok "ask finished — eyeball check: is there a 'Sources:' section?"
  else
    fail "ask failed — check ANTHROPIC_API_KEY"
  fi

  echo "== 7. Golden set =="
  if [ -f data/golden_set.jsonl ]; then
    python -m src.cli eval --stage full --note "smoke test" && ok "eval finished — see EXPERIMENTS.md"
  else
    warn "No data/golden_set.jsonl yet — step 6 in TEST_AT_HOME.md"
  fi
fi

echo
echo "===== RESULT: $PASS pass, $WARN warnings, $FAIL fail ====="
[ "$FAIL" -eq 0 ] || exit 1
