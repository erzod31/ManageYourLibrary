"""Temporary, private Serve smoke check with disposable data and exact cleanup."""
import argparse
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.mobile_access import DeviceAccess, MobileService
from core.mobile_tailscale import TailscaleAccess


class FixtureAdapter:
    def dispatch(self, method, path, query, body, owner):
        if path != "/api/v1/status":
            raise RuntimeError("Unexpected fixture request")
        return {"fixture": True, "personal_books": 0}

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    proxy = TailscaleAccess()
    before = json.loads(proxy._run("serve", "status", "--json"))
    report = {"fixture_only": True, "personal_books": 0, "physical_phone": "not_tested"}
    with tempfile.TemporaryDirectory(prefix="myl_tailnet_qa_") as temp:
        access = DeviceAccess(Path(temp) / "devices.json")
        service = MobileService(access, FixtureAdapter())
        try:
            port = service.start()
            url = proxy.start(port)
            def request(path, data=None, token=None):
                headers = {"Content-Type": "application/json"} if data is not None else {}
                if token:
                    headers["Authorization"] = "Bearer " + token
                raw = json.dumps(data).encode() if data is not None else None
                with urllib.request.urlopen(urllib.request.Request(url + path, raw, headers), timeout=15) as response:
                    return json.load(response)
            assert request("/api/v1/health")["protocol"] == 1
            paired = request("/api/v1/pair", {"code": access.new_code(), "device": "Disposable Tailscale check"})
            assert request("/api/v1/status", token=paired["token"])["fixture"] is True
            report["https_health_pairing_authenticated_request"] = "passed"
        except Exception as exc:
            report["failure"] = str(exc)
        finally:
            proxy.stop()
            service.stop()
    after = json.loads(proxy._run("serve", "status", "--json"))
    report["existing_routes_preserved"] = before == after
    report["passed"] = "failure" not in report and before == after
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
