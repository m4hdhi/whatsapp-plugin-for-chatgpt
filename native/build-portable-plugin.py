"""Package the frozen desktop bridge as a private, installer-free local plugin."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

source = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--workspace', type=Path, default=source,
                    help='Build root containing work/native-stage, work/native-python and work/native-link.')
args = parser.parse_args()
workspace = args.workspace.resolve()
work = workspace / 'work'
target = work / 'portable-plugin' / 'GroupBrief'
target.mkdir(parents=True, exist_ok=True)
shutil.copytree(source / 'native/chatgpt-plugin', target, dirs_exist_ok=True)
(target / 'bin').mkdir(exist_ok=True)
link = work / 'native-link/GroupBriefLink.exe'
python_build = work / 'native-python/GroupBrief'
assert link.is_file() and python_build.is_dir(), 'Run native/build-windows.py --stage-only first.'
shutil.copy2(link, target / 'bin/GroupBriefLink.exe')
helper = target / 'helper'
helper.mkdir(exist_ok=True)
shutil.copytree(python_build, helper, dirs_exist_ok=True)
for folder in ('runtime', 'licenses'):
    shutil.copytree(work / 'native-stage/GroupBrief' / folder, helper / folder, dirs_exist_ok=True)
shutil.copytree(source / 'native/bridge', helper / 'bridge', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('*.test.cjs', '__pycache__', '.env'))
for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md', 'runtime-manifest.json'):
    shutil.copy2(work / 'native-stage/GroupBrief' / name, helper / name)
shutil.copy2(source / 'LICENSE', target / 'LICENSE')
manifest = json.loads((target / 'plugin.json').read_text())
assert manifest['author']['url'] == manifest['extensions']['com.openai']['interface']['websiteURL'] == 'https://www.linkedin.com/in/m4hdhi/'
assert manifest['extensions']['com.openai']['requires_local_executor'] is True
files = sorted(p for p in target.rglob('*') if p.is_file())
for file in files:
    relative = file.relative_to(target)
    assert not any(part in {'.sessions', 'whatsapp', 'data', 'demo-data', '__pycache__'} for part in relative.parts)
    assert file.name not in {'.env', 'runtime.json', 'local-config.json', 'installed-files.json'}
    assert file.suffix not in {'.sqlite3', '.log', '.pyc'}
outputs = workspace / 'outputs'
outputs.mkdir(parents=True, exist_ok=True)
archive_path = outputs / 'WhatsApp-ChatGPT-Plugin-2.2.0.zip'
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in files:
        archive.write(file, 'GroupBrief/' + file.relative_to(target).as_posix())
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(set(archive.namelist()))
    assert archive.read('GroupBrief/helper/bridge/bridge.cjs') == (source / 'native/bridge/bridge.cjs').read_bytes()
    assert archive.read('GroupBrief/bin/GroupBriefLink.exe') == link.read_bytes()
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
archive_path.with_suffix('.sha256').write_text(digest + '  ' + archive_path.name + '\n')
shutil.copy2(source / 'native/chatgpt-plugin/README.md', outputs / 'WhatsApp-ChatGPT-Plugin-Guide.md')
print(json.dumps({'plugin_package': archive_path.name, 'files': len(files), 'bytes': archive_path.stat().st_size,
                  'sha256': digest, 'private_data_included': False}))
