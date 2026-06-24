"""
procedural_memory.py — Phase 4: load Skill.md procedural memory into system prompt.

Architecture (Architecture_Daigram.excalidraw):
  Procedural Memory (Files, Text) — Skill.md, how to act while interacting with user
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "procedural.json"
DEFAULT_SKILL_NAMES = ("Skill.md", "SKILL.md", "skill.md")


def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "enabled": True,
        "skill_filenames": list(DEFAULT_SKILL_NAMES),
        "skills_dirs": ["skills", "prompts/skills"],
        "include_workspace_skills": True,
    }
    if CONFIG_PATH.is_file():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if not k.startswith("_"):
                cfg[k] = v
    if os.environ.get("PROCEDURAL_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        cfg["enabled"] = False
    if os.environ.get("SKILLS_DIR"):
        cfg["skills_dirs"] = [os.environ["SKILLS_DIR"]]
    return cfg


def _resolve_skill_dirs(workspace: str, cfg: dict[str, Any]) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    for entry in cfg.get("skills_dirs", []):
        p = Path(str(entry).replace("__LMSTUDIO__", str(PROJECT_ROOT)))
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        add(p.expanduser())

    if cfg.get("include_workspace_skills", True):
        ws = Path(workspace).expanduser().resolve()
        add(ws / "skills")
        add(ws / ".skills")

    add(PROJECT_ROOT / "skills")
    return dirs


def discover_skill_files(workspace: str = "") -> list[Path]:
    """Return existing Skill.md files from configured search paths."""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return []

    names = {str(n) for n in cfg.get("skill_filenames", DEFAULT_SKILL_NAMES)}
    found: list[Path] = []
    seen: set[str] = set()

    for directory in _resolve_skill_dirs(workspace, cfg):
        if not directory.is_dir():
            continue
        for name in names:
            path = (directory / name).resolve()
            key = str(path)
            if path.is_file() and key not in seen:
                seen.add(key)
                found.append(path)

        for path in sorted(directory.glob("*.md")):
            if path.name in names:
                continue
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                found.append(path.resolve())

    return found


def load_procedural_context(workspace: str = "") -> str:
    """Build procedural memory block for the system prompt."""
    cfg = load_config()
    if not cfg.get("enabled", True):
        return ""

    files = discover_skill_files(workspace)
    if not files:
        return ""

    sections: list[str] = ["## Procedural memory (Skill.md)", ""]
    for path in files:
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not body:
            continue
        if body.startswith("#"):
            sections.append(body)
        else:
            sections.append(f"### {path.name} ({path.parent.name}/)\n\n{body}")
        sections.append("")

    return "\n".join(sections).strip()
