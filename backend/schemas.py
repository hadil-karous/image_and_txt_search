from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DatasetName=Literal['mirflickr_25k','objects','mirflickr_1m']


class TextRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset: DatasetName
    keywords: str=Field(min_length=1,max_length=500)
    k: int=Field(default=12,ge=1,le=100)


class VisualRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    dataset: DatasetName
    query_id: int=Field(ge=1)
    descriptors: list[Literal['hsv','lbp','hog','mpeg7_edgehistogram','mpeg7_homogeneoustexture']]=Field(default=['hsv'],min_length=1,max_length=5)
    weights: list[float]|None=None
    k: int=Field(default=12,ge=1,le=100)
    method: Literal['exhaustive','indexed']='exhaustive'
    keywords: str=Field(default='',max_length=500)

    @model_validator(mode='after')
    def validate_weights(self):
        import math
        if len(set(self.descriptors))!=len(self.descriptors):
            raise ValueError('Descripteurs dupliqués')
        if self.weights is not None and (len(self.weights)!=len(self.descriptors)
                or any(not math.isfinite(w) or w<0 for w in self.weights) or not any(self.weights)):
            raise ValueError('Poids invalides')
        return self
