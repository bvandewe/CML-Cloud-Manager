import datetime


def relative_time(past_datetime: datetime.datetime) -> str:
    """Calculates the relative time from a past datetime to now.

    Args:
      past_datetime: A datetime object representing the past time.

    Returns:
      A string representing the relative time.
    """
    now = datetime.datetime.now(datetime.timezone.utc).astimezone()
    delta = now - past_datetime

    if delta.days > 365:
        years = delta.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    elif delta.days > 30:
        months = delta.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    elif delta.days > 0:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "just now"
