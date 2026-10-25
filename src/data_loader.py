"""Import progressif MIRFLICKR (imN/tagsN) ou images Objects sans tags inventés."""
import json
import re
import time
from pathlib import Path

from PIL import Image

from src.database import connect, initialize

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def discover(root):
    return sorted((p for p in root.rglob('*') if p.suffix.lower() in EXTENSIONS),
                  key=lambda p: (int(re.search(r'\d+', p.stem)[0])
                                 if re.fullmatch(r'im\d+', p.stem) else 10**12, str(p)))


def import_dataset(settings, dataset, limit=None, batch_size=250):
    if limit is not None and limit < 1 or batch_size < 1:
        raise ValueError("Limite et taille de lot doivent être positives")
    paths = settings.dataset(dataset)
    files = discover(paths.images)
    if not files:
        raise ValueError(f"Aucune image dans {paths.images}")
    # Aucun rapprochement implicite entre MIRFLICKR-1M et MIRFLICKR-25K.
    tag_files = {}
    if dataset == 'mirflickr_25k':
        for folder in [paths.annotations, paths.images]:
            for p in folder.rglob('tags*.txt'):
                # tags_raw contient aussi des tagsN.txt : ne pas les confondre
                # avec les tags normalisés décrits et utilisés par la collection.
                if p.parent.name != 'tags':
                    continue
                match = re.fullmatch(r'tags(\d+)', p.stem)
                if match:
                    sid = str(int(match[1]))
                    if sid in tag_files and tag_files[sid].read_bytes() != p.read_bytes():
                        raise ValueError(f"Annotations contradictoires pour {sid}")
                    tag_files[sid] = p
    ids = [str(int(p.stem[2:])) if dataset == 'mirflickr_25k' and re.fullmatch(r'im\d+', p.stem)
           else p.relative_to(paths.images).with_suffix('').as_posix() for p in files]
    if len(set(ids)) != len(ids):
        raise ValueError("Identifiants source dupliqués : import arrêté sans écrasement")
    initialize(settings.catalog_path)
    report = dict(dataset=dataset, discovered=len(files), imported=0, unreadable=[],
                  orphan_annotations=sorted(set(tag_files)-set(ids)),
                  annotations_outside_selection=len(set(tag_files)-set(ids[:limit])),
                  annotated=0, annotation_kind='user_tags' if tag_files else 'none')
    started = time.perf_counter()
    with connect(settings.catalog_path) as db:
        db.execute('INSERT INTO datasets(name,root) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET root=excluded.root',
                   (dataset, str(paths.root)))
        dataset_id = db.execute('SELECT id FROM datasets WHERE name=?', (dataset,)).fetchone()[0]
        for p, source_id in list(zip(files, ids))[:limit]:
            try:
                with Image.open(p) as image:
                    image.load()
                    width, height = image.size
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                report['unreadable'].append({'path':str(p), 'error':str(exc)})
                continue
            metadata = {}
            tag_path = tag_files.get(source_id)
            tags = []
            if tag_path:
                tags = sorted(set(t.strip().casefold() for t in tag_path.read_text(encoding='utf-8', errors='replace').splitlines() if t.strip()))
                metadata['annotation_kind'] = 'user_tags'
                metadata['tag_source'] = tag_path.relative_to(paths.root).as_posix()
                report['annotated'] += bool(tags)
                for name in ('exif', 'license'):
                    extra = tag_path.parent.parent / name / f'{name}{source_id}.txt'
                    if extra.is_file():
                        metadata[name] = extra.read_text(encoding='utf-8', errors='replace')
            stat = p.stat()
            db.execute('''INSERT INTO images(dataset_id,source_id,relative_path,width,height,size_bytes,mtime_ns,metadata_json)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(dataset_id,source_id) DO UPDATE SET
                relative_path=excluded.relative_path,width=excluded.width,height=excluded.height,
                size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,metadata_json=excluded.metadata_json''',
                (dataset_id, source_id, p.relative_to(paths.root).as_posix(), width, height,
                 stat.st_size, stat.st_mtime_ns, json.dumps(metadata, ensure_ascii=False)))
            image_id = db.execute('SELECT id FROM images WHERE dataset_id=? AND source_id=?', (dataset_id, source_id)).fetchone()[0]
            db.execute('DELETE FROM image_tags WHERE image_id=?', (image_id,))
            db.executemany('INSERT OR IGNORE INTO tags(name) VALUES (?)', [(t,) for t in tags])
            db.executemany('INSERT INTO image_tags(image_id,tag_id) SELECT ?,id FROM tags WHERE name=?', [(image_id,t) for t in tags])
            db.execute('DELETE FROM image_fts WHERE rowid=?', (image_id,))
            db.execute('INSERT INTO image_fts(rowid,tags) VALUES (?,?)', (image_id, ' '.join(tags)))
            report['imported'] += 1
            if report['imported'] % batch_size == 0:
                db.commit()
                print(f"Import : {report['imported']}/{min(len(files), limit or len(files))}", flush=True)
    report['seconds'] = time.perf_counter()-started
    return report
