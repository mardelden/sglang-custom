"""A/B the Anthropic streaming adapter on real model output, with no restart.

Runs on any SGLang host with the serving venv; installs nothing. The adapter is
a pure converter over the OpenAI chat stream, so real streams captured once from
the loaded model can be replayed through any adapter version.

    # 1. capture real multi-tool streams from the running engine
    python ab_adapter.py capture --url http://127.0.0.1:30000 --out /tmp/caps.json
    # 2. replay through the INSTALLED adapter
    python ab_adapter.py convert /tmp/caps.json
    # 3. replay through a PATCHED tree (e.g. the overlay branch's python/ dir)
    PYTHONPATH=/tmp/patched/python python ab_adapter.py convert /tmp/caps.json

A tool call whose streamed input is not valid JSON is what Claude Code rejects.
"""

import argparse
import asyncio
import json
import logging
import sys
import urllib.request
from types import SimpleNamespace

TOOLS = [
    {"name": "Read", "description": "Read a file",
     "parameters": {"type": "object", "required": ["file_path"],
                    "properties": {"file_path": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "Bash", "description": "Run a shell command",
     "parameters": {"type": "object", "required": ["command"],
                    "properties": {"command": {"type": "string"}, "description": {"type": "string"}}}},
    {"name": "Grep", "description": "Search file contents",
     "parameters": {"type": "object", "required": ["pattern"],
                    "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}}},
]
PROMPTS = [
    "First tell me in one sentence what you will do, then read /etc/hostname and also list /tmp with ls. Use the tools.",
    'Read /etc/os-release, grep for "root" in /etc/passwd, and run uname -a. Call all three tools now.',
    "Check disk usage with df -h and read /proc/meminfo with limit 5, in parallel.",
]


def capture(url, out, n):
    tools = [{"type": "function", "function": t} for t in TOOLS]
    caps = []
    for i in range(n):
        body = json.dumps({"model": "x", "stream": True, "max_tokens": 2000, "tools": tools,
                           "messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}]}).encode()
        req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            lines = [raw.decode().strip() + "\n\n" for raw in r if raw.decode().strip().startswith("data:")]
        caps.append(lines)
        print(f"capture {i}: {len(lines)} SSE lines", flush=True)
    json.dump(caps, open(out, "w"))


class _ReplayChat:
    """Stands in for OpenAIServingChat: replays captured SSE lines."""

    def __init__(self, lines):
        self.lines = lines
        self.tokenizer_manager = SimpleNamespace(tokenizer=SimpleNamespace(chat_template=None))

    def _generate_chat_stream(self, adapted_request, processed_request, raw_request):
        async def gen():
            for line in self.lines:
                yield line
        return gen()

    def apply_reasoning_enabled(self, chat_request, enabled):
        pass

    def wrap_reasoning_history(self, text):
        return text


def convert(path):
    logging.disable(logging.WARNING)
    try:
        from sglang.test.test_utils import maybe_stub_sgl_kernel
        maybe_stub_sgl_kernel()
    except ImportError:
        pass
    import sglang.srt.entrypoints.anthropic.serving as mod
    from sglang.srt.entrypoints.anthropic.protocol import AnthropicMessagesRequest

    req = AnthropicMessagesRequest.model_validate(
        {"model": "x", "max_tokens": 16, "stream": True, "messages": [{"role": "user", "content": "hi"}]})
    print(f"adapter: {mod.__file__}")

    async def collect(lines):
        events = []
        serving = mod.AnthropicServing(_ReplayChat(lines))
        async for sse in serving._generate_anthropic_stream(
                adapted_request=object(), processed_request=object(),
                anthropic_request=req, raw_request=object()):
            events += [json.loads(l[6:]) for l in sse.splitlines() if l.startswith("data: ")]
        return events

    calls = bad = 0
    for i, lines in enumerate(json.load(open(path))):
        blocks, order = {}, []
        for e in asyncio.run(collect(lines)):
            if e["type"] == "content_block_start":
                order.append(e["content_block"]["type"])
                if e["content_block"]["type"] == "tool_use":
                    blocks[e["index"]] = ""
            elif e["type"] == "content_block_delta" and e["delta"].get("type") == "input_json_delta":
                blocks[e["index"]] += e["delta"]["partial_json"]
        verdicts = []
        for idx in sorted(blocks):
            try:
                json.loads(blocks[idx])
                verdicts.append("ok")
            except ValueError:
                verdicts.append("BAD:" + blocks[idx][-25:])
        calls += len(verdicts)
        bad += sum(v != "ok" for v in verdicts)
        print(f"stream {i}: blocks={order} tool_inputs={verdicts}")
    print(f"TOTAL: {bad}/{calls} tool calls with invalid JSON")
    return 1 if bad else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--url", default="http://127.0.0.1:30000")
    c.add_argument("--out", required=True)
    c.add_argument("-n", type=int, default=6)
    v = sub.add_parser("convert")
    v.add_argument("captures")
    a = p.parse_args()
    if a.cmd == "capture":
        capture(a.url, a.out, a.n)
    else:
        sys.exit(convert(a.captures))
