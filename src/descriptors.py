"""Trois signatures positives de norme L2 <= 1 ; distance euclidienne métrique."""
from dataclasses import asdict, dataclass
import math

import numpy as np
from PIL import Image, ImageOps
from skimage import color, feature

METHODS = ('hsv', 'lbp', 'hog')
MPEG7_METHODS = ('mpeg7_edgehistogram', 'mpeg7_homogeneoustexture')
SEARCH_METHODS = METHODS + MPEG7_METHODS


@dataclass(frozen=True)
class DescriptorConfig:
    size: int = 64
    hsv_bins: tuple = (8, 4, 4)
    lbp_points: int = 8
    lbp_radius: float = 1.0
    hog_orientations: int = 9
    hog_cell: int = 8
    hog_block: int = 2

    def __post_init__(self):
        if self.size < 16 or any(b < 1 for b in self.hsv_bins) or len(self.hsv_bins) != 3:
            raise ValueError('Paramètres de taille ou HSV invalides')
        if self.lbp_points < 1 or not math.isfinite(self.lbp_radius) or self.lbp_radius <= 0 or self.hog_cell < 1 or self.hog_block < 1 or self.hog_orientations < 1:
            raise ValueError('Paramètres LBP/HOG invalides')
        if self.size % self.hog_cell or self.size // self.hog_cell < self.hog_block:
            raise ValueError('Taille incompatible avec les cellules HOG')

    def parameters(self):
        # JSON représente les tuples comme listes.
        import json
        return json.loads(json.dumps(asdict(self)))


def prepare(image, config):
    image = ImageOps.exif_transpose(image)
    if image.mode in ('RGBA','LA') or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, 'white')
        image = Image.alpha_composite(background, rgba)
    return np.asarray(image.convert('RGB').resize((config.size,config.size), Image.Resampling.BILINEAR))


def describe(image, method, config=DescriptorConfig()):
    rgb = prepare(image, config)
    if method == 'hsv':
        hsv = color.rgb2hsv(rgb)
        vector = np.histogramdd(hsv.reshape(-1,3), bins=config.hsv_bins, range=((0,1),)*3)[0].ravel()
        vector = np.sqrt(vector / max(vector.sum(),1))
    elif method == 'lbp':
        gray = np.rint(color.rgb2gray(rgb)*255).astype(np.uint8)
        codes = feature.local_binary_pattern(gray, config.lbp_points, config.lbp_radius, method='uniform')
        vector = np.bincount(codes.astype(int).ravel(), minlength=config.lbp_points+2).astype(float)
        vector = np.sqrt(vector / max(vector.sum(),1))
    elif method == 'hog':
        vector = feature.hog(color.rgb2gray(rgb), orientations=config.hog_orientations,
                             pixels_per_cell=(config.hog_cell,)*2,
                             cells_per_block=(config.hog_block,)*2, block_norm='L2-Hys')
    else:
        raise ValueError(f'Descripteur inconnu : {method}')
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector.astype(np.float64))
    if norm:
        vector /= norm
    if not np.isfinite(vector).all():
        raise ValueError('Descripteur non fini')
    return vector
