"""Offline tests: real case data, scripted (fake) model. Run:  python test_agent.py"""
import json, os, tempfile, types
os.environ.setdefault("TT_NOTES_DB", os.path.join(tempfile.mkdtemp(), "n.db"))
import part4.backend.agent as agent
from part4.backend.case_store import store

S = store()
ok = lambda c, m: print(("PASS  " if c else "FAIL  ") + m) or (c or (_ for _ in ()).throw(SystemExit(1)))

# ---- 1) deterministic tools on the real synthetic case
h = S.find_handler()
ok(h.get("handler_found") and len(h.get("calls_by_account", [])) >= 5 and not h.get("appears_in_payments", False), f"handler found: {h.get('phone', 'None')} via {len(h.get('calls_by_account', []))} accounts, not in payments")
tr = S.trace_funds("Rajesh Kumar Sharma")
ok(len(tr["hops"]) == 7 and tr["entered"] == 290000, f"trace: {len(tr['hops'])} hops, ₹{tr['entered']:,} entered, ₹{tr['reached_end']:,} reached {tr['end_account']['name']}")
fs = S.find_suspicious_accounts(); ok(fs["count"] == 8, f"{fs['count']} flagged accounts")
sh = S.shared_identifiers(); ok(sh["groups"][0]["involves_flagged_accounts"] == 2, f"shared {sh['groups'][0]['kind']} between {[a['name'] for a in sh['groups'][0]['accounts']]}")
m = S.account_summary("Rohan Mehta"); ok(m["pass_through_ratio"] >= 0.9 and m["ml_engine_risk"] is not None, f"account_summary Rohan Mehta: pass-through {m['pass_through_ratio']}, risk {m['ml_engine_risk']}")
tl = S.case_timeline("2026-03-14T05:40", "2026-03-14T06:00", ["txn"]); ok(tl["matched"] > 0 and all(e["ref"].startswith("txn:") for e in tl["events"]), f"timeline 05:40-06:00: {tl['matched']} events")
st = S.search_transactions(account="Rajesh Kumar Sharma", counterparty="Amit Tiwari"); ok(st["matched"] == 3 and st["total_amount_successful"] == 290000, f"search: {st['matched']} payments to Amit Tiwari totalling ₹{st['total_amount_successful']:,}")
ok("error" in S.account_summary("Nobody Here"), "unknown account returns an error, not a guess")
nid = S.add_note("Investigator A", "I think Amit Tiwari is the recruiter", "Amit Tiwari"); ok(S.list_notes("Amit Tiwari")[0]["ref"] == f"note:{nid}", "notes saved and listed with author")

# ---- 2) agent loop with a scripted model
def tc(name, args="{}", i="1"): return types.SimpleNamespace(id=i, function=types.SimpleNamespace(name=name, arguments=args))
def msg(content=None, calls=None): return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content, tool_calls=calls))])
class Fake:
    def __init__(self, script): self.script, self.n = script, 0; self.chat = types.SimpleNamespace(completions=self)
    def create(self, **kw): r = self.script[min(self.n, len(self.script) - 1)]; self.n += 1; return r(kw) if callable(r) else r
ref = h["calls_by_account"][0]["calls"][0]["ref"]

r = agent.run_agent("Who is the handler?", client=Fake([msg(None, [tc("find_handler")]), msg(f"The phone {h['phone']} called the flagged accounts after each deposit (heuristic) [{ref}].")]))
ok(r["verified"] and r["tools_used"] == ["find_handler"] and r["citations"][0]["record"]["record_id"], "good answer: tool called, citation exists, record attached")

r = agent.run_agent("x", client=Fake([msg(None, [tc("find_handler")]), msg("He paid ₹5 lakh [txn:FAKE-123]."), msg(f"Called [{ref}].")]))
ok(r["verified"] and "FAKE" not in r["answer"], "invented citation rejected, model corrected, final answer verified")

r = agent.run_agent("x", client=Fake([msg("The handler is Bob Smith."), msg(None, [tc("find_handler")]), msg(f"See [{ref}].")]))
ok(r["verified"] and r["tools_used"], "answer without tools rejected, model forced to use tools")

r = agent.run_agent("x", client=Fake([msg(None, [tc("find_handler")]), msg("He did it [txn:NOPE].")]))
ok(not r["verified"] and "could not produce" in r["answer"], "persistent hallucination -> refuses instead of showing it")

r = agent.run_agent("x", client=Fake([msg(None, [tc("find_handler")]), msg(f"A citation for another turn [txn:{S.txns[0]['txn_id']}] exists in the case but was never retrieved."), msg(f"[{ref}]")]))
ok(r["verified"] and S.txns[0]["txn_id"] not in r["answer"], "citing a real record that tools did not return this turn is also rejected")

r = agent.run_agent("What's the capital of France?", client=Fake([msg("OUT_OF_SCOPE I can only help with questions about this case.")]))
ok(r["verified"] and r["tools_used"] == [] and "capital" not in r["answer"].lower(), "out-of-scope question politely refused")

r = agent.run_agent("Show amounts", client=Fake([msg(None, [tc("search_transactions", '{"account": "Nobody"}')]), msg("That account is not in the case data.")]))
ok(r["verified"], "'not in the case data' answer accepted without citations")

r = agent.run_agent("x", client=Fake([msg(None, [tc("search_transactions", "not json")]), msg("This is not in the case data.")]))
ok(r["verified"], "malformed tool arguments do not crash the chat")
print("\nAll tests passed")