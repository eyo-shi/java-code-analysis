"""Tests for project environment seeding."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from code_analysis.config import PROJECT_ENV_SEEDS, validate_neo4j_uri_for_ingest
from code_analysis.seed_project_env import seed_project_environment


class SeedProjectEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_project_id = os.environ.get("CDSW_PROJECT_ID")
        os.environ.pop("CDSW_PROJECT_ID", None)

    def tearDown(self) -> None:
        os.environ.pop("CDSW_PROJECT_ID", None)
        if self._saved_project_id is not None:
            os.environ["CDSW_PROJECT_ID"] = self._saved_project_id

    @patch("code_analysis.seed_project_env._cml_bootstrap_client")
    @patch("code_analysis.seed_project_env.read_cml_project_env")
    def test_seed_creates_missing_keys(self, mock_read: MagicMock, mock_client_factory: MagicMock) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        mock_read.return_value = None
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client

        updates = seed_project_environment()
        self.assertEqual(set(updates.keys()), set(PROJECT_ENV_SEEDS.keys()))
        mock_client.create_environment_variable.assert_called_once_with(PROJECT_ENV_SEEDS)

    @patch("code_analysis.seed_project_env._cml_bootstrap_client")
    @patch("code_analysis.seed_project_env.read_cml_project_env")
    def test_seed_skips_existing_keys(self, mock_read: MagicMock, mock_client_factory: MagicMock) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        mock_read.side_effect = lambda name: "existing" if name == "NEO4J_URI" else None
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client

        updates = seed_project_environment()
        self.assertNotIn("NEO4J_URI", updates)
        self.assertIn("GIT_REPO_URL", updates)

    def test_validate_rejects_browser_url(self) -> None:
        with self.assertRaises(ValueError):
            validate_neo4j_uri_for_ingest(
                "bolt://neo4j-launcher-10j1ta.ml.example.cloudera.site:7687"
            )

    def test_validate_rejects_placeholder(self) -> None:
        with self.assertRaises(ValueError):
            validate_neo4j_uri_for_ingest(PROJECT_ENV_SEEDS["NEO4J_URI"])


if __name__ == "__main__":
    unittest.main()
