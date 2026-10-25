import argparse
from pathlib import Path
from backend.config import get_settings
from src.feature_store import atomic_json
from src.mpeg7_loader import FAMILIES,import_mpeg7


def main():
    parser=argparse.ArgumentParser(description='Read only verified catalogue descriptors directly from ZIP')
    parser.add_argument('--methods',nargs='+',choices=FAMILIES,default=list(FAMILIES))
    parser.add_argument('--mapping',type=Path)
    parser.add_argument('--archive-dir',type=Path)
    args=parser.parse_args()
    settings=get_settings()
    folder=args.archive_dir or settings.dataset('mirflickr_1m').descriptors
    mapping=args.mapping or settings.data_dir/'processed/mpeg7_mapping.json'
    report={}
    for method in args.methods:
        metadata=import_mpeg7(settings,method,folder/(FAMILIES[method]['folder']+'.zip'),mapping)
        report[method]={key:metadata[key] for key in ('count','dimension','total_catalog','mapping_matched',
            'unmapped_images','unmapped_image_ids','missing_descriptors','invalid_descriptors',
            'archive_entries','descriptor_payloads_read','seconds','signature','raw_min','raw_max')}
        print(method,metadata['count'],'images,',metadata['dimension'],'dimensions',flush=True)
    atomic_json(Path('benchmarks/mpeg7_import.json'),report)


if __name__=='__main__':
    main()
