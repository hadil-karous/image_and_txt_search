import argparse
import json
from pathlib import Path
from backend.config import get_settings
from src.data_loader import import_dataset


def main():
    parser = argparse.ArgumentParser(description='Importer les images et les tags MIRFLICKR-25K')
    parser.add_argument('--dataset', choices=['mirflickr_25k','objects','mirflickr_1m'], default='mirflickr_25k')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--report', default='benchmarks/import.json')
    args = parser.parse_args()
    report = import_dataset(get_settings(), args.dataset, args.limit)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
