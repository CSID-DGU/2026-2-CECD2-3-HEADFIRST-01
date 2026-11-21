#!/bin/bash
# vLLM 시험 서버 켜기/끄기/상태. 사용법: bash /var/tmp/csuhyeon/vllm_ctl.sh start|stop|status
# 서버 설정(모델, GPU, 어댑터)은 serve_vllm.sh에 있다. 켜면 약 6분 뒤 준비된다.
LOG=/var/tmp/csuhyeon/serve_vllm.log
pid() { pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" | head -1; }
case "$1" in
  start)
    if [ -n "$(pid)" ]; then echo "이미 켜져 있음 (pid $(pid))"; exit 0; fi
    nohup /var/tmp/csuhyeon/serve_vllm.sh > "$LOG" 2>&1 &
    echo "켜는 중 (pid $!). 준비되면 'status'가 ready를 보여 준다 (약 6분)." ;;
  stop)
    p=$(pid); [ -z "$p" ] && { echo "꺼져 있음"; exit 0; }
    kill "$p"; echo "끄는 중 (pid $p). GPU 메모리는 몇 초 뒤 비워진다." ;;
  status|*)
    p=$(pid)
    if [ -z "$p" ]; then echo "꺼져 있음"; 
    elif curl -sf localhost:8001/v1/models >/dev/null; then echo "ready (pid $p): $(curl -s localhost:8001/v1/models | python3 -c 'import json,sys; print([m["id"] for m in json.load(sys.stdin)["data"]])')";
    else echo "켜는 중 (pid $p). 마지막 로그: $(grep -oE '\[[a-z_]+\.py:[0-9]+\] .{0,80}' "$LOG" | tail -1)"; fi
    nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' '; echo ;;
esac
