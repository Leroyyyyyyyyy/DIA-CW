from __future__ import annotations

from pathlib import Path

from research.utils import kaggle_dataset


class _FakeFile:
    def __init__(self, name: str, total_bytes: int, creation_date: str):
        self.name = name
        self.total_bytes = total_bytes
        self.creation_date = creation_date


class _FakeListResponse:
    def __init__(self):
        self.files = [_FakeFile("header.parquet", 128, "2026-03-30")]
        self.next_page_token = "token-2"


class _FakeApi:
    def __init__(self):
        self.list_calls: list[tuple[str, str | None, int]] = []
        self.download_calls: list[tuple[str, str, str, bool, bool]] = []

    def dataset_list_files(self, dataset: str, page_token: str | None = None, page_size: int = 100):
        self.list_calls.append((dataset, page_token, page_size))
        return _FakeListResponse()

    def dataset_download_file(self, dataset: str, file_name: str, path: str, force: bool = False, quiet: bool = False):
        self.download_calls.append((dataset, file_name, path, force, quiet))


def test_list_dataset_files_uses_kaggle_api(monkeypatch) -> None:
    fake_api = _FakeApi()
    monkeypatch.setattr(kaggle_dataset, "_build_kaggle_api", lambda: fake_api)

    files, next_page_token = kaggle_dataset.list_dataset_files(page_size=50, page_token="token-1")

    assert fake_api.list_calls == [("billpureskillgg/cs2-2023-11-23", "token-1", 50)]
    assert files[0].name == "header.parquet"
    assert files[0].size_bytes == 128
    assert next_page_token == "token-2"


def test_download_dataset_file_uses_single_file_download(monkeypatch, tmp_path: Path) -> None:
    fake_api = _FakeApi()
    monkeypatch.setattr(kaggle_dataset, "_build_kaggle_api", lambda: fake_api)

    destination = kaggle_dataset.download_dataset_file("header.parquet", output_dir=tmp_path, force=True)

    assert destination == tmp_path / "header.parquet"
    assert fake_api.download_calls == [
        ("billpureskillgg/cs2-2023-11-23", "header.parquet", str(tmp_path), True, False)
    ]


def test_recommended_csds_files_are_minimal() -> None:
    assert kaggle_dataset.recommended_csds_files() == [
        "header.parquet",
        "round_state.parquet",
        "player_status.parquet",
        "player_info.parquet",
        "round_end.parquet",
        "player_death.parquet",
    ]
