def format_size(bytes_size) -> str:
    """Formats a size in bytes to a human-readable string (e.g., 12.34 GB)."""
    try:
        bytes_size = float(bytes_size)
    except (ValueError, TypeError):
        return "Unknown Size"
    
    if bytes_size < 0:
        return "0 B"
        
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"

def format_speed(bytes_per_sec) -> str:
    """Formats speed in bytes/s to human-readable speed (e.g., 2.50 MB/s)."""
    try:
        speed = float(bytes_per_sec)
    except (ValueError, TypeError):
        return "0 B/s"
        
    return f"{format_size(speed)}/s"

def format_eta(seconds) -> str:
    """Formats ETA in seconds to human-readable format (e.g., 1h 45m 12s)."""
    try:
        secs = int(seconds)
    except (ValueError, TypeError):
        return "Unknown"
        
    # qBittorrent returns 8640000 or other massive numbers for stalled/infinite ETA
    if secs >= 8640000 or secs < 0:
        return "∞"
        
    if secs < 60:
        return f"{secs}s"
        
    mins = secs // 60
    secs = secs % 60
    if mins < 60:
        return f"{mins}m {secs}s"
        
    hours = mins // 60
    mins = mins % 60
    if hours < 24:
        return f"{hours}h {mins}m"
        
    days = hours // 24
    hours = hours % 24
    return f"{days}d {hours}h"

def get_progress_bar(progress: float, length: int = 10) -> str:
    """Generates a text progress bar for a progress float (0.0 to 1.0)."""
    try:
        progress = max(0.0, min(1.0, float(progress)))
    except (ValueError, TypeError):
        progress = 0.0
        
    filled_len = int(round(length * progress))
    bar = "█" * filled_len + "░" * (length - filled_len)
    percent = progress * 100
    return f"`{bar}` {percent:.1f}%"
