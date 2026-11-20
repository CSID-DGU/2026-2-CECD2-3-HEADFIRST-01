"""
labeling.csv 검수 페이지 (로컬 웹). 엑셀 대신 브라우저에서 유튜브 구간을 바로 듣고 라벨을 단다.

실행:  python review_server.py              # http://localhost:8765 열림
       python review_server.py --csv 내몫.csv --port 8766

- 표준 라이브러리만 사용 (설치 없음)
- 저장할 때마다 CSV 전체를 다시 씀 (utf-8-sig). 같은 파일을 여러 사람이 동시에 열지 말 것 → 팀원은 영상 단위로 CSV를 나눠서 각자 실행
- usable 소문자 y/n = 미확인(prefill_labels.py가 채움), 대문자 Y/N = 사람이 확인함. 기본 필터는 미확인 y만 보여줌
- 단축키: Ctrl+Enter 저장 후 다음 / Alt+Y usable=Y / Alt+N usable=N / Alt+R 다시 듣기 / Alt+← 이전 / Alt+→ 다음(저장 안 함)
"""

import argparse
import csv
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from convert_raw import to_action  # 변환 규칙을 그대로 써서 INFORM/UNCERTAIN 미리보기

LABEL_COLS = ["speaker_group", "corrected_text", "entity_type", "gt_value", "pattern_tag", "usable", "notes"]
PATTERN_TAGS = ["PLAIN", "NON-INFORM", "REASK", "FIX", "NM-L1-1", "NM-L1-2", "NM-L1-3", "NM-L2-1", "NM-L2-2", "NM-L2-3",
                "NM-SP-1", "NM-SP-2", "NM-SP-3", "NM-SP-4", "DA-1", "DA-2", "DA-3", "DA-4", "DA-5", "UN-1", "UN-2", "CT-1"]

STATE = {"path": None, "rows": [], "cols": []}


def load():
    with STATE["path"].open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        STATE["rows"], STATE["cols"] = list(r), r.fieldnames


def save():
    tmp = STATE["path"].with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STATE["cols"])
        w.writeheader()
        w.writerows(STATE["rows"])
    tmp.replace(STATE["path"])


def video_id(cand_id):
    return cand_id.rsplit("_", 1)[0]


def preview(r):
    """convert_raw와 같은 규칙으로 이 행이 어떤 action이 되는지 + UNCERTAIN이면 이유."""
    if r.get("usable") != "Y":
        return {"act": "-", "slot": "", "value": "", "reason": "usable=Y가 아니라 변환 안 됨"}
    slot, act = to_action(r, [])
    if act is None:
        return {"act": "제외", "slot": "", "value": "", "reason": "entity_type 비어 있음 (notes에 Q: 표시도 없음)"}
    etype, gt = (r.get("entity_type") or "").strip(), (r.get("gt_value") or "").strip()
    reason = ""
    if act["act"] == "UNCERTAIN":
        if not gt:
            reason = "gt_value 비어 있음"
        elif etype == "age":
            reason = "entity_type=age (나이만) → 생년월일 확정 불가. 월·일까지 들리면 entity_type=birth_date, gt=YYYY-MM-DD"
        elif slot == "birth_date":
            reason = "연도만 (YYYY). 월·일까지 들리면 YYYY-MM-DD로"
        elif slot == "occurred_date":
            reason = "상대 표현/기간. 날짜 특정되면 YYYY-MM-DD로"
        else:
            reason = "값 확정 불가"
    return {"act": act["act"], "slot": slot, "value": (act["values"] or [""])[0], "reason": reason}


HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>raw 발화 검수</title>
<style>
 body{font-family:system-ui,"Malgun Gothic",sans-serif;margin:0;background:#f4f5f7;color:#222}
 header{display:flex;gap:16px;align-items:center;padding:10px 16px;background:#fff;border-bottom:1px solid #ddd}
 header>b{white-space:nowrap}
 header select,header button{font-size:14px;padding:4px 8px;flex:0 0 auto;max-width:360px}
 main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px;max-width:1500px}
 .card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px}
 iframe{width:100%;aspect-ratio:16/9;border:0;border-radius:6px}
 .ctx{color:#777;font-size:14px;margin:4px 0}
 .raw{font-size:20px;font-weight:600;margin:8px 0;padding:8px;background:#fff8e1;border-radius:6px}
 .hint{font-size:13px;color:#555}
 .hint b{color:#0a5}
 label{display:block;font-size:13px;color:#555;margin-top:10px}
 input[type=text],textarea,select{width:100%;box-sizing:border-box;font-size:16px;padding:6px;border:1px solid #bbb;border-radius:5px}
 textarea{height:70px}
 .row{display:flex;gap:10px}
 .row>div{flex:1}
 .btns{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
 button{font-size:15px;padding:8px 14px;border-radius:6px;border:1px solid #999;background:#fff;cursor:pointer}
 button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
 button.y{background:#16a34a;color:#fff;border-color:#16a34a} button.n{background:#dc2626;color:#fff;border-color:#dc2626}
 .usable{display:flex;gap:16px;align-items:center;font-size:16px}
 .usable label{display:inline;margin:0}
 .guide{font-size:12.5px;color:#444;line-height:1.5;margin-top:12px;border-top:1px dashed #ccc;padding-top:8px}
 #msg{color:#0a5;font-size:13px;margin-left:8px}
 .done{color:#16a34a;font-weight:600}
 .conv{margin-top:8px;padding:8px;border-radius:6px;font-size:14px;background:#eef}
 .conv.unc{background:#fdecec} .conv.inf{background:#e6f7ea}
 .conv b{font-size:15px}
 #list{grid-column:1/3;max-height:260px;overflow:auto;font-size:13px}
 #list table{width:100%;border-collapse:collapse}
 #list td,#list th{padding:3px 6px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}
 #list td.t{white-space:normal}
 #list tr{cursor:pointer} #list tr.cur{background:#fff3c4} #list tr:hover{background:#f0f4ff}
 .badge{padding:1px 6px;border-radius:4px;font-size:12px;color:#fff} .badge.UNCERTAIN{background:#dc2626} .badge.INFORM{background:#16a34a} .badge.x{background:#999}
</style></head><body>
<header>
 <b>raw 발화 검수</b>
 <select id="filter">
  <option value="ai">AI 유력 미확인</option><option value="notrack">확정 Y 중 트랙 미상</option><option value="uncertain">확정 Y 중 값 없음(UNCERTAIN)</option><option value="emptygt">확정 Y 중 gt_value 빈 칸</option><option value="Y">확인된 Y 전체</option><option value="y">미확인 y 전체</option><option value="yn">미확인 y+n</option><option value="all">전체</option>
 </select>
 <select id="video"><option value="">모든 영상</option></select>
 <span id="progress"></span><span id="msg"></span>
</header>
<main>
 <section class="card">
  <iframe id="player" allow="autoplay" src=""></iframe>
  <div class="btns"><button onclick="replay()">▶ 다시 듣기 (Alt+R)</button><a id="ytlink" target="_blank"><button>유튜브에서 열기</button></a><span id="meta" class="hint"></span></div>
  <div class="ctx" id="prev"></div>
  <div class="raw" id="raw"></div>
  <div class="ctx" id="next"></div>
  <div class="hint" id="hints"></div>
  <div class="conv" id="conv"></div>
  <div class="guide">
   <b>usable</b> Y=본인 발화·정답 확신(값 없는 회피·딴소리도 Y) / N=MC·가사·내레이션·화자불명·전사불가<br>
   <b>corrected_text</b> 들리는 대로 한글로. 숫자도 "칠십오"/"일흔다섯"처럼. 추임새·사투리 그대로<br>
   <b>gt_value</b> name=한글 성명 / age=숫자만(75) / birth_date=YYYY-MM-DD(연도만이면 YYYY, 음력은 " (음력)") / 비정보 답이면 비움<br>
   <b>pattern_tag</b> PLAIN(바로 답) · NON-INFORM(회피·딴소리) · REASK(되묻기) · FIX(번복) · 패턴표 코드. 여러 개면 |
  </div>
 </section>
 <section class="card">
  <form id="form" onsubmit="return false">
   <div class="row">
    <div><label>speaker_group</label><select name="speaker_group"><option value="">(미상)</option><option>노인</option><option>일반</option></select></div>
    <div><label>entity_type</label><select name="entity_type"><option value="">(없음)</option><option>name</option><option>age</option><option>birth_date</option><option>occurred_date</option><option>complaint</option></select></div>
   </div>
   <label>corrected_text (들리는 대로)</label><textarea name="corrected_text"></textarea>
   <div class="row">
    <div><label>gt_value</label><input type="text" name="gt_value" autocomplete="off"></div>
    <div><label>pattern_tag</label><input type="text" name="pattern_tag" list="tags" autocomplete="off"><datalist id="tags"></datalist></div>
   </div>
   <label>notes</label><input type="text" name="notes" autocomplete="off">
   <label>usable</label>
   <div class="usable">
    <label><input type="radio" name="usable" value="Y"> Y</label>
    <label><input type="radio" name="usable" value="N"> N</label>
    <span id="usable_raw" class="hint"></span>
   </div>
   <div class="btns">
    <button class="y" onclick="setU('Y')">Y (Alt+Y)</button>
    <button class="n" onclick="setU('N')">N (Alt+N)</button>
    <button class="primary" onclick="saveNext()">저장 후 다음 (Ctrl+Enter)</button>
    <button onclick="move(-1)">← 이전</button>
    <button onclick="move(1)">다음 →</button>
   </div>
  </form>
 </section>
 <section class="card" id="list"></section>
</main>
<script>
let rows=[], idx=0;
const $=s=>document.querySelector(s);
document.getElementById('tags').innerHTML=%TAGS%.map(t=>`<option value="${t}">`).join('');
async function load(){
  const f=$('#filter').value, v=$('#video').value;
  rows=await (await fetch(`/api/rows?filter=${f}&video=${encodeURIComponent(v)}`)).json();
  idx=0; renderList(); render();
}
function renderList(){
  const esc=t=>(t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  $('#list').innerHTML='<table><tr><th>#</th><th>변환</th><th>그룹</th><th>entity</th><th>gt_value</th><th>태그</th><th>발화</th><th>notes</th></tr>'+
    rows.map((r,i)=>{const p=r._preview||{};return `<tr data-i="${i}" class="${i===idx?'cur':''}"><td>${i+1}</td><td><span class="badge ${p.act==='INFORM'||p.act==='UNCERTAIN'?p.act:'x'}">${esc(p.act||'-')}</span></td><td>${esc(r.speaker_group)}</td><td>${esc(r.entity_type)}</td><td>${esc(r.gt_value)}</td><td>${esc(r.pattern_tag)}</td><td class="t">${esc(r.corrected_text||r.raw_text)}</td><td class="t">${esc(r.notes)}</td></tr>`;}).join('')+'</table>';
  $('#list').querySelectorAll('tr[data-i]').forEach(tr=>tr.onclick=()=>{idx=+tr.dataset.i; render();});
}
async function loadVideos(){
  const vs=await (await fetch('/api/videos')).json();
  $('#video').innerHTML='<option value="">모든 영상</option>'+vs.map(v=>`<option value="${v.id}">${v.id} (미확인 ${v.pending}/${v.total})</option>`).join('');
}
function render(){
  if(!rows.length){$('#progress').innerHTML='<span class="done">이 필터에 해당하는 행이 없음</span> — 위 필터를 바꿔 보세요'; $('#raw').textContent=''; $('#prev').textContent=''; $('#next').textContent=''; $('#conv').textContent=''; $('#player').src=''; return;}
  const r=rows[idx];
  $('#progress').textContent=`${idx+1} / ${rows.length}`;
  const vid=r.cand_id.replace(/_[^_]+$/,''), t=Math.max(0,Math.floor(+r.start)-2);
  $('#player').src=`https://www.youtube.com/embed/${vid}?start=${t}&autoplay=1&rel=0`;
  $('#ytlink').href=r.url;
  $('#meta').textContent=`${r.cand_id}  ${r.start}s`;
  $('#prev').textContent='◀ '+(r.context_prev||'');
  $('#raw').textContent=r.raw_text;
  $('#next').textContent='▶ '+(r.context_next||'');
  $('#hints').innerHTML='단서: <b>'+(r.pattern_hint||'-')+'</b> '+(r.hint_matched?'['+r.hint_matched+']':'');
  showConv(r._preview);
  $('#list').querySelectorAll('tr[data-i]').forEach(tr=>{tr.classList.toggle('cur',+tr.dataset.i===idx); if(+tr.dataset.i===idx) tr.scrollIntoView({block:'nearest'});});
  const f=document.forms[0];
  for(const c of ['speaker_group','corrected_text','entity_type','gt_value','pattern_tag','notes']) f[c].value=r[c]||'';
  const u=(r.usable||'').toUpperCase();
  for(const el of f.usable) el.checked=(el.value===u);
  $('#usable_raw').textContent=r.usable&&r.usable!==u?`(자동 제안: ${r.usable})`:'';
  f.corrected_text.focus();
}
function showConv(p){
  const el=$('#conv'); if(!p){el.textContent='';el.className='conv';return;}
  el.className='conv '+(p.act==='UNCERTAIN'?'unc':p.act==='INFORM'?'inf':'');
  el.innerHTML='변환 결과: <b>'+p.act+'</b>'+(p.slot?' · slot='+p.slot:'')+(p.value?' · value='+p.value:'')+(p.reason?'<br><span style="color:#a33">'+p.reason+'</span>':'');
}
function replay(){const p=$('#player'); p.src=p.src;}
function setU(v){for(const el of document.forms[0].usable) el.checked=(el.value===v);}
function move(d){idx=Math.min(Math.max(idx+d,0),rows.length-1); render();}
async function saveNext(){
  if(!rows.length) return;
  const f=document.forms[0], r=rows[idx], data={cand_id:r.cand_id};
  for(const c of ['speaker_group','corrected_text','entity_type','gt_value','pattern_tag','notes']) data[c]=f[c].value.trim();
  data.usable=[...f.usable].find(e=>e.checked)?.value||'';
  if(!data.usable){$('#msg').textContent='usable을 Y/N으로 정해 주세요'; return;}
  const res=await (await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})).json();
  Object.assign(r,data); r._preview=res.preview; showConv(res.preview); renderList(); $('#msg').textContent=`저장됨 (확인 ${res.confirmed}/${res.total}) → ${res.preview.act}`;
  if(idx<rows.length-1){idx++; render();} else {$('#progress').innerHTML='<span class="done">이 묶음 끝!</span> 필터를 바꾸거나 다른 영상을 고르세요'; }
  loadVideos();
}
document.addEventListener('keydown',e=>{
  if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();saveNext();}
  else if(e.altKey&&e.key.toLowerCase()==='y'){e.preventDefault();setU('Y');}
  else if(e.altKey&&e.key.toLowerCase()==='n'){e.preventDefault();setU('N');}
  else if(e.altKey&&e.key.toLowerCase()==='r'){e.preventDefault();replay();}
  else if(e.altKey&&e.key==='ArrowLeft'){e.preventDefault();move(-1);}
  else if(e.altKey&&e.key==='ArrowRight'){e.preventDefault();move(1);}
});
$('#filter').onchange=load; $('#video').onchange=load;
loadVideos().then(load);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            body = HTML.replace("%TAGS%", json.dumps(PATTERN_TAGS, ensure_ascii=False)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/rows":
            q = parse_qs(u.query)
            flt, vid = q.get("filter", ["y"])[0], q.get("video", [""])[0]
            rows = STATE["rows"]
            if vid:
                rows = [r for r in rows if video_id(r["cand_id"]) == vid]
            if flt == "notrack":
                rows = [r for r in rows if r.get("usable") == "Y" and not (r.get("speaker_group") or "").strip()]
            elif flt == "uncertain":
                rows = [r for r in rows if r.get("usable") == "Y" and preview(r)["act"] == "UNCERTAIN"]
            elif flt == "emptygt":
                rows = [r for r in rows if r.get("usable") == "Y" and not (r.get("gt_value") or "").strip()]
            elif flt == "ai":
                rows = [r for r in rows if r.get("usable") == "y" and (r.get("notes") or "").startswith("AI유력")]
            elif flt == "y":
                rows = [r for r in rows if r.get("usable") == "y"]
            elif flt == "yn":
                rows = [r for r in rows if r.get("usable") in ("y", "n", "")]
            elif flt == "Y":
                rows = [r for r in rows if r.get("usable") == "Y"]
            self._json([dict(r, _preview=preview(r)) for r in rows])
        elif u.path == "/api/videos":
            agg = {}
            for r in STATE["rows"]:
                v = agg.setdefault(video_id(r["cand_id"]), {"id": video_id(r["cand_id"]), "total": 0, "pending": 0})
                v["total"] += 1
                v["pending"] += r.get("usable") == "y" and (r.get("notes") or "").startswith("AI유력")
            self._json(sorted(agg.values(), key=lambda v: -v["pending"]))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/save":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n).decode("utf-8"))
        for r in STATE["rows"]:
            if r["cand_id"] == data["cand_id"]:
                for c in LABEL_COLS:
                    if c in data:
                        r[c] = data[c]
                break
        else:
            return self._json({"error": "cand_id not found"}, 404)
        save()
        confirmed = sum(1 for r in STATE["rows"] if r.get("usable") in ("Y", "N"))
        self._json({"ok": True, "confirmed": confirmed, "total": len(STATE["rows"]), "preview": preview(r)})

    def log_message(self, *a):  # 조용히
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="labeling.csv")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    STATE["path"] = Path(args.csv)
    load()
    pending = sum(1 for r in STATE["rows"] if r.get("usable") == "y")
    print(f"[csv] {args.csv}: {len(STATE['rows'])}행, 미확인 y {pending}행")
    url = f"http://localhost:{args.port}"
    print(f"[server] {url}  (Ctrl+C로 종료)")
    if not args.no_browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
