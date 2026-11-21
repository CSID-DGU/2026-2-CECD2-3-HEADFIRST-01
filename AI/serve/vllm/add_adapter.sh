#!/bin/bash
# H200에서 받아 온 LoRA 어댑터를 vLLM이 읽는 형태로 바꿔 MODEL_ROOT/adapters/<이름>-vl 에 둔다.
#   bash add_adapter.sh <받아 온 어댑터 폴더> <이름>
#   예) bash add_adapter.sh ~/capstone_design_2/runs/v31-r16-e3/checkpoint-842 v31-ckpt842
# 하는 일: adapter_config.json + adapter_model.safetensors 복사, Qwen3.8 어댑터만 키 이름 변경(model.layers. → model.language_model.layers.)
#          키 이름을 안 바꾸면 vLLM이 오류 없이 어댑터를 무시한다 (학습 전 모델과 점수가 같아진다).
# 끝나면 serve_vllm.sh의 --lora-modules 에 "<짧은이름>=\$MODEL_ROOT/adapters/<이름>-vl" 을 추가하고 vllm_ctl.sh restart.
set -euo pipefail
SRC=${1:?어댑터 폴더}; NAME=${2:?이름}
MODEL_ROOT=${MODEL_ROOT:-$HOME/var_tmp_backup_20261107}
DST=$MODEL_ROOT/adapters/$NAME-vl
for f in adapter_config.json adapter_model.safetensors; do [ -f "$SRC/$f" ] || { echo "$SRC/$f 가 없다"; exit 1; }; done
[ -e "$DST" ] && { echo "$DST 가 이미 있다 (지우거나 다른 이름을 쓴다)"; exit 1; }
source /var/tmp/csuhyeon/venvs/vllm/bin/activate
python - "$SRC" "$DST" <<'PY'
import json, os, shutil, sys
from safetensors.torch import load_file, save_file
src, dst = sys.argv[1], sys.argv[2]
cfg = json.load(open(f"{src}/adapter_config.json"))
assert cfg.get("r", 0) <= 16, f"rank {cfg.get('r')} > serve_vllm.sh --max-lora-rank 16"
t = load_file(f"{src}/adapter_model.safetensors")
old = "base_model.model.model.layers."
new_p = "base_model.model.model.language_model.layers."
n_old = sum(k.startswith(old) for k in t)
assert n_old == len(t), f"예상 밖의 키 {len(t) - n_old}개 (이미 바뀐 어댑터인가?): {[k for k in t if not k.startswith(old)][:3]}"
# 키 이름 변경은 Qwen3.8(vLLM에서 ConditionalGeneration 구조)만 필요하다. Qwen3-14B 같은 일반 구조는 그대로 둔다
rename = "Qwen3.8" in (cfg.get("base_model_name_or_path") or "")
new = {new_p + k[len(old):]: v for k, v in t.items()} if rename else dict(t)
os.makedirs(dst)
save_file(new, f"{dst}/adapter_model.safetensors", metadata={"format": "pt"})
shutil.copy(f"{src}/adapter_config.json", f"{dst}/adapter_config.json")
print(f"ok: 키 {len(new)}개 {'변경' if rename else '그대로(변경 불필요)'}, r={cfg['r']}, alpha={cfg['lora_alpha']}, base={cfg.get('base_model_name_or_path')} -> {dst}")
PY
