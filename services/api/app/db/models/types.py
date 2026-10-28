from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def enum_column[E: enum.Enum](enum_cls: type[E], length: int = 48) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda values: [item.value for item in values],
        validate_strings=True,
    )
