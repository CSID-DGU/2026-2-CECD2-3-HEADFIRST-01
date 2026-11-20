# -*- coding: utf-8 -*-
"""문장 틀(template) 계산 공용 모듈.

틀 = 발화에서 '값'을 가린 형태소 열.
  - 정답 이름 문자열 → <NAME>
  - 숫자(아라비아·한글 수사, Kiwi 품사 SN/NR + 숫자 낭독 음절) → <N>  (연속하면 하나로)
  - 고유명사(NNP) → <P>
  - 문장부호·공백 제거
같은 틀 = 값만 바꾸면 같은 문장. 겹침 검사·분포 집계·줄이기 규칙이 모두 이 정의를 쓴다.
"""
import json
import re
from functools import lru_cache

from kiwipiepy import Kiwi

_kiwi = Kiwi()
# 숫자 낭독에 쓰이는 음절만으로 된 토큰(공일공, 삼구칠하나 등). 한 글자짜리 조사 '이'는 품사로 걸러짐
_NUM_CHARS = set("영공일이삼사오육륙칠팔구십백천만하나둘셋넷")
_NUM_TAGS = {"SN", "NR"}
_SKIP_TAGS = {"SF", "SP", "SS", "SE", "SO", "SW", "SSO", "SSC"}
_UNIT = {"년", "월", "일", "번", "개", "살", "세", "년생", "달", "주", "시", "분", "호"}


_MONTH_RE = re.compile(r"^(일|이|삼|사|오|유|육|칠|팔|구|시|십|십일|십이|동짓|섣)(월|달)$")


def _is_num_token(form, tag):
    if tag in _NUM_TAGS or any(c.isdigit() for c in form):
        return True
    if tag.startswith("N") and len(form) >= 2 and all(c in _NUM_CHARS for c in form):
        return True
    return False


def _pieces(seg):
    for tok in _kiwi.tokenize(seg):
        form, tag = tok.form, tok.tag
        if tag in _SKIP_TAGS:
            continue
        m = _MONTH_RE.match(form)
        if m:
            yield "<N>"
            yield m.group(2)
        elif _is_num_token(form, tag):
            yield "<N>"
        elif tag == "NNP":
            yield "<P>"
        else:
            yield form


@lru_cache(maxsize=200000)
def _template_cached(utt, names):
    segs = [utt]
    for n in names:  # 정답 이름 자리에서 잘라 조각별로 형태소 분석
        nxt = []
        for seg in segs:
            if seg == "<NAME>":
                nxt.append(seg)
                continue
            parts = seg.split(n)
            for i, part in enumerate(parts):
                if i:
                    nxt.append("<NAME>")
                nxt.append(part)
        segs = nxt
    out = []
    for seg in segs:
        for piece in (["<NAME>"] if seg == "<NAME>" else _pieces(seg)):
            if piece == "<N>" and out and out[-1] == "<N>":
                continue
            out.append(piece)
    return " ".join(out)


def template(utt, names=()):
    return _template_cached(utt, tuple(sorted(set(n for n in names if n), key=len, reverse=True)))


def char_ngrams(t, n=3):
    s = t.replace(" ", "")
    s = re.sub(r"<(NAME|N|P)>", lambda m: {"NAME": "Ⓝ", "N": "①", "P": "Ⓟ"}[m.group(1)], s)
    return {s[i:i + n] for i in range(max(1, len(s) - n + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# 데이터 읽기: 어떤 형식이든 (id, 발화, actions, pattern, 추가정보) 목록으로
# ---------------------------------------------------------------------------
def load_sft(path):
    """sft_train*.jsonl / raw_*.jsonl (messages 형식)"""
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            o = json.loads(line)
            user = o["messages"][1]["content"]
            utt = user.split("[마지막 USER 발화]\n", 1)[1]
            hist = user.split("[마지막 USER 발화]", 1)[0]
            try:
                acts = json.loads(o["messages"][2]["content"])["actions"]
            except Exception:
                acts = []
            out.append({"id": f"{o.get('dialogue_id', '')}#{i}", "utt": utt, "actions": acts,
                        "pattern": o.get("pattern", ""), "history": hist, "line": i})
    return out


def load_dialogues(path):
    """minwon_eval*.json / hard_*.json (KoSGD 대화 형식). eval=False가 아닌 USER 턴만"""
    out = []
    for d in json.load(open(path, encoding="utf-8")):
        for k, t in enumerate(d["turns"]):
            if t["speaker"] != "USER" or t.get("eval") is False:
                continue
            out.append({"id": f"{d['dialogue_id']}#{k}" if "type" not in d else d["dialogue_id"],
                        "utt": t["utterance"], "actions": t["frames"][0]["actions"],
                        "pattern": d.get("pattern", ""), "type": d.get("type", ""),
                        "difficulty": d.get("difficulty"), "source": d.get("source", {})})
    return out


def load_any(path):
    return load_sft(path) if str(path).endswith(".jsonl") else load_dialogues(path)


def names_of(item):
    return [v for a in item["actions"] if a.get("slot") == "name" for v in a.get("canonical_values", [])]


def cell_of(item):
    """(질문받은 슬롯 = 첫 action의 slot, act). action이 없으면 ('-', '-')"""
    if not item["actions"]:
        return ("-", "-")
    a = item["actions"][0]
    return (a["slot"], a["act"])


def value_signature(utt, names=()):
    """발화에 나온 값 토큰(숫자·정답 이름)의 표면형을 순서대로 이어 붙인 문자열.
    표현 다양화 전후로 이 값이 같으면 '값과 값의 순서는 그대로'라고 본다."""
    names = sorted(set(n for n in names if n), key=len, reverse=True)
    s, sig = utt, []
    pat = "|".join(re.escape(n) for n in names)
    parts = re.split(f"({pat})", s) if pat else [s]
    for part in parts:
        if part in names:
            sig.append(part)
            continue
        for tok in _kiwi.tokenize(part):
            m = _MONTH_RE.match(tok.form)
            if m:
                sig.append(m.group(1))
            elif tok.tag not in _SKIP_TAGS and _is_num_token(tok.form, tok.tag):
                sig.append(tok.form)
    return "".join(sig)
