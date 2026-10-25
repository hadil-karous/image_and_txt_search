from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app
from src.database import connect


def test_endpoints_images_and_search(prepared):
    with TestClient(create_app(prepared)) as client:
        assert client.get('/health').status_code==200
        bases=client.get('/datasets').json()
        assert bases[0]['image_count']==6
        assert not bases[1]['available']
        page=client.get('/images',params=dict(dataset='mirflickr_25k',limit=2,offset=1)).json()
        assert [i['id'] for i in page['items']]==[2,3]
        item=page['items'][0]
        response=client.get(item['url'])
        assert response.status_code==200
        with Image.open(BytesIO(response.content)) as image:
            assert image.size==(42,32)
        body=dict(dataset='mirflickr_25k',query_id=1,descriptors=['hsv'],k=4)
        result=client.post('/search/visual',json=body).json()
        assert len(result['items'])==4
        assert all(i['id']!=1 for i in result['items'])
        combined=client.post('/search/combined',json=dict(**body,keywords='sky water')).json()
        assert {i['id'] for i in combined['items']}=={2,3}
        assert not client.post('/search/combined',json=dict(**body,keywords='nonexistent')).json()['items']
        assert len(client.post('/search/text',json=dict(dataset='mirflickr_25k',keywords='sky water')).json()['items'])==3
        assert client.post('/search/visual',json=dict(**body,weights=[0])).status_code==422
        assert client.post('/search/visual',json=dict(**body,weights=[-1])).status_code==422
        assert client.post('/search/visual',json=dict(body,k=101)).status_code==422
        assert client.post('/search/visual',json=dict(body,descriptors=['hsv','hsv'])).status_code==422
        assert client.get('/images',params=dict(dataset='mirflickr_25k',offset=-1)).status_code==422
        assert client.get('/images/999/file').status_code==404
        assert client.post('/search/combined',json=body).status_code==422
        with connect(prepared.catalog_path) as db:
            db.execute("UPDATE images SET relative_path='../../secret.jpg' WHERE id=1")
        assert client.get('/images/1/file').status_code==403


def test_empty_catalog(tmp_path):
    from backend.config import Settings
    with TestClient(create_app(Settings(tmp_path))) as client:
        assert client.get('/health').status_code==200
        assert not any(d['available'] for d in client.get('/datasets').json())
        assert client.get('/images?dataset=objects').status_code==404
