from datetime import date, datetime
from datetime import datetime as d
from datetime import timedelta
from datetime import tzinfo
from typing import cast, Type

from testfixtures import mock_datetime, mock_date
from testfixtures import replace, Replacer, compare, ShouldRaise
from testfixtures.datetime import MockDateTime
from testfixtures.tests import sample1
from unittest import TestCase


class SampleTZInfo(tzinfo):

    __test__ = False

    def utcoffset(self, dt):
        return timedelta(minutes=3) + self.dst(dt)

    def dst(self, dt):
        return timedelta(minutes=1)


class SampleTZInfo2(tzinfo):

    __test__ = False

    def utcoffset(self, dt):
        return timedelta(minutes=5)

    def dst(self, dt):
        return timedelta(minutes=0)


class TestDateTime(TestCase):

    @replace('datetime.datetime', mock_datetime())
    def test_now(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 0))
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 10))
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 30))

    @replace('datetime.datetime', mock_datetime())
    def test_now_with_tz_supplied(self):
        from datetime import datetime
        info = SampleTZInfo()
        compare(datetime.now(info), d(2001, 1, 1, 0, 4, tzinfo=SampleTZInfo()))

    @replace('datetime.datetime', mock_datetime(tzinfo=SampleTZInfo()))
    def test_now_with_tz_setup(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 1))

    @replace('datetime.datetime', mock_datetime(tzinfo=SampleTZInfo()))
    def test_now_with_tz_setup_and_supplied(self):
        from datetime import datetime
        info = SampleTZInfo2()
        compare(datetime.now(info), d(2001, 1, 1, 0, 1, tzinfo=info))

    @replace('datetime.datetime', mock_datetime(tzinfo=SampleTZInfo()))
    def test_now_with_tz_setup_and_same_supplied(self):
        from datetime import datetime
        info = SampleTZInfo()
        compare(datetime.now(info), d(2001, 1, 1, tzinfo=info))

    def test_now_with_tz_instance(self):
        dt = mock_datetime(d(2001, 1, 1, tzinfo=SampleTZInfo()))
        compare(dt.now(), d(2001, 1, 1))

    def test_now_with_tz_instance_and_supplied(self):
        dt = mock_datetime(d(2001, 1, 1, tzinfo=SampleTZInfo()))
        info = SampleTZInfo2()
        compare(dt.now(info), d(2001, 1, 1, 0, 1, tzinfo=info))

    def test_now_with_tz_instance_and_same_supplied(self):
        dt = mock_datetime(d(2001, 1, 1, tzinfo=SampleTZInfo()))
        info = SampleTZInfo()
        compare(dt.now(info), d(2001, 1, 1, tzinfo=info))

    @replace('datetime.datetime', mock_datetime(2002, 1, 1, 1, 2, 3))
    def test_now_supplied(self):
        from datetime import datetime
        compare(datetime.now(), d(2002, 1, 1, 1, 2, 3))

    @replace('datetime.datetime', mock_datetime(None))
    def test_now_sequence(self, t):
        t.add(2002, 1, 1, 1, 0, 0)
        t.add(2002, 1, 1, 2, 0, 0)
        t.add(2002, 1, 1, 3, 0, 0)
        from datetime import datetime
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 3, 0, 0))

    @replace('datetime.datetime', mock_datetime())
    def test_add_and_set(self, t):
        t.add(2002, 1, 1, 1, 0, 0)
        t.add(2002, 1, 1, 2, 0, 0)
        t.set(2002, 1, 1, 3, 0, 0)
        from datetime import datetime
        compare(datetime.now(), d(2002, 1, 1, 3, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 3, 0, 10))
        compare(datetime.now(), d(2002, 1, 1, 3, 0, 30))

    @replace('datetime.datetime', mock_datetime(None))
    def test_add_datetime_supplied(self, t: Type[MockDateTime]):
        from datetime import datetime
        t.add(d(2002, 1, 1, 1))
        t.add(datetime(2002, 1, 1, 2))
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 0))
        tzinfo = SampleTZInfo()
        tzrepr = repr(tzinfo)
        with ShouldRaise(ValueError(
            'Cannot add datetime with tzinfo of %s as configured to use None' %(
                tzrepr
            ))):
            t.add(d(2001, 1, 1, tzinfo=tzinfo))

    def test_instantiate_with_datetime(self):
        from datetime import datetime
        t = mock_datetime(datetime(2002, 1, 1, 1))
        compare(t.now(), d(2002, 1, 1, 1, 0, 0))

    @replace('datetime.datetime', mock_datetime(None))
    def test_now_requested_longer_than_supplied(self, t: Type[MockDateTime]):
        t.add(2002, 1, 1, 1, 0, 0)
        t.add(2002, 1, 1, 2, 0, 0)
        from datetime import datetime
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 10))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 30))

    @replace('datetime.datetime', mock_datetime(strict=True))
    def test_call(self, t: Type[MockDateTime]):
        compare(t(2002, 1, 2, 3, 4, 5), d(2002, 1, 2, 3, 4, 5))
        from datetime import datetime
        dt = datetime(2001, 1, 1, 1, 0, 0)
        self.assertFalse(dt.__class__ is d)
        compare(dt, d(2001, 1, 1, 1, 0, 0))

    def test_date_return_type(self):
        with Replacer() as r:
            r.replace('datetime.datetime', mock_datetime())
            from datetime import datetime
            dt = datetime(2001, 1, 1, 1, 0, 0)
            d = dt.date()
            compare(d, date(2001, 1, 1))
            self.assertTrue(d.__class__ is date)

    def test_date_return_type_picky(self):
        # type checking is a bitch :-/
        date_type = mock_date(strict=True)
        with Replacer() as r:
            r.replace('datetime.datetime', mock_datetime(date_type=date_type,
                                                         strict=True,
                                                         ))
            from datetime import datetime
            dt = datetime(2010, 8, 26, 14, 33, 13)
            d = dt.date()
            compare(d, date_type(2010, 8, 26))
            self.assertTrue(d.__class__ is date_type)

    # if you have an embedded `now` as above, *and* you need to supply
    # a list of required datetimes, then it's often simplest just to
    # do a manual try-finally with a replacer:
    def test_import_and_obtain_with_lists(self):

        t = mock_datetime(None)
        t.add(2002, 1, 1, 1, 0, 0)
        t.add(2002, 1, 1, 2, 0, 0)

        from testfixtures import Replacer
        r = Replacer()
        r.replace('testfixtures.tests.sample1.now', t.now)
        try:
            compare(sample1.str_now_2(), '2002-01-01 01:00:00')
            compare(sample1.str_now_2(), '2002-01-01 02:00:00')
        finally:
            r.restore()

    @replace('datetime.datetime', mock_datetime())
    def test_repr(self):
        from datetime import datetime
        compare(repr(datetime), "<class 'testfixtures.datetime.MockDateTime'>")

    @replace('datetime.datetime', mock_datetime(delta=1))
    def test_delta(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 0))
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 1))
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 2))

    @replace('datetime.datetime', mock_datetime(delta_type='minutes'))
    def test_delta_type(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 1, 0, 0, 0))
        compare(datetime.now(), d(2001, 1, 1, 0, 10, 0))
        compare(datetime.now(), d(2001, 1, 1, 0, 30, 0))

    @replace('datetime.datetime', mock_datetime(None))
    def test_set(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        datetime.set(2001, 1, 1, 1, 0, 1)
        compare(datetime.now(), d(2001, 1, 1, 1, 0, 1))
        datetime.set(2002, 1, 1, 1, 0, 0)
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 0))
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 20))

    @replace('datetime.datetime', mock_datetime(None))
    def test_set_datetime_supplied(self, t: Type[MockDateTime]):
        from datetime import datetime
        t.set(d(2002, 1, 1, 1))
        compare(datetime.now(), d(2002, 1, 1, 1, 0, 0))
        t.set(datetime(2002, 1, 1, 2))
        compare(datetime.now(), d(2002, 1, 1, 2, 0, 0))
        tzinfo = SampleTZInfo()
        tzrepr = repr(tzinfo)
        with ShouldRaise(ValueError(
            'Cannot add datetime with tzinfo of %s as configured to use None' %(
                tzrepr
            ))):
            t.set(d(2001, 1, 1, tzinfo=tzinfo))

    @replace('datetime.datetime', mock_datetime(None, tzinfo=SampleTZInfo()))
    def test_set_tz_setup(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        datetime.set(year=2002, month=1, day=1)
        compare(datetime.now(), d(2002, 1, 1))

    @replace('datetime.datetime', mock_datetime(None))
    def test_set_kw(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        datetime.set(year=2002, month=1, day=1)
        compare(datetime.now(), d(2002, 1, 1))

    @replace('datetime.datetime', mock_datetime(None))
    def test_set_tzinfo_kw(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        with ShouldRaise(TypeError('Cannot add using tzinfo on MockDateTime')):
            datetime.set(year=2002, month=1, day=1, tzinfo=SampleTZInfo())

    @replace('datetime.datetime', mock_datetime(None))
    def test_set_tzinfo_args(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        with ShouldRaise(TypeError('Cannot add using tzinfo on MockDateTime')):
            datetime.set(2002, 1, 2, 3, 4, 5, 6, SampleTZInfo())

    @replace('datetime.datetime', mock_datetime(None))
    def test_add_kw(self, t: Type[MockDateTime]):
        from datetime import datetime
        t.add(year=2002, day=1, month=1)
        compare(datetime.now(), d(2002, 1, 1))

    @replace('datetime.datetime', mock_datetime(None))
    def test_add_tzinfo_kw(self, t: Type[MockDateTime]):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        with ShouldRaise(TypeError('Cannot add using tzinfo on MockDateTime')):
            datetime.add(year=2002, month=1, day=1, tzinfo=SampleTZInfo())

    @replace('datetime.datetime', mock_datetime(None))
    def test_add_tzinfo_args(self, t: Type[MockDateTime]):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        with ShouldRaise(TypeError('Cannot add using tzinfo on MockDateTime')):
            datetime.add(2002, 1, 2, 3, 4, 5, 6, SampleTZInfo())

    @replace('datetime.datetime',
             mock_datetime(2001, 1, 2, 3, 4, 5, 6, SampleTZInfo()))
    def test_max_number_args(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 2, 3, 4, 5, 6))

    @replace('datetime.datetime', mock_datetime(2001, 1, 2))
    def test_min_number_args(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 2))

    @replace('datetime.datetime', mock_datetime(
        year=2001,
        month=1,
        day=2,
        hour=3,
        minute=4,
        second=5,
        microsecond=6,
        tzinfo=SampleTZInfo()
        ))
    def test_all_kw(self):
        from datetime import datetime
        compare(datetime.now(), d(2001, 1, 2, 3, 4, 5, 6))

    @replace('datetime.datetime', mock_datetime(2001, 1, 2))
    def test_utc_now(self):
        from datetime import datetime
        compare(datetime.utcnow(), d(2001, 1, 2))

    @replace('datetime.datetime',
             mock_datetime(2001, 1, 2, tzinfo=SampleTZInfo()))
    def test_utc_now_with_tz(self):
        from datetime import datetime
        compare(datetime.utcnow(), d(2001, 1, 1, 23, 56))

    @replace('datetime.datetime', mock_datetime(strict=True))
    def test_isinstance_strict(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        to_check = []
        to_check.append(datetime(1999, 1, 1))
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        to_check.append(datetime.utcnow())
        datetime.set(2001, 1, 1, 20)
        to_check.append(datetime.now())
        datetime.add(2001, 1, 1, 21)
        to_check.append(datetime.now())
        to_check.append(datetime.now())
        datetime.set(datetime(2001, 1, 1, 22))
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        datetime.add(datetime(2001, 1, 1, 23))
        to_check.append(datetime.now())
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        datetime.set(d(2001, 1, 1, 22))
        to_check.append(datetime.now())
        datetime.add(d(2001, 1, 1, 23))
        to_check.append(datetime.now())
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))

        for inst in to_check:
            self.assertTrue(isinstance(inst, datetime), inst)
            self.assertTrue(inst.__class__ is datetime, inst)
            self.assertTrue(isinstance(inst, d), inst)
            self.assertFalse(inst.__class__ is d, inst)

    def test_strict_addition(self):
        mock_dt = mock_datetime(strict=True)
        dt = mock_dt(2001, 1, 1) + timedelta(days=1)
        assert type(dt) is mock_dt

    def test_non_strict_addition(self):
        from datetime import datetime
        mock_dt = mock_datetime(strict=False)
        dt = mock_dt(2001, 1, 1) + timedelta(days=1)
        assert type(dt) is datetime

    def test_strict_add(self):
        mock_dt = mock_datetime(None, strict=True)
        mock_dt.add(2001, 1, 1)
        assert type(mock_dt.now()) is mock_dt

    def test_non_strict_add(self):
        from datetime import datetime
        mock_dt = mock_datetime(None, strict=False)
        mock_dt.add(2001, 1, 1)
        assert type(mock_dt.now()) is datetime

    @replace('datetime.datetime', mock_datetime())
    def test_isinstance_default(self):
        from datetime import datetime
        datetime = cast(Type[MockDateTime], datetime)
        to_check = []
        to_check.append(datetime(1999, 1, 1))
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        to_check.append(datetime.utcnow())
        datetime.set(2001, 1, 1, 20)
        to_check.append(datetime.now())
        datetime.add(2001, 1, 1, 21)
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        datetime.set(datetime(2001, 1, 1, 22))
        to_check.append(datetime.now())
        datetime.add(datetime(2001, 1, 1, 23))
        to_check.append(datetime.now())
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))
        datetime.set(d(2001, 1, 1, 22))
        to_check.append(datetime.now())
        datetime.add(d(2001, 1, 1, 23))
        to_check.append(datetime.now())
        to_check.append(datetime.now())
        to_check.append(datetime.now(SampleTZInfo()))

        for inst in to_check:
            self.assertFalse(isinstance(inst, datetime), inst)
            self.assertFalse(inst.__class__ is datetime, inst)
            self.assertTrue(isinstance(inst, d), inst)
            self.assertTrue(inst.__class__ is d, inst)

    def test_subsecond_deltas(self):
        datetime = mock_datetime(delta=0.5)
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 0, 0))
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 0, 500000))
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 1, 0))

    def test_ms_delta(self):
        datetime = mock_datetime(delta=100, delta_type='microseconds')
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 0, 0))
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 0, 100))
        compare(datetime.now(), datetime(2001, 1, 1, 0, 0, 0, 200))

    def test_tick_when_static(self):
        datetime = mock_datetime(delta=0)
        compare(datetime.now(), expected=d(2001, 1, 1))
        datetime.tick(hours=1)
        compare(datetime.now(), expected=d(2001, 1, 1, 1))

    def test_tick_when_dynamic(self):
        # hopefully not that common?
        datetime = mock_datetime()
        compare(datetime.now(), expected=d(2001, 1, 1))
        datetime.tick(hours=1)
        compare(datetime.now(), expected=d(2001, 1, 1, 1, 0, 10))

    def test_tick_with_timedelta_instance(self):
        datetime = mock_datetime(delta=0)
        compare(datetime.now(), expected=d(2001, 1, 1))
        datetime.tick(timedelta(hours=1))
        compare(datetime.now(), expected=d(2001, 1, 1, 1))

    def test_old_import(self):
        from testfixtures import test_datetime
        assert test_datetime is mock_datetime

    def test_add_timedelta_not_strict(self):
        mock_class = mock_datetime()
        value = mock_class.now() + timedelta(seconds=10)
        assert isinstance(value, datetime)
        assert type(value) is datetime

    def test_add_timedelta_strict(self):
        mock_class = mock_datetime(strict=True)
        value = mock_class.now() + timedelta(seconds=10)
        assert isinstance(value, datetime)
        assert type(value) is mock_class
