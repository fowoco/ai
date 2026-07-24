---
id: log-2026-07-24-sample-render-validation
type: log
title: "Downloads HWPX 샘플 4종 렌더링 검증"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/06-tdd.md
---

# Downloads HWPX 샘플 4종 렌더링 검증

## 작업 요약

- Downloads에 있는 HWPX 4종을 현재 Python Manifest로 분석했다.
- 공식 `rhwp` CLI의 `info`와 `export-svg --debug-overlay`를 모두 실행했다.

## 주요 변경점 & 설계 결정

- 표준근로계약서: 2페이지, 표 2개, 이미지 0개
- 통합신청서: 1페이지, 표 1개, 이미지 0개
- 취업기간 연장신청서: 2페이지, 표 2개, 이미지 0개
- 신원보증서: 1페이지, 표 1개, 이미지 0개
- 표준근로계약서와 취업기간 연장신청서 원본에서 `LAYOUT_OVERFLOW` 경고가 발생했지만 CLI는 렌더를 완료했다.
- 원본 경고는 기존 양식의 기준선으로 보존하고, 수정 후 신규 경고만 차단하도록 구현했다.

## 테스트 결과

- 4개 HWPX 구조 분석: 통과
- 4개 HWPX SVG 렌더링: 통과
- `uv run pytest`: `18 passed`
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 이미지가 포함된 HWPX 샘플을 확보해 `BinData`와 위치 후보를 검증한다.
- 실제 셀 입력 후 신규 레이아웃 경고 차단을 샘플로 확인한다.
