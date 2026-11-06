"""Explicit catalog inventory, shared by updates, builds and market generation."""
import json
from pathlib import Path, PurePosixPath

from resource_catalog import obj, require, validate_catalog


def json_value(content):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=pairs)


def relative_path(value):
    require(isinstance(value, str) and value and '\\' not in value, 'Invalid repository path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == value and value != '.',
            'Use a normalized repository-relative path: ' + value)
    return path


def repository_path(root, relative):
    path = Path(root) / relative_path(relative)
    cursor = path
    while cursor != Path(root):
        require(not cursor.is_symlink(), 'Repository input/output must not be a symlink: ' + relative)
        cursor = cursor.parent
    return path


def filesystem_reader(root):
    return lambda relative: repository_path(root, relative).read_bytes()


def load_catalogs(read):
    index = json_value(read('catalogs.json'))
    obj(index, ('schema_version', 'catalogs'), ('schema_version', 'catalogs'), 'catalog index')
    require(type(index['schema_version']) is int and index['schema_version'] == 1, 'Unsupported catalog index version')
    paths = index['catalogs']
    require(isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths), 'List catalog paths')
    require(len(set(paths)) == len(paths), 'Duplicate catalog path')
    result = {}
    for path in paths:
        require(relative_path(path).name == 'catalog.json', 'Index entries must name catalog.json')
        catalog = validate_catalog(json_value(read(path)))
        require(catalog['name'] not in result, 'Duplicate catalog name: ' + catalog['name'])
        result[catalog['name']] = (path, catalog)
    return result


def catalog_paths(root):
    return [Path(root) / path for path, _ in load_catalogs(filesystem_reader(root)).values()]
