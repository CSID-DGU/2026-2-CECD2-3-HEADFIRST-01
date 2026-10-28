import type { Frame, IntentKey } from '@/types/dialog'

/**
 * 구청 민원 전화 접수 온톨로지 (프론트 사본)
 * 원본: ontology/ontology.yaml v0.2 — yaml 이 바뀌면 이 파일도 같이 고쳐주세요.
 */
export const ONTOLOGY_VERSION = '0.2'

export type OntologyExample = {
  utterance: string
  frames: Frame[]
  /** 상대 날짜 예시의 기준 통화 날짜 */
  callDate?: string
}

export type IntentDef = {
  key: IntentKey
  /** 화면 표시용 이름 */
  label: string
  /** AI가 묻는 질문 */
  question: string
  valueType: 'boolean' | 'free_text' | 'categorical'
  format?: string
  values?: string[]
  examples: OntologyExample[]
}

const inform = (intent: IntentKey, value: string | boolean): Frame => ({ intent, action: 'inform', value })
const uncertain = (intent: IntentKey): Frame => ({ intent, action: 'uncertain', value: null })

/** 질문 순서대로 정렬 (시나리오 진행 순서) */
export const INTENTS: IntentDef[] = [
  {
    key: 'consent',
    label: '개인정보 동의',
    question: '민원 접수를 위해 개인정보 수집에 동의하시나요?',
    valueType: 'boolean',
    examples: [
      { utterance: '네 동의해요', frames: [inform('consent', true)] },
      { utterance: '뭐 그러던가요', frames: [inform('consent', true)] },
      { utterance: '동의 안 할래요', frames: [inform('consent', false)] },
      { utterance: '이거 안 하면 어떻게 돼요', frames: [uncertain('consent')] },
    ],
  },
  {
    key: 'name',
    label: '성함',
    question: '성함이 어떻게 되세요?',
    valueType: 'free_text',
    format: '한글 2~5자',
    examples: [
      { utterance: '김천일입니다', frames: [inform('name', '김천일')] },
      { utterance: '김밥 할 때 김 그리고 천 원 할 때 천 하나 둘 할 때 일', frames: [inform('name', '김천일')] },
      { utterance: '손 승 현이요 손자 할 때 손', frames: [inform('name', '손승현')] },
      { utterance: '내 이름이 뭐였더라', frames: [uncertain('name')] },
      { utterance: '이름은 왜 물어보는 건데', frames: [uncertain('name')] },
      { utterance: '이름 말하기 싫은데요', frames: [uncertain('name')] },
      { utterance: '오공년생이요', frames: [uncertain('name'), inform('birth_date', '1950-??-??')] },
      {
        utterance: '김천일이고 오공년생 칠월 이일이에요',
        frames: [inform('name', '김천일'), inform('birth_date', '1950-07-02')],
      },
      { utterance: '김천일이고 말띠예요', frames: [inform('name', '김천일'), uncertain('birth_date')] },
    ],
  },
  {
    key: 'birth_date',
    label: '생년월일',
    question: '생년월일을 말씀해 주시겠어요?',
    valueType: 'free_text',
    format: "YYYY-MM-DD (모르는 자리는 '?')",
    examples: [
      { utterance: '오공년생 칠월 이일', frames: [inform('birth_date', '1950-07-02')] },
      { utterance: '1950년 6월 닷새요', frames: [inform('birth_date', '1950-06-05')] },
      { utterance: '오공년생이에요', frames: [inform('birth_date', '1950-??-??')] },
      { utterance: '공오년생이요', frames: [inform('birth_date', '2005-??-??')] },
      { utterance: '말띠고요', frames: [uncertain('birth_date')] },
      { utterance: '오사년생 말띠', frames: [inform('birth_date', '1954-??-??')] },
      { utterance: '오오년생 말띠', frames: [uncertain('birth_date')] },
      { utterance: '이월 삼십일이에요', frames: [uncertain('birth_date')] },
    ],
  },
  {
    key: 'phone',
    label: '연락처',
    question: '연락받으실 전화번호를 알려주세요.',
    valueType: 'free_text',
    format: "010-0000-0000 (모르는 자리는 '?')",
    examples: [
      { utterance: '공일공 3456 칠팔 구공', frames: [inform('phone', '010-3456-7890')] },
      { utterance: '010에 앞자리는 집 번호랑 같고 끝자리는 칠 4개', frames: [inform('phone', '010-????-7777')] },
      { utterance: '공일공에 일이삼사에 오육칠팔 아니 오육칠구', frames: [inform('phone', '010-1234-5679')] },
      { utterance: '공일공 일이삼 사오육', frames: [uncertain('phone')] },
      { utterance: '번호는 우리 아들이 알아', frames: [uncertain('phone')] },
    ],
  },
  {
    key: 'complaint_type',
    label: '민원 유형',
    question: '어떤 일로 연락 주셨어요?',
    valueType: 'categorical',
    values: ['불법 주정차', '도로·보도 파손', '가로등·보안등 고장', '불법 광고물', '쓰레기·동물 사체', '기타'],
    examples: [
      { utterance: '집 앞 길이 움푹 패여서 할머니가 넘어질 뻔했어', frames: [inform('complaint_type', '도로·보도 파손')] },
      { utterance: '골목 전봇대 불이 나갔는데 거기 차까지 세워놔서 밤에 못 지나가', frames: [uncertain('complaint_type')] },
    ],
  },
  {
    key: 'occurred_date',
    label: '발생 일자',
    question: '언제부터 그러셨어요?',
    valueType: 'free_text',
    format: 'YYYY-MM-DD',
    examples: [
      { utterance: '그저께부터요', callDate: '2026-10-08', frames: [inform('occurred_date', '2026-10-06')] },
      { utterance: '추석 지나고 한 닷새 됐나', frames: [uncertain('occurred_date')] },
    ],
  },
  {
    key: 'description',
    label: '민원 내용',
    question: '어떤 상황인지 자세히 말씀해 주세요.',
    valueType: 'free_text',
    format: '한두 문장 요약',
    examples: [
      {
        utterance: '우리 집 앞에 길이 움푹 패여서 어제 할머니가 넘어질 뻔했어 그거 좀 고쳐줘',
        frames: [inform('description', '집 앞 도로가 패여 보행자가 넘어질 뻔함')],
      },
    ],
  },
  {
    key: 'reply_channel',
    label: '회신 방법',
    question: '처리 결과는 어떻게 알려드릴까요?',
    valueType: 'categorical',
    values: ['문자', '전화', '회신 안 함'],
    examples: [
      { utterance: '문자로 주세요', frames: [inform('reply_channel', '문자')] },
      { utterance: '문자는 내가 못 봐요', frames: [inform('reply_channel', '전화')] },
      { utterance: '아무거나 해요', frames: [uncertain('reply_channel')] },
    ],
  },
]

export const INTENT_MAP = Object.fromEntries(INTENTS.map((d) => [d.key, d])) as Record<IntentKey, IntentDef>

export const INTENT_ORDER: IntentKey[] = INTENTS.map((d) => d.key)
