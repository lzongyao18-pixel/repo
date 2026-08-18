class IngestError(Exception):
    """Base error with a stable, user-safe code."""

    code = "INGEST_ERROR"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigurationError(IngestError):
    code = "CONFIGURATION_ERROR"


class InvalidInputError(IngestError):
    code = "INVALID_INPUT"


class DependencyMissingError(IngestError):
    code = "DEPENDENCY_MISSING"


class DownloadError(IngestError):
    code = "DOWNLOAD_FAILED"


class TranscriptionError(IngestError):
    code = "TRANSCRIPTION_FAILED"


class LocalizationError(IngestError):
    code = "LOCALIZATION_FAILED"


class RemoteSyncError(IngestError):
    code = "REMOTE_SYNC_FAILED"

