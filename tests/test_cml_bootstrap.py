"""Tests for CML bootstrap environment persistence."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from code_analysis.cml_bootstrap import ensure_project_environment, resolve_managed_env_value
from code_analysis.config import METADATA_DEFAULTS


class CmlBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get("NEO4J_URI")
        self._saved_project_id = os.environ.get("CDSW_PROJECT_ID")
        os.environ.pop("NEO4J_URI", None)
        os.environ.pop("CDSW_PROJECT_ID", None)

    def tearDown(self) -> None:
        os.environ.pop("NEO4J_URI", None)
        os.environ.pop("CDSW_PROJECT_ID", None)
        if self._saved is not None:
            os.environ["NEO4J_URI"] = self._saved
        if self._saved_project_id is not None:
            os.environ["CDSW_PROJECT_ID"] = self._saved_project_id

    def test_resolve_from_os_environ(self) -> None:
        os.environ["NEO4J_URI"] = "bolt://neo4j.example:7687"
        value, source = resolve_managed_env_value("NEO4J_URI")
        self.assertEqual(value, "bolt://neo4j.example:7687")
        self.assertEqual(source, "os.environ")

    def test_resolve_from_metadata_default_outside_cml(self) -> None:
        value, source = resolve_managed_env_value("GIT_REF")
        self.assertEqual(value, METADATA_DEFAULTS["GIT_REF"])
        self.assertEqual(source, "metadata default")

    @patch("code_analysis.cml_bootstrap.read_cml_project_env")
    def test_resolve_prefers_project_env_over_os_environ(self, mock_read: MagicMock) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        os.environ["NEO4J_URI"] = "bolt://from-env:7687"
        mock_read.return_value = "bolt://from-project:7687"
        value, source = resolve_managed_env_value("NEO4J_URI")
        self.assertEqual(value, "bolt://from-project:7687")
        self.assertEqual(source, "CML project environment")

    @patch("code_analysis.cml_bootstrap._cml_bootstrap_client")
    def test_ensure_project_environment_persists(self, mock_client_factory: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        os.environ["NEO4J_URI"] = "bolt://persist.example:7687"

        updates = ensure_project_environment()
        self.assertEqual(updates["NEO4J_URI"], "bolt://persist.example:7687")
        mock_client.create_environment_variable.assert_called_once_with(
            {"NEO4J_URI": "bolt://persist.example:7687"}
        )
        self.assertEqual(os.environ["NEO4J_URI"], "bolt://persist.example:7687")

    @patch("code_analysis.cml_bootstrap._cml_bootstrap_client")
    def test_ensure_requires_neo4j_uri(self, mock_client_factory: MagicMock) -> None:
        with self.assertRaises(ValueError):
            ensure_project_environment()
        mock_client_factory.assert_not_called()

    @patch("code_analysis.cml_bootstrap._cml_bootstrap_client")
    @patch("code_analysis.cml_bootstrap.read_cml_project_env")
    def test_ensure_does_not_overwrite_existing_project_env(
        self, mock_read: MagicMock, mock_client_factory: MagicMock
    ) -> None:
        mock_read.return_value = "bolt://from-project:7687"
        os.environ["NEO4J_URI"] = "bolt://from-env:7687"

        updates = ensure_project_environment()
        self.assertEqual(updates["NEO4J_URI"], "bolt://from-project:7687")
        mock_client_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
