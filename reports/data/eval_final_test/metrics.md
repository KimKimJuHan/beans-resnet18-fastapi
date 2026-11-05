# Evaluation Result

- Model: `artifacts/beans_resnet18_full`
- Data: `dataset/test`
- Images: 128  /  Correct: 122
- **Accuracy: 0.9531**  /  Macro F1: 0.9533

## Class별 성능

| Class | 장수 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 43 | 0.9149 | 1.0000 | 0.9556 |
| bean_rust | 43 | 0.9512 | 0.9070 | 0.9286 |
| healthy | 42 | 1.0000 | 0.9524 | 0.9756 |

## Confusion Matrix (행=정답, 열=예측)

| 정답 \ 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot | 43 | 0 | 0 |
| bean_rust | 4 | 39 | 0 |
| healthy | 0 | 2 | 40 |

## 병든 잎 vs 건강한 잎 (병든 잎 = 불량)

| 항목 | 값 |
|---|---:|
| 병든 잎을 찾음 (TP) | 86 |
| 건강한 잎을 건강하다고 함 (TN) | 40 |
| 건강한 잎을 병들었다고 함 (FP) | 2 |
| 병든 잎을 놓침 (FN) | 0 |
| Accuracy | 0.9844 |
| Precision | 0.9773 |
| Recall | 1.0000 |
