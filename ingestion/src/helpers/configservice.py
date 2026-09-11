from pathlib import Path
import yaml

def load_config(path: str | Path | None = None):
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "config.yml"

    with Path(path).open() as f:
        return yaml.safe_load(f)