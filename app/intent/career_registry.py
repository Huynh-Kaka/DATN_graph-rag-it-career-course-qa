from __future__ import annotations

from neo4j import Driver, GraphDatabase

from app.core.config import settings

_LIST_CAREERS = """
MATCH (c:Career)
RETURN c.career_name AS name
ORDER BY c.career_name
"""


class CareerRegistry:
    """Danh sách Career từ Neo4j — cache trong memory sau lần load đầu."""

    def __init__(self) -> None:
        self._names: list[str] | None = None
        self._driver: Driver | None = None
        try:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            self._driver.verify_connectivity()
        except Exception:
            if self._driver is not None:
                self._driver.close()
            self._driver = None

    def list_careers(self, *, force_reload: bool = False) -> list[str]:
        if self._names is not None and not force_reload:
            return list(self._names)

        if self._driver is None:
            self._names = []
            return []

        try:
            with self._driver.session() as session:
                rows = session.run(_LIST_CAREERS)
                self._names = [r["name"] for r in rows if r.get("name")]
        except Exception:
            self._names = []

        return list(self._names or [])

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
