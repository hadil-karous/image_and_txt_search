import argparse
import json
from backend.config import get_settings
from src.database import connect
from src.text_search import text_search
from src.visual_search import SearchEngine


def main():
    p=argparse.ArgumentParser(description='Recherche locale hors interface')
    p.add_argument('--dataset',default='mirflickr_25k')
    p.add_argument('--query-id',type=int)
    p.add_argument('--keywords',default='')
    p.add_argument('--descriptors',nargs='+',default=['hsv'])
    p.add_argument('--weights',nargs='+',type=float)
    p.add_argument('--k',type=int,default=12)
    p.add_argument('--method',choices=['exhaustive','indexed'],default='exhaustive')
    args=p.parse_args()
    settings=get_settings()
    with connect(settings.catalog_path) as db:
        rows=text_search(db,args.dataset,args.keywords) if args.keywords else None
    if args.query_id:
        output=SearchEngine(settings).search(args.dataset,args.query_id,args.descriptors,args.weights,args.k,args.method,
                                             {r['id'] for r in rows} if rows is not None else None)
    else:
        output=[dict(r) for r in (rows or [])[:args.k]]
    print(json.dumps(output,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
