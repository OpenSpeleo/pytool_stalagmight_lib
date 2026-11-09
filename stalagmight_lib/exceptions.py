"""Public reader exceptions. Filesystem errors retain their standard types."""


class StalagMightError(Exception):
    """Base exception for unsupported or invalid survey files."""


class StalagMightFormatError(StalagMightError):
    """Wrong container, missing tables, or missing columns."""


class UnsupportedSchemaError(StalagMightError):
    """Missing, conflicting, or unsupported schema version markers."""


class DatabaseReadError(StalagMightError):
    """SQLite failed while opening or reading the database."""


class DataValidationError(StalagMightError):
    """A stored record or relationship is invalid."""
