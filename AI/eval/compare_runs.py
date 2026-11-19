"""평가 결과 파일 여러 개를 '모두에게 있는 같은 문제'끼리만 모아 점수를 나란히 비교한다.

용도: 결과 파일끼리 점수를 맞대어 본다. 2026-10-20에 '우리 서버 4bit 측정 = 멘토 서버 베이스라인(JGA 62.1)'인지 확인하고,
      이후 학습 전 vs 학습 후 비교에 썼다.

- 예) 학습 전 vs 학습 후:  python compare_runs.py --kit 채점키트폴더 base_t0.jsonl lora_t0.jsonl
- 예) 우리 측정 vs 멘토 서버:  python compare_runs.py --kit 채점키트폴더 results_mentor_ref_mini155.jsonl base_t07.jsonl
- 원본 check_responses.py의 score로 다시 채점한다. 예전 결과 파일엔 slot_F1용 항목이 없어서다(맞음/틀림 판정은 저장값과 같다).
- JGA는 state가 None인 문제(정답에 INFORM이 없는 문제)를 분모에서 뺀다 (기존 56.8 · 62.1과 같은 방식).
"""
import argparse
import json
import sys
from pathlib import Path


def load(path, cr):
    with open(path, encoding="utf-8") as f:
        rows = {(r["dialogue_id"], r["turn"]): r for r in map(json.loads, f)}
    for r in rows.values():
        r["score"] = cr.score(r)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="check_responses.py가 있는 폴더")
    p.add_argument("--by-pattern", action="store_true", help="패턴별 JGA도 출력")
    p.add_argument("runs", nargs="+", help="결과 jsonl 파일들")
    a = p.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(a.kit).resolve()))
    import check_responses as cr

    runs = [load(r, cr) for r in a.runs]
    common = sorted(set.intersection(*(set(r) for r in runs)))   # 모든 파일에 있는 문제만
    names = [Path(r).stem for r in a.runs]
    print(f"공통 문제 {len(common)}개 (파일별 전체: {', '.join(str(len(r)) for r in runs)})")

    print(f"\n{'run':<36}{'n':>5}{'JGA_n':>7}{'JGA':>8}{'parse':>8}{'intent':>8}{'action':>8}{'slot_F1':>9}")
    tables = []
    for name, run in zip(names, runs):
        t = cr.summarize([run[k] for k in common])["ALL"]
        jga_n = sum(run[k]["score"]["state"] is not None for k in common)
        print(f"{name:<36}{t['n']:>5}{jga_n:>7}{t['state']*100:>8.1f}{t['parse']*100:>8.1f}"
              f"{t['intent']*100:>8.1f}{t['action']*100:>8.1f}{t['slot_F1']*100:>9.1f}")
        tables.append(cr.summarize([run[k] for k in common], key=lambda r: r["noise"]))

    if a.by_pattern:   # 패턴별 JGA를 파일마다 한 칸씩
        print(f"\n{'pattern':<14}" + "".join(f"{n[:16]:>18}" for n in names))
        for pat in sorted(set().union(*tables)):
            cells = []
            for t in tables:
                v = t.get(pat, {}).get("state")
                cells.append("-" if v is None or v != v else f"{v*100:.0f}")   # v != v 는 nan(JGA 대상 없음)
            print(f"{pat:<14}" + "".join(f"{c:>18}" for c in cells))


if __name__ == "__main__":
    main()
