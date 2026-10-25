"""Chemins du projet ; aucun accès aux données ni création à l'import."""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    value = os.environ.get("IMAGE_SEARCH_DATA_DIR")
    if value is not None and not value.strip():
        raise ValueError("IMAGE_SEARCH_DATA_DIR ne doit pas être vide")
    path = Path(value).expanduser() if value else PROJECT_ROOT / "data"
    # Les chemins relatifs sont toujours relatifs au projet, pas au terminal.
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


@dataclass(frozen=True)
class DatasetPaths:
    root: Path

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def annotations(self) -> Path:
        return self.root / "annotations"

    @property
    def descriptors(self) -> Path:
        return self.root / "descriptors"


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def dataset(self, name: str) -> DatasetPaths:
        if name not in {"objects", "mirflickr_1m", "mirflickr_25k"}:
            raise ValueError(f"Base inconnue : {name}")
        return DatasetPaths(self.raw_dir / name)

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.sqlite3"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "processed" / "vectors"

    @property
    def indexes_dir(self) -> Path:
        return self.data_dir / "processed" / "indexes"


def get_settings() -> Settings:
    """Relit l'environnement à chaque appel, sans créer de fichier."""
    return Settings(data_dir=_data_root())
