"""API HTTP ; aucune extraction dans les requêtes. Redémarrer après préparation."""
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.schemas import DatasetName, TextRequest, VisualRequest
from src.database import connect, initialize, resolve_image
from src.descriptors import SEARCH_METHODS, MPEG7_METHODS
from src.text_search import text_search
from src.visual_search import SearchEngine


def create_app(settings=None):
    settings=settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        initialize(settings.catalog_path)
        app.state.engine=SearchEngine(settings)
        yield

    app=FastAPI(title='Recherche textuelle et visuelle',version='1.0.0',lifespan=lifespan)

    def check_dataset(db,dataset):
        if db.execute('SELECT id FROM datasets WHERE name=?',(dataset,)).fetchone() is None:
            raise HTTPException(404,'Base non importée')

    def serialize(db,row,request):
        tags=[r[0] for r in db.execute('SELECT t.name FROM tags t JOIN image_tags it ON it.tag_id=t.id WHERE it.image_id=? ORDER BY t.name',(row['id'],))]
        item=dict(id=row['id'],dataset=row['dataset'],source_id=row['source_id'],
                  width=row['width'],height=row['height'],tags=tags,
                  url=str(request.url_for('image_file',image_id=row['id'])))
        if 'text_score' in row.keys():
            item['text_score']=row['text_score']
        return item

    @app.get('/health')
    def health():
        return dict(status='ok',catalog_ready=True)

    @app.get('/datasets')
    def datasets(request:Request):
        result=[]
        engine=app.state.engine
        with connect(settings.catalog_path) as db:
            for name in ('mirflickr_25k','objects','mirflickr_1m'):
                count=db.execute('SELECT COUNT(*) FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE d.name=?',(name,)).fetchone()[0]
                annotated=db.execute('SELECT COUNT(DISTINCT i.id) FROM images i JOIN datasets d ON d.id=i.dataset_id JOIN image_tags it ON it.image_id=i.id WHERE d.name=?',(name,)).fetchone()[0]
                descriptors=[]
                for descriptor in SEARCH_METHODS:
                    key=(name,descriptor)
                    store=engine.stores.get(key)
                    descriptors.append(dict(name=descriptor,available=store is not None,
                        count=len(store.ids) if store else 0,index_available=key in engine.trees,
                        dimension=store.vectors.shape[1] if store else None,
                        family='mpeg7' if descriptor in MPEG7_METHODS else 'computed',
                        distance='euclidean_after_l2 / 2' if descriptor in MPEG7_METHODS else 'euclidean / sqrt(2)',
                        missing_images=count-len(store.ids) if store else count,
                        message=engine.messages.get(key)))
                result.append(dict(name=name,available=count>0,image_count=count,
                    annotated_images=annotated,annotation_kind='user_tags' if annotated else 'none',
                    descriptors=descriptors,mpeg7_available=any(d['available'] and d['family']=='mpeg7' for d in descriptors)))
        return result

    @app.get('/descriptors')
    def descriptors(dataset:DatasetName,request:Request):
        return next(d['descriptors'] for d in datasets(request) if d['name']==dataset)

    @app.get('/images')
    def browse(request:Request,dataset:DatasetName,offset:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=100)):
        with connect(settings.catalog_path) as db:
            check_dataset(db,dataset)
            total=db.execute('SELECT COUNT(*) FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE d.name=?',(dataset,)).fetchone()[0]
            rows=db.execute('SELECT i.*, d.name AS dataset FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE d.name=? ORDER BY i.id LIMIT ? OFFSET ?',(dataset,limit,offset)).fetchall()
            return dict(total=total,offset=offset,items=[serialize(db,r,request) for r in rows])

    @app.get('/images/{image_id}')
    def image_info(image_id:int,request:Request):
        with connect(settings.catalog_path) as db:
            row=db.execute('SELECT i.*, d.name AS dataset FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?',(image_id,)).fetchone()
            if row is None:
                raise HTTPException(404,'Image inconnue')
            return serialize(db,row,request)

    @app.get('/images/{image_id}/file',name='image_file')
    def image_file(image_id:int):
        with connect(settings.catalog_path) as db:
            row=db.execute('SELECT i.*,d.name AS dataset FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?',(image_id,)).fetchone()
        if row is None:
            raise HTTPException(404,'Image inconnue')
        try:
            path=resolve_image(row,settings)
        except ValueError:
            raise HTTPException(403,'Chemin image non autorisé')
        if not path.is_file():
            raise HTTPException(404,'Fichier image absent')
        return FileResponse(path)

    @app.post('/search/text')
    def search_text(body:TextRequest,request:Request):
        start=time.perf_counter()
        with connect(settings.catalog_path) as db:
            check_dataset(db,body.dataset)
            annotated=db.execute('SELECT 1 FROM image_tags it JOIN images i ON i.id=it.image_id JOIN datasets d ON d.id=i.dataset_id WHERE d.name=? LIMIT 1',(body.dataset,)).fetchone()
            try:
                rows=text_search(db,body.dataset,body.keywords,body.k)
            except ValueError as exc:
                raise HTTPException(422,str(exc))
            items=[serialize(db,r,request) for r in rows]
        return dict(items=items,method_used='fts5_and',elapsed_ms=(time.perf_counter()-start)*1000,
                    message=None if annotated else 'Aucune annotation : recherche textuelle indisponible.')

    def run_visual(body,request,combined=False):
        if combined and not body.keywords.strip():
            raise HTTPException(422,'La recherche combinée exige des mots-clés')
        started=time.perf_counter()
        with connect(settings.catalog_path) as db:
            check_dataset(db,body.dataset)
            candidates=None
            if combined:
                try:
                    candidates={r['id'] for r in text_search(db,body.dataset,body.keywords)}
                except ValueError as exc:
                    raise HTTPException(422,str(exc))
        try:
            result=app.state.engine.search(body.dataset,body.query_id,body.descriptors,body.weights,body.k,body.method,candidates)
        except ValueError as exc:
            raise HTTPException(422,str(exc))
        pairs=result.pop('matches')
        with connect(settings.catalog_path) as db:
            items=[]
            for image_id,distance in pairs:
                row=db.execute('SELECT i.*, d.name AS dataset FROM images i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?',(image_id,)).fetchone()
                if row:
                    items.append(dict(**serialize(db,row,request),distance=distance))
        result['items']=items
        result['elapsed_ms']=(time.perf_counter()-started)*1000
        if combined:
            with connect(settings.catalog_path) as db:
                annotated=db.execute('SELECT 1 FROM image_tags it JOIN images i ON i.id=it.image_id JOIN datasets d ON d.id=i.dataset_id WHERE d.name=? LIMIT 1',(body.dataset,)).fetchone()
            if not annotated:
                result['message']='Aucune annotation : recherche combinée indisponible.'
        return result

    @app.post('/search/visual')
    def search_visual(body:VisualRequest,request:Request):
        if body.keywords.strip():
            raise HTTPException(422,'Utiliser /search/combined pour filtrer par mots-clés')
        return run_visual(body,request)

    @app.post('/search/combined')
    def search_combined(body:VisualRequest,request:Request):
        return run_visual(body,request,True)

    return app


app=create_app()
