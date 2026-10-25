"""FTS5 : tous les mots sont exigés (AND), sans syntaxe FTS fournie par l'utilisateur."""
import re


def text_search(db, dataset, keywords, limit=None, offset=0):
    words = re.findall(r'[^\W_]+', keywords, flags=re.UNICODE)
    if not words:
        return []
    if len(words) > 32 or len(keywords) > 500:
        raise ValueError('Requête textuelle trop longue')
    expression = ' AND '.join('"'+w+'"' for w in words)
    sql = '''SELECT i.*, d.name AS dataset, -bm25(image_fts) AS text_score
        FROM image_fts JOIN images i ON i.id=image_fts.rowid
        JOIN datasets d ON d.id=i.dataset_id
        WHERE image_fts MATCH ? AND d.name=? ORDER BY text_score DESC,i.id'''
    params = [expression,dataset]
    if limit is not None:
        sql += ' LIMIT ? OFFSET ?'
        params += [limit,offset]
    return db.execute(sql,params).fetchall()
