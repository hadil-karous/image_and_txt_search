"""Import only verified catalogue members from the two observed MPEG-7 ZIP formats.

No extraction, no fabricated identifiers, no change to the supplied raw values.
"""
import json
import hashlib
import re
import time
import zipfile
from pathlib import Path

import numpy as np

from src.database import catalog_signature,connect,image_rows
from src.feature_store import atomic_json,file_hash,fingerprint

FAMILIES={
    'mpeg7_edgehistogram':dict(folder='features_edgehistogram',dimension=150),
    'mpeg7_homogeneoustexture':dict(folder='features_homogeneoustexture',dimension=43),
}
PARAMETERS=dict(format_version=1,representation='raw_float32',search_transform='row_l2_on_load',
                distance='euclidean',distance_scale=2.0)


def validate_spec(metadata,method):
    spec=metadata['spec']
    if method not in FAMILIES or spec.get('kind')!='mpeg7_zip' or spec.get('method')!=method:
        raise ValueError('Famille MPEG-7 incompatible')
    if spec.get('parameters')!=PARAMETERS or metadata['dimension']!=FAMILIES[method]['dimension']:
        raise ValueError('Paramètres MPEG-7 incompatibles')
    if not spec.get('mapping_signature') or metadata.get('mapping_status')!='verified':
        raise ValueError('Correspondance MPEG-7 non vérifiée')


def load_mapping(path,rows):
    evidence=json.loads(Path(path).read_text(encoding='utf-8'))
    value=dict(evidence)
    signature=value.pop('signature',None)
    if not signature or fingerprint(value)!=signature:
        raise ValueError('Empreinte de correspondance invalide')
    if evidence.get('status')!='verified' or evidence.get('dataset')!='mirflickr_25k':
        raise ValueError('Correspondance image/descripteur non vérifiée')
    if evidence.get('catalog_signature')!=catalog_signature(rows):
        raise ValueError('Correspondance obsolète : catalogue modifié')
    by_id={r['id']:r for r in rows}
    seen=set()
    for item in evidence['mapping']:
        image_id=item['image_id']
        if image_id not in by_id or item['source_id']!=by_id[image_id]['source_id'] or image_id in seen:
            raise ValueError('Identifiants de correspondance invalides ou dupliqués')
        if type(item['descriptor_id']) is not int or not 0<=item['descriptor_id']<1000000:
            raise ValueError('Identifiant source MPEG-7 invalide')
        seen.add(image_id)
    if len(seen)!=evidence['matched'] or not seen:
        raise ValueError('Couverture de correspondance invalide')
    return evidence


def parse_descriptor(payload,dimension):
    if len(payload)>65536:
        raise ValueError('Descripteur trop volumineux')
    lines=[line.strip() for line in payload.decode('ascii').splitlines() if line.strip()]
    if len(lines)!=dimension or any(len(line.split())!=1 for line in lines):
        raise ValueError(f'Dimension incorrecte : {len(lines)}, attendu {dimension}')
    values=np.array([float(line) for line in lines],dtype=np.float64)
    if not np.isfinite(values).all() or np.any(np.abs(values)>np.finfo(np.float32).max):
        raise ValueError('Valeurs non finies ou non représentables en float32')
    return values.astype(np.float32)


def import_mpeg7(settings,method,archive_path,mapping_path):
    if method not in FAMILIES:
        raise ValueError('Famille MPEG-7 inconnue')
    started=time.perf_counter()
    dataset='mirflickr_25k'
    with connect(settings.catalog_path) as db:
        rows=image_rows(db,dataset)
    evidence=load_mapping(mapping_path,rows)
    archive_path=Path(archive_path)
    before=archive_path.stat()
    digest=file_hash(archive_path)
    family=FAMILIES[method]
    folder,dimension=family['folder'],family['dimension']
    mapping=sorted(evidence['mapping'],key=lambda r:r['image_id'])
    vectors=np.empty((len(mapping),dimension),dtype=np.float32)
    ids=[]
    missing=[]
    invalid=[]
    payloads_read=0
    with zipfile.ZipFile(archive_path,'r') as archive:
        labels_info=archive.getinfo(f'{folder}/feature_names.txt')
        if labels_info.file_size>65536:
            raise ValueError('Documentation de dimensions trop volumineuse')
        labels_payload=archive.read(labels_info)
        labels=[line.strip() for line in labels_payload.decode('utf-8').splitlines() if line.strip()]
        if len(labels)!=dimension:
            raise ValueError('Dimensions différentes de la documentation observée')
        # The ZIP directory is scanned, but only selected descriptor payloads are read.
        selected={item['descriptor_id'] for item in mapping}
        occurrences={}
        pattern=re.compile(re.escape(folder)+r'/(\d+)/(\d+)\.txt')
        descriptor_files=0
        for info in archive.infolist():
            match=pattern.fullmatch(info.filename)
            if match:
                descriptor_files+=1
                source_id=int(match[2])
                if source_id in selected:
                    if int(match[1])!=source_id//10000:
                        raise ValueError('Arborescence MPEG-7 incohérente')
                    occurrences[source_id]=occurrences.get(source_id,0)+1
        if any(count!=1 for count in occurrences.values()):
            raise ValueError('Membres ZIP dupliqués pour des identifiants sélectionnés')
        for n,item in enumerate(mapping):
            source_id=item['descriptor_id']
            name=f'{folder}/{source_id//10000}/{source_id}.txt'
            try:
                info=archive.getinfo(name)
            except KeyError:
                missing.append(dict(image_id=item['image_id'],descriptor_id=source_id))
                continue
            try:
                if info.file_size>65536:
                    raise ValueError('Taille de membre excessive')
                payload=archive.read(info)
                payloads_read+=1
                vector=parse_descriptor(payload,dimension)
            except (ValueError,UnicodeError,zipfile.BadZipFile) as exc:
                invalid.append(dict(image_id=item['image_id'],descriptor_id=source_id,error=str(exc)))
                continue
            vectors[len(ids)]=vector
            ids.append(item['image_id'])
            if (n+1)%5000==0:
                print(f'{method}: {n+1}/{len(mapping)} membres sélectionnés',flush=True)
    after=archive_path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Archive modifiée pendant la lecture')
    if not ids:
        raise ValueError('Aucun vecteur MPEG-7 vérifié disponible')
    spec=dict(version=1,kind='mpeg7_zip',method=method,parameters=PARAMETERS,
        catalog_signature=catalog_signature(rows),archive_sha256=digest,
        feature_names_sha256=hashlib.sha256(labels_payload).hexdigest(),
        mapping_signature=evidence['signature'])
    generation=fingerprint(spec)
    directory=settings.vectors_dir/dataset/method
    work=directory/generation
    work.mkdir(parents=True,exist_ok=True)
    # A compatible published generation is immutable, including on Windows.
    manifest=directory/'manifest.json'
    if manifest.exists():
        from src.feature_store import FeatureStore
        try:
            current=FeatureStore(settings,dataset,method,rows=rows)
            if current.metadata['spec']==spec:
                return current.metadata
        except (OSError,ValueError,KeyError):
            pass
    for name,values in [('vectors',vectors[:len(ids)]),('ids',np.array(ids,dtype=np.int64))]:
        temp=work/f'{name}.pending'
        with temp.open('wb') as stream:
            np.save(stream,values,allow_pickle=False)
        temp.replace(work/f'{name}.npy')
    raw_hash=file_hash(work/'vectors.npy')
    metadata=dict(spec=spec,generation=generation,count=len(ids),dimension=dimension,
        total_catalog=len(rows),mapping_status='verified',mapping_matched=evidence['matched'],
        unmapped_images=len(rows)-len(mapping),unmapped_image_ids=sorted({r['id'] for r in rows}-{r['image_id'] for r in mapping}),
        missing_descriptors=missing,invalid_descriptors=invalid,archive=str(archive_path),
        archive_entries=descriptor_files,descriptor_payloads_read=payloads_read,
        feature_names=labels,vector_sha256=raw_hash,
        raw_min=float(vectors[:len(ids)].min()),raw_max=float(vectors[:len(ids)].max()),
        seconds=time.perf_counter()-started)
    metadata['signature']=fingerprint(dict(spec=spec,ids=ids,vectors=raw_hash))
    atomic_json(manifest,metadata)
    return metadata
