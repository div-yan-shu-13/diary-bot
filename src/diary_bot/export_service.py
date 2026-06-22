"""Export service for generating JSON exports of all diary data."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from diary_bot.models import Err, Ok, Result
from diary_bot.repository import Repository


@dataclass
class ExportError:
    """Error returned when export generation fails."""

    message: str


class ExportService:
    """Generates JSON exports of all diary entries."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def export_all(self) -> Result[bytes, ExportError]:
        """Generate JSON export of all entries.

        Returns Ok(bytes) with JSON content ordered by date ascending,
        or Err(ExportError) if no entries exist.
        """
        entries = await self._repo.get_all_entries_ordered()

        if not entries:
            return Err(ExportError("No entries available to export."))

        export_data = {
            "export_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entries": entries,
        }

        json_bytes = json.dumps(export_data, indent=2).encode("utf-8")
        return Ok(json_bytes)
