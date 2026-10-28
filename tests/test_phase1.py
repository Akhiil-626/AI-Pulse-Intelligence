"""Phase 1 automated verification test suite."""

import importlib.util
import os
import unittest
from pathlib import Path


class TestPhase1Scaffold(unittest.TestCase):
    """Test case verifying Phase 1 scaffold, environment, and files."""

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent

    def test_required_directories_exist(self):
        """Verify all mandated directories exist in project root."""
        expected_dirs = [
            "app",
            "services",
            "data/raw",
            "data/processed",
            "assets",
            "tests",
            ".streamlit",
        ]
        for rel_path in expected_dirs:
            full_path = self.root_dir / rel_path
            self.assertTrue(
                full_path.is_dir(),
                f"Required directory does not exist: {rel_path}",
            )

    def test_required_files_exist(self):
        """Verify all mandated Phase 1 files exist."""
        expected_files = [
            "app/__init__.py",
            "app/dashboard.py",
            "services/__init__.py",
            ".streamlit/config.toml",
            "requirements.txt",
            ".env.example",
            ".gitignore",
        ]
        for rel_path in expected_files:
            full_path = self.root_dir / rel_path
            self.assertTrue(
                full_path.is_file(),
                f"Required file does not exist: {rel_path}",
            )

    def test_core_dependencies_importable(self):
        """Verify streamlit, pandas, and plotly can be imported."""
        for pkg in ["streamlit", "pandas", "plotly"]:
            spec = importlib.util.find_spec(pkg)
            self.assertIsNotNone(spec, f"Package {pkg} is not importable")

    def test_dashboard_symbols(self):
        """Verify dashboard defines required UI rendering methods."""
        dashboard_path = self.root_dir / "app" / "dashboard.py"
        with open(dashboard_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("AI Pulse", code)
        self.assertIn("render_sidebar", code)
        self.assertIn("render_overview", code)
        self.assertIn("render_metrics_row", code)
        self.assertIn("render_placeholder", code)
        self.assertIn("Intelligence Feed", code)
        self.assertIn("Threat Center", code)
        self.assertIn("Analytics", code)
        self.assertIn("Reading List", code)
        self.assertIn("n8n", code)

    def test_dashboard_runtime_render(self):
        """Verify dashboard executes cleanly in Streamlit runtime."""
        from streamlit.testing.v1 import AppTest

        dashboard_file = str(self.root_dir / "app" / "dashboard.py")
        app_test = AppTest.from_file(dashboard_file).run()

        # Ensure no runtime unhandled exceptions
        self.assertEqual(len(app_test.exception), 0)

        # Ensure sidebar radio navigation exists with expected items
        self.assertGreater(len(app_test.radio), 0)
        nav_radio = app_test.radio[0]
        self.assertEqual(nav_radio.value, "Overview")

        # Test selecting a placeholder tab
        nav_radio.set_value("Threat Center").run()
        self.assertEqual(len(app_test.exception), 0)
        self.assertGreater(len(app_test.info), 0)

    def test_gitignore_covers_essentials(self):
        """Verify .gitignore contains necessary exclusions."""
        gitignore_path = self.root_dir / ".gitignore"
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        for term in [".venv/", "__pycache__/", ".env", "*.db", "data/raw/*"]:
            self.assertIn(term, content, f"Missing {term} in .gitignore")


if __name__ == "__main__":
    unittest.main()
