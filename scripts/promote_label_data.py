"""CLI wrapper for promoting reviewed label_data rows."""

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from khmer_transliteration.label_review import main


if __name__ == "__main__":
    main()
