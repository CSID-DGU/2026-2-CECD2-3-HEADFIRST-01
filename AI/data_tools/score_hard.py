# -*- coding: utf-8 -*-
"""하드셋 채점: 유형·난이도·슬롯별 표, 짝 문장 정답률, 학습 전 vs 학습 후 4분류.

입력 = hard_*_eval_turns.jsonl 각 줄에 모델 출력 "pred"를 붙인 jsonl (팀 results_*.jsonl과 같은 방식).
  pred는 {"active_intent":..., "actions":[...]} dict 또는 그 JSON 문자열.

  python score_hard.py score   --pred pred_dev_Aprime.jsonl
  python score_hard.py compare --base pred_dev_untrained.jsonl --model pred_dev_Aprime.jsonl [--show] [--csv out.csv]

--show(발화 내용 출력)는 dev 전용. split이 test인 줄이 하나라도 있으면 거부한다.

판정
  문제 정답   = 예측 action 집합이 정답 action 집합과 완전히 같음 ((act, slot, canonical 값) 단위)
  라벨 정답   = 질문받은 슬롯의 act(INFORM/UNCERTAIN)가 정답과 같음
  값 정답     = 정답이 INFORM인 문제 중 질문받은 슬롯의 canonical 값까지 같음
  짝 정답     = 한 군데만 다른 짝 문장 2개를 둘 다 맞힘(문제 정답 기준)
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_raw import _d, score_rows


def load(path):
    return [json.loads(l) for l in Path(path).open(encoding="utf-8") if l.strip()]


def actions_of(x):
    try:
        return _d(x)["actions"]
    except Exception:
        return []


def aset(actions):
    return {(a.get("act"), a.get("slot"), tuple(a.get("canonical_values") or [])) for a in actions}


def judge(r):
    g, p = actions_of(r["gold"]), actions_of(r.get("pred"))
    g0 = g[0]
    p0 = next((a for a in p if a.get("slot") == g0["slot"]), None)
    return {"all": aset(g) == aset(p),
            "act": bool(p0) and p0.get("act") == g0["act"],
            "value": (bool(p0) and (p0.get("canonical_values") or []) == g0["canonical_values"]) if g0["act"] == "INFORM" else None,
            "gold_act": g0["act"], "slot": g0["slot"],
            "pred_str": " ; ".join(f"{a.get('slot')}|{a.get('act')}|{','.join(a.get('canonical_values') or [])}" for a in p) or "(출력 없음/파싱 실패)",
            "gold_str": " ; ".join(f"{a['slot']}|{a['act']}|{','.join(a['canonical_values'])}" for a in g)}


def table(rows, key, title):
    by = defaultdict(list)
    for r in rows:
        by[key(r)].append(r["_j"])
    print(f"\n### {title}\n")
    print("| 구분 | n | 문제 정답 | 라벨 정답 | INFORM 재현(n) | UNCERTAIN 재현(n) | 값 정답(INFORM 중) |\n|---|---:|---:|---:|---:|---:|---:|")

    def frac(xs):
        return f"{sum(xs)}/{len(xs)}" if xs else "-"
    for k in sorted(by, key=lambda s: (int(str(s).split()[0]) if str(s).split()[0].isdigit() else 99, str(s))):
        v = by[k]
        flag = " *" if len(v) < 20 else ""
        print(f"| {k}{flag} | {len(v)} | {frac([j['all'] for j in v])} | {frac([j['act'] for j in v])} | "
              f"{frac([j['act'] for j in v if j['gold_act'] == 'INFORM'])} | "
              f"{frac([j['act'] for j in v if j['gold_act'] == 'UNCERTAIN'])} | "
              f"{frac([j['value'] for j in v if j['value'] is not None])} |")
    print("\n\\* n<20: 결론 보류")


def cmd_score(args):
    rows = load(args.pred)
    for r in rows:
        r["_j"] = judge(r)
    s = score_rows(rows)
    n = len(rows)
    ok = sum(r["_j"]["all"] for r in rows)
    print(f"## {Path(args.pred).name} — {n}문제\n")
    print(f"- 문제 정답률: {ok}/{n} = {ok / n:.3f}")
    for c, (p, rc, f) in s["per_class"].items():
        print(f"- {c}: precision {p:.3f} / recall {rc:.3f} / F1 {f:.3f}")
    print(f"- macro-F1: {s['macro_F1']:.3f}")
    maj = Counter(r["_j"]["gold_act"] for r in rows).most_common(1)[0]
    print(f"- 한 라벨로만 찍었을 때({maj[0]}): {maj[1]}/{n} = {maj[1] / n:.3f}")
    table(rows, lambda r: r.get("type", "-"), "유형별")
    table(rows, lambda r: f"난이도 {r.get('difficulty')}", "난이도별")
    table(rows, lambda r: r["_j"]["slot"], "질문받은 슬롯별")
    pairs = defaultdict(list)
    for r in rows:
        p = (r.get("source") or {}).get("pair")
        if p:
            pairs[((r.get("source") or {}).get("author"), p)].append(r["_j"]["all"])
    full = [v for v in pairs.values() if len(v) >= 2]
    if full:
        print(f"\n- 짝 정답률: {sum(all(v) for v in full)}/{len(full)} (둘 다 맞힘) · 한쪽만 맞힘 {sum(any(v) and not all(v) for v in full)} · 둘 다 틀림 {sum(not any(v) for v in full)}")


CLASS4 = {(True, True): "원래 맞춤", (False, True): "학습으로 풀림", (False, False): "학습해도 안 풀림", (True, False): "학습 후 퇴보"}
ACTION4 = {"원래 맞춤": "줄일 대상", "학습으로 풀림": "현재 데이터 유지", "학습해도 안 풀림": "보강 대상", "학습 후 퇴보": "원인 확인"}


def cmd_compare(args):
    base = {r["dialogue_id"]: r for r in load(args.base)}
    model = {r["dialogue_id"]: r for r in load(args.model)}
    ids = [i for i in base if i in model]
    if len(ids) != len(base) or len(ids) != len(model):
        print(f"주의: 두 파일의 문제 id가 다름 (공통 {len(ids)}, base {len(base)}, model {len(model)})")
    is_test = any((base[i].get("source") or {}).get("split") == "test" for i in ids)
    if is_test and (args.show or args.csv):
        sys.exit("test가 섞인 파일은 --show/--csv로 내용을 볼 수 없음(누수 방지). 표만 보려면 옵션을 빼고 실행")
    rows = []
    for i in ids:
        jb, jm = judge(base[i]), judge(model[i])
        rows.append({"id": i, "type": base[i].get("type", "-"), "difficulty": base[i].get("difficulty"),
                     "slot": jb["slot"], "gold_act": jb["gold_act"], "class4": CLASS4[(jb["all"], jm["all"])],
                     "utterance": base[i]["utterance"], "gold": jb["gold_str"], "base_pred": jb["pred_str"],
                     "model_pred": jm["pred_str"], "원인(문제 오류/애매/모델 오류)": "", "메모": ""})
    types = sorted({r["type"] for r in rows}, key=lambda s: int(s.split()[0]) if s.split()[0].isdigit() else 99)
    cols = list(ACTION4)
    print(f"## 4분류: {Path(args.base).name} → {Path(args.model).name} ({len(rows)}문제)\n")
    print("| 유형 | n | " + " | ".join(f"{c}({ACTION4[c]})" for c in cols) + " |\n|---|---:|" + "---:|" * len(cols))
    for t in types:
        v = [r for r in rows if r["type"] == t]
        print(f"| {t} | {len(v)} | " + " | ".join(str(sum(r["class4"] == c for r in v)) for c in cols) + " |")
    print(f"| **합계** | {len(rows)} | " + " | ".join(str(sum(r["class4"] == c for r in rows)) for c in cols) + " |")
    print("\n| 슬롯·정답 라벨 | n | " + " | ".join(cols) + " |\n|---|---:|" + "---:|" * len(cols))
    for k in sorted({(r["slot"], r["gold_act"]) for r in rows}):
        v = [r for r in rows if (r["slot"], r["gold_act"]) == k]
        print(f"| {k[0]} {k[1]} | {len(v)} | " + " | ".join(str(sum(r["class4"] == c for r in v)) for c in cols) + " |")
    # 오답 종류(건수만. 문제 내용은 안 찍으므로 test에서도 볼 수 있음)
    kinds = ["정답 INFORM → UNCERTAIN으로 냄(재질문 과다)", "정답 UNCERTAIN → INFORM으로 냄(값을 확정·지어냄)",
             "라벨은 맞고 값이 틀림", "그 외(다른 슬롯 추가·누락, 출력 없음)"]

    def kind(i):
        j = judge(model[i])
        if not j["act"] and any(a.get("slot") == j["slot"] for a in actions_of(model[i].get("pred"))):
            return kinds[0] if j["gold_act"] == "INFORM" else kinds[1]
        if j["act"] and j["value"] is False:
            return kinds[2]
        return kinds[3]
    print(f"\n| {Path(args.model).name}의 오답 종류 | 학습해도 안 풀림 | 학습 후 퇴보 |\n|---|---:|---:|")
    for k in kinds:
        print(f"| {k} | " + " | ".join(str(sum(1 for r in rows if r["class4"] == c and kind(r["id"]) == k))
                                       for c in ("학습해도 안 풀림", "학습 후 퇴보")) + " |")
    if args.show:
        for c in ("학습해도 안 풀림", "학습 후 퇴보"):
            print(f"\n### {c}\n")
            for r in rows:
                if r["class4"] == c:
                    print(f"- {r['id']} [{r['type']}] {r['utterance']}\n    정답 {r['gold']}\n    학습 전 {r['base_pred']}\n    학습 후 {r['model_pred']}")
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n저장: {args.csv}  (원인 칸을 채우면 보강 대상 = '학습해도 안 풀림' + 원인 '모델 오류')")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("score"); p.add_argument("--pred", required=True); p.set_defaults(fn=cmd_score)
    p = sub.add_parser("compare"); p.add_argument("--base", required=True); p.add_argument("--model", required=True)
    p.add_argument("--show", action="store_true"); p.add_argument("--csv"); p.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
