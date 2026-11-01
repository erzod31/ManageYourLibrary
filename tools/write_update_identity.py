"""Generate build-only product identity inside each native application payload."""
import argparse
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app_updates import APP_ID, MAC_BUNDLE_ID, PRODUCT


def write(output, target):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {"schema": 1, "product": PRODUCT, "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
             "platform": target, "appId": APP_ID, "macBundleId": MAC_BUNDLE_ID}
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--platform", choices=["linux", "macos"], required=True)
    args = parser.parse_args()
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    write(args.output, args.platform + "-" + arch)
