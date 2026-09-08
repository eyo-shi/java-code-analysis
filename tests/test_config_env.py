"""Tests for AMP Configuration -> code resolution."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from code_analysis.config import (
    CML_USER_SUPPLIED_VARS,
    MANAGED_ENV_VARS,
    METADATA_DEFAULTS,
    Config,
    _env,
    _normalize_env_value,
    _parse_project_environment,
    _resolve_env_value,
    _sanitize_managed_env,
)


class ConfigEnvResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in MANAGED_ENV_VARS}
        self._saved["CDSW_PROJECT_ID"] = os.environ.get("CDSW_PROJECT_ID")
        for key in list(MANAGED_ENV_VARS) + ["CDSW_PROJECT_ID"]:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key in list(MANAGED_ENV_VARS) + ["CDSW_PROJECT_ID"]:
            os.environ.pop(key, None)
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value

    def test_yaml_keys_match_managed_vars(self) -> None:
        yaml_keys = {
            "GIT_REPO_URL",
            "GIT_REF",
            "NEO4J_URI",
            "NEO4J_USERNAME",
            "NEO4J_PASSWORD",
            "CLONE_DIR",
            "SOURCE_PATH",
            "PROJECT_ID",
            "PROJECT_NAME",
            "EXCLUDE_DIRS",
        }
        self.assertEqual(set(MANAGED_ENV_VARS), yaml_keys)

    def test_project_env_wins_over_os_environ(self) -> None:
        os.environ["NEO4J_URI"] = "bolt://localhost:7687"
        os.environ["GIT_REF"] = "main"
        project_env = {
            "NEO4J_URI": "bolt://neo4j-launcher:7687",
            "GIT_REF": "release/5.7.1.SP1.RELEASE",
            "GIT_REPO_URL": "https://github.com/example/custom.git",
        }
        self.assertEqual(_env("NEO4J_URI", project_env), "bolt://neo4j-launcher:7687")
        self.assertEqual(_env("GIT_REF", project_env), "release/5.7.1.SP1.RELEASE")
        self.assertEqual(_env("GIT_REPO_URL", project_env), "https://github.com/example/custom.git")

    def test_os_environ_used_when_project_env_missing_key(self) -> None:
        os.environ["NEO4J_URI"] = "bolt://from-task-start:7687"
        value, source = _resolve_env_value("NEO4J_URI", {})
        self.assertEqual(value, "bolt://from-task-start:7687")
        self.assertEqual(source, "os.environ")

    def test_react_event_target_value_is_extracted(self) -> None:
        parsed = _parse_project_environment(
            {"NEO4J_URI": {"target": {"value": "bolt://neo4j-launcher:7687"}}}
        )
        self.assertEqual(parsed["NEO4J_URI"], "bolt://neo4j-launcher:7687")

    def test_empty_react_event_is_rejected(self) -> None:
        parsed = _parse_project_environment(
            {"NEO4J_URI": {"dispatchConfig": None, "nativeEvent": None}}
        )
        self.assertNotIn("NEO4J_URI", parsed)

    def test_neo4j_uri_without_scheme_gets_bolt_prefix(self) -> None:
        self.assertEqual(
            _normalize_env_value("NEO4J_URI", "cml-neo4j-xxxxx.namespace:7687"),
            "bolt://cml-neo4j-xxxxx.namespace:7687",
        )

    def test_cml_runtime_does_not_use_metadata_default_for_user_vars(self) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        value, source = _resolve_env_value("NEO4J_URI", {})
        self.assertIsNone(value)
        self.assertEqual(source, "missing")
        self.assertIn("NEO4J_URI", CML_USER_SUPPLIED_VARS)

    def test_cml_runtime_still_uses_metadata_default_for_optional_vars(self) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        value, source = _resolve_env_value("CLONE_DIR", {})
        self.assertEqual(value, METADATA_DEFAULTS["CLONE_DIR"])
        self.assertEqual(source, "metadata default")

    def test_sanitize_removes_corrupted_os_environ_values(self) -> None:
        os.environ["NEO4J_URI"] = json.dumps({"dispatchConfig": None, "nativeEvent": None})
        _sanitize_managed_env()
        self.assertNotIn("NEO4J_URI", os.environ)

    def test_config_from_env_uses_all_user_inputs(self) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        project_env = {
            "GIT_REPO_URL": "https://github.com/example/app.git",
            "GIT_REF": "develop",
            "NEO4J_URI": "bolt://neo4j.example:7687",
            "NEO4J_USERNAME": "admin",
            "NEO4J_PASSWORD": "secret-pass",
            "CLONE_DIR": "/tmp/custom",
            "PROJECT_ID": "my-app",
            "PROJECT_NAME": "My App",
            "EXCLUDE_DIRS": ".git,target",
        }
        with patch("code_analysis.config._load_project_environment_from_cml", return_value=project_env):
            with patch("code_analysis.config._sanitize_managed_env"):
                with patch("code_analysis.config.diagnose_environment"):
                    config = Config.from_env()

        self.assertEqual(config.git_repo_url, "https://github.com/example/app.git")
        self.assertEqual(config.git_ref, "develop")
        self.assertEqual(config.neo4j_uri, "bolt://neo4j.example:7687")
        self.assertEqual(config.neo4j_username, "admin")
        self.assertEqual(config.neo4j_password, "secret-pass")
        self.assertEqual(config.clone_dir, "/tmp/custom")
        self.assertEqual(config.project_id, "my-app")
        self.assertEqual(config.project_name, "My App")
        self.assertEqual(config.exclude_dirs, (".git", "target"))

    def test_config_requires_neo4j_uri_in_cml(self) -> None:
        os.environ["CDSW_PROJECT_ID"] = "proj-123"
        os.environ["GIT_REPO_URL"] = "https://github.com/example/app.git"
        with patch("code_analysis.config._load_project_environment_from_cml", return_value={}):
            with patch("code_analysis.config._sanitize_managed_env"):
                with patch("code_analysis.config.diagnose_environment"):
                    with self.assertRaises(ValueError):
                        Config.from_env()


if __name__ == "__main__":
    unittest.main()
