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

    def test_resolve_from_metadata_default(self) -> None:
        value, source = resolve_managed_env_value("NEO4J_URI")
        self.assertEqual(value, METADATA_DEFAULTS["NEO4J_URI"])
        self.assertEqual(source, "metadata default")

    @patch("code_analysis.cml_bootstrap._read_from_project_environment")
    def test_resolve_prefers_os_environ_over_metadata(self, mock_read: MagicMock) -> None:
        os.environ["NEO4J_URI"] = "bolt://from-env:7687"
        mock_read.return_value = "bolt://from-project:7687"
        value, source = resolve_managed_env_value("NEO4J_URI")
        self.assertEqual(value, "bolt://from-env:7687")
        self.assertEqual(source, "os.environ")

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


if __name__ == "__main__":
    unittest.main()
