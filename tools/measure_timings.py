"""산출물 6용: 동기/비동기 × 캐시 MISS/HIT 응답시간을 같은 조건으로 반복 측정해 원본 CSV를 남깁니다.
서버(web)와 Worker, Redis, PostgreSQL이 실행 중이어야 합니다. 표준 라이브러리만 사용합니다.

예:
    python tools/measure_timings.py --data dataset/test --repeat 5 --out reports/data

측정 방법
  - 캐시는 '같은 이미지 + 같은 모델'이면 HIT 이므로,
      MISS = 아직 한 번도 보내지 않은 새 이미지,  HIT = 방금 보낸 같은 이미지를 다시 보냄
  - 동기와 비동기는 같은 Redis 캐시를 공유하므로 서로 다른 이미지를 사용합니다.
  - 첫 요청은 모델 로딩이 섞일 수 있어 warmup 으로 따로 기록하고 요약에서 제외합니다.
  - 비동기 final_ms = 접수 요청 시작 ~ 상태조회에서 done/failed 를 처음 본 시점 (폴링 간격 포함)
  - 이미 한 번이라도 서버에 보낸 이미지는 MISS가 아닐 수 있으므로, 처음 측정할 때 실행하거나
    응답의 cache_hit 값을 그대로 기록한 cache_status 열을 기준으로 판단하세요.

결과:
    timings.csv          run_id,path,cache_status,http_ms,final_ms,inference_ms,job_id,image,top1_label,actual_label,expected_cache
    timings_summary.md   조건별 중앙값 표
"""
import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def post_image(url, path, timeout):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {MIME[path.suffix.lower()]}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, data = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, data = e.code, e.read()
    ms = (time.perf_counter() - t0) * 1000
    try:
        payload = json.loads(data)
    except ValueError:
        payload = {"raw": data[:200].decode("utf-8", "replace")}
    return status, payload, ms, t0


def get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, json.loads(r.read())


def collect_images(data):
    images = []
    for cls_dir in sorted(p for p in Path(data).iterdir() if p.is_dir()):
        images += [(p, cls_dir.name) for p in sorted(cls_dir.iterdir()) if p.suffix.lower() in EXTS]
    # 클래스가 섞이도록 번갈아 배치
    by_cls = {}
    for p, c in images:
        by_cls.setdefault(c, []).append((p, c))
    mixed = []
    while any(by_cls.values()):
        for c in list(by_cls):
            if by_cls[c]:
                mixed.append(by_cls[c].pop(0))
    return mixed


def main(a):
    base = a.base_url.rstrip("/")
    images = collect_images(a.data)
    need = 1 + 2 * a.repeat
    if len(images) < need:
        raise ValueError(f"이미지가 {need}장 이상 필요합니다 (현재 {len(images)}장): {a.data}")
    status, health = get_json(f"{base}/health", a.timeout)
    print(f"health: {status} {health}")

    warm, sync_imgs, async_imgs = images[0], images[1:1 + a.repeat], images[1 + a.repeat:need]
    rows = []

    def record(run_id, path_kind, expected, payload, http_ms, final_ms, job_id, img):
        hit = payload.get("cache_hit")
        rows.append({
            "run_id": run_id, "path": path_kind,
            "cache_status": "HIT" if hit is True else "MISS" if hit is False else "UNKNOWN",
            "http_ms": round(http_ms, 1), "final_ms": round(final_ms, 1) if final_ms is not None else "",
            "inference_ms": payload.get("inference_ms") if payload.get("inference_ms") is not None else "",
            "job_id": job_id if job_id is not None else "",
            "image": str(img[0]), "top1_label": (payload.get("top1") or {}).get("label", ""),
            "actual_label": img[1], "expected_cache": expected,
        })
        r = rows[-1]
        print(f"{path_kind:6} {expected:6} run={run_id} cache={r['cache_status']:4} http={r['http_ms']}ms "
              f"final={r['final_ms']}ms infer={r['inference_ms']} label={r['top1_label']} (정답 {img[1]})")

    def run_sync(img, run_id, expected):
        st, payload, ms, _ = post_image(f"{base}/api/sync/classify/", img[0], a.timeout)
        if st != 200:
            raise RuntimeError(f"동기 요청 실패 {st}: {payload}")
        record(run_id, "sync", expected, payload, ms, ms, None, img)

    def run_async(img, run_id, expected):
        st, payload, ms, t0 = post_image(f"{base}/api/async/classify/", img[0], a.timeout)
        if st != 202:
            raise RuntimeError(f"비동기 접수 실패 {st}: {payload}")
        job_id = payload["job_id"]
        check = payload.get("check_url") or f"/api/async/jobs/{job_id}/"
        deadline = time.time() + a.job_timeout
        while True:
            _, job = get_json(f"{base}{check}", a.timeout)
            if job.get("status") in ("done", "failed"):
                final_ms = (time.perf_counter() - t0) * 1000
                break
            if time.time() > deadline:
                raise RuntimeError(f"job {job_id}가 {a.job_timeout}초 안에 끝나지 않았습니다 (Worker 실행 확인)")
            time.sleep(a.poll)
        if job.get("status") == "failed":
            print(f"  job {job_id} failed: {job.get('error_message')}")
        record(run_id, "async", expected, job, ms, final_ms, job_id, img)
        rows[-1]["http_ms"] = round(ms, 1)  # 접수 HTTP 시간

    print("\n[warmup] 모델 로딩 등 첫 요청 (요약에서 제외)")
    run_sync(warm, 0, "warmup")
    print("\n[sync] MISS → HIT")
    for i, img in enumerate(sync_imgs, 1):
        run_sync(img, i, "MISS")
        run_sync(img, i, "HIT")
    print("\n[async] MISS → HIT")
    for i, img in enumerate(async_imgs, 1):
        run_async(img, i, "MISS")
        run_async(img, i, "HIT")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fields = ["run_id", "path", "cache_status", "http_ms", "final_ms", "inference_ms", "job_id",
              "image", "top1_label", "actual_label", "expected_cache"]
    with open(out / "timings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    def med(vals):
        vals = [float(v) for v in vals if v not in ("", None)]
        return f"{statistics.median(vals):.1f}" if vals else "NULL"

    lines = ["# 응답시간 측정 요약 (중앙값, ms)", "",
             f"- 서버: {base}", f"- 이미지 폴더: {a.data}", f"- 반복: 조건별 {a.repeat}회 (warmup 1회 제외)",
             f"- 비동기 상태조회 간격: {a.poll}초 (final_ms에 포함)", "",
             "| 경로 | 캐시 | 횟수 | HTTP 응답 | 최종 결과 확인 | 모델 추론(inference_ms) |",
             "|---|---|---:|---:|---:|---:|"]
    for path_kind in ("sync", "async"):
        for cache in ("MISS", "HIT"):
            g = [r for r in rows if r["path"] == path_kind and r["cache_status"] == cache and r["expected_cache"] != "warmup"]
            name = "동기" if path_kind == "sync" else "비동기(HTTP=접수)"
            lines.append(f"| {name} | {cache} | {len(g)} | {med(r['http_ms'] for r in g)} | "
                         f"{med(r['final_ms'] for r in g)} | {med(r['inference_ms'] for r in g)} |")
    mismatch = [r for r in rows if r["expected_cache"] in ("MISS", "HIT") and r["cache_status"] != r["expected_cache"]]
    lines += ["", f"- 예상과 다른 캐시 상태: {len(mismatch)}건 (이미 보낸 이미지였거나 캐시가 꺼져 있으면 발생)",
              "- HIT의 inference_ms=NULL은 모델 추론을 생략했다는 뜻이며 0ms가 아닙니다.",
              "- 비동기 HTTP 시간은 '접수' 시간이고, 실제 결과는 '최종 결과 확인' 열입니다."]
    (out / "timings_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n저장: {out}/timings.csv, {out}/timings_summary.md")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--data", default="dataset/test", help="클래스 폴더가 들어 있는 이미지 폴더")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--poll", type=float, default=0.2, help="비동기 상태조회 간격(초)")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--job-timeout", type=float, default=120)
    p.add_argument("--out", default="reports/data")
    main(p.parse_args())
