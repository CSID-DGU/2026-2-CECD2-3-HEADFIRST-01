"""
유튜브 영상에서 실제 발화(raw) 후보 구간을 뽑아 라벨링용 CSV로 만드는 스크립트.

흐름: urls.txt → yt-dlp 오디오 다운로드(ffmpeg 불필요) → faster-whisper 전사(캐시)
      → 이름/나이/날짜/숫자 키워드 후보 구간 → 발화 패턴 단서(pattern_hint) 태깅
      → labeling.csv (기존 라벨 보존, 새 후보만 추가)

pattern_hint: 우리가 정의한 발화 패턴(9/30 패턴표) 중 방송 raw에서 나올 수 있는 것만
  정규식 단서로 자동 표시한다. 전화번호 계열(NU-1~5, DS-1~5)은 방송에서 거의 안 나와
  생성 데이터로 커버하므로 여기선 제외. 사람이 확인 후 pattern_tag에 확정값을 적는다.
  --pattern-only 를 주면 단서 없는 후보는 CSV에 넣지 않는다.

실행 예:
    python collect_utterances.py urls.txt                 # Mac/CPU
    python collect_utterances.py urls.txt --device cuda   # Windows GPU

필요 패키지: pip install -U yt-dlp faster-whisper kiwipiepy
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)로는 못 쓰는 문자(노래/노이즈 구간을 whisper가
# 히브리 문자 등 엉뚱한 유니코드로 잘못 전사하는 경우 등)가 나오면 디버그 print()가
# 그대로 죽어서 전사 결과가 캐시되기 전에 통째로 날아간다. 못 쓰는 문자는 ?로 치환.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

# ---------------------------------------------------------------------------
# 후보 키워드 패턴
# 숫자 부분은 (?P<num>...) / (?P<num1>...) / (?P<num2>...) 로, 단위 부분은
# (?P<unit>...) 로 이름을 붙인다. find_candidates()가 이 그룹들을 Kiwi 형태소
# 경계와 대조해서, "같이"의 "이", "오시면"의 "오시"처럼 단어 중간 음절이
# 우연히 숫자/단위처럼 보여서 걸리는 오탐을 걸러낸다.
# ---------------------------------------------------------------------------
NATIVE_NUM = r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔)"
SINO_NUM = r"(?:[일이삼사오육륙칠팔구십백천만]+)"
NUM = rf"(?:\d+|{NATIVE_NUM}+|{SINO_NUM})"

PATTERNS = {
    "age": [
        rf"(?P<num>{NUM})\s*(?P<unit>살)",
        rf"(?P<num>\d+)\s*(?P<unit>세)",
        r"연세|나이|몇\s*살|춘추",
    ],
    "date": [
        rf"(?P<num>{NUM})\s*년생",
        rf"(?P<num>\d+)\s*년",
        rf"(?P<num>{SINO_NUM})\s*년(?!\s*(?:동안|째))",
        rf"(?P<num1>{NUM})\s*월\s*(?P<num2>{NUM})?\s*일?",
        rf"(?P<num>\d+)\s*일",
        r"생일|생년|양력|음력|태어[나났]",
        r"(?:쥐|소|호랑이|범|토끼|용|뱀|말|양|원숭이|잔나비|닭|개|돼지)\s*띠",
    ],
    "name": [
        r"이름|성함|존함",
        r"[가-힣]{2,4}\s*(?:이라고|라고)\s*(?:합니다|해요|하는데|하고)",
        r"저는\s*[가-힣]{2,4}\s*(?:입니다|이에요|예요|이고)",
    ],
    "number": [
        r"(?P<num>\d+)",
        rf"(?P<num>{NUM})\s*(?P<unit>개|명|번|원|시|분|대|마리|그릇|권|장|병|잔|층|호|동|평|킬로|키로)",
        r"공일공|010|전화번호|번호",
    ],
}
COMPILED = {k: [re.compile(p) for p in v] for k, v in PATTERNS.items()}

# ---------------------------------------------------------------------------
# 발화 패턴 단서 (전화번호 패턴 제외)
# 값이 있는지가 아니라 "어떻게 말하는지"를 잡는다. raw_text만 검사한다
# (문맥까지 합치면 옆 문장의 단어가 붙어 오탐이 늘어남. 질문→답 관계는 SLOT_QUESTIONS가 문맥을 봄).
# 키 = 패턴표 코드. 사람이 pattern_tag에 확정값을 적을 때 참고용.
# ---------------------------------------------------------------------------
JAMO = (r"(?:기역|니은|디귿|리을|미음|비읍|시옷|이응|지읒|치읓|키읔|티읕|피읖|히읗"
        r"|쌍기역|쌍디귿|쌍비읍|쌍시옷|쌍지읒)")
HAN = r"[가-힣]"
PATTERN_HINTS = {
    # 이름: 글자풀이 ("박사 할 때 박", "영화의 영", "호 자예요")
    "NM-L1-1": [
        rf"{HAN}+\s*할\s*때\s*(?:그\s*)?(?![도는가를만에의요])({HAN})(?:\s|,|\.|$)",  # "박사 할 때 박" (밥할 때도 X)
        rf"(?:할\s*때\s*{HAN}\W*){{2,}}",
        rf"{HAN}+의\s+{HAN}\s+자",  # "영화의 영 자" (일요일의 남자 X)
        rf"(?<![가-힣])(?!외)(?:{HAN})\s+자\s*(?:[예이]에?요|입니다|를?\s*써|쓰[고는]|고요)",  # 띄어쓴 단독 글자 + 자 ("호 자예요"); 남자예요·외자예요 제외
    ],
    # 이름: 자모 설명 ("시옷에 오 이응 받침")
    "NM-L1-2/3": [JAMO, r"받침\s*(?:다음|이고|에|이에요)"],
    # 이름: 글자 단위 교정 ("지읒이 아니라 치읓", "우가 아니라 오")
    "NM-L2": [
        rf"{HAN}{{1,2}}(?:이|가)\s*아니라\s*{HAN}{{1,2}}(?:[예이]에?요|입니다|이고|요)",
        rf"(?:^|\s){HAN}\s*말고\s*{HAN}(?:\s|$|[예이]에?요)",
        r"(?:첫|가운데|끝|마지막)\s*(?:글자|자)\s*(?:가|는|를|의|모음|받침)",
    ],
    # 이름: 두 글자 단어+한 글자 ("공주 할 때 그 공주에 영 자")
    "NM-SP-1": [rf"{HAN}{{2}}\s*할\s*때\s*(?:그\s*)?{HAN}{{2}}에\s*{HAN}\s*자"],
    # 이름: 서류상 표기 다름
    "NM-SP-3": [r"서류|호적|주민등록|등본|신분증|주민증"],
    # 이름: 외자
    "NM-SP-4": [r"외자|외\s*자(?:예요|입니다|야)"],
    # 생년월일: 연속 숫자/년생 ("천구백사십팔 년", "오삼년생")
    "DA-1": [
        rf"(?:천\s*구백|19)\s*(?:{SINO_NUM}|\d+)?\s*년",
        rf"(?:{SINO_NUM}|\d{{2,4}})\s*년\s*생",
        rf"(?:{SINO_NUM}|\d+)\s*년\s*(?:{SINO_NUM}|\d+)\s*월\s*(?:{SINO_NUM}|\d+)\s*일",
    ],
    # 음력·전통 날짜 표현
    "DA-2": [
        r"음력|양력으로|초하루|초이틀|초사흘|초나흘|초닷새|초엿새|초이레|초여드레|초아흐레"
        r"|보름|그믐|정월|섣달|동짓달|윤달",
    ],
    # 나이 + 생일 조합 ("올해 예순일곱이고 생일은 십이월 팔일")
    "DA-3": [
        rf"(?:올해|금년|지금)\s*(?:{NUM})[가-힣]*\s*(?:이고|인데|이에요|예요|입니다|살)",
        rf"생일(?:은|이)?\s*(?:{NUM})\s*월",
    ],
    # 상대 날짜(근접) ("그저께부터", "어제 아침에")
    "DA-4": [r"그저께|그제|어제|엊그제|오늘\s*(?:아침|새벽|오전|오후)|며칠\s*전|사흘\s*전|나흘\s*전|이틀\s*전"],
    # 상대 날짜(주·요일 기준) ("지난주 목요일부터")
    "DA-5": [r"지난\s*주|이번\s*주|저번\s*주|지지난|지난\s*달|저번\s*달|[월화수목금토일]요일\s*(?:부터|에|쯤)"],
    # 교정·번복 (이름·날짜 등 비번호 값) ("아니 팔일", "다시 말하면")
    "FIX": [
        rf"(?:^|\s)아니\s+(?!까|야|요|고|지|에요|예요|면|근데|그래)(?:[일이삼사오육륙칠팔구십백천]{{2,}}|(?:{SINO_NUM}|{NATIVE_NUM})\s*(?:년|월|일|살|번)|{HAN}{{2,3}}(?:이요|예요|이에요|입니다))",
        r"다시\s*말(?:하|씀)|잘못\s*말|틀렸(?:어|네|다|습)|아니고\s",
    ],
    # 불확실 ("몇 년이더라", "기억이 안 나", "양띠인데")
    "UN-1": [
        r"기억이?\s*(?:안|잘)\s*(?:나|남)|몇\s*(?:년|살|월|일)이?더라|가물가물|확실치|헷갈",
        r"(?:나이|생일|생년|날짜|몇\s*(?:년|살|월|일)|언제|이름|성함)[^.?!]{0,10}(?:모르겠|잊어|기억)",  # 값 근처의 모르겠/잊어
        r"(?:쥐|소|호랑이|범|토끼|용|뱀|말|양|원숭이|잔나비|닭|개|돼지)띠(?:인데|[예이]에?요|입니다|이고|야|요|니까|\s|$)",
    ],
    # 불확실·무관심 ("아무렇게나 해요", "상관없어요")
    "UN-2": [r"아무렇게나|상관\s*없|알아서\s*(?:해|하세요)|아무\s*때나|언젠지"],
    # 민원 유형 서술 ("길이 움푹 패여서", "차를 양쪽으로 대놔서")
    "CT-1": [
        r"움푹|패[여였]|파손|깨[져졌]|불법\s*주정차|주차\s*(?:해|를|가)|소음|시끄러|쓰레기|악취|냄새"
        r"|가로등|신호등|하수구|맨홀|누수|물이\s*새|방치|무단\s*투기|불편(?:해|하|을|이)|민원|신고(?:를|했|하|할)|고장\s*(?:났|이\s*나|나서)",
    ],
}
COMPILED_HINTS = {k: [re.compile(p) for p in v] for k, v in PATTERN_HINTS.items()}

# 직전 세그먼트가 슬롯 질문이면 현재 발화를 "답변 후보"로 표시한다 (Q:age 등).
# 답이 값이면 inform, "아이 몰라요"·동문서답이면 재질문 대상(나머지 클래스) → 이진 분류의 양쪽 예시가 모두 모인다.
SLOT_QUESTIONS = {
    "Q:age": r"연세|나이|몇\s*살|춘추|년생이",
    "Q:name": r"성함|이름|존함|누구|어떻게\s*불러",  # 질문 문맥("?"/의문형 어미)에서만 검사하므로 누구 단독 허용
    "Q:date": r"생일|생년|몇\s*년|언제|며칠|몇\s*월",
    "Q:where": r"어디\s*(?:사|살|서\s*오|에서)|사는\s*곳|고향",
}
COMPILED_Q = {k: re.compile(v) for k, v in SLOT_QUESTIONS.items()}
# 질문 뒤에 오는 전형적 비정보 답(재질문 대상). UN-1과 별도로 질문 문맥에서만 잡는다.
NON_INFORM_ANSWER = re.compile(r"몰라|모르|글쎄|뭐라고|네\?|에\?|응\?|말이에요|왜\s*물어|비밀")


def find_slot_questions(prev_text, cur_text):
    """prev_text가 슬롯 질문이면 해당 Q 코드 목록을 돌려준다. 답이 비정보형이면 'A:non-inform'도 붙인다."""
    if not prev_text or "?" not in prev_text and not re.search(r"(?:세요|습니까|예요|에요|나요|어요|죠)\s*$", prev_text):
        return []
    codes = [k for k, r in COMPILED_Q.items() if r.search(prev_text)]
    if codes and NON_INFORM_ANSWER.search(cur_text):
        codes.append("A:non-inform")
    return codes
# 패턴표에 있지만 방송 raw에선 안 모으는 것: NU-1~5, DS-1~5(전화번호), CS-1(동의), RC-1(회신)
EXCLUDED_PATTERNS = ["NU-1", "NU-2", "NU-3", "NU-4", "NU-5", "DS-1", "DS-2", "DS-3", "DS-4", "DS-5",
                     "CS-1", "RC-1"]


def find_pattern_hints(text):
    """발화 패턴 단서 코드 목록과 매칭 문자열 반환. text는 앞뒤 문맥을 합친 문자열."""
    codes, matched = [], []
    for code, regs in COMPILED_HINTS.items():
        hits = [m.group(0).strip() for r in regs for m in r.finditer(text)]
        hits = [h for h in hits if h]
        if hits:
            codes.append(code)
            matched.extend(hits)
    return codes, list(dict.fromkeys(matched))


NUM_TAGS = {"SN", "NR", "MM"}  # 아라비아 숫자 / 수사 / 수 관형사(한·두·세·스무 등)

# 사람이 채울 칸
LABEL_COLS = ["speaker_group", "corrected_text", "entity_type", "gt_value",
              "pattern_tag", "usable", "notes"]
# 10/19 정리: video_id·memo·end·cand_types·matched 제거(url에 영상ID·시작초가 있고, 1단계 필터 디버그 칸은 라벨링에 불필요)
AUTO_COLS = ["cand_id", "url", "start",
             "context_prev", "raw_text", "context_next",
             "pattern_hint", "hint_matched"]
ALL_COLS = AUTO_COLS + LABEL_COLS


BLACKLIST = {"한번"}  # "한번/한 번" 등 띄어쓰기 무관하게 걸러냄: 횟수 관용구라 엔티티 신호 아님

_kiwi = None


def get_kiwi():
    """Kiwi 형태소 분석기 지연 로딩(싱글턴)."""
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()
    return _kiwi


def _span_covered(s, e, spans, allowed_tags=None):
    """[s, e) 구간이 spans(형태소 (start,end,tag) 목록)로 빈틈/겹침 없이 정확히
    덮이는지 확인. allowed_tags가 주어지면 그 형태소들의 태그도 전부 검사한다.
    "같이"의 "이"처럼 형태소 중간에서 잘린 구간이나, "오시"(VV+EP)처럼 경계는
    맞아도 태그가 숫자류가 아닌 구간을 걸러내는 용도."""
    covered = sorted(sp for sp in spans if sp[0] < e and sp[1] > s)
    if not covered or covered[0][0] != s or covered[-1][1] != e:
        return False
    cursor = s
    for a, b, tag in covered:
        if a != cursor or (allowed_tags is not None and tag not in allowed_tags):
            return False
        cursor = b
    return cursor == e


def find_candidates(text):
    """텍스트에서 매칭된 엔티티 타입과 매칭 문자열 반환.
    num/num1/num2로 표시된 숫자 구간은 Kiwi 형태소 태그가 SN/NR/MM(아라비아
    숫자·수사·수관형사)인지 확인하고, unit으로 표시된 단위 구간은 독립된
    형태소 경계와 맞는지만 확인한다. 둘 중 하나라도 안 맞으면 그 매치는 버린다."""
    spans = [(t.start, t.start + t.len, t.tag) for t in get_kiwi().tokenize(text)]
    types, matched = [], []
    for etype, regs in COMPILED.items():
        hits = []
        for r in regs:
            for m in r.finditer(text):
                ok = True
                for name, val in m.groupdict().items():
                    if val is None:
                        continue
                    s, e = m.span(name)
                    allowed = NUM_TAGS if name.startswith("num") else None
                    if not _span_covered(s, e, spans, allowed):
                        ok = False
                        break
                if ok:
                    hits.append(m.group(0).strip())
        hits = [h for h in hits if h and re.sub(r"\s+", "", h) not in BLACKLIST]
        if hits:
            types.append(etype)
            matched.extend(hits)
    # number는 다른 타입과 겹치면 중복이라 단독일 때만 남김
    if "number" in types and len(types) > 1:
        types.remove("number")
    return types, list(dict.fromkeys(matched))


# ---------------------------------------------------------------------------
# urls.txt / 다운로드
# ---------------------------------------------------------------------------
def read_urls(path):
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        items.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return items


def guess_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})", url)
    return m.group(1) if m else None


def find_cached_audio(audio_dir, vid):
    for p in audio_dir.glob(f"{vid}.*"):
        if p.suffix not in (".part", ".ytdl", ".json"):
            return p
    return None


def download_audio(url, audio_dir):
    import yt_dlp

    vid = guess_video_id(url)
    if vid and (cached := find_cached_audio(audio_dir, vid)):
        return vid, cached

    opts = {
        # 후처리(ffmpeg) 없이 원본 오디오 스트림만 받음. faster-whisper가 PyAV로 바로 디코딩.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(audio_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    vid = info["id"]
    path = find_cached_audio(audio_dir, vid)
    if path is None:
        raise RuntimeError(f"다운로드 후 파일을 못 찾음: {vid}")
    return vid, path


# ---------------------------------------------------------------------------
# 전사 (캐시)
# ---------------------------------------------------------------------------
_model = None


def add_nvidia_dll_paths():
    """Windows: pip로 깐 nvidia-cublas/cudnn DLL(site-packages/nvidia/*/bin)을 검색 경로에 추가.
    안 하면 'cublas64_12.dll is not found' 에러."""
    if os.name != "nt":
        return
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        print("[cuda] nvidia-cublas-cu12 / nvidia-cudnn-cu12 미설치", file=sys.stderr)
        return
    for base in spec.submodule_search_locations:
        for bin_dir in Path(base).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


def get_model(args):
    global _model
    if _model is None:
        if args.device == "cuda":
            add_nvidia_dll_paths()
        from faster_whisper import WhisperModel

        compute = args.compute_type or ("float16" if args.device == "cuda" else "int8")
        print(f"[model] {args.model} / {args.device} / {compute}")
        _model = WhisperModel(args.model, device=args.device, compute_type=compute)
    return _model


def load_audio(path, sr=16000):
    """16kHz mono float32로 디코딩.
    faster-whisper 내장 decode_audio는 PyAV 15+에서 metadata_errors 인자 때문에 깨져서 직접 디코딩."""
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    chunks = []
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray() for f in resampler.resample(None))  # flush
    audio = np.concatenate(chunks, axis=1).flatten()
    return audio.astype(np.float32) / 32768.0


def transcribe(audio_path, vid, tr_dir, args):
    cache = tr_dir / f"{vid}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["segments"]

    model = get_model(args)
    segments, info = model.transcribe(
        load_audio(audio_path), language="ko", beam_size=5, vad_filter=True,
    )
    segs = []
    for s in segments:
        segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                     # 노래·무음 구간 환청 판정용 (mark_junk 참고)
                     "no_speech_prob": round(s.no_speech_prob, 3),
                     "avg_logprob": round(s.avg_logprob, 3),
                     "compression_ratio": round(s.compression_ratio, 3)})
        print(f"  [{s.start:7.1f}s] {s.text.strip()}", flush=True)
    cache.write_text(
        json.dumps({"video_id": vid, "model": args.model, "duration": info.duration,
                    "segments": segs}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return segs


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def load_existing(csv_path):
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sort_key(row):
    """영상ID → 시작 시각 순. cand_id가 '영상ID_시작초(08.2f)' 형식이라 문자열 정렬만으로는
    영상 안에서 시간순이 보장되지만, 영상 간 순서는 urls.txt 등장 순이 아니라 ID 순이 된다."""
    vid, start = row["cand_id"].rsplit("_", 1)
    try:
        start = float(row.get("start") or start)
    except ValueError:
        start = 0.0
    return (vid, start)


def save_rows(csv_path, rows):
    # 저장할 때마다 영상별·시간순으로 정렬 (후보가 나중에 추가돼도 섞이지 않게)
    rows.sort(key=sort_key)
    # utf-8-sig: 윈도우 엑셀에서 한글 안 깨지게
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ALL_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# 노래·무음 구간 환청 제거
# 전국노래자랑처럼 노래가 긴 영상에서 whisper가 가사 대신 "hell", "한국어로요?" 같은
# 엉뚱한 문장을 1초 간격으로 반복 생성한다. 아래 두 계열로 거른다.
#  (a) whisper 신뢰도: no_speech_prob 높음 / avg_logprob 낮음 / compression_ratio 높음
#      (전사 캐시에 값이 없으면 이 검사는 건너뜀 → 캐시 json을 지우고 다시 전사하면 적용)
#  (b) 텍스트: 직전과 같은 문장 반복, 한글 비율 낮음
#      (1.0초 간격 연속 규칙은 실제 대화도 그렇게 잘려서 오탐이 많아 뺐다)
# 실제로 부른 가사(제대로 전사된 노래)는 여기서 못 거른다 → 사람이 usable=N
# ---------------------------------------------------------------------------
NO_SPEECH_MAX = 0.6
LOGPROB_MIN = -1.0
COMPRESSION_MAX = 2.4


def _norm(t):
    return re.sub(r"[\s.,!?~]", "", t)


def _hangul_ratio(t):
    core = re.sub(r"[\s\d.,!?~'\"()\[\]-]", "", t)
    if not core:
        return 0.0
    return sum("가" <= ch <= "힣" for ch in core) / len(core)


def mark_junk(segs):
    """각 세그먼트에 junk 사유 문자열을 붙여 돌려준다(빈 문자열이면 정상)."""
    reasons = [""] * len(segs)
    for i, s in enumerate(segs):
        r = []
        if s.get("no_speech_prob", 0) > NO_SPEECH_MAX:
            r.append("no_speech")
        if s.get("avg_logprob", 0) < LOGPROB_MIN:
            r.append("low_logprob")
        if s.get("compression_ratio", 0) > COMPRESSION_MAX:
            r.append("repetitive")
        if _hangul_ratio(s["text"]) < 0.5:
            r.append("non_hangul")
        if i > 0 and _norm(s["text"]) and _norm(s["text"]) == _norm(segs[i - 1]["text"]):
            r.append("dup_prev")
        reasons[i] = "|".join(r)
    return reasons


def build_candidates(vid, segs, pattern_only=False):
    rows = []
    junk = mark_junk(segs)
    for i, s in enumerate(segs):
        if junk[i]:
            continue
        types, matched = find_candidates(s["text"])
        prev = segs[i - 1]["text"] if i > 0 else ""
        nxt = segs[i + 1]["text"] if i + 1 < len(segs) else ""
        hints, hint_matched = find_pattern_hints(s["text"])
        hints = find_slot_questions(prev, s["text"]) + hints
        # 패턴 단서가 있으면 엔티티 키워드가 없어도 후보로 올린다(교정·불확실 발화는
        # 값 없이 나오는 경우가 많음). 둘 다 없으면 제외.
        if not types and not hints:
            continue
        if pattern_only and not hints:
            continue
        rows.append({
            "cand_id": f"{vid}_{s['start']:08.2f}",
            "url": f"https://youtu.be/{vid}?t={int(s['start'])}",
            "start": s["start"],
            "context_prev": prev,
            "raw_text": s["text"],
            "context_next": nxt,
            "pattern_hint": "|".join(hints),
            "hint_matched": "|".join(hint_matched),
            **{c: "" for c in LABEL_COLS},
        })
    return rows


def backfill_hints(rows, force=False):
    """pattern_hint 열이 없던 시절의 기존 행에 단서를 소급 계산한다. 라벨 칸은 건드리지 않음.
    force=True면 단서 규칙을 바꾼 뒤 전체 행을 다시 계산한다(--rehint)."""
    n = 0
    for r in rows:
        if force or r.get("pattern_hint") is None or r.get("hint_matched") is None:
            hints, matched = find_pattern_hints(r.get("raw_text", ""))
            hints = find_slot_questions(r.get("context_prev", ""), r.get("raw_text", "")) + hints
            r["pattern_hint"], r["hint_matched"] = "|".join(hints), "|".join(matched)
            n += 1
    return n


def drop_junk_rows(rows, tr_dir):
    """전사 캐시로 junk를 다시 판정해 라벨이 비어 있는 junk 행을 제거한다. 제거 수를 돌려준다."""
    junk_ids = set()
    for vid in {r["cand_id"].rsplit("_", 1)[0] for r in rows}:
        cache = tr_dir / f"{vid}.json"
        if not cache.exists():
            continue
        segs = json.loads(cache.read_text(encoding="utf-8"))["segments"]
        for s, why in zip(segs, mark_junk(segs)):
            if why:
                junk_ids.add(f"{vid}_{s['start']:08.2f}")
    keep, dropped = [], 0
    for r in rows:
        labelled = any(r.get(c) for c in LABEL_COLS)
        if r["cand_id"] in junk_ids and not labelled:
            dropped += 1
        else:
            keep.append(r)
    rows[:] = keep
    return dropped


def print_pattern_table(rows):
    """패턴 코드별 후보 수(단서 기준). 어떤 패턴이 비는지 보고 영상을 고르는 용도."""
    from collections import Counter

    c = Counter()
    for r in rows:
        for h in filter(None, r.get("pattern_hint", "").split("|")):
            c[h] += 1
    print("\n=== 패턴 단서별 후보 수 (사람 확인 전, 오탐 포함)")
    for code in list(SLOT_QUESTIONS) + ["A:non-inform"] + list(PATTERN_HINTS):
        print(f"  {code:12s} {c.get(code, 0):4d}")
    n_hint = sum(1 for r in rows if r.get("pattern_hint"))
    print(f"  단서 있는 행 {n_hint} / 전체 {len(rows)}")
    per_video = Counter(r["cand_id"].rsplit("_", 1)[0] for r in rows)
    per_video_hint = Counter(r["cand_id"].rsplit("_", 1)[0] for r in rows if r.get("pattern_hint"))
    print("\n=== 영상별 후보 수 (전체 / 단서 있음)")
    for vid, n in per_video.most_common():
        print(f"  {vid:12s} {n:4d} {per_video_hint.get(vid, 0):4d}")
    print(f"  (raw 수집 제외 패턴: {', '.join(EXCLUDED_PATTERNS)} → 생성 데이터로 커버)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", help="URL 목록 파일 (한 줄에 URL + 메모)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"],
                    help="Mac은 cpu (faster-whisper는 MPS 미지원)")
    ap.add_argument("--model", default=None,
                    help="whisper 모델 (기본: cuda=large-v3, cpu=medium)")
    ap.add_argument("--compute-type", default=None)
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="labeling.csv")
    ap.add_argument("--pattern-only", action="store_true",
                    help="발화 패턴 단서(pattern_hint)가 있는 후보만 CSV에 추가")
    ap.add_argument("--rehint", action="store_true",
                    help="단서 규칙을 바꾼 뒤 기존 행 전체의 pattern_hint를 다시 계산하고 노래·환청 행을 제거")
    args = ap.parse_args()
    args.model = args.model or ("large-v3" if args.device == "cuda" else "medium")

    work = Path(args.work)
    audio_dir, tr_dir = work / "audio", work / "transcripts"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tr_dir.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.out)

    rows = load_existing(csv_path)
    seen = {r["cand_id"] for r in rows}
    print(f"[csv] 기존 {len(rows)}행")
    if n := backfill_hints(rows, force=args.rehint):
        print(f"[csv] 기존 {n}행에 pattern_hint 소급 계산")
        save_rows(csv_path, rows)
    if args.rehint and (n := drop_junk_rows(rows, tr_dir)):
        print(f"[csv] 노래·환청 구간 후보 {n}행 제거 (라벨 달린 행은 보존)")
        save_rows(csv_path, rows)

    summary = []
    for url, memo in read_urls(args.urls):
        print(f"\n=== {url}  ({memo})")
        try:
            vid, audio = download_audio(url, audio_dir)
            print(f"[audio] {audio.name}")
            segs = transcribe(audio, vid, tr_dir, args)
        except Exception as e:  # 영상 하나 실패해도 나머지는 계속
            print(f"[실패] {e}", file=sys.stderr)
            summary.append((url, "FAIL", 0, 0))
            continue

        cands = build_candidates(vid, segs, pattern_only=args.pattern_only)
        new = [c for c in cands if c["cand_id"] not in seen]
        rows.extend(new)
        seen.update(c["cand_id"] for c in new)
        save_rows(csv_path, rows)  # 영상마다 저장
        summary.append((url, vid, len(cands), len(new)))

    print("\n=== 요약 (영상 / 후보 / 신규)")
    for url, vid, n, n_new in summary:
        print(f"  {vid:12s} {n:4d} {n_new:4d}  {url}")
    print(f"[csv] {csv_path} 총 {len(rows)}행")
    print_pattern_table(rows)


if __name__ == "__main__":
    main()
