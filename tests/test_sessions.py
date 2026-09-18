import pytest

from scrapy.sessions import Session
from scrapy.utils.test import get_crawler


def test_get() -> None:
    sessions = get_crawler().sessions
    session = sessions["foo"]
    assert isinstance(session, Session)
    assert session.id == "foo"
    assert sessions["foo"] is session
    assert "foo" in sessions
    assert "bar" not in sessions


def test_non_string_id() -> None:
    sessions = get_crawler().sessions
    assert sessions[1].id == "1"
    assert sessions[1] is sessions["1"]
    assert 1 in sessions
    sessions.retire(1)
    assert "1" not in sessions


def test_create() -> None:
    sessions = get_crawler().sessions
    session = sessions.create()
    assert sessions[session.id] is session
    assert sessions.create().id != session.id


def test_retire() -> None:
    crawler = get_crawler()
    sessions = crawler.sessions
    sessions["foo"].meta["a"] = 1
    sessions.retire("foo")
    assert "foo" not in sessions
    assert sessions["foo"].meta == {}
    sessions.retire("bar")  # unknown IDs are ignored
    assert crawler.stats.get_value("sessions/retired") == 1


def test_max(caplog: pytest.LogCaptureFixture) -> None:
    crawler = get_crawler(settings_dict={"SESSIONS_MAX": 2})
    sessions = crawler.sessions
    a = sessions["a"]
    sessions["b"]
    assert sessions["a"] is a
    caplog.clear()
    sessions["c"]
    assert "b" not in sessions
    assert "a" in sessions
    assert crawler.stats.get_value("sessions/created") == 3
    assert crawler.stats.get_value("sessions/dropped") == 1
    assert "Dropped session 'b'" in caplog.text
    caplog.clear()
    sessions["d"]
    assert crawler.stats.get_value("sessions/dropped") == 2
    assert not caplog.text
