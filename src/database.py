"""Catalogue de références ; aucune image n'est stockée en SQLite."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager


@contextmanager
def connect(path):
    connection = sqlite3.connect(str(path), timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS datasets (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, root TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES datasets(id),
            source_id TEXT NOT NULL, relative_path TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
            metadata_json TEXT NOT NULL, UNIQUE(dataset_id, source_id));
        CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS image_tags (
            image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            PRIMARY KEY(image_id,tag_id));
        CREATE INDEX IF NOT EXISTS idx_images_dataset ON images(dataset_id,id);
        CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag_id,image_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS image_fts USING fts5(
            tags, tokenize='unicode61 remove_diacritics 2');
        ''')


def image_rows(db, dataset):
    return db.execute('''SELECT i.*, d.name AS dataset, d.root FROM images i
        JOIN datasets d ON d.id=i.dataset_id WHERE d.name=? ORDER BY i.id''',
        (dataset,)).fetchall()


def catalog_signature(rows):
    """Empreinte des données qui influencent les vecteurs, sans les tags."""
    data = [(r['id'], r['relative_path'], r['size_bytes'], r['mtime_ns']) for r in rows]
    return hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()


def resolve_image(row, settings):
    # La racine est reconstruite depuis la configuration pour faciliter le transfert.
    root = settings.dataset(row['dataset']).root.resolve()
    path = (root / row['relative_path']).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
        raise ValueError("Chemin image hors de la base autorisée")
    return path
