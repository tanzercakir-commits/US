from pathlib import Path
import tomllib
import unittest

from semantic_verifier.model import SCHEMA


ROOT = Path(__file__).resolve().parents[1]


class ChangelogDisciplineTests(unittest.TestCase):
    def test_current_project_version_has_release_section(self):
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        release_heading = f"## [{project['version']}]"
        self.assertIn("## [Unreleased]", changelog)
        self.assertIn(release_heading, changelog)
        self.assertLess(
            changelog.index("## [Unreleased]"),
            changelog.index(release_heading),
        )

    def test_current_schema_and_migration_are_recorded(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn(SCHEMA, changelog)
        self.assertIn("### Migration", changelog)
        self.assertIn("docs/schema_versioning.md", changelog)
