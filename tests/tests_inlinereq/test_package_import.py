import inline_requests


def test_package_metadata():
    assert inline_requests.__author__
    assert inline_requests.__email__
    assert inline_requests.__version__
