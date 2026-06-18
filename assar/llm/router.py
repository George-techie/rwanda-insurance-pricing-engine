"""Query router + synthesizer.

Flow for a free-text query:
  1. Retrieve relevant prose chunks (always — cheap, grounds the answer).
  2. Ask the LLM, exposing the pricing tools. If it emits tool calls we execute
     them deterministically (assar.pricing) and capture the quotes.
  3. Synthesize a final answer from the prose context + any quote results,
     instructed to cite manual pages and show the exact rates used.

Everything degrades gracefully: no LLM key -> return retrieved prose with a note;
LLM error -> surface it without crashing the UI. The structured "Get a Quote"
tab in the app bypasses this entirely and calls the calculators directly, so the
pricing demo works regardless of LLM availability.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..pricing.registry import TOOL_SCHEMAS, run_tool
from ..rag.retriever import get_retriever
from .client import get_client

# A quote needs a figure (sum insured / limit / value) or an explicit pricing
# word. Coverage/definition questions have neither — for those we don't expose
# the pricing tools at all, so a small model can't make a spurious tool call.
_QUOTE_CUES = re.compile(
    r"\b(rate|premium|cost|costs|how much|quote|price|pricing|charge|"
    r"sum insured|insured value|limit of indemnity|per mille)\b|\d", re.I)
_CONCEPT_CUES = re.compile(
    r"\b(cover|covers|covered|coverage|exclud|exclusion|definition|define|"
    r"mean|meaning|differ|difference|warrant|condition|what is|what are|"
    r"explain|describe|tell me about|how does|included)\b", re.I)


def _offer_tools(query: str) -> bool:
    """True if the pricing tools should be exposed for this question."""
    if _QUOTE_CUES.search(query):
        return True
    if _CONCEPT_CUES.search(query):
        return False
    return True

SYSTEM_PROMPT = """You are a pricing assistant for the Rwandan insurance market, \
grounded in ASSAR's Approved General Business Pricing Manual (Version 3).

SCOPE: This manual covers GENERAL (non-life) business only — fire, liability, \
transit, marine, aviation, engineering, bonds, PA/GPA, PVT, etc. It does NOT \
cover MOTOR/vehicle, LIFE, or MEDICAL/health insurance. If asked about those, \
say they are outside this manual's scope and do not call a pricing tool or \
invent a rate.

Rules:
- Call a pricing tool ONLY to compute a premium/quote/rate for a SPECIFIC risk \
with a sum insured, limit, or value. For questions about what a cover \
includes or excludes, definitions, conditions, warranties, or how a cover \
works, answer ONLY from the manual excerpts and do NOT call any tool.
- When you do compute a premium, CALL a pricing tool. Never do the arithmetic \
yourself and never invent a rate — the tools read exact rates from the manual.
- Call tools ONLY by their exact provided names (e.g. quote_fidelity, \
quote_marine_hull). Never invent or rename a tool.
- Pass numeric arguments as numbers (e.g. 1000000), not strings.
- PVT (Political Violence & Terrorism) rates are quoted PER MILLE, every other \
class is percent. The tools already handle this; never override it.
- When you explain a rule, definition, warranty or exclusion, base it on the \
provided manual excerpts and cite the page (e.g. "(p.11)").
- Be concise and show the rate(s) and figures actually used. If a rate or \
category is not in the manual, say so rather than guessing.
- These figures must be verified against the source manual before binding cover."""


@dataclass
class RouterResult:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)   # [{name, args, result}]
    retrieved: list[dict] = field(default_factory=list)    # [{text, page, score}]
    backend: str = ""
    error: str | None = None


def _format_context(chunks: list[dict]) -> str:
    blocks = []
    for c in chunks:
        blocks.append(f"[p.{c['page']}] {c['text']}")
    return "\n\n".join(blocks)


def answer_query(query: str, k: int = 4, history: list[tuple[str, str]] | None = None) -> RouterResult:
    retriever = get_retriever()
    retrieved: list[dict] = []
    if retriever.available:
        try:
            retrieved = retriever.search(query, k=k)
        except Exception as exc:  # noqa: BLE001
            retrieved = []
            ctx_err = str(exc)
    client = get_client()
    result = RouterResult(answer="", retrieved=retrieved, backend=client.config.backend)

    if not client.ready:
        # No model configured — still useful: hand back the grounded prose.
        if retrieved:
            ctx = _format_context(retrieved)
            result.answer = (
                "No LLM backend is configured, so here are the most relevant "
                "passages from the manual:\n\n" + ctx
            )
        else:
            result.answer = (
                "No LLM backend is configured and the vector store has not been "
                "built yet. Set GROQ_API_KEY (or LLM_BACKEND=ollama) and run "
                "`python -m assar.ingest`."
            )
        result.error = "llm_not_ready"
        return result

    context = _format_context(retrieved) if retrieved else "(no prose retrieved)"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Prior conversation turns (text only) so follow-ups keep context, e.g.
    # "and for a hotel?" after a fire question. Cap to the last few turns.
    for role, content in (history or [])[-6:]:
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({
        "role": "user",
        "content": f"Manual excerpts:\n{context}\n\nQuestion: {query}",
    })

    tools = TOOL_SCHEMAS if _offer_tools(query) else None
    try:
        msg = client.chat(messages, tools=tools, tool_choice="auto")
    except Exception as exc:  # noqa: BLE001
        result.error = f"LLM call failed: {exc}"
        result.answer = (
            "The language model call failed. The deterministic 'Get a Quote' tab "
            "still works. Error: " + str(exc)
        )
        return result

    # Execute any tool calls deterministically.
    tool_messages = []
    if getattr(msg, "tool_calls", None):
        # Record the assistant turn that requested the tools.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            quote = run_tool(name, args)
            result.tool_calls.append({"name": name, "args": args, "result": quote})
            tool_messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(quote)}
            )
        messages.extend(tool_messages)

        # Second pass: synthesize a final answer from the tool results + prose.
        try:
            final = client.chat(messages, tools=None)
            result.answer = final.content or ""
        except Exception as exc:  # noqa: BLE001
            result.error = f"Synthesis failed: {exc}"
            # Fall back to a plain rendering of the quote(s).
            result.answer = _render_quotes(result.tool_calls)
    else:
        result.answer = msg.content or ""

    return result


def _render_quotes(tool_calls: list[dict]) -> str:
    out = []
    for tc in tool_calls:
        r = tc["result"]
        if "error" in r:
            out.append(f"- {tc['name']}: error — {r['error']}")
            continue
        out.append(
            f"**{r['product']}** — final premium **Rwf{r['final_premium']:,.0f}** "
            f"(rate {r['rate']} {r.get('rate_unit', 'percent')})"
        )
        for line in r.get("breakdown", []):
            out.append(f"  - {line}")
    return "\n".join(out)
