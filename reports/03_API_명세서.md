# 03. API 명세서

> 모든 응답 JSON은 실제 실행 결과에서 옮겨 적었다 (2026-11-04). 점수는 소수 4자리로 줄였다. 원문은 증빙 파일에 있다.

## 1. API 목록

| API ID | Method | URL | 요청 형태 | 성공 HTTP | 주요 응답 | 실패 HTTP |
|---|---|---|---|---:|---|---|
| API-01 | GET | `/health` | 없음 | 200 | `status` | 서버가 꺼져 있으면 HTTP 응답 없음 |
| API-02 | POST | `/api/sync/classify/` | `multipart/form-data` / `image` | 200 | `model_id`, `top1`, `all`, `inference_ms`, `cache_hit` | 400, 413 |
| API-03 | POST | `/api/async/classify/` | `multipart/form-data` / `image` | **202** | `job_id`, `status`, `check_url` | 400, 413, 503 |
| API-04 | GET | `/api/async/jobs/{job_id}/` | 정수형 `job_id` | 200 | `job_id`, `status`, `model_id`, `top1`, `all`, `inference_ms`, `cache_hit`, `error_message` | 404 |
| WEB-01 | GET | `/vision/sync/` | 없음 | 200 | HTML | — |
| WEB-02 | GET | `/vision/async/` | 없음 | 200 | HTML | — |
| DOC | GET | `/docs` | 없음 | 200 | Swagger UI | — |

- `202`는 **작업 접수**다. 작업이 **완료**됐는지는 API-04 응답의 `status: "done"`으로 판단한다.
- 응답 필드 이름은 `all`이다. `all_scores`는 DB 컬럼 이름이다.

## 2. 요청 조건 (API-02·03 공통, `ai/services.py`)

| 항목 | 조건 | 어기면 |
|---|---|---|
| 필드 이름 | `image` | 422 (FastAPI 기본 검증, 실행 확인은 미실시) |
| 크기 | 1바이트 이상, 5MB 이하 | 413 (5MB 초과, 실행 확인) / 400 (0바이트, 코드상 동작이고 실행은 미실시) |
| 형식 | 실제 내용이 JPEG·PNG·WEBP (확장자가 아니라 내용으로 판별) | 400 |
| 해상도 | 1,200만 픽셀 이하 | 400 |
| 503 | Redis 브로커에 작업을 등록하지 못함 → DB 행을 `failed`로 기록 | 실환경 **미실시** (모의 테스트에만 있음) |

## 3. 실제 응답

**API-01** — `cli/04_health.txt`
```http
HTTP/1.1 200 OK
{"status":"ok"}
```

**API-02 성공 (MISS)** — `bean_rust_test.0.jpg`, `sync_rust.png`
```json
{
  "model_id": "artifacts/beans_resnet18",
  "top1": {"label": "bean_rust", "score": 0.6051},
  "all": [
    {"label": "bean_rust", "score": 0.6051},
    {"label": "healthy", "score": 0.2607},
    {"label": "angular_leaf_spot", "score": 0.1342}
  ],
  "inference_ms": 21.27,
  "cache_hit": false
}
```

**API-02 성공 (HIT, 같은 파일 다시 보냄)** — `sync_rust_hit.png`: 점수는 같고 `"inference_ms": null, "cache_hit": true`이다. HIT의 `null`은 추론을 **생략했다**는 뜻이며 0ms가 아니다.

**API-03 접수** — `cli/05_async_202.txt`
```http
HTTP/1.1 202 Accepted
{"job_id":2,"status":"queued","check_url":"/api/async/jobs/2/"}
```

**API-04 처리 중 → 완료** — `cli/06_async_job_poll.txt`
```json
{"job_id":2,"status":"running","model_id":"artifacts/beans_resnet18","top1":null,"all":null,"inference_ms":null,"cache_hit":null,"error_message":null}
```
```json
{
  "job_id": 2, "status": "done", "model_id": "artifacts/beans_resnet18",
  "top1": {"label": "bean_rust", "score": 0.6051},
  "all": [{"label": "bean_rust", "score": 0.6051}, {"label": "healthy", "score": 0.2607}, {"label": "angular_leaf_spot", "score": 0.1342}],
  "inference_ms": 3059.36, "cache_hit": false, "error_message": null
}
```
- 이 `inference_ms` 3059.36은 Worker 프로세스가 모델을 처음 불러온 시간까지 포함한 값이다 ([산출물 6](06_성능비교_보고서.md) 참고).

**API-04 대기 중 (Worker 정지)** — `async_worker_stopped_queued.png`
```json
{"job_id":3,"status":"queued","model_id":"artifacts/beans_resnet18","top1":null,"all":null,"inference_ms":null,"cache_hit":null,"error_message":null}
```

**오류 응답**

| 상황 | HTTP | 응답 원문 | 증빙 |
|---|---:|---|---|
| 동기에 `.txt` 업로드 | 400 | `{"detail":"올바른 이미지 파일이 아닙니다."}` | `cli/07_err_400_sync_txt.txt` |
| 비동기에 `.txt` 업로드 | 400 | `{"detail":"올바른 이미지 파일이 아닙니다."}` | `cli/08_err_400_async_txt.txt` |
| 동기에 5MB+1바이트 업로드 | 413 | `{"detail":"5MB 이하 파일만 허용합니다."}` | `cli/09_err_413_sync_big.txt` |
| 없는 작업 `999999` 조회 | 404 | `{"detail":"해당 작업이 없습니다."}` | `cli/10_err_404_job.txt` |

## 4. 실행 근거표

| 검증 ID | 테스트 입력 | 실제 상태코드 | 첨부 증빙 |
|---|---|---:|---|
| API-01-T01 | GET `/health` | 200 | `evidence/cli/04_health.txt` |
| API-02-T01 | `angular_leaf_spot_test.0.jpg` (MISS) | 200 | `evidence/sync_angular.png` |
| API-02-T02 | `bean_rust_test.0.jpg` (MISS) | 200 | `evidence/sync_rust.png` |
| API-02-T03 | `healthy_test.0.jpg` (MISS) | 200 | `evidence/sync_healthy.png` |
| API-02-T04 | `bean_rust_test.0.jpg` 재요청 (HIT) | 200 | `evidence/sync_rust_hit.png` |
| API-02-T05 | `.txt` | 400 | `evidence/cli/07_err_400_sync_txt.txt` |
| API-02-T06 | 5MB+1B | 413 | `evidence/cli/09_err_413_sync_big.txt` |
| API-03-T01 | `bean_rust_test.0.jpg` | 202 | `evidence/cli/05_async_202.txt` |
| API-03-T02 | `.txt` | 400 | `evidence/cli/08_err_400_async_txt.txt` |
| API-04-T01 | `job_id=2` | 200 (running → done) | `evidence/cli/06_async_job_poll.txt` |
| API-04-T02 | `job_id=1` (브라우저) | 200 (done) | `evidence/async_done_hit.png` |
| API-04-T03 | `job_id=999999` | 404 | `evidence/cli/10_err_404_job.txt` |
| WEB-01·02 | 화면 접속 | 200 | `evidence/uvicorn.log` |
