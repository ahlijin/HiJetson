"""
Common utilities — minimal set ported from the original HiWonder SDK.
"""

def set_range(x, x_min, x_max):
    """Clamp x to [x_min, x_max]."""
    tmp = x if x > x_min else x_min
    tmp = tmp if tmp < x_max else x_max
    return tmp
