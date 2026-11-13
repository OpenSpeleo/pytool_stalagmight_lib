"""Public reader exceptions. Filesystem errors retain their standard types."""


class StalagmightError(Exception):
    """Base exception for unsupported or invalid survey files."""


class StalagmightFormatError(StalagmightError):
    """Wrong container, missing tables, or missing columns."""


class UnsupportedSchemaError(StalagmightError):
    """Missing, conflicting, or unsupported schema version markers."""


class DatabaseReadError(StalagmightError):
    """SQLite failed while opening or reading the database."""


class DataValidationError(StalagmightError):
    """A stored record or relationship is invalid."""
