# Figure Price Analyzer

시연 영상 : https://youtu.be/vsqRjZAaQkg?si=t3-4_uBBwtopFGyn

피규어 사진 한 장 → **어떤 피규어인지** + **정가/시장가 비교**.

로컬 전용 도구입니다. 외부 배포 안 함, MacBook M-series에서 동작 검증.

```
사진 업로드
   │
   ├─ rembg(u2net) 배경 제거 → DINOv2-large 임베딩 (MPS)
   │                              │
   │                              ▼
   │                      sqlite-vec top-K (L2 = 정규화 코사인)
   │                              │
   │                              ▼
   │                       figure_id 기준 dedupe
   │                              │
   │                              ▼  (선택)
   │                       Gemini 재랭크 → best
   │                              │
   │                              ▼  (실패시)
   │                  Gemini + Google Search → 후보 3개
   │
   ├─ MSRP + MFC 파트너 호가 (JPY/USD) → KRW 환산
   └─ 응답 (FastAPI) → React UI
```

## 현재 데이터셋

```
figures           : 12,019
figure_embeddings : 12,028
partner_prices    : 20,149
```

(스케일: 1/7 ~4.5K, 1/8 ~4.2K, 기타 1/4/1/6/1/10 등 ~600. 본인이 더 채우려면 `crawler/mfc_crawler.py` 부분 참고.)

## 디렉토리

```
.
├── config.py                 # 경로/모델/API 키
├── requirements.txt
├── .env.example              # GEMINI_API_KEY 등
│
├── db/
│   ├── schema.sql            # figures / figure_images / partner_prices / fx_rates
│   ├── connection.py         # sqlite-vec 로딩 헬퍼
│   ├── init_db.py            # DB 초기화 (vec0 가상테이블 포함)
│   └── migrate_figure_images.py  # 일회성 스키마 마이그레이션
│
├── crawler/
│   ├── mfc_crawler.py        # MFC 메타/이미지/파트너 호가
│   └── fx_updater.py         # 환율 일일 캐시 (frankfurter.dev)
│
├── embeddings/
│   ├── embedder.py           # DINOv2-large + rembg, MPS
│   └── build_index.py        # figure_images → vec0
│
├── api/
│   ├── main.py               # FastAPI 엔드포인트들
│   └── rerank.py             # Gemini 재랭크 + 웹 검색 폴백
│
├── data/                     # DB 파일 + 다운로드된 이미지
│   ├── figures.db
│   └── images/<figure_id>/*.jpg
│
└── web/                      # Vite + React + TS 프론트엔드
    ├── src/
    │   ├── App.tsx
    │   ├── api.ts            # 백엔드 호출 래퍼
    │   └── components/       # UploadCard, CandidateCard, PriceSection, ...
    ├── tailwind.config.js    # Duolingo 디자인 토큰
    └── vite.config.ts        # /api → :8000 프록시
```

## 1. 설치

### 백엔드 (Python 3.11)

```bash
# 1) Python 3.11이 필요해요 (transformers/torchvision이 3.14 미지원)
brew install python@3.11

# 2) 가상환경 + 의존성
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) Gemini API 키 (https://aistudio.google.com/apikey 무료)
cp .env.example .env
# .env 의 GEMINI_API_KEY= 값 채우기
```

### 프론트엔드 (Node 20+)

```bash
cd web
npm install
```

## 2. 초기 데이터 준비

이미 DB(`data/figures.db`)가 있다면 이 단계는 건너뛰어도 됩니다.

```bash
source .venv/bin/activate

# DB + vec 가상테이블 생성
python -m db.init_db

# 환율 캐시 (frankfurter.dev, 무료/무키)
python -m crawler.fx_updater

# MFC 크롤 (1/7+1/8 인기 desc, --max-items 없으면 자연 종료까지)
python -m crawler.mfc_crawler --max-items 500

# 임베딩 인덱스 빌드 (12K 기준 ~1시간, MPS)
python -m embeddings.build_index
```

크롤 옵션:

- `--max-items N` : N개 저장하면 종료
- `--refresh` : skip-if-exists 우회 (재방문 후 partner 호가 갱신)
- `--refresh-existing` : listings 건너뛰고 DB의 모든 figure 직접 재크롤
- `--seeds URL1 URL2 ...` : 다른 카테고리/스케일 시드로 오버라이드

## 3. 서버 띄우기

파이썬 GUI 기반 프로그램 실행

```bash
source .venv/bin/activate
python -d gui

# 한 번에 실행
source .venv/bin/activate && python -m gui 
```

### 백엔드 + 프론트엔드 동시에

터미널 두 개:

```bash
# 터미널 1: API 서버 (FastAPI + DINOv2)
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

```bash
# 터미널 2: React dev 서버
cd web
npm run dev
```

브라우저: [http://localhost:5173](http://localhost:5173)

Vite가 `/api/*` 와 `/img/*` 를 `:8000`으로 프록시하므로 CORS 신경 안 써도 됩니다.

API 문서 (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)

### 한 명령으로 띄우기 (선택)

```bash
# 백엔드 백그라운드
source .venv/bin/activate
PYTHONUNBUFFERED=1 uvicorn api.main:app --port 8000 --reload > /tmp/api.log 2>&1 &

# 프론트 백그라운드
cd web && npm run dev > /tmp/vite.log 2>&1 &
```

## 4. 환경변수 (`.env`)


| 키                            | 기본값                     | 설명                                                               |
| ---------------------------- | ----------------------- | ---------------------------------------------------------------- |
| `GEMINI_API_KEY`             | (필수)                    | aistudio.google.com 무료 발급                                        |
| `GEMINI_MODEL`               | `gemini-3.1-flash-lite` | 재랭크용. 무료 ~500 RPD.                                               |
| `GEMINI_LOOKUP_MODEL`        | `gemini-3.1-flash-lite` | /lookup 비전 (Search OFF)                                          |
| `GEMINI_LOOKUP_SEARCH_MODEL` | `gemini-2.5-flash`      | /lookup 비전 (Search ON). 무료티어에서 3.x는 grounding 불가, 2.5-flash만 가능. |
| `GEMINI_LOOKUP_USE_SEARCH`   | `true`                  | false면 Search OFF 모델로 검색 (그라운딩 없이 비전만)                           |
| `DATA_DIR`                   | `./data`                | DB + 이미지 저장 위치                                                   |


Gemini 무료 한도 (한국 키 기준 실측, 2026-05):

- `gemini-2.5-flash` + Google Search → ~500 RPD 공유 (실제로 가장 안정)
- `gemini-3.1-flash-lite` → ~500 RPD 일반 generate, Search는 유료만
- 한도 초과 시 UI에 "X초 후 다시" / "내일 다시"로 분기 표시됨

## 5. 주요 API 엔드포인트


| 메소드  | 경로               | 용도                                  |
| ---- | ---------------- | ----------------------------------- |
| GET  | `/health`        | DB/임베딩 카운트, 환율, 모델명                 |
| POST | `/identify`      | 사진 → 벡터 검색 (+ 옵션 Gemini 재랭크)        |
| POST | `/lookup`        | Gemini Google Search로 figure 후보 3개  |
| POST | `/add_by_mfc`    | MFC URL → 단건 크롤 + 임베딩               |
| POST | `/add_manual`    | 폼 입력 + 이미지 → DB 추가 + 임베딩            |
| POST | `/confirm_image` | 기존 figure에 사진 추가 + 임베딩              |
| GET  | `/suggest`       | character/origin/maker autocomplete |
| GET  | `/img/*`         | 크롤된 이미지 정적 서빙                       |


예시:

```bash
curl -X POST http://localhost:8000/identify \
  -F "image=@/path/to/figure.jpg" \
  -F "rerank=true" -F "k=10"
```

## 6. 프론트엔드 UX

### 메인 페이지 (idle)

- 사진 업로드 (drag&drop / 파일 / 카메라)
- Gemini 재랭크 토글
- **➕ DB에 추가하기** (접힘) — MFC URL 탭 / 직접 입력 탭. 직접 입력은 캐릭터/origin/제조사가 DB autocomplete.

### 결과 페이지

- best 카드 + 정가/파트너 호가 막대 차트
- 매칭 confidence가 high가 아니면 **🌐 Gemini 웹 검색** (힌트 입력 가능)
- Gemini 후보 3개 탭으로 비교
- "✅ 이 사진이 맞아요" — best/alternates에 → 올린 사진을 그 figure의 추가 reference로 등록 + 즉시 임베딩

## 7. 자주 쓰는 명령

```bash
# DB 직접 조회
sqlite3 data/figures.db
.headers on
.mode column
SELECT COUNT(*) FROM figures;
SELECT character_name, COUNT(*) FROM figures GROUP BY character_name ORDER BY 2 DESC LIMIT 20;

# 임베딩 카운트
sqlite3 data/figures.db "SELECT COUNT(*) FROM figure_embeddings"

# 이미지 디스크 사용량
du -sh data/images
```

## 8. 문제 해결


| 증상                                  | 원인/대응                                                                                |
| ----------------------------------- | ------------------------------------------------------------------------------------ |
| `transformers` 임포트 시 torchvision 에러 | `pip install torchvision`                                                            |
| 첫 식별이 ~45초 걸림                       | DINOv2 모델 + u2net 모델 최초 다운로드. 이후 ~3 img/s                                            |
| MFC가 503/403 무더기로 반환                | rate limit. 1~2시간 쉬고 `MFC_REQUEST_DELAY_SEC`을 2.5+로 올려서 재시도                          |
| `figure_images.figure_id UNIQUE` 충돌 | `python -m db.migrate_figure_images` 실행 (1회)                                         |
| `Cannot find variable` HMR 에러       | Vite HMR 깨진 잔재. 브라우저 새로고침                                                            |
| /lookup "Gemini가 JSON 대신 텍스트"       | lite 모델 instruction-follow 약함. uvicorn 로그에 raw reply 찍힘 — prompt 손보거나 모델을 2.5-flash로 |
| /lookup 한도 초과                       | UI 메시지대로 분당이면 N초 대기, 일일이면 익일                                                         |


## 9. 라이선스 / 사용 주의

- 학습/개인용 도구. 배포 안 함.
- MFC 크롤링은 robots.txt + `MFC_REQUEST_DELAY_SEC=1.0` 폴라이트 페이스 준수. 본인 IP에서만 운영.
- 이미지는 MFC/메이커 사이트에서 캐싱하므로 재배포 금지.

