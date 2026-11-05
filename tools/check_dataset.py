"""산출물 1용: 데이터 폴더의 클래스별 이미지 수와 중복·누출(같은 이미지가 여러 Split에 있는지)을 확인합니다.

예:
    python tools/check_dataset.py --root beans_source --out reports/data   # 제공 원본 (train/validation/test)
    python tools/check_dataset.py --root dataset      --out reports/data   # 코드 실행용 (train/val/test)

결과:
    reports/data/dataset_counts.csv      split, class, count
    reports/data/dataset_duplicates.csv  같은 내용(MD5)의 파일 목록
    reports/data/dataset_check.md        보고서에 붙일 표
"""
import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SPLIT_ORDER = ["train", "validation", "val", "test"]


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main(args):
    root = Path(args.root)
    if not root.is_dir():
        raise FileNotFoundError(f"폴더가 없습니다: {root}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    splits = [s for s in SPLIT_ORDER if (root / s).is_dir()]
    splits += sorted(p.name for p in root.iterdir() if p.is_dir() and p.name not in splits)
    if not splits:
        raise ValueError(f"split 폴더(train/val/validation/test)가 없습니다: {root}")

    counts = defaultdict(int)          # (split, class) -> n
    classes_by_split = {}
    by_hash = defaultdict(list)        # md5 -> [(split, class, relpath)]
    skipped = 0
    for split in splits:
        classes = sorted(p.name for p in (root / split).iterdir() if p.is_dir())
        classes_by_split[split] = classes
        for cls in classes:
            for path in sorted((root / split / cls).rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in EXTS:
                    skipped += 1
                    continue
                counts[(split, cls)] += 1
                by_hash[md5(path)].append((split, cls, str(path.relative_to(root))))

    all_classes = sorted({c for cs in classes_by_split.values() for c in cs})
    dup_groups = {h: v for h, v in by_hash.items() if len(v) > 1}
    cross_split = {h: v for h, v in dup_groups.items() if len({s for s, _, _ in v}) > 1}
    cross_label = {h: v for h, v in dup_groups.items() if len({c for _, c, _ in v}) > 1}

    with open(out / "dataset_counts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split", "class", "count"])
        for split in splits:
            for cls in all_classes:
                w.writerow([split, cls, counts[(split, cls)]])

    with open(out / "dataset_duplicates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["md5", "split", "class", "file"])
        for h, items in dup_groups.items():
            for split, cls, rel in items:
                w.writerow([h, split, cls, rel])

    lines = [f"# 데이터 구성 확인 — `{root}`", "",
             "| 클래스 | " + " | ".join(splits) + " | 합계 |",
             "|---|" + "---:|" * (len(splits) + 1)]
    for cls in all_classes:
        row = [counts[(s, cls)] for s in splits]
        lines.append(f"| {cls} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    totals = [sum(counts[(s, c)] for c in all_classes) for s in splits]
    lines.append("| **합계** | " + " | ".join(f"**{t}**" for t in totals) + f" | **{sum(totals)}** |")

    missing = [f"{s}/{c}" for s in splits for c in all_classes if c not in classes_by_split[s]]
    lines += ["", "## 점검 결과", "",
              f"- 확인 방식: 모든 이미지 파일의 내용 해시(MD5)를 계산해 같은 내용의 파일을 찾음",
              f"- 이미지가 아닌 파일(건너뜀): {skipped}개",
              f"- 클래스 폴더 누락: {', '.join(missing) if missing else '없음'}",
              f"- 내용이 같은 파일 묶음: {len(dup_groups)}개",
              f"- **서로 다른 Split에 같은 이미지(누출 의심): {len(cross_split)}개**",
              f"- 서로 다른 클래스에 같은 이미지(라벨 충돌): {len(cross_label)}개",
              "", "> MD5는 바이트가 완전히 같은 파일만 찾습니다. 크기·밝기만 다른 비슷한 사진은 찾지 못하므로, 그런 경우는 '미확인'으로 기록하세요."]
    if cross_split:
        lines += ["", "### 누출 의심 목록 (최대 20개)", "", "| MD5 | 위치 |", "|---|---|"]
        for h, items in list(cross_split.items())[:20]:
            lines.append(f"| `{h[:10]}` | " + "<br>".join(f"{s}/{c}: {r}" for s, c, r in items) + " |")
    (out / "dataset_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"\n저장: {out}/dataset_counts.csv, dataset_duplicates.csv, dataset_check.md")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, help="beans_source 또는 dataset 폴더")
    p.add_argument("--out", default="reports/data")
    main(p.parse_args())
