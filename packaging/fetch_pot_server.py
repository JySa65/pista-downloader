"""Fetch bgutil's PO Token generator (the "server" folder, run by deno in script mode) into vendor/.

    uv run python packaging/fetch_pot_server.py

The version is the installed bgutil-ytdlp-pot-provider plugin's (pinned in uv.lock), so plugin and
generator always match. Skips the work when vendor/bgutil-server/VERSION already says that version.
VERSION is written last: Pista ignores a folder without it (a fetch that stopped halfway).
"""
import importlib.metadata
import io
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pista.core.system import find_deno  # noqa: E402

DEST = ROOT / "vendor" / "bgutil-server"
REPO = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider"


def _only_server(member: tarfile.TarInfo, dest: str) -> tarfile.TarInfo | None:
    """Keep `<repo>-<ver>/server/...` as `...`; the 'data' filter rejects anything unsafe."""
    parts = member.name.split("/", 2)
    if len(parts) < 3 or parts[1] != "server":
        return None
    return tarfile.data_filter(member.replace(name=parts[2], deep=False), dest)


def _is_link(p: Path) -> bool:
    return p.is_symlink() or p.is_junction()  # deno may link packages with junctions on Windows


def _remove(p: Path) -> None:
    if _is_link(p) or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


def _links(modules: Path) -> list[Path]:
    """Package links in a node_modules dir (`name` and `@scope/name`)."""
    if not modules.is_dir():
        return []
    found = []
    for p in modules.iterdir():
        if p.name.startswith("@") and p.is_dir() and not p.is_symlink():
            found += [q for q in p.iterdir() if _is_link(q)]
        elif _is_link(p):
            found.append(p)
    return found


def prune_dev_packages(server: Path) -> None:
    """Delete deno store packages that no runtime dependency reaches: devDependencies (typescript,
    eslint, swc, …) and their trees. deno runs src/*.ts directly, so none of them is needed."""
    nm = server / "node_modules"
    store = nm / ".deno"  # deno's layout: .deno/<name>@<version>/node_modules/<name> + links to its deps
    runtime = json.loads((server / "package.json").read_text()).get("dependencies", {})
    todo = [nm / name for name in runtime]
    keep: set[str] = set()
    while todo:
        target = todo.pop().resolve()
        if not target.is_relative_to(store):
            continue
        entry = target.relative_to(store).parts[0]
        if entry not in keep:
            keep.add(entry)
            todo += _links(store / entry / "node_modules")
    for d in store.iterdir():
        if d.is_dir() and "@" in d.name.lstrip("@") and d.name not in keep:
            shutil.rmtree(d)
    for link in [p for p in nm.rglob("*") if _is_link(p) and not p.exists()]:
        link.unlink()  # dangling: pointed into a pruned package (top-level devDependencies, .bin/tsc, …)
    for scope in nm.glob("@*"):
        if scope.is_dir() and not any(scope.iterdir()):
            scope.rmdir()


def main() -> Path:
    ver = importlib.metadata.version("bgutil-ytdlp-pot-provider")
    stamp = DEST / "VERSION"
    if stamp.is_file() and stamp.read_text().strip() == ver:
        print(f"bgutil server {ver} already in {DEST.relative_to(ROOT)}")
        return DEST
    deno = find_deno()
    if not deno:
        sys.exit("deno not found: run `uv sync` first (the yt-dlp[deno] extra installs it)")
    stamp.unlink(missing_ok=True)  # first: if anything below fails, the old/partial folder stays inactive
    _remove(DEST)
    DEST.mkdir(parents=True)
    print(f"downloading bgutil server {ver}…")
    with urllib.request.urlopen(f"{REPO}/archive/refs/tags/{ver}.tar.gz", timeout=60) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(DEST, filter=_only_server)
    print("installing npm dependencies with deno…")
    subprocess.run([deno, "install", "--allow-scripts=npm:canvas", "--frozen"], cwd=DEST, check=True)
    prune_dev_packages(DEST)
    stamp.write_text(ver + "\n")
    print(f"bgutil server {ver} ready in {DEST.relative_to(ROOT)}")
    return DEST


if __name__ == "__main__":
    main()
