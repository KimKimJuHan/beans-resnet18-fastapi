#!/usr/bin/env bash
# [추가 보조 스크립트] WSL 프로젝트의 결과물만 Windows 공유 폴더로 복사한다 (Claude가 가져갈 수 있게).
# 사용: bash tools/sync_results.sh /mnt/c/Users/<윈도우사용자>/ai_vision/subject9_machinevision/beans_eval/fastapi_resnet18
set -euo pipefail
DEST="${1:?Windows 쪽 대상 폴더 경로를 인자로 주세요}"
mkdir -p "$DEST/reports" "$DEST/artifacts"
cp -r reports/. "$DEST/reports/"                                   # 보고서·CSV·캡처
for d in artifacts/*/; do                                          # 가중치(.safetensors)는 크므로 제외
  [ -d "$d" ] || continue; mkdir -p "$DEST/$d"
  cp "$d"/*.json "$DEST/$d" 2>/dev/null || true
done
echo "복사 완료 → $DEST"
