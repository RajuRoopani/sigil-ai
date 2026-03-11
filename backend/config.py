import subprocess
from pydantic_settings import BaseSettings

def _gh_token() -> str:
    """Fall back to `gh auth token` if GITHUB_TOKEN not set in env."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5
        )
        token = result.stdout.strip()
        if token and not result.returncode:
            return token
    except Exception:
        pass
    return ""

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    github_token: str = ""
    ado_token: str = ""             # Azure DevOps OAuth token (from az account get-access-token)
    ado_pat: str = ""               # Azure DevOps Personal Access Token (preferred for org access)
    max_commits: int = 500          # hard cap; date window is the primary filter
    lookback_days: int = 365        # 1 year of commits
    model: str = "claude-sonnet-4-6"
    personas_dir: str = "personas"  # directory where agent files are saved

    class Config:
        env_file = ".env"
        extra = "ignore"

    def effective_github_token(self) -> str:
        return self.github_token or _gh_token()

settings = Settings()
