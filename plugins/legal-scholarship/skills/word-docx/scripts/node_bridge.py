"""Locator + invocation helper for Node.js + the `docx` npm package.

Used only by the JS-routed `build` path. Python-native commands and
Anthropic-subprocess commands do not depend on this module.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_NODE_INSTALL_MSG = (
    "Node.js is not installed or not on PATH. "
    "Install Node from https://nodejs.org/ to enable the JS-routed build path."
)

_DOCX_PACKAGE_MSG = (
    "The `docx` npm package is not reachable from Node. Install it with:\n"
    "  npm install -g docx"
)


class NodeNotInstalledError(RuntimeError):
    """Raised when `node` is not on PATH."""

    def __init__(self) -> None:
        super().__init__(_NODE_INSTALL_MSG)


class DocxPackageMissingError(RuntimeError):
    """Raised when Node is present but `require('docx')` fails."""

    def __init__(self) -> None:
        super().__init__(_DOCX_PACKAGE_MSG)


def ensure_node() -> str:
    """Return the path to the `node` executable, or raise NodeNotInstalledError."""
    found = shutil.which("node")
    if not found:
        raise NodeNotInstalledError()
    return found


def ensure_docx_package() -> None:
    """Verify the `docx` npm package can be resolved by Node.

    Checks (a) project-local ``node_modules`` (looking up from CWD) and (b) the
    global npm root. Either is sufficient.
    """
    node = ensure_node()
    candidate_cwds: list[Path | None] = []
    # Current CWD (picks up local node_modules in the caller's directory)
    candidate_cwds.append(None)
    # Skill root (where the skill's own node_modules would live)
    skill_root = Path(__file__).resolve().parent.parent
    candidate_cwds.append(skill_root)
    # Global npm root: run `npm root -g` and use its parent as the CWD
    try:
        npm = shutil.which("npm")
        if npm:
            r = subprocess.run([npm, "root", "-g"], capture_output=True, text=True)
            if r.returncode == 0:
                global_root = r.stdout.strip()
                if global_root:
                    candidate_cwds.append(Path(global_root).parent)
    except Exception:
        pass

    for cwd in candidate_cwds:
        kwargs: dict = {"capture_output": True, "text": True}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        r = subprocess.run([node, "-e", "require.resolve('docx');"], **kwargs)
        if r.returncode == 0:
            return
    raise DocxPackageMissingError()


def run_node_script(script_path: Path) -> subprocess.CompletedProcess:
    """Execute a .mjs / .js file with the resolved node executable."""
    node = ensure_node()
    return subprocess.run(
        [node, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
