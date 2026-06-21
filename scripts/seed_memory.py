#!/usr/bin/env python3
"""
seed_memory.py — Pre-load the `memory` server's knowledge graph with durable
facts about the user and this setup, so the local model starts out informed.

The memory server stores newline-delimited JSON (JSONL): each line is either
  {"type":"entity",  "name":..., "entityType":..., "observations":[...]}
  {"type":"relation","from":..., "to":..., "relationType":...}

This script is idempotent: re-running merges observations (union) and avoids
duplicate entities/relations. It NEVER stores secrets.

Usage:
    uv run python scripts/seed_memory.py
    MEMORY_FILE_PATH=/path/to/.agent-memory.json uv run python scripts/seed_memory.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEMORY_FILE = Path(os.environ.get("MEMORY_FILE_PATH", str(REPO / ".agent-memory.json")))

# --- Facts to seed (edit freely; no secrets) -------------------------------- #
ENTITIES = [
    {
        "name": "priyansh19",
        "entityType": "Person",
        "observations": [
            "Git author name is priyansh19",
            "Git commit email is guptapriyansh1907@gmail.com",
            "GitHub login is priyansh19",
            "Works on macOS",
            "Prefers running LLMs locally via LM Studio",
            "Is building an autonomous local coding agent",
        ],
    },
    {
        "name": "lmstudio-agent-mcp",
        "entityType": "Project",
        "observations": [
            "Local MCP toolkit that gives LM Studio models coding powers",
            "Located at ~/Desktop/lmstudio-agent-mcp",
            "Sandbox root for the agent is ~/Desktop",
            "Custom servers: coding-tools, web-tools, docker-tools, github-watch",
            "Community servers: codebase-memory, memory, sequential-thinking, git, time, context7, playwright, github",
            "Web: playwright (browser) + web-tools (search); fetch MCP removed (playwright covers pages)",
            "Setup is re-run via ./install.sh",
            "GitHub token lives in the macOS keychain and in ~/.lmstudio/mcp.json (never store the token value itself)",
        ],
    },
    {
        "name": "LM Studio",
        "entityType": "Tool",
        "observations": [
            "Local LLM runtime with an OpenAI-compatible server and MCP support",
            "MCP config file is at ~/.lmstudio/mcp.json",
            "Start server with: lms server start",
        ],
    },
]

RELATIONS = [
    {"from": "priyansh19", "to": "lmstudio-agent-mcp", "relationType": "owns"},
    {"from": "lmstudio-agent-mcp", "to": "LM Studio", "relationType": "runs on"},
    {"from": "priyansh19", "to": "LM Studio", "relationType": "uses"},
]


def _load(path: Path) -> tuple[dict, list]:
    entities: dict[str, dict] = {}
    relations: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "entity":
                entities[obj["name"]] = obj
            elif obj.get("type") == "relation":
                relations.append(obj)
    return entities, relations


def main() -> None:
    entities, relations = _load(MEMORY_FILE)

    for ent in ENTITIES:
        existing = entities.get(ent["name"])
        if existing:
            merged = list(dict.fromkeys(existing.get("observations", []) + ent["observations"]))
            existing["observations"] = merged
            existing["entityType"] = ent["entityType"]
        else:
            entities[ent["name"]] = {"type": "entity", **ent}

    def rel_key(r: dict) -> tuple:
        return (r["from"], r["to"], r["relationType"])

    have = {rel_key(r) for r in relations}
    for rel in RELATIONS:
        if rel_key(rel) not in have:
            relations.append({"type": "relation", **rel})
            have.add(rel_key(rel))

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "entity", **{k: v for k, v in e.items() if k != "type"}})
             for e in entities.values()]
    lines += [json.dumps(r if r.get("type") else {"type": "relation", **r}) for r in relations]
    MEMORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Seeded {len(entities)} entities and {len(relations)} relations -> {MEMORY_FILE}")


if __name__ == "__main__":
    main()
