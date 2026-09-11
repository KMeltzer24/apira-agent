"""Tests for skill markdown loading, fence extraction, and codegen tools."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import Field

from agents.skills_runtime import (
    extract_code_fence,
    make_codegen_skill_tool,
    read_skill_markdown,
    run_generated_code,
)


class SkillsRuntimeTests(unittest.TestCase):
    def test_extract_code_fence_prefers_python(self) -> None:
        lang, code = extract_code_fence("Here:\n```python\nprint(1)\n```\n")
        self.assertEqual(lang, "python")
        self.assertEqual(code, "print(1)")

    def test_extract_code_fence_bash(self) -> None:
        lang, code = extract_code_fence("```bash\necho hi\n```")
        self.assertEqual(lang, "bash")
        self.assertEqual(code, "echo hi")

    def test_extract_code_fence_rejects_missing(self) -> None:
        with self.assertRaises(ValueError):
            extract_code_fence("no fence here")

    def test_extract_code_fence_rejects_unsupported_lang(self) -> None:
        with self.assertRaises(ValueError):
            extract_code_fence("```javascript\nconsole.log(1)\n```")

    def test_run_generated_python(self) -> None:
        out = run_generated_code("python", 'print("ok-json")')
        self.assertEqual(out, "ok-json")

    def test_run_generated_bash(self) -> None:
        out = run_generated_code("bash", "echo from-bash")
        self.assertEqual(out, "from-bash")

    def test_run_generated_nonzero(self) -> None:
        with self.assertRaises(RuntimeError):
            run_generated_code("bash", "exit 7")

    def test_read_skill_markdown_strips_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "login.md"
            path.write_text(
                "---\nname: login\n---\n\n# login\n\nDo the thing.\n",
                encoding="utf-8",
            )
            text = read_skill_markdown(path)
            self.assertIn("Do the thing.", text)
            self.assertNotIn("name: login", text)

    def test_codegen_skill_tool_runs_generated_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "login.md").write_text(
                "# login\n\nPOST to the login API and print JSON.\n",
                encoding="utf-8",
            )
            model = FakeListChatModel(
                responses=[
                    '```python\nprint(\'{"success":true,"user_id":1}\')\n```'
                ]
            )
            tool = make_codegen_skill_tool(
                model=model,
                tool_name="login",
                skills_dir=root,
                description="login",
                arg_fields={
                    "username": (str, Field(...)),
                    "password": (str, Field(...)),
                },
                kind="prompt",
            )
            out = asyncio.run(
                tool.ainvoke({"username": "alice", "password": "password"})
            )
            self.assertIn("user_id", out)
            self.assertIn("1", out)


class PortfolioSkillsIntegrationTests(unittest.TestCase):
    def test_prompt_and_shell_tools_named_like_mcp(self) -> None:
        from agents.portfolio_sub_agent.mcp_tools import TOOL_NAMES
        from agents.portfolio_sub_agent.skills import (
            load_prompt_tools,
            load_shell_tools,
        )

        model = FakeListChatModel(responses=["unused"])
        for loader in (load_prompt_tools, load_shell_tools):
            tools = loader(model)
            self.assertEqual({t.name for t in tools}, set(TOOL_NAMES))


class ResearchSkillsIntegrationTests(unittest.TestCase):
    def test_prompt_and_shell_tools_are_local_folder_only(self) -> None:
        from agents.research_sub_agent.skills import (
            load_prompt_tools,
            load_shell_tools,
        )

        model = FakeListChatModel(responses=["unused"])
        for loader in (load_prompt_tools, load_shell_tools):
            tools = loader(model)
            self.assertEqual([t.name for t in tools], ["searchLocalFolder"])


if __name__ == "__main__":
    unittest.main()
