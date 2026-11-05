
from pydantic import Field

from screenwise.schemas.common import ScreenWiseModel


class AppUsage(ScreenWiseModel):
    """Usage information for an individual application."""

    app_name: str = Field(min_length=1)

    duration_seconds: int = Field(ge=0)

    category: str | None = None

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60


class CategoryUsage(ScreenWiseModel):
    """Usage information for an app category."""

    category_name: str = Field(min_length=1)

    duration_seconds: int = Field(ge=0)

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60


class PickupMetrics(ScreenWiseModel):
    """Device pickup and notification statistics."""

    total_pickups: int = Field(ge=0)

    notifications: int | None = Field(
        default=None,
        ge=0,
    )

    pickups_per_day: float | None = Field(
        default=None,
        ge=0,
    )
