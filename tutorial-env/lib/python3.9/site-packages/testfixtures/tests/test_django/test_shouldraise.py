from django.core.exceptions import ValidationError

from testfixtures import ShouldRaise
from testfixtures.shouldraise import ShouldAssert


class TestShouldRaiseWithValidatorErrors(object):

    def test_as_expected(self):
        with ShouldRaise(ValidationError("d'oh")):
            raise ValidationError("d'oh")

    def test_not_as_expected(self):
        message = (
            'ValidationError(["d\'oh"]) (expected) != '
            'ValidationError([\'nuts\']) (raised)'
        )
        with ShouldAssert(message):
            with ShouldRaise(ValidationError("d'oh")):
                raise ValidationError("nuts")
