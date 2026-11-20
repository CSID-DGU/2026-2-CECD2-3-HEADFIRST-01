# -*- coding: utf-8 -*-
"""학습 데이터 분포 집계 (슬롯 × 라벨, 패턴 × 라벨, 문장 틀 쏠림).

  python dist_train.py <sft_train.jsonl> [--name v3.1] [--top 15]

집계 단위
  - action 단위: 타깃 발화의 모든 action을 셈(한 발화에 슬롯 3개면 3건). TEAM_PLAN 표와 같은 기준
  - 턴 단위: 타깃 발화 1건 = 1. 칸은 (첫 action의 슬롯, 발화에 UNCERTAIN이 하나라도 있으면 UNCERTAIN)
  - 틀: template_tools.template (값·이름·숫자를 가린 형태소 열)
"""
import argparse
from collections import Counter, defaultdict

from template_tools import load_sft, names_of, template

SLOTS = ["name", "phone", "birth_date", "occurred_date", "complaint_type", "reply_channel", "consent"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--name", default="")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    items = load_sft(args.path)
    n = len(items)
    print(f"## {args.name or args.path} — {n}턴\n")

    # 1) action 단위 슬롯 × 라벨
    c = Counter((a["slot"], a["act"]) for x in items for a in x["actions"])
    tot = sum(c.values())
    print("### 슬롯 × 라벨 (action 단위)\n")
    print("| 슬롯 | INFORM | UNCERTAIN | 슬롯 비중 | 슬롯 내 UNCERTAIN |\n|---|---:|---:|---:|---:|")
    for s in SLOTS:
        i, u = c[(s, "INFORM")], c[(s, "UNCERTAIN")]
        if i + u:
            print(f"| {s} | {i:,} | {u:,} | {(i + u) / tot:.1%} | {u / (i + u):.1%} |")
    ti = sum(v for (s, a), v in c.items() if a == "INFORM")
    tu = tot - ti
    print(f"| **합계** | {ti:,} | {tu:,} | | **{tu / tot:.1%}** |")
    other = {k: v for k, v in c.items() if k[0] not in SLOTS or k[1] not in ("INFORM", "UNCERTAIN")}
    if other:
        print("\n기타 action:", other)
    cf = Counter(tuple(a["canonical_values"]) for x in items for a in x["actions"] if a["slot"] == "consent")
    print(f"\n- consent 값: {dict(cf)}")
    unc_turn = sum(any(a["act"] == "UNCERTAIN" for a in x["actions"]) for x in items)
    print(f"- 턴 단위 UNCERTAIN 포함 비율: {unc_turn}/{n} = {unc_turn / n:.1%}")
    print(f"- action 2개 이상인 턴: {sum(len(x['actions']) > 1 for x in items)}/{n}")

    # 2) 패턴 × 라벨
    pc = defaultdict(Counter)
    for x in items:
        pc[x["pattern"]]["UNCERTAIN" if any(a["act"] == "UNCERTAIN" for a in x["actions"]) else "INFORM"] += 1
    both = [p for p, v in pc.items() if v["INFORM"] and v["UNCERTAIN"]]
    only_u = [p for p, v in pc.items() if not v["INFORM"]]
    only_i = [p for p, v in pc.items() if not v["UNCERTAIN"]]
    print(f"\n### 패턴 × 라벨 (턴 단위, 패턴 {len(pc)}개)\n")
    print(f"- INFORM만 나오는 패턴 {len(only_i)}개: {', '.join(sorted(only_i))}")
    print(f"- UNCERTAIN만 나오는 패턴 {len(only_u)}개: {', '.join(f'{p}({pc[p]['UNCERTAIN']})' for p in sorted(only_u))}")
    print(f"- 둘 다 나오는 패턴 {len(both)}개: {', '.join(f'{p}(I {pc[p]['INFORM']}/U {pc[p]['UNCERTAIN']})' for p in sorted(both))}")
    print(f"- 패턴만 보고 라벨을 찍었을 때 맞는 턴: {sum(max(v.values()) for v in pc.values())}/{n} "
          f"= {sum(max(v.values()) for v in pc.values()) / n:.1%}")

    # 3) 틀 쏠림
    tpl = Counter()
    tpl_cell = defaultdict(Counter)
    ex = {}
    for x in items:
        t = template(x["utt"], names_of(x))
        tpl[t] += 1
        ex.setdefault(t, x["utt"])
        a = x["actions"][0] if x["actions"] else {"slot": "-", "act": "-"}
        tpl_cell[t][(a["slot"], a["act"])] += 1
    top50 = sum(v for _, v in tpl.most_common(50))
    print(f"\n### 문장 틀\n")
    print(f"- 틀 수: {len(tpl):,}개 / {n:,}턴 (턴당 {len(tpl) / n:.2f})")
    print(f"- 상위 50개 틀 비중: {top50}/{n} = {top50 / n:.1%}")
    print(f"- 1번만 나오는 틀: {sum(v == 1 for v in tpl.values()):,}개")
    for k in (5, 10, 20, 30):
        over = sum(v - k for v in tpl.values() if v > k)
        print(f"- 틀당 {k}개로 제한하면 빠지는 턴: {over:,} ({over / n:.1%}), 해당 틀 {sum(v > k for v in tpl.values())}개")
    print(f"\n| 순위 | 건수 | 칸(슬롯·라벨) | 틀 | 예시 |\n|---:|---:|---|---|---|")
    for r, (t, v) in enumerate(tpl.most_common(args.top), 1):
        cells = ", ".join(f"{s} {a[0]} {k}" for (s, a), k in tpl_cell[t].most_common(2))
        print(f"| {r} | {v} | {cells} | `{t}` | {ex[t]} |")


if __name__ == "__main__":
    main()
