#!/usr/bin/env python3
"""Validate catalog bodies at a checkout; reports remain outside its Git tree."""
import argparse
import json
import subprocess
from pathlib import Path

from build_candidates import build, write_json
from run_updates import catalogs
from resource_catalog import require


def validate(root, output, *, fetch=False, prepared=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(root), 'Use a new validation directory outside the checkout')
    output.mkdir(parents=True)
    rows = []
    for catalog in catalogs(root):
        name = catalog.parent.name if catalog.parent != root else 'root'
        try:
            report = build(catalog, output / name, fetch=fetch, prepared=prepared)
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            report = {'status': 'blocked', 'reason': str(exc)}
        write_json(output / (name + '.json'), report)
        rows.append({'catalog': str(catalog.relative_to(root)), 'status': report['status']})
    result = {'schema_version': 1, 'kind': 'claudespace-validation', 'catalogs': rows,
              'status': 'passed' if all(row['status'] == 'ok' for row in rows) else 'failed', 'native_runtime': 'not-verified'}
    write_json(output / 'validation.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args(argv)
    result = validate(args.root, args.output, fetch=args.fetch)
    print('资源结构检查：' + result['status']); print('完整 JSON：' + str((args.output/'validation.json').resolve()))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
