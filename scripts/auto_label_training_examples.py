"""CLI wrapper for khmer_transliteration.auto_label_training."""

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from khmer_transliteration.auto_label_training import main


if __name__ == "__main__":
    # Keep this thin so the reusable logic stays importable from the package.
    main()
