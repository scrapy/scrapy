def get_callback_name(request):
    """Extract the name of the callback function from a request."""
    callback = request.callback
    if callback is None:
        return "None"
    return f"{callback.__module__}.{callback.__name__}"
