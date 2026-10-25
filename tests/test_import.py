from src.data_loader import import_dataset
from src.database import connect, image_rows


def test_idempotent_stable_import(sample):
    first=import_dataset(sample,'mirflickr_25k',limit=3,batch_size=2)
    with connect(sample.catalog_path) as db:
        before=[(r['id'],r['source_id']) for r in image_rows(db,'mirflickr_25k')]
    import_dataset(sample,'mirflickr_25k')
    import_dataset(sample,'mirflickr_25k')
    with connect(sample.catalog_path) as db:
        rows=image_rows(db,'mirflickr_25k')
        assert [(r['id'],r['source_id']) for r in rows[:3]]==before
        assert len(rows)==6
        assert db.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT COUNT(*) FROM image_fts').fetchone()[0]==6
    assert first['annotations_outside_selection']==3


def test_corrupt_and_orphan(sample):
    paths=sample.dataset('mirflickr_25k')
    (paths.images/'im7.jpg').write_bytes(b'invalid')
    (paths.annotations/'meta/tags/tags99.txt').write_text('orphan')
    report=import_dataset(sample,'mirflickr_25k')
    assert report['imported']==6
    assert len(report['unreadable'])==1
    assert report['orphan_annotations']==['99']


def test_raw_tags_are_not_confused(sample):
    raw=sample.dataset('mirflickr_25k').annotations/'meta/tags_raw'
    raw.mkdir()
    (raw/'tags1.txt').write_text('different raw tag')
    assert import_dataset(sample,'mirflickr_25k')['imported']==6
    with connect(sample.catalog_path) as db:
        assert db.execute("SELECT COUNT(*) FROM tags WHERE name='different raw tag'").fetchone()[0]==0
