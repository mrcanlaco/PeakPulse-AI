"""Interactive, server-local credential entry. Nothing passes through the web UI."""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import tempfile
from pathlib import Path


def save_credentials(path: Path, key: str, secret: str, *, replace=False):
    if not all(re.fullmatch(r"[A-Za-z0-9]{16,256}", value) for value in (key, secret)):
        raise ValueError("requires_binance_hmac_credentials")
    path = path.resolve()
    if path.exists() and not replace:
        raise ValueError("credentials_file_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".binance-private-", dir=path.parent)
    temp = Path(filename)
    try:
        os.close(fd)
        if os.name == "nt":
            # Apply the DACL before writing any secret bytes.
            subprocess.run(
                [
                    "icacls",
                    str(temp),
                    "/inheritance:r",
                    "/grant:r",
                    f"{getpass.getuser()}:(F)",
                ],
                check=True,
                capture_output=True,
            )
        else:
            temp.chmod(0o600)
        temp.write_text(
            f"DAO_VANG_ACCOUNT_MONITOR__API_KEY={key}\nDAO_VANG_ACCOUNT_MONITOR__API_SECRET={secret}\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
