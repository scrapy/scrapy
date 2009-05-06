import time

def to_date(format):
    """
    Converts a date string to a YYYY-MM-DD one suitable for DateField

    format is the format string passed to time.strptime
    
    Input: string/unicode
    Output: string
    """
    def _to_date(value):
        return time.strftime('%Y-%m-%d', time.strptime(value, format))
    return _to_date
