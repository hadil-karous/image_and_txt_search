import argparse
from backend.config import get_settings
from src.descriptors import DescriptorConfig, METHODS
from src.feature_store import atomic_json, extract_features
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='Extraction hors ligne, reprise automatique des lots')
    p.add_argument('--dataset', default='mirflickr_25k')
    p.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    p.add_argument('--limit', type=int)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--batch-size', type=int, default=250)
    p.add_argument('--size', type=int, default=64)
    p.add_argument('--hsv-bins', type=int, nargs=3, default=[8,4,4])
    p.add_argument('--lbp-points', type=int, default=8)
    p.add_argument('--lbp-radius', type=float, default=1)
    p.add_argument('--hog-cell', type=int, default=8)
    p.add_argument('--hog-block', type=int, default=2)
    p.add_argument('--hog-orientations', type=int, default=9)
    args = p.parse_args()
    config = DescriptorConfig(args.size,tuple(args.hsv_bins),args.lbp_points,args.lbp_radius,
                              args.hog_orientations,args.hog_cell,args.hog_block)
    result = extract_features(get_settings(),args.dataset,args.methods,args.limit,args.workers,args.batch_size,config)
    atomic_json(Path('benchmarks/extraction.json'),result)


if __name__ == '__main__':
    main()
