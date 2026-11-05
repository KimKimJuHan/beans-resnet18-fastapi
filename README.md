# FastAPI Beans ResNet18 — 동기·비동기 분류 서비스 (교과 9 평가)

콩잎 사진을 `angular_leaf_spot` / `bean_rust` / `healthy` 중 하나로 분류합니다. `microsoft/resnet-18`을 Head-only로 파인튜닝했고, FastAPI 동기 API와 Celery 비동기 작업 큐로 서빙합니다.

- 결과 요약: [reports/08_최종기술보고서.md](reports/08_최종기술보고서.md)

## 1. 환경

| 항목 | 사용한 값 |
|---|---|
| OS | Windows + WSL2 Ubuntu |
| Python | 3.11 (예: `conda create -n py311 python=3.11` → `python -m venv ~/venvs/beans311`) |
| Docker | Docker Desktop (WSL Integration 켬) — Redis 6379, PostgreSQL 5432 |
| Python 프로세스 | FastAPI(Uvicorn), Celery Worker — WSL 가상환경에서 실행 |
| GPU | 학습에만 사용 (선택). 서빙은 CPU |

## 2. 데이터 준비

```bash
# 제공 원본 → beans_source/{train,validation,test}/{angular_leaf_spot,bean_rust,healthy}/ (보존)
mkdir -p dataset
cp -r ../beans_source/train      dataset/train
cp -r ../beans_source/validation dataset/val     # 제공 코드는 'val' 폴더를 읽습니다
cp -r ../beans_source/test       dataset/test    # 학습에 사용하지 않음
python tools/check_dataset.py --root ../beans_source --out reports/data   # 개수·중복 점검
```
- 압축을 풀었을 때 `train/train/<클래스>`처럼 겹쳐 있으면 한 단계 올려서 정리하세요.
- 데이터셋은 공개·배포 조건을 확인한 뒤 공유하세요. 이 저장소에는 포함하지 않습니다.

## 3. 설치와 모델 준비

```bash
source ~/venvs/beans311/bin/activate
pip install -r requirements.txt
cp .env.example .env                    # MODEL_PATH=artifacts/beans_resnet18
python -m training.finetune --data dataset --output artifacts/beans_resnet18 \
  --epochs 3 --batch-size 8 --freeze-backbone
# (선택) Full Fine-tuning 비교
python -m training.finetune --data dataset --output artifacts/beans_resnet18_full \
  --epochs 3 --batch-size 8 --lr 0.00005
```

## 4. 실행 순서 (터미널 3개, 모두 `source ~/venvs/beans311/bin/activate && cd <프로젝트>` 후)

| 터미널 | 명령 | 확인 |
|---|---|---|
| 1 | `docker compose up -d redis postgres` → `docker compose exec redis redis-cli ping` | `PONG`, `docker compose ps`에 healthy |
| 2 | `celery -A ai.celery_app:celery_app worker --loglevel=info --pool=solo --concurrency=1` | `celery@... ready.` |
| 3 | `uvicorn main:app --host 127.0.0.1 --port 8000` | `Application startup complete` |

- `compose.yaml`에는 `web`·`worker` 서비스도 있지만, 이 평가에서는 **redis·postgres만** Docker로 띄웠습니다.
- 접속 주소: 동기 http://127.0.0.1:8000/vision/sync/ · 비동기 http://127.0.0.1:8000/vision/async/ · Swagger http://127.0.0.1:8000/docs
- `MODEL_PATH`를 바꾸면 FastAPI와 Worker를 **둘 다** 다시 켜세요.
- `docker compose down -v`는 DB·Redis 데이터를 지우니 쓰지 마세요.

## 5. 확인할 응답

- `/health` → `{"status":"ok"}`
- 동기 POST → `top1`, `all`, `inference_ms`, `cache_hit`
- 비동기 POST → **202** + `job_id` / GET `/api/async/jobs/{id}/` → `status: done`
- PostgreSQL: `docker compose exec postgres psql -U vision_user -d vision_db -c 'SELECT id,status,top1_label,cache_hit FROM image_jobs ORDER BY id DESC LIMIT 10;'`
- 캐시 비우기 (MISS를 다시 재려면): `docker compose exec redis redis-cli -n 1 FLUSHDB`

## 6. 제공 코드 외 추가 스크립트 (제공 코드는 수정하지 않음)

| 파일 | 용도 |
|---|---|
| `tools/check_dataset.py` | 클래스별 개수, MD5 중복·누출 점검 |
| `tools/collect_evidence.sh` | API·Redis·DB 증빙을 텍스트로 저장 → `reports/evidence/cli/` |
| `tools/measure_timings.py` | 동기/비동기 × MISS/HIT 응답시간 측정 → `reports/data/timings.csv` |
| `tools/sync_results.sh` | (WSL 내부 폴더에서 작업할 때) 결과를 Windows 폴더로 복사 — 이번에는 사용하지 않음 |
| `training/evaluate.py` | 정확도·P/R/F1·혼동행렬 평가. B 모델로 Validation(재현 확인) → Test 1회 실행 → `reports/data/eval_*` |

## 7. 결과물 위치

- 보고서: `reports/01_*.md` ~ `reports/08_*.md`
- 측정 원본: `reports/data/timings.csv`, `dataset_*.csv`
- 증빙: `reports/evidence/` (화면 캡처, 로그), `reports/evidence/cli/` (명령 결과 원문)
- 학습 결과: `artifacts/beans_resnet18/training_report.json`, `artifacts/beans_resnet18_full/training_report.json`

## 8. 제출과 보안

- `.env`, 비밀번호, API 키는 GitHub에 올리지 않습니다 (`.gitignore` 포함).
- `dataset/`, `artifacts/`(모델 44.8MB), `media/jobs/`는 저장소에서 빼고, 허용된 경로로 따로 전달합니다.
- 빠진 파일은 2·3절 명령으로 다시 만들 수 있습니다.
- `compose.yaml`의 DB 비밀번호(`vision_pass`)는 교재 실습용 값입니다. 운영 환경에서는 바꿔야 합니다.
