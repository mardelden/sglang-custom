"""Post-deploy check of a live SGLang endpoint's Anthropic /v1/messages stream.

Sends Claude-Code-shaped multi-tool requests and reassembles every tool_use
block's streamed input. Exit 1 if any input is not valid JSON.

    python verify_live.py --url http://127.0.0.1:30000

Pair it with the journal: after the restart there must be no new
"Dropping tool_call argument delta" warnings, e.g.
    journalctl -u sglang --since @<restart-epoch> | grep -c 'Dropping tool_call argument delta'
"""

import argparse
import json
import sys
import urllib.request

TOOLS = [
    {"name": "Read", "description": "Read a file",
     "input_schema": {"type": "object", "required": ["file_path"],
                      "properties": {"file_path": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "Bash", "description": "Run a shell command",
     "input_schema": {"type": "object", "required": ["command"],
                      "properties": {"command": {"type": "string"}, "description": {"type": "string"}}}},
    {"name": "Grep", "description": "Search file contents",
     "input_schema": {"type": "object", "required": ["pattern"],
                      "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}}},
]
PROMPTS = [
    "First tell me in one sentence what you will do, then read /etc/hostname and also list /tmp with ls. Use the tools.",
    'Read /etc/os-release, grep for "root" in /etc/passwd, and run uname -a. Call all three tools now.',
    "Check disk usage with df -h and read /proc/meminfo with limit 5, in parallel.",
]
HEADERS = {"Content-Type": "application/json", "x-api-key": "x", "anthropic-version": "2023-06-01"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://127.0.0.1:30000")
    p.add_argument("-n", type=int, default=6)
    a = p.parse_args()

    calls = bad = multi = 0
    cache_seen = False
    for i in range(a.n):
        body = json.dumps({"model": "x", "max_tokens": 2000, "stream": True, "tools": TOOLS,
                           "messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}]}).encode()
        req = urllib.request.Request(a.url.rstrip("/") + "/v1/messages", data=body, headers=HEADERS)
        blocks, order = {}, []
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                e = json.loads(line[5:])
                t = e.get("type")
                if t == "content_block_start":
                    order.append(e["content_block"]["type"])
                    if e["content_block"]["type"] == "tool_use":
                        blocks[e["index"]] = ""
                elif t == "content_block_delta" and e["delta"].get("type") == "input_json_delta":
                    blocks[e["index"]] += e["delta"]["partial_json"]
                for usage in (e.get("usage"), (e.get("message") or {}).get("usage")):
                    if isinstance(usage, dict) and "cache_read_input_tokens" in usage:
                        cache_seen = True
        verdicts = []
        for idx in sorted(blocks):
            try:
                json.loads(blocks[idx])
                verdicts.append("ok")
            except ValueError:
                verdicts.append("BAD:" + blocks[idx][-25:])
        calls += len(verdicts)
        bad += sum(v != "ok" for v in verdicts)
        multi += len(verdicts) > 1
        print(f"stream {i}: blocks={order} tool_inputs={verdicts}", flush=True)
    print(f"TOTAL: {bad}/{calls} tool calls invalid JSON; {multi}/{a.n} streams multi-tool; "
          f"cache_read_input_tokens reported: {cache_seen}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
