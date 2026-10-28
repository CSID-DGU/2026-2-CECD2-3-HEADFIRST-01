# 의도-엔티티 분류기 PoC — Web

생성형 AI 활용 사용자 의도-엔티티 분류기 구축 PoC의 프론트엔드입니다.
AI 상담원이 구청 민원 접수 질문을 순서대로 하고, 민원인 답변(음성/텍스트)을 **턴마다 분류해 접수 상태를 누적**합니다.
분류 규칙은 레포 루트의 [`ontology/ontology.yaml`](../ontology/ontology.yaml) (v0.2)을 따릅니다.

> 현재는 백엔드 없이 **Mock 모드**로 동작합니다.
> 음성은 녹음 내용과 관계없이 시연용 대화가 순서대로 나오고, 텍스트는 온톨로지 예시 발화만 인식합니다.

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

> 마이크 녹음은 브라우저 보안 정책상 **HTTPS 또는 localhost** 에서만 됩니다.
> 같은 와이파이의 다른 기기에서 `http://192.168.x.x:5173` 으로 접속하면 녹음이 막힙니다 (텍스트·파일 입력은 가능).

## 기술 스택

- **Vite + React 19 + TypeScript**
- **Tailwind CSS v4** — `className` 으로 스타일링 (`src/index.css` 에 브랜드 색 정의)
- **react-router-dom v7** — 페이지 라우팅
- **lucide-react** — 아이콘
- 녹음은 브라우저 내장 `MediaRecorder` (별도 라이브러리 없음)

## 페이지

| 경로          | 페이지         | 상태                                                     |
| ------------- | -------------- | -------------------------------------------------------- |
| `/`           | 상담 데모      | ✅ 대화 진행 · 음성 녹음/파일/텍스트 입력 · 접수 상태 누적 |
| `/classify`   | 단일 발화 분류 | ✅ 음성 파일 1개 분류 (이전 규격, 정리 예정)              |
| `/history`    | 분류 기록      | 🚧 자리만 있음                                           |
| `/evaluation` | 모델 평가      | 🚧 자리만 있음 (LLM-as-a-Judge)                          |
| `/about`      | 시스템 소개    | ✅ 파이프라인 · 프로젝트 정보                            |

## 상담 데모 동작

1. AI 상담원이 아직 못 받은 항목을 순서대로 묻는다 (`utils/nextQuestion.ts`)
2. 민원인이 음성(녹음 / 파일) 또는 텍스트로 답한다
3. 서버가 발화를 분류해 `frames` 를 돌려준다 (한 발화에 여러 개 가능, 질문한 의도가 맨 앞)
4. `frames` 를 접수 상태에 반영한다 (`utils/dialogState.ts`)
   - `inform` → 값 저장. 이미 다른 값이 있으면 **최신 값으로 정정**하고 이전 값은 기록에 남김
   - `uncertain` → 이미 받은 값은 유지, 값이 없으면 ‘불확실’ 표시 후 다시 질문
   - 부분값(`010-????-7777`)은 ‘일부’ 로 표시하고 일단 넘어감
5. 모든 항목을 받으면 요약을 보여주고 끝낸다. 개인정보 수집에 동의하지 않으면 바로 끝낸다.

> 재질문·확인 질문 같은 **대화 정책**은 분류기 완성 후 팀에서 정하기로 했으므로
> 지금은 가장 단순한 규칙만 `utils/nextQuestion.ts` 한 곳에 모아 두었습니다. 정책이 정해지면 이 파일만 바꾸면 됩니다.

## 폴더 구조

```
src/
├── api/                    # 서버 통신
│   ├── client.ts           #   fetch 공통 래퍼 (에러 처리)
│   ├── dialog.ts           #   ⭐ 대화 턴 API 호출 (Mock / 실제 전환)
│   ├── mockDialog.ts       #   가짜 분류기 (시연용 대화 + 온톨로지 예시 매칭)
│   ├── classify.ts         #   단일 발화 분류 API (이전 규격)
│   └── mock.ts             #   단일 발화 가짜 응답
├── components/
│   ├── dialog/             # 상담 데모: 말풍선, frame 표시, 접수 상태, 입력창(녹음·텍스트)
│   ├── audio/              # 업로드 영역, 미리듣기 플레이어, 파형
│   ├── common/             # Card, PageHeader, Placeholder
│   ├── layout/             # 사이드바, 모바일 헤더
│   ├── pipeline/           # 처리 단계 진행 표시
│   └── result/             # 단일 발화 결과 (의도 · 발화 · 엔티티)
├── constants/
│   ├── ontology.ts         # ⭐ ontology.yaml 사본 (의도 · 질문 · 형식 · 예시)
│   └── pipeline.ts         # 파이프라인 단계 정의
├── hooks/
│   ├── useDialog.ts        # ⭐ 대화 상태 (턴 보내기 → frames 받기 → 상태 갱신)
│   ├── useRecorder.ts      # 마이크 녹음 (경과 시간 · 입력 크기)
│   ├── useAudioFile.ts     # 파일 검사 · 미리듣기 URL · 재생 길이
│   ├── useClassify.ts      # 단일 발화 분류 요청 상태
│   └── useWaveform.ts      # 파형 계산
├── pages/                  # 라우트별 페이지
├── types/
│   ├── dialog.ts           # ⭐ 대화 API 요청/응답 타입 (백엔드와 맞출 규격)
│   └── classify.ts         # 단일 발화 API 타입 (이전 규격)
├── utils/
│   ├── dialogState.ts      # frames → 접수 상태 반영 (정정 · 부분값 처리)
│   ├── nextQuestion.ts     # 다음 질문 결정 (대화 정책 자리)
│   └── ...                 # 날짜 · 포맷팅 · 파일 검사 · 엔티티 색상
├── config.ts               # 환경 변수
└── routes.tsx              # 사이드바 메뉴 목록
```

> `constants/ontology.ts` 는 `ontology/ontology.yaml` 을 손으로 옮긴 사본입니다. **yaml 이 바뀌면 이 파일도 같이 고쳐주세요.**

## 백엔드 연결하기

1. `.env.example` 을 `.env.local` 로 복사
2. 아래처럼 수정 후 `npm run dev` 재시작

```env
VITE_USE_MOCK=false
VITE_API_PROXY_TARGET=http://localhost:8000   # 백엔드 주소
```

개발 서버가 `/api/*` 요청을 백엔드로 넘겨주므로(프록시) CORS 설정 없이 붙일 수 있습니다.

### API 명세 초안 — `POST /api/dialog/turn`

대화 한 턴(AI 질문 1개 + 민원인 응답 1개)마다 한 번 호출합니다. 서버는 상태를 저장하지 않아도 됩니다.
프론트가 매번 지금까지의 대화(`history`)를 같이 보내고, 접수 상태 누적은 프론트에서 합니다.

**요청**: `multipart/form-data`

| 필드      | 타입          | 설명                                              |
| --------- | ------------- | ------------------------------------------------- |
| `payload` | string (JSON) | 아래 `TurnRequest`                                |
| `audio`   | File          | 음성 입력일 때만 (`.webm` · `.m4a` · `.wav` 등) |

```json
{
  "sessionId": "8f1c…",
  "callDate": "2026-10-12",
  "askedIntent": "occurred_date",
  "history": [
    { "askedIntent": "consent", "utterance": "뭐 그러던가요" },
    { "askedIntent": "phone", "utterance": "공일공에 일이삼사에 오육칠팔" }
  ],
  "text": "그저께부터요"
}
```

- `callDate`: 통화 날짜. "그저께" 같은 상대 날짜는 이 날짜 기준으로 계산
- `askedIntent`: 이번에 물어본 의도. 온톨로지 규칙대로 응답 `frames` 맨 앞에 항상 포함
- `history`: 이전 턴들 (예: "아까 전화번호 끝자리 5679예요" 같은 이전 턴 정정을 풀 때 필요)
- `text`: 텍스트 입력일 때만 있음 → STT 없이 바로 분류

**응답** (`src/types/dialog.ts` 의 `TurnResponse`)

```json
{
  "transcript": "그저께부터요 아 그리고 아까 전화번호 끝자리 오육칠팔 아니고 오육칠구예요",
  "frames": [
    { "intent": "occurred_date", "action": "inform", "value": "2026-10-10" },
    { "intent": "phone", "action": "inform", "value": "010-1234-5679" }
  ],
  "sttEngine": "whisper-large-v3-turbo",
  "latencyMs": { "stt": 800, "inference": 900, "total": 1700 }
}
```

- `frames` 형식은 `ontology.yaml` 의 `output` 과 같음 (`action`: `inform` | `uncertain`, `uncertain` 이면 `value` 는 `null`)
- `consent` 의 `value` 는 `true` / `false`, 나머지는 각 의도의 `format` 을 따르는 문자열
- `sttEngine`, `latencyMs` 는 **선택** 필드
- 모르는 `intent` · `action` 은 프론트에서 무시함
- 에러 시 `{ "detail": "메시지" }` 형태로 주면 화면에 그대로 표시

<details>
<summary>단일 발화 분류 — <code>POST /api/classify</code> (이전 규격)</summary>

**요청**: `multipart/form-data` 의 `audio` (음성 파일)

**응답** (`src/types/classify.ts` 의 `ClassifyResponse`)

```json
{
  "requestId": "abc123",
  "transcript": "음 그 저기 지하철 이호선 강남역에서 어 지갑을 잃어버렸는데요",
  "normalizedText": "지하철 2호선 강남역에서 지갑을 잃어버렸는데",
  "intent": { "label": "분실물_문의", "confidence": 0.94 },
  "candidates": [{ "label": "분실물_문의", "confidence": 0.94 }],
  "entities": [{ "type": "역명", "value": "강남역", "start": 8, "end": 11 }],
  "latencyMs": { "stt": 900, "inference": 1600, "total": 3000 }
}
```

</details>

## 다음 할 일

- [ ] 백엔드와 `/api/dialog/turn` 규격 확정 → `types/dialog.ts` 수정
- [ ] 대화 정책 확정 (부분값 재질문, 확인 질문, 같은 질문 반복 제한) → `utils/nextQuestion.ts`
- [ ] 단계별 진행 상황 실시간 수신 (SSE / WebSocket) → `api/dialog.ts` 의 TODO
- [ ] 단일 발화 분류 페이지 정리 (새 규격으로 바꾸거나 삭제)
- [ ] 분류 기록 페이지
- [ ] LLM-as-a-Judge 평가 페이지
