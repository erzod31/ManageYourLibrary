"""Frozen updater smoke gate. Native installation is replaced by a fake launcher."""
import io
import json
import sys
import tempfile
import threading
import zipfile
from dataclasses import replace
from pathlib import Path


def run_and_record(output, *, version):
    from core.app_updates import APP_ID, DEFAULT_REPOSITORY, MAC_BUNDLE_ID, PRODUCT, UpdateChannel, UpdateError, UpdateOffer, sha256, version_tuple
    from core.update_apply import UpdateCoordinator, windows_file_info
    report={"version":version,"frozen":bool(getattr(sys,"frozen",False)),"checks":{},
            "nativeInstallationsApplied":False,"realInstallerExecuted":False,"launcher":"fake"}
    checks=report["checks"]
    try:
        import ui.update_panel
        assert callable(ui.update_panel.UpdatePanel)
        current=version_tuple(version);new_version=f"{current[0]}.{current[1]}.{current[2]+1}"
        with tempfile.TemporaryDirectory(prefix="myl_updater_fixture_") as temporary:
            root=Path(temporary);profile=root/"profile";profile.mkdir();library=root/"books";library.mkdir()
            book=library/"original.epub";book.write_bytes(b"Only synthetic QA data")
            catalog=profile/"catalog.json";catalog.write_text('{"sentinel":true}')
            original_hashes=(sha256(book),sha256(catalog))
            installed=root/"installed-stub";(installed/"_internal").mkdir(parents=True)
            (installed/"_internal/VERSION").write_text(version)
            (installed/"ManageYourLibrary.exe").write_bytes(b"PE fixture, not an executable")
            invocations=[]
            def launch(arguments):
                invocations.append(arguments)
                return type("FakeProcess",(),{"pid":12345})()
            def inspect(path):
                return {"product":"Manage Your Library","version":version if Path(path).parent==installed else new_version,
                        "status":"NotSigned","signer":""}
            manager=UpdateCoordinator(profile/"updates",version,"windows-portable-x64",installed,
                protected=[profile,library],native_inspect=inspect,launcher=launch)
            session=manager.new_session();name=f"ManageYourLibrary-{new_version}-Windows-x64-portable.zip";archive=session/name
            identity={"product":PRODUCT,"version":new_version,"platform":"windows-portable-x64","appId":APP_ID,"macBundleId":MAC_BUNDLE_ID}
            with zipfile.ZipFile(archive,"w") as target:
                target.writestr("ManageYourLibrary/_internal/update-identity.json",json.dumps(identity))
                target.writestr("ManageYourLibrary/_internal/VERSION",new_version)
                target.writestr("ManageYourLibrary/ManageYourLibrary.exe",b"PE fixture, never execute")
            offer=UpdateOffer(PRODUCT,new_version,manager.target,name,
                f"https://github.com/{DEFAULT_REPOSITORY}/releases/download/v{new_version}/{name}",
                archive.stat().st_size,sha256(archive),DEFAULT_REPOSITORY,"v"+new_version)
            class Response(io.BytesIO):
                headers={}
            release={"tag_name":offer.tag,"draft":False,"prerelease":False,"published_at":"2026-10-28T00:00:00Z",
                "assets":[{"name":name,"state":"uploaded","browser_download_url":offer.url,"size":offer.size,"digest":"sha256:"+offer.sha256}]}
            channel=UpdateChannel(opener=lambda _:Response(json.dumps([release]).encode()))
            assert channel.check(version,manager.target)["offer"]==offer
            assert channel.check(new_version,manager.target)["status"]=="up_to_date"
            checks["current_and_available_versions"]="passed"
            binary=archive.read_bytes();data_channel=UpdateChannel(opener=lambda _:Response(binary))
            download=data_channel.download(offer,version,manager.target,manager.new_session())
            assert sha256(download)==offer.sha256
            event=threading.Event();event.set()
            try:data_channel.download(offer,version,manager.target,manager.new_session(),cancelled=event)
            except UpdateError:pass
            else:raise AssertionError("Cancellation ignored")
            checks["verified_download_and_cancellation"]="passed"
            plan=manager.prepare(offer,download)
            try:manager.handoff(plan)
            except UpdateError:pass
            else:raise AssertionError("Missing confirmation accepted")
            if sys.platform=="win32":
                result=manager.handoff(plan,confirmed=True)
                assert Path(result["arguments"][0]).name=="powershell.exe" and len(invocations)==1
            else:
                # Request a POSIX handoff separately in unit tests; never run a
                # Windows helper even with stub files on a native POSIX runner.
                assert not invocations
            checks["explicit_confirmation_fake_handoff"]="passed"
            for changed in (replace(offer,product="Other"),replace(offer,platform="linux-x64"),replace(offer,version=version)):
                try:changed.validate(version,manager.target)
                except UpdateError:pass
                else:raise AssertionError("Wrong product/platform/version accepted")
            download.write_bytes(b"Altered after preparation")
            try:manager.handoff(plan,confirmed=True)
            except UpdateError:pass
            else:raise AssertionError("Altered package accepted")
            checks["tamper_wrong_identity_and_downgrade_rejection"]="passed"
            assert original_hashes==(sha256(book),sha256(catalog))
            checks["library_profile_unchanged"]="passed"
            if sys.platform=="win32" and getattr(sys,"frozen",False):
                native=windows_file_info(sys.executable)
                assert native["product"]=="Manage Your Library" and native["version"]==version
                assert native["status"] in {"NotSigned","Valid"}
                checks["own_pe_metadata_signature_readonly"]="passed"
        report["passed"]=True
    except Exception as exc:
        report.update(passed=False,error=f"{type(exc).__name__}: {exc}")
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return 0 if report["passed"] else 1
