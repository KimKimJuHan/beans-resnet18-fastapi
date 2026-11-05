# ResNet18 콩잎 3클래스 Fine-tuning 결과보고서

- 평가 대상: 콩잎 이미지 3종 분류 (`angular_leaf_spot`, `bean_rust`, `healthy`)
- 기준 모델: `microsoft/resnet-18` (Hugging Face 사전학습 가중치, 모델 카드 라이선스 Apache-2.0)
- 학습 방식: **Head-only Fine-tuning** (`--freeze-backbone`: Backbone 고정, 새 3클래스 분류 헤드만 학습)
- 입력 데이터: `dataset/train`, `dataset/val`
- 보관 데이터: `dataset/test` (학습·모델 선택에 사용하지 않음)
- 모델 저장 위치: `artifacts/beans_resnet18/`
- 실험 상태: **실행 완료** (2026-11-04)

## 1. 데이터 구성

정답은 제공 데이터의 **폴더 라벨**을 따른다. 개수는 `tools/check_dataset.py`(제공 코드 외 추가 점검 스크립트)로 셌다.

| 클래스 | Train | Validation | Test |
|---|---:|---:|---:|
| angular_leaf_spot | 345 | 44 | 43 |
| bean_rust | 348 | 45 | 43 |
| healthy | 341 | 44 | 42 |
| **합계** | **1,034** | **133** | **128** |

- 학습 로그에 찍힌 개수(`Train: 1034, Val: 133`)와 `training_report.json`의 `train_count`·`val_count`가 위 표와 같다.

### 1-1. 원본 → 실행용 폴더 매핑

| 제공 원본 (`beans_source/`, 보존) | 코드 실행용 (`dataset/`) | 용도 |
|---|---|---|
| `train/` | `train/` | 학습 |
| `validation/` | **`val/`** (제공 코드가 `val`을 읽음) | 검증·best 모델 선택 |
| `test/` | `test/` | 학습 미사용 |

### 1-2. 데이터 점검 결과

| 점검 항목 | 방법 | 결과 |
|---|---|---|
| 클래스 폴더 누락 | 3개 Split × 3개 클래스 폴더 존재 확인 | 없음 |
| Split 간 같은 이미지 (누출) | 전체 1,295장 MD5 해시 비교 | **0건** |
| 클래스 간 같은 이미지 (라벨 충돌) | 같은 방법 | 0건 |
| 이미지가 아닌 파일 | 확장자 검사 | 1개: `train/healthy/healthy_train.120tore` (macOS `.DS_Store` 형식). `finetune.py`가 확장자(`.jpg/.jpeg/.png/.webp`)로 걸러내므로 학습에서 제외됨 |
| 비슷한 사진 (크기·밝기만 다른 것) | dHash 64bit 해밍거리, Split 간 전체 쌍 (`tools/check_near_duplicates.py`, 추가 스크립트) | 거리 5 이하 **0쌍**. 가장 가까운 거리 6 쌍도 육안상 다른 사진 (`evidence/near_dup_closest_pair.png`, `data/near_duplicates.txt`) |
| 이미지 형식 | 표본 확인 | 500×500 JPG |

- 근거: `reports/data/dataset_check.md`, `dataset_counts.csv`, `dataset_duplicates.csv`
- 작업 중 문제: 제공 압축본을 풀었을 때 `train/train/<클래스>`처럼 한 단계 겹친 폴더가 생겼다. 학습 전에 한 단계 올려서 `train/<클래스>` 구조로 정리했다.

## 2. 실행 설정

```bash
python -m training.finetune --data dataset --output artifacts/beans_resnet18 \
  --epochs 3 --batch-size 8 --freeze-backbone
```

| 파라미터 | 값 |
|---|---|
| base_model | microsoft/resnet-18 |
| epochs | 3 |
| batch_size | 8 |
| learning_rate | 0.0002 (제공 코드 기본값) |
| freeze_backbone | True |
| optimizer | AdamW (학습 대상 파라미터만) |
| output | artifacts/beans_resnet18 |
| seed | 42 (제공 코드) |
| 학습 장치 | NVIDIA RTX 3060 12GB (`torch.cuda.is_available()=True`, 코드가 cuda를 자동 선택) |
| 실행환경 | Windows + WSL2, Python 3.11.17, torch 2.15.0+cu132, transformers 4.57.6 |
| 제공 코드 수정 | 없음 (`training/finetune.py` 원본 그대로) |

**출력층 교체 확인 (학습 로그 원문):**
```text
- classifier.1.bias: found shape torch.Size([1000]) in the checkpoint and torch.Size([3]) in the model instantiated
- classifier.1.weight: found shape torch.Size([1000, 512]) in the checkpoint and torch.Size([3, 512]) in the model instantiated
```
→ ImageNet 1,000개 출력층(512→1000)이 3개 출력층(512→3)으로 바뀌고 새로 초기화됐다.

## 3. 학습 결과

| Epoch | Train Loss | Validation Accuracy |
|---|---:|---:|
| 1 | 0.9924 | 0.6617 |
| 2 | 0.8108 | **0.7669** |
| 3 | 0.7078 | 0.7669 |

- **Best Validation Accuracy: 0.7669 (76.69%, 133장 중 102장 정답)**
- **저장된 모델은 Epoch 2의 가중치다.** 제공 코드는 정확도가 이전 best보다 *클 때만* 저장하는데, Epoch 3은 Epoch 2와 같아서(0.7669) 덮어쓰지 않았다. 파일 수정 시각도 이와 맞는다 (`model.safetensors` 10:39:59, `training_report.json` 10:40:17).
- (A 모델) Test Accuracy: **미측정** (기본 코드에 Test 평가 절차 없음)
- (A 모델) 혼동행렬·Precision·Recall·F1: **미측정** — 최종 선택 모델 B의 Test 결과는 7절
- 관찰: 3 epoch 동안 Train Loss가 계속 내려갔다(0.99 → 0.71). 아직 학습이 덜 된 상태(underfitting)로 보인다. 다만 epoch 수나 학습 방식을 바꾼 비교 실험은 하지 않았으므로, 성능이 오를지는 확인되지 않았다.

## 4. 생성 파일 확인

| 파일 | 크기 | 확인 |
|---|---:|---|
| `config.json` | 808 B | ✅ `id2label`: 0 angular_leaf_spot / 1 bean_rust / 2 healthy |
| `model.safetensors` | 44.8 MB | ✅ |
| `preprocessor_config.json` | 352 B | ✅ |
| `training_report.json` | 468 B | ✅ 위 표의 수치와 같음 |

- 증빙: `reports/evidence/train_log_headonly.txt` (학습 터미널 출력 원문), `artifacts/beans_resnet18/training_report.json`
- 학습 로그는 터미널 출력을 그대로 저장한 텍스트 파일로 대신함. 모델 폴더 파일 목록·크기는 위 표로 기록

## 5. 서비스 연결 확인

- MODEL_PATH: `artifacts/beans_resnet18` (`.env`) — API 응답 `model_id`도 같은 값
- 응답 라벨이 ImageNet 1,000개 클래스가 아니라 **3개 클래스**로 나옴 → 학습한 모델이 서비스에 연결됨

| 이미지 (Test 폴더) | 폴더 라벨 | 동기 API top1 | score | 일치 | 증빙 |
|---|---|---|---:|---|---|
| angular_leaf_spot_test.0.jpg | angular_leaf_spot | angular_leaf_spot | 0.4623 | ✅ (확신도 낮음) | `evidence/sync_angular.png` |
| bean_rust_test.0.jpg | bean_rust | bean_rust | 0.6051 | ✅ | `evidence/sync_rust.png` |
| healthy_test.0.jpg | healthy | healthy | 0.6369 | ✅ | `evidence/sync_healthy.png` |

- 위 3장은 서비스 연결을 확인하려고 고른 표본이다. Test 정확도가 아니다.

## 6. 결과 판정

- 완료: Head-only Fine-tuning 학습, 모델 파일 생성, 3클래스 라벨 저장 확인
- 한계: Validation 정확도 0.7669로 오분류가 약 23%(31장). A 모델 Test 정량평가 미수행
- 선택 실험: Full Fine-tuning 비교 → 아래 7절

## 7. 선택 실험 — Full Fine-tuning 비교 (실행 완료)

```bash
python -m training.finetune --data dataset --output artifacts/beans_resnet18_full \
  --epochs 3 --batch-size 8 --lr 0.00005
```
- `training/finetune.py`는 **수정하지 않았다.** `--freeze-backbone`을 빼고 `--lr`만 바꿨다 (평가가이드 6-1 B 실험 예시와 같은 값).
- 저장 위치는 `artifacts/beans_resnet18_full/`로 따로 뒀다. A 실험 결과를 덮어쓰지 않았다.
- 서비스(`.env MODEL_PATH`)는 계속 **A 모델**을 쓴다. 산출물 2~7의 모든 실행·측정은 A 모델 기준이다.

| Epoch | B Train Loss | B Validation Accuracy |
|---|---:|---:|
| 1 | 0.4407 | **0.9699** |
| 2 | 0.1556 | 0.9624 |
| 3 | 0.0854 | 0.9624 |

### A vs B 비교 (같은 Train 1,034장 / 같은 Validation 133장)

| 실험 | 학습 대상 | lr | epochs / batch | Best Val Acc | 정답 수 | 저장된 epoch | 상태 |
|---|---|---:|---|---:|---:|---:|---|
| A. Head-only (기준선) | 분류 헤드만 (512→3) | 0.0002 | 3 / 8 | 0.7669 | 102 / 133 | 2 | 서비스에 사용 |
| B. Full Fine-tuning | 전체 가중치 | 0.00005 | 3 / 8 | **0.9699** | **129 / 133** | 1 | 선택 실험, 서비스 미적용 |

- **차이: 0.7669 → 0.9699, 20.3%p(0.2030) 상승.** Validation 오답이 31장에서 4장으로 줄었다.
- 같은 데이터 분할·전처리(같은 `AutoImageProcessor`)·seed 42·epochs·batch로 학습했다.
- **바뀐 변수는 두 개다** (학습 대상, 학습률). 그래서 이 차이를 Backbone 학습 효과 *하나만으로* 설명할 수는 없다. 학습률은 전체 학습에 맞춰 낮춘 값이다.
- B는 1 epoch째가 best였다. 그 뒤 Train Loss는 계속 줄었지만(0.44 → 0.09) Validation은 0.9699 → 0.9624(1장 차이)로 조금 내려갔다. 과적합의 시작일 수도 있지만, 1장 차이라 판단하기엔 근거가 부족하다.
- 모델 선택은 Validation으로만 했다.
- 증빙: `reports/evidence/train_log_full.txt`, `artifacts/beans_resnet18_full/training_report.json` (모델 파일 44.8MB, `config.json`·`preprocessor_config.json` 생성 확인)

### Test 평가 (B 모델, 1회)

- 추가 작성한 평가 스크립트 `training/evaluate.py`로 측정했다 (**제공 코드 외**).
- 순서: ① 같은 스크립트로 B를 Validation으로 평가해서 학습 기록과 같은 **0.9699 (129/133)**가 재현되는지 확인 → ② **Validation으로 B를 최종 모델로 정한 뒤** Test 128장을 **1회** 평가. A는 Test로 평가하지 않았다 (Test로 모델을 고르지 않기 위해).

| 지표 | Validation (133) | **Test (128)** |
|---|---:|---:|
| Accuracy | 0.9699 | **0.9531** (122/128) |
| Macro F1 | 0.9700 | 0.9533 |
| 병든 잎 Recall (병든 잎 = 불량) | 0.9775 | **1.0000** (놓친 것 0장) |
| 건강한 잎을 병들었다고 함 (FP) | 1 | 2 |

**Test 클래스별**

| Class | 장수 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 43 | 0.9149 | 1.0000 | 0.9556 |
| bean_rust | 43 | 0.9512 | 0.9070 | 0.9286 |
| healthy | 42 | 1.0000 | 0.9524 | 0.9756 |

**Test 혼동행렬 (행=정답, 열=예측)**

| 정답 \ 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot | 43 | 0 | 0 |
| bean_rust | 4 | 39 | 0 |
| healthy | 0 | 2 | 40 |

- Validation → Test에서 1.7%p 떨어졌다. 가장 약한 지점은 **bean_rust → angular_leaf_spot 혼동 (4장)**이다.
- 틀린 사진: `bean_rust_test.3/15/28/31.jpg` (→ angular), `healthy_test.10/27.jpg` (→ bean_rust). `healthy_test.10`은 A 모델도 측정 중에 bean_rust로 틀린 사진이다 (B 점수 0.8859).
- 근거: `reports/data/eval_B_val/`, `reports/data/eval_final_test/` (`metrics.md`·`metrics.json`·`predictions.csv`·`wrong.csv`), 로그 `reports/evidence/eval_*_log.txt`
- 서비스 모델 A의 Test 성능: **미측정**
