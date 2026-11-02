"""Run unittest regressions, failing on empty discovery or background exceptions."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-directory", default="tests")
    parser.add_argument("--pattern", default="test_*.py")
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    start_directory = Path(arguments.start_directory)
    if not start_directory.is_absolute():
        start_directory = root / start_directory

    background_errors: list[str] = []
    original_hook = threading.excepthook

    def record_thread_error(error: threading.ExceptHookArgs) -> None:
        background_errors.append(f"{error.exc_type.__name__}: {error.exc_value}")
        original_hook(error)

    threading.excepthook = record_thread_error
    try:
        suite = unittest.defaultTestLoader.discover(
            str(start_directory), pattern=arguments.pattern
        )
        if suite.countTestCases() == 0:
            print("ERROR: test discovery found no tests.", file=sys.stderr)
            return 1
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if background_errors:
            print(
                f"ERROR: {len(background_errors)} unhandled background thread exception(s).",
                file=sys.stderr,
            )
        return 0 if result.wasSuccessful() and not background_errors else 1
    finally:
        threading.excepthook = original_hook


if __name__ == "__main__":
    raise SystemExit("Intentional CI gate probe; never merge.")
