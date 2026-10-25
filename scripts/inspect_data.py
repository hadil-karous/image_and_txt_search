"""Inventaire local reproductible, sans modification des sources."""
import collections
import hashlib
import json
import os
import re
from pathlib import Path
from backend.config import get_settings


def main():
    settings=get_settings()
    report={}
    for name in ('mirflickr_25k','objects','mirflickr_1m'):
        root=settings.dataset(name).root
        counts=collections.Counter()
        bytes_total=0
        image_ids=set()
        tag_ids=set()
        docs=[]
        for folder,_,files in os.walk(root):
            for filename in files:
                if filename=='.gitkeep':
                    continue
                path=Path(folder)/filename
                rel=path.relative_to(root)
                counts[str(rel.parent)]+=1
                bytes_total+=path.stat().st_size
                if re.fullmatch(r'im\d+\.jpg',filename):
                    image_ids.add(int(re.search(r'\d+',filename)[0]))
                if re.fullmatch(r'tags\d+\.txt',filename):
                    tag_ids.add(int(re.search(r'\d+',filename)[0]))
                if rel.parent.name=='doc':
                    docs.append(dict(path=rel.as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        examples=[]
        for number in (1,2,10,100,25000):
            tag=root/f'annotations/meta/tags/tags{number}.txt'
            if tag.exists():
                examples.append(dict(source_id=number,image_present=number in image_ids,
                                     tags=tag.read_text(encoding='utf-8',errors='replace').splitlines()))
        report[name]=dict(file_counts=dict(counts),bytes=bytes_total,image_ids=len(image_ids),
                         image_range=[min(image_ids),max(image_ids)] if image_ids else None,
                         tags=len(tag_ids),matched=len(image_ids&tag_ids),
                         orphan_tags=sorted(tag_ids-image_ids),missing_tags=sorted(image_ids-tag_ids),
                         contiguous_1_to_25000=image_ids==set(range(1,25001)),docs=docs,examples=examples)
    path=Path('benchmarks/data_inspection.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
