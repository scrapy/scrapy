from difflib import unified_diff


def report_collection_diff(from_collection, to_collection, from_id, to_id):
    """Report the collected test difference between two nodes.

    :returns: detailed message describing the difference between the given
    collections, or None if they are equal.
    """
    if from_collection == to_collection:
        return None

    diff = unified_diff(from_collection, to_collection, fromfile=from_id, tofile=to_id)
    error_message = (
        "Different tests were collected between {from_id} and {to_id}. "
        "The difference is:\n"
        "{diff}\n"
        "To see why this happens see Known limitations in documentation"
    ).format(from_id=from_id, to_id=to_id, diff="\n".join(diff))
    msg = "\n".join(x.rstrip() for x in error_message.split("\n"))
    return msg
