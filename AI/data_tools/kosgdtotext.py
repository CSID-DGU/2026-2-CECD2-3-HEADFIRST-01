"""
KoSGD JSON → 텍스트 / CSV 변환

사용법
  python kosgd_to_text.py <dialogues_*.json 있는 폴더> [--user-only]

결과
  kosgd_utterances.txt  발화만 한 줄씩
  kosgd_utterances.csv  dialogue_id, turn_idx, speaker, utterance, slot_values (엑셀용)
"""

import argparse
import csv
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--user-only", action="store_true", help="USER 발화만 뽑기")
    ap.add_argument("--out", default="kosgd_utterances")
    args = ap.parse_args()

    files = sorted(Path(args.folder).glob("dialogues_*.json"))
    if not files:
        raise SystemExit("dialogues_*.json 파일을 못 찾았어. 폴더 경로 확인!")

    rows = []
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        for dlg in data:
            for i, turn in enumerate(dlg.get("turns", [])):
                spk = turn.get("speaker", "")
                if args.user_only and spk.upper() != "USER":
                    continue
                utt = (turn.get("utterance") or "").strip()
                # 이 턴에서 실제로 말한 슬롯 값 (start/exclusive_end 구간)
                spans = []
                for fr in turn.get("frames", []):
                    for s in fr.get("slots", []):
                        st, en = s.get("start"), s.get("exclusive_end")
                        if isinstance(st, int) and isinstance(en, int):
                            spans.append(f"{s.get('slot')}={utt[st:en]}")
                rows.append({
                    "dialogue_id": dlg.get("dialogue_id", ""),
                    "turn_idx": i,
                    "speaker": spk,
                    "utterance": utt,
                    "slot_values": "; ".join(spans),
                })

    txt = Path(f"{args.out}.txt")
    txt.write_text("\n".join(r["utterance"] for r in rows), encoding="utf-8")
    with Path(f"{args.out}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"파일 {len(files)}개 → 발화 {len(rows)}개")
    print(f"저장: {txt}, {args.out}.csv")


if __name__ == "__main__":
    main()