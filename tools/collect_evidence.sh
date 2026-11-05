#!/usr/bin/env bash
# [추가 보조 스크립트 — 제공 코드 아님] 실환경 API·Redis·PostgreSQL 증빙을 텍스트로 저장한다.
# 전제: docker compose(redis, postgres) + Celery Worker + FastAPI(127.0.0.1:8000) 실행 중
# 사용: 프로젝트 루트에서  bash tools/collect_evidence.sh
set -uo pipefail
API=http://127.0.0.1:8000
OUT=reports/evidence/cli; mkdir -p "$OUT"
IMG_RUST=dataset/test/bean_rust/bean_rust_test.0.jpg
IMG_ALS=dataset/test/angular_leaf_spot/angular_leaf_spot_test.0.jpg
log(){ echo -e "\n===== $* =====" ; }
run(){ # run <파일명> <설명> <명령...> : 명령과 결과를 함께 저장
  local f="$OUT/$1"; shift; local d="$1"; shift
  { echo "# $d"; echo "# 실행시각: $(date '+%F %T %Z')"; echo "\$ $*"; echo; bash -c "$*" 2>&1; } > "$f"
  echo "[저장] $f"; }

log "1. 인프라 상태"
run 01_compose_ps.txt      "Docker 컨테이너 상태"        "docker compose ps"
run 02_redis_ping.txt      "Redis 연결"                  "docker compose exec -T redis redis-cli ping"
run 03_pg_isready.txt      "PostgreSQL 준비 상태"        "docker compose exec -T postgres pg_isready -U vision_user -d vision_db"
run 04_health.txt          "FastAPI 헬스"                "curl -s -i $API/health"

log "2. 비동기 MISS (캐시 비운 뒤 접수 → 완료까지 폴링)"
docker compose exec -T redis redis-cli -n 1 FLUSHDB >/dev/null
RESP=$(curl -s -i -F "image=@$IMG_RUST" $API/api/async/classify/)
{ echo "# 비동기 접수 (캐시 FLUSHDB 직후 = MISS 조건), 이미지: $IMG_RUST"; echo "\$ curl -i -F image=@$IMG_RUST $API/api/async/classify/"; echo; echo "$RESP"; } > "$OUT/05_async_202.txt"
JOB=$(echo "$RESP" | grep -o '"job_id":[0-9]*' | grep -o '[0-9]*')
echo "[저장] $OUT/05_async_202.txt  (job_id=$JOB)"
{ echo "# 상태 폴링 (1초 간격, 최대 30회) job_id=$JOB"; for i in $(seq 1 30); do
    R=$(curl -s $API/api/async/jobs/$JOB/); echo "[$(date +%T)] try=$i $R"
    echo "$R" | grep -qE '"status":"(done|failed)"' && break; sleep 1; done; } > "$OUT/06_async_job_poll.txt"
echo "[저장] $OUT/06_async_job_poll.txt"

log "3. 오류 처리"
printf 'not an image' > /tmp/bad.txt
head -c $((5*1024*1024+1)) /dev/zero > /tmp/big.jpg
run 07_err_400_sync_txt.txt   "동기 .txt 업로드 → 400 기대"     "curl -s -i -F 'image=@/tmp/bad.txt;type=text/plain' $API/api/sync/classify/"
run 08_err_400_async_txt.txt  "비동기 .txt 업로드 → 400 기대"   "curl -s -i -F 'image=@/tmp/bad.txt;type=text/plain' $API/api/async/classify/"
run 09_err_413_sync_big.txt   "동기 5MB 초과 → 413 기대"        "curl -s -i -F 'image=@/tmp/big.jpg;type=image/jpeg' $API/api/sync/classify/"
run 10_err_404_job.txt        "없는 job_id → 404 기대"          "curl -s -i $API/api/async/jobs/999999/"

log "4. 동기 MISS→HIT 연속 (CLI, 캐시 비운 뒤 같은 파일 2회)"
docker compose exec -T redis redis-cli -n 1 FLUSHDB >/dev/null
{ echo "# 캐시 FLUSHDB 직후 같은 파일 2회 동기 요청. time_total=클라이언트 측정 HTTP 전체시간(초)"; for n in 1 2; do
    echo "--- 요청 $n"; curl -s -w '\n[time_total=%{time_total}s http=%{http_code}]\n' -F "image=@$IMG_ALS" $API/api/sync/classify/; done; } > "$OUT/11_sync_miss_hit.txt"
echo "[저장] $OUT/11_sync_miss_hit.txt"
run 12_redis_cache_keys.txt "Redis DB1 캐시 키·TTL" "docker compose exec -T redis redis-cli -n 1 --scan --pattern 'vision:classify:*' | while read k; do echo \"\$k ttl=\$(docker compose exec -T redis redis-cli -n 1 ttl \$k </dev/null)\"; done"

log "5. PostgreSQL"
run 13_db_schema.txt "image_jobs 테이블 구조" "docker compose exec -T postgres psql -U vision_user -d vision_db -c '\\d image_jobs'"
run 14_db_rows.txt   "image_jobs 최근 10행"   "docker compose exec -T postgres psql -U vision_user -d vision_db -c 'SELECT id, status, image_path, model_id, top1_label, round(top1_score::numeric,4) AS score, inference_ms, cache_hit, error_message, created_at, updated_at FROM image_jobs ORDER BY id DESC LIMIT 10;'"
run 15_db_status_count.txt "상태별 개수" "docker compose exec -T postgres psql -U vision_user -d vision_db -c 'SELECT status, count(*) FROM image_jobs GROUP BY status;'"
run 16_media_jobs.txt "업로드 원본 저장 위치" "ls -la media/jobs | head -20"
rm -f /tmp/bad.txt /tmp/big.jpg
echo -e "\n완료 → $OUT/"
