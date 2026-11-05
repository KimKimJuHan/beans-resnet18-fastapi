"""[추가 점검 스크립트 — 제공 코드 아님] dHash(64bit) 해밍거리로 Split 사이 '거의 같은 사진'을 찾는다.
사용: python tools/check_near_duplicates.py ../beans_source   (거리 0~5 = 거의 같은 사진 의심, 6 이상 = 보통 다른 사진)
"""
import sys, pathlib, itertools, collections
from PIL import Image
root = pathlib.Path(sys.argv[1])
def dhash(p, n=8):
    im = Image.open(p).convert("L").resize((n+1, n), Image.BILINEAR)
    px = list(im.getdata()); bits = 0
    for r in range(n):
        for c in range(n):
            bits = (bits << 1) | (px[r*(n+1)+c] > px[r*(n+1)+c+1])
    return bits
items = []
for split in ["train","validation","test"]:
    for p in sorted((root/split).rglob("*.jpg")):
        items.append((split, p.parent.name, p.name, dhash(p)))
print("images", len(items))
dist = collections.Counter()
hits = []
for a, b in itertools.combinations(items, 2):
    if a[0] == b[0]: continue
    d = bin(a[3] ^ b[3]).count("1")
    if d <= 10: dist[d] += 1
    if d <= 6: hits.append((d, a[:3], b[:3]))
print("cross-split pairs by hamming distance (<=10):", dict(sorted(dist.items())))
for h in sorted(hits)[:20]: print(h)
