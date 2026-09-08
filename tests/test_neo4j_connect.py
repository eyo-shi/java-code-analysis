"""Tests for Neo4j connection URI resolution."""

from __future__ import annotations

import unittest

from code_analysis.neo4j_connect import format_neo4j_connection_help, iter_neo4j_connection_uris


class Neo4jConnectTests(unittest.TestCase):
    def test_cloudera_site_prefers_internal_service(self) -> None:
        uri = "bolt+ssc://neo4j-launcher-10j1ta.ml.example.cloudera.site:7687"
        self.assertEqual(
            iter_neo4j_connection_uris(uri),
            [
                "bolt://neo4j-launcher-10j1ta:7687",
                "bolt://neo4j-launcher:7687",
                "bolt+ssc://neo4j-launcher-10j1ta.ml.example.cloudera.site:7687",
                "bolt://neo4j-launcher-10j1ta.ml.example.cloudera.site:7687",
            ],
        )

    def test_internal_launcher_adds_short_name(self) -> None:
        uri = "bolt://neo4j-launcher-10j1ta:7687"
        self.assertEqual(
            iter_neo4j_connection_uris(uri),
            [
                "bolt://neo4j-launcher-10j1ta:7687",
                "bolt://neo4j-launcher:7687",
            ],
        )

    def test_connection_help_mentions_internal_uri(self) -> None:
        message = format_neo4j_connection_help(
            "bolt+ssc://neo4j-launcher-10j1ta.ml.example.cloudera.site:7687",
            ["  bolt://neo4j-launcher-10j1ta:7687: failed"],
        )
        self.assertIn("bolt://neo4j-launcher-10j1ta:7687", message)
        self.assertIn("browser URL", message)


if __name__ == "__main__":
    unittest.main()
