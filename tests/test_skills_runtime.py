"""Tests for skill markdown loading, fence extraction, and codegen tools."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import Field

from agents.skills_runtime import (
    extract_code_fence,
    make_codegen_skill_tool,
    read_skill_markdown,
    run_generated_code,
    skill_path_for,
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

    def test_skill_path_for_mcp_suffixes(self) -> None:
        root = Path("/tmp/skills")
        self.assertEqual(
            skill_path_for(root, "searchLocalFolder", kind="prompt").name,
            "searchLocalFolder.md",
        )
        self.assertEqual(
            skill_path_for(root, "searchLocalFolder", kind="prompt", mcp=True).name,
            "searchLocalFolder_MCP.md",
        )
        self.assertEqual(
            skill_path_for(root, "searchLocalFolder", kind="shell", mcp=True).name,
            "searchLocalFolder_shell_MCP.md",
        )
        self.assertEqual(
            skill_path_for(root, "searchVectorDB", kind="shell", mcp=True).name,
            "searchVectorDB_shell_MCP.md",
        )
        self.assertEqual(
            skill_path_for(root, "searchVectorDB", kind="prompt", mcp=True).name,
            "searchVectorDB_MCP.md",
        )

    def test_codegen_mcp_true_reads_mcp_skill_and_exposes_rag_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "searchLocalFolder_MCP.md").write_text(
                "# searchLocalFolder\n\nCall RAG MCP.\n",
                encoding="utf-8",
            )
            model = FakeListChatModel(
                responses=["```bash\necho \"$RAG_MCP_URL\"\n```"]
            )
            tool = make_codegen_skill_tool(
                model=model,
                tool_name="searchLocalFolder",
                skills_dir=root,
                description="searchLocalFolder",
                arg_fields={"query": (str, Field(""))},
                kind="prompt",
                mcp=True,
                extra_env=lambda: {"RAG_MCP_URL": "http://example.test/mcp"},
            )
            out = asyncio.run(tool.ainvoke({"query": "AAPL"}))
            self.assertEqual(out, "http://example.test/mcp")


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
            with patch.dict(
                os.environ,
                {"TOOL_MODE": "python", "SKILLS_MCP": "false"},
            ):
                tools = loader(model)
            self.assertEqual([t.name for t in tools], ["searchLocalFolder"])

    def test_skills_mcp_loads_folder_and_vector_from_mcp_markdown(self) -> None:
        from agents.research_sub_agent.skills import (
            SKILLS_DIR,
            load_prompt_tools,
            load_shell_tools,
        )
        from agents.tool_mode import TOOL_MODE_SKILLS_PROMPT, TOOL_MODE_SKILLS_SHELL

        model = FakeListChatModel(responses=["unused"])
        cases = (
            (TOOL_MODE_SKILLS_PROMPT, load_prompt_tools, "prompt"),
            (TOOL_MODE_SKILLS_SHELL, load_shell_tools, "shell"),
        )
        for mode, loader, kind in cases:
            with patch.dict(
                os.environ, {"TOOL_MODE": mode, "SKILLS_MCP": "true"}
            ):
                tools = loader(model)
            self.assertEqual(
                [t.name for t in tools],
                ["searchLocalFolder", "searchVectorDB"],
                msg=mode,
            )
            for name in ("searchLocalFolder", "searchVectorDB"):
                path = skill_path_for(SKILLS_DIR, name, kind=kind, mcp=True)
                self.assertTrue(path.is_file(), msg=str(path))

    def test_mcp_skill_markdown_contracts(self) -> None:
        from agents.research_sub_agent.skills import SKILLS_DIR

        forbidden = ("python_tools", "mcp_tools")
        prompt_files = {
            "searchLocalFolder": SKILLS_DIR / "searchLocalFolder_MCP.md",
            "searchVectorDB": SKILLS_DIR / "searchVectorDB_MCP.md",
        }
        shell_files = {
            "searchLocalFolder": SKILLS_DIR / "searchLocalFolder_shell_MCP.md",
            "searchVectorDB": SKILLS_DIR / "searchVectorDB_shell_MCP.md",
        }

        for tool_name, path in {**prompt_files, **shell_files}.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn("RAG_MCP_URL", text, msg=path.name)
            self.assertIn("tools/call", text, msg=path.name)
            self.assertIn(tool_name, text, msg=path.name)
            self.assertIn("Accept: application/json, text/event-stream", text, msg=path.name)
            for token in forbidden:
                self.assertIn(token, text, msg=f"{path.name} should forbid {token}")

        for tool_name, path in prompt_files.items():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("```bash", text, msg=path.name)

        vector_prompt = prompt_files["searchVectorDB"].read_text(encoding="utf-8")
        self.assertIn("```python", vector_prompt)
        self.assertIn("Accept", vector_prompt)

        for tool_name, path in shell_files.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn("```bash", text, msg=path.name)
            self.assertIn("curl", text, msg=path.name)
            self.assertIn("initialize", text, msg=path.name)
            self.assertNotIn("ClientSession", text, msg=path.name)
            self.assertNotIn("streamablehttp_client", text, msg=path.name)
            self.assertNotIn("asyncio", text, msg=path.name)


if __name__ == "__main__":
    unittest.main()
