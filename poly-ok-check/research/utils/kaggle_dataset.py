from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_CSDS_DATASET = "billpureskillgg/cs2-2023-11-23"
RECOMMENDED_CSDS_FILES = [
    "header.parquet",
    "round_state.parquet",
    "player_status.parquet",
    "player_info.parquet",
    "round_end.parquet",
    "player_death.parquet",
]


@dataclass(slots=True)
class KaggleDatasetFile:
    name: str
    size_bytes: int | None
    creation_date: str | None


def recommended_csds_files() -> list[str]:
    return list(RECOMMENDED_CSDS_FILES)


def list_dataset_files(dataset: str = DEFAULT_CSDS_DATASET, page_token: str | None = None, page_size: int = 100) -> tuple[list[KaggleDatasetFile], str | None]:
    api = _build_kaggle_api()
    response = api.dataset_list_files(dataset, page_token=page_token, page_size=page_size)
    files = [
        KaggleDatasetFile(
            name=str(item.name),
            size_bytes=_coerce_optional_int(getattr(item, "total_bytes", None)),
            creation_date=_coerce_optional_str(getattr(item, "creation_date", None)),
        )
        for item in getattr(response, "files", [])
    ]
    next_page_token = _coerce_optional_str(getattr(response, "next_page_token", None))
    return files, next_page_token


def download_dataset_file(
    file_name: str,
    dataset: str = DEFAULT_CSDS_DATASET,
    output_dir: Path | str | None = None,
    force: bool = False,
) -> Path:
    api = _build_kaggle_api()
    target_dir = Path(output_dir) if output_dir is not None else Path.cwd()
    target_dir.mkdir(parents=True, exist_ok=True)
    api.dataset_download_file(dataset, file_name, path=str(target_dir), force=force, quiet=False)
    return target_dir / file_name


def _build_kaggle_api():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise RuntimeError(
            "The 'kaggle' package is not installed. Install research dependencies before using Kaggle tooling."
        ) from exc

    api = KaggleApi()
    try:
        api.authenticate()
    except OSError as exc:
        raise RuntimeError(
            "Kaggle credentials are not configured. Set KAGGLE_USERNAME/KAGGLE_KEY or create ~/.kaggle/kaggle.json."
        ) from exc
    return api


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
