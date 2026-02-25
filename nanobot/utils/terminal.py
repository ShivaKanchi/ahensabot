"""Utility functions for terminal interaction."""

try:
    import termios
except ImportError:
    termios = None


def flush_input(fd: int) -> bool:
    """
    Flush pending input from the terminal.

    Returns:
        True if flush was successful using termios, False otherwise.
    """
    if termios is None:
        return False
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
        return True
    except Exception:
        return False


def get_terminal_settings(fd: int):
    """Get current terminal settings (termios attributes)."""
    if termios is None:
        return None
    try:
        return termios.tcgetattr(fd)
    except Exception:
        return None


def restore_terminal_settings(fd: int, settings) -> None:
    """Restore terminal settings."""
    if termios is None or settings is None:
        return
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, settings)
    except Exception:
        pass
