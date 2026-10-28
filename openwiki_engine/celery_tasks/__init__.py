"""Celery task package metadata for the generic IKC task registrar.

The entry point group ``ikc.celery_tasks`` points at ``MANIFEST_PATH`` so
``rag-celery-registrar`` can discover the task declarations without importing
the application's own Celery app.
"""

from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "manifest.yaml"
