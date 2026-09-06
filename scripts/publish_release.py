"""Publish artifacts only from a fully successful desktop build in this repository."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def main():
    run_id = os.environ['RELEASE_RUN_ID']
    tag = os.environ.get('RELEASE_TAG', 'v0.1.0')
    run = json.loads(gh('run', 'view', run_id, '--json', 'status,conclusion,headSha'))
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        raise RuntimeError('Both desktop jobs must finish successfully before publication')
    root = Path('release-artifacts')
    sources = root / 'third-party-sources'
    sources.mkdir(parents=True, exist_ok=True)
    manifest = [
        {'file':'flowsom-0.2.2.tar.gz', 'url':'https://files.pythonhosted.org/packages/5f/b6/4be17631fbe45befc01b27fae24c894528a2ea25ada842c0a112da7f4bfa/flowsom-0.2.2.tar.gz', 'sha256':'465ead0447509ea01fc929bc9b41a46282dc9ed7b6b906c3bd87735b1d431562'},
        {'file':'igraph-1.0.0.tar.gz', 'url':'https://files.pythonhosted.org/packages/23/be/56bef1919005b4caf1f71522b300d359f7faeb7ae93a3b0baa9b4f146a87/igraph-1.0.0.tar.gz', 'sha256':'2414d0be2e4d77ee5357807d100974b40f6082bb1bb71988ec46cfb6728651ee'},
    ]
    for item in manifest:
        with urllib.request.urlopen(item['url'], timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError('Third-party source hash mismatch')
        (sources/item['file']).write_bytes(data)
    (sources/'SOURCES.json').write_text(json.dumps(manifest, indent=2))
    shutil.copyfile('docs/THIRD_PARTY_SOURCES.md', sources/'README.md')
    shutil.make_archive(str(root/'FlowAnalysis-0.1.0-ThirdPartySources'), 'zip', root, 'third-party-sources')
    assets = sorted([*root.rglob('*.zip'), *root.rglob('*Setup.exe')])
    if not any('Windows' in p.name for p in assets) or not any('macOS' in p.name for p in assets):
        raise RuntimeError('Missing platform artifacts')
    for report in root.rglob('frozen-smoke.json'):
        contents = json.loads(report.read_text())
        if contents.get('numerical_worker') != 'passed':
            raise RuntimeError('Frozen numerical smoke test did not pass')
        target = root/(report.parent.name+'-validation.json')
        target.write_text(json.dumps(contents, indent=2))
        assets.append(target)
    sums = root/'SHA256SUMS.txt'
    sums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in assets))
    assets.append(sums)
    notes = root/'release-notes.md'
    notes.write_text(Path('docs/RELEASE_NOTES_0.1.0.md').read_text() + '\n\nValidated source commit: `' + run['headSha'] + '`.\n')
    args = ['release', 'create', tag, '--target', run['headSha'], '--prerelease', '--title',
            'FlowAnalysis '+tag+' — research preview', '--notes-file', str(notes), *map(str,assets)]
    print(gh(*args))


if __name__ == '__main__':
    main()
