"""Tests for SKILL.md loading and bash extraction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.skills_runtime import (
    extract_bash_blocks,
    load_prompt_skills,
    run_embedded_bash,
)


class SkillsRuntimeTests(unittest.TestCase):
    def test_extract_bash_blocks(self) -> None:
        md = """
# demo

```bash
echo hello
```

```sh
echo world
```
"""
        self.assertEqual(extract_bash_blocks(md), ["echo hello", "echo world"])

    def test_extract_ignores_other_fences(self) -> None:
        md = "```python\nprint(1)\n```\n"
        self.assertEqual(extract_bash_blocks(md), [])

    def test_run_embedded_bash(self) -> None:
        out = run_embedded_bash("```bash\necho hi-$name\n```", env={"name": "alice"})
        self.assertEqual(out, "hi-alice")

    def test_run_embedded_bash_nonzero(self) -> None:
        with self.assertRaises(RuntimeError):
            run_embedded_bash("```bash\nexit 7\n```")

    def test_load_prompt_skills_strips_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "login.md").write_text(
                "---\nname: login\n---\n\n# login\n\nDo the thing.\n",
                encoding="utf-8",
            )
            text = load_prompt_skills(root, ["login"])
            self.assertIn("### Skill: login", text)
            self.assertIn("Do the thing.", text)
            self.assertNotIn("name: login", text)


class PortfolioSkillsIntegrationTests(unittest.TestCase):
    def test_prompt_skills_load(self) -> None:
        from agents.portfolio_sub_agent.skills import load_prompt_skill_text

        text = load_prompt_skill_text()
        self.assertIn("Skill: login", text)
        self.assertIn("Skill: get_portfolio", text)

    def test_shell_tools_named_like_mcp(self) -> None:
        from agents.portfolio_sub_agent.mcp_tools import TOOL_NAMES
        from agents.portfolio_sub_agent.skills import load_shell_tools

        tools = load_shell_tools()
        self.assertEqual({t.name for t in tools}, set(TOOL_NAMES))


class ResearchSkillsIntegrationTests(unittest.TestCase):
    def test_prompt_skills_load(self) -> None:
        from agents.research_sub_agent.skills import load_prompt_skill_text

        text = load_prompt_skill_text()
        self.assertIn("searchLocalFolder", text)
        self.assertNotIn("searchVectorDB", text)

    def test_shell_tools_are_local_folder_only(self) -> None:
        from agents.research_sub_agent.skills import load_shell_tools

        tools = load_shell_tools()
        self.assertEqual([t.name for t in tools], ["searchLocalFolder"])


if __name__ == "__main__":
    unittest.main()
