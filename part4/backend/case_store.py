"""
Case store: loads the case's evidence once and answers questions with plain code.
Nothing in this file calls an AI model. The agent can only see what these functions return,
and every record it returns carries a `ref` (like "txn:UPI-123") that the agent must cite.
"""
import json
import math
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # TrueTrail/
def _pick_case_dir():
    """Use the case investigators uploaded (data/runtime/canonical) if it exists, else Jaya's synthetic case."""
    cands = [os.getenv("TT_CASE_DIR"), REPO / "data" / "runtime" / "canonical", REPO / "data" / "canonical"]
    for c in cands:
        if c and (Path(c) / "transactions.json").exists():
            return Path(c)
    for c in cands:
        if c and Path(c).exists() and any(Path(c).glob("*.json")):
            return Path(c)
    return REPO / "data" / "canonical"


CASE_DIR = _pick_case_dir()
FRONT = REPO / "part4" / "frontend" / "src"
DB_PATH = Path(os.getenv("TT_NOTES_DB", HERE / "case_notes.db"))

# Heuristic thresholds (same as the dashboard graph)
MIN_FLOW = 100_000
MIN_PASSTHROUGH = 0.8
HANDLER_WINDOW_S = 600


def _load(name, *fallbacks):
    for p in (CASE_DIR / name, *fallbacks):
        if Path(p).exists():
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
    return []


def _load_from_forensics_db(case_id=None, include_all=True):
    db_file = HERE / "data" / "forensics.db"
    if not db_file.exists():
        return [], [], [], []
    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        if include_all or not case_id:
            ev_rows = conn.execute(
                "SELECT evidence_id, filename, evidence_type, sha256, record_count, ingested_at FROM evidence_items"
            ).fetchall()
            txns = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM transactions").fetchall()]
            calls = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM call_records").fetchall()]
            ips = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM ip_sessions").fetchall()]
        else:
            ev_rows = conn.execute(
                "SELECT evidence_id, filename, evidence_type, sha256, record_count, ingested_at FROM evidence_items WHERE case_id = ?",
                (case_id,),
            ).fetchall()
            ev_ids = [r["evidence_id"] for r in ev_rows]
            if not ev_ids:
                return [], [], [], []
            ph = ",".join("?" for _ in ev_ids)
            txns = [json.loads(r[0]) for r in conn.execute(f"SELECT payload_json FROM transactions WHERE evidence_id IN ({ph})", ev_ids).fetchall()]
            calls = [json.loads(r[0]) for r in conn.execute(f"SELECT payload_json FROM call_records WHERE evidence_id IN ({ph})", ev_ids).fetchall()]
            ips = [json.loads(r[0]) for r in conn.execute(f"SELECT payload_json FROM ip_sessions WHERE evidence_id IN ({ph})", ev_ids).fetchall()]
        evidence = [dict(r) for r in ev_rows]
    return txns, calls, ips, evidence


def parse_ts(s, end_of_day=False):
    """ISO string -> aware UTC datetime. Accepts '2026-03-14', '2026-03-14T05:40', '...Z'."""
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    if end_of_day and len(s) == 10:
        d = d.replace(hour=23, minute=59, second=59)
    return d


def inr(n):
    return "₹" + f"{round(n):,}"


class CaseStore:
    def __init__(self, case_id=None, include_all=True):
        txns, calls, ips, evidence = _load_from_forensics_db(case_id=case_id, include_all=include_all)
        self.txns = txns or (_load("transactions.json", FRONT / "transactions.json") if include_all else [])
        self.calls = calls or (_load("calls.json") if include_all else [])
        self.ips = ips or (_load("ip_sessions.json") if include_all else [])
        self.evidence = evidence or (_load("evidence_items.json") if include_all else [])
        self.scores = {}
        for p in (os.getenv("TT_SCORES", ""), FRONT / "engineScores.json"):
            if p and Path(p).exists():
                self.scores = json.loads(Path(p).read_text(encoding="utf-8-sig"))
                break
        self._init_db()
        self._index()

    # ------------------------------------------------------------------ notes (workspace)
    def _init_db(self):
        with sqlite3.connect(DB_PATH) as c:
            c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, author TEXT, entity TEXT, text TEXT)")

    def add_note(self, author, text, entity=None):
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute("INSERT INTO notes (ts, author, entity, text) VALUES (?,?,?,?)",
                            (datetime.now(timezone.utc).isoformat(timespec="seconds"), author, entity, text))
            return cur.lastrowid

    def list_notes(self, entity=None):
        with sqlite3.connect(DB_PATH) as c:
            q, a = "SELECT id, ts, author, entity, text FROM notes", ()
            if entity:
                q, a = q + " WHERE entity = ? OR text LIKE ?", (entity, f"%{entity}%")
            rows = c.execute(q + " ORDER BY id", a).fetchall()
        return [{"ref": f"note:{r[0]}", "time": r[1], "author": r[2], "entity": r[3], "text": r[4]} for r in rows]

    # ------------------------------------------------------------------ indexing
    def _index(self):
        ok = [t for t in self.txns if t.get("status") == "SUCCESS"]
        self.vpa_to_acct, self.names, self.phone_to_acct = {}, {}, {}
        for t in ok:
            for s in ("sender", "receiver"):
                a, v, n = t.get(s + "_account"), t.get(s + "_vpa"), t.get(s + "_name")
                if a and v:
                    self.vpa_to_acct[v] = a
                if a and n:
                    self.names.setdefault(a, n)
            if t.get("sender_account") and t.get("sender_mobile"):
                self.phone_to_acct.setdefault(t["sender_mobile"], t["sender_account"])
        self.nodes, self.edges = {}, {}
        for t in ok:
            s, r = self.acct(t, "sender"), self.acct(t, "receiver")
            ts = parse_ts(t["timestamp"])
            if s and r:
                a, b = self._node(s, t.get("sender_name")), self._node(r, t.get("receiver_name"))
                a["out_sum"] += t["amount"]; a["out_cnt"] += 1
                b["in_sum"] += t["amount"]; b["in_cnt"] += 1
                b["in_times"].append(ts)
                a["first_out"] = min(a["first_out"], ts) if a["first_out"] else ts
                if t.get("device_id"): a["devices"][t["device_id"]] += 1
                if t.get("ip_address"): a["ips"][t["ip_address"]] += 1
                if t.get("sender_mobile"): a["phones"][t["sender_mobile"]] += 1
                e = self.edges.setdefault((s, r), {"source": s, "target": r, "total": 0, "count": 0, "txns": [], "first": ts, "last": ts})
                e["total"] += t["amount"]; e["count"] += 1; e["txns"].append(t)
                e["first"], e["last"] = min(e["first"], ts), max(e["last"], ts)
            elif r:
                self._node(r, t.get("receiver_name"))["cash_in"] += t["amount"]
            elif s:
                self._node(s, t.get("sender_name"))["cash_out"] += t["amount"]
        for n in self.nodes.values():
            hi, lo = max(n["in_sum"], n["out_sum"]), min(n["in_sum"], n["out_sum"])
            n["passthrough"] = lo / hi if hi else 0
            n["role"] = "other"
            if lo >= MIN_FLOW and n["passthrough"] >= MIN_PASSTHROUGH: n["role"] = "mule"
            elif n["out_sum"] >= MIN_FLOW and n["out_sum"] >= 3 * n["in_sum"]: n["role"] = "source"
            elif n["in_sum"] >= MIN_FLOW and n["in_sum"] >= 3 * n["out_sum"]: n["role"] = "terminal"
            sc = self.scores.get(n["id"], {})
            n["risk"], n["reasons"] = sc.get("risk"), sc.get("reasons", [])
        self.flagged = {i for i, n in self.nodes.items() if n["role"] != "other"}
        self.call_by_id = {c["record_id"]: c for c in self.calls}
        self.ip_by_id = {c["record_id"]: c for c in self.ips}
        self.txn_by_id = {t["txn_id"]: t for t in self.txns}
        self.ev_by_id = {e["evidence_id"]: e for e in self.evidence}

    def acct(self, t, side):
        return t.get(side + "_account") or (t.get(side + "_vpa") and self.vpa_to_acct.get(t[side + "_vpa"])) or t.get(side + "_vpa")

    def _node(self, i, name=None):
        if i not in self.nodes:
            self.nodes[i] = {"id": i, "name": self.names.get(i) or name or i, "in_sum": 0, "out_sum": 0, "in_cnt": 0, "out_cnt": 0,
                             "cash_in": 0, "cash_out": 0, "first_out": None, "in_times": [], "devices": Counter(), "ips": Counter(), "phones": Counter()}
        return self.nodes[i]

    def name(self, i):
        return self.nodes.get(i, {}).get("name") or self.names.get(i) or i

    def phone_of(self, node):
        return node["phones"].most_common(1)[0][0] if node["phones"] else None

    def resolve(self, q):
        """account number / UPI id / phone / (part of) a name -> (account_id, error)"""
        if not q:
            return None, "no account given"
        q = str(q).strip()
        if q in self.nodes: return q, None
        if q in self.vpa_to_acct: return self.vpa_to_acct[q], None
        if q in self.phone_to_acct: return self.phone_to_acct[q], None
        hits = [i for i, n in self.nodes.items() if q.lower() in n["name"].lower()]
        if len(hits) == 1: return hits[0], None
        if hits: return None, "ambiguous: " + ", ".join(f"{self.name(h)} ({h})" for h in hits[:8])
        return None, f"no account matches '{q}'"

    # ------------------------------------------------------------------ record helpers
    def _txn_row(self, t):
        s, r = self.acct(t, "sender"), self.acct(t, "receiver")
        return {"ref": "txn:" + t["txn_id"], "time": t["timestamp"], "amount": t["amount"], "channel": t.get("channel"),
                "status": t.get("status"),
                "from": {"account": s, "name": self.name(s) if s else None},
                "to": {"account": r, "name": self.name(r) if r else None},
                "remarks": t.get("narration") or t.get("remarks")}

    def _party(self, phone):
        a = self.phone_to_acct.get(phone)
        return {"number": phone, "name": self.name(a) if a else None}

    def _call_row(self, c):
        return {"ref": "call:" + c["record_id"], "time": c["start_time"], "duration_s": c.get("duration_sec"),
                "from": self._party(c["caller"]), "to": self._party(c["callee"]), "tower": c.get("tower_address")}

    # ------------------------------------------------------------------ tools
    def search_transactions(self, account=None, counterparty=None, min_amount=None, max_amount=None,
                            start=None, end=None, channel=None, limit=25):
        a = c = None
        if account:
            a, err = self.resolve(account)
            if err: return {"error": err}
        if counterparty:
            c, err = self.resolve(counterparty)
            if err: return {"error": err}
        num = lambda v: float(v) if v not in (None, "") else None   # some models send numbers as text
        min_amount, max_amount = num(min_amount), num(max_amount)
        t0, t1 = parse_ts(start), parse_ts(end, end_of_day=True)
        out = []
        for t in self.txns:
            s, r = self.acct(t, "sender"), self.acct(t, "receiver")
            if a and a not in (s, r): continue
            if c and c not in (s, r): continue
            if min_amount is not None and t["amount"] < min_amount: continue
            if max_amount is not None and t["amount"] > max_amount: continue
            if channel and (t.get("channel") or "").upper() != channel.upper(): continue
            ts = parse_ts(t["timestamp"])
            if t0 and ts < t0: continue
            if t1 and ts > t1: continue
            out.append(t)
        out.sort(key=lambda t: t["timestamp"])
        limit = min(int(limit or 25), 50)
        total = sum(t["amount"] for t in out if t.get("status") == "SUCCESS")
        return {"matched": len(out), "total_amount_successful": total, "returned": min(len(out), limit),
                "records": [self._txn_row(t) for t in out[:limit]]}

    def account_summary(self, account):
        i, err = self.resolve(account)
        if err: return {"error": err}
        n = self.nodes[i]
        top = lambda items: [{"account": k, "name": self.name(k), "total": round(v), "count": cnt}
                             for k, v, cnt in sorted(items, key=lambda x: -x[1])[:5]]
        outs = [(e["target"], e["total"], e["count"]) for (s, _), e in self.edges.items() if s == i]
        ins = [(e["source"], e["total"], e["count"]) for (_, r), e in self.edges.items() if r == i]
        label = {"mule": "mule-like pass-through pattern (heuristic)", "source": "main source of outgoing funds (heuristic)",
                 "terminal": "end point where funds accumulate (heuristic)", "other": "no suspicious pattern detected by the heuristic"}[n["role"]]
        return {"ref": "acct:" + i, "name": n["name"], "account": i, "phones": list(n["phones"]),
                "received": {"total": round(n["in_sum"]), "count": n["in_cnt"]}, "sent": {"total": round(n["out_sum"]), "count": n["out_cnt"]},
                "cash_deposits_total": round(n["cash_in"]), "cash_withdrawals_total": round(n["cash_out"]),
                "pass_through_ratio": round(n["passthrough"], 2), "heuristic_pattern": label,
                "ml_engine_risk": n["risk"], "ml_engine_reasons": n["reasons"],
                "devices_used": list(n["devices"]), "ips_used": list(n["ips"]),
                "top_incoming": top(ins), "top_outgoing": top(outs)}

    def find_suspicious_accounts(self):
        order = self._chain_order()
        rows = []
        for i in order:
            n = self.nodes[i]
            rows.append({"ref": "acct:" + i, "name": n["name"], "account": i, "pattern": n["role"],
                         "received": round(n["in_sum"]), "sent": round(n["out_sum"]), "pass_through_ratio": round(n["passthrough"], 2),
                         "ml_engine_risk": n["risk"]})
        return {"rule": f"flagged when an account moves at least {inr(MIN_FLOW)} and forwards at least {int(MIN_PASSTHROUGH*100)}% of what it receives (heuristic, not proof)",
                "count": len(rows), "accounts_in_chain_order": rows}

    def _chain_order(self):
        src = [i for i in self.flagged if self.nodes[i]["role"] == "source"]
        order, seen = [], set()
        cur = src[0] if src else None
        while cur and cur not in seen:
            order.append(cur); seen.add(cur)
            nxt = [e for (s, _), e in self.edges.items() if s == cur and e["target"] in self.flagged and e["target"] not in seen]
            cur = max(nxt, key=lambda e: e["total"])["target"] if nxt else None
        return order + [i for i in self.flagged if i not in seen]

    def trace_funds(self, start_account, max_hops=10):
        cur, err = self.resolve(start_account)
        if err: return {"error": err}
        hops, seen = [], {cur}
        for _ in range(min(int(max_hops or 10), 15)):
            outs = [e for (s, _), e in self.edges.items() if s == cur and e["target"] not in seen]
            if not outs: break
            e = max(outs, key=lambda e: e["total"])
            if hops and e["total"] < 0.1 * hops[-1]["total"]:
                break  # the money stopped here; what follows is unrelated small payments
            hops.append({"from": {"account": cur, "name": self.name(cur)}, "to": {"account": e["target"], "name": self.name(e["target"])},
                         "total": round(e["total"]), "count": e["count"], "first": e["first"].isoformat(), "last": e["last"].isoformat(),
                         "transactions": [{"ref": "txn:" + t["txn_id"], "time": t["timestamp"], "amount": t["amount"]} for t in sorted(e["txns"], key=lambda t: t["timestamp"])]})
            cur = e["target"]; seen.add(cur)
        if not hops: return {"hops": [], "note": "no outgoing transfers between known accounts"}
        return {"rule": "follows the largest outgoing transfer from each account and stops when the next transfer is under 10% of the previous one", "hops": hops,
                "entered": hops[0]["total"], "reached_end": hops[-1]["total"], "end_account": hops[-1]["to"]}

    def find_handler(self):
        mules = [self.nodes[i] for i in self.flagged if self.nodes[i]["role"] == "mule" and self.phone_of(self.nodes[i])]
        mine = {self.phone_of(m) for m in mules}
        hits = defaultdict(lambda: defaultdict(list))
        for c in self.calls:
            if c.get("direction") != "OUT" or c["caller"] in mine: continue
            m = next((m for m in mules if self.phone_of(m) == c["callee"]), None)
            if not m: continue
            ts = parse_ts(c["start_time"])
            if any(0 <= (ts - t).total_seconds() <= HANDLER_WINDOW_S for t in m["in_times"]):
                hits[c["caller"]][m["id"]].append(c)
        need = max(3, math.ceil(0.6 * len(mules)))
        best = max(((p, d) for p, d in hits.items() if len(d) >= need), key=lambda x: len(x[1]), default=None)
        if not best:
            return {"handler_found": False, "rule": f"a phone that calls at least {need} flagged accounts within {HANDLER_WINDOW_S//60} min after each received money"}
        phone, d = best
        return {"handler_found": True, "phone": phone, "appears_in_payments": phone in self.phone_to_acct,
                "rule": f"phone that called {len(d)} of {len(mules)} flagged accounts within {HANDLER_WINDOW_S//60} min after money arrived (a pattern, not proof of identity)",
                "calls_by_account": [{"account": i, "name": self.name(i), "calls": [self._call_row(c) for c in sorted(cs, key=lambda c: c["start_time"])]} for i, cs in d.items()]}

    def shared_identifiers(self):
        groups = []
        for kind, key in (("device", "devices"), ("ip", "ips")):
            m = defaultdict(set)
            for i, n in self.nodes.items():
                for v in n[key]: m[v].add(i)
            for v, accts in m.items():
                if len(accts) >= 2:
                    ev = [{"ref": "txn:" + t["txn_id"], "time": t["timestamp"], "account": self.acct(t, "sender")}
                          for t in self.txns if self.acct(t, "sender") in accts and t.get("device_id" if kind == "device" else "ip_address") == v][:6]
                    groups.append({"kind": kind, "value": v, "accounts": [{"account": a, "name": self.name(a)} for a in sorted(accts)],
                                   "involves_flagged_accounts": sum(a in self.flagged for a in accts), "example_transactions": ev})
        groups.sort(key=lambda g: -g["involves_flagged_accounts"])
        return {"count": len(groups), "groups": groups[:10]}

    def case_timeline(self, start=None, end=None, kinds=None, limit=40):
        kinds = set(kinds or ["txn", "call", "ip"])
        t0, t1 = parse_ts(start), parse_ts(end, end_of_day=True)
        ev = []
        if "txn" in kinds:
            for t in self.txns:
                r = self._txn_row(t)
                who = f"{r['from']['name'] or 'unknown'} → {r['to']['name'] or 'cash/external'}"
                ev.append((t["timestamp"], {"ref": r["ref"], "time": t["timestamp"], "kind": "payment", "summary": f"{inr(t['amount'])} {t.get('channel')} {who} ({t.get('status')})"}))
        if "call" in kinds:
            for c in self.calls:
                if c.get("direction") != "OUT": continue
                r = self._call_row(c)
                ev.append((c["start_time"], {"ref": r["ref"], "time": c["start_time"], "kind": "call",
                                            "summary": f"call {r['from']['name'] or r['from']['number']} → {r['to']['name'] or r['to']['number']}, {c.get('duration_sec')} s"}))
        if "ip" in kinds:
            for s in self.ips:
                ev.append((s["start_time"], {"ref": "ip:" + s["record_id"], "time": s["start_time"], "kind": "ip_session",
                                            "summary": f"IP session {s['msisdn']} {s['src_ip']} → {s['dst_ip']}:{s['dst_port']}"}))
        ev = [e for e in sorted(ev, key=lambda x: x[0]) if (not t0 or parse_ts(e[0]) >= t0) and (not t1 or parse_ts(e[0]) <= t1)]
        limit = min(int(limit or 40), 60)
        return {"matched": len(ev), "returned": min(len(ev), limit), "events": [e[1] for e in ev[:limit]]}

    def search_calls(self, party, start=None, end=None, limit=25):
        nums = set()
        if str(party).startswith("+"): nums.add(party)
        else:
            i, err = self.resolve(party)
            if err: return {"error": err}
            nums = set(self.nodes[i]["phones"])
            if not nums: return {"error": f"no phone number is known for {self.name(i)}"}
        t0, t1 = parse_ts(start), parse_ts(end, end_of_day=True)
        rows = [c for c in self.calls if c.get("direction") == "OUT" and (c["caller"] in nums or c["callee"] in nums)
                and (not t0 or parse_ts(c["start_time"]) >= t0) and (not t1 or parse_ts(c["start_time"]) <= t1)]
        rows.sort(key=lambda c: c["start_time"]); limit = min(int(limit or 25), 50)
        return {"matched": len(rows), "returned": min(len(rows), limit), "records": [self._call_row(c) for c in rows[:limit]]}

    def tool_list_notes(self, entity=None):
        n = self.list_notes(entity)
        return {"count": len(n), "notes": n, "reminder": "these are investigators' opinions, not evidence"}

    def list_evidence(self):
        return {"count": len(self.evidence), "items": [{"ref": "ev:" + e["evidence_id"], "file": e["filename"], "type": e["evidence_type"],
                "sha256": e["sha256"][:16] + "…", "records": e["record_count"], "ingested_at": e["ingested_at"]} for e in self.evidence]}

    # ------------------------------------------------------------------ citation lookup
    def lookup(self, ref):
        kind, _, i = ref.partition(":")
        if kind == "txn": return self.txn_by_id.get(i)
        if kind == "call": return self.call_by_id.get(i)
        if kind == "ip": return self.ip_by_id.get(i)
        if kind == "ev": return self.ev_by_id.get(i)
        if kind == "acct": return self.account_summary(i) if i in self.nodes else None
        if kind == "note": return next((n for n in self.list_notes() if n["ref"] == ref), None)
        return None

    def stats(self):
        return {"case_dir": str(CASE_DIR), "transactions": len(self.txns), "calls": len(self.calls), "ip_sessions": len(self.ips), "evidence_items": len(self.evidence),
                "accounts": len(self.nodes), "flagged": len(self.flagged), "ml_scores_loaded": bool(self.scores)}


def store(case_id=None, include_all=True):
    return CaseStore(case_id=case_id, include_all=include_all)