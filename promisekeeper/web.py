"""PromiseKeeper web app: one page plus a JSON API on the standard-library HTTP server. Loopback by default;
bind to 0.0.0.0 only behind a reverse proxy with PROMISEKEEPER_PUBLIC=1 (the hosted demo)."""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import ledger
from .extract import extract
from .llm import LLMError, TokenFactoryClient
from .research import ResearchError, TavilyClient, escalation_research

MAX_SOURCE_CHARS = 20000


def _load_fixtures():
    """Import fake_tokenfactory and samples from fixtures/, which sits beside the package (not inside it) so it
    is never shipped as installable code. Mirrors the sys.path convention the test suite already uses."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fdir = os.path.join(root, "fixtures")
    if fdir not in sys.path:
        sys.path.insert(0, fdir)
    import fake_tokenfactory  # type: ignore
    import samples  # type: ignore
    return fake_tokenfactory, samples

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PromiseKeeper</title>
<style>
body{font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f4f6fa;color:#1c2230}
header{background:#152238;color:#fff;padding:16px 24px}header h1{margin:0;font-size:20px}header small{opacity:.75}
main{display:grid;grid-template-columns:380px 1fr;gap:16px;padding:16px;max-width:1400px;margin:0 auto}
.card{background:#fff;border:1px solid #dde3ec;border-radius:10px;padding:14px;margin-bottom:12px}
.case{cursor:pointer}.case.active{outline:2px solid #2b6cb0}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;background:#e6ecf5;margin-left:6px}
.tag.promise_broken,.tag.decision_needed{background:#fde8e8;color:#9b1c1c}.tag.resolved{background:#e3f6ea;color:#1e6b3a}.tag.waiting_on_company{background:#fff4d6;color:#8a5a00}
button{background:#2b6cb0;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer;font:inherit}button.ghost{background:#e6ecf5;color:#1c2230}
input,textarea,select{font:inherit;padding:7px;border:1px solid #cbd5e1;border-radius:6px;width:100%;box-sizing:border-box}
label{display:block;font-size:12px;color:#475569;margin-top:8px}
.commit{border-left:4px solid #94a3b8;padding:6px 10px;margin:6px 0;background:#f8fafc}.commit.broken{border-color:#dc2626}.commit.kept{border-color:#16a34a}.commit.superseded{opacity:.6}
.next{background:#fff7ed;border-left:4px solid #f59e0b;padding:8px 10px;margin:8px 0}
.err{color:#9b1c1c;background:#fde8e8;padding:8px;border-radius:6px}.muted{color:#64748b;font-size:12px}
pre{white-space:pre-wrap;background:#f8fafc;padding:8px;border-radius:6px;font-size:12px;max-height:300px;overflow:auto}
.banner{background:#fff4d6;color:#8a5a00;border-bottom:1px solid #f2d38b;padding:10px 24px;font-size:13px}
</style></head><body>
<header><h1>PromiseKeeper</h1><small>what did they promise, and did they keep it? An open language model reads the call; you keep the receipts</small></header>
<div id="demoBanner"></div>
<main><aside>
<div class="card"><b>New case</b>
<label>Company</label><input id="company" placeholder="Example Home Insurance">
<label>Your name</label><input id="customer" placeholder="Alex Example">
<label>Reference</label><input id="reference" placeholder="EXAMPLE-CLAIM-0001">
<label>What they owe you</label><input id="owed" placeholder="Reimbursement of 4,200 dollars">
<div style="margin-top:10px"><button onclick="createCase()">Create case</button></div></div>
<div id="samples"></div>
<div id="list"></div></aside>
<section id="detail"><div class="card">Create or select a case, then paste a call transcript, chat log or email thread.</div></section></main>
<script>
const HDR={'content-type':'application/json','x-promisekeeper':'ui'};let cases=[],sel=null,DEMO=false,SAMPLES=[];
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function cls(s){return String(s??'').replace(/[^a-z_]/g,'')}
async function api(p,o){const r=await fetch(p,o);return r.json()}
async function load(){cases=await api('/api/cases');renderList();if(sel)renderDetail()}
async function init(){
  try{
    const h=await api('/healthz');
    DEMO=h.mode==='demo';
    if(DEMO){
      document.getElementById('demoBanner').innerHTML='<div class="banner">Demo mode: canned model responses for the three sample transcripts; run locally with a real model</div>';
      SAMPLES=await api('/api/samples');
      document.getElementById('samples').innerHTML='<div class="card"><b>Load sample</b><div class="muted" style="margin:4px 0 8px">Creates a matching case and pastes one of the three canned transcripts.</div>'
        +SAMPLES.map((s,i)=>`<div style="margin-bottom:6px"><button class="ghost" onclick="loadSample(${i})">${esc(s.label)}</button></div>`).join('')+'</div>';
    }
  }catch(e){}
  await load();
}
async function loadSample(i){
  const s=SAMPLES[i];
  const r=await api('/api/cases',{method:'POST',headers:HDR,body:JSON.stringify({company:s.company,customer:s.customer,reference:s.reference,what_is_owed:s.what_is_owed})});
  if(r.error)return alert(r.error);
  sel=r.id;await load();
  document.getElementById('kind').value=s.kind;
  document.getElementById('cdate').value=s.conversation_date;
  document.getElementById('src').value=s.text;
}
function renderList(){document.getElementById('list').innerHTML=cases.map(c=>`<div class="card case ${sel===c.id?'active':''}" data-id="${esc(c.id)}"><b>${esc(c.company)}</b><span class="tag ${cls(c.status)}">${esc(c.status.replace(/_/g,' '))}</span><br><small>${esc(c.reference)} for ${esc(c.customer)}</small><br><small class="muted">${c.commitments.length} commitment(s), ${c.sources.length} source(s)</small></div>`).join('')}
document.getElementById('list').addEventListener('click',e=>{const el=e.target.closest('.case');if(!el)return;sel=el.dataset.id;renderList();renderDetail()});
function renderDetail(){const c=cases.find(x=>x.id===sel);if(!c)return;
let h=`<div class="card"><h2 style="margin:0 0 4px">${esc(c.company)}<span class="tag ${cls(c.status)}">${esc(c.status.replace(/_/g,' '))}</span></h2>
<div>${esc(c.reference)} for ${esc(c.customer)} | owed: ${esc(c.what_is_owed)}</div>
<div class="next"><b>Next step:</b> ${esc(c.next_step)}</div>
<label>Conversation date</label><input id="cdate" type="date" value="${esc(c.today)}">
<label>Source type</label><select id="kind"><option value="call">Call transcript</option><option value="chat">Chat log</option><option value="email">Email thread</option></select>
<label>Paste the transcript, chat or email</label><textarea id="src" rows="8" placeholder="Agent: ... Representative: ..."></textarea>
<div style="margin-top:10px"><button onclick="addSource()">Extract commitments</button> <button class="ghost" onclick="research()">Find where to escalate (Tavily)</button> <button class="ghost" onclick="resolveCase()">Mark resolved</button> <a style="margin-left:10px" href="/api/evidence/${encodeURIComponent(c.id)}" target="_blank">Evidence pack</a></div>
<div id="out"></div></div>`;
h+=`<div class="card"><h3 style="margin:0 0 6px">Commitments</h3>${c.commitments.length?c.commitments.map(k=>`<div class="commit ${cls(k.status)}"><b>${esc(k.status)}</b> ${esc(k.action)} by ${esc(k.by_date||'unspecified')}<br><i>"${esc(k.quote)}"</i> (${esc(k.who)}, confidence ${esc(k.confidence)})</div>`).join(''):'<small class="muted">none yet</small>'}</div>`;
if(c.offers.length)h+=`<div class="card"><h3 style="margin:0 0 6px">Offers (your decision, not the assistant's)</h3>${c.offers.map((o,i)=>`<div class="commit"><b>${esc(o.kind)}</b> <i>"${esc(o.quote)}"</i><br>${o.decision?`decision: ${esc(o.decision)}`:`<button class="ghost" onclick="decide(${i},'accept')">Accept</button> <button class="ghost" onclick="decide(${i},'decline')">Decline</button>`}</div>`).join('')}</div>`;
if(c.customer_actions.length)h+=`<div class="card"><h3 style="margin:0 0 6px">They asked you to</h3>${c.customer_actions.map(a=>`<div class="commit">${esc(a.action)}</div>`).join('')}</div>`;
if(c.research)h+=`<div class="card"><h3 style="margin:0 0 6px">Where to escalate</h3><small class="muted">query: ${esc(c.research.query)}</small>${c.research.results.map(r=>`<div class="commit"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a><br><small>${esc(r.snippet)}</small></div>`).join('')}</div>`;
h+=`<div class="card"><h3 style="margin:0 0 6px">Sources</h3>${c.sources.length?c.sources.map(s=>`<div class="commit"><b>${esc(s.conversation_date)}</b> [${esc(s.kind)}] ${esc(s.summary)}<br><small class="muted">model ${esc(s.model)}, ${esc(s.usage.total_tokens||'?')} tokens</small><details><summary>text (${s.chars} chars)</summary><pre>${esc(s.text)}</pre></details></div>`).join(''):'<small class="muted">none yet</small>'}</div>`;
document.getElementById('detail').innerHTML=h}
async function createCase(){const b={company:v('company'),customer:v('customer'),reference:v('reference'),what_is_owed:v('owed')};const r=await api('/api/cases',{method:'POST',headers:HDR,body:JSON.stringify(b)});if(r.error)return alert(r.error);sel=r.id;await load()}
function v(id){return document.getElementById(id).value.trim()}
async function addSource(){const o=document.getElementById('out');o.innerHTML='<div class="muted">Asking Nemotron...</div>';const r=await api(`/api/cases/${encodeURIComponent(sel)}/sources`,{method:'POST',headers:HDR,body:JSON.stringify({kind:v('kind'),conversation_date:v('cdate'),text:document.getElementById('src').value})});if(r.error){o.innerHTML=`<div class="err">${esc(r.error)}</div>`;return}await load();document.getElementById('out').innerHTML=`<pre>${esc(JSON.stringify(r.extraction,null,1))}</pre>`}
async function research(){const r=await api(`/api/cases/${encodeURIComponent(sel)}/research`,{method:'POST',headers:HDR,body:'{}'});if(r.error)return alert(r.error);await load()}
async function decide(i,d){await api(`/api/cases/${encodeURIComponent(sel)}/offers/${i}`,{method:'POST',headers:HDR,body:JSON.stringify({decision:d})});await load()}
async function resolveCase(){await api(`/api/cases/${encodeURIComponent(sel)}/resolve`,{method:'POST',headers:HDR,body:'{}'});await load()}
init();
</script></body></html>"""


def make_handler(store: ledger.Store, llm: Optional[TokenFactoryClient], tavily: Optional[TavilyClient], public: bool,
                  demo: bool = False, samples: Optional[list] = None, demo_markers: tuple = ()):
    samples = samples or []
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def _json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def _text(self, code: int, text: str, ctype: str = "text/html; charset=utf-8") -> None:
            body = text.encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def _view(self, c: Dict[str, Any]) -> Dict[str, Any]:
            c = ledger.refresh_status(dict(c))
            c["next_step"] = ledger.next_step(c)
            c["today"] = date.today().isoformat()
            return c

        def do_GET(self) -> None:
            u = urlparse(self.path)
            if u.path == "/":
                return self._text(200, PAGE)
            if u.path == "/healthz":
                return self._json(200, {"ok": True, "model": llm.model if llm else None, "mode": "demo" if demo else "live"})
            if u.path == "/api/samples":
                if not demo:
                    return self._json(404, {"error": "not found"})
                return self._json(200, samples)
            if u.path == "/api/cases":
                return self._json(200, [self._view(c) for c in store.list()])
            if u.path.startswith("/api/evidence/"):
                try:
                    return self._text(200, ledger.evidence_pack(ledger.refresh_status(store.get(u.path.rsplit("/", 1)[1]))), "text/plain; charset=utf-8")
                except KeyError:
                    return self._json(404, {"error": "no such case"})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.headers.get("X-PromiseKeeper") != "ui":
                return self._json(403, {"error": "missing X-PromiseKeeper header"})
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length", "0"))
            if n > MAX_SOURCE_CHARS * 4:
                return self._json(413, {"error": "request too large"})
            try:
                body: Dict[str, Any] = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad JSON"})
            parts = u.path.strip("/").split("/")
            if u.path == "/api/cases":
                fields = {k: str(body.get(k, "")).strip()[:200] for k in ("company", "customer", "reference", "what_is_owed")}
                if not all(fields.values()):
                    return self._json(400, {"error": "company, customer, reference and what_is_owed are required"})
                case = ledger.new_case(**fields); store.upsert(case)
                return self._json(200, self._view(case))
            if len(parts) >= 4 and parts[:2] == ["api", "cases"]:
                try:
                    case = store.get(parts[2])
                except KeyError:
                    return self._json(404, {"error": "no such case"})
                action = parts[3]
                if action == "sources":
                    text = str(body.get("text", ""))
                    if not text.strip():
                        return self._json(400, {"error": "paste a transcript, chat log or email first"})
                    if len(text) > MAX_SOURCE_CHARS:
                        return self._json(400, {"error": f"source is over {MAX_SOURCE_CHARS} characters; split it"})
                    if demo and not any(m in text for m in demo_markers):
                        return self._json(422, {"error": "Demo mode only recognizes the three sample transcripts (use a "
                                                          "Load sample button). Run PromiseKeeper locally with your own "
                                                          "NEBIUS_API_KEY to extract commitments from any text."})
                    kind = body.get("kind") if body.get("kind") in ("call", "chat", "email") else "call"
                    cdate = str(body.get("conversation_date") or date.today().isoformat())
                    if llm is None:
                        return self._json(503, {"error": "NEBIUS_API_KEY is not configured on this server"})
                    try:
                        extraction = extract(llm, text, cdate, case["company"])
                    except (LLMError, ValueError) as e:
                        return self._json(422, {"error": str(e)})
                    ledger.add_source(case, kind, cdate, text, extraction, llm.model, llm.last_usage)
                    ledger.refresh_status(case); store.upsert(case)
                    return self._json(200, {"extraction": extraction, "case": self._view(case)})
                if action == "research":
                    if tavily is None:
                        return self._json(503, {"error": "TAVILY_API_KEY is not configured on this server"})
                    try:
                        case["research"] = escalation_research(tavily, case["company"], case["what_is_owed"][:60])
                    except ResearchError as e:
                        return self._json(502, {"error": str(e)})
                    store.upsert(case)
                    return self._json(200, self._view(case))
                if action == "offers" and len(parts) == 5 and parts[4].isdigit():
                    i = int(parts[4]); d = body.get("decision")
                    if i >= len(case["offers"]) or d not in ("accept", "decline"):
                        return self._json(400, {"error": "bad offer index or decision"})
                    case["offers"][i]["decision"] = d
                    ledger.refresh_status(case); store.upsert(case)
                    return self._json(200, self._view(case))
                if action == "resolve":
                    ledger.resolve(case); store.upsert(case)
                    return self._json(200, self._view(case))
            self._json(404, {"error": "not found"})
    return H


def serve(data_dir: str, host: str, port: int, llm: Optional[TokenFactoryClient], tavily: Optional[TavilyClient],
          demo: bool = False, samples: Optional[list] = None, demo_markers: tuple = ()) -> ThreadingHTTPServer:
    public = os.environ.get("PROMISEKEEPER_PUBLIC") == "1"
    if host not in ("127.0.0.1", "localhost", "::1") and not public:
        raise SystemExit("set PROMISEKEEPER_PUBLIC=1 to bind beyond loopback (only behind a reverse proxy)")
    httpd = ThreadingHTTPServer((host, port), make_handler(ledger.Store(data_dir), llm, tavily, public, demo, samples, demo_markers))
    return httpd


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1"); port = int(os.environ.get("PORT", "8800"))
    data_dir = os.environ.get("PROMISEKEEPER_DATA", os.path.join(os.getcwd(), "data"))
    demo = os.environ.get("PROMISEKEEPER_DEMO") == "1"
    demo_fake = None
    samples: list = []
    demo_markers: tuple = ()
    if demo:
        fake_tokenfactory, samples_mod = _load_fixtures()
        demo_fake = fake_tokenfactory.FakeServer().start()
        llm = TokenFactoryClient("demo-mode-no-key-needed", demo_fake.base_url, allow_local_fake=True)
        tavily = TavilyClient("demo-mode-no-key-needed", demo_fake.base_url, allow_local_fake=True)
        samples = samples_mod.SAMPLES
        demo_markers = samples_mod.DEMO_MARKERS
    else:
        llm = TokenFactoryClient.from_env() if os.environ.get("NEBIUS_API_KEY") else None
        tavily = TavilyClient.from_env() if os.environ.get("TAVILY_API_KEY") else None
    httpd = serve(data_dir, host, port, llm, tavily, demo=demo, samples=samples, demo_markers=demo_markers)
    mode = "DEMO (canned responses, no key needed)" if demo else (llm.model if llm else "NOT CONFIGURED")
    print(f"PromiseKeeper at http://{host}:{port}  model={mode}  tavily={'on' if tavily else 'off'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if demo_fake is not None:
            demo_fake.stop()


if __name__ == "__main__":
    main()
