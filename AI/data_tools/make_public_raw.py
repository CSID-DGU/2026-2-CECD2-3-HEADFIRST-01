# -*- coding: utf-8 -*-
"""노인 실발화 공개용 파일: 발화 원문 대신 URL + 타임스탬프 + 라벨만 담는다.

  python make_public_raw.py
입력: out/raw_release_노인_20261021/raw_노인_{train,val,test}.json, raw_노인_eval_turns.jsonl
출력: github_upload/AI/data/raw_elderly_public/raw_elderly_labels.csv, README.md
"""
import csv, json, collections, pathlib

SRC = pathlib.Path("out/raw_release_노인_20261021")
OUT = pathlib.Path("github_upload/AI/data/raw_elderly_public"); OUT.mkdir(parents=True, exist_ok=True)


def main():
    gold = {}
    for l in open(SRC / "raw_노인_eval_turns.jsonl", encoding="utf-8"):
        r = json.loads(l)
        g = r["gold"] if isinstance(r["gold"], dict) else json.loads(r["gold"])
        gold[r["dialogue_id"]] = g["actions"]
    rows = []
    for sp in ("train", "val", "test"):
        for d in json.load(open(SRC / f"raw_노인_{sp}.json", encoding="utf-8")):
            s = d["source"]
            for a in gold[d["dialogue_id"]]:
                rows.append({"dialogue_id": d["dialogue_id"], "split": sp, "url": s["url"], "start_sec": s["start"],
                             "call_date": d.get("call_date", ""), "slot": a["slot"], "act": a["act"],
                             "canonical_value": " ".join(a.get("canonical_values") or []), "pattern": d.get("pattern", "")})
    with open(OUT / "raw_elderly_labels.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    n = len({r["dialogue_id"] for r in rows})
    c = collections.Counter((r["split"], r["slot"], r["act"]) for r in rows)
    L = [f"# 노인 실발화 라벨 (공개용, {n}턴)", "",
         "유튜브에 공개된 방송 · 라디오에서 노인 발화를 전사하고 사람이 듣고 라벨을 확정한 데이터다.",
         "발화 원문은 재배포하지 않는다. 영상 URL과 시작 시각(초), 라벨만 담았다. URL의 해당 시점을 들으면 발화를 확인할 수 있다.", "",
         "## 컬럼", "",
         "| 컬럼 | 뜻 |", "|---|---|",
         "| dialogue_id | 턴 id |", "| split | train / val / test (영상 단위 분할) |",
         "| url, start_sec | 영상 주소와 발화 시작 시각 |", "| call_date | 기준일(방송일) |",
         "| slot | 질문받은 슬롯 (name / birth_date / occurred_date) |",
         "| act | INFORM(값을 말함) / UNCERTAIN(재질문 대상) |",
         "| canonical_value | INFORM일 때의 정답 값 |", "| pattern | 발화 패턴 태그 |", "",
         "## 건수 (action 단위)", "", "| split | slot | act | 건수 |", "|---|---|---|---:|"]
    for k in sorted(c):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {c[k]} |")
    (OUT / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"턴 {n}, 행 {len(rows)}, 이름 값이 있는 행 {sum(1 for r in rows if r['slot']=='name' and r['canonical_value'])}")


if __name__ == "__main__":
    main()
