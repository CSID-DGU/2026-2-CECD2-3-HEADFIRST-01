"""학교 서버에서 Qwen3.8-27B(4bit)로 평가셋을 풀고, 멘토 베이스라인과 같은 기준으로 채점한다.

용도: 멘토 채점기(check_responses.py) 기준 평가셋 점수를 학교 서버 GPU에서 잰다.
      2026-10-20 학습 전 베이스라인(mini 175), v3 학습 후 비교, 중간발표(10/22) 평가셋 620 JGA 숫자를 이 스크립트로 냈다.

- 문제 만들기 · 프롬프트 · JSON 읽기 · 채점 · 집계는 check_responses.py(멘토 서버 베이스라인을 낸 원본)를 그대로 불러다 쓴다.
  여기서 새로 짠 부분은 "모델에게 묻기" 하나뿐이다 (원본은 vLLM 서버에 HTTP로 묻고, 여기서는 GPU의 모델에 직접 묻는다).
- 학습 전:  --adapter 없이 실행 / 학습 후:  --adapter 어댑터폴더 (나머지 조건은 같게)
- GPU 1장:  python eval_local.py --kit 채점키트폴더 --data 평가셋.json --out 결과.jsonl
- GPU 3장:  accelerate launch --num_processes 3 eval_local.py ... (문제를 3등분해 나눠 푼다)
- temperature 0이면 항상 같은 답(주 측정), 0.7이면 원본 vLLM 설정과 같은 샘플링(확인용).
- 경로 설정은 AI/.env에서 읽는다 (AI/.env.example 참고).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent           # AI/eval
AI_DIR = EVAL_DIR.parent                             # AI

# AI/.env에서 경로를 읽는다. torch·transformers를 불러오기 전에 해야 HF_HOME과 캐시 위치가 적용된다.
ENV_FILE = AI_DIR / ".env"
if not ENV_FILE.exists():
    sys.exit("AI/.env가 없다. AI/.env.example을 복사해 AI/.env를 만들고 경로를 채운다.")
load_dotenv(ENV_FILE, override=True)
_missing = [k for k in ("HF_HOME", "LOCAL_ROOT") if not os.environ.get(k)]
if _missing:
    sys.exit(f"AI/.env에 값이 비어 있다: {', '.join(_missing)}")
LOCAL_ROOT = Path(os.environ["LOCAL_ROOT"])

# NAS는 작은 파일 쓰기가 매우 느리므로, 커널 컴파일 캐시는 로컬 디스크에 둔다.
os.environ.setdefault("TRITON_CACHE_DIR", str(LOCAL_ROOT / "triton-cache"))
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(LOCAL_ROOT / "inductor-cache"))

import torch
import torch.distributed as dist
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="check_responses.py가 있는 폴더")
    p.add_argument("--data", required=True, nargs="+", help="평가셋 JSON (여러 개면 이어 붙여 푼다)")
    p.add_argument("--out", required=True, help="문제별 결과 jsonl (check_responses.py 결과와 같은 형식)")
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--adapter", default=None, help="LoRA 어댑터 폴더. 없으면 학습 전 모델")
    p.add_argument("--temperature", type=float, default=0.0, help="0이면 항상 1등 후보만 고른다")
    p.add_argument("--max_new_tokens", type=int, default=1024)   # 원본 max_tokens와 같게
    p.add_argument("--limit", type=int, default=0, help="앞에서 N문제만 (시험 실행용)")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def load_scorer(kit):
    """원본 채점 스크립트를 모듈로 불러온다. 파일은 고치지 않고, __pycache__도 만들지 않는다."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(kit).resolve()))
    import check_responses
    return check_responses


def build_items(cr, data_paths, limit):
    """원본 main()과 같은 순서로 대화를 읽고 문제(채점할 USER 턴)를 만든다."""
    items = []
    for path in data_paths:
        # 원본 load_dialogues가 읽는 옵션만 채운 간이 args
        opts = argparse.Namespace(hf=None, data=path, per_pattern=0, limit=0)
        dialogues = cr.load_dialogues(opts)
        cr.PROMPT_VER = "v2" if any(d.get("call_date") for d in dialogues) else "v1"   # 원본 --prompt auto
        schema = cr.build_schema(dialogues)
        for it in cr.make_items(dialogues, "noisy"):
            it["messages"] = cr.build_messages(it, schema)   # 파일마다 프롬프트 버전이 다를 수 있어 미리 만든다
            items.append(it)
    return items[:limit] if limit else items


def ask(model, tok, messages, a, device):
    """원본 call()에서 HTTP 요청 부분만 GPU 생성으로 바꾼 것. 반환값은 모델이 쓴 글(raw)."""
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)   # 원본과 같은 비추론 모드
    ids = tok(prompt, return_tensors="pt").to(device)
    if a.temperature > 0:   # 원본 vLLM 호출과 같은 샘플링 설정
        gen = dict(do_sample=True, temperature=a.temperature, top_p=0.8, top_k=20, min_p=0.0)
    else:                   # 항상 확률 1등 토큰만 고른다
        gen = dict(do_sample=False)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=a.max_new_tokens, **gen)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def main():
    a = parse_args()
    # accelerate launch로 띄우면 RANK·WORLD_SIZE가 정해진다. 그냥 python으로 띄우면 GPU 1장(0번).
    rank, world = int(os.environ.get("RANK", 0)), int(os.environ.get("WORLD_SIZE", 1))
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    is_main = rank == 0
    if world > 1:
        dist.init_process_group("gloo")   # 결과(파이썬 객체)만 모으면 되므로 CPU 통신으로 충분
    set_seed(a.seed + rank)               # 0.7일 때 프로세스마다 다른 난수, 그래도 재실행하면 같게

    cr = load_scorer(a.kit)
    items = build_items(cr, a.data, a.limit)
    mine = items[rank::world]             # 문제를 GPU 수만큼 번갈아 나눠 맡는다
    if is_main:
        print(f"[data] {len(items)}문제, GPU {world}장 (프롬프트 {cr.PROMPT_VER}, temperature {a.temperature}, "
              f"adapter {a.adapter or '없음'})", flush=True)

    # 학습과 같은 4bit(NF4) 설정으로 모델을 이 프로세스의 GPU 한 장에 올린다.
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": local_rank}, dtype=torch.bfloat16)
    if a.adapter:   # 학습 후 측정: 4bit 원본 위에 LoRA 어댑터를 얹는다
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()

    rows, t0 = [], time.time()
    for i, it in enumerate(mine, 1):
        messages = it.pop("messages")
        try:
            raw = ask(model, tok, messages, a, local_rank)
            try:
                pred = cr.parse_json(raw)
            except Exception:
                pred = None
            rows.append({**it, "raw": raw, "pred": pred})
        except Exception as e:  # noqa  원본처럼 실패도 한 행으로 남긴다
            rows.append({**it, "raw": None, "pred": None, "error": str(e)})
        if is_main:   # 0번 GPU 진행 상황으로 전체 남은 시간을 가늠한다
            print(f"[gen] {i}/{len(mine)}  {time.time()-t0:.0f}s 경과", flush=True)

    if world > 1:   # 모든 GPU의 결과를 0번으로 모은다
        gathered = [None] * world
        dist.all_gather_object(gathered, rows)
        rows = [r for part in gathered for r in part]
    if is_main:
        order = {(it["dialogue_id"], it["turn"]): k for k, it in enumerate(items)}
        rows.sort(key=lambda r: order[(r["dialogue_id"], r["turn"])])   # 원래 문제 순서로
        for r in rows:
            r["score"] = cr.score(r)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        errs = [r for r in rows if r.get("error")]
        if errs:
            print(f"생성 실패 {len(errs)}건, 예: {errs[0]['error']}")
        cr.print_table("전체", cr.summarize(rows))
        cr.print_table("대분류별", cr.summarize(rows, key=lambda r: r["category"]))
        cr.print_table("패턴별", cr.summarize(rows, key=lambda r: r["noise"]))
        print(f"\n[done] {time.time()-t0:.0f}s, 문제별 결과: {a.out}", flush=True)
    if world > 1:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
