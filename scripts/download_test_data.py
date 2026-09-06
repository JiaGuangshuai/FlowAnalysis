"""Download public FlowKit fixtures, checking the recorded SHA-256 for every file."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "local-data/public-flowkit")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("test-data-manifest.json").read_text())
    for item in manifest:
        target = args.output / item["file"]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]:
            print(f"Verified {target.name}")
            continue
        request = urllib.request.Request(item["source"], headers={"User-Agent": "FlowAnalysis-test-data"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Upstream content changed: {item['file']}; inspect before updating manifest")
        target.write_bytes(data)
        print(f"Downloaded {target.name}")
    (args.output / "SOURCES.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
