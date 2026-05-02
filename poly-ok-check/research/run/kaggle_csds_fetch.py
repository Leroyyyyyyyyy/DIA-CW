from __future__ import annotations

import argparse
from pathlib import Path

from research.utils.kaggle_dataset import (
    DEFAULT_CSDS_DATASET,
    download_dataset_file,
    list_dataset_files,
    recommended_csds_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and download Kaggle CSDS files on demand.")
    parser.add_argument("--dataset", default=DEFAULT_CSDS_DATASET, help="Kaggle dataset slug in owner/name format.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List files available in the dataset.")
    list_parser.add_argument("--page-size", type=int, default=100)
    list_parser.add_argument("--page-token")
    list_parser.add_argument(
        "--show-recommended",
        action="store_true",
        help="Print the minimal CSDS file set needed for the research adapter.",
    )

    download_parser = subparsers.add_parser("download", help="Download a single dataset file.")
    download_parser.add_argument("--file", required=True, help="Exact file name returned by the list command.")
    download_parser.add_argument("--output-dir", default=str(Path("research") / "data" / "raw" / "csds"))
    download_parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        files, next_page_token = list_dataset_files(
            dataset=args.dataset,
            page_token=args.page_token,
            page_size=args.page_size,
        )
        for item in files:
            size = item.size_bytes if item.size_bytes is not None else "-"
            created = item.creation_date or "-"
            print(f"{item.name}\t{size}\t{created}")
        if args.show_recommended:
            print("\nRecommended minimal CSDS file set:")
            for name in recommended_csds_files():
                print(name)
        if next_page_token:
            print(f"\nNext page token: {next_page_token}")
        return

    if args.command == "download":
        destination = download_dataset_file(
            file_name=args.file,
            dataset=args.dataset,
            output_dir=args.output_dir,
            force=args.force,
        )
        print(destination)
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
