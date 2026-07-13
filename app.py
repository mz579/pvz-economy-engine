"""V2.0 Streamlit entry point.

Batch 1 keeps the existing dashboard available through a stable root command.
Batch 6 will replace this compatibility bridge with the V2.0 presentation layer.
"""

from pathlib import Path
import runpy


LEGACY_APP = Path(__file__).resolve().parent / "src" / "app.py"


def main() -> None:
    """Execute the compatibility dashboard from a root-level entry point."""
    runpy.run_path(str(LEGACY_APP), run_name="__main__")


if __name__ == "__main__":
    main()
