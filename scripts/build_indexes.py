import argparse
import time
from pathlib import Path
from backend.config import get_settings
from src.descriptors import METHODS,SEARCH_METHODS
import json
from src.feature_store import FeatureStore, atomic_json
from src.vp_tree import VPTree


def main():
    p=argparse.ArgumentParser(description='Construction hors ligne des VP-Trees')
    p.add_argument('--dataset',default='mirflickr_25k')
    p.add_argument('--methods',nargs='+',choices=SEARCH_METHODS,default=list(METHODS))
    args=p.parse_args()
    settings=get_settings()
    report_path=Path('benchmarks/index_build.json')
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    for method in args.methods:
        start=time.perf_counter()
        store=FeatureStore(settings,args.dataset,method)
        load=time.perf_counter()-start
        start=time.perf_counter()
        tree=VPTree(store.vectors,store.ids)
        build=time.perf_counter()-start
        tree.save(settings.indexes_dir/args.dataset/f'{method}.npz',store.signature)
        report[method]=dict(count=len(store.ids),load_seconds=load,build_seconds=build)
        print(method,report[method],flush=True)
    atomic_json(report_path,report)


if __name__=='__main__':
    main()
