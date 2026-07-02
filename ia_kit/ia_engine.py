# -*- coding: utf-8 -*-
"""
ia_engine.py — 프로젝트 IA(정보구조) 그래프를 만드는 재사용 엔진.

개념: IA = Node/Edge 그래프가 '단일 진실원천'. 요구사항정의서·ERD·화면명세서·
화면 미리보기는 모두 이 그래프의 '투영(projection)'으로 렌더된다(build_docs.py).

이 엔진은 그래프를 손쉽게 author 하고, 렌더러(build_docs.py)가 그대로 읽을 수 있는
JSON(`<project_id>_ia.json`)을 만들어 준다. 화면에 보이는 모든 한글 라벨/예시/타입은
전부 IA(JSON)에 저장된다 — 렌더러는 도메인 지식을 갖지 않는다.

사용법은 build_ia.py(템플릿) 참고. 핵심:
    ia = IA("myproj", "내 프로젝트", "한 줄 설명")
    ia.surface("surface.app", "고객 앱", "설명", device="phone")
    ia.actor("actor.user", "사용자", role="user", desc="...", operates="surface.app")
    ia.data_model("dm.order","Order","주문", fields=[
        F("order_number","string", req=True, ex="ORD-20260629-0001", note="unique"),
        F("status","enum", req=True, enum={"pending":"대기","paid":"결제완료"}, ex="paid",
          guide=("주문 상태","PATCH /status/ 로 갱신")),
    ])
    ia.api("api.create_order","POST","/api/orders/", app="orders", actors=["user"],
           summary="주문 생성", writes=["dm.order"])
    ia.screen("screen.s1","S-1","주문하기","surface.app","actor.user","주문 생성",
              requirements=["FR-ORD-01"], apis=["api.create_order"], transitions=["screen.s2"])
    ia.finalize(__file__)
"""
import json, os, re

# ---- 필드 스펙 헬퍼 --------------------------------------------------------
def F(name, type="string", req=False, ex=None, note="", enum=None, guide=None):
    """data_model 의 필드 하나를 정의.
    type: string|number|enum|datetime|date|boolean|url|email|array/json
    enum: {코드:한글라벨, ...} (type='enum' 일 때)
    ex  : 예시값. enum 이면 '코드' 하나. array/json 이면 파이썬 list/dict 또는 JSON 문자열.
    guide: (무엇인지, 어떻게 대입하는지) 튜플  또는  {"what":..,"howto":..}
    """
    return {"name": name, "type": type, "req": req, "ex": ex, "note": note,
            "enum": enum or {}, "guide": guide}

def R(effect, roles, targets):
    """화면 접근 제어 규칙 하나 (screen access=[...] 에 사용).
    effect : 'hide' | 'disable' | 'readonly' | 'mask'
    roles  : 적용 대상 액터 id 목록  (예: ['actor.guest','actor.user'])
    targets: 'self'(화면 전체) | 컴포넌트 id 'comp.x' | 필드 'dm.x.field' | 모델 'dm.x'
    예) R('hide', ['actor.user'], ['dm.order.price_dk_burden','comp.admin_panel'])
    """
    return {"effect": effect, "roles": list(roles), "targets": list(targets)}

# 표준 노드 타입(참고): screen component actor data_model api business_rule
#   validation permission context state_machine state surface project

class IA:
    def __init__(self, project_id, name, description, sources=None,
                 today="2026-01-01T00:00:00+09:00"):
        self.pid = project_id
        self.today = today
        self.nodes, self.edges = [], []
        self._ids, self._path = set(), {}
        self.param_labels = {  # 경로 파라미터 → 한글 (필요시 .param_labels.update())
            "id": "리소스 ID", "pk": "리소스 ID",
        }
        self.projections = [
            {"name": "User Flow", "derive": "screen + transitions_to"},
            {"name": "ERD", "derive": "data_model + belongs_to/reads/writes"},
            {"name": "화면명세서", "derive": "screen + calls + reads/writes + transitions_to"},
            {"name": "요구사항정의서", "derive": "screen.requirements + business_rule + validation"},
        ]
        self.sources = sources or []
        self._warn = []
        self._access_refs = []
        self.root = f"project.{project_id}"
        self._node(self.root, "project", name, "seed",
                   {"description": description}, path=project_id)
        # 표준(구조) 서피스 자동 생성
        self._std = {}
        for sid, nm, desc in [
            ("surface.actors", "액터", "시스템 사용 주체"),
            ("surface.data", "데이터 모델", "도메인 객체"),
            ("surface.api", "API", "엔드포인트 계약"),
            ("surface.rules", "비즈니스 규칙", "정책"),
            ("surface.validations", "검증 규칙", "입력 검증"),
            ("surface.contexts", "컨텍스트", "설계 근거"),
            ("surface.states", "상태 머신", "상태/전이"),
        ]:
            self._node(sid, "surface", nm, "seed", {"description": desc}, parent=self.root)
            self._std[sid] = True
        self._api_apps = set()

    # ---- 저수준 -----------------------------------------------------------
    def _node(self, nid, ntype, name, origin, payload=None, parent=None, path=None, short=None):
        assert nid not in self._ids, f"중복 노드 id: {nid}"
        self._ids.add(nid)
        if path is None:
            short = short or nid.split(".")[-1]
            ppath = self._path.get(parent, self.pid)
            path = f"{ppath}/{short}"
        self._path[nid] = path
        self.nodes.append({
            "id": nid, "project_id": self.pid, "type": ntype, "name": name,
            "path": path, "origin_context": origin, "payload": payload or {},
            "version": 1, "schema_version": 1,
            "created_at": self.today, "updated_at": self.today,
        })
        if parent:
            self.edge(parent, nid, "contains")
        return nid

    def edge(self, frm, to, rel, meta=None):
        e = {"from": frm, "to": to, "relation": rel}
        if meta: e["metadata"] = meta
        self.edges.append(e)

    # ---- 컨테이너 / 액터 --------------------------------------------------
    def surface(self, sid, name, desc, device="desktop"):
        """UI 표면(화면 묶음). device='phone' 이면 미리보기에서 폰 프레임."""
        return self._node(sid, "surface", name, "seed",
                          {"description": desc, "form_factor": device}, parent=self.root)

    def actor(self, aid, name, role="user", desc="", operates=None, origin="seed"):
        self._node(aid, "actor", name, origin, {"role": role, "description": desc},
                   parent="surface.actors")
        if operates:
            self.edge(aid, operates, "operates")
        return aid

    # ---- 데이터 모델 ------------------------------------------------------
    def data_model(self, did, name, desc, fields=None, belongs_to=None, status=None, origin="seed"):
        pay = self._dm_payload(desc, fields or [], status, did)
        self._node(did, "data_model", name, origin, pay, parent="surface.data", short=name)
        for tgt in (belongs_to or []):
            self.edge(did, tgt if isinstance(tgt, str) else tgt[0],
                      "belongs_to", None if isinstance(tgt, str) else tgt[1])
        return did

    def _dm_payload(self, desc, fields, status, did):
        pay = {"description": desc}
        flist, enums, elabels, ftypes, fex, fguide = [], {}, {}, {}, {}, {}
        for f in fields:
            n, t = f["name"], f["type"]
            note = f.get("note", "")
            if f.get("req") and not re.search(r"필수|unique|PK|FK|upsert", note):
                note = (note + " 필수").strip()
            flist.append(n + (f"({note})" if note else ""))
            ftypes[n] = t
            ex = f.get("ex")
            if t == "enum":
                en = f.get("enum") or {}
                codes = list(en.keys())
                if not codes:
                    self._warn.append(f"{did}.{n}: enum 라벨 없음")
                enums[n] = codes
                elabels[n] = dict(en)
                for c, lab in en.items():
                    if not lab:
                        self._warn.append(f"{did}.{n}={c}: 라벨 비어있음")
                if ex is None:
                    ex = codes[0] if codes else ""
                fex[n] = en.get(ex, ex)            # 화면엔 라벨, JSON엔 코드(렌더러가 역매핑)
                guide_ex = f"{en.get(ex, ex)} ({ex})"
            else:
                if t == "array/json" and not isinstance(ex, str):
                    ex = json.dumps(ex, ensure_ascii=False) if ex is not None else "[]"
                if ex is None:
                    ex = ""
                    self._warn.append(f"{did}.{n}: 예시값 없음(빈 문자열)")
                fex[n] = ex
                guide_ex = ex
            g = f.get("guide")
            if g:
                if isinstance(g, (list, tuple)):
                    fguide[n] = {"what": g[0], "howto": g[1] if len(g) > 1 else "", "example": guide_ex}
                elif isinstance(g, dict):
                    fguide[n] = {"what": g.get("what", ""), "howto": g.get("howto", ""), "example": guide_ex}
        pay["fields"] = flist
        if enums:
            pay["enums"] = enums
            pay["enum_labels"] = elabels
        pay["field_types"] = ftypes
        pay["field_examples"] = fex
        if fguide:
            pay["field_guide"] = fguide
        if status:
            pay["status"] = status
        return pay

    # ---- API --------------------------------------------------------------
    def api(self, aid, method, path, app="general", actors=None, summary="",
            reads=None, writes=None, depends_on=None, origin="seed"):
        sub = f"surface.api.{app}"
        if sub not in self._api_apps:
            self._node(sub, "surface", f"/api/{app}", "seed", {"app": app}, parent="surface.api")
            self._api_apps.add(sub)
        self._node(aid, "api", f"{method} {path}", origin,
                   {"method": method, "path": path, "app": app, "summary": summary,
                    "actor_permissions": actors or []},
                   parent=sub, short=aid.split(".")[-1])
        for d in (reads or []):  self.edge(aid, d, "reads")
        for d in (writes or []): self.edge(aid, d, "writes")
        for d in (depends_on or []): self.edge(aid, d, "depends_on")
        return aid

    # ---- 화면 / 컴포넌트 --------------------------------------------------
    def screen(self, sid, code, name, surface, actor=None, purpose="", requirements=None,
               apis=None, transitions=None, proto=None, context=None, access=None, origin="seed"):
        pay = {"code": code, "purpose": purpose, "primary_actor": actor,
               "requirements": requirements or [], "status": "implemented"}
        if proto: pay["prototype_page"] = proto
        if access:                       # UI 접근 제어 정책(역할별 hide/disable/readonly/mask)
            pay["access"] = access
            for r in access:
                for t in r.get("targets", []):
                    if t.startswith("comp.") or t.startswith("dm."):
                        self._access_refs.append((sid, t.split(".")[0] + "." + t.split(".")[1]))
                for role in r.get("roles", []):
                    self._access_refs.append((sid, role))
        self._node(sid, "screen", f"{code} · {name}", origin, pay, parent=surface, short=code)
        for ap in (apis or []):
            self.edge(sid, ap, "calls")
        for t in (transitions or []):     # 노드 미생성이어도 OK(finalize에서 검증)
            self.edge(sid, t, "transitions_to")
        if context:
            self.edge(sid, context, "mentioned_in")
        return sid

    def component(self, cid, name, home_screen, impacts=None, payload=None, origin="seed"):
        self._node(cid, "component", name, origin, payload or {}, parent=home_screen,
                   short=cid.split(".")[-1])
        for s in (impacts or []):
            self.edge(cid, s, "impacts", {"reuse": "재사용"})
        return cid

    # ---- 규칙 / 검증 / 권한 / 컨텍스트 ------------------------------------
    def business_rule(self, rid, name, desc, priority="🟡", derived_from=None, governs=None, origin="seed"):
        self._node(rid, "business_rule", name, origin, {"priority": priority, "description": desc},
                   parent="surface.rules")
        for c in (derived_from or []):
            self.edge(rid, c, "derived_from")
        for g in (governs or []):
            self.edge(g, rid, "governed_by")
        return rid

    def validation(self, vid, name, condition, message="", code="", targets=None, origin="seed"):
        self._node(vid, "validation", name, origin,
                   {"condition": condition, "message": message, "error_code": code},
                   parent="surface.validations")
        for t in (targets or []):
            self.edge(t, vid, "validated_by")
        return vid

    def context(self, cid, name, source_type="PRD", desc="", origin="seed"):
        self._node(cid, "context", name, origin, {"source_type": source_type, "description": desc},
                   parent="surface.contexts")
        if cid not in self.sources:
            self.sources.append(cid)
        return cid

    def state_machine(self, mid, name, desc, states, transitions=None, owner=None, origin="seed"):
        """states: [(state_id, 한글라벨), ...]  transitions: [(from_id, to_id, meta?), ...]"""
        self._node(mid, "state_machine", name, origin, {"description": desc}, parent="surface.states")
        for sid, label in states:
            self._node(sid, "state", label, origin, {"machine": mid}, parent=mid,
                       short=sid.split(".")[-1])
        for tr in (transitions or []):
            a, b = tr[0], tr[1]; meta = tr[2] if len(tr) > 2 else None
            self.edge(a, b, "transitions_to", meta)
        if owner:
            self.edge(owner, mid, "governed_by", {"note": "상태 머신"})
        return mid

    # ---- 마무리 -----------------------------------------------------------
    def finalize(self, script_file, out_dir=None):
        counts, rels = {}, {}
        for n in self.nodes:
            counts[n["type"]] = counts.get(n["type"], 0) + 1
        for e in self.edges:
            rels[e["relation"]] = rels.get(e["relation"], 0) + 1
        doc = {
            "schema": "ia-graph/1.0",
            "generated_at": self.today,
            "project": {
                "id": self.pid,
                "name": self.nodes[0]["name"],
                "description": self.nodes[0]["payload"].get("description", ""),
                "backbone_relation": "contains",
                "node_types": sorted(counts), "edge_relations": sorted(rels),
                "sources": self.sources,
            },
            "stats": {"nodes": len(self.nodes), "edges": len(self.edges),
                      "by_node_type": counts, "by_relation": rels},
            "glossary": {
                "note": ("화면에 쓰이는 한글 라벨·예시·타입은 전부 IA에 저장됨 "
                         "(data_model payload.enum_labels/field_examples/field_types/field_guide, "
                         "param_labels). 렌더러는 도메인 지식을 갖지 않음."),
                "param_labels": self.param_labels,
            },
            "projections": self.projections,
            "nodes": self.nodes, "edges": self.edges,
        }
        # 무결성: dangling edge
        ids = set(n["id"] for n in self.nodes)
        dangling = [(e["from"], e["to"], e["relation"]) for e in self.edges
                    if e["from"] not in ids or e["to"] not in ids]
        bad_access = sorted(set(f"{sid}→{ref}" for sid, ref in self._access_refs if ref not in ids))
        out_dir = out_dir or os.path.dirname(os.path.abspath(script_file))
        out = os.path.join(out_dir, f"{self.pid}_ia.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"nodes={len(self.nodes)} edges={len(self.edges)} -> {out}")
        print("by type:", counts)
        if dangling:
            print("WARNING dangling edges (대상 노드 없음):", dangling[:20], "..." if len(dangling) > 20 else "")
        else:
            print("integrity OK: 모든 엣지 양끝 노드 존재")
        if self._warn:
            print("WARNING 라벨/예시 누락:", self._warn[:20], "..." if len(self._warn) > 20 else "")
        else:
            print("integrity OK: 모든 enum 라벨 / 필드 예시·타입 존재")
        if bad_access:
            print("WARNING access 규칙이 없는 노드를 가리킴:", bad_access[:20])
        else:
            print("integrity OK: 모든 access 규칙 대상(액터/컴포넌트/모델) 존재")
        return out
