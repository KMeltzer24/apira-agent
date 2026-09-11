"""Load skill markdown and run Gemini-codegen skill tools."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from logging_config import get_request_id

SkillKind = Literal["prompt", "shell"]

_CODE_FENCE_RE = re.compile(
    r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```",
    re.DOTALL,
)
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)

_EXECUTABLE_LANGS = frozenset({"python", "bash", "sh"})

_CODEGEN_SYSTEM = (
    "You implement one tool call by writing a short program. "
    "Read the skill markdown and arguments, then output exactly one fenced code "
    "block in python, bash, or sh that does the work. "
    "Print the result to stdout (typically JSON). "
    "Use environment variables from the prompt when URLs or paths are needed. "
    "Do not invent credentials, user_ids, or file contents — call the real APIs "
    "or search the real folder. "
    "If the skill includes sample bash, treat it as a hint you may adapt; "
    "still emit your own single fence to run."
)


def skill_root(skills_pkg_dir: Path | str) -> Path:
    return Path(skills_pkg_dir)


def prompt_skill_path(skills_dir: Path | str, tool_name: str) -> Path:
    return skill_root(skills_dir) / f"{tool_name}.md"


def shell_skill_path(skills_dir: Path | str, tool_name: str) -> Path:
    return skill_root(skills_dir) / f"{tool_name}_shell.md"


def skill_path_for(
    skills_dir: Path | str, tool_name: str, *, kind: SkillKind
) -> Path:
    if kind == "shell":
        return shell_skill_path(skills_dir, tool_name)
    return prompt_skill_path(skills_dir, tool_name)


def read_skill_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def extract_code_fence(text: str) -> tuple[str, str]:
    """Return ``(lang, code)`` for the first executable python/bash/sh fence."""
    for match in _CODE_FENCE_RE.finditer(text or ""):
        lang = (match.group(1) or "").strip().casefold()
        code = (match.group(2) or "").strip()
        if not code:
            continue
        if lang in _EXECUTABLE_LANGS:
            return lang, code
        if lang in {"py", "python3"}:
            return "python", code
    raise ValueError(
        "Model response must include one fenced python, bash, or sh code block "
        "that performs the tool work."
    )


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content or "")


def run_generated_code(
    lang: str,
    code: str,
    *,
    env: dict[str, str] | None = None,
    timeout_sec: float = 60.0,
) -> str:
    """Execute generated python or bash/sh and return stdout."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items() if v is not None})

    normalized = lang.casefold()
    if normalized in {"bash", "sh"}:
        completed = subprocess.run(
            ["bash", "-lc", code],
            check=False,
            capture_output=True,
            text=True,
            env=merged_env,
            timeout=timeout_sec,
        )
    elif normalized == "python":
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(code)
            script_path = handle.name
        try:
            completed = subprocess.run(
                [sys.executable, script_path],
                check=False,
                capture_output=True,
                text=True,
                env=merged_env,
                timeout=timeout_sec,
            )
        finally:
            Path(script_path).unlink(missing_ok=True)
    else:
        raise ValueError(f"Unsupported generated language: {lang}")

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"generated {normalized} exited {completed.returncode}: "
            f"{err or 'no output'}"
        )
    return (completed.stdout or "").strip()


def _args_schema_for(tool_name: str, fields: dict[str, Any]) -> type[BaseModel]:
    return create_model(f"{tool_name}Args", **fields)  # type: ignore[call-overload]


def _build_codegen_user_prompt(
    *,
    tool_name: str,
    skill_markdown: str,
    kwargs: dict[str, Any],
    env: dict[str, str],
) -> str:
    env_keys = sorted(
        k
        for k in env
        if k
        in {
            "USER_SERVICE_URL",
            "PORTFOLIO_SERVICE_URL",
            "STOCK_RESEARCH_DIR",
            "X_REQUEST_ID",
            "PYTHONPATH",
            "PYTHON_BIN",
        }
        or k in kwargs
    )
    env_view = {k: env.get(k, "") for k in env_keys}
    return (
        f"Tool name: {tool_name}\n\n"
        f"## Skill markdown\n\n{skill_markdown}\n\n"
        f"## Tool arguments (JSON)\n\n{json.dumps(kwargs, indent=2)}\n\n"
        f"## Environment variables available to your program\n\n"
        f"{json.dumps(env_view, indent=2)}\n\n"
        "Emit one fenced python, bash, or sh block now."
    )


def make_codegen_skill_tool(
    *,
    model: Any,
    tool_name: str,
    skills_dir: Path | str,
    description: str,
    arg_fields: dict[str, Any],
    kind: SkillKind,
    extra_env: Callable[[], dict[str, str]] | None = None,
    timeout_sec: float = 60.0,
) -> StructuredTool:
    """Build a tool that asks the model to codegen from a skill, then runs it."""

    path = skill_path_for(skills_dir, tool_name, kind=kind)
    schema = _args_schema_for(tool_name, arg_fields)

    def _prepare_env(kwargs: dict[str, Any]) -> dict[str, str]:
        env: dict[str, str] = {
            k: "" if v is None else str(v) for k, v in kwargs.items()
        }
        if extra_env:
            env.update(extra_env())
        request_id = get_request_id()
        if request_id:
            env["X_REQUEST_ID"] = request_id
        return env

    def _generate_and_run(kwargs: dict[str, Any]) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {kind} skill: {path}")
        markdown = read_skill_markdown(path)
        env = _prepare_env(kwargs)
        messages = [
            SystemMessage(content=_CODEGEN_SYSTEM),
            HumanMessage(
                content=_build_codegen_user_prompt(
                    tool_name=tool_name,
                    skill_markdown=markdown,
                    kwargs=kwargs,
                    env=env,
                )
            ),
        ]
        raw = model.invoke(messages)
        text = _message_text(getattr(raw, "content", raw))
        lang, code = extract_code_fence(text)
        return run_generated_code(lang, code, env=env, timeout_sec=timeout_sec)

    def _run(**kwargs: Any) -> str:
        return _generate_and_run(kwargs)

    async def _arun(**kwargs: Any) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {kind} skill: {path}")
        markdown = read_skill_markdown(path)
        env = _prepare_env(kwargs)
        messages = [
            SystemMessage(content=_CODEGEN_SYSTEM),
            HumanMessage(
                content=_build_codegen_user_prompt(
                    tool_name=tool_name,
                    skill_markdown=markdown,
                    kwargs=kwargs,
                    env=env,
                )
            ),
        ]
        ainvoke = getattr(model, "ainvoke", None)
        if callable(ainvoke):
            raw = await ainvoke(messages)
        else:
            raw = model.invoke(messages)
        text = _message_text(getattr(raw, "content", raw))
        lang, code = extract_code_fence(text)
        return run_generated_code(lang, code, env=env, timeout_sec=timeout_sec)

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=tool_name,
        description=description,
        args_schema=schema,
    )
