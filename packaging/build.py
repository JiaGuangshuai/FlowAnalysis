"""Build on the target operating system: python packaging/build.py."""
from importlib import metadata
from pathlib import Path
import json
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    licenses = ROOT / "build/licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    inventory = []
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        inventory.append({"name": name, "version": dist.version,
                          "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                          "urls": dist.metadata.get_all("Project-URL", [])})
        for file in dist.files or []:
            if any(s in str(file).lower() for s in ["license", "copying", "copyright", "notice"]):
                source = Path(dist.locate_file(file))
                if source.is_file() and source.suffix not in {".py", ".pyc", ".so", ".dylib", ".dll"}:
                    target = licenses / name / str(file).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (licenses / "DEPENDENCIES.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "packaging/FlowAnalysis.spec")],
                   cwd=ROOT, check=True)
    if sys.platform == "darwin":
        # Some distribution/cache systems retain UF_HIDDEN on wheel files.
        # Qt intentionally ignores hidden plugin files when enumerating plugins.
        subprocess.run(["chflags", "-R", "nohidden", str(ROOT / "dist/FlowAnalysis.app")], check=True)
        bundle = ROOT / "dist/FlowAnalysis.app"
        for attribute in ["com.apple.FinderInfo", "com.apple.ResourceFork"]:
            subprocess.run(["xattr", "-dr", attribute, str(bundle)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        output = ROOT / f"dist/FlowAnalysis-0.1.0-macOS-{platform.machine()}.zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(ROOT / "dist/FlowAnalysis.app"), str(output)], check=True)
    elif sys.platform == "win32":
        output = shutil.make_archive(str(ROOT / "dist/FlowAnalysis-0.1.0-Windows-x64"), "zip",
                                     ROOT / "dist", "FlowAnalysis")
        iscc = shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if Path(iscc).is_file():
            subprocess.run([iscc, str(ROOT / "packaging/FlowAnalysis.iss")], check=True)
    else:
        output = shutil.make_archive(str(ROOT / "dist/FlowAnalysis-0.1.0-Linux"), "gztar",
                                     ROOT / "dist", "FlowAnalysis")
    print(f"Built: {output}")


if __name__ == "__main__":
    main()
