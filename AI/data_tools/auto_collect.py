"""
자동 수집 루프: 유튜브 검색 → 미사용 영상 선별 → 전사 → 선채움 → '강한 후보' 수 집계 → 목표 도달까지 반복.

강한 후보 = 선채움 y 행 중 질문→답 단서(Q:age/Q:name/Q:date/A:non-inform)나 값 단서(DA-1~3, NM-*, FIX, UN-1)가 있고
내레이션 문어체(~습니다/~이다 로 끝남)가 아닌 행. 사람(또는 AI 선라벨)이 볼 가치가 있는 행의 근사치.

각 배치는 work/labeling_autoN.csv 로 따로 저장한다 (검수 중인 labeling.csv와 충돌 방지). 합치기는 나중에 수동.

실행:
  python auto_collect.py --target 150 --batch-size 40 --max-batches 6
  (conda env capstone2. 로그: work/auto_collect.log, 상태: work/auto_collect_state.json)
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PY = sys.executable
BASE = Path(__file__).parent
WORK = BASE / "work"
STATE = WORK / "auto_collect_state.json"
LOG = WORK / "auto_collect.log"

# 수율이 확인된 유형의 검색어 (순환). 각 검색어에서 상위 N개 중 미사용만 고른다.
QUERIES = [
    "6시 내고향 전국장수자랑 어르신",
    "전국장수자랑 슬리피 장수 어르신 #6시내고향",
    "전국 노래자랑 Korea Sings 씨의 할머니",
    "전국 노래자랑 Korea Sings 할아버지 씨의",
    "전국노래자랑 할머니 참가자 KBS",
    "광주보라 청취자 전화 노래대결 놀라운 3시",
    "싱글벙글쇼 한줄노래교실 전화연결 박미현",
    "경로당 어르신 자기소개",
    "노인복지관 어르신 자기소개 영상자서전",
    "장수의 비밀 EBS 할머니 알고e즘",
    "장수의 비밀 EBS 할아버지",
    "특종세상 할머니 장수 Full영상",
    "아침마당 사람 찾기 KBS 헤어진",
    "6시 내고향 할머니 인터뷰 연세",
    "라디오 청취자 전화연결 어르신 사연 생방송",
    "시니어 합창단 어르신 자기소개",
    "어르신 구술 생애사 인터뷰 영상",
]
STRONG = re.compile(r"Q:age|Q:name|Q:date|A:non|DA-1|DA-2|DA-3|NM-|FIX|UN-1")
NARR = re.compile(r"(습니다|입니다|됩니다|합니다|이다|였다|했다)\.?$")
MIN_SEC, MAX_SEC = 60, 3700  # 1분~62분
# 제목에 이 중 하나는 있어야 선택 (검색 결과의 엉뚱한 영상 걸러내기)
TITLE_OK = re.compile(r"인간극장|동네 ?한 ?바퀴|여성시대|라디오시대|낭만시대|꿈의 무대|인터뷰|최고령|인기상|장수마을|장수자랑|어르신|할머니|할아버지|노래자랑|Korea Sings|노래대결|자기소개|장수의 비밀|특종세상|사람 ?찾|노래교실|청취자|전화연결|경로당|복지관|구술|생애|세 |년생|살 ")


def log(msg):
    line = f"[{datetime.now():%m-%d %H:%M}] {msg}"
    print(line, flush=True)
    LOG.open("a", encoding="utf-8").write(line + "\n")


def used_ids():
    ids = set()
    for f in [BASE / "urls.txt", *BASE.glob("urls_*.txt")]:
        if f.exists():
            ids |= set(re.findall(r"v=([\w-]{11})", f.read_text(encoding="utf-8")))
    return ids


def search(query, n=40):
    out = subprocess.run([PY, "-m", "yt_dlp", f"ytsearch{n}:{query}", "--flat-playlist",
                          "--print", "%(id)s|%(duration)s|%(title)s"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    items = []
    for line in out.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        vid, dur, title = parts
        try:
            dur = float(dur)
        except ValueError:
            continue
        items.append((vid, dur, title))
    return items


def pick_batch(size, qi):
    """검색어를 순환하며 미사용 영상을 size개 모은다. (검색어 인덱스, 목록) 반환"""
    used = used_ids()
    chosen, seen = [], set()
    tries = 0
    while len(chosen) < size and tries < len(QUERIES):
        q = QUERIES[qi % len(QUERIES)]
        qi += 1
        tries += 1
        for vid, dur, title in search(q):
            if vid in used or vid in seen or not (MIN_SEC <= dur <= MAX_SEC) or not TITLE_OK.search(title):
                continue
            seen.add(vid)
            chosen.append((vid, dur, title, q))
            if len(chosen) >= size:
                break
        log(f"검색 '{q}' → 누적 {len(chosen)}개")
    return qi, chosen


def strong_count(csv_path):
    n = 0
    for r in csv.DictReader(csv_path.open(encoding="utf-8-sig")):
        if r.get("usable") == "y" and STRONG.search(r.get("pattern_hint") or "") and not NARR.search(r.get("raw_text", "").strip()):
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=150, help="누적 강한 후보 수 목표")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--max-batches", type=int, default=6)
    ap.add_argument("--start-index", type=int, default=None, help="work/labeling_autoN.csv 의 N 시작값")
    ap.add_argument("--queries", default=None, help="검색어 목록 txt(한 줄 하나). 주면 QUERIES 대체 + 검색 인덱스 0부터")
    ap.add_argument("--reset-strong", action="store_true", help="누적 강한 후보 수를 0부터 다시 셈")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"qi": 0, "next": 1, "total_strong": 0, "batches": []}
    if args.queries:
        QUERIES[:] = [l.strip() for l in Path(args.queries).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        state["qi"] = 0
    if args.reset_strong:
        state["total_strong"] = 0
    if args.start_index:
        state["next"] = args.start_index
    log(f"시작: target={args.target} 누적 강한 후보={state['total_strong']}")

    for _ in range(args.max_batches):
        if state["total_strong"] >= args.target:
            log("목표 도달. 종료")
            break
        qi, batch = pick_batch(args.batch_size, state["qi"])
        state["qi"] = qi
        if not batch:
            log("미사용 영상을 더 못 찾음. 종료")
            break
        n = state["next"]
        urls = BASE / f"urls_auto{n}.txt"
        with urls.open("w", encoding="utf-8") as f:
            f.write(f"# auto {n} ({datetime.now():%Y-%m-%d %H:%M})\n")
            for vid, dur, title, q in batch:
                f.write(f"https://www.youtube.com/watch?v={vid}   [노인] {title[:50]} {int(dur)//60}:{int(dur)%60:02d} ({q[:12]})\n")
        (BASE / "urls.txt").open("a", encoding="utf-8").write(urls.read_text(encoding="utf-8"))
        out_csv = WORK / f"labeling_auto{n}.csv"
        log(f"배치 {n}: {len(batch)}개 영상 전사 시작 (총 {sum(d for _, d, _, _ in batch)/3600:.1f}시간)")
        t0 = time.time()
        subprocess.run([PY, "collect_utterances.py", str(urls), "--device", "cuda", "--out", str(out_csv)],
                       stdout=(WORK / f"auto{n}_run.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT, cwd=BASE)
        subprocess.run([PY, "prefill_labels.py", "--csv", str(out_csv)],
                       stdout=(WORK / f"auto{n}_prefill.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT, cwd=BASE)
        s = strong_count(out_csv) if out_csv.exists() else 0
        state["total_strong"] += s
        state["batches"].append({"n": n, "videos": len(batch), "strong": s, "minutes": round((time.time() - t0) / 60)})
        state["next"] = n + 1
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"배치 {n} 완료: 강한 후보 {s} (누적 {state['total_strong']}/{args.target}), {round((time.time()-t0)/60)}분")
    log("루프 종료")


if __name__ == "__main__":
    main()
