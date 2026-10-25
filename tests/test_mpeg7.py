import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from src.database import catalog_signature,connect,image_rows
from src.feature_store import FeatureStore,atomic_json,file_hash,fingerprint
from src.mpeg7_loader import FAMILIES,import_mpeg7,load_mapping,parse_descriptor
from src.remote_zip import RangeReader
from src.visual_search import SearchEngine
from src.vp_tree import VPTree


@pytest.fixture
def mpeg7_source(prepared,tmp_path):
    with connect(prepared.catalog_path) as db:
        rows=image_rows(db,'mirflickr_25k')
    evidence=dict(status='verified',dataset='mirflickr_25k',catalog_signature=catalog_signature(rows),
        matched=3,mapping=[dict(image_id=i,source_id=str(i),descriptor_id=d)
                          for i,d in [(1,10),(3,20),(5,30)]])
    evidence['signature']=fingerprint(evidence)
    mapping=tmp_path/'mapping.json'
    atomic_json(mapping,evidence)
    method='mpeg7_edgehistogram'
    archive=tmp_path/'descriptors.zip'
    folder=FAMILIES[method]['folder']
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr(f'{folder}/feature_names.txt','\n'.join(f'eh {n}' for n in range(150)))
        for n in range(100):
            z.writestr(f'{folder}/0/{n}.txt','\n'.join(str((j+n)%151) for j in range(150)))
    return prepared,method,archive,mapping


def test_selective_import_alignment_and_immutable_sources(mpeg7_source,monkeypatch):
    settings,method,archive,mapping=mpeg7_source
    before=file_hash(archive)
    hsv=FeatureStore(settings,'mirflickr_25k','hsv')
    hsv_hash=hsv.metadata['vector_sha256']
    reads=[]
    original=zipfile.ZipFile.read
    def read(self,name,*args,**kwargs):
        reads.append(name.filename if isinstance(name,zipfile.ZipInfo) else name)
        return original(self,name,*args,**kwargs)
    def refuse(*args,**kwargs):
        raise AssertionError('ZIP extraction is forbidden')
    monkeypatch.setattr(zipfile.ZipFile,'read',read)
    monkeypatch.setattr(zipfile.ZipFile,'extract',refuse)
    monkeypatch.setattr(zipfile.ZipFile,'extractall',refuse)
    report=import_mpeg7(settings,method,archive,mapping)
    assert len(reads)==4  # one labels file + only the three mapped descriptors
    assert not any('/0/0.txt' in name for name in reads)
    assert report['count']==3 and report['dimension']==150
    assert report['unmapped_images']==3 and not report['missing_descriptors']
    assert file_hash(archive)==before
    assert FeatureStore(settings,'mirflickr_25k','hsv').metadata['vector_sha256']==hsv_hash
    store=FeatureStore(settings,'mirflickr_25k',method)
    assert store.ids.tolist()==[1,3,5]
    raw=np.load(settings.vectors_dir/'mirflickr_25k'/method/store.metadata['generation']/'vectors.npy')
    np.testing.assert_array_equal(raw[0],np.array([(j+10)%151 for j in range(150)],dtype=np.float32))
    np.testing.assert_allclose(np.linalg.norm(store.vectors,axis=1),1,atol=1e-6)
    assert store.distance_scale==2
    tree=VPTree(store.vectors,store.ids)
    tree.save(settings.indexes_dir/'mirflickr_25k'/f'{method}.npz',store.signature)
    engine=SearchEngine(settings)
    args=dict(dataset='mirflickr_25k',query_id=1,methods=[method],k=10)
    assert engine.search(**args)['matches']==engine.search(**args,method='indexed')['matches']
    assert '3/6' in engine.search(**args)['message']
    with pytest.raises(ValueError,match='absente'):
        engine.search('mirflickr_25k',2,[method])
    with TestClient(create_app(settings)) as client:
        base=client.get('/datasets').json()[0]
        assert base['mpeg7_available']
        descriptor=next(d for d in base['descriptors'] if d['name']==method)
        assert descriptor['count']==3 and descriptor['dimension']==150
        body=dict(dataset='mirflickr_25k',query_id=1,descriptors=[method],method='indexed')
        result=client.post('/search/visual',json=body)
        assert result.status_code==200 and result.json()['method_used']=='vp_tree'
        assert {i['id'] for i in result.json()['items']}=={3,5}
        assert client.post('/search/visual',json=dict(body,query_id=2)).status_code==422
        fusion=client.post('/search/combined',json=dict(body,descriptors=['hsv',method],weights=[1,2],keywords='sky'))
        assert fusion.status_code==200 and {i['id'] for i in fusion.json()['items']}=={3}


def test_unverified_stale_and_duplicate_mapping_rejected(mpeg7_source):
    settings,method,archive,mapping=mpeg7_source
    evidence=json.loads(mapping.read_text())
    evidence['status']='unverified'
    evidence.pop('signature')
    evidence['signature']=fingerprint(evidence)
    atomic_json(mapping,evidence)
    with pytest.raises(ValueError,match='non vérifiée'):
        import_mpeg7(settings,method,archive,mapping)
    assert not (settings.vectors_dir/'mirflickr_25k'/method).exists()
    evidence['status']='verified'
    evidence['catalog_signature']='changed'
    evidence.pop('signature')
    evidence['signature']=fingerprint(evidence)
    atomic_json(mapping,evidence)
    with pytest.raises(ValueError,match='obsolète'):
        import_mpeg7(settings,method,archive,mapping)
    with connect(settings.catalog_path) as db:
        rows=image_rows(db,'mirflickr_25k')
    evidence['catalog_signature']=catalog_signature(rows)
    evidence['mapping'].append(evidence['mapping'][0])
    evidence.pop('signature')
    evidence['signature']=fingerprint(evidence)
    atomic_json(mapping,evidence)
    with pytest.raises(ValueError,match='dupliqués'):
        load_mapping(mapping,rows)


def test_missing_malformed_and_dimensions(mpeg7_source):
    settings,method,archive,mapping=mpeg7_source
    # Build an archive containing one valid, one malformed and one absent mapped member.
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('features_edgehistogram/feature_names.txt','\n'.join(f'eh {i}' for i in range(150)))
        z.writestr('features_edgehistogram/0/10.txt','\n'.join(['1']*150))
        z.writestr('features_edgehistogram/0/20.txt','nan\n'*150)
    report=import_mpeg7(settings,method,archive,mapping)
    assert report['count']==1
    assert report['descriptor_payloads_read']==2
    assert report['missing_descriptors']==[dict(image_id=5,descriptor_id=30)]
    assert report['invalid_descriptors'][0]['image_id']==3
    with pytest.raises(ValueError):
        parse_descriptor(b'1\n2\n',43)
    with pytest.raises(ValueError):
        parse_descriptor(b'inf\n'*43,43)
    with pytest.raises(ValueError):
        parse_descriptor(b'1\n'*42+b'1 extra\n',43)


def test_http_range_never_downloads_a_whole_zip(monkeypatch):
    import requests
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('example.txt','direct range access')
    payload=buffer.getvalue()
    class Response:
        def __init__(self,start,end,status=206):
            self.status_code=status
            self.headers={'Content-Range':f'bytes {start}-{end}/{len(payload)}'}
            self.raw=io.BytesIO(payload[start:end+1])
        def __enter__(self): return self
        def __exit__(self,*args): pass
    def get(self,url,headers,**kwargs):
        start,end=map(int,headers['Range'][6:].split('-'))
        return Response(start,end)
    monkeypatch.setattr(requests.Session,'get',get)
    with RangeReader('https://example.test/file.zip',max_bytes=2048) as reader:
        with zipfile.ZipFile(reader) as archive:
            assert archive.read('example.txt')==b'direct range access'
    with RangeReader('https://example.test/file.zip',max_bytes=1) as reader:
        with pytest.raises(ValueError,match='budget exceeded'):
            reader.read(2)
    monkeypatch.setattr(requests.Session,'get',lambda *args,**kwargs:Response(0,0,status=200))
    with pytest.raises(ValueError,match='download refused'):
        RangeReader('https://example.test/file.zip')
