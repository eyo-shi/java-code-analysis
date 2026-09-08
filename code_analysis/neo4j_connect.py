"""Neo4j connection URI helpers for CML neo4j-launcher."""

from __future__ import annotations

from urllib.parse import urlparse


def iter_neo4j_connection_uris(uri: str) -> list[str]:
    """
    Build URIs to try when connecting from a CML job.

    CML neo4j-launcher exposes a browser URL (*.cloudera.site) that does not
    reliably serve Bolt on port 7687. Jobs in the same cluster should use the
    in-cluster service name instead (e.g. bolt://neo4j-launcher-10j1ta:7687).
    """
    text = uri.strip()
    if "://" not in text:
        text = f"bolt://{text}"

    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if not host:
        return [text]

    port = parsed.port or 7687
    scheme = (parsed.scheme or "bolt").lower()
    seen: set[str] = set()
    ordered: list[str] = []

    def add(candidate_scheme: str, candidate_host: str) -> None:
        candidate = f"{candidate_scheme}://{candidate_host}:{port}"
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)

    if host.endswith(".cloudera.site") and "neo4j-launcher" in host:
        launcher_service = host.split(".", 1)[0]
        add("bolt", launcher_service)
        add("bolt", "neo4j-launcher")

    add(scheme, host)

    if scheme in {"bolt+ssc", "bolt+s", "neo4j+ssc", "neo4j+s"}:
        add("bolt", host)

    if "neo4j-launcher" in host and not host.endswith(".cloudera.site"):
        add("bolt", "neo4j-launcher")

    return ordered


def format_neo4j_connection_help(configured_uri: str, errors: list[str]) -> str:
    candidates = iter_neo4j_connection_uris(configured_uri)
    internal_hint = next(
        (uri for uri in candidates if ".cloudera.site" not in uri and "neo4j-launcher" in uri),
        "bolt://neo4j-launcher-<id>:7687",
    )
    attempts = "\n".join(errors) if errors else "  (no attempts recorded)"
    return (
        f"Could not connect to Neo4j (configured: {configured_uri}).\n"
        f"Attempts:\n{attempts}\n"
        "CML neo4j-launcher checklist:\n"
        "  1. neo4j-launcher application is Running (Applications page)\n"
        "  2. Use the in-cluster Bolt URI, not the browser URL (*.cloudera.site)\n"
        f"     Example: {internal_hint}\n"
        "  3. NEO4J_PASSWORD is the password from neo4j-launcher startup\n"
        "     (not the metadata default Neo4jPass1234)\n"
        "  4. NEO4J_USERNAME is usually neo4j"
    )
