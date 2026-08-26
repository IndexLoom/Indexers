from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from import_upstreams import load_document  # noqa: E402


class Yaml12LoaderTests(unittest.TestCase):
    def test_cardigann_identifiers_with_underscores_remain_strings(self) -> None:
        source = """\
id: test
name: Test
description: Test definition
language: en-US
type: public
encoding: UTF-8
links:
  - https://example.com/
caps: {}
requestDelay: 2
settings:
  - name: category
    type: select
    default: 0_0
    options:
      0_0: All categories
      1_2: Movies
search:
  paths:
    - path: /api
      inputs:
        category: 0_0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.yml"
            path.write_text(source, encoding="utf-8")
            document, _ = load_document(path)

        setting = document["settings"][0]
        self.assertEqual(setting["default"], "0_0")
        self.assertEqual(list(setting["options"]), ["0_0", "1_2"])
        self.assertEqual(document["search"]["paths"][0]["inputs"]["category"], "0_0")
        self.assertEqual(document["requestDelay"], 2)


if __name__ == "__main__":
    unittest.main()
