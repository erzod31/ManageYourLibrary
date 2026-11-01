"""Distribution gates must reject wrong identity/architecture, QA keys and native approval gaps."""
import hashlib
import json
import os
import plistlib
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from core.app_updates import APP_ID, MAC_BUNDLE_ID, PRODUCT
from tools import validate_android_build_input as android
from tools import validate_macos_release as mac
from tools.lock_native_wheels import wheel_record
from tools import prepare_macos_python_notices as notices


def fixture_unix_permissions():
    """Windows cannot store POSIX executable bits; emulate them only on synthetic fixture files."""
    original=Path.stat
    def stat(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        if path.name=='ManageYourLibrary' and path.parent.name=='MacOS':
            fields=list(value);fields[0]|=0o111;return os.stat_result(fields)
        return value
    return patch.object(Path,'stat',stat)


def bundle_fixture(root, arch='arm64'):
    bundle=root/'ManageYourLibrary.app'
    (bundle/'Contents/MacOS').mkdir(parents=True)
    resources=bundle/'Contents/Resources';resources.mkdir()
    (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':MAC_BUNDLE_ID,
        'CFBundleExecutable':'ManageYourLibrary','CFBundleVersion':'0.5.5','CFBundleShortVersionString':'0.5.5',
        'LSMinimumSystemVersion':'14.0'}))
    (resources/'update-identity.json').write_text(json.dumps({'product':PRODUCT,'appId':APP_ID,'macBundleId':MAC_BUNDLE_ID,
        'version':'0.5.5','platform':'macos-'+arch}))
    (resources/'VERSION').write_text('0.5.5')
    notice_folder=resources/'third_party/python-runtime';notice_folder.mkdir(parents=True)
    notice_hashes={}
    for name in notices.REQUIRED:
        content=b'Synthetic unit-test fixture; no distribution approval'
        (notice_folder/name).write_bytes(content);notice_hashes[name]=hashlib.sha256(content).hexdigest()
    target,archive_hash=notices.SOURCES[arch]
    (notice_folder/'provenance.json').write_text(json.dumps({'release':notices.RELEASE,'pythonVersion':'3.12.16',
        'target':target,'archiveSha256':archive_hash,'notices':notice_hashes}))
    executable=bundle/'Contents/MacOS/ManageYourLibrary'
    executable.write_bytes(b'\xcf\xfa\xed\xfe'+struct.pack('<I',0x0100000C if arch=='arm64' else 0x01000007)+b'\0'*24)
    executable.chmod(0o755)
    return bundle


class MacReleaseGateTests(unittest.TestCase):
    def test_macho_thin_fat_and_truncated_headers(self):
        for cpu,name in [(0x01000007,'x64'),(0x0100000C,'arm64')]:
            self.assertEqual(mac.macho_architectures(b'\xcf\xfa\xed\xfe'+struct.pack('<I',cpu)),{name})
        fat=b'\xca\xfe\xba\xbe'+struct.pack('>I',2)+struct.pack('>IIIII',0x01000007,0,0,0,0)+struct.pack('>IIIII',0x0100000C,0,0,0,0)
        self.assertEqual(mac.macho_architectures(fat),{'arm64','x64'})
        with self.assertRaises(ValueError):mac.macho_architectures(fat[:20])
        self.assertEqual(mac.macho_architectures(b'ordinary resource'),set())

    def test_bundle_identity_and_all_macho_architectures(self):
        with tempfile.TemporaryDirectory() as temporary, fixture_unix_permissions():
            bundle=bundle_fixture(Path(temporary))
            self.assertEqual(mac.inspect_bundle(bundle,'0.5.5','arm64')['machOBinariesChecked'],1)
            extra=bundle/'Contents/Resources/wrong.so';extra.write_bytes(b'\xcf\xfa\xed\xfe'+struct.pack('<I',0x01000007))
            with self.assertRaises(ValueError):mac.inspect_bundle(bundle,'0.5.5','arm64')
            extra.unlink()
            with self.assertRaises(ValueError):mac.inspect_bundle(bundle,'0.5.6','arm64')
            identity=bundle/'Contents/Resources/update-identity.json'
            value=json.loads(identity.read_text());value['macBundleId']='other.app';identity.write_text(json.dumps(value))
            with self.assertRaises(ValueError):mac.inspect_bundle(bundle,'0.5.5','arm64')

    def test_native_command_gate_cannot_run_on_windows_or_linux(self):
        runner=Mock()
        with patch.object(mac.sys,'platform','win32'),self.assertRaises(RuntimeError):
            mac.native_validate(Path('not-a-real-app'),'0.5.5','arm64',run=runner)
        runner.assert_not_called()

    def test_bundle_rejects_missing_minimum_os_or_changed_runtime_notices(self):
        with tempfile.TemporaryDirectory() as temporary, fixture_unix_permissions():
            bundle=bundle_fixture(Path(temporary))
            info=bundle/'Contents/Info.plist';original=info.read_bytes();value=plistlib.loads(original)
            del value['LSMinimumSystemVersion'];info.write_bytes(plistlib.dumps(value))
            with self.assertRaisesRegex(ValueError,'14.0'):mac.inspect_bundle(bundle,'0.5.5','arm64')
            info.write_bytes(original)
            (bundle/'Contents/Resources/third_party/python-runtime/LICENSE.tcl.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'changed'):mac.inspect_bundle(bundle,'0.5.5','arm64')

    def test_full_python_archive_hash_is_checked_before_tar_or_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'wrong.tar.zst';archive.write_bytes(b'altered download')
            with patch.object(notices.subprocess,'check_output') as tar, self.assertRaisesRegex(ValueError,'hash'):
                notices.prepare(archive,root/'python',root/'notices','arm64')
            tar.assert_not_called();self.assertFalse((root/'notices').exists())

    def test_qa_adhoc_gate_is_never_distribution_approved(self):
        with tempfile.TemporaryDirectory() as temporary, fixture_unix_permissions():
            bundle=bundle_fixture(Path(temporary))
            runner=Mock(side_effect=[{'exitCode':0,'output':''},{'exitCode':0,'output':'Signature=adhoc\nTeamIdentifier=not set'},
                                    {'exitCode':3,'output':'rejected'},{'exitCode':65,'output':'ticket missing'}]*2)
            with patch.object(mac.sys,'platform','darwin'),patch.object(mac.platform,'machine',return_value='arm64'):
                qa=mac.native_validate(bundle,'0.5.5','arm64',run=runner)
                distribution=mac.native_validate(bundle,'0.5.5','arm64',require_distribution=True,run=runner)
            self.assertTrue(qa['passed']);self.assertFalse(qa['distributionEligible']);self.assertFalse(distribution['passed'])

    def test_distribution_needs_actual_team_gatekeeper_ticket_and_trusted_apk(self):
        with tempfile.TemporaryDirectory() as temporary, fixture_unix_permissions():
            root=Path(temporary);bundle=bundle_fixture(root)
            (root/'dist/android').mkdir(parents=True);(root/'platforms/android').mkdir(parents=True)
            pin=(android.ROOT/'platforms/android/release-certificate.sha256').read_text().strip()
            (root/'platforms/android/release-certificate.sha256').write_text(pin)
            apk=bundle/'Contents/Resources/android/ManageYourLibrary-0.5.5.apk';apk.parent.mkdir();apk.write_bytes(b'synthetic APK')
            proof={'passed':True,'releaseSigner':True,'sha256':android.digest(apk),'version':'0.5.5','certificateSha256':pin}
            (root/'dist/android/build-input-validation.json').write_text(json.dumps(proof))
            def runner(args):return {'exitCode':0,'output':'Authority=Developer ID Application: Synthetic QA\nTeamIdentifier=TEAM'}
            with patch.object(mac,'ROOT',root),patch.object(mac.sys,'platform','darwin'),patch.object(mac.platform,'machine',return_value='arm64'):
                self.assertTrue(mac.native_validate(bundle,'0.5.5','arm64',expected_team='TEAM',require_distribution=True,run=runner)['passed'])
                self.assertFalse(mac.native_validate(bundle,'0.5.5','arm64',expected_team='OTHER',require_distribution=True,run=runner)['passed'])
                apk.write_bytes(b'changed after certification')
                self.assertFalse(mac.native_validate(bundle,'0.5.5','arm64',expected_team='TEAM',require_distribution=True,run=runner)['passed'])


class AndroidInputAndWheelTests(unittest.TestCase):
    def test_apk_pin_version_hash_and_ci_key_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);apk=root/'ManageYourLibrary-0.5.5.apk';apk.write_bytes(b'synthetic, never installed')
            pin=(android.ROOT/'platforms/android/release-certificate.sha256').read_text().strip()
            metadata={'schema':1,'product':'ManageYourLibrary','platform':'android-universal','version':'0.5.5',
                'packageName':'com.erzod31.manageyourlibrary','versionCode':5005,'minSdk':26,'name':apk.name,
                'bytes':apk.stat().st_size,'sha256':android.digest(apk),'certificateSha256':pin}
            descriptor=apk.with_suffix('.update.json');descriptor.write_text(json.dumps(metadata))
            signature='Number of signers: 1\nSigner #1 certificate SHA-256 digest: '+pin
            badging="package: name='com.erzod31.manageyourlibrary' versionCode='5005' versionName='0.5.5'\nsdkVersion:'26'\ntargetSdkVersion:'37'"
            self.assertTrue(android.validate(root,'0.5.5',signature,badging)['releaseSigner'])
            for field,value in [('sha256','0'*64),('packageName','other.app'),('version','0.5.4')]:
                descriptor.write_text(json.dumps(dict(metadata,**{field:value})))
                with self.assertRaises(ValueError):android.validate(root,'0.5.5',signature,badging)
            metadata['certificateSha256']='a'*64;descriptor.write_text(json.dumps(metadata))
            signature=signature.replace(pin,'a'*64)
            with self.assertRaises(ValueError):android.validate(root,'0.5.5',signature,badging)
            self.assertFalse(android.validate(root,'0.5.5',signature,badging,allow_ci_certificate=True)['distributionEligible'])

    def test_wheel_lock_uses_real_metadata_and_content_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            wheel=Path(temporary)/'fixture.whl'
            with zipfile.ZipFile(wheel,'w') as archive:archive.writestr('fixture-1.0.dist-info/METADATA','Name: fixture\nVersion: 1.0\n')
            record=wheel_record(wheel)
            self.assertEqual(record['name'],'fixture');self.assertEqual(record['sha256'],android.digest(wheel))
            with zipfile.ZipFile(wheel,'a') as archive:archive.writestr('fixture/_vendor/nested-1.0.dist-info/METADATA','Name: nested\nVersion: 1.0\n')
            self.assertEqual(wheel_record(wheel)['name'],'fixture')
            with zipfile.ZipFile(wheel,'a') as archive:archive.writestr('other-1.0.dist-info/METADATA','Name: other\nVersion: 1.0\n')
            with self.assertRaises(ValueError):wheel_record(wheel)


if __name__=='__main__':unittest.main()
