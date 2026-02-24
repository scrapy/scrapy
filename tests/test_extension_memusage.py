import sys
from unittest.mock import MagicMock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions import memusage


@pytest.fixture
def dummy_crawler():
    crawler = MagicMock()
    crawler.settings.getbool.return_value = True
    crawler.settings.getlist.return_value = ["test@email.com"]
    crawler.settings.getint.side_effect = lambda key: {
        "MEMUSAGE_LIMIT_MB": 50,
        "MEMUSAGE_WARNING_MB": 30,
    }[key]
    crawler.settings.getfloat.return_value = 0.1
    crawler.stats.get_value.return_value = 0
    crawler.stats.set_value = MagicMock()
    crawler.stats.max_value = MagicMock()
    crawler.signals.connect = MagicMock()
    crawler.engine = MagicMock()
    crawler.engine.spider = None
    crawler.stop_async = MagicMock()
    return crawler


def test_1_init_disabled(dummy_crawler):
    """
    Test that MemoryUsage raises NotConfigured if MEMUSAGE_ENABLED is False.
    """
    dummy_crawler.settings.getbool.return_value = False
    with pytest.raises(NotConfigured):
        memusage.MemoryUsage(dummy_crawler)


def test_2_init_resource_missing(dummy_crawler, monkeypatch):
    """
    Test that MemoryUsage raises NotConfigured if the resource
    module cannot be imported.
    """
    dummy_crawler.settings.getbool.return_value = True

    def raise_import_error(name):
        raise ImportError

    monkeypatch.setattr(memusage, "import_module", raise_import_error)
    with pytest.raises(NotConfigured):
        memusage.MemoryUsage(dummy_crawler)


@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_3_memoryusage_initialization(mock_mail, dummy_crawler):
    """
    Test that MemoryUsage initializes correctly with the
    expected settings and connects signals.
    """
    # mock MailSender to return a dummy object
    mock_mail.return_value = MagicMock()

    crawler = memusage.MemoryUsage(dummy_crawler)

    # check that the object is created
    assert isinstance(crawler, memusage.MemoryUsage)

    # check key attributes
    assert crawler.crawler == dummy_crawler
    assert crawler.mail == mock_mail.return_value
    assert crawler.limit == 50 * 1024 * 1024
    assert crawler.warning == 30 * 1024 * 1024
    assert crawler.notify_mails == ["test@email.com"]
    assert crawler.warned is False

    # check that signals were connected
    dummy_crawler.signals.connect.assert_any_call(
        crawler.engine_started, signal=memusage.signals.engine_started
    )
    dummy_crawler.signals.connect.assert_any_call(
        crawler.engine_stopped, signal=memusage.signals.engine_stopped
    )


@patch("scrapy.extensions.memusage.MailSender")
def test_4_from_crawler_initializes_fields(mock_mail):
    """
    Test that from_crawler initializes the MemoryUsage
    object with the correct fields.
    """
    crawler = MagicMock()
    crawler.settings.getbool.return_value = True
    crawler.settings.getlist.return_value = ["test@email.com"]
    crawler.settings.getint.side_effect = lambda k: {
        "MEMUSAGE_LIMIT_MB": 50,
        "MEMUSAGE_WARNING_MB": 30,
    }[k]
    crawler.settings.getfloat.return_value = 1.0
    crawler.signals.connect = MagicMock()

    mu = memusage.MemoryUsage.from_crawler(crawler)

    assert isinstance(mu, memusage.MemoryUsage)
    assert mu.crawler is crawler
    assert mu.warned is False
    assert mu.limit == 50 * 1024 * 1024
    assert mu.warning == 30 * 1024 * 1024


@patch("scrapy.extensions.memusage.MailSender")
def test_get_virtual_size(mock_mail, dummy_crawler, monkeypatch):
    """
    Test that get_virtual_size returns the correct value based
    on the platform and ru_maxrss.
    """
    mu = memusage.MemoryUsage(dummy_crawler)
    dummy_crawler.settings.getbool.return_value = True

    # simulate ru_maxrss
    mu.resource.getrusage = MagicMock(
        return_value=type("RU", (), {"ru_maxrss": 1024})()
    )

    if sys.platform == "darwin":
        assert mu.get_virtual_size() == 1024

        # spoof OS
        monkeypatch.setattr(sys, "platform", "linux")
        mu = memusage.MemoryUsage(dummy_crawler)
        # simulate ru_maxrss
        mu.resource.getrusage = MagicMock(
            return_value=type("RU", (), {"ru_maxrss": 1024})()
        )
        assert mu.get_virtual_size() == 1024 * 1024
    else:
        assert mu.get_virtual_size() == 1024 * 1024  # Linux scales by 1024

        # spoof OS
        monkeypatch.setattr(sys, "platform", "darwin")
        mu = memusage.MemoryUsage(dummy_crawler)
        # simulate ru_maxrss
        mu.resource.getrusage = MagicMock(
            return_value=type("RU", (), {"ru_maxrss": 1024})()
        )
        assert mu.get_virtual_size() == 1024


@patch("scrapy.extensions.memusage.create_looping_call")
@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_6_engine_started_creates_tasks(mock_mail, mock_loop, dummy_crawler):
    """
    Test that engine_started creates looping call tasks for update,
    limit check, and warning check.
    """
    # mock MailSender
    mock_mail.return_value = MagicMock()

    # mock looping call object
    fake_task = MagicMock()
    mock_loop.return_value = fake_task

    mu = memusage.MemoryUsage(dummy_crawler)

    # patch get_virtual_size to a fixed number so we can check stats
    mu.get_virtual_size = MagicMock(return_value=1024)

    # call engine_started
    mu.engine_started()

    # check that the startup memory was recorded
    dummy_crawler.stats.set_value.assert_any_call("memusage/startup", 1024)

    # check that tasks were created and called
    assert len(mu.tasks) == 3
    for task in mu.tasks:
        assert task.start.called


@patch("scrapy.extensions.memusage.create_looping_call")
@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_7_engine_started_creates_tasks_no_limit(mock_mail, mock_loop, dummy_crawler):
    """
    Test that engine_started creates looping call tasks
    for update and warning check when limit is 0 (disabled).
    """
    # mock MailSender
    mock_mail.return_value = MagicMock()

    # mock looping call object
    fake_task = MagicMock()
    mock_loop.return_value = fake_task

    mu = memusage.MemoryUsage(dummy_crawler)

    # patch get_virtual_size to a fixed number so we can check stats
    mu.get_virtual_size = MagicMock(return_value=1024)

    # set the limit to 0
    mu.limit = 0

    # call engine_started
    mu.engine_started()

    # check that the startup memory was recorded
    dummy_crawler.stats.set_value.assert_any_call("memusage/startup", 1024)

    # check that tasks were created and called
    assert len(mu.tasks) == 2
    for task in mu.tasks:
        assert task.start.called


@patch("scrapy.extensions.memusage.create_looping_call")
@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_8_engine_started_creates_tasks_no_warning(mock_mail, mock_loop, dummy_crawler):
    """
    Test that engine_started creates looping call tasks for
    update and limit check when warning is 0 (disabled).
    """
    # mock MailSender
    mock_mail.return_value = MagicMock()

    # mock looping call object
    fake_task = MagicMock()
    mock_loop.return_value = fake_task

    mu = memusage.MemoryUsage(dummy_crawler)

    # patch get_virtual_size to a fixed number so we can check stats
    mu.get_virtual_size = MagicMock(return_value=1024)

    # set the warning to 0
    mu.warning = 0

    # call engine_started
    mu.engine_started()

    # check that the startup memory was recorded
    dummy_crawler.stats.set_value.assert_any_call("memusage/startup", 1024)

    # check that tasks were created and called
    assert len(mu.tasks) == 2
    for task in mu.tasks:
        assert task.start.called


@patch("scrapy.extensions.memusage.create_looping_call")
@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_9_engine_started_creates_tasks_no_limit_no_warning(
    mock_mail, mock_loop, dummy_crawler
):
    """
    Test that engine_started creates looping call task only
    for update when both limit and warning are 0 (disabled).
    """
    # mock MailSender
    mock_mail.return_value = MagicMock()

    # mock looping call object
    fake_task = MagicMock()
    mock_loop.return_value = fake_task

    mu = memusage.MemoryUsage(dummy_crawler)

    # patch get_virtual_size to a fixed number so we can check stats
    mu.get_virtual_size = MagicMock(return_value=1024)

    # set both limit and warning to 0
    mu.warning = 0
    mu.limit = 0

    # call engine_started
    mu.engine_started()

    # check that the startup memory was recorded
    dummy_crawler.stats.set_value.assert_any_call("memusage/startup", 1024)

    # check that tasks were created and called
    assert len(mu.tasks) == 1
    for task in mu.tasks:
        assert task.start.called


@patch("scrapy.extensions.memusage.create_looping_call")
@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_10_engine_stopped_stops_tasks(mock_mail, mock_loop, dummy_crawler):
    """
    Test that engine_stopped stops all looping call
    tasks created by engine_started.
    """
    # mock MailSender
    mock_mail.return_value = MagicMock()

    # mock looping call object
    fake_task = MagicMock()
    mock_loop.return_value = fake_task

    mu = memusage.MemoryUsage(dummy_crawler)

    # patch get_virtual_size to a fixed number so we can check stats
    mu.get_virtual_size = MagicMock(return_value=1024)

    # call engine_started
    mu.engine_started()

    # check that the startup memory was recorded
    dummy_crawler.stats.set_value.assert_any_call("memusage/startup", 1024)

    # check that tasks were stopped
    mu.engine_stopped()
    for task in mu.tasks:
        assert task.stop.called


@patch("scrapy.extensions.memusage.MailSender.from_crawler")
def test_11_update_sets_max_memory(mock_mail, dummy_crawler):
    """
    Test that update calls stats.max_value with the current virtual size."""
    # Arrange: fake crawler
    mu = memusage.MemoryUsage(dummy_crawler)

    # Force a predictable memory value
    mu.get_virtual_size = MagicMock(return_value=1234)

    # Act
    mu.update()

    # Assert
    dummy_crawler.stats.max_value.assert_called_once_with("memusage/max", 1234)


@patch("scrapy.extensions.memusage._schedule_coro")
@patch("scrapy.extensions.memusage.MailSender")
def test_12_check_limit_exceeds_calls_stop(mock_mail, mock_schedule, dummy_crawler):
    """
    Test that _check_limit sets stats and calls stop
    when memory usage exceeds the limit.
    """
    mu = memusage.MemoryUsage(dummy_crawler)
    mu.get_virtual_size = MagicMock(
        return_value=dummy_crawler.settings.getint("MEMUSAGE_LIMIT_MB") * 1024 * 1024
        + 1
    )
    mu._send_report = MagicMock()
    mu._check_limit()
    assert dummy_crawler.stats.set_value.called
    assert mu._send_report.called
    assert mock_schedule.called


@patch("scrapy.extensions.memusage.MailSender")
def test_13_check_warning_sends_email_once(mock_mail, dummy_crawler):
    """
    Test that _check_warning sends an email and sets warned to True
    when memory usage exceeds the warning threshold, and does not
    send again on subsequent calls.
    """
    mu = memusage.MemoryUsage(dummy_crawler)
    mu.get_virtual_size = MagicMock(
        return_value=dummy_crawler.settings.getint("MEMUSAGE_WARNING_MB") * 1024 * 1024
        + 1
    )
    mu._send_report = MagicMock()
    mu._check_warning()

    assert dummy_crawler.stats.set_value.called
    assert mu._send_report.called
    assert mu.warned is True

    # calling again should do nothing
    mu._check_warning()
    assert mu._send_report.call_count == 1
