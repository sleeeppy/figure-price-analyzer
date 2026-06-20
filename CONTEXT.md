# Project Context — Figure Price Analyzer

> 이 문서는 Claude Code 세션 시작 시 첫 메시지로 붙여넣기 위한 컨텍스트 문서입니다.
> 프로젝트 결정사항, 현재 상태, 다음 작업을 압축해서 담고 있습니다.

---

## 1. 프로젝트 개요

피규어 사진을 업로드하면 **(1) 어떤 피규어인지 식별**하고 **(2) 정가 + 시장가 분포**를 보여주는 로컬 전용 도구.

- **전 과정 무료** (유료 API 호출 없음)
- **로컬 실행 전제** (배포 안 함, MacBook M5 Pro에서 동작)
- **MVP 범위**: MyFigureCollection (MFC) 의 **1/7 ~ 1/8 스케일 Prepainted** 피규어
  (굿스마일 / 알터 / 코토부키야 등). 이후 카테고리 확장 가능.

---

## 2. 기술 스택 (확정)

| 영역 | 선택 | 이유 |
|---|---|---|
| 이미지 임베딩 | `facebook/dinov2-large` (1024-dim, MPS) | CLIP보다 시각 미세차이(피규어 버전) 식별에 강함 |
| 전처리 | `rembg` (u2net) → 흰 배경 합성 | 진열장/박스 배경 노이즈 제거 |
| 벡터 DB | `sqlite-vec` (`vec0` 가상 테이블) | SQLite 단일 파일로 통일, 별도 인프라 불필요 |
| 정형 DB | SQLite (동일 파일) | 무료, 로컬, WAL 모드 |
| 재랭킹 | Gemini 1.5 Flash 무료 티어 | top-10 → top-1, 일 1500회로 충분 |
| 백엔드 | Python 3.11 + FastAPI | ML 라이브러리와 같은 언어, 통합 깔끔 |
| 프론트엔드 | React (Vite) + Recharts | 정규분포풍 가격 분포 차트 |
| 환율 | `exchangerate.host` JPY→KRW, 일일 SQLite 캐시 | 무료, 폴백 가능 |
| 가격 데이터 | MFC `msrp_jpy` + Loose/MIB 사용자 집계가 | 별도 크롤링 사이트 추가는 v2로 미룸 |

비채택: CLIP (시각 정확도 열세), FAISS (sqlite-vec로 충분), 중고나라/번개장터/메루카리 크롤링 (ToS / 한국 IP 차단 / 유지보수 비용).

---

## 3. 현재 코드 상태

스캐폴딩 1차 완료. 모든 파일이 syntactically valid하며 파이프라인이 end-to-end로 연결되어 있음.

```
figure-price-analyzer/
├── README.md                 # 실행 순서 6단계
├── requirements.txt
├── .env.example              # GEMINI_API_KEY
├── config.py                 # 경로, 모델명, 시드 URL, 폴리트 딜레이
├── db/
│   ├── schema.sql            # figures / figure_images / price_history / fx_rates
│   ├── connection.py         # sqlite-vec 로딩 (sqlite3 → pysqlite3 폴백)
│   └── init_db.py            # 정형 테이블 + vec0(figure_image_id PK, embedding[1024])
├── crawler/
│   ├── mfc_crawler.py        # httpx + bs4, 2.5s 딜레이, scale ∈ {1/7,1/8} 필터
│   └── fx_updater.py         # JPY→KRW 일일 캐시 + latest_jpy_to_krw() 헬퍼
├── embeddings/
│   ├── embedder.py           # DINOv2-Large, MPS, L2-normalized CLS, rembg 전처리
│   └── build_index.py        # figure_images → vec0 멱등 인덱싱
└── api/
    ├── rerank.py             # Gemini 멀티이미지 한 번 호출, JSON 파싱
    └── main.py               # /identify (vector search → dedupe by figure_id → 후보 N개 → 선택적 rerank → 가격 변환)
```

**핵심 응답 스키마 (`api/main.py` 의 `IdentifyResponse`):**

```python
{
  "best": FigureCandidate | None,
  "alternates": [FigureCandidate, ...],
  "rerank_meta": {"best_index": int, "confidence": str, "reason": str} | None,
  "fx_jpy_to_krw": float
}

FigureCandidate = {
  "figure_id", "name_en", "name_jp", "maker", "scale",
  "character_name", "origin", "release_date", "mfc_url",
  "image_paths": [...],
  "distance": float,
  "price": {
    "msrp_jpy", "msrp_krw",
    "loose_jpy", "loose_krw",
    "mib_jpy", "mib_krw",
    "observations": [{source, condition, price_jpy, observed_at}, ...]
  }
}
```

---

## 4. 알려진 미해결 항목 (검증/개선 필요)

### 4-1. MFC 셀렉터 검증 (즉시 필요)
`crawler/mfc_crawler.py` 의 아래 함수는 합리적 추측이지 검증된 셀렉터가 아님:
- `_data_field(soup, label)` — div.data-field / .item-info-field / tr 순회
- `_parse_market_prices` — 정규식으로 "Loose"/"MIB" 근처 ¥금액 추출
- `_parse_images` — `/pics/picture/` 또는 `/upload/` 경로 포함된 img 찾기

**검증 방법**: `python -m crawler.mfc_crawler --max-items 5` 로 5개만 크롤한 뒤
```sql
SELECT id, name_en, scale, msrp_jpy, raw_meta_json FROM figures;
SELECT figure_id, source, price_jpy FROM price_history;
SELECT figure_id, COUNT(*) FROM figure_images GROUP BY figure_id;
```
필드가 비어있으면 브라우저 devtools로 실제 HTML 보고 셀렉터만 손보면 됨.

### 4-2. 시드 URL placeholder
`config.py` 의 `MFC_SEED_URLS` 가 추측값. MFC에서 직접 "1/7 scale Prepainted" 필터 건 listing URL을 복사해서 교체해야 함.

### 4-3. 다중 시점 풀링 (개선 여지)
현재 `_dedupe_to_figures` 는 figure당 best 거리 하나만 사용. Mean pooling으로 바꾸면 정확도 향상 여지. 측정 후 결정.

### 4-4. 프론트엔드 미구현
백엔드 API 응답 스키마는 확정됐지만 React UI는 아직 없음. Recharts로 정규분포풍 곡선 + 정가/평균가 마커 + 후보 카드 디자인 필요.

### 4-5. sqlite-vec 거리 검증
`vec0` 의 기본 거리는 L2. 임베딩이 L2-normalized 되어 있으므로 L2 거리와 코사인 거리가 동치이지만, 결과 distance 값의 절대 스케일 확인 필요 (UI에서 confidence 표시할 때).

---

## 5. 실행 순서 (재확인)

```bash
cd figure-price-analyzer
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # GEMINI_API_KEY 입력

python -m db.init_db
python -m crawler.fx_updater
python -m crawler.mfc_crawler --max-items 5    # 셀렉터 검증용 스모크 테스트
python -m embeddings.build_index
uvicorn api.main:app --reload --port 8000

curl -X POST http://localhost:8000/identify \
  -F "image=@/path/to/figure.jpg" -F "rerank=true"
```

---

## 6. 다음에 할 작업 (우선순위 순)

1. **MFC 크롤러 셀렉터 실측 검증** — 5개 스모크 후 누락 필드 보정
2. **시드 URL 확정** — MFC 1/7, 1/8 Prepainted 카테고리 URL 복사
3. **본격 크롤 200~500개** — 임베딩 인덱스 채우기
4. **React 프론트엔드 (Vite + Recharts)**
   - 업로드 컴포넌트 (드래그&드롭 + 카메라 `<input capture>`)
   - 후보 카드 (best + alternates), 사용자가 후보 교체 가능
   - 가격 분포 차트: msrp_krw + loose_krw + mib_krw + observations 히스토그램
   - distance → confidence 매핑 표시
5. **(여유 되면) 다중 시점 mean pooling 실험**

---

## 7. 협업 스타일 메모 (Claude Code 용)

- 작업 단위가 명확하면 바로 코드로. 추측이 필요하면 한 가지 옵션을 결정해서 진행하고 끝에 다른 선택지 적어둘 것.
- **MFC 크롤링 셀렉터는 추측하지 말고 사용자에게 실제 HTML 샘플을 받아서** 수정할 것. 잘못 추측해서 셀렉터를 무한히 바꾸지 말 것.
- 모든 비용 발생 가능 작업 (Gemini 호출, 외부 API, 대량 크롤) 은 dry-run / `--max-items` 같은 안전장치를 먼저 둘 것.
- 한국어로 응답.
