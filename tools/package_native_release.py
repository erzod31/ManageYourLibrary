"""Package a native onedir build with the existing published archive layout."""
import argparse
import json
import os
import platform
import stat
import sys
import tarfile
import tempfile
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.write_build_manifest import sha256, source_tree_fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform",choices=["linux","macos"],required=True)
    parser.add_argument("--validation-only",action="store_true",help="Explicitly permit a non-distributable native QA candidate")
    args=parser.parse_args()
    if (args.platform=="macos" and sys.platform!="darwin") or (args.platform=="linux" and not sys.platform.startswith("linux")):
        raise SystemExit("Run the native build and packaging on the target OS")
    version=(ROOT/"VERSION").read_text().strip()
    arch="arm64" if platform.machine().lower() in {"aarch64","arm64"} else "x64"
    bundle=ROOT/"dist"/args.platform/("ManageYourLibrary.app" if args.platform=="macos" else "ManageYourLibrary")
    executable=bundle/"Contents/MacOS/ManageYourLibrary" if args.platform=="macos" else bundle/"ManageYourLibrary"
    manifest_path = ROOT/"dist/macos/build-manifest.json" if args.platform=="macos" else executable.parent/"build-manifest.json"
    manifest=json.loads(manifest_path.read_text())
    if manifest["version"]!=version or manifest["source_tree"]!=source_tree_fingerprint() or manifest["sha256"]!=sha256(executable):
        raise SystemExit("Native build provenance no longer matches the source/executable")
    if any(manifest["validation"].get(name)!="passed" for name in ("automated_tests","frozen_smoke","runtime_self_test","first_use_self_test","mobile_self_test","updater_self_test")):
        raise SystemExit("Required native build gates have not passed")
    quality = None
    if args.platform == "macos":
        from tools.validate_macos_release import native_validate
        quality = native_validate(bundle, version, arch, require_distribution=not args.validation_only,
                                  expected_team=os.environ.get('MYL_MACOS_TEAM_ID'))
        if not quality['passed']:
            raise SystemExit('Native macOS architecture/signature/distribution gates rejected this bundle')
    output=ROOT/"dist/native-release";output.mkdir(parents=True,exist_ok=True)
    archive=output/f"ManageYourLibrary-{version}-{'macOS' if args.platform=='macos' else 'Linux'}-{arch}{'.zip' if args.platform=='macos' else '.tar.gz'}"
    if archive.exists():raise SystemExit("Previous native candidate is preserved; choose an isolated output workspace")
    if args.platform=="macos":
        with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as target:
            for path in sorted(bundle.rglob("*")):
                relative=(Path(bundle.name)/path.relative_to(bundle)).as_posix()
                if path.is_symlink():
                    info=zipfile.ZipInfo(relative);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                    target.writestr(info,path.readlink().as_posix())
                elif path.is_file():target.write(path,relative)
    else:
        with tarfile.open(archive,"x:gz",dereference=False) as target:target.add(bundle,arcname=bundle.name)
    (output/(archive.name+".sha256")).write_text(sha256(archive)+"  "+archive.name+"\n")
    if args.platform == "macos":
        from core.update_apply import extract_archive, inventory
        with tempfile.TemporaryDirectory(prefix='myl_macos_archive_check_') as temporary:
            destination = extract_archive(archive,Path(temporary)/'stage') / bundle.name
            if inventory(destination) != inventory(bundle):
                raise SystemExit('Packaged macOS bytes/modes/symlinks differ from the validated bundle')
            original_modes={name:stat.S_IMODE((bundle/name).lstat().st_mode) for name in inventory(bundle)}
            extracted_modes={name:stat.S_IMODE((destination/name).lstat().st_mode) for name in inventory(destination)}
            if original_modes != extracted_modes:
                raise SystemExit('Packaged macOS permission bits changed during extraction')
            roundtrip = native_validate(destination, version, arch, require_distribution=not args.validation_only,
                                       expected_team=os.environ.get('MYL_MACOS_TEAM_ID'))
            if not roundtrip['passed']:
                raise SystemExit('Extracted archive failed native macOS gates')
            environment=os.environ.copy()
            for name in ['XDG_DATA_HOME','XDG_CONFIG_HOME','APPDATA','LOCALAPPDATA']:
                environment[name]=str(Path(temporary)/'profile'/name)
            environment['MANAGE_YOUR_LIBRARY_OFFLINE']='1'
            for option in ['smoke-test','runtime-self-test','first-use-self-test','mobile-self-test','update-self-test']:
                command=[str(destination/'Contents/MacOS/ManageYourLibrary'),'--'+option]
                if option!='smoke-test':command.append(str(output/(archive.stem+'-extracted-'+option+'.json')))
                subprocess.run(command,env=environment,check=True,timeout=180)
        (output/(archive.stem+'-native-validation.json')).write_text(json.dumps({'beforePackaging':quality,'afterExtraction':roundtrip},indent=2))
    result={"artifact":str(archive),"version":version,"bytes":archive.stat().st_size,"sha256":sha256(archive),"published":False}
    if quality is not None:
        result.update(distributionEligible=quality['distributionEligible'],validationMode=quality['validationMode'])
    (output/(archive.stem+'-candidate.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
