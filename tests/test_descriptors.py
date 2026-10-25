import numpy as np
import pytest
from PIL import Image
from src.database import connect
from src.descriptors import DescriptorConfig, describe
from src.feature_store import FeatureStore, extract_features


@pytest.mark.parametrize('mode',['RGB','L','RGBA','LA','P'])
@pytest.mark.parametrize('method,dimension',[('hsv',128),('lbp',10),('hog',1764)])
def test_dimensions_finite(mode,method,dimension):
    vector=describe(Image.new(mode,(23,57)),method)
    assert vector.shape==(dimension,)
    assert np.isfinite(vector).all()
    assert np.linalg.norm(vector)<=1.000001


def test_alignment_resume_invalidation(prepared):
    store=FeatureStore(prepared,'mirflickr_25k','hsv')
    assert list(store.ids)==[1,2,3,4,5,6]
    extract_features(prepared,'mirflickr_25k',['hsv'],batch_size=2)
    assert np.array_equal(store.vectors,FeatureStore(prepared,'mirflickr_25k','hsv').vectors)
    with pytest.raises(ValueError,match='incompatibles'):
        FeatureStore(prepared,'mirflickr_25k','hsv',config=DescriptorConfig(hsv_bins=(4,4,4)))
    with connect(prepared.catalog_path) as db:
        db.execute('UPDATE images SET size_bytes=size_bytes+1 WHERE id=1')
    with pytest.raises(ValueError,match='obsolète'):
        FeatureStore(prepared,'mirflickr_25k','hsv')


def test_partial_coverage_and_altered_vectors(sample):
    from src.data_loader import import_dataset
    from src.visual_search import SearchEngine
    import_dataset(sample,'mirflickr_25k')
    extract_features(sample,'mirflickr_25k',['hsv'],limit=3,workers=1)
    engine=SearchEngine(sample)
    result=engine.search('mirflickr_25k',1,['hsv'])
    assert result['searchable_images']==3
    assert '3/6' in result['message']
    with pytest.raises(ValueError,match='absente'):
        engine.search('mirflickr_25k',6,['hsv'])
    store=engine.stores[('mirflickr_25k','hsv')]
    path=sample.vectors_dir/'mirflickr_25k/hsv'/store.metadata['generation']/'vectors.npy'
    # Altération d'une valeur finie, sans modifier taille ni dimension.
    array=np.load(path,mmap_mode='r+')
    array[0,0]+=0.01
    array.flush()
    del array
    with pytest.raises(ValueError,match='altéré'):
        FeatureStore(sample,'mirflickr_25k','hsv')


def test_reordered_ids_rejected(prepared):
    import json
    directory=prepared.vectors_dir/'mirflickr_25k/hsv'
    metadata=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    path=directory/metadata['generation']/'ids.npy'
    np.save(path,np.load(path)[::-1],allow_pickle=False)
    with pytest.raises(ValueError,match='Signature'):
        FeatureStore(prepared,'mirflickr_25k','hsv')
