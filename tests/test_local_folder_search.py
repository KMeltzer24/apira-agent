"""Tests for local stock-research folder search."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agents.research_sub_agent.local_folder_search import (
    main,
    search_local_folder,
)


class LocalFolderSearchTests(unittest.TestCase):
    def test_matches_filename_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aapl-outlook.md").write_text("Apple holds cash.\n", encoding="utf-8")
            (root / "msft-notes.md").write_text("Cloud growth.\n", encoding="utf-8")
            (root / "readme.md").write_text("skip me\n", encoding="utf-8")

            by_name = search_local_folder("aapl", root=root)
            self.assertEqual(by_name["file_count"], 1)
            self.assertEqual(by_name["files"][0]["filename"], "aapl-outlook.md")

            by_content = search_local_folder("cloud", root=root)
            self.assertEqual(by_content["file_count"], 1)
            self.assertEqual(by_content["files"][0]["filename"], "msft-notes.md")

    def test_missing_folder_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            search_local_folder("aapl", root="/no/such/stock-research")

    def test_cli_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "googl.md").write_text("ads\n", encoding="utf-8")
            import os
            from io import StringIO
            from unittest.mock import patch

            buf = StringIO()
            with patch.dict(os.environ, {"STOCK_RESEARCH_DIR": str(root)}):
                with patch("sys.stdout", buf):
                    code = main(["googl"])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
