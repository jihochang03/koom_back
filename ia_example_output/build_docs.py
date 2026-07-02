# -*- coding: utf-8 -*-
"""
Render koom_ia.json -> koom_ia_docs.html

A single self-contained app where the IA graph is the ONLY source of truth.
Documents (요구사항정의서 / ERD / 화면명세서) are *projections* rendered live
from the IA. Editing a node in the IA tab re-renders every document instantly.
"""
import json, os

here = os.path.dirname(os.path.abspath(__file__))
doc = json.load(open(os.path.join(here, "koom_ia.json"), encoding="utf-8"))
data_json = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))

HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KOOM IA · 문서 자동 렌더링</title>
<style>
:root{--bg:#0b1020;--panel:#121a2f;--panel2:#0f1729;--line:#26324d;--txt:#e7ecf5;--mut:#8a97b3;--acc:#4f8cff;--good:#2dd4bf;--warn:#fbbf24;--bad:#fb7185}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--txt);font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif}
#top{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,#0d1426,#0b1020);border-bottom:1px solid var(--line)}
.bar{display:flex;align-items:center;gap:14px;padding:10px 18px}
.bar h1{font-size:15px;margin:0;white-space:nowrap}
.bar .sub{color:var(--mut);font-size:11px}
.spacer{flex:1}
.tabs{display:flex;gap:4px;padding:0 12px}
.tabs button{background:transparent;color:var(--mut);border:0;border-bottom:2px solid transparent;padding:10px 16px;font-size:13px;cursor:pointer;font-weight:600}
.tabs button.on{color:var(--txt);border-bottom-color:var(--acc)}
.tabs button:hover{color:var(--txt)}
.btn{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:7px 12px;font-size:12px;cursor:pointer}
.btn:hover{border-color:var(--acc)}
.btn.acc{background:var(--acc);border-color:var(--acc);color:#fff}
#dirty{font-size:11px;color:var(--warn);display:none}#dirty.show{display:inline}
#wrap{padding:0}
.view{display:none}.view.on{display:block}
/* doc shell */
.doc{max-width:1180px;margin:0 auto;padding:22px}
.doc h2{font-size:20px;margin:0 0 4px}
.doc .lead{color:var(--mut);font-size:12.5px;margin-bottom:14px}
.usage{display:flex;flex-wrap:wrap;gap:7px;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:18px;font-size:11.5px}
.usage b{color:var(--mut);font-weight:600;margin-right:4px}
.chip{display:inline-flex;align-items:center;gap:5px;background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:3px 9px;font-size:11px}
.chip .dot{width:9px;height:9px;border-radius:3px}
.chip .n{color:var(--mut)}
.arrow{color:var(--mut)}
/* table */
table.rtm{width:100%;border-collapse:collapse;font-size:12px}
table.rtm th,table.rtm td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
table.rtm th{background:var(--panel);color:var(--mut);font-weight:600;position:sticky;top:96px}
table.rtm tr:hover td{background:rgba(79,140,255,.06)}
.fr{font-family:ui-monospace,monospace;color:var(--acc);font-weight:700;cursor:pointer}
.pri{font-size:10px;padding:1px 6px;border-radius:10px;border:1px solid var(--line)}
.mono{font-family:ui-monospace,monospace;font-size:11px}
.tagk{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px 6px;margin:1px 2px;font-size:10.5px;cursor:pointer}
.method{font-family:ui-monospace,monospace;font-size:10.5px;font-weight:700;padding:1px 5px;border-radius:5px;color:#fff;margin-right:4px}
.GET{background:#2563eb}.POST{background:#16a34a}.PATCH{background:#d97706}.PUT{background:#7c3aed}.DELETE{background:#dc2626}
/* erd cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card h3{margin:0;padding:10px 13px;font-size:13.5px;background:linear-gradient(180deg,#16203a,#121a2f);border-bottom:1px solid var(--line);cursor:pointer;display:flex;align-items:center;gap:8px}
.card h3 .pin{width:10px;height:10px;border-radius:3px;background:var(--good)}
.card .body{padding:6px 0}
.fld{display:flex;gap:8px;padding:4px 13px;font-size:11.5px;border-top:1px solid rgba(38,50,77,.5)}
.fld:first-child{border-top:0}
.fld .fn{font-family:ui-monospace,monospace;color:#cdd6ea}
.fld .key{color:var(--warn);font-size:10px;margin-left:auto}
.enum{padding:7px 13px;font-size:11px;color:var(--mut);border-top:1px dashed var(--line)}
.enum code{color:var(--good)}
.rel{padding:7px 13px;font-size:11px;border-top:1px solid var(--line);color:var(--mut)}
.rel b{color:#cdd6ea}
.relbadge{color:var(--acc)}
/* screen spec */
.sgroup{margin-bottom:22px}
.sgroup>h3{font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;border-bottom:1px solid var(--line);padding-bottom:6px;margin:0 0 12px}
.scard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:12px}
.scard .hd{display:flex;align-items:baseline;gap:10px;cursor:pointer}
.scard .code{font-family:ui-monospace,monospace;font-weight:700;color:var(--acc)}
.scard .nm{font-size:14px;font-weight:600}
.scard .ac{margin-left:auto;font-size:11px;color:var(--mut)}
.scard .pp{color:var(--mut);font-size:12px;margin:5px 0 9px}
.srow{display:flex;gap:8px;font-size:11.5px;margin:5px 0}
.srow .lab{color:var(--mut);width:74px;flex:none}
.srow .val{flex:1}
/* graph */
#g-main{position:relative;height:calc(100vh - 96px)}
#cv{display:block;width:100%;height:100%}
#ginfo{position:absolute;left:12px;top:12px;background:rgba(15,23,41,.9);border:1px solid var(--line);border-radius:10px;padding:8px 11px;font-size:11px;color:var(--mut)}
#glegend{position:absolute;left:12px;bottom:12px;background:rgba(15,23,41,.9);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:11px;color:var(--mut);max-width:60%}
#editor{position:absolute;top:12px;right:12px;width:360px;max-height:calc(100% - 24px);overflow:auto;background:rgba(15,23,41,.97);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:none}
#editor.show{display:block}
#editor .x{float:right;cursor:pointer;color:var(--mut)}
#editor h3{margin:0 0 6px;font-size:14px}
#editor label{display:block;font-size:11px;color:var(--mut);margin:9px 0 3px}
#editor input,#editor textarea{width:100%;background:var(--panel2);border:1px solid var(--line);border-radius:8px;color:var(--txt);font-size:12px;padding:7px 9px;font-family:ui-monospace,monospace}
#editor textarea{min-height:200px;resize:vertical;white-space:pre}
#editor .err{color:var(--bad);font-size:11px;margin-top:6px;display:none}
#editor .tag{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;color:#fff;margin-bottom:6px}
.hint{color:var(--mut);font-size:11px}
.banner{background:rgba(79,140,255,.1);border:1px solid rgba(79,140,255,.4);border-radius:10px;padding:9px 13px;font-size:12px;margin-bottom:16px}
.banner b{color:var(--acc)}
/* ---- 화면 미리보기(프로토타입) ---- */
.pv{display:flex;gap:16px;padding:16px;align-items:flex-start}
.pvindex{width:232px;flex:none;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:8px;max-height:calc(100vh - 132px);overflow:auto;position:sticky;top:108px}
.ixg{margin-bottom:10px}.ixh{font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);padding:6px 8px}
.ixi{display:block;padding:6px 8px;border-radius:7px;font-size:11.5px;color:#cdd6ea;cursor:pointer;text-decoration:none}
.ixi:hover{background:var(--panel2)}.ixi.on{background:var(--acc);color:#fff}.ixi b{font-family:ui-monospace,monospace;margin-right:5px}
.pvstage{flex:1;min-width:0}.pvmeta{margin-bottom:12px}
.device{margin:0 auto}.device.phone{width:392px}.device.desktop{width:100%}
.scr{background:#eef1f6;color:#1b2430;border-radius:26px;overflow:hidden;box-shadow:0 14px 44px rgba(0,0,0,.5);display:flex;flex-direction:column;min-height:700px}
.scr.desk{flex-direction:row;border-radius:12px;min-height:640px}
.appbar{background:linear-gradient(135deg,#4f8cff,#3b6fe0);color:#fff;padding:14px 16px;font-size:14px;font-weight:700;display:flex;align-items:center;gap:8px}
.appbar.light{background:#fff;color:#1b2430;border-bottom:1px solid #e3e8f0}
.appbar .code{font-family:ui-monospace,monospace;font-size:11px;background:rgba(255,255,255,.25);padding:2px 7px;border-radius:6px}
.appbar.light .code{background:#eef2f8;color:#4f8cff}
.appbar .who{margin-left:auto;font-size:11px;font-weight:500;opacity:.8}
.scrbody{padding:8px 12px 12px;flex:1;overflow:auto}
.scrbody.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 12px;align-content:start}
.wb{background:#fff;border:1px solid #e3e8f0;border-radius:13px;padding:11px 13px;margin:10px 2px;box-shadow:0 1px 2px rgba(20,30,50,.04)}
.wb:hover{border-color:#bcd0f5}
.wb h4{margin:0 0 8px;font-size:12px;color:#3a4660;display:flex;align-items:center;gap:6px}
.wb .reuse{font-size:9px;background:#e6f6f3;color:#0d9488;border-radius:10px;padding:1px 6px}
.wb .goto{margin-left:auto;font-size:10px;color:#4f8cff;font-family:ui-monospace,monospace}
.wb .badge{margin-left:auto;font-size:9px;background:#eef2f8;color:#5b6b8c;border-radius:10px;padding:1px 6px}
.wb .badge.in{background:#fff3e0;color:#d97706}
.ff{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:11px;color:#5b6b8c}.ff i{flex:1;height:8px;background:#eef2f8;border-radius:5px}
.fin{margin:6px 0}.fin label{display:block;font-size:10.5px;color:#5b6b8c;margin-bottom:3px}.fin .box{display:block;height:30px;background:#f3f6fb;border:1px solid #e3e8f0;border-radius:8px}
.bar{height:12px;background:#eef2f8;border-radius:6px;margin:5px 0}.bar.w60{width:60%}
.line{height:9px;background:#eef2f8;border-radius:5px;margin:6px 0}
.navrow{display:flex;gap:6px}.navrow i{flex:1;height:26px;background:#eef2f8;border-radius:7px}
.pills{display:flex;gap:6px}.pills span{flex:1;height:24px;background:#eef2f8;border-radius:20px}
.actions{padding:10px 14px;border-top:1px solid #e3e8f0;background:#fff}
.wbtn{background:#4f8cff;color:#fff;border-radius:11px;padding:11px;text-align:center;font-weight:600;font-size:12.5px;cursor:pointer;margin:6px 2px}
.wbtn:hover{background:#3b6fe0}.wbtn.sec{background:#eef2f8;color:#1b2430}
.tabbar{display:flex;border-top:1px solid #e3e8f0;background:#fff}
.tabbar a{flex:1;text-align:center;padding:11px 0;font-size:11px;color:#8a97b3;cursor:pointer}.tabbar a.on{color:#4f8cff;font-weight:700}
.adside{width:212px;flex:none;background:#0f1729;color:#cdd6ea;padding:10px;overflow:auto}
.adside .adlogo{font-weight:700;font-size:12px;padding:8px;color:#fff}
.adside a{display:block;padding:7px 9px;border-radius:7px;font-size:11px;color:#aeb9d0;cursor:pointer}
.adside a:hover{background:#1a2540}.adside a.on{background:#4f8cff;color:#fff}.adside a b{font-family:ui-monospace,monospace;margin-right:5px}
.adcontent{flex:1;display:flex;flex-direction:column;background:#eef1f6;min-width:0}
.empty{color:#8a97b3;font-size:12px;padding:20px;text-align:center}
.miniprev{font-size:10px;color:var(--acc);cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:1px 7px;margin-left:6px}
.reqlbl{font-size:10px;color:#7c5cff;margin:9px 2px 4px;font-family:ui-monospace,monospace;font-weight:700}
.reqjson{background:#0b1020;border:1px solid #26324d;border-radius:8px;padding:9px 11px;font-family:ui-monospace,monospace;font-size:10.5px;line-height:1.5;color:#cdd6ea;white-space:pre;overflow-x:auto;margin:0 2px}
/* mode toggle + right inspector */
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-right:10px}
.seg button{background:var(--panel2);color:var(--mut);border:0;padding:7px 15px;font-size:12px;cursor:pointer;font-weight:600}
.seg button.on{background:var(--acc);color:#fff}
.pvtop{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.pvtop .modedesc{font-size:11px;color:var(--mut)}
.pvside{width:340px;flex:none;position:sticky;top:108px;max-height:calc(100vh - 132px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.pvside h5{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);margin:16px 0 8px;border-top:1px solid var(--line);padding-top:12px}
.pvside h5.first{margin-top:0;border-top:0;padding-top:0}
.ff.click,.fin.click{cursor:pointer;border-radius:7px;padding-left:4px;padding-right:4px}
.ff.click:hover{background:#eaf1ff}
.ff em{font-style:normal;color:#1b2430;background:#eef2f8;border-radius:5px;padding:1px 6px;font-size:10.5px;margin-left:auto}
.ff.dev code{font-family:ui-monospace,monospace;color:#3a4660;font-size:11px}
.ff.dev .ty{margin-left:auto;font-size:10px;color:#7c5cff;font-family:ui-monospace,monospace}
.ff .req{color:#e11d48;font-weight:800;margin-left:1px}
.moref{font-size:10.5px;color:#4f8cff;padding:5px 2px;cursor:pointer;user-select:none}
.moref:hover{text-decoration:underline}
.wb .ff-hide{display:none}.wb.expanded .ff-hide{display:flex}
.fd .fdh{font-size:14px;font-weight:700;margin-bottom:2px;color:var(--txt)}
.fd .fdt{font-family:ui-monospace,monospace;font-size:11px;color:#a78bfa;margin-bottom:6px}
.fd .lbl{color:var(--mut);font-size:10.5px;margin-top:9px;text-transform:none;letter-spacing:0}
.fd>div{font-size:12px;color:#cdd6ea}
.fd .vals{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.fd .vchip{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:3px 9px;font-size:11px}
.fd .vchip b{color:var(--good)}.fd .vchip code{color:var(--mut);font-size:9.5px;margin-left:5px}
.tr{border:1px solid var(--line);border-radius:9px;padding:9px 10px;margin-bottom:8px;background:var(--panel2)}
.tr .trh{font-weight:600;font-size:12px;color:#cdd6ea;cursor:pointer}.tr .trh:hover{color:#fff}
.tr .kv2{font-size:10.5px;color:var(--mut);margin-top:6px}
.tr .api{font-family:ui-monospace,monospace;font-size:10px;color:#a78bfa;display:block}
.tr .st{display:inline-block;background:#0f1729;border:1px solid var(--line);border-radius:6px;padding:1px 7px;margin:3px 4px 0 0;font-size:10px;color:#2dd4bf;font-family:ui-monospace,monospace}
</style></head><body>
<div id="top">
  <div class="bar">
    <h1>KOOM · IA → 문서 자동 렌더링</h1>
    <span class="sub">IA(그래프)가 단일 진실원천 · 문서는 투영(projection)</span>
    <span class="spacer"></span>
    <span id="dirty">● 미저장 변경</span>
    <button class="btn" id="exportBtn">IA JSON 내보내기</button>
    <button class="btn" id="restoreBtn">원본 복원</button>
  </div>
  <div class="tabs" id="tabs"></div>
</div>
<div id="wrap">
  <div class="view" id="v-graph"><div id="g-main">
    <canvas id="cv"></canvas>
    <div id="ginfo"></div><div id="glegend"></div><div id="editor"></div>
  </div></div>
  <div class="view" id="v-preview"></div>
  <div class="view" id="v-req"></div>
  <div class="view" id="v-erd"></div>
  <div class="view" id="v-screens"></div>
</div>
<script id="ia-data" type="application/json">__DATA__</script>
<script>
const ORIGINAL = document.getElementById('ia-data').textContent;
let DOC = JSON.parse(ORIGINAL);
let byId={}, adj={};
function rebuild(){ byId={}; adj={}; DOC.nodes.forEach(n=>{byId[n.id]=n;adj[n.id]=[];});
  DOC.edges.forEach(e=>{ if(adj[e.from]&&adj[e.to]){adj[e.from].push(e.to);adj[e.to].push(e.from);} }); }
rebuild();
const out=(id,rel)=>DOC.edges.filter(e=>e.from===id&&(!rel||e.relation===rel));
const inc=(id,rel)=>DOC.edges.filter(e=>e.to===id&&(!rel||e.relation===rel));
const nt =t=>DOC.nodes.filter(n=>n.type===t);
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cleanName=n=>{const p=(n.name||'').split(' · ');return p.length>1?p.slice(1).join(' · '):n.name;};

const TYPE_COLOR={project:'#f5d76e',surface:'#5b6b8c',actor:'#ff7ab6',screen:'#4f8cff',component:'#7cc7ff',
 data_model:'#2dd4bf',api:'#a78bfa',business_rule:'#fb7185',validation:'#fbbf24',permission:'#f97316',
 context:'#94a3b8',state_machine:'#34d399',state:'#86efac'};
const TYPE_LABEL={project:'프로젝트',surface:'그룹',actor:'액터',screen:'화면',component:'컴포넌트',
 data_model:'데이터모델',api:'API',business_rule:'비즈니스규칙',validation:'검증',permission:'권한',
 context:'컨텍스트',state_machine:'상태머신',state:'상태'};
// 모든 한글 라벨/가이드/파라미터 라벨은 IA에서 로드 — 렌더러는 도메인 지식을 보유하지 않음
const GLOSS=DOC.glossary||{}; const PARAM_LABEL=GLOSS.param_labels||{};
function elabel(m,f,c){const L=((m&&m.payload.enum_labels)||{})[f]||{};return L[c]||c;}
function fguide(m,f){return (((m&&m.payload.field_guide)||{})[f])||{};}
function exampleOf(m,pf){return (m&&m.payload.field_examples&&m.payload.field_examples[pf.name])||'';}
// IA 값(라벨/예시/타입)을 JSON 적합한 실제 값으로 변환 (enum은 코드로 역매핑)
function jsonValue(m,pf){const ty=typeOf(m,pf);const ex=exampleOf(m,pf);const en=(m.payload.enums||{})[pf.name];
 if(en&&en.length){const L=(m.payload.enum_labels||{})[pf.name]||{};for(const c of en){if(L[c]===ex)return c;}return en[0];}
 if(ty==='number'){if(typeof ex==='number')return ex;const num=Number(String(ex).replace(/[, ]/g,''));return isNaN(num)?ex:num;}
 if(ty==='boolean')return (ex===true||ex==='true');
 if(ty==='array/json'){try{return JSON.parse(ex);}catch(e){return ex;}}
 return ex;}
function jsonBody(m){const skip=/^id$|_at$|^group$|snapshot_uuid|balance_after|reason_display|^unique$|^pk$/;
 const obj={};let k=0;for(const f of (m.payload.fields||[])){const pf=parseField(f);if(skip.test(pf.name))continue;if(k++>=12){obj["…"]="…";break;}obj[pf.name]=jsonValue(m,pf);}
 return JSON.stringify(obj,null,2);}
const TYPE_KO={string:'문자열',number:'숫자',datetime:'일시(YYYY-MM-DD HH:mm)',date:'날짜(YYYY-MM-DD)',url:'URL',email:'이메일',boolean:'참/거짓(true/false)','array/json':'배열/JSON'};
function formatOf(m,pf,ev,ty){if(ev&&ev.length)return ev.length+'개 보기 중 하나 — 코드 저장·한글 라벨 표시';
 const p=[TYPE_KO[ty]||ty];if(pf.note)p.push('제약: '+pf.note);const ex=exampleOf(m,pf);if(ex)p.push('형식 예: '+ex);return p.join(' · ');}
function parseField(f){const mm=f.match(/[\(\[\{=]/);if(!mm)return{name:f.trim(),note:''};const i=mm.index;return{name:f.slice(0,i).trim(),note:f.slice(i).replace(/^[\(\[\{=]/,'').replace(/[\)\]\}]\s*$/,'').trim()};}
// 타입은 IA(data_model.payload.field_types)에서 읽음 — 렌더러는 추론하지 않음
function typeOf(m,pf){return (m&&m.payload.field_types&&m.payload.field_types[pf.name])||'string';}
function isReq(note,name){return /필수|unique|upsert|PK|FK/.test(note);}
// 예시값 생성 로직 없음 — 모든 예시는 IA(data_model.payload.field_examples)에서만 읽음
// PARAM_LABEL은 IA glossary에서 로드됨(상단 정의)
function pathParams(scr){const set=new Set();out(scr.id,'calls').forEach(e=>{const a=byId[e.to];if(!a)return;(a.payload.path.match(/\{[^}]+\}/g)||[]).forEach(p=>set.add(p.replace(/[{}]/g,'')));});return[...set];}
function fieldInfo(id,i){const m=byId[id];if(!m)return;const f=(m.payload.fields||[])[i];const pf=parseField(f);
 const ev=(m.payload.enums||{})[pf.name];const ty=typeOf(m,pf);const req=isReq(pf.note,pf.name);
 const g=fguide(m,pf.name);const el=document.getElementById('fieldDetail');if(!el)return;
 const enumHtml=ev?`<div class="vals">${ev.map(v=>`<span class="vchip"><b>${esc(elabel(m,pf.name,v))}</b><code>${esc(v)}</code></span>`).join('')}</div>`:'';
 if(mode==='developer'){
   el.innerHTML=`<div class="fd"><div class="fdh">${esc(pf.name)}</div>
     <div class="fdt">type: ${ty}${req?' · <span class="req">required</span>':' · optional'}</div>
     <div class="lbl">형식</div><div>${esc(formatOf(m,pf,ev,ty))}</div>
     ${pf.note?`<div class="lbl">제약 / 설명</div><div>${esc(pf.note)}</div>`:''}
     ${ev?`<div class="lbl">enum · ${ev.length}개 중 하나</div>${enumHtml}`:`<div class="lbl">예시 값</div><div class="vals"><span class="vchip">${esc(exampleOf(m,pf,ev,ty))}</span></div>`}
     <div class="lbl">소속 모델</div><div>${esc(m.name)} · <code style="color:#a78bfa">${esc(f)}</code></div>
     ${g.howto?`<div class="lbl">프론트 대입</div><div>${esc(g.howto)}</div>`:''}</div>`;
 }else{
   el.innerHTML=`<div class="fd"><div class="fdh">${esc(pf.name)}</div>
     <div>${esc(g.what||(ev?'정해진 보기 중 하나를 고르는 값입니다.':'이 화면에 표시·입력되는 값입니다.'))}</div>
     ${ev?`<div class="lbl">가능한 값 — ${ev.length}가지 중 하나</div>${enumHtml}`:`<div class="lbl">예시</div><div class="vals"><span class="vchip">${esc(exampleOf(m,pf,ev,ty))}</span></div>`}
     <div class="lbl">형식</div><div>${esc(formatOf(m,pf,ev,ty))}</div>
     ${g.howto?`<div class="lbl">어떻게 대입하나요?</div><div>${esc(g.howto)}</div>`:(ev?`<div class="lbl">대입</div><div>위 보기 중 하나 선택 — 코드값 저장, 화면엔 한글 라벨 표시.</div>`:'')}</div>`;
 }
}

// node-usage bar: given an array of node ids actually consumed, count by type
function usageBar(ids, note){
  const c={}; ids.forEach(id=>{const n=byId[id];if(n)c[n.type]=(c[n.type]||0)+1;});
  const chips=Object.entries(c).sort((a,b)=>b[1]-a[1]).map(([t,n])=>
    `<span class="chip"><span class="dot" style="background:${TYPE_COLOR[t]}"></span>${TYPE_LABEL[t]||t}<span class="n">${n}</span></span>`).join('<span class="arrow">·</span>');
  return `<div class="usage"><b>이 문서가 사용하는 IA 노드:</b>${chips}${note?`<span class="arrow">|</span><span class="n">${note}</span>`:''}</div>`;
}
function gotoNode(id){ activate('graph'); select(byId[id]); focusOn(byId[id]); }

/* ============================ 요구사항정의서 (RTM) ============================ */
function renderReq(){
  const used=new Set(); const rows=[];
  nt('screen').forEach(s=>{
    used.add(s.id);
    const apis=out(s.id,'calls').map(e=>byId[e.to]).filter(Boolean);
    const rules=out(s.id,'governed_by').map(e=>byId[e.to]).filter(Boolean);
    const vals=out(s.id,'validated_by').map(e=>byId[e.to]).filter(Boolean);
    const actor=byId[s.payload.primary_actor];
    apis.forEach(a=>used.add(a.id)); rules.forEach(r=>used.add(r.id)); vals.forEach(v=>used.add(v.id)); if(actor)used.add(actor.id);
    (s.payload.requirements||['—']).forEach(fr=>{
      rows.push({fr,s,actor,apis,rules,vals});
    });
  });
  rows.sort((a,b)=>a.fr.localeCompare(b.fr));
  const prioColor={'🔴':'var(--bad)','🟡':'var(--warn)','⚪':'var(--mut)'};
  const body=rows.map(r=>{
    const pri=(r.rules[0]&&r.rules[0].payload.priority)||'';
    return `<tr>
      <td><span class="fr" onclick="gotoNode('${r.s.id}')">${esc(r.fr)}</span></td>
      <td>${esc(cleanName(r.s))}<div class="hint">${esc(r.s.payload.purpose||'')}</div></td>
      <td>${r.actor?esc(cleanName(r.actor)):'—'}</td>
      <td><span class="tagk" onclick="gotoNode('${r.s.id}')">${esc(r.s.payload.code)}</span></td>
      <td>${r.apis.map(a=>`<div class="mono"><span class="method ${a.payload.method}">${a.payload.method}</span>${esc(a.payload.path)}</div>`).join('')||'—'}</td>
      <td>${r.rules.map(x=>`<span class="tagk" onclick="gotoNode('${x.id}')" title="${esc(x.payload.description||'')}">${esc(x.payload.priority||'')} ${esc(x.name)}</span>`).join(' ')||'—'}</td>
      <td>${r.vals.map(x=>`<span class="tagk" onclick="gotoNode('${x.id}')" title="${esc(x.payload.condition||'')}">${esc(x.name)}</span>`).join(' ')||'—'}</td>
    </tr>`;
  }).join('');
  document.getElementById('v-req').innerHTML=`<div class="doc">
    <h2>요구사항 정의서 (RTM)</h2>
    <div class="lead">화면 노드의 <code>requirements(FR)</code> 를 펼치고, <code>calls</code>(API)·<code>governed_by</code>(규칙)·<code>validated_by</code>(검증)·<code>primary_actor</code> 관계를 따라 자동 생성됩니다. 행을 클릭하면 IA 그래프의 해당 노드로 이동합니다.</div>
    ${usageBar([...used], rows.length+'개 요구사항 행')}
    <table class="rtm"><thead><tr><th>FR</th><th>기능(화면)</th><th>액터</th><th>화면</th><th>API / 처리</th><th>관련 규칙</th><th>검증</th></tr></thead><tbody>${body}</tbody></table>
  </div>`;
}

/* ================================== ERD ================================== */
function renderErd(){
  const used=new Set(); const dms=nt('data_model');
  const cards=dms.map(d=>{
    used.add(d.id);
    const fields=(d.payload.fields||[]).map(f=>{
      const isKey=/unique|FK|PK|1:1|upsert|FK\)/.test(f);
      return `<div class="fld"><span class="fn">${esc(f)}</span>${isKey?'<span class="key">KEY/REL</span>':''}</div>`;
    }).join('');
    const enums=d.payload.enums?Object.entries(d.payload.enums).map(([k,v])=>
      `<div class="enum">${esc(k)}: ${v.map(c=>`${esc(elabel(d,k,c))} <code>${esc(c)}</code>`).join(' · ')}</div>`).join(''):'';
    const rels=out(d.id,'belongs_to').concat(out(d.id,'derived_from'))
      .filter(e=>byId[e.to]&&byId[e.to].type==='data_model');
    rels.forEach(e=>used.add(e.to));
    const relHtml=rels.map(e=>`<div class="rel"><span class="relbadge">${e.relation}</span> → <b onclick="gotoNode('${e.to}')" style="cursor:pointer">${esc(byId[e.to].name)}</b>${e.metadata&&e.metadata.note?` <span class="hint">(${esc(e.metadata.note)})</span>`:''}</div>`).join('');
    const writers=inc(d.id,'writes').map(e=>byId[e.from]).filter(Boolean);
    const readers=inc(d.id,'reads').map(e=>byId[e.from]).filter(Boolean);
    writers.concat(readers).forEach(a=>used.add(a.id));
    const apiHtml=(writers.length||readers.length)?`<div class="rel"><span class="hint">쓰기:</span> ${writers.map(a=>`<span class="tagk" onclick="gotoNode('${a.id}')">${esc(a.payload.path)}</span>`).join('')||'—'}<br><span class="hint">읽기:</span> ${readers.map(a=>`<span class="tagk" onclick="gotoNode('${a.id}')">${esc(a.payload.path)}</span>`).join('')||'—'}</div>`:'';
    const proposed=(d.payload.status||'').includes('proposed');
    return `<div class="card">
      <h3 onclick="gotoNode('${d.id}')"><span class="pin" style="background:${proposed?'var(--warn)':'var(--good)'}"></span>${esc(d.name)}</h3>
      <div class="body">
        ${d.payload.description?`<div class="enum" style="border-top:0;color:#cdd6ea">${esc(d.payload.description)}</div>`:''}
        ${fields}${enums}${relHtml}${apiHtml}
      </div></div>`;
  }).join('');
  document.getElementById('v-erd').innerHTML=`<div class="doc">
    <h2>ERD · 데이터 모델</h2>
    <div class="lead"><code>data_model</code> 노드를 엔티티로, <code>belongs_to</code>/<code>derived_from</code> 를 관계로, <code>reads</code>/<code>writes</code>(API) 를 접근 경로로 렌더링합니다. <span style="color:var(--warn)">노란 핀</span> = 스펙 미확정(프로토타입 only).</div>
    ${usageBar([...used], dms.length+'개 엔티티')}
    <div class="grid">${cards}</div>
  </div>`;
}

/* ============================== 화면 명세서 ============================== */
function renderScreens(){
  const used=new Set();
  const surfaces=nt('surface').filter(s=>['surface.customer_app','surface.cs_console','surface.hq_admin','surface.public'].includes(s.id));
  const groups=surfaces.map(sf=>{
    const screens=out(sf.id,'contains').map(e=>byId[e.to]).filter(n=>n&&n.type==='screen');
    const cards=screens.map(s=>{
      used.add(s.id);
      const actor=byId[s.payload.primary_actor]; if(actor)used.add(actor.id);
      const apis=out(s.id,'calls').map(e=>byId[e.to]).filter(Boolean); apis.forEach(a=>used.add(a.id));
      const trans=out(s.id,'transitions_to').map(e=>byId[e.to]).filter(Boolean);
      // 표시(reads) / 입력(writes) data models via the called APIs
      const showDM=new Set(), inDM=new Set();
      apis.forEach(a=>{ out(a.id,'reads').forEach(e=>{showDM.add(e.to);used.add(e.to);});
                        out(a.id,'writes').forEach(e=>{inDM.add(e.to);used.add(e.to);}); });
      const rules=out(s.id,'governed_by').map(e=>byId[e.to]).filter(Boolean); rules.forEach(r=>used.add(r.id));
      const dmChips=set=>[...set].map(id=>`<span class="tagk" onclick="gotoNode('${id}')">${esc(byId[id]?byId[id].name:id)}</span>`).join('')||'—';
      return `<div class="scard">
        <div class="hd">
          <span class="code" onclick="gotoNode('${s.id}')" style="cursor:pointer">${esc(s.payload.code)}</span><span class="nm">${esc(cleanName(s))}</span>
          <span class="miniprev" onclick="event.stopPropagation();openPreview('${s.id}')">🖥 미리보기</span>
          <span class="ac">${actor?esc(cleanName(actor)):''} · ${(s.payload.requirements||[]).join(', ')}</span>
        </div>
        <div class="pp">${esc(s.payload.purpose||'')}</div>
        <div class="srow"><span class="lab">처리 API</span><span class="val">${apis.map(a=>`<div class="mono"><span class="method ${a.payload.method}">${a.payload.method}</span>${esc(a.payload.path)} <span class="hint">${esc(a.payload.summary||'')}</span></div>`).join('')||'—'}</span></div>
        <div class="srow"><span class="lab">표시(읽기)</span><span class="val">${dmChips(showDM)}</span></div>
        <div class="srow"><span class="lab">입력(쓰기)</span><span class="val">${dmChips(inDM)}</span></div>
        <div class="srow"><span class="lab">전이</span><span class="val">${trans.map(t=>`<span class="tagk" onclick="gotoNode('${t.id}')">→ ${esc(t.payload.code)} ${esc(cleanName(t))}</span>`).join('')||'(종단)'}</span></div>
        ${rules.length?`<div class="srow"><span class="lab">규칙</span><span class="val">${rules.map(r=>`<span class="tagk" onclick="gotoNode('${r.id}')">${esc(r.payload.priority||'')} ${esc(r.name)}</span>`).join('')}</span></div>`:''}
      </div>`;
    }).join('');
    return `<div class="sgroup"><h3>${esc(cleanName(sf)||sf.name)} <span class="hint">· ${screens.length}화면</span></h3>${cards}</div>`;
  }).join('');
  document.getElementById('v-screens').innerHTML=`<div class="doc">
    <h2>화면 명세서</h2>
    <div class="lead">각 <code>screen</code> 노드를 표면(surface)별로 묶고, <code>calls</code>→API, API의 <code>reads</code>/<code>writes</code>→데이터모델(표시/입력), <code>transitions_to</code>→전이, <code>governed_by</code>→규칙을 따라 렌더링합니다.</div>
    ${usageBar([...used], nt('screen').length+'화면')}
    ${groups}
  </div>`;
}

/* =============================== IA GRAPH =============================== */
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
let cam={x:0,y:0,z:0.8}, drag=null, pan=false, last=null, sel=null, hover=null, graphActive=false;
DOC.nodes.forEach((n,i)=>{const a=i/DOC.nodes.length*6.28;n.x=Math.cos(a)*340;n.y=Math.sin(a)*340;n.vx=0;n.vy=0;});
function resize(){const r=devicePixelRatio||1;cv.width=cv.clientWidth*r;cv.height=cv.clientHeight*r;ctx.setTransform(r,0,0,r,0,0);}
addEventListener('resize',()=>{if(graphActive)resize();});
const W=()=>cv.clientWidth,H=()=>cv.clientHeight;
const toS=n=>({x:n.x*cam.z+W()/2+cam.x,y:n.y*cam.z+H()/2+cam.y});
const toW=(px,py)=>({x:(px-W()/2-cam.x)/cam.z,y:(py-H()/2-cam.y)/cam.z});
const rad=n=>n.type==='project'?13:n.type==='surface'?9:n.type==='screen'?7:n.type==='state_machine'?8:6;
function step(){const N=DOC.nodes;const rep=2500,k=0.02,cl=0.85;
  for(let i=0;i<N.length;i++){const a=N[i];
    for(let j=i+1;j<N.length;j++){const b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01;if(d2>140000)continue;let d=Math.sqrt(d2),f=rep/d2,fx=dx/d*f,fy=dy/d*f;a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;}
    a.vx+=-a.x*0.001;a.vy+=-a.y*0.001;}
  DOC.edges.forEach(e=>{const a=byId[e.from],b=byId[e.to];if(!a||!b)return;let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+.01;const L=e.relation==='contains'?64:120,f=(d-L)*k,fx=dx/d*f,fy=dy/d*f;a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;});
  N.forEach(n=>{if(n===drag)return;n.x+=n.vx*=cl;n.y+=n.vy;n.vy*=cl;});}
function draw(){ctx.clearRect(0,0,W(),H());
  DOC.edges.forEach(e=>{const a=byId[e.from],b=byId[e.to];if(!a||!b)return;const A=toS(a),B=toS(b);const hot=sel&&(e.from===sel.id||e.to===sel.id);
    ctx.strokeStyle=hot?'#fff':'#3a4a6b';ctx.globalAlpha=hot?.95:(sel?.08:.4);ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(A.x,A.y);if(e.relation==='contains')ctx.lineTo(B.x,B.y);else{const mx=(A.x+B.x)/2,my=(A.y+B.y)/2-(B.x-A.x)*.08;ctx.quadraticCurveTo(mx,my,B.x,B.y);}ctx.stroke();});
  ctx.globalAlpha=1;
  DOC.nodes.forEach(n=>{const p=toS(n),r=rad(n)*(cam.z<1?1:cam.z*.9);const dim=sel&&sel!==n&&!adj[sel.id].includes(n.id);
    ctx.globalAlpha=dim?.2:1;ctx.beginPath();ctx.arc(p.x,p.y,r,0,7);ctx.fillStyle=TYPE_COLOR[n.type]||'#888';ctx.fill();
    if(n===sel){ctx.lineWidth=2.5;ctx.strokeStyle='#fff';ctx.stroke();}else if(n===hover){ctx.lineWidth=2;ctx.strokeStyle='#fff9';ctx.stroke();}
    if(cam.z>0.95||n.type==='surface'||n.type==='project'||n===hover||n===sel){ctx.globalAlpha=dim?.3:.9;ctx.fillStyle='#dde6f7';ctx.font=(n.type==='surface'||n.type==='project'?'700 ':'')+'11px sans-serif';const l=n.name||n.id;ctx.fillText(l.length>28?l.slice(0,27)+'…':l,p.x+r+3,p.y+4);}});
  ctx.globalAlpha=1;
  document.getElementById('ginfo').innerHTML=`노드 <b style="color:#fff">${DOC.stats.nodes}</b> · 엣지 <b style="color:#fff">${DOC.stats.edges}</b> · 줌 ${cam.z.toFixed(2)}×<br><span style="opacity:.7">드래그=이동 · 휠=줌 · 노드클릭=편집</span>`;}
function loop(){if(graphActive){for(let i=0;i<2;i++)step();draw();}requestAnimationFrame(loop);}
function pick(px,py){let best=null,bd=14;for(const n of DOC.nodes){const p=toS(n);const d=Math.hypot(p.x-px,p.y-py);if(d<bd+rad(n)){bd=d;best=n;}}return best;}
cv.addEventListener('mousedown',e=>{const n=pick(e.offsetX,e.offsetY);if(n)drag=n;else pan=true;last={x:e.offsetX,y:e.offsetY};});
addEventListener('mousemove',e=>{if(!graphActive)return;const r=cv.getBoundingClientRect();const px=e.clientX-r.left,py=e.clientY-r.top;
  if(drag){const w=toW(px,py);drag.x=w.x;drag.y=w.y;drag.vx=0;drag.vy=0;}else if(pan&&last){cam.x+=px-last.x;cam.y+=py-last.y;last={x:px,y:py};}else{hover=pick(px,py);cv.style.cursor=hover?'pointer':'default';}});
addEventListener('mouseup',e=>{if(drag&&last){const m=Math.hypot(e.offsetX-last.x,e.offsetY-last.y);if(m<4)select(drag);}drag=null;pan=false;last=null;});
cv.addEventListener('click',e=>{if(!pick(e.offsetX,e.offsetY))select(null);});
cv.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY<0?1.1:1/1.1;const w=toW(e.offsetX,e.offsetY);cam.z=Math.max(.2,Math.min(3,cam.z*f));const w2=toW(e.offsetX,e.offsetY);cam.x+=(w2.x-w.x)*cam.z;cam.y+=(w2.y-w.y)*cam.z;},{passive:false});
function focusOn(n){if(!n)return;cam.x=-n.x*cam.z;cam.y=-n.y*cam.z;cam.z=1.1;}

function select(n){sel=n;const d=document.getElementById('editor');if(!n){d.classList.remove('show');return;}
  const ins=inc(n.id),outs=out(n.id);
  d.innerHTML=`<span class="x" onclick="select(null)">×</span>
   <span class="tag" style="background:${TYPE_COLOR[n.type]}">${TYPE_LABEL[n.type]||n.type}</span>
   <h3>${esc(n.name)}</h3>
   <div class="hint">id: ${esc(n.id)} · v${n.version} · origin: ${esc(n.origin_context)}</div>
   <label>이름 (name)</label><input id="ed-name" value="${esc(n.name)}">
   <label>payload (JSON · 편집 시 문서에 즉시 반영)</label>
   <textarea id="ed-pl">${esc(JSON.stringify(n.payload,null,2))}</textarea>
   <div class="err" id="ed-err"></div>
   <div style="margin-top:10px;display:flex;gap:6px">
     <button class="btn acc" onclick="applyEdit('${n.id}')">적용 → 문서 재렌더</button>
     <button class="btn" onclick="select(null)">취소</button>
   </div>
   <div class="hint" style="margin-top:10px">연결: 나감 ${outs.length} · 들어옴 ${ins.length}</div>`;
  d.classList.add('show');}
function applyEdit(id){const n=byId[id];const nm=document.getElementById('ed-name').value;const txt=document.getElementById('ed-pl').value;const err=document.getElementById('ed-err');
  let pl;try{pl=JSON.parse(txt);}catch(e){err.textContent='payload JSON 오류: '+e.message;err.style.display='block';return;}
  err.style.display='none';n.name=nm;n.payload=pl;n.version=(n.version||1)+1;n.updated_at=new Date().toISOString();
  markDirty();rebuild();renderAll();select(n);}
function markDirty(){DOC.__dirty=true;document.getElementById('dirty').classList.add('show');}

/* ============================ 화면 미리보기(프로토타입) ============================ */
let curScreen='screen.s_02';
let mode='designer';
function setMode(m){mode=m;renderPreview();}
function surfaceOf(sid){const e=inc(sid,'contains').find(x=>byId[x.from]&&byId[x.from].type==='surface');return e?byId[e.from]:null;}
function compsOf(sid){const m={};out(sid,'contains').forEach(e=>{const n=byId[e.to];if(n&&n.type==='component')m[n.id]=n;});
  DOC.edges.forEach(e=>{if(e.relation==='impacts'&&e.to===sid){const n=byId[e.from];if(n&&n.type==='component')m[n.id]=n;}});return Object.values(m);}
function compTarget(c,sid){const imp=out(c.id,'impacts').map(e=>byId[e.to]).find(n=>n&&n.type==='screen');if(imp)return imp;
  const tr=out(sid,'transitions_to').map(e=>byId[e.to]).find(Boolean);return tr||null;}
function navTo(sid){if(byId[sid]&&byId[sid].type==='screen'){curScreen=sid;renderPreview();const v=document.getElementById('v-preview');if(v)v.scrollTop=0;}}
function openPreview(sid){curScreen=sid;activate('preview');renderPreview();}
const APP_TABS=[['screen.s_02','홈'],['screen.s_06','장바구니'],['screen.s_09','주문'],['screen.s_14a','마이']];
function compFaux(c){const k=(c.payload.kind||'');
  if(k==='navigation')return '<div class="navrow"><i></i><i></i><i></i></div>';
  if(k==='control')return '<div class="pills"><span></span><span></span><span></span></div>';
  if(k==='form')return (c.payload.required||['입력 1','입력 2']).map(f=>`<div class="fin"><label>${esc(f)}</label><span class="box"></span></div>`).join('');
  if(k==='display')return '<div class="bar"></div><div class="bar w60"></div>';
  if(k==='panel')return '<div class="line"></div><div class="line"></div>';
  return '<div class="bar"></div>';}
function renderPreview(){
  const s=byId[curScreen]; const host=document.getElementById('v-preview'); if(!s){host.innerHTML='';return;}
  const sf=surfaceOf(curScreen); const sfid=sf?sf.id:'';
  const isApp = sfid==='surface.customer_app'||sfid==='surface.public';
  const order=['surface.customer_app','surface.cs_console','surface.hq_admin','surface.public'];
  const index=order.map(oid=>{const sff=byId[oid];if(!sff)return'';
    const scr=out(oid,'contains').map(e=>byId[e.to]).filter(n=>n&&n.type==='screen');
    return `<div class="ixg"><div class="ixh">${esc(cleanName(sff)||sff.name)}</div>${scr.map(n=>`<a class="ixi ${n.id===curScreen?'on':''}" onclick="navTo('${n.id}')"><b>${esc(n.payload.code)}</b>${esc(cleanName(n))}</a>`).join('')}</div>`;}).join('');
  const actor=byId[s.payload.primary_actor];
  const comps=compsOf(curScreen);
  const apis=out(curScreen,'calls').map(e=>byId[e.to]).filter(Boolean);
  const showDM=new Set(),inDM=new Set();
  apis.forEach(a=>{out(a.id,'reads').forEach(e=>showDM.add(e.to));out(a.id,'writes').forEach(e=>inDM.add(e.to));});
  const trans=out(curScreen,'transitions_to').map(e=>byId[e.to]).filter(Boolean);
  const compBlock=c=>{const t=compTarget(c,curScreen);const cl=t?`onclick="navTo('${t.id}')" style="cursor:pointer"`:'';
    return `<div class="wb" ${cl}><h4>${esc(cleanName(c))}${c.payload.reusable?'<span class="reuse">재사용</span>':''}${t?`<span class="goto">→ ${esc(t.payload.code)}</span>`:''}</h4>${compFaux(c)}</div>`;};
  // mode-aware data panel (designer: 예시값 / developer: 타입·필수·enum)
  const dataPanel=(id,kind)=>{const m=byId[id];if(!m)return'';const fields=m.payload.fields||[];const enums=m.payload.enums||{};
    const lim=mode==='developer'?9:6;
    const rows=fields.map((f,i)=>{const pf=parseField(f);const ev=enums[pf.name];const ty=typeOf(m,pf);const req=isReq(pf.note,pf.name);const hc=i>=lim?' ff-hide':'';
      if(mode==='developer')return `<div class="ff click dev${hc}" onclick="fieldInfo('${id}',${i})"><code>${esc(pf.name)}</code><span class="ty">${ty}${req?'<span class="req">*</span>':''}${ev?' · enum('+ev.length+')':''}</span></div>`;
      return `<div class="ff click${hc}" onclick="fieldInfo('${id}',${i})"><span>${esc(pf.name)}</span><em>${esc(exampleOf(m,pf,ev,ty))}</em></div>`;}).join('');
    const hidden=fields.length-lim;
    const more=hidden>0?`<div class="moref" onclick="var w=this.closest('.wb');var on=w.classList.toggle('expanded');this.textContent=on?'접기 ▲':'+ ${hidden}개 필드 더 보기 ▼';">+ ${hidden}개 필드 더 보기 ▼</div>`:'';
    let jsonEx='';
    if(mode==='developer'){
      if(kind==='입력'){const api=apis.find(a=>a.payload.method!=='GET'&&out(a.id,'writes').some(e=>e.to===id));
        const hdr=api?`${api.payload.method} ${api.payload.path}`:'요청 본문';
        jsonEx=`<div class="reqlbl">API 요청 예시 · ${esc(hdr)}</div><pre class="reqjson">${esc(jsonBody(m))}</pre>`;}
      else {const api=apis.find(a=>a.payload.method==='GET'&&out(a.id,'reads').some(e=>e.to===id));
        const hdr=api?`${api.payload.method} ${api.payload.path}`:'응답 본문';
        jsonEx=`<div class="reqlbl">API 응답 예시 · ${esc(hdr)}</div><pre class="reqjson">${esc(jsonBody(m))}</pre>`;}
    }
    return `<div class="wb"><h4>${esc(m.name)}<span class="badge${kind==='입력'?' in':''}">${kind}</span></h4>${rows}${more}${jsonEx}</div>`;};
  let content=comps.filter(c=>c.payload.kind!=='navigation').map(compBlock).join('');
  [...showDM].slice(0,5).forEach(id=>content+=dataPanel(id,'표시'));
  [...inDM].slice(0,4).forEach(id=>content+=dataPanel(id,'입력'));
  const actions=trans.map(t=>`<div class="wbtn" onclick="navTo('${t.id}')">${esc(cleanName(t))} <span style="opacity:.7">→ ${esc(t.payload.code)}</span></div>`).join('');
  let frame;
  if(isApp){
    frame=`<div class="device phone"><div class="scr">
      <div class="appbar"><span class="code">${esc(s.payload.code)}</span>${esc(cleanName(s))}<span class="who">${actor?esc(cleanName(actor)):''}</span></div>
      <div class="scrbody">${content||'<div class="empty">정의된 컴포넌트/데이터 없음</div>'}${actions?`<div class="actions">${actions}</div>`:''}</div>
      <div class="tabbar">${APP_TABS.map(([id,l])=>`<a class="${id===curScreen?'on':''}" onclick="navTo('${id}')">${l}</a>`).join('')}</div>
    </div></div>`;
  }else{
    const siblings=out(sfid,'contains').map(e=>byId[e.to]).filter(n=>n&&n.type==='screen');
    const side=siblings.map(n=>`<a class="${n.id===curScreen?'on':''}" onclick="navTo('${n.id}')"><b>${esc(n.payload.code)}</b>${esc(cleanName(n))}</a>`).join('');
    frame=`<div class="device desktop"><div class="scr desk">
      <div class="adside"><div class="adlogo">${sfid==='surface.hq_admin'?'본사 어드민':'CS 콘솔'}</div>${side}</div>
      <div class="adcontent"><div class="appbar light"><span class="code">${esc(s.payload.code)}</span>${esc(cleanName(s))}<span class="who">${actor?esc(cleanName(actor)):''}</span></div>
        <div class="scrbody grid2">${content||'<div class="empty">—</div>'}</div>
        ${actions?`<div class="actions" style="display:flex;flex-wrap:wrap;gap:6px">${actions}</div>`:''}
      </div></div></div>`;
  }
  // right inspector: 필드 상세 + 전이(API·state) + 액션 API
  const actApis=apis.filter(a=>a.payload.method!=='GET');
  const transHtml=trans.map(t=>{const load=out(t.id,'calls').map(e=>byId[e.to]).filter(a=>a&&a.payload.method==='GET');
    const params=pathParams(t);
    return `<div class="tr"><div class="trh" onclick="navTo('${t.id}')">→ ${esc(t.payload.code)} ${esc(cleanName(t))}</div>
      <div class="kv2">진입 시 호출 API${load.length?'':' 없음'}${load.map(a=>`<span class="api">${a.payload.method} ${esc(a.payload.path)}</span>`).join('')}</div>
      <div class="kv2">넘기는 state(props): ${params.length?params.map(p=>`<span class="st">${esc(PARAM_LABEL[p]||p)}</span>`).join(''):'<span style="opacity:.6">없음(전역 컨텍스트)</span>'}</div>
    </div>`;}).join('');
  const placeholder=mode==='designer'
    ?'데이터(필드)를 클릭하면 <b>무슨 값인지·어떻게 대입하는지</b>가 여기 나옵니다.'
    :'필드를 클릭하면 <b>타입·필수 여부·enum 보기</b>를 확인할 수 있습니다.';
  const side=`<div class="pvside">
    <h5 class="first">필드 상세 <span style="text-transform:none;color:${mode==='designer'?'#2dd4bf':'#a78bfa'}">· ${mode==='designer'?'디자이너':'개발자'} 모드</span></h5>
    <div id="fieldDetail"><div class="kv2" style="color:var(--mut)">${placeholder}</div></div>
    <h5>화면 전이 · 데이터 전달</h5>
    ${transHtml||'<div class="kv2">전이 없음 (종단 화면)</div>'}
    <h5>이 화면 처리(액션) API</h5>
    ${actApis.length?actApis.map(a=>`<div class="api" style="font-family:ui-monospace,monospace;font-size:10.5px;color:#a78bfa;margin:3px 0">${a.payload.method} ${esc(a.payload.path)}</div>`).join(''):'<div class="kv2">조회 전용(GET)</div>'}
  </div>`;
  host.innerHTML=`<div class="pv"><div class="pvindex">${index}</div>
    <div class="pvstage">
      <div class="pvtop"><div class="seg"><button class="${mode==='designer'?'on':''}" onclick="setMode('designer')">디자이너</button><button class="${mode==='developer'?'on':''}" onclick="setMode('developer')">개발자</button></div>
        <span class="modedesc">${mode==='designer'?'데이터 예시와 대입 방법을 봅니다':'타입·필수·enum 스키마를 봅니다'} · 컴포넌트/버튼 클릭 → 화면 이동</span></div>
      <div class="pvmeta">${usageBar([curScreen,...comps.map(c=>c.id),...apis.map(a=>a.id),...showDM,...inDM,...trans.map(t=>t.id)].filter(Boolean))}</div>
      ${frame}
    </div>
    ${side}
  </div>`;
}

/* ============================== tabs / wiring ============================== */
const TABS=[['preview','화면 미리보기'],['graph','IA 그래프 (편집)'],['req','요구사항정의서'],['erd','ERD'],['screens','화면명세서']];
function activate(key){
  TABS.forEach(([k])=>{document.getElementById('v-'+k).classList.toggle('on',k===key);
    document.querySelector('#tab-'+k).classList.toggle('on',k===key);});
  graphActive=(key==='graph');
  if(graphActive){resize();}
}
function renderAll(){renderPreview();renderReq();renderErd();renderScreens();}
const tabsEl=document.getElementById('tabs');
TABS.forEach(([k,label])=>{const b=document.createElement('button');b.id='tab-'+k;b.textContent=label;b.onclick=()=>activate(k);tabsEl.appendChild(b);});
document.getElementById('exportBtn').onclick=()=>{const blob=new Blob([JSON.stringify(DOC,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='koom_ia.edited.json';a.click();};
document.getElementById('restoreBtn').onclick=()=>{DOC=JSON.parse(ORIGINAL);DOC.nodes.forEach((n,i)=>{const a=i/DOC.nodes.length*6.28;n.x=Math.cos(a)*340;n.y=Math.sin(a)*340;n.vx=0;n.vy=0;});rebuild();renderAll();sel=null;document.getElementById('editor').classList.remove('show');document.getElementById('dirty').classList.remove('show');};
document.getElementById('glegend').innerHTML=Object.keys(TYPE_LABEL).map(t=>`<span style="margin-right:9px"><span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:${TYPE_COLOR[t]}"></span> ${TYPE_LABEL[t]}</span>`).join('');

renderAll(); activate('preview'); resize(); loop();
</script></body></html>"""
# 한글 라벨/가이드/파라미터 라벨은 모두 IA(koom_ia.json)에 저장됨 — 렌더러는 읽기만 함.
HTML = HTML.replace("__DATA__", data_json)
outp = os.path.join(here, "koom_ia_docs.html")
open(outp, "w", encoding="utf-8").write(HTML)
print("wrote", outp, round(len(HTML)/1024), "KB")
