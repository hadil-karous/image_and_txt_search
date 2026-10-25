"""Inspect ZIP directories and a few tiny numeric payloads; never extract members."""
import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path
from backend.config import get_settings
from src.feature_store import atomic_json,file_hash
from src.mpeg7_loader import FAMILIES,parse_descriptor


def inspect_archive(path,method):
    family=FAMILIES[method]
    folder=family['folder']
    report=dict(archive=str(path),size_bytes=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns,
                sha256=file_hash(path))
    with zipfile.ZipFile(path) as archive:
        report['entries']=len(archive.infolist())
        report['files']=sum(not i.is_dir() for i in archive.infolist())
        report['uncompressed_bytes']=sum(i.file_size for i in archive.infolist() if not i.is_dir())
        report['suffix_counts']=dict(Counter(Path(i.filename).suffix for i in archive.infolist() if not i.is_dir()))
        labels=archive.read(f'{folder}/feature_names.txt').decode('utf-8')
        report['feature_names']=[s.strip() for s in labels.splitlines() if s.strip()]
        report['dimension']=len(report['feature_names'])
        report['samples']=[]
        for source_id in (0,1,9,99,9999,10000,24999,999999):
            member=f'{folder}/{source_id//10000}/{source_id}.txt'
            try:
                info=archive.getinfo(member)
            except KeyError:
                continue
            if info.file_size>65536:
                raise ValueError('Sample payload exceeds safety limit')
            vector=parse_descriptor(archive.read(info),family['dimension'])
            report['samples'].append(dict(name=member,size=info.file_size,dimension=len(vector),
                                          first_values=vector[:8].tolist()))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir',type=Path)
    args=parser.parse_args()
    folder=args.archive_dir or get_settings().dataset('mirflickr_1m').descriptors
    reports=[]
    for method,family in FAMILIES.items():
        path=folder/(family['folder']+'.zip')
        report=inspect_archive(path,method)
        reports.append(report)
        print(path.name,report['files'],'files;',report['dimension'],'values per descriptor',flush=True)
    atomic_json(Path('benchmarks/mpeg7_inspection.json'),reports)


if __name__=='__main__':
    main()
