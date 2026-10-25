"""Essai réel isolé avant import principal, sans recopier les images sources."""
import gc
import tempfile
from pathlib import Path
from backend.config import Settings, get_settings
from src.data_loader import import_dataset
from src.database import connect, image_rows
from src.descriptors import METHODS
from src.feature_store import FeatureStore, atomic_json, extract_features
from src.visual_search import SearchEngine
from src.vp_tree import VPTree


def main():
    source=get_settings()
    class TrialSettings(Settings):
        def dataset(self,name):
            return source.dataset(name)
    with tempfile.TemporaryDirectory(prefix='prisme-real-subset-') as directory:
        trial=TrialSettings(Path(directory))
        first=import_dataset(trial,'mirflickr_25k',limit=32)
        with connect(trial.catalog_path) as db:
            ids=[(r['id'],r['source_id']) for r in image_rows(db,'mirflickr_25k')]
        second=import_dataset(trial,'mirflickr_25k',limit=32)
        with connect(trial.catalog_path) as db:
            assert ids==[(r['id'],r['source_id']) for r in image_rows(db,'mirflickr_25k')]
        assert first['imported']==second['imported']==32
        features=extract_features(trial,'mirflickr_25k',workers=4)
        for method in METHODS:
            store=FeatureStore(trial,'mirflickr_25k',method)
            tree=VPTree(store.vectors,store.ids)
            tree.save(trial.indexes_dir/'mirflickr_25k'/f'{method}.npz',store.signature)
        engine=SearchEngine(trial)
        for method in METHODS:
            exhaustive=engine.search('mirflickr_25k',ids[0][0],[method],k=10)
            indexed=engine.search('mirflickr_25k',ids[0][0],[method],k=10,method='indexed')
            assert exhaustive['matches']==indexed['matches']
        del store,tree,engine
        gc.collect()
    atomic_json(Path('benchmarks/subset_validation.json'),dict(status='passed',real_images=32,
        stable_reimport=True,exact_indexes=True,import_report=first,
        descriptors={m:dict(count=d['count'],dimension=d['dimension']) for m,d in features.items()}))
    print('Sous-ensemble réel : 32 imports stables, trois signatures et index exacts validés.')


if __name__=='__main__':
    main()
