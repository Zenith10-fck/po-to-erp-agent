"""The only place that talks to a model.

`ClaudeCliClient` calls the Claude Code CLI in print mode (`claude -p`) on the user's own
subscription: no API key. Each call runs in a folder that holds only the page images of one
document, with only the `Read` tool, in restricted mode. The model cannot run code, write
files or reach the network, whatever a document tells it.

`FakeClient` replays stored answers for the offline tests. Its output is never a result.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"   # not the WSL bash, which drops env vars


@dataclass
class ModelResult:
    ok: bool
    output: dict | None = None
    error: str | None = None
    seconds: float = 0.0
    cost_usd: float | None = None      # API-equivalent cost reported by the CLI
    model: list[str] = field(default_factory=list)

    def meta(self) -> dict:
        return {"ok": self.ok, "error": self.error, "seconds": round(self.seconds, 1),
                "cost_usd": self.cost_usd, "model": self.model}


class ModelClient(Protocol):
    def ask(self, kind: str, doc_id: str, workdir: Path, system: str, user: str, schema: dict) -> ModelResult: ...


def check_schema(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Small JSON-schema check for the subset docs/*.schema.json uses. The CLI already enforces
    the schema; this is the second lock, because model output is untrusted."""
    root = root or schema
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    errs: list[str] = []
    types = schema.get("type")
    types = [types] if isinstance(types, str) else (types or [])
    py = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if types:
        ok = any(
            (t == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (t in py and isinstance(value, py[t]))
            for t in types
        )
        if not ok:
            return [f"{path}: expected {'/'.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: not one of {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: missing")
        if schema.get("additionalProperties") is False:
            errs += [f"{path}.{k}: not allowed" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                errs += check_schema(value[k], sub, root, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs += check_schema(item, schema["items"], root, f"{path}[{i}]")
    return errs


def inline_refs(schema: dict) -> dict:
    """Replace every $ref with its definition, so the CLI gets a flat schema."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                merged = dict(walk(defs[node["$ref"].split("/")[-1]]))
                merged.update({k: walk(v) for k, v in node.items() if k != "$ref"})
                return merged
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "$schema", "title")}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


class ClaudeCliClient:
    def __init__(self, model: str = "sonnet", timeout: int = 600, retries: int = 1):
        self.model = model
        self.timeout = timeout
        self.retries = retries

    def ask(self, kind, doc_id, workdir, system, user, schema) -> ModelResult:
        last = ModelResult(ok=False, error="not run")
        for _ in range(self.retries + 1):
            last = self._once(workdir, system, user, schema)
            if last.ok:
                break
        return last

    def _once(self, workdir: Path, system: str, user: str, schema: dict) -> ModelResult:
        cmd = [GIT_BASH if os.path.exists(GIT_BASH) else "bash", "-c",
               'claude -p --output-format json --model "$PO_MODEL" --system-prompt "$PO_SYSTEM" '
               '--restricted --safe-mode --tools "Read" --allowedTools "Read" --strict-mcp-config '
               '--no-session-persistence --json-schema "$PO_SCHEMA"']
        env = dict(os.environ, PO_MODEL=self.model, PO_SYSTEM=system,
                   PO_SCHEMA=json.dumps(inline_refs(schema)))
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=workdir, env=env, input=user, capture_output=True,
                               text=True, timeout=self.timeout, encoding="utf-8")
        except subprocess.TimeoutExpired:
            return ModelResult(ok=False, error="timeout", seconds=time.time() - t0)
        res = ModelResult(ok=False, seconds=time.time() - t0)
        try:
            data = json.loads(p.stdout)
        except Exception:
            res.error = ("no JSON from CLI: " + (p.stderr or p.stdout or ""))[:300]
            return res
        res.cost_usd = data.get("total_cost_usd")
        res.model = list((data.get("modelUsage") or {}).keys())
        out = data.get("structured_output")
        if out is None:
            try:
                out = json.loads(data.get("result") or "")
            except Exception:
                res.error = "no structured output: " + str(data.get("result"))[:200]
                return res
        errs = check_schema(out, schema)
        if errs:
            res.error = "schema: " + "; ".join(errs[:5])
            res.output = out
            return res
        res.ok, res.output = True, out
        return res


class FakeClient:
    """Replays answers: {(kind, doc_id): dict}. `extract2` falls back to `extract`."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def ask(self, kind, doc_id, workdir, system, user, schema) -> ModelResult:
        self.calls.append((kind, doc_id))
        out = self.answers.get((kind, doc_id))
        if out is None and kind == "extract2":
            out = self.answers.get(("extract", doc_id))
        if out is None:
            return ModelResult(ok=False, error="no fixture")
        errs = check_schema(out, schema)
        if errs:
            return ModelResult(ok=False, output=out, error="schema: " + "; ".join(errs[:5]))
        return ModelResult(ok=True, output=out, model=["fake"])
