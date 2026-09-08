"""Tests for CML bootstrap environment persistence."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from code_analysis.cml_bootstrap import _resolve_neo4j_uri, ensure_project_environment


class CmlBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get("NEO4J_URI")
        os.environ.pop("NEO4J_URI", None)

    def tearDown(self) -> None:
        os.environ.pop("NEO4J_URI", None)
        if self._saved is not None:
            os.environ["NEO4J_URI"] = self._saved

    def test_resolve_from_os_environ(self) -> None:
        os.environ["NEO4J_URI"] = "bolt://neo4j.example:7687"
        self.assertEqual(_resolve_neo4j_uri(), "bolt://neo4j.example:7687")

    def test_resolve_from_override(self) -> None:
        self.assertEqual(
            _resolve_neo4j_uri("bolt://override.example:7687"),
            "bolt://override.example:7687",
        )

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
