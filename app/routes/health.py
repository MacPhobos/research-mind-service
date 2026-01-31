from fastapi import APIRouter
import subprocess

router = APIRouter()


def get_git_sha() -> str:
    """Get git SHA, fallback to 'unknown' if not in git repo."""
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "name": "research-mind-service",
        "version": "0.1.0",
        "git_sha": get_git_sha(),
    }
