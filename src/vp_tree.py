"""VP-Tree exact euclidien, partitions équilibrées, feuilles vectorisées."""
import heapq
import json
from pathlib import Path

import numpy as np


def distances(vectors, query):
    # Calcul identique dans l'exhaustif et dans l'index ; accumulation float64.
    output = np.empty(len(vectors),dtype=np.float64)
    for start in range(0,len(vectors),2048):
        difference = np.asarray(vectors[start:start+2048],dtype=np.float64)-np.asarray(query,dtype=np.float64)
        output[start:start+2048] = np.sqrt(np.einsum('ij,ij->i',difference,difference))
    return output


class VPTree:
    def __init__(self, vectors, ids, leaf_size=32):
        if leaf_size < 1 or len(vectors) != len(ids) or len(set(ids)) != len(ids):
            raise ValueError('Données ou taille de feuille invalides')
        self.vectors, self.ids = vectors, np.asarray(ids)
        self.nodes, self.order = [], []

        def build(indices):
            if not len(indices):
                return -1
            node_id = len(self.nodes)
            self.nodes.append(None)
            if len(indices) <= leaf_size:
                start = len(self.order)
                self.order.extend(indices.tolist())
                self.nodes[node_id] = [-1,0,-1,-1,start,len(indices)]
            else:
                vantage = int(indices[-1])
                others = indices[:-1]
                ds = distances(vectors[others],vectors[vantage])
                permutation = np.lexsort((self.ids[others],ds))
                others, ds = others[permutation], ds[permutation]
                middle = len(others)//2
                threshold = float(ds[middle])
                left, right = build(others[:middle]), build(others[middle:])
                self.nodes[node_id] = [vantage,threshold,left,right,0,0]
            return node_id

        build(np.arange(len(ids)))
        self.nodes = np.asarray(self.nodes,dtype=np.float64).reshape(-1,6)
        self.order = np.asarray(self.order,dtype=np.int64)

    def search(self, query, k=10, exclude_id=None):
        if k < 1:
            raise ValueError('k doit être positif')
        heap = []
        evaluated = 0

        def offer(index, distance):
            image_id = int(self.ids[index])
            if image_id == exclude_id:
                return
            item = (-float(distance),-image_id)
            if len(heap) < k:
                heapq.heappush(heap,item)
            elif item > heap[0]:
                heapq.heapreplace(heap,item)

        def radius():
            return -heap[0][0] if len(heap) == k else float('inf')

        def visit(node_id):
            nonlocal evaluated
            if node_id < 0:
                return
            vantage, threshold, left, right, start, count = self.nodes[node_id]
            if count:
                indices = self.order[int(start):int(start+count)]
                ds = distances(self.vectors[indices],query)
                evaluated += len(indices)
                for i,d in zip(indices,ds):
                    offer(i,d)
                return
            vantage = int(vantage)
            distance = distances(self.vectors[vantage:vantage+1],query)[0]
            evaluated += 1
            offer(vantage,distance)
            # Tolérance conservatrice : explorer davantage en cas d'arrondi, jamais moins.
            epsilon = 1e-10
            if distance < threshold:
                if distance-radius() <= threshold+epsilon:
                    visit(int(left))
                if distance+radius() >= threshold-epsilon:
                    visit(int(right))
            else:
                if distance+radius() >= threshold-epsilon:
                    visit(int(right))
                if distance-radius() <= threshold+epsilon:
                    visit(int(left))

        if len(self.nodes):
            visit(0)
        result = sorted([(-i,-d) for d,i in heap],key=lambda item:(item[1],item[0]))
        return result,evaluated

    def save(self, path, signature):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp = path.with_suffix('.tmp')
        with temp.open('wb') as stream:
            np.savez(stream,nodes=self.nodes,order=self.order,ids=self.ids,
                     metadata=np.array(json.dumps(dict(version=1,signature=signature))))
        temp.replace(path)

    @classmethod
    def load(cls,path,store):
        with np.load(Path(path),allow_pickle=False) as data:
            metadata = json.loads(str(data['metadata']))
            if metadata != dict(version=1,signature=store.signature) or not np.array_equal(data['ids'],store.ids):
                raise ValueError('Index obsolète : reconstruire les index')
            tree = cls.__new__(cls)
            tree.nodes,tree.order = data['nodes'],data['order']
        tree.ids,tree.vectors = store.ids,store.vectors
        return tree
