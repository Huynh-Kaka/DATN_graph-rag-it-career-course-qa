from __future__ import annotations

from neo4j import Driver, GraphDatabase

from app.core.config import settings

_COMPETENCY_LABELS = (
    "ProgrammingLanguage",
    "Framework",
    "Platform",
    "Tool",
    "Knowledge",
    "Softskill",
    "Certification",
)


class Neo4jClient:
    """Kết nối Neo4j dùng chung cho các truy vấn Bước 2."""

    def __init__(self) -> None:
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

    @property
    def available(self) -> bool:
        return self._driver is not None

    def session(self):
        if self._driver is None:
            raise RuntimeError(
                "Không kết nối Neo4j. Chạy: docker compose up -d neo4j "
                'và python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx"'
            )
        return self._driver.session()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @staticmethod
    def competency_labels() -> tuple[str, ...]:
        return _COMPETENCY_LABELS
