import ast
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "pipslayer" / "contracts"

class IsolationTests(unittest.TestCase):
    def test_core_does_not_import_msnr(self):
        for path in CORE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else ""
                if isinstance(node, ast.Import):
                    module = " ".join(x.name for x in node.names)
                self.assertNotIn("msnr", module.lower(), path.name)
if __name__ == "__main__": unittest.main()
