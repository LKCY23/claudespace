"""Stdlib-only active machine profile reader and catalog dependency expander."""
from pathlib import Path, PurePosixPath
import re

from prepare_update import share_update
from resource_catalog import REF, require

_INT = re.compile(r'-?(?:0|[1-9][0-9]*)\Z')
_FLOAT = re.compile(r'-?(?:0|[1-9][0-9]*)\.[0-9]+\Z')
_UNSUPPORTED_PREFIXES = ('&', '*', '!', '|', '>')


def _strip_comment(line):
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch == '#' and (i == 0 or line[i - 1].isspace()):
                return line[:i].rstrip()
        i += 1
    if quote is not None:
        raise ValueError('Unterminated quoted string in YAML')
    return line.rstrip()


def _tokenize_lines(text):
    tokens = []
    for raw_number, raw_line in enumerate(text.splitlines(), 1):
        stripped_indent = len(raw_line) - len(raw_line.lstrip(' '))
        prefix = raw_line[:len(raw_line) - len(raw_line.lstrip(' \t'))]
        if '\t' in prefix:
            raise ValueError(f'Tabs are not supported in YAML indentation (line {raw_number})')
        cleaned = _strip_comment(raw_line)
        content = cleaned[stripped_indent:]
        if not content or content in ('---', '...'):
            continue
        tokens.append((stripped_indent, content, raw_number))
    return tokens


def _split_mapping_entry(content):
    quote = None
    depth = 0
    i = 0
    while i < len(content):
        ch = content[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < len(content) and content[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch in ('{', '['):
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
            elif ch == ':' and depth == 0 and (i + 1 == len(content) or content[i + 1] == ' '):
                key_raw = content[:i].strip()
                if not key_raw:
                    raise ValueError('Empty mapping key in YAML')
                key = _parse_scalar(key_raw)
                if not isinstance(key, str):
                    raise ValueError('YAML mapping keys must be strings')
                rest = content[i + 1:].strip()
                return key, rest
        i += 1
    return None


def _parse_double_quoted(token):
    escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
    out = []
    i = 1
    end = len(token) - 1
    while i < end:
        ch = token[i]
        if ch == '\\':
            i += 1
            if i >= end:
                raise ValueError('Invalid escape sequence in YAML string')
            esc = token[i]
            if esc not in escapes:
                raise ValueError(f'Unsupported YAML escape sequence: \\{esc}')
            out.append(escapes[esc])
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def _split_flow_items(inner):
    items = []
    start = 0
    quote = None
    depth = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < len(inner) and inner[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch in ('{', '['):
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
                if depth < 0:
                    raise ValueError('Unbalanced brackets in flow YAML')
            elif ch == ',' and depth == 0:
                part = inner[start:i].strip()
                if not part:
                    raise ValueError('Empty element in flow YAML')
                items.append(part)
                start = i + 1
        i += 1
    if quote is not None or depth != 0:
        raise ValueError('Unterminated flow collection in YAML')
    tail = inner[start:].strip()
    if tail:
        items.append(tail)
    return items


def _parse_scalar(token):
    token = token.strip()
    if not token:
        return None
    if token[0] in _UNSUPPORTED_PREFIXES:
        raise ValueError(f'Unsupported YAML construct: {token[0]}')
    if token.startswith("'"):
        if len(token) < 2 or not token.endswith("'"):
            raise ValueError('Malformed single-quoted YAML string')
        return token[1:-1].replace("''", "'")
    if token.startswith('"'):
        if len(token) < 2 or not token.endswith('"'):
            raise ValueError('Malformed double-quoted YAML string')
        return _parse_double_quoted(token)
    if token.startswith('{') and token.endswith('}'):
        inner = token[1:-1].strip()
        result = {}
        if inner:
            for part in _split_flow_items(inner):
                entry = _split_mapping_entry(part)
                if entry is None:
                    raise ValueError(f'Invalid flow mapping entry: {part}')
                key, val = entry
                result[key] = _parse_scalar(val)
        return result
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        return [_parse_scalar(part) for part in _split_flow_items(inner)] if inner else []
    if token in ('null', 'Null', 'NULL', '~'):
        return None
    if token in ('true', 'True', 'TRUE'):
        return True
    if token in ('false', 'False', 'FALSE'):
        return False
    if _INT.fullmatch(token):
        return int(token)
    if _FLOAT.fullmatch(token):
        return float(token)
    if any(ch in token for ch in ('{', '}', '[', ']')):
        raise ValueError(f'Malformed flow YAML token: {token}')
    return token


def _is_seq_line(content):
    return content == '-' or content.startswith('- ')


def _parse_seq_item(tokens, idx, seq_indent):
    indent, content, _ = tokens[idx]
    rest = content[1:].lstrip(' ')
    idx += 1
    if not rest:
        if idx < len(tokens) and tokens[idx][0] > seq_indent:
            return _parse_block(tokens, idx)
        return None, idx
    entry = _split_mapping_entry(rest)
    if entry is None:
        return _parse_scalar(rest), idx
    item = {}
    key, val_str = entry
    if val_str:
        item[key] = _parse_scalar(val_str)
    elif idx < len(tokens) and (tokens[idx][0] > seq_indent or (tokens[idx][0] == seq_indent and _is_seq_line(tokens[idx][1]))):
        # Nested block under first key of a "- key:" list item; only consume keys deeper than seq_indent + 2 if deeper
        item_indent = None
        # Look ahead carefully: if next line is indented deeper than the key column (`seq_indent + 2`), it's nested under `key`.
        key_col = seq_indent + 2
        if tokens[idx][0] > key_col or (tokens[idx][0] == key_col and _is_seq_line(tokens[idx][1])):
            item[key], idx = _parse_block(tokens, idx)
        else:
            item[key] = None
    else:
        item[key] = None
    item_indent = None
    while idx < len(tokens) and tokens[idx][0] > seq_indent:
        cur_indent, cur_content, _ = tokens[idx]
        if item_indent is None:
            item_indent = cur_indent
        if cur_indent != item_indent:
            raise ValueError('Inconsistent indentation inside YAML sequence mapping')
        if _is_seq_line(cur_content):
            raise ValueError('Unexpected sequence item inside mapping')
        more = _split_mapping_entry(cur_content)
        if more is None:
            raise ValueError(f'Expected mapping entry in YAML: {cur_content}')
        k, v_str = more
        idx += 1
        if v_str:
            item[k] = _parse_scalar(v_str)
        elif idx < len(tokens) and (tokens[idx][0] > item_indent or (tokens[idx][0] == item_indent and _is_seq_line(tokens[idx][1]))):
            item[k], idx = _parse_block(tokens, idx)
        else:
            item[k] = None
    return item, idx


def _parse_block(tokens, idx):
    base_indent, content, _ = tokens[idx]
    if _is_seq_line(content):
        items = []
        while idx < len(tokens) and tokens[idx][0] == base_indent and _is_seq_line(tokens[idx][1]):
            val, idx = _parse_seq_item(tokens, idx, base_indent)
            items.append(val)
        if idx < len(tokens) and tokens[idx][0] > base_indent:
            raise ValueError('Unexpected indentation after YAML sequence')
        return items, idx
    mapping = {}
    while idx < len(tokens) and tokens[idx][0] == base_indent:
        cur_indent, cur_content, _ = tokens[idx]
        if _is_seq_line(cur_content):
            break
        entry = _split_mapping_entry(cur_content)
        if entry is None:
            raise ValueError(f'Expected mapping entry in YAML: {cur_content}')
        key, val_str = entry
        if key in mapping:
            raise ValueError(f'Duplicate YAML key: {key}')
        idx += 1
        if val_str:
            mapping[key] = _parse_scalar(val_str)
        elif idx < len(tokens) and (tokens[idx][0] > base_indent or (tokens[idx][0] == base_indent and _is_seq_line(tokens[idx][1]))):
            mapping[key], idx = _parse_block(tokens, idx)
        else:
            mapping[key] = None
    if idx < len(tokens) and tokens[idx][0] > base_indent:
        raise ValueError('Unexpected indentation in YAML mapping')
    return mapping, idx


def parse_simple_yaml(text):
    """Parse the configuration YAML subset using only the Python standard library."""
    require(isinstance(text, str), 'YAML input must be text')
    tokens = _tokenize_lines(text)
    if not tokens:
        return {}
    value, idx = _parse_block(tokens, 0)
    if idx != len(tokens):
        raise ValueError('Unexpected trailing YAML content')
    return value


def _safe_inside(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative, 'Invalid relative YAML path')
    posix = PurePosixPath(relative)
    require(not posix.is_absolute() and '..' not in posix.parts and relative != '.', 'Profile path escapes repository root')
    base = root.resolve()
    cursor = root
    for part in posix.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), 'Profile path must not cross symlinks')
    resolved = cursor.resolve()
    require(resolved.is_relative_to(base) and resolved.is_file(), 'Profile file is missing or escapes repository root')
    return resolved


def is_resource_enabled(entry):
    """Disabled entries opt out of updates only when no other machine enables them."""
    if entry is None:
        return True
    require(isinstance(entry, dict), 'Resource declaration must be an object or null')
    options = entry.get('options')
    if options is None:
        return True
    require(isinstance(options, dict), 'Resource options must be an object')
    if options.get('enabled') is False:
        return False
    control = options.get('control')
    if control is not None:
        require(isinstance(control, dict), 'Resource control options must be an object')
        if control.get('enabled') is False:
            return False
    return True


def collect_active_resources(config_root):
    """Union every resource enabled by at least one machine and bound agent/app profile."""
    root = Path(config_root)
    base = root.resolve()
    machines_dir = root / 'machines'
    require(machines_dir.exists() and not machines_dir.is_symlink() and machines_dir.is_dir()
            and machines_dir.resolve().is_relative_to(base), 'Missing machines directory')
    machine_files = sorted(machines_dir.glob('*.yaml'))
    require(machine_files, 'No machine configurations found')
    active = set()
    profile_cache = {}
    for machine_file in machine_files:
        _safe_inside(root, machine_file.relative_to(root).as_posix())
        machine = parse_simple_yaml(machine_file.read_text(encoding='utf-8'))
        require(isinstance(machine, dict), 'Machine configuration must be a mapping')
        for section_key in ('agents', 'apps'):
            bindings = machine.get(section_key)
            if bindings is None:
                continue
            require(isinstance(bindings, dict), f'Machine {section_key} must be a mapping')
            for rel_path in bindings.values():
                profile_file = _safe_inside(root, rel_path)
                if profile_file not in profile_cache:
                    profile = parse_simple_yaml(profile_file.read_text(encoding='utf-8'))
                    require(isinstance(profile, dict), 'Profile configuration must be a mapping')
                    profile_cache[profile_file] = profile
                profile = profile_cache[profile_file]
                resources = profile.get('resources')
                if resources is None:
                    continue
                require(isinstance(resources, dict), 'Profile resources must be a mapping')
                for entries in resources.values():
                    if entries is None:
                        continue
                    require(isinstance(entries, dict), 'Profile resource section must be a mapping')
                    for ref, entry in entries.items():
                        require(isinstance(ref, str) and REF.fullmatch(ref), 'Invalid resource reference in profile')
                        if is_resource_enabled(entry):
                            active.add(ref)
    return frozenset(active)


def expand_active_dependencies(catalogs_by_name, active_refs):
    """Include transitive requires.resources dependencies of active resources."""
    expanded = set(active_refs)
    pending = sorted(expanded)
    while pending:
        ref = pending.pop()
        name, _, catalog_name = ref.partition('@')
        catalog = catalogs_by_name.get(catalog_name)
        if not catalog:
            continue
        item = catalog['resources'].get(name)
        if not item:
            continue
        for dep_ref in item.get('requires', {}).get('resources', []):
            if dep_ref not in expanded:
                expanded.add(dep_ref)
                pending.append(dep_ref)
    return frozenset(expanded)


def active_catalog_names(catalog, active_refs):
    """Expand active catalog members across non-manual share_update components."""
    items = catalog['resources']
    suffix = '@' + catalog['name']
    active = {name for name, item in items.items()
              if (name + suffix) in active_refs and item['update']['strategy'] != 'manual'}
    pending = sorted(active)
    while pending:
        current = pending.pop()
        for other_name, other_item in items.items():
            if other_name in active or other_item['update']['strategy'] == 'manual':
                continue
            if share_update(items[current], other_item):
                active.add(other_name)
                pending.append(other_name)
    return frozenset(active)
