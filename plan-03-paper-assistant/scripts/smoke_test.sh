#!/usr/bin/env bash
# Smoke test tổng thể — chạy từ thư mục plan-03-paper-assistant:
#   ./scripts/smoke_test.sh
# Tự động các bước 1-6 trong TEST_AT_HOME.md tới mức có thể, in PASS/FAIL từng mục.
# Các bước tốn tiền API chỉ chạy khi có cờ: RUN_LIVE=1 ./scripts/smoke_test.sh

set -u
cd "$(dirname "$0")/.."

PASS=0; FAIL=0; WARN=0
ok()   { echo "  [OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "== 1. Test offline (không cần docker/key) =="
if EMBED_BACKEND=fake RERANK_BACKEND=fake python -m pytest tests/ -q >/tmp/smoke_pytest.log 2>&1; then
  ok "pytest: $(tail -1 /tmp/smoke_pytest.log)"
else
  fail "pytest fail — xem /tmp/smoke_pytest.log. Dừng ở đây."
  exit 1
fi

echo "== 2. Services =="
if curl -sf -m 5 http://localhost:8070/api/isalive >/dev/null 2>&1; then
  ok "GROBID (8070) sống"
else
  fail "GROBID không phản hồi — docker compose up -d rồi chờ ~60s"
fi
if curl -sf -m 5 http://localhost:6333/healthz >/dev/null 2>&1; then
  ok "Qdrant server (6333) sống"
else
  warn "Qdrant server không chạy — sẽ dùng embedded mode (data/qdrant), vẫn OK"
fi

echo "== 3. Cấu hình =="
if [ -f .env ]; then
  ok ".env tồn tại"
  if grep -qE "^LLM_BACKEND=openai_compat" .env; then
    ok "LLM_BACKEND=openai_compat (local/free — nhớ chạy Ollama/endpoint trước khi ask)"
  else
    grep -q "ANTHROPIC_API_KEY=sk" .env && ok "ANTHROPIC_API_KEY đã điền" || warn "ANTHROPIC_API_KEY chưa điền — bước ask sẽ fail"
  fi
  if grep -qE "^EMBED_BACKEND=fake" .env; then
    warn "EMBED_BACKEND=fake — pipeline chạy được nhưng search vô nghĩa về ngữ nghĩa"
  elif grep -qE "^EMBED_BACKEND=local" .env; then
    python -c "import sentence_transformers" 2>/dev/null \
      && ok "EMBED_BACKEND=local (bge-m3, \$0)" \
      || fail "EMBED_BACKEND=local nhưng thiếu: pip install sentence-transformers"
  elif grep -q "VOYAGE_API_KEY=pa" .env; then
    ok "VOYAGE_API_KEY đã điền"
  else
    warn "VOYAGE_API_KEY chưa điền (hoặc EMBED_BACKEND=local/fake — xem SETUP.md 3b)"
  fi
else
  fail ".env chưa có — cp .env.example .env rồi điền theo SETUP.md mục 3b"
fi

echo "== 4. Seed papers =="
SEED_COUNT=$(grep -vE '^\s*(#|$)' data/seed_papers.txt 2>/dev/null | wc -l | tr -d ' ')
if [ "$SEED_COUNT" -gt 0 ]; then
  ok "seed_papers.txt có $SEED_COUNT id"
else
  warn "seed_papers.txt trống — thêm 2-3 arXiv id rồi chạy lại để test ingest"
fi

if [ "${RUN_LIVE:-0}" != "1" ]; then
  echo
  echo "== Các bước live (ingest + ask, có gọi API) bị bỏ qua =="
  echo "   Chạy đầy đủ:  RUN_LIVE=1 ./scripts/smoke_test.sh"
else
  echo "== 5. Ingest live =="
  if [ "$SEED_COUNT" -gt 0 ] && python -m src.cli ingest; then
    ok "ingest chạy xong"
    python -m src.cli list
    echo "== 5b. Idempotency =="
    BEFORE=$(python -c "from src.index import load_chunks; print(len(load_chunks()))")
    python -m src.cli ingest >/dev/null 2>&1
    AFTER=$(python -c "from src.index import load_chunks; print(len(load_chunks()))")
    [ "$BEFORE" = "$AFTER" ] && ok "ingest lần 2 không duplicate ($AFTER chunk)" || fail "duplicate! $BEFORE -> $AFTER"
  else
    fail "ingest lỗi hoặc seed trống"
  fi

  echo "== 6. Ask live (1 câu, tốn vài cent) =="
  FIRST_ID=$(grep -vE '^\s*(#|$)' data/seed_papers.txt | head -1 | awk '{print $1}')
  if python -m src.cli ask "Paper $FIRST_ID giải quyết vấn đề gì? Tóm tắt 3 câu." --no-expand; then
    ok "ask chạy xong — kiểm tra bằng mắt: có mục 'Nguồn:' không?"
  else
    fail "ask lỗi — kiểm tra ANTHROPIC_API_KEY"
  fi

  echo "== 7. Golden set =="
  if [ -f data/golden_set.jsonl ]; then
    python -m src.cli eval --stage full --note "smoke test" && ok "eval chạy xong — xem EXPERIMENTS.md"
  else
    warn "Chưa có data/golden_set.jsonl — bước 6 trong TEST_AT_HOME.md"
  fi
fi

echo
echo "===== KẾT QUẢ: $PASS pass, $WARN cảnh báo, $FAIL fail ====="
[ "$FAIL" -eq 0 ] || exit 1
