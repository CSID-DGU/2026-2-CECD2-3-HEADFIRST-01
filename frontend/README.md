# 의도-엔티티 분류기 PoC — Web

생성형 AI 활용 사용자 의도-엔티티 분류기 구축 PoC의 프론트엔드입니다.
음성 파일을 올리면 **STT → 발화 노이즈 제거 → 의도·엔티티 분류** 결과를 보여줍니다.

> 현재는 백엔드 없이 **Mock 모드**로 동작합니다. 음성 내용과 관계없이 샘플 결과가 나옵니다.

## 실행

```bash
npm install
npm run dev        # http://localhost:5173
```

| 명령어            | 설명                         |
| ----------------- | ---------------------------- |
| `npm run dev`     | 개발 서버                    |
| `npm run build`   | 타입 검사 + 배포용 빌드      |
| `npm run preview` | 빌드 결과 미리보기           |
| `npm run lint`    | 코드 검사 (oxlint)           |

## 기술 스택

- **Vite + React 19 + TypeScript**
- **Tailwind CSS v4** — `className` 으로 스타일링 (`src/index.css` 에 브랜드 색 정의)
- **react-router-dom v7** — 페이지 라우팅
- **lucide-react** — 아이콘

## 페이지

| 경로          | 페이지      | 상태                                   |
| ------------- | ----------- | -------------------------------------- |
| `/`           | 분류 데모   | ✅ 음성 업로드 · 미리듣기 · 결과 표시 |
| `/history`    | 분류 기록   | 🚧 자리만 있음                         |
| `/evaluation` | 모델 평가   | 🚧 자리만 있음 (LLM-as-a-Judge)        |
| `/about`      | 시스템 소개 | ✅ 파이프라인 · 프로젝트 정보          |

## 폴더 구조

```
src/
├── api/                  # 서버 통신
│   ├── client.ts         #   fetch 공통 래퍼 (에러 처리)
│   ├── classify.ts       #   분류 API 호출 (Mock / 실제 전환)
│   └── mock.ts           #   가짜 응답
├── components/
│   ├── audio/            # 업로드 영역, 미리듣기 플레이어, 파형
│   ├── common/           # Card, PageHeader, Placeholder
│   ├── layout/           # 사이드바, 모바일 헤더
│   ├── pipeline/         # 처리 단계 진행 표시
│   └── result/           # 의도 · 발화 · 엔티티 · 처리 정보
├── constants/pipeline.ts # 파이프라인 단계 정의
├── hooks/
│   ├── useAudioFile.ts   # 파일 검사 · 미리듣기 URL · 재생 길이
│   ├── useClassify.ts    # 분류 요청 상태 (idle → running → success/error)
│   └── useWaveform.ts    # 파형 계산
├── pages/                # 라우트별 페이지
├── types/classify.ts     # ⭐ API 요청/응답 타입 (백엔드와 맞출 규격)
├── utils/                # 포맷팅, 파일 검사, 엔티티 색상
├── config.ts             # 환경 변수
└── routes.tsx            # 사이드바 메뉴 목록
```

## 음성 업로드

- 드래그 앤 드롭 또는 클릭으로 파일 1개 선택
- 허용 형식: `.wav` `.mp3` `.m4a` `.flac` `.ogg` `.webm`, 최대 25MB (`VITE_MAX_UPLOAD_MB` 로 변경)
- 파형 + 재생 / 일시정지 / 파형 클릭으로 위치 이동
- 분류 중 취소 가능

## 백엔드 연결하기

1. `.env.example` 을 `.env.local` 로 복사
2. 아래처럼 수정 후 `npm run dev` 재시작

```env
VITE_USE_MOCK=false
VITE_API_PROXY_TARGET=http://localhost:8000   # 백엔드 주소
```

개발 서버가 `/api/*` 요청을 백엔드로 넘겨주므로(프록시) CORS 설정 없이 붙일 수 있습니다.

### API 명세 초안 — `POST /api/classify`

**요청**: `multipart/form-data`

| 필드    | 타입 | 설명      |
| ------- | ---- | --------- |
| `audio` | File | 음성 파일 |

**응답** (`src/types/classify.ts` 의 `ClassifyResponse`)

```json
{
  "requestId": "abc123",
  "transcript": "음 그 저기 지하철 이호선 강남역에서 어 지갑을 잃어버렸는데요",
  "normalizedText": "지하철 2호선 강남역에서 지갑을 잃어버렸는데",
  "intent": { "label": "분실물_문의", "confidence": 0.94 },
  "candidates": [
    { "label": "분실물_문의", "confidence": 0.94 },
    { "label": "역_시설_문의", "confidence": 0.04 }
  ],
  "entities": [
    { "type": "노선", "value": "2호선", "start": 4, "end": 7 },
    { "type": "역명", "value": "강남역", "start": 8, "end": 11 }
  ],
  "latencyMs": { "stt": 900, "inference": 1600, "total": 3000 }
}
```

- `normalizedText`, `candidates`, `start/end`, `latencyMs` 는 **선택** 필드 (없어도 화면이 깨지지 않음)
- `start/end` 는 `normalizedText` 기준 글자 위치. 없으면 `value` 로 문장에서 찾아서 강조
- 에러 시 `{ "detail": "메시지" }` 형태로 주면 화면에 그대로 표시

## 다음 할 일

- [ ] 백엔드와 응답 규격 확정 → `types/classify.ts` 수정
- [ ] 단계별 진행 상황 실시간 수신 (SSE / WebSocket) → `api/classify.ts` 의 TODO
- [ ] 분류 기록 페이지
- [ ] LLM-as-a-Judge 평가 페이지
