from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Simple liveness check — Cloud Run pings this to verify the service is up."""
    return {"status": "ok"}
