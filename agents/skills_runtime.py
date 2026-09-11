"""Load and execute agent skill markdown files (prompt-only or embedded bash)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from logging_config import get_request_id

_FENCE_RE = re.compile(
    r"```(?:bash|sh)\s*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)


def skill_root(skills_pkg_dir: Path | str) -> Path:
    return Path(skills_pkg_dir)


def prompt_skill_path(skills_dir: Path | str, tool_name: str) -> Path:
    return skill_root(skills_dir) / f"{tool_name}.md"


def shell_skill_path(skills_dir: Path | str, tool_name: str) -> Path:
    return skill_root(skills_dir) / f"{tool_name}_shell.md"


def read_skill_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def load_prompt_skills(skills_dir: Path | str, tool_names: Sequence[str]) -> str:
    """Concatenate no-code ``<tool>.md`` bodies for system-prompt injection."""
    sections: list[str] = []
    root = skill_root(skills_dir)
    for name in tool_names:
        path = prompt_skill_path(root, name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing prompt skill: {path}")
        body = read_skill_markdown(path)
        sections.append(f"### Skill: {name}\n\n{body}")
    return "\n\n".join(sections)


def extract_bash_blocks(markdown: str) -> list[str]:
    """Return fenced bash/sh code blocks from a skill markdown body."""
    return [m.group(1).strip() for m in _FENCE_RE.finditer(markdown) if m.group(1).strip()]


def run_embedded_bash(
    markdown: str,
    *,
    env: dict[str, str] | None = None,
    timeout_sec: float = 60.0,
) -> str:
    """Run all embedded bash blocks sequentially; return combined stdout."""
    blocks = extract_bash_blocks(markdown)
    if not blocks:
        raise ValueError("Skill markdown has no bash/sh fenced code blocks to run")

    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items() if v is not None})

    outputs: list[str] = []
    for block in blocks:
        completed = subprocess.run(
            ["bash", "-lc", block],
            check=False,
            capture_output=True,
            text=True,
            env=merged_env,
            timeout=timeout_sec,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"skill bash exited {completed.returncode}: {err or 'no output'}"
            )
        outputs.append(completed.stdout)
    return "".join(outputs).strip()


def _args_schema_for(tool_name: str, fields: dict[str, Any]) -> type[BaseModel]:
    return create_model(f"{tool_name}Args", **fields)  # type: ignore[call-overload]


def make_shell_skill_tool(
    *,
    tool_name: str,
    skills_dir: Path | str,
    description: str,
    arg_fields: dict[str, Any],
    extra_env: Callable[[], dict[str, str]] | None = None,
) -> StructuredTool:
    """Build a LangChain tool that executes ``<tool>_shell.md`` bash blocks."""

    path = shell_skill_path(skills_dir, tool_name)
    schema = _args_schema_for(tool_name, arg_fields)

    def _run(**kwargs: Any) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Missing shell skill: {path}")
        markdown = read_skill_markdown(path)
        env: dict[str, str] = {k: "" if v is None else str(v) for k, v in kwargs.items()}
        if extra_env:
            env.update(extra_env())
        request_id = get_request_id()
        if request_id:
            env["X_REQUEST_ID"] = request_id
        return run_embedded_bash(markdown, env=env)

    async def _arun(**kwargs: Any) -> str:
        return _run(**kwargs)

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=tool_name,
        description=description,
        args_schema=schema,
    )
