# -*- coding: utf-8 -*-
"""작성한 문장 묶음을 자동 검사. 입력 = {"req_id":..., "utterance":...} jsonl (여러 개 가능)
  python v32_check.py out/v32/batches/b01_out*.jsonl [--expect out/v32/batches/b01.txt]
통과/탈락 수와 탈락 사유(req_id별)를 찍는다. 내용은 탈락한 줄만 찍는다."""
import argparse, glob, json, re, sys
from collections import Counter
from make_v32 import OUT, check_transform, read_jsonl
from template_tools import template, value_signature, load_sft, names_of
_K = []
def kept_tpl():
    if not _K: _K.append(Counter(template(x["utt"], names_of(x)) for x in load_sft(OUT / "kept.jsonl")))
    return _K[0]

ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="+"); ap.add_argument("--expect"); ap.add_argument("--quiet", action="store_true")
a = ap.parse_args()
reqs = {r["req_id"]: r for r in read_jsonl(OUT / "requests.jsonl")}
rows, bad_lines = {}, 0
for pat in a.files:
    for f in glob.glob(pat):
        for l in open(f, encoding="utf-8"):
            if not l.strip(): continue
            try:
                d = json.loads(l); rows[d["req_id"]] = str(d["utterance"]).strip()
            except Exception:
                bad_lines += 1
fails, tpl = [], Counter()
for rid, utt in rows.items():
    r = reqs.get(rid)
    if r is None: fails.append((rid, "없는 req_id", utt)); continue
    if r["kind"] == "transform":
        why = check_transform(r, utt)
        if why is None and re.search(r"[A-Za-z]", utt): why = "영문자"
    else:
        names = r["names"]
        why = None if utt and utt != r["src_utt"] else "원문과 같음"
        if not why and value_signature(utt, names) != value_signature(r["src_utt"], names): why = "값 또는 값 순서 바뀜"
        if not why and template(utt, names) == template(r["src_utt"], names): why = "틀이 원문과 같음(구조를 더 바꿀 것)"
        if not why and kept_tpl()[template(utt, names)] >= 10: why = "이미 많이 있는 틀(구조를 더 바꿀 것)"
        if not why and re.search(r"[A-Za-z]", utt): why = "영문자"
    if why: fails.append((rid, why, utt))
    else: tpl[template(utt, [r.get("name", "")] if r["kind"] == "transform" else r.get("names", []))] += 1
missing = []
if a.expect:
    want = re.findall(r"^### (\S+)", open(a.expect, encoding="utf-8").read(), re.M)
    missing = [w for w in want if w not in rows]
print(f"문장 {len(rows)} · 통과 {len(rows) - len(fails)} · 탈락 {len(fails)} · 안 쓴 것 {len(missing)} · 깨진 줄 {bad_lines}")
print("탈락 사유:", dict(Counter(w for _, w, _ in fails)))
rep = [(t, n) for t, n in tpl.most_common(3) if n > 3]
if rep: print("같은 틀 반복:", [n for _, n in rep], "→ 문장 구조를 더 다르게")
if not a.quiet:
    for rid, why, utt in fails: print(f"  {rid}\t{why}\t{utt}")
    if missing: print("  안 쓴 것:", " ".join(missing[:40]))
