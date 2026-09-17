from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TransferInstruction:
    source_station_id: str
    destination_generator_reference: str
    start_period: str
    end_period: str
    certificate_type: str = "REGO"


ScraperOperations = Literal["refresh_data", "transfer_certificates"]


@dataclass
class RefreshResult:
    organisations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TransferPreparationResult:
    source_station_id: str
    destination_generator_reference: str
    selected: bool
    reason: str | None = None


@dataclass
class ScraperResult:
    refresh_result: RefreshResult | None = None
    transfer_results: list[TransferPreparationResult] = field(default_factory=list)
