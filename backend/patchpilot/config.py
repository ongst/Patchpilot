from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PATCHPILOT_",
        extra="ignore",
    )

    app_name: str = "PatchPilot"
    data_dir: Path = Path("data")
    workspace_dir: Path = Path("workspaces")
    frontend_origin: str = "http://localhost:5173"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_timeout_seconds: int = 120
    llm_max_tool_rounds: int = 12

    github_token: str = ""
    git_author_name: str = "PatchPilot Agent"
    git_author_email: str = "patchpilot@localhost"

    max_repair_retries: int = Field(default=2, ge=0, le=5)
    max_patch_files: int = Field(default=8, ge=1, le=30)
    max_patch_lines: int = Field(default=800, ge=50, le=5000)
    max_file_bytes: int = Field(default=256_000, ge=1_024)
    max_tool_output_chars: int = Field(default=16_000, ge=1_000)

    docker_enabled: bool = True
    docker_cpus: float = 1.0
    docker_memory: str = "1g"
    docker_pids_limit: int = 256
    test_timeout_seconds: int = 300

    @property
    def database_path(self) -> Path:
        return self.data_dir / "patchpilot.sqlite3"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite3"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
