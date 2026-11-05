"""[추가 평가 스크립트 · 선택] Fine-tuning한 분류 모델을 이미지 폴더로 평가합니다.
제공 코드(finetune.py)에는 없는 기능이므로, 보고서에는 '추가 작성한 평가 스크립트로 측정'이라고 밝히세요.

예:
    # Head-only(A)와 Full(B)을 같은 Validation으로 자세히 비교
    python -m training.evaluate --model artifacts/beans_resnet18      --data dataset/val --out reports/data/eval_A_val
    python -m training.evaluate --model artifacts/beans_resnet18_full --data dataset/val --out reports/data/eval_B_val
    # 최종 모델을 정한 뒤에만, Test를 한 번 측정 (Test로 모델을 고르지 않음)
    python -m training.evaluate --model artifacts/beans_resnet18      --data dataset/test --out reports/data/eval_final_test

폴더 구조 (클래스 이름은 학습할 때와 같아야 합니다):
    dataset/test/angular_leaf_spot/*.jpg
    dataset/test/bean_rust/*.jpg
    dataset/test/healthy/*.jpg

결과:
    predictions.csv   이미지별 정답·예측·점수
    wrong.csv         틀린 이미지 목록 (발표용 실패 사례)
    metrics.json      Accuracy, 클래스별 Precision/Recall/F1, Confusion Matrix
    metrics.md        발표에 붙여 넣기 쉬운 표
"""
import argparse
import csv
import json
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def compute_metrics(rows, classes, healthy_name="healthy"):
    """rows: [{"actual": str, "predicted": str}, ...]"""
    matrix = {a: {p: 0 for p in classes} for a in classes}
    for r in rows:
        matrix[r["actual"]][r["predicted"]] += 1

    per_class = {}
    for c in classes:
        tp = matrix[c][c]
        fp = sum(matrix[a][c] for a in classes if a != c)
        fn = sum(matrix[c][p] for p in classes if p != c)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[c] = {
            "support": tp + fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    total = len(rows)
    correct = sum(r["actual"] == r["predicted"] for r in rows)
    result = {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "macro_f1": round(sum(v["f1"] for v in per_class.values()) / len(classes), 4),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }

    # 병든 잎(healthy가 아닌 것)을 '불량'으로 보는 2분류 관점
    if healthy_name in classes:
        tp = sum(r["actual"] != healthy_name and r["predicted"] != healthy_name for r in rows)
        tn = sum(r["actual"] == healthy_name and r["predicted"] == healthy_name for r in rows)
        fp = sum(r["actual"] == healthy_name and r["predicted"] != healthy_name for r in rows)
        fn = sum(r["actual"] != healthy_name and r["predicted"] == healthy_name for r in rows)
        result["diseased_vs_healthy"] = {
            "TP_diseased_found": tp,
            "TN_healthy_ok": tn,
            "FP_healthy_called_diseased": fp,
            "FN_diseased_missed": fn,
            "accuracy": round((tp + tn) / total, 4) if total else 0.0,
            "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
            "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
        }
    return result


def to_markdown(m, classes, model, data):
    lines = [
        "# Evaluation Result",
        "",
        f"- Model: `{model}`",
        f"- Data: `{data}`",
        f"- Images: {m['total']}  /  Correct: {m['correct']}",
        f"- **Accuracy: {m['accuracy']:.4f}**  /  Macro F1: {m['macro_f1']:.4f}",
        "",
        "## Class별 성능",
        "",
        "| Class | 장수 | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for c in classes:
        v = m["per_class"][c]
        lines.append(f"| {c} | {v['support']} | {v['precision']:.4f} | {v['recall']:.4f} | {v['f1']:.4f} |")
    lines += ["", "## Confusion Matrix (행=정답, 열=예측)", "",
              "| 정답 \\ 예측 | " + " | ".join(classes) + " |",
              "|---|" + "---:|" * len(classes)]
    for a in classes:
        lines.append(f"| {a} | " + " | ".join(str(m["confusion_matrix"][a][p]) for p in classes) + " |")
    if "diseased_vs_healthy" in m:
        b = m["diseased_vs_healthy"]
        lines += ["", "## 병든 잎 vs 건강한 잎 (병든 잎 = 불량)", "",
                  "| 항목 | 값 |", "|---|---:|",
                  f"| 병든 잎을 찾음 (TP) | {b['TP_diseased_found']} |",
                  f"| 건강한 잎을 건강하다고 함 (TN) | {b['TN_healthy_ok']} |",
                  f"| 건강한 잎을 병들었다고 함 (FP) | {b['FP_healthy_called_diseased']} |",
                  f"| 병든 잎을 놓침 (FN) | {b['FN_diseased_missed']} |",
                  f"| Accuracy | {b['accuracy']:.4f} |",
                  f"| Precision | {b['precision']:.4f} |",
                  f"| Recall | {b['recall']:.4f} |"]
    return "\n".join(lines) + "\n"


def run(args):
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForImageClassification

    model_dir, data, out = Path(args.model), Path(args.data), Path(args.out)
    if not model_dir.is_dir():
        raise FileNotFoundError(f"모델 폴더가 없습니다: {model_dir}")
    if not data.is_dir():
        raise FileNotFoundError(f"평가 데이터 폴더가 없습니다: {data}")
    out.mkdir(parents=True, exist_ok=True)

    processor = AutoImageProcessor.from_pretrained(model_dir)
    model = AutoModelForImageClassification.from_pretrained(model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()

    id2label = {int(k): v for k, v in model.config.id2label.items()}
    classes = [id2label[i] for i in sorted(id2label)]

    rows = []
    for actual in classes:
        folder = data / actual
        if not folder.is_dir():
            raise ValueError(f"클래스 폴더가 없습니다: {folder} (학습 클래스: {classes})")
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in EXTS:
                continue
            with Image.open(path) as raw:
                image = raw.convert("RGB")
            pixels = processor(images=image, return_tensors="pt")["pixel_values"].to(device)
            with torch.no_grad():
                probs = model(pixel_values=pixels).logits.softmax(dim=-1)[0].cpu()
            idx = int(probs.argmax())
            rows.append({
                "file": str(path.relative_to(data)),
                "actual": actual,
                "predicted": id2label[idx],
                "score": round(float(probs[idx]), 4),
                "correct": id2label[idx] == actual,
            })
    if not rows:
        raise ValueError(f"평가할 이미지가 없습니다: {data}")

    metrics = compute_metrics(rows, classes)
    metrics["model"], metrics["data"] = str(model_dir), str(data)

    fields = ["file", "actual", "predicted", "score", "correct"]
    for name, subset in (("predictions.csv", rows), ("wrong.csv", [r for r in rows if not r["correct"]])):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(subset)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "metrics.md").write_text(to_markdown(metrics, classes, model_dir, data), encoding="utf-8")

    print(f"Accuracy={metrics['accuracy']:.4f}  Macro F1={metrics['macro_f1']:.4f}  "
          f"({metrics['correct']}/{metrics['total']})")
    if "diseased_vs_healthy" in metrics:
        b = metrics["diseased_vs_healthy"]
        print(f"병든 잎 놓침(FN)={b['FN_diseased_missed']}  건강한 잎 오탐(FP)={b['FP_healthy_called_diseased']}")
    print(f"저장: {out}/ (predictions.csv, wrong.csv, metrics.json, metrics.md)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Fine-tuning 결과 폴더 (예: artifacts/beans_baseline)")
    parser.add_argument("--data", required=True, help="평가 폴더 (dataset/val 또는 dataset/test)")
    parser.add_argument("--out", required=True, help="결과 저장 폴더 (예: reports/baseline_val)")
    run(parser.parse_args())
