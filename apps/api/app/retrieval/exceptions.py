"""Domain exception for M7 retrieval (spec §93). Mirrors this codebase's
existing lightweight pattern (see app/ingestion/validation.py's
UploadValidationError) rather than a deep custom hierarchy.
"""


class RetrievalTimeout(Exception):
    pass
