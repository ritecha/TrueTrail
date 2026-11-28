"""
Grounded case assistant.
The model (Grok, through xAI's OpenAI-compatible API) never sees the case files directly. It can only call the
tools below, every record they return has a `ref`, and the answer is rejected unless every ref it cites was
actually returned by a tool in this conversation turn.
"""
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from case_store import store

try:  # optional: load XAI_API_KEY from a .env file next to this file
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# Any OpenAI-compatible provider works. Defaults are Groq's free tier (no card needed).
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("XAI_BASE_URL") or "https://api.groq.com/openai/v1"
MODEL = os.getenv("LLM_MODEL") or os.getenv("XAI_MODEL") or "llama-3.3-70b-versatile"  # check the provider's model list
MAX_STEPS = 8
REF_RE = re.compile(r"\[((?:txn|call|ip|acct|note|ev):[^\]\s]+)\]")
NOT_FOUND = "not in the case data"

SYSTEM_PROMPT = """You are the TrueTrail case assistant. You help investigators who are working on ONE case.

RULES (follow all of them):
1. Answer ONLY from tool results. You know nothing else about this case. Never use outside knowledge, memory or guesses about names, amounts, times, places or relationships.
2. Cite the source of every factual statement with the `ref` exactly as the tool returned it, in square brackets, for example [txn:UPI-123] or [call:ab12cd]. Never invent, shorten or change a ref.
3. Do not calculate anything yourself. Use the totals and counts the tools return. Give times in UTC as they appear.
4. Keep three things apart and say which one you are using:
   - EVIDENCE: records returned by the tools.
   - ANALYSIS: heuristic results from tools (for example "mule-like pattern", "likely handler"). Call them heuristics, not facts.
   - INVESTIGATOR NOTES: what a named investigator wrote. Attribute them ("Investigator X noted...") and never present them as facts.
5. If the tools return nothing relevant, reply that it is "not in the case data" and say what data would be needed. Never fill a gap.
6. If the question is not about this case (general knowledge, other cases, legal advice, programming, personal opinions) or is only a greeting, reply politely and begin your reply with the word OUT_OF_SCOPE. You only answer about this case.
7. A pattern is not proof. Use wording like "consistent with" and say what extra evidence would confirm it.
8. Be concise: start with the direct answer, then the supporting records.
Always call at least one tool before answering a question about the case."""

TOOLS = [
    {"type": "function", "function": {"name": "search_transactions", "description": "Find payments. Filter by account (number, UPI id, phone or name), counterparty, amount range, UTC time range or channel. Returns the total of ALL matches plus up to `limit` records.",
        "parameters": {"type": "object", "properties": {"account": {"type": "string"}, "counterparty": {"type": "string"}, "min_amount": {"type": "number"}, "max_amount": {"type": "number"},
                       "start": {"type": "string", "description": "UTC, e.g. 2026-03-14T05:40"}, "end": {"type": "string"}, "channel": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "account_summary", "description": "Totals, devices, phones, heuristic pattern and ML risk score for one account (number, UPI id, phone or name).",
        "parameters": {"type": "object", "properties": {"account": {"type": "string"}}, "required": ["account"]}}},
    {"type": "function", "function": {"name": "find_suspicious_accounts", "description": "Accounts flagged by the pass-through heuristic, in chain order, with their metrics.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "trace_funds", "description": "Follow the money from an account along the largest outgoing transfers. Returns each hop with its transactions.",
        "parameters": {"type": "object", "properties": {"start_account": {"type": "string"}, "max_hops": {"type": "integer"}}, "required": ["start_account"]}}},
    {"type": "function", "function": {"name": "find_handler", "description": "Looks for a phone that called the flagged accounts shortly after each received money. Returns the phone and the call records.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "shared_identifiers", "description": "Devices or IP addresses used by more than one account.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "case_timeline", "description": "Chronological events (payments, calls, IP sessions) in a UTC time range. Use for 'what happened when' questions.",
        "parameters": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string", "enum": ["txn", "call", "ip"]}}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "search_calls", "description": "Calls made or received by a phone number (starting with +) or by an account/name.",
        "parameters": {"type": "object", "properties": {"party": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["party"]}}},
    {"type": "function", "function": {"name": "list_notes", "description": "Investigators' notes and theories from the workspace, optionally about one entity. These are opinions, not evidence.",
        "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_evidence", "description": "Evidence files uploaded to the case (file name, type, hash, record count).", "parameters": {"type": "object", "properties": {}}}},
]
DISPATCH = {
    "search_transactions": lambda s, **a: s.search_transactions(**a), "account_summary": lambda s, **a: s.account_summary(**a),
    "find_suspicious_accounts": lambda s, **a: s.find_suspicious_accounts(), "trace_funds": lambda s, **a: s.trace_funds(**a),
    "find_handler": lambda s, **a: s.find_handler(), "shared_identifiers": lambda s, **a: s.shared_identifiers(),
    "case_timeline": lambda s, **a: s.case_timeline(**a), "search_calls": lambda s, **a: s.search_calls(**a),
    "list_notes": lambda s, **a: s.tool_list_notes(**a), "list_evidence": lambda s, **a: s.list_evidence(),
}


def _refs_in(obj, acc):
    """collect every `ref` value found in a tool result"""
    if isinstance(obj, dict):
        if isinstance(obj.get("ref"), str):
            acc.add(obj["ref"])
        for v in obj.values():
            _refs_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _refs_in(v, acc)


def _assistant_dict(msg):
    d = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls]
    return d


def make_client():
    if not API_KEY:
        raise HTTPException(503, "LLM_API_KEY is not set. Add it to part4/backend/.env and restart the server.")
    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(503, "The openai package is missing in the Python environment that runs the server. Run: pip install openai python-dotenv")
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def run_agent(question, history=None, investigator="investigator", client=None, ctx=None):
    ctx = ctx or {}
    case_key = ctx.get("case_label") or ctx.get("case_id")
    is_primary = case_key in (None, "c1", "CR-2026-001")
    s = store(case_id=case_key, include_all=is_primary)
    client = client or make_client()
    has_data = bool(ctx.get("has_data", True) or len(s.txns) > 0 or len(s.calls) > 0 or len(s.ips) > 0 or len(s.evidence) > 0)
    notes = [{"ref": f"note:{ctx.get('case_id','x')}-{n.get('id')}", "author": n.get("author"), "text": n.get("text")} for n in ctx.get("notes", [])]
    evid = [{"ref": f"ev:{ctx.get('case_id','x')}-{e.get('id')}", "file": e.get("file"), "sha256": e.get("sha"), "uploaded_by": e.get("by"), "time": e.get("ts")} for e in ctx.get("evidence", [])]
    extra = {"list_notes": lambda **a: {"count": len(notes), "notes": notes, "reminder": "these are investigators' opinions, not evidence"},
             "list_evidence": lambda **a: {"count": len(evid), "items": evid}}
    tools = TOOLS if has_data else [t for t in TOOLS if t["function"]["name"] in extra]

    def lookup(ref):
        for r in notes + evid:
            if r["ref"] == ref:
                return r
        return s.lookup(ref) if has_data else None

    case_line = f"\nCurrent case: {ctx.get('case_label') or ''} {ctx.get('case_name') or ''}. Members: {', '.join(ctx.get('members', [])) or 'unknown'}."
    if not has_data:
        case_line += " This case has NO transaction, call or IP data loaded yet; only investigator notes and uploaded evidence files are available. Say so if asked about money, calls or accounts."
    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\nThe investigator asking is: {investigator}." + case_line}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
    messages.append({"role": "user", "content": question})

    seen, used, corrections, errors = set(), [], 0, 0
    for _ in range(MAX_STEPS):
        try:
            resp = client.chat.completions.create(model=MODEL, messages=messages, tools=tools, temperature=0.1)
        except Exception as e:  # free models sometimes produce a malformed tool call: retry, then explain
            errors += 1
            text = str(e)
            if "429" in text or "rate" in text.lower():
                raise HTTPException(429, "The AI provider's free rate limit was hit. Wait a minute and ask again.")
            if errors <= 2:
                continue
            raise HTTPException(502, f"The AI provider returned an error: {text[:300]}")
        msg = resp.choices[0].message
        messages.append(_assistant_dict(msg))
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    if tc.function.name in extra:
                        result = extra[tc.function.name](**args)
                    else:
                        fn = DISPATCH.get(tc.function.name) if has_data else None
                        result = fn(s, **args) if fn else {"error": "unknown tool"}
                except Exception as e:  # a bad argument must not crash the chat
                    result = {"error": f"tool failed: {e}"}
                used.append(tc.function.name)
                _refs_in(result, seen)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)})
            continue

        answer = (msg.content or "").strip()
        if answer.startswith("OUT_OF_SCOPE") and not used:
            return {"answer": answer.removeprefix("OUT_OF_SCOPE").lstrip(" :.-—\n") or "I can only help with questions about this case.",
                    "verified": True, "citations": [], "tools_used": []}
        cited = list(dict.fromkeys(REF_RE.findall(answer)))
        bad = [c for c in cited if c not in seen or lookup(c) is None]
        problem = None
        if not used:
            problem = "You answered without calling any tool. Call the relevant tools first, then answer only from their results."
        elif bad:
            problem = f"These citations were not returned by the tools in this conversation: {bad}. Rewrite the answer using only refs from tool results, or call the tools that return them."
        if problem and corrections < 2:
            corrections += 1
            messages.append({"role": "user", "content": problem})
            continue
        if problem:
            return {"answer": "I could not produce an answer I can fully verify against the case data, so I am not giving one. Try a more specific question (an account, a phone number or a time range).",
                    "verified": False, "citations": [], "tools_used": used}
        final_refs = cited if cited else list(seen)[:5]
        return {"answer": answer, "verified": True, "tools_used": used,
                "citations": [{"ref": c, "record": rec} for c in final_refs if (rec := lookup(c)) is not None]}
    return {"answer": "I could not finish this question within the allowed number of steps. Please ask something narrower.", "verified": False, "citations": [], "tools_used": used}


# ---------------------------------------------------------------- API
router = APIRouter()


class Chat(BaseModel):
    question: str
    history: list[dict] = []
    investigator: str = "investigator"   # Clerk display name, sent by the frontend
    investigator_id: str | None = None   # Clerk user id
    case_id: str | None = None
    case_label: str | None = None
    case_name: str | None = None
    has_data: bool = False               # True only for the case that has the loaded dataset
    members: list[str] = []
    notes: list[dict] = []
    evidence: list[dict] = []


class NoteIn(BaseModel):
    author: str
    text: str
    entity: str | None = None


@router.post("/agent/chat")
def chat(body: Chat):
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    if not body.case_id:
        raise HTTPException(400, "case_id is required")
    return run_agent(body.question.strip(), body.history, body.investigator, ctx=body.model_dump())


@router.get("/agent/health")
def health():
    return {"model": MODEL, "provider": BASE_URL, "key_configured": bool(API_KEY), "case": store().stats()}


@router.post("/notes")
def add_note(n: NoteIn):
    return {"ref": f"note:{store().add_note(n.author, n.text, n.entity)}"}


@router.get("/notes")
def get_notes(entity: str | None = None):
    return store().list_notes(entity)