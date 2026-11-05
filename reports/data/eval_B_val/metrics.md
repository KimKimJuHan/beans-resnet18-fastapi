# Evaluation Result

- Model: `artifacts/beans_resnet18_full`
- Data: `dataset/val`
- Images: 133  /  Correct: 129
- **Accuracy: 0.9699**  /  Macro F1: 0.9700

## Class별 성능

| Class | 장수 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 44 | 1.0000 | 0.9545 | 0.9767 |
| bean_rust | 45 | 0.9565 | 0.9778 | 0.9670 |
| healthy | 44 | 0.9556 | 0.9773 | 0.9663 |

## Confusion Matrix (행=정답, 열=예측)

| 정답 \ 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot | 42 | 1 | 1 |
| bean_rust | 0 | 44 | 1 |
| healthy | 0 | 1 | 43 |

## 병든 잎 vs 건강한 잎 (병든 잎 = 불량)

| 항목 | 값 |
|---|---:|
| 병든 잎을 찾음 (TP) | 87 |
| 건강한 잎을 건강하다고 함 (TN) | 43 |
| 건강한 잎을 병들었다고 함 (FP) | 1 |
| 병든 잎을 놓침 (FN) | 2 |
| Accuracy | 0.9774 |
| Precision | 0.9886 |
| Recall | 0.9775 |
