# -*- coding: utf-8 -*-
"""평가셋 문장 틀이 학습 데이터에 있는지 검사.

  python check_template_overlap.py --train <sft_train.jsonl> --eval hardset/hard_dev.json --show
  python check_template_overlap.py --train <sft_train.jsonl> --eval hardset/test_DO_NOT_OPEN/hard_test.json
      (--show를 빼면 발화 내용 없이 개수와 id만 찍음 → test용)

지표
  완전 일치율 = (틀이 학습 틀 집합에 그대로 있는 문제 수) / (전체 문제 수)
  유사 일치율 = (학습 틀과의 글자 3-gram Jaccard 최댓값 ≥ 임계값인 문제 수) / (전체 문제 수)
  발화 일치   = 발화 문자열이 학습 발화와 완전히 같은 문제 수
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from template_tools import char_ngrams, jaccard, load_any, names_of, template


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--show", action="store_true", help="겹친 문제의 발화와 가장 가까운 학습 발화를 출력(dev 전용)")
    ap.add_argument("--csv", help="문제별 결과 저장 경로(--show일 때만 발화 포함)")
    args = ap.parse_args()

    train = [x for p in args.train for x in load_any(p)]
    ev = load_any(args.eval)
    tr_tpl = defaultdict(list)
    for x in train:
        tr_tpl[template(x["utt"], names_of(x))].append(x["utt"])
    tr_utts = {x["utt"].strip() for x in train}
    tpl_list = list(tr_tpl)
    grams = [char_ngrams(t) for t in tpl_list]
    # 3-gram 역색인으로 후보만 비교
    inv = defaultdict(set)
    for i, g in enumerate(grams):
        for x in g:
            inv[x].add(i)

    rows = []
    for x in ev:
        t = template(x["utt"], names_of(x))
        g = char_ngrams(t)
        exact = t in tr_tpl
        cand = Counter(i for gg in g for i in inv.get(gg, ()))
        best, best_i = 0.0, None
        for i, _ in cand.most_common(300):
            s = jaccard(g, grams[i])
            if s > best:
                best, best_i = s, i
        rows.append({"id": x["id"], "type": x.get("type") or x.get("pattern", ""), "exact": exact,
                     "sim": 1.0 if exact else best, "same_utt": x["utt"].strip() in tr_utts,
                     "utt": x["utt"], "template": t,
                     "nearest": tr_tpl[tpl_list[best_i]][0] if best_i is not None else ""})

    n = len(rows)
    ex = sum(r["exact"] for r in rows)
    near = sum(r["sim"] >= args.threshold for r in rows)
    print(f"학습 {len(train)}턴(틀 {len(tr_tpl)}개) vs 평가 {n}문제  [{Path(args.eval).name}]")
    print(f"  발화 완전 일치: {sum(r['same_utt'] for r in rows)}/{n}")
    print(f"  틀 완전 일치율: {ex}/{n} = {ex / n:.1%}")
    print(f"  틀 유사 일치율(Jaccard ≥ {args.threshold}): {near}/{n} = {near / n:.1%}")
    by = defaultdict(list)
    for r in rows:
        by[r["type"]].append(r)
    if len(by) <= 60:
        print("  유형별 (완전 / 유사 / n):")
        for k in sorted(by, key=lambda s: (not s[:1].isdigit(), int(s.split()[0]) if s[:1].isdigit() else 0, s)):
            v = by[k]
            print(f"    {k}: {sum(r['exact'] for r in v)} / {sum(r['sim'] >= args.threshold for r in v)} / {len(v)}")
    hit = [r for r in rows if r["sim"] >= args.threshold]
    if args.show:
        for r in sorted(hit, key=lambda r: -r["sim"]):
            print(f"  [{r['sim']:.2f}] {r['id']}  {r['utt']}\n          ≈ 학습: {r['nearest']}")
    else:
        print("  겹친 문제 id:", ", ".join(f"{r['id']}({r['sim']:.2f})" for r in sorted(hit, key=lambda r: -r["sim"])) or "없음")
    if args.csv:
        cols = ["id", "type", "exact", "sim", "same_utt"] + (["utt", "template", "nearest"] if args.show else [])
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({**r, "sim": f"{r['sim']:.3f}"})
        print("  저장:", args.csv)


if __name__ == "__main__":
    main()
