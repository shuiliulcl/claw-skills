"""Auto-detect or download deno binary for yt-dlp dash format support.

deno is yt-dlp's default JS runtime for solving EJS challenges. Without it,
720p (and any dash format) downloads will hang silently after printing
"[download] Destination: ...".

Usage:
    python ensure_deno.py [<install_dir>]
        # default install_dir = ./bin

Returns the deno executable path on stdout (so callers can capture it).
"""
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


def find_deno(install_dir: Path) -> Path | None:
    # 1. PATH
    p = shutil.which("deno")
    if p:
        return Path(p)
    # 2. install_dir
    candidate = install_dir / ("deno.exe" if os.name == "nt" else "deno")
    if candidate.exists():
        return candidate
    return None


def download(install_dir: Path) -> Path:
    install_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
    elif sys.platform == "darwin":
        url = "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip"
    else:
        url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"

    zip_path = install_dir / "deno.zip"
    print(f"Downloading deno from {url} ...", file=sys.stderr)
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(install_dir)
    zip_path.unlink()
    deno_path = install_dir / ("deno.exe" if os.name == "nt" else "deno")
    if not (os.name == "nt"):
        deno_path.chmod(0o755)
    return deno_path


def main() -> None:
    install_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./bin")
    install_dir = install_dir.resolve()

    found = find_deno(install_dir)
    if found:
        ver = subprocess.run([str(found), "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        print(f"deno found: {found}", file=sys.stderr)
        print(f"  {ver}", file=sys.stderr)
        print(found)
        return

    print(f"deno not found, downloading to {install_dir}", file=sys.stderr)
    deno_path = download(install_dir)
    ver = subprocess.run([str(deno_path), "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"  Installed: {ver}", file=sys.stderr)
    print(deno_path)


if __name__ == "__main__":
    main()
