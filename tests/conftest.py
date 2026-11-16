import sys
from pathlib import Path

# Make `import src.xxx` work when running pytest from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
