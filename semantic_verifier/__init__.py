"""Small, deterministic semantic-verification prototype."""

from .pipeline import VerificationPipeline, verify_file, verify_source

__all__ = ["VerificationPipeline", "verify_file", "verify_source"]
__version__ = "0.1.0"
