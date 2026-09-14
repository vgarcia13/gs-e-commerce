import dataclasses


@dataclasses.dataclass(frozen=True)
class RowError:
    line: int
    field: str | None
    value: str
    message: str

    def __str__(self) -> str:
        location = f"line {self.line}"
        if self.field:
            location += f", {self.field}"
        return f"{location}: {self.message} (got {self.value!r})"


@dataclasses.dataclass(frozen=True)
class RowWarning:
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


@dataclasses.dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    resurrected: int = 0
    blank_rows: int = 0
    errors: list[RowError] = dataclasses.field(default_factory=list)
    warnings: list[RowWarning] = dataclasses.field(default_factory=list)

    @property
    def written(self) -> int:
        return self.created + self.updated + self.resurrected

    @property
    def rejected(self) -> int:
        return len({error.line for error in self.errors})
