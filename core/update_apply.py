"""Verified staging and native update handoff; libraries and profiles stay outside."""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from .app_updates import APP_ID, MAC_BUNDLE_ID, PRODUCT, UpdateError, UpdateOffer, atomic_json, sha256

MAX_EXPANDED = 3 * 1024**3
MAX_MEMBERS = 30000


def windows_powershell():
    return str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")


def windows_powershell_environment():
    # PowerShell 7 can export an incompatible module search path to a Python
    # child. The trusted Windows PowerShell verifier needs its own system modules.
    environment = os.environ.copy()
    environment["PSModulePath"] = str(Path(windows_powershell()).parent / "Modules")
    return environment


def checked_run(arguments):
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise UpdateError("La verificación nativa rechazó el paquete. No se instaló ningún cambio.")
    return result.stdout


def windows_file_info(path):
    # Pass the path as an environment value, never interpolated shell code.
    script = "$ErrorActionPreference='Stop'; $p=$env:MYL_VERIFY_FILE; $v=[Diagnostics.FileVersionInfo]::GetVersionInfo($p); $s=Get-AuthenticodeSignature -LiteralPath $p; @{product=$v.ProductName;version=$v.ProductVersion;status=[string]$s.Status;signer=$(if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{''})}|ConvertTo-Json -Compress"
    env = windows_powershell_environment()
    env["MYL_VERIFY_FILE"] = str(Path(path).resolve())
    result = subprocess.run([windows_powershell(), "-NoProfile", "-NonInteractive", "-Command", script],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise UpdateError("Windows no pudo verificar la identidad y firma del paquete.")
    try:
        value = json.loads(result.stdout.lstrip("\ufeff"))
    except (ValueError, TypeError) as exc:
        raise UpdateError("La verificación de Windows no devolvió una identidad válida.") from exc
    return value


def verify_windows(path, version, *, installed=None, inspect=windows_file_info):
    value = inspect(path)
    actual = str(value.get("version") or "").strip()
    if actual.endswith(".0") and actual.count(".") == 3:
        actual = actual[:-2]
    if str(value.get("product") or "").strip() != "Manage Your Library" or actual != version:
        raise UpdateError("El ejecutable no pertenece al producto y versión esperados.")
    status = value.get("status")
    if status not in {"Valid", "NotSigned"}:
        raise UpdateError("La firma Authenticode es inválida o Windows no confía en ella.")
    previous = inspect(installed) if installed else None
    if previous and previous.get("status") not in {"Valid", "NotSigned"}:
        raise UpdateError("No se puede establecer la firma de la aplicación instalada.")
    if previous and previous.get("status") == "Valid":
        if status != "Valid" or not value.get("signer") or value.get("signer") != previous.get("signer"):
            raise UpdateError("La actualización no conserva el firmante de la aplicación instalada.")
    return {"kind": "authenticode", "status": status, "signer": value.get("signer", "")}


def _member_path(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name or ":" in name:
        raise UpdateError("El archivo contiene una ruta no segura.")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"..", "."} for part in path.parts):
        raise UpdateError("El archivo contiene una ruta fuera del paquete.")
    return path


def extract_archive(archive, folder):
    """Reject traversal/devices/hardlinks; create internal macOS symlinks last."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    links, names, total = [], set(), 0
    is_zip = zipfile.is_zipfile(archive)
    opened = zipfile.ZipFile(archive) if is_zip else tarfile.open(archive, "r:gz")
    try:
        members = opened.infolist() if is_zip else opened.getmembers()
        if len(members) > MAX_MEMBERS:
            raise UpdateError("El paquete contiene demasiados archivos.")
        entries = []
        for member in members:
            relative = _member_path(member.filename if is_zip else member.name)
            key = str(relative).casefold()
            if key in names:
                raise UpdateError("El paquete contiene rutas duplicadas.")
            names.add(key)
            mode = (member.external_attr >> 16) if is_zip else member.mode
            is_link = stat.S_ISLNK(mode) if is_zip else member.issym()
            is_dir = member.is_dir() if is_zip else member.isdir()
            if not is_zip and not (member.isfile() or is_dir or is_link):
                raise UpdateError("El paquete contiene enlaces duros o archivos especiales.")
            if is_zip and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                raise UpdateError("El paquete contiene un archivo especial.")
            size = member.file_size if is_zip else member.size
            total += size
            if total > MAX_EXPANDED or size > MAX_EXPANDED:
                raise UpdateError("El paquete descomprimido supera el límite de espacio.")
            entries.append((member, relative, mode, is_link, is_dir))
        link_paths = [str(relative).casefold() for _, relative, _, link, _ in entries if link]
        if shutil.disk_usage(folder).free < total + 128 * 1024**2:
            raise UpdateError("Falta espacio libre para preparar la actualización con seguridad.")
        for member, relative, mode, is_link, is_dir in entries:
            if any(str(relative).casefold().startswith(name + "/") for name in link_paths):
                raise UpdateError("Un archivo intenta atravesar un enlace del paquete.")
            destination = folder.joinpath(*relative.parts)
            if is_link:
                target = opened.read(member).decode("utf-8") if is_zip else member.linkname
                target_path = PurePosixPath(target)
                if target_path.is_absolute() or any(c in target for c in ("\\", ":", "\x00")):
                    raise UpdateError("El enlace contiene un destino no seguro.")
                resolved = (destination.parent / str(target_path)).resolve()
                if not resolved.is_relative_to(folder.resolve()):
                    raise UpdateError("Un enlace sale de la carpeta de preparación.")
                links.append((destination, target))
            elif is_dir:
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                stream = opened.open(member) if is_zip else opened.extractfile(member)
                with stream as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if destination.stat().st_size != (member.file_size if is_zip else member.size):
                    raise UpdateError("El archivo descomprimido está incompleto.")
                if os.name != "nt":
                    destination.chmod(mode & 0o777)
        for destination, target in links:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(target)
    finally:
        opened.close()
    return folder


def inventory(folder):
    result = {}
    for file in sorted(Path(folder).rglob("*")):
        relative = file.relative_to(folder).as_posix()
        if file.is_symlink():
            if not file.resolve().is_relative_to(Path(folder).resolve()):
                raise UpdateError("Un enlace sale de la aplicación.")
            result[relative] = {"link": os.readlink(file)}
        elif file.is_file():
            result[relative] = {"sha256": sha256(file), "size": file.stat().st_size}
    return result


def verify_identity(root, offer):
    root = Path(root)
    markers = [root / "_internal/update-identity.json", root / "Contents/Frameworks/update-identity.json",
               root / "Contents/Resources/update-identity.json"]
    found = [path for path in markers if path.is_file()]
    if not found:
        raise UpdateError("Falta la identidad de actualización del paquete. No se reemplazará la app.")
    value = json.loads(found[0].read_text(encoding="utf-8"))
    expected = {"product": PRODUCT, "version": offer.version, "platform": offer.platform,
                "appId": APP_ID, "macBundleId": MAC_BUNDLE_ID}
    if any(value.get(key) != item for key, item in expected.items()):
        raise UpdateError("La identidad interna del paquete no corresponde al producto, plataforma o versión.")
    version_file = found[0].parent / "VERSION"
    if not version_file.is_file() or version_file.read_text(encoding="utf-8").strip() != offer.version:
        raise UpdateError("La versión interna de la aplicación no coincide con el canal.")
    if offer.platform.startswith("macos"):
        plist = plistlib.loads((root / "Contents/Info.plist").read_bytes())
        if (plist.get("CFBundleIdentifier") != MAC_BUNDLE_ID or plist.get("CFBundleShortVersionString") != offer.version or
                plist.get("CFBundleExecutable") != "ManageYourLibrary"):
            raise UpdateError("El bundle macOS no conserva su identidad o versión.")
        executable = root / "Contents/MacOS/ManageYourLibrary"
    else:
        executable = root / ("ManageYourLibrary.exe" if offer.platform.startswith("windows") else "ManageYourLibrary")
    if not executable.is_file():
        raise UpdateError("Falta el ejecutable principal del paquete.")
    return executable


def verify_mac(root, installed, *, run=checked_run):
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(root)])
    def team(path):
        # codesign emits identity information to stderr even on success.
        result = subprocess.run(["/usr/bin/codesign", "-dv", "--verbose=4", str(path)], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise UpdateError("macOS no pudo leer la identidad de firma.")
        import re
        match = re.search(r"^TeamIdentifier=(.+)$", result.stderr, re.M)
        return match.group(1) if match else "not set"
    old_team, new_team = team(installed), team(root)
    if old_team != "not set" and old_team != new_team:
        raise UpdateError("El paquete cambia la identidad del desarrollador macOS.")
    # Gatekeeper remains authoritative. No removal of quarantine or re-signing.
    run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(root)])
    return {"kind": "codesign-and-gatekeeper", "status": "Valid", "team": new_team}


def protect_install_root(install_root, protected):
    root = Path(install_root).resolve()
    if root == Path(root.anchor) or root == Path.home().resolve() or root.is_symlink():
        raise UpdateError("La carpeta de instalación no es segura para una actualización.")
    for path in protected:
        path = Path(path).resolve()
        if path == root or path.is_relative_to(root) or root.is_relative_to(path):
            raise UpdateError("La instalación se cruza con la biblioteca o el perfil. Conserva los datos y utiliza una instalación separada.")
    return root


class UpdateCoordinator:
    def __init__(self, state, current_version, target, install_root, *, protected=(), native_inspect=windows_file_info,
                 mac_verify=verify_mac, launcher=None):
        self.state = Path(state).resolve()
        self.version, self.target = current_version, target
        self.install_root = Path(install_root).resolve()
        self.protected = list(protected)
        self.native_inspect, self.mac_verify = native_inspect, mac_verify
        self.real_launcher = launcher is None
        self.launcher = launcher or self._launch

    @staticmethod
    def _launch(arguments):
        return subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=windows_powershell_environment() if os.name == "nt" and arguments[0] == windows_powershell() else None)

    def new_session(self):
        self.state.mkdir(parents=True, exist_ok=True)
        session = self.state / uuid.uuid4().hex
        session.mkdir(mode=0o700)
        return session

    def prepare(self, offer, package):
        offer.validate(self.version, self.target)
        package = Path(package).resolve()
        if not package.is_relative_to(self.state) or package.stat().st_size != offer.size or sha256(package) != offer.sha256:
            raise UpdateError("El paquete descargado cambió antes de prepararlo.")
        install_root = protect_install_root(self.install_root, [self.state, *self.protected])
        if self.target != "windows-installer-x64" and not os.access(install_root.parent, os.W_OK):
            raise UpdateError("La carpeta de aplicaciones requiere permisos de administración. No se cerrará ni modificará la aplicación.")
        session = package.parent
        signature = {"kind": "github-https-sha256", "status": "No platform signature"}
        staged_root = None
        if self.target == "windows-installer-x64":
            signature = verify_windows(package, offer.version, installed=install_root / "ManageYourLibrary.exe", inspect=self.native_inspect)
            launch = "ManageYourLibrary.exe"
        else:
            stage = extract_archive(package, session / "stage")
            root_name = "ManageYourLibrary.app" if self.target.startswith("macos") else "ManageYourLibrary"
            staged_root = stage / root_name
            if list(stage.iterdir()) != [staged_root]:
                raise UpdateError("El archivo no contiene una única aplicación válida.")
            executable = verify_identity(staged_root, offer)
            launch = executable.relative_to(staged_root).as_posix()
            if self.target.startswith("windows"):
                signature = verify_windows(executable, offer.version, installed=install_root / launch, inspect=self.native_inspect)
            elif self.target.startswith("macos"):
                signature = self.mac_verify(staged_root, install_root)
        plan = {"schema": 1, "product": PRODUCT, "appId": APP_ID, "offer": asdict(offer),
                "currentVersion": self.version, "target": self.target, "package": str(package),
                "installRoot": str(install_root), "stagedRoot": str(staged_root or ""), "launch": launch,
                "rollbackRoot": str(install_root.with_name(install_root.name + ".before-" + self.version + "-" + session.name[:8])),
                "protectedPaths": [str(p) for p in [self.state, *self.protected]], "signature": signature,
                "stagedFiles": inventory(staged_root) if staged_root else {}, "state": "verified",
                "ownerPid": os.getpid(), "created": time.time()}
        if sha256(package) != offer.sha256:
            raise UpdateError("El archivo cambió mientras se verificaba la aplicación.")
        path = session / "plan.json"
        atomic_json(path, plan)
        return path

    def handoff(self, plan_path, *, confirmed=False, cancelled=None):
        if confirmed is not True:
            raise UpdateError("La actualización necesita confirmación explícita.")
        path, plan, offer = validate_plan(plan_path, self.state)
        if plan["target"] != self.target or plan["currentVersion"] != self.version or Path(plan["installRoot"]) != self.install_root:
            raise UpdateError("El plan no pertenece a esta instalación.")
        if self.target == "windows-installer-x64":
            verify_windows(plan["package"], offer.version, installed=self.install_root / "ManageYourLibrary.exe", inspect=self.native_inspect)
            # Inno Setup retains its normal license/security/user confirmations.
            arguments = [plan["package"], "/DIR=" + str(self.install_root), "/RESTARTAPPLICATIONS"]
        elif self.target.startswith("windows"):
            source = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "platforms/windows/APPLY_PORTABLE_UPDATE.ps1"
            helper = path.parent / "apply-portable.ps1"
            shutil.copyfile(source, helper)
            arguments = [windows_powershell(), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-File", str(helper), "-PlanPath", str(path)]
        else:
            arguments = [sys.executable, "--apply-update", str(path)]
        plan["state"] = "handoff_requested"
        atomic_json(path, plan)
        if cancelled is not None and cancelled.is_set():
            plan["state"] = "verified"
            atomic_json(path, plan)
            from .app_updates import UpdateCancelled
            raise UpdateCancelled("Instalación cancelada antes de abrir el instalador.")
        try:
            process = self.launcher(arguments)
            if self.real_launcher and self.target != "windows-installer-x64":
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise UpdateError("El sistema impidió iniciar el aplicador. La aplicación actual sigue abierta.")
                    if cancelled is not None and cancelled.is_set():
                        process.terminate()  # Only our helper, before the parent exits or any swap.
                        raise UpdateError("Actualización cancelada antes del cierre.")
                    status = json.loads(path.read_text(encoding="utf-8"))
                    if status.get("state") == "waiting_parent":
                        break
                    time.sleep(.05)
                else:
                    process.terminate()
                    raise UpdateError("El aplicador no confirmó su inicio. Se conserva la aplicación abierta.")
        except Exception:
            plan["state"] = "handoff_failed"
            atomic_json(path, plan)
            raise
        return {"arguments": arguments, "pid": getattr(process, "pid", None), "restart": "native_installer_open_action" if self.target.endswith("installer-x64") else "helper_after_exit"}


def validate_plan(path, state):
    path, state = Path(path).resolve(), Path(state).resolve()
    if not path.is_relative_to(state) or path.name != "plan.json":
        raise UpdateError("Plan de actualización fuera de su carpeta privada.")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema") != 1 or plan.get("product") != PRODUCT or plan.get("appId") != APP_ID:
        raise UpdateError("El plan pertenece a otro producto.")
    offer = UpdateOffer(**plan["offer"]).validate(plan["currentVersion"], plan["target"])
    package = Path(plan["package"]).resolve()
    if (package.parent != path.parent or package.name != offer.name or not package.is_file() or
            package.stat().st_size != offer.size or sha256(package) != offer.sha256):
        raise UpdateError("El paquete cambió después de la verificación.")
    root = protect_install_root(plan["installRoot"], plan["protectedPaths"])
    rollback = Path(plan["rollbackRoot"])
    if rollback.parent != root.parent or not rollback.name.startswith(root.name + ".before-") or rollback.exists():
        raise UpdateError("La carpeta de recuperación no es válida o ya existe.")
    if plan["target"] != "windows-installer-x64":
        staged = Path(plan["stagedRoot"]).resolve()
        expected_name = "ManageYourLibrary.app" if plan["target"].startswith("macos") else "ManageYourLibrary"
        if staged.parent != path.parent / "stage" or staged.name != expected_name or inventory(staged) != plan["stagedFiles"]:
            raise UpdateError("La aplicación preparada cambió después de verificarla.")
        verify_identity(staged, offer)
        versions = [root / "_internal/VERSION", root / "Contents/Frameworks/VERSION", root / "Contents/Resources/VERSION"]
        present = [p for p in versions if p.is_file()]
        if not present or present[0].read_text(encoding="utf-8").strip() != plan["currentVersion"]:
            raise UpdateError("La instalación cambió desde que se preparó el plan.")
    return path, plan, offer


def apply_posix_plan(path, state, *, launcher=subprocess.Popen, wait_parent=True, mac_verify=verify_mac):
    """Called by the old frozen binary on POSIX, with a retained rollback folder."""
    path, plan, offer = validate_plan(path, state)
    if plan["target"].startswith("windows"):
        raise UpdateError("Este aplicador no ejecuta paquetes Windows.")
    if plan.get("state") != "handoff_requested":
        raise UpdateError("El plan no ha sido confirmado desde la aplicación.")
    plan["state"] = "waiting_parent"
    atomic_json(path, plan)
    if wait_parent:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                os.kill(int(plan["ownerPid"]), 0)
            except ProcessLookupError:
                break
            time.sleep(.2)
        else:
            plan["state"] = "waiting_parent_timeout"
            atomic_json(path, plan)
            raise UpdateError("La aplicación sigue abierta. No se forzó su cierre.")
    path, plan, offer = validate_plan(path, state)
    root, staged, rollback = map(Path, (plan["installRoot"], plan["stagedRoot"], plan["rollbackRoot"]))
    if plan["target"].startswith("macos"):
        mac_verify(staged, root)
    adjacent = root.with_name(root.name + ".prepared-" + path.parent.name[:8])
    protect_install_root(adjacent, plan["protectedPaths"])
    plan["preparedRoot"] = str(adjacent)
    atomic_json(path, plan)
    if not adjacent.exists():
        shutil.copytree(staged, adjacent, symlinks=True)
    if inventory(adjacent) != plan["stagedFiles"]:
        raise UpdateError("La copia preparada cambió. Se conserva para revisión.")
    if plan["target"].startswith("macos"):
        mac_verify(adjacent, root)
    plan["state"] = "applying"
    atomic_json(path, plan)
    try:
        root.rename(rollback)
        adjacent.rename(root)
        arguments = ["/usr/bin/open", "-n", str(root)] if plan["target"].startswith("macos") else [str(root / plan["launch"])]
        launcher(arguments)
    except Exception as exc:
        # No delete: preserve the failed candidate and restore the old folder.
        try:
            if rollback.exists():
                if root.exists():
                    root.rename(adjacent)
                rollback.rename(root)
            plan.update(state="rolled_back", error=str(exc))
        except OSError as recovery:
            plan.update(state="needs_recovery", error=str(exc), recoveryError=str(recovery))
        atomic_json(path, plan)
        raise
    plan["state"] = "completed"
    atomic_json(path, plan)
    return plan
