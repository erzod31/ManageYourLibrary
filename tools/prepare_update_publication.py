"""Prepare a reviewable release/channel plan from verified existing packages; never upload/publish."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.app_updates import APP_ID, DEFAULT_REPOSITORY, MAC_BUNDLE_ID, PRODUCT, UpdateChannel


def sha256(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def runtime_input(relative):
    path=Path(relative);name=path.as_posix()
    return ((len(path.parts)==1 and (path.suffix in {'.py','.ico','.svg'} or name in {'VERSION','LICENSE','THIRD_PARTY_NOTICES.md'}))
        or (path.parts[0] in {'core','ui','metadata','data'} and path.suffix in {'.py','.json','.txt','.png','.svg','.webp'})
        or name.startswith(('platforms/android/src/','platforms/android/res/'))
        or name in {'platforms/android/AndroidManifest.xml','platforms/android/BUILD_ANDROID.ps1',
                    'platforms/windows/APPLY_PORTABLE_UPDATE.ps1','tools/runtime_self_test.py','tools/first_use_self_test.py',
                    'tools/mobile_runtime_self_test.py','tools/update_runtime_self_test.py'})


def verify_runtime_baseline(root, baseline):
    files=[f for f in baseline['sourceBefore']['files'] if runtime_input(f['relativePath'])]
    if not files:raise ValueError('No immutable product-runtime source baseline supplied')
    root=Path(root)
    paths=list(root.iterdir())
    for prefix in ['core','ui','metadata','data','platforms/android/src','platforms/android/res','tools']:
        if (root/prefix).is_dir():paths.extend((root/prefix).rglob('*'))
    paths.extend(root/p for p in ['platforms/android/AndroidManifest.xml','platforms/android/BUILD_ANDROID.ps1',
                                 'platforms/windows/APPLY_PORTABLE_UPDATE.ps1'])
    present={p.relative_to(root).as_posix() for p in paths if p.is_file() and runtime_input(p.relative_to(root).as_posix())}
    expected={f['relativePath'].replace('\\','/') for f in files}
    if present!=expected:raise ValueError('Runtime input set changed; new/missing runtime files require a reviewed rebuild')
    for item in files:
        path=Path(root)/item['relativePath']
        if not path.is_file() or sha256(path).lower()!=item['sha256'].lower():
            raise ValueError('Runtime input changed; existing binaries require a reviewed rebuild: '+item['relativePath'])
    return {'matched':True,'filesChecked':len(files),'baselineTaskId':baseline['taskId'],
            'note':'Only native build/validation tooling and audit documentation changed. Original complete build fingerprints remain historical, not relabeled.'}


def prepare(directory, output, baseline, *, root=ROOT):
    directory,output,root=map(Path,(directory,output,root))
    version=(root/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid product version')
    runtime=verify_runtime_baseline(root,baseline)
    source_report=json.loads((root/'docs/in-app-updates-DG-0020.json').read_text(encoding='utf-8'))
    current={a['name']:a for a in source_report['candidateArtifacts']}
    package_names=[f'ManageYourLibrary-{version}-Setup-x64.exe',f'ManageYourLibrary-{version}-Windows-x64-portable.zip',
                   f'ManageYourLibrary-{version}.apk',f'ManageYourLibrary-{version}-Linux-x64.tar.gz']
    artifacts=[]
    for name in package_names:
        path=directory/name;prior=current.get(name)
        if path.is_symlink() or not path.is_file() or not prior or sha256(path).lower()!=prior['sha256'].lower() or path.stat().st_size!=prior['bytes']:
            raise ValueError('Package does not match recorded validated candidate: '+name)
        artifacts.append({'path':str(path.resolve()),'name':name,'version':version,'bytes':path.stat().st_size,
                          'sha256':sha256(path),'role':prior['platform'],'reusedFrom':'DG-0020'})
    descriptor=json.loads((directory/f'ManageYourLibrary-{version}.update.json').read_text())
    pin=(root/'platforms/android/release-certificate.sha256').read_text().strip()
    apk=next(a for a in artifacts if a['role']=='android-universal')
    if descriptor.get('certificateSha256')!=pin or descriptor.get('sha256')!=apk['sha256'] or descriptor.get('version')!=version:
        raise ValueError('Android update descriptor changed or uses a different signing key')
    # Offline fixture uses real candidate identities/hashes. It is not a live release or offer.
    fixture={'tag_name':'v'+version,'draft':False,'prerelease':False,'published_at':'2026-11-01T00:00:00Z','assets':[]}
    for artifact in artifacts:
        if artifact['role']=='android-universal':continue
        fixture['assets'].append({'name':artifact['name'],'state':'uploaded','size':artifact['bytes'],
            'digest':'sha256:'+artifact['sha256'],'browser_download_url':f'https://github.com/{DEFAULT_REPOSITORY}/releases/download/v{version}/{artifact["name"]}'})
    import io
    class Response(io.BytesIO):headers={}
    channel=UpdateChannel(opener=lambda _:Response(json.dumps([fixture]).encode()))
    for target in ['windows-installer-x64','windows-portable-x64','linux-x64']:
        result=channel.check('0.5.4',target)
        if result['offer'] is None or result['offer'].version!=version:raise ValueError('Prepared channel layout cannot select '+target)
    output.mkdir(parents=True,exist_ok=False)
    review={'taskId':'DG-0035','projectKey':'manage_your_library','product':PRODUCT,'version':version,
        'repository':DEFAULT_REPOSITORY,'artifacts':artifacts,'runtimeCompatibility':runtime,
        'identities':{'windowsAppId':APP_ID,'macBundleId':MAC_BUNDLE_ID,'androidPackage':'com.erzod31.manageyourlibrary','androidCertificateSha256':pin},
        'macOS':{'included':False,'reason':'Native QA bundles must not enter the production channel without Developer ID/team/Gatekeeper/stapled-ticket and release-signed APK approval.'},
        'prepared':True,'performed':False,'channelSourceChanged':False,'offlineChannelSelectionChecked':True,
        'targetCommit':None,'dependencies':['Commit the reviewed source snapshot matching the runtime baseline; do not tag the old dirty-tree base as new source.',
            'Review Windows NotSigned baseline and all package hashes; retain previous releases and all library data.',
            'macOS supplement requires matching native architecture/signature/notarization/distribution gate evidence.'],
        'steps':['After explicit operational review: create a NEW draft v'+version+' release at the reviewed source commit; never overwrite an existing tag/release.',
            'Upload only the verified artifacts plus Android descriptor/checksums/provenance. Compare GitHub asset digests/size with this plan.',
            'Verify complete platform selection in the existing real release channel while still a draft (drafts are ignored by clients).',
            'Only then publish the draft. Users check/download/confirm in the app; old binaries need one manual migration.'],
        'impact':'Publishing would make 0.5.5 selectable by explicit update checks on Windows/Linux; Android remains the paired PC bundled APK channel. No auto install, Tailscale/firewall/device or LG changes.',
        'rollback':'Return the new release to draft to stop new offers. Keep old releases and local rollback folders. Never silently downgrade or roll back catalogs/books.',
        'commandsForReviewOnly':[
            f'gh release view v{version} --repo {DEFAULT_REPOSITORY}  # abort if it already exists',
            f'gh release create v{version} --repo {DEFAULT_REPOSITORY} --target REVIEWED_SOURCE_COMMIT --draft --latest=false --notes-file REVIEWED_NOTES',
            f'gh release upload v{version} VERIFIED_FILES --repo {DEFAULT_REPOSITORY}  # no --clobber',
            f'gh release edit v{version} --repo {DEFAULT_REPOSITORY} --draft=false --latest=false',
            f'gh release edit v{version} --repo {DEFAULT_REPOSITORY} --draft=true']}
    (output/'publication-review.json').write_text(json.dumps(review,indent=2)+'\n')
    (output/'offline-release-layout-fixture.json').write_text(json.dumps(fixture,indent=2)+'\n')
    (output/'SHA256SUMS.txt').write_text(''.join(a['sha256']+'  '+a['name']+'\n' for a in artifacts))
    return review


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=ROOT/'dist/release')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-baseline',type=Path,default=ROOT/'docs/cleanup-DG-0028-manifest.json')
    args=parser.parse_args()
    review=prepare(args.artifacts,args.output,json.loads(args.runtime_baseline.read_text()))
    print(json.dumps({'prepared':review['prepared'],'performed':False,'artifacts':review['artifacts'],'runtimeCompatibility':review['runtimeCompatibility']},indent=2))
