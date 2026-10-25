"""Verify content identities against the official 1M image ZIP without extracting it.

Only its central directory and a few JPEG payloads are transferred (32 MiB cap).
Catalogue images are compared by (CRC32,size), independent of filenames/order.
SHA-256 checks of distributed examples corroborate the exact image identity.
"""
import argparse
import hashlib
import json
import re
import zipfile
import zlib
from io import BytesIO
from PIL import Image,ImageOps
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

from backend.config import get_settings
from src.database import catalog_signature,connect,image_rows,resolve_image
from src.feature_store import atomic_json,fingerprint
from src.remote_zip import RangeReader

OFFICIAL_IMAGES='https://press.liacs.nl/mirflickr/mirflickr1m.v3b/images0.zip'
DOCUMENTATION='https://press.liacs.nl/mirflickr/mirdownload.html'


def verify(settings,url=OFFICIAL_IMAGES,output=Path('data/processed/mpeg7_mapping.json')):
    with connect(settings.catalog_path) as db:
        rows=image_rows(db,'mirflickr_25k')
    if not rows:
        raise ValueError('Import MIRFLICKR-25K first')
    by_content=defaultdict(list)
    with RangeReader(url) as remote,zipfile.ZipFile(remote) as archive:
        # No descriptor/row-order assumption is used to find an image counterpart.
        for info in archive.infolist():
            match=re.fullmatch(r'images/(\d+)/(\d+)\.jpg',info.filename)
            if match:
                by_content[(info.CRC,info.file_size)].append((int(match[2]),info.filename))
        mapping=[]
        missing=[]
        ambiguous=[]
        local_hashes={}
        for n,row in enumerate(rows):
            path=resolve_image(row,settings)
            stat=path.stat()
            if (stat.st_size,stat.st_mtime_ns)!=(row['size_bytes'],row['mtime_ns']):
                raise ValueError('Image changed since catalogue import')
            data=path.read_bytes()
            crc=zlib.crc32(data)&0xffffffff
            matches=by_content.get((crc,len(data)),[])
            if not matches:
                missing.append(row['id'])
                continue
            if len(matches)!=1:
                # Never silently choose by name when duplicate content is ambiguous.
                ambiguous.append(dict(image_id=row['id'],candidates=matches))
                continue
            descriptor_id,member=matches[0]
            local_hashes[row['id']]=hashlib.sha256(data).hexdigest()
            mapping.append(dict(image_id=row['id'],source_id=row['source_id'],
                descriptor_id=descriptor_id,reference_member=member,size_bytes=len(data),
                crc32=f'{crc:08x}',image_sha256=local_hashes[row['id']]))
            if (n+1)%5000==0:
                print(f'Content matches: {n+1}/{len(rows)}',flush=True)
        exceptions=[]
        # The offset is corroborated by thousands of independent content matches.
        # For byte mismatches, require exact decoded RGB identity, not visual resemblance.
        offset_confirmed=len(mapping)>100 and all(r['descriptor_id']==int(r['source_id'])-1 for r in mapping)
        unresolved=[]
        unresolved_ambiguous=[]
        if offset_confirmed:
            by_id={r['id']:r for r in rows}
            for image_id in missing+[r['image_id'] for r in ambiguous]:
                row=by_id[image_id]
                descriptor_id=int(row['source_id'])-1
                member=f'images/{descriptor_id//10000}/{descriptor_id}.jpg'
                local=resolve_image(row,settings).read_bytes()
                try:
                    reference=archive.read(member)
                except KeyError:
                    unresolved.append(image_id)
                    continue
                exact=hashlib.sha256(local).digest()==hashlib.sha256(reference).digest()
                def pixels(data):
                    with Image.open(BytesIO(data)) as image:
                        rgb=ImageOps.exif_transpose(image).convert('RGB')
                        return rgb.size,hashlib.sha256(rgb.tobytes()).hexdigest()
                local_pixels,reference_pixels=pixels(local),pixels(reference)
                verified=exact or local_pixels==reference_pixels
                exceptions.append(dict(image_id=image_id,descriptor_id=descriptor_id,member=member,
                    byte_identical=exact,decoded_pixels_identical=local_pixels==reference_pixels,
                    local_pixel_sha256=local_pixels[1],reference_pixel_sha256=reference_pixels[1]))
                if verified:
                    mapping.append(dict(image_id=image_id,source_id=row['source_id'],descriptor_id=descriptor_id,
                        reference_member=member,size_bytes=len(local),crc32=f'{zlib.crc32(local)&0xffffffff:08x}',
                        image_sha256=hashlib.sha256(local).hexdigest(),
                        identity_check='sha256_bytes' if exact else 'sha256_decoded_rgb'))
                else:
                    unresolved.append(image_id)
            mapping.sort(key=lambda r:r['image_id'])
            missing,ambiguous=unresolved,unresolved_ambiguous
        checks=[]
        # Include first/last images, folder boundaries and reproducible interior points.
        requested={1,2,10,100,9999,10000,10001,10002,19999,20000,20001,20002,24999,25000}
        selected=[r for r in mapping if r['source_id'].isdigit() and int(r['source_id']) in requested]
        for row in selected:
            data=archive.read(row['reference_member'])
            digest=hashlib.sha256(data).hexdigest()
            if digest!=row['image_sha256']:
                raise ValueError('Remote SHA-256 identity check failed')
            checks.append(dict(image_id=row['image_id'],source_id=row['source_id'],
                               descriptor_id=row['descriptor_id'],member=row['reference_member'],sha256=digest))
        status='verified' if mapping and len(checks)>=2 else 'unverified'
        evidence=dict(status=status,dataset='mirflickr_25k',catalog_signature=catalog_signature(rows),
            documentation_url=DOCUMENTATION,reference_url=url,reference_archive_size=remote.size,
            verification='content CRC32+length; SHA256 examples and exact byte/pixel checks for exceptions',
            matched=len(mapping),coverage_complete=len(mapping)==len(rows),missing=missing,
            ambiguous=ambiguous,exception_checks=exceptions,sha256_checks=checks,
            transferred_bytes=remote.downloaded,range_requests=len(remote.ranges),
            zero_based_offset_minus_one=all(r['descriptor_id']==int(r['source_id'])-1 for r in mapping),
            checked_at_utc=datetime.now(timezone.utc).isoformat(),mapping=mapping)
    evidence['signature']=fingerprint(evidence)
    atomic_json(output,evidence)
    summary={k:v for k,v in evidence.items() if k not in ('mapping','sha256_checks')}
    summary['sha256_examples']=len(checks)
    atomic_json(Path('benchmarks/mpeg7_mapping_verification.json'),summary)
    print(json.dumps(summary,indent=2),flush=True)
    if status!='verified':
        raise ValueError('No reliable mapping established; descriptors must remain disabled')
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    settings=get_settings()
    verify(settings,output=args.output or settings.data_dir/'processed/mpeg7_mapping.json')


if __name__=='__main__':
    main()
