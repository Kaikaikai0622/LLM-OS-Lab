"""Local Python execution backend for workspace-aware code runs."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional


class LocalPythonSandbox:
    """
    Execute Python code with local interpreter in workspace context.

    Compatible with SandboxProtocol.execute signature used by agent.tools.execute_python.
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = str(Path(workspace_root).resolve())

    async def execute(
        self,
        code: str,
        timeout_seconds: Optional[float] = None,
        memory_limit_mb: Optional[int] = None,
    ) -> dict:
        start = time.monotonic()
        timeout = timeout_seconds or 15.0

        with NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            self.workspace_root if not existing_pythonpath else f"{self.workspace_root}{os.pathsep}{existing_pythonpath}"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                tmp_path,
                cwd=self.workspace_root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                status = "success" if proc.returncode == 0 else "error"
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_b, stderr_b = b"", f"Execution timed out after {timeout} seconds".encode("utf-8")
                status = "timeout"

            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            elapsed = time.monotonic() - start

            return {
                "status": status,
                "stdout": stdout,
                "stderr": stderr,
                "result": None,
                "execution_time": elapsed,
            }
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                # Keep cleanup best-effort to avoid masking execution outcome.
                pass
