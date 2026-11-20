"""Download and install a verified Vydra profile outside the source tree."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vydra_core"))
from profile_install import main

if __name__ == "__main__":
    main()
