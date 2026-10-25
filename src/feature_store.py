"""Caches versionnés, reprise par lots et publication atomique d'un manifeste."""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import skimage
from PIL import Image, __version__ as pillow_version

from src.database import catalog_signature, connect, image_rows, resolve_image
from src.descriptors import DescriptorConfig, METHODS, SEARCH_METHODS, describe

FEATURE_VERSION = 1


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def specification(rows, method, config):
    return dict(version=FEATURE_VERSION, method=method, parameters=config.parameters(),
                catalog_signature=catalog_signature(rows), skimage=skimage.__version__,
                pillow=pillow_version, numpy=np.__version__)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


class FeatureStore:
    def __init__(self, settings, dataset, method, rows=None, config=None):
        if method not in SEARCH_METHODS:
            raise ValueError('Descripteur inconnu')
        directory = settings.vectors_dir / dataset / method
        self.metadata = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        if rows is None:
            with connect(settings.catalog_path) as db:
                rows = image_rows(db, dataset)
        if self.metadata['spec']['catalog_signature'] != catalog_signature(rows):
            raise ValueError('Cache obsolète : réimport du catalogue, relancer l’extraction')
        if self.metadata['spec']['version'] != FEATURE_VERSION:
            raise ValueError('Version de cache incompatible')
        self.distance_scale = float(np.sqrt(2))
        if method in METHODS:
            stored_config = DescriptorConfig(**self.metadata['spec']['parameters'])
            expected = specification(rows, method, config or stored_config)
            if self.metadata['spec'] != expected:
                raise ValueError('Paramètres ou bibliothèques du cache incompatibles')
        else:
            from src.mpeg7_loader import validate_spec
            validate_spec(self.metadata,method)
            self.distance_scale = 2.0
        generation = self.metadata['generation']
        if not generation.isalnum():
            raise ValueError('Nom de génération invalide')
        self.ids = np.load(directory/generation/'ids.npy', allow_pickle=False)
        if file_hash(directory/generation/'vectors.npy') != self.metadata['vector_sha256']:
            raise ValueError('Empreinte des vecteurs incompatible : cache altéré')
        self.vectors = np.load(directory/generation/'vectors.npy', mmap_mode='r', allow_pickle=False)
        if self.ids.ndim != 1 or not np.issubdtype(self.ids.dtype,np.integer) or self.vectors.ndim != 2 or len(self.ids) != len(self.vectors):
            raise ValueError('Alignement vecteurs/identifiants incorrect')
        if len(np.unique(self.ids)) != len(self.ids) or not set(self.ids).issubset({r['id'] for r in rows}):
            raise ValueError('Identifiants de cache invalides')
        if self.vectors.shape[1] != self.metadata['dimension'] or not np.isfinite(self.vectors).all():
            raise ValueError('Valeurs de cache invalides')
        expected_signature = fingerprint(dict(spec=self.metadata['spec'],ids=self.ids.tolist(),
                                              vectors=self.metadata['vector_sha256']))
        if self.metadata['signature'] != expected_signature or self.metadata['count'] != len(self.ids):
            raise ValueError('Signature ou nombre des identifiants incompatible')
        self.positions = {int(i):n for n,i in enumerate(self.ids)}
        self.signature = self.metadata['signature']
        if method not in METHODS:
            # Raw supplied values stay unchanged on disk. This explicit adapter
            # supplies a fixed, bounded Euclidean geometry for search and fusion.
            raw = np.asarray(self.vectors,dtype=np.float64)
            norms = np.linalg.norm(raw,axis=1,keepdims=True)
            self.vectors = (raw/np.where(norms>0,norms,1)).astype(np.float32)


def extract_features(settings, dataset, methods=METHODS, limit=None, workers=4,
                     batch_size=250, config=DescriptorConfig()):
    if workers < 1 or batch_size < 1 or (limit is not None and limit < 1):
        raise ValueError('Limite, workers et taille de lot doivent être positifs')
    if not methods or not set(methods).issubset(METHODS):
        raise ValueError('Liste de descripteurs invalide')
    with connect(settings.catalog_path) as db:
        all_rows = image_rows(db, dataset)
    if not all_rows:
        raise ValueError('Importer la base avant extraction')
    rows = all_rows[:limit]
    reports = {}
    for method in methods:
        started = time.perf_counter()
        spec = specification(all_rows, method, config)
        # La génération dépend aussi de la sélection ; les lots sont réutilisables à la reprise.
        generation = fingerprint(dict(spec=spec, ids=[r['id'] for r in rows]))
        directory = settings.vectors_dir/dataset/method
        if (directory/'manifest.json').is_file():
            try:
                current = FeatureStore(settings,dataset,method,rows=all_rows,config=config)
                if current.metadata['generation'] == generation:
                    reports[method] = current.metadata
                    print(f'{method}: génération déjà complète ({len(current.ids)} vecteurs)',flush=True)
                    continue
            except (OSError,ValueError,KeyError):
                pass
        work = directory/generation
        work.mkdir(parents=True, exist_ok=True)

        def process(row):
            try:
                path = resolve_image(row, settings)
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (row['size_bytes'], row['mtime_ns']):
                    raise ValueError('Source modifiée depuis l’import : réimporter')
                with Image.open(path) as image:
                    return row['id'], describe(image, method, config), None
            except (OSError, ValueError) as exc:
                return row['id'], None, str(exc)

        chunks = []
        errors = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(rows), batch_size):
                part = rows[start:start+batch_size]
                chunk = work/f'batch_{start:08d}_{batch_size}.npz'
                error_file = chunk.with_suffix('.json')
                if not chunk.exists():
                    result = list(pool.map(process, part))
                    good = [(i,v) for i,v,e in result if v is not None]
                    failed = [dict(id=i,error=e) for i,v,e in result if e]
                    dimension = len(describe(Image.new('RGB',(config.size,config.size)),method,config))
                    vectors = np.stack([v for _,v in good]) if good else np.empty((0,dimension),dtype=np.float32)
                    # Métadonnées d'erreur avant publication du lot.
                    atomic_json(error_file, failed)
                    temp = chunk.with_suffix('.tmp')
                    with temp.open('wb') as stream:
                        np.savez(stream, ids=np.array([i for i,_ in good],dtype=np.int64), vectors=vectors)
                    os.replace(temp,chunk)
                chunks.append(chunk)
                errors.extend(json.loads(error_file.read_text(encoding='utf-8')))
                print(f'{method}: {min(start+batch_size,len(rows))}/{len(rows)}',flush=True)
        id_parts = []
        dimension = 0
        for chunk in chunks:
            with np.load(chunk, allow_pickle=False) as data:
                id_parts.append(data['ids'])
                dimension = data['vectors'].shape[1]
        ids = np.concatenate(id_parts)
        if not len(ids):
            raise ValueError(f'Aucun vecteur valide : {errors[:3]}')
        vectors_path = work/'vectors.npy'
        temp_vectors = work/'vectors.pending.npy'
        array = np.lib.format.open_memmap(temp_vectors, mode='w+', dtype=np.float32, shape=(len(ids),dimension))
        offset = 0
        for chunk in chunks:
            with np.load(chunk, allow_pickle=False) as data:
                values = data['vectors']
                array[offset:offset+len(values)] = values
                offset += len(values)
        array.flush()
        del array
        os.replace(temp_vectors, vectors_path)
        np.save(work/'ids.npy',ids,allow_pickle=False)
        metadata = dict(spec=spec, generation=generation, count=len(ids), total_catalog=len(all_rows),
                        dimension=dimension, errors=errors, seconds=time.perf_counter()-started,
                        vector_sha256=file_hash(vectors_path))
        metadata['signature'] = fingerprint(dict(spec=spec,ids=ids.tolist(),vectors=metadata['vector_sha256']))
        atomic_json(directory/'manifest.json', metadata)
        reports[method] = metadata
    return reports
