"""Platform detection constants."""
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
PLATFORM = "windows" if IS_WINDOWS else ("macos" if IS_MACOS else "linux")
