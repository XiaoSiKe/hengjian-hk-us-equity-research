"""Release package checks catch broken references before publication."""

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_package  # noqa: E402


class PackageChecks(unittest.TestCase):
    def test_current_package_has_resolvable_local_links(self):
        issues, documents, links = check_package.check_package(ROOT)
        self.assertEqual(issues, [])
        self.assertGreater(documents, 5)
        self.assertGreater(links, 5)

    def test_missing_reference_fails_a_disposable_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = pathlib.Path(temporary) / "sample-skill"
            package.mkdir()
            (package / "SKILL.md").write_text("---\nname: sample-skill\ndescription: Example skill\n---\n", encoding="utf-8")
            (package / "README.md").write_text("[Missing](references/does-not-exist.md)\n", encoding="utf-8")
            issues, _, _ = check_package.check_package(package)
            self.assertTrue(any("broken local link" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
