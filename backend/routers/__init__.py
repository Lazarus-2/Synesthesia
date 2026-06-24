"""Domain router modules for the Synesthesia API.

Each module exposes a module-level ``router = APIRouter()`` that ``backend.main``
mounts twice (canonical ``/api/v1`` + legacy root) to preserve the existing
dual-mount behaviour.
"""
