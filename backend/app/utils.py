"""Utility functions."""
from datetime import datetime


def format_ymd(ymd: int) -> str:
    """Format YYYYMMDD integer to date string."""
    date_str = str(ymd)
    if len(date_str) == 8:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    return ""


def parse_ymd(date_str: str) -> int:
    """Parse date string (YYYY-MM-DD) to YYYYMMDD integer."""
    try:
        dt = datetime.fromisoformat(date_str)
        return int(dt.strftime("%Y%m%d"))
    except:
        return 0

