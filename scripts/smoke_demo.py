"""Validation HTTP réelle du parcours et des octets servis par les URLs."""
import argparse
import hashlib
import time
from pathlib import Path
import requests
from backend.config import get_settings
from src.database import connect, resolve_image
from src.feature_store import atomic_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://127.0.0.1:8000')
    args=p.parse_args()
    session=requests.Session()
    def call(method,path,**kwargs):
        response=session.request(method,args.url+path,timeout=120,**kwargs)
        response.raise_for_status()
        return response.json()
    started=time.perf_counter()
    assert call('GET','/health')['status']=='ok'
    bases=call('GET','/datasets')
    page=call('GET','/images',params=dict(dataset='mirflickr_25k',limit=4))
    query=page['items'][0]
    settings=get_settings()
    checks=[]
    bodies=[('text',dict(dataset='mirflickr_25k',keywords='sky water',k=8)),
            ('visual',dict(dataset='mirflickr_25k',query_id=query['id'],descriptors=['hsv'],method='indexed',k=8)),
            ('visual',dict(dataset='mirflickr_25k',query_id=query['id'],descriptors=['hsv','lbp','hog'],weights=[1,1,1],k=8)),
            ('combined',dict(dataset='mirflickr_25k',query_id=query['id'],descriptors=['hsv'],keywords='sky water',method='indexed',k=8)),
            ('combined',dict(dataset='mirflickr_25k',query_id=query['id'],descriptors=['hsv'],keywords='zzzxnonexistent',k=8))]
    for kind,body in bodies:
        result=call('POST','/search/'+kind,json=body)
        items=result['items']
        if kind!='text':
            assert query['id'] not in [i['id'] for i in items]
            assert [i['distance'] for i in items]==sorted(i['distance'] for i in items)
        for item in items[:2]:
            response=session.get(item['url'],timeout=30)
            response.raise_for_status()
            with connect(settings.catalog_path) as db:
                row=db.execute('SELECT i.*,d.name AS dataset FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?',(item['id'],)).fetchone()
            expected=resolve_image(row,settings).read_bytes()
            assert hashlib.sha256(response.content).digest()==hashlib.sha256(expected).digest()
        checks.append(dict(kind=kind,body=body,count=len(items),method_used=result['method_used'],
                           elapsed_ms=result['elapsed_ms'],message=result.get('message'),url_checks=min(2,len(items))))
    assert checks[-1]['count']==0
    first_result=call('POST','/search/visual',json=bodies[1][1])['items'][0]
    follow=call('POST','/search/visual',json=dict(bodies[1][1],query_id=first_result['id']))
    assert first_result['id'] not in [i['id'] for i in follow['items']]
    report=dict(status='passed',bases=bases,checks=checks,requery_passed=True,seconds=time.perf_counter()-started)
    atomic_json(Path('benchmarks/http_smoke.json'),report)
    print('Parcours HTTP et correspondance exacte des URLs : OK')


if __name__=='__main__':
    main()
