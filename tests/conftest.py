import pytest
from PIL import Image
from backend.config import Settings
from src.data_loader import import_dataset
from src.feature_store import extract_features


@pytest.fixture
def sample(tmp_path):
    settings=Settings(tmp_path/'data')
    paths=settings.dataset('mirflickr_25k')
    paths.images.mkdir(parents=True)
    tags=paths.annotations/'meta'/'tags'
    tags.mkdir(parents=True)
    for n,color in enumerate(['red','red','blue','green','yellow','black'],1):
        image=Image.new('RGB',(40+n,32),color)
        # Motif non uniforme pour exercer aussi LBP et HOG.
        image.paste('white',(n,2,n+8,15))
        image.save(paths.images/f'im{n}.jpg')
        (tags/f'tags{n}.txt').write_text('sky\nwater' if n<4 else 'forest\ntree',encoding='utf-8')
    return settings


@pytest.fixture
def prepared(sample):
    import_dataset(sample,'mirflickr_25k')
    extract_features(sample,'mirflickr_25k',batch_size=2,workers=1)
    return sample
