"""Hardened subprocess execution — allowlisted binaries, no shell, timeouts."""

import logging
import shutil
import subprocess
import time

_log = logging.getLogger("LimeWire.security")

# Only these executables may be invoked
_ALLOWED_BINARIES = frozenset({
    "ffmpeg",
    "ffprobe",
    "yt-dlp",
})


class SubprocessPolicyError(ValueError):
    """Raised when a subprocess call violates policy."""


class CommandResult:
    """Structured result from a subprocess invocation."""
    __slots__ = ("family", "argv", "returncode", "duration", "stdout", "stderr")

    def __init__(self, family, argv, returncode, duration, stdout, stderr):
        self.family = family
        self.argv = argv
        self.returncode = returncode
        self.duration = duration
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self):
        return self.returncode == 0


def run_safe(
    executable: str,
    args: list[str],
    *,
    family: str = "",
    cwd: str | None = None,
    timeout: int = 300,
    max_output: int = 100_000,
) -> CommandResult:
    """Run a subprocess with security constraints.

    Args:
        executable: Binary name (must be in allowlist).
        args: Command arguments (list form only, no shell expansion).
        family: Label for audit logging (e.g. "transcode", "download").
        cwd: Working directory (optional).
        timeout: Max seconds before kill.
        max_output: Truncate stdout/stderr to this many chars.

    Returns:
        CommandResult with exit code, stdout, stderr, duration.

    Raises:
        SubprocessPolicyError: If executable not allowed or not found.
        subprocess.TimeoutExpired: If process exceeds timeout.
    """
    if executable not in _ALLOWED_BINARIES:
        raise SubprocessPolicyError(f"Executable not in allowlist: {executable}")

    resolved = shutil.which(executable)
    if not resolved:
        raise SubprocessPolicyError(f"Executable not found on PATH: {executable}")

    argv = [resolved, *args]
    label = family or executable

    _log.info("[subprocess] %s: %s (timeout=%ds)", label, executable, timeout)

    start = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )
    duration = time.perf_counter() - start

    result = CommandResult(
        family=label,
        argv=argv,
        returncode=proc.returncode,
        duration=round(duration, 2),
        stdout=proc.stdout[-max_output:] if proc.stdout else "",
        stderr=proc.stderr[-max_output:] if proc.stderr else "",
    )

    level = logging.INFO if result.ok else logging.WARNING
    _log.log(level, "[subprocess] %s: exit=%d duration=%.1fs", label, result.returncode, duration)

    return result


def ffmpeg(args: list[str], *, timeout: int = 600, cwd: str | None = None) -> CommandResult:
    """Convenience wrapper for ffmpeg calls."""
    return run_safe("ffmpeg", args, family="ffmpeg", timeout=timeout, cwd=cwd)


def ffprobe(args: list[str], *, timeout: int = 30, cwd: str | None = None) -> CommandResult:
    """Convenience wrapper for ffprobe calls."""
    return run_safe("ffprobe", args, family="ffprobe", timeout=timeout, cwd=cwd)
