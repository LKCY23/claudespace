"""Synthetic CLI and app only; never target the user's real Claude installation."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
import uuid


def fake_cli(root, application):
    machine = root / '机器 "binding".yaml'
    machine.write_text('synthetic: true\n')
    options = root / 'scenario.json'
    options.write_text(json.dumps({'application': str(application)}))
    command = root / 'fake "claude-config"'
    command.write_text(f'#!{sys.executable}\n' + '''
from pathlib import Path
import json, sys
root = Path(__file__).parent
options = json.loads((root / 'scenario.json').read_text())
if sys.argv[1:] == ['--version']:
    print('claude-config ' + options.get('version', '0.1.4'))
    raise SystemExit()
args = sys.argv[1:]
operation = args[0]
with (root / 'calls.jsonl').open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
if options.get('malformed') == operation:
    print('synthetic non-JSON failure')
    raise SystemExit(2)
failed = options.get('fail') == operation
target = {'app': 'claude-desktop', 'application': options['application'],
          'machine_file': args[args.index('--machine') + 1], 'profile': 'profiles/apps/claude-desktop/third-party.yaml',
          'data_root': str(root / 'native'), 'deployment_mode': options.get('mode', '3p'),
          'default_third_party_data_root': str(root / 'native')}
if options.get('changed_target') and operation == 'apply':
    target['application'] = str(root / 'Other.app')
if options.get('missing_binding'):
    target.pop(options['missing_binding'])
if options.get('wrong_machine'):
    target['machine_file'] = str(root / 'different.yaml')
if options.get('custom_data_root'):
    target['data_root'] = str(root / 'custom')
report = {'schema_version': 1, 'status': 'blocked' if failed else 'ok', 'ready': not failed,
          'operation': operation, 'preview_only': operation == 'plan',
          'plan_id': ('b' if options.get('changed_plan') and operation == 'apply' else 'a') * 64,
          'targets': [target], 'summary': {'changes': options.get('changes', 0)},
          'decisions': options.get('decisions', []),
          'errors': [], 'blockers': [{'code': options.get('failure_code', 'synthetic_block'), 'reason': 'synthetic blocked'}] if failed else [],
          'execution': {'status': 'preview' if operation == 'plan' else options.get('execution_status', 'completed'), 'started': operation == 'apply'}}
if options.get('not_started'):
    report['execution']['started'] = False
if options.get('incomplete') and operation == 'apply':
    report['execution']['status'] = 'incomplete'
report_path = root / (operation + '-report.json')
report['artifacts'] = {'saved': True, 'json_path': str(report_path)}
report_path.write_text(json.dumps(report))
print(json.dumps(report))
raise SystemExit(1 if failed else 0)
''')
    command.chmod(0o700)
    return command, machine


def scenario(root, **changes):
    path = root / 'scenario.json'
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


def calls(root):
    path = root / 'calls.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def fake_app(root, marker):
    app = root / 'Synthetic Desktop.app'
    source = root / 'desktop.applescript'
    literal = str(marker).replace('\\', '\\\\').replace('"', '\\"')
    source.write_text('on run\n do shell script "/usr/bin/touch " & quoted form of "' + literal + '"\nend run\n')
    subprocess.run(['/usr/bin/osacompile', '-o', str(app), str(source)], check=True, capture_output=True)
    path = app / 'Contents/Info.plist'
    data = plistlib.loads(path.read_bytes())
    data['CFBundleIdentifier'] = 'io.claudespace.synthetic-desktop.' + uuid.uuid4().hex
    path.write_bytes(plistlib.dumps(data))
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', str(app)], check=True, capture_output=True)
    return app


def wait_marker(marker):
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return marker.exists()
