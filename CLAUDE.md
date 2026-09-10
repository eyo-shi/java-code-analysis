# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python-based Cloudera Machine Learning (CML) Applied ML Prototype (AMP). It clones an arbitrary Java repo (defaults to a Spring MVC + MyBatis project), walks the sources with hand-written parsers, and ingests a business-to-database knowledge graph into any Neo4j reachable via Bolt. Two CML jobs — **Install Dependencies** and **Analyze and Ingest** — drive the flow at deploy time; the same pipeline runs locally.

## Common commands

```bash
# Install runtime deps (local dev)
pip install -r 0_session-install-dependencies/requirements.txt
# setup.sh additionally installs cmlbootstrap from GitHub; only needed to test seeding code paths.

# Run the whole pipeline locally
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=...
export GIT_REPO_URL=https://github.com/your-org/your-java-app.git   # or set SOURCE_PATH
export GIT_REF=main
python3 1_session-analyze-ingest/analyze_ingest.py

# Tests (unittest, no pytest config)
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_config_env.ConfigEnvResolutionTests.test_reads_from_os_environ

# Diagnose env-var resolution without running the pipeline
python3 -c "from code_analysis.config import diagnose_environment; diagnose_environment()"
```

## Architecture — analysis pipeline

Single entry point, fixed stages, dataclass-based graph. Nothing async, no plugin registry.

`1_session-analyze-ingest/analyze_ingest.py`
→ `Config.from_env()` (`code_analysis/config.py`)
→ `resolve_source_path()` (`code_analysis/source_fetcher.py`) — either git-clones or reuses `SOURCE_PATH`
→ `build_graph()` (`code_analysis/graph_builder.py`) — orchestrates every parser under `code_analysis/parsers/` (java_parser, mybatis_parser, ddl_parser, database_parser, domain_parser, form_parser, rule_parser, i18n_parser, document_parser, validation_linker, process_parser, evidence_builder) and stitches results into an `AnalysisGraph` (`code_analysis/models.py`)
→ `Neo4jLoader.ingest()` (`code_analysis/neo4j_loader.py`) — deletes anything scoped to `project_id`, ensures constraints, re-ingests in batches (`BATCH_SIZE=200`). Every node carries `project_id`; re-runs are idempotent per project.

The parsers assume **Spring MVC + MyBatis** conventions:
- Module names come from `*.app.<module>.*` packages (see `_module_from_package` in `graph_builder.py`).
- SQL binding assumes `<pkg>.<Foo>Repository` Java + matching `<Foo>Repository.xml` MyBatis mapper — see `_build_operations` and `_build_executes`.
- Business/Screen display names fall back to Japanese i18n keys hardcoded in `MODULE_BUSINESS_KEYS` / `MODULE_SCREEN_KEYS`. When adapting to a new domain, update those maps rather than the parsers.

## Architecture — configuration resolution

Everything the pipeline needs is a CML project environment variable. This bit trips people up:

- `code_analysis/config.py:_env()` resolves each managed variable in order: **CML project env (via `cmlapi`)** → `os.environ` → metadata default (local-dev only, skipped inside CML). `MANAGED_ENV_VARS` lists them; `PROJECT_ENV_SEEDS` provides non-empty placeholder defaults so the keys actually appear in *Project Settings → Advanced → Environment Variables* after AMP deploy.
- Values are corruption-checked. CML's Advanced settings UI has been observed to write serialized React synthetic events into env vars — `_looks_corrupted()` filters strings containing `dispatchConfig`, `nativeEvent`, `isTrusted`, or JSON-looking payloads and treats them as unset. Do not remove this without understanding why it exists.
- `NEO4J_URI` is validated twice:
  - Load-time: `validate_neo4j_uri_for_ingest()` rejects the placeholder, `*.cloudera.site` browser URLs, and ELB hostnames — from a CML job only the **Internal Bolt** URI from the neo4j-launcher Application Log works (`bolt://cml-neo4j-<hash>.mlx-user-<id>:7687`).
  - Connect-time: `code_analysis/neo4j_connect.py:iter_neo4j_connection_uris()` picks the best in-cluster candidate; `NEO4J_INTERNAL_URI` overrides.
- Project-env seeding runs from `code_analysis/seed_project_env.py`, invoked by the **Install Dependencies** job (see `0_session-install-dependencies/install-dependencies.py`).

## Testing notes

- Tests are plain `unittest` under `tests/`. Anything that reads env vars monkey-patches `os.environ` and saves/restores `MANAGED_ENV_VARS` in `setUp`/`tearDown` — follow that pattern.
- `tests/test_seed_project_env.py` stubs `cmlbootstrap` / `cmlapi`; those packages don't need to be installed to run the suite.

## Change-target hints

- **New node kind or relation:** add the dataclass in `code_analysis/models.py`, hang it off `AnalysisGraph`, populate it in a parser under `code_analysis/parsers/`, wire it into `graph_builder.build_graph()`, and add a batch + Cypher write in `code_analysis/neo4j_loader.py`.
- **New managed env variable:** add to `MANAGED_ENV_VARS` and `PROJECT_ENV_SEEDS` in `code_analysis/config.py`, add a matching entry under `environment_variables:` in `.project-metadata.yaml` (so CML Project Settings shows the key after deploy), and cover it in `tests/test_config_env.py`.
- **New parser:** put it in `code_analysis/parsers/`, take `root: Path` (+ `exclude_dirs` if walking the tree), return dataclass instances rather than mutating shared state, and let `build_graph()` be the only place that composes them.
