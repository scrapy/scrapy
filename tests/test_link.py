import unittest

from scrapy.link import Link


class LinkTest(unittest.TestCase):
    def _assert_same_links(self, link1, link2):
        self.assertEqual(link1, link2)
        self.assertEqual(hash(link1), hash(link2))

    def _assert_different_links(self, link1, link2):
        self.assertNotEqual(link1, link2)
        self.assertNotEqual(hash(link1), hash(link2))

    def test_eq_and_hash_1(self):
        """
        Tests if two instances of Link with the
        same url recognize they have the same url
        """
        l1 = Link("http://www.example.com")

        self._assert_same_links(l1, l1)

    def test_eq_and_hash_2(self):
        """
        Tests if two instances of Link with different
        url address recognize they are different even
        if the initial part is the same.
        """
        l1 = Link("http://www.example.com")
        l2 = Link("http://www.example.com/other")

        self._assert_different_links(l1, l2)

    def test_eq_and_hash_3(self):
        """
        Checks if two instances of Link successufully
        capture the address they are point two if it is
        the same address.
        """
        l1 = Link("http://www.example.com")
        l3 = Link("http://www.example.com")

        self._assert_same_links(l1, l3)

    def test_eq_and_hash_4(self):
        """
        Tests if an instance of Link successfully recognizes
        it points to the same url if it is compared with itself
        """
        l4 = Link("http://www.example.com", text="test")
        self._assert_same_links(l4, l4)

    def test_eq_and_hash_5(self):
        """
        Tests if two instances of Link that point to the same url
        are not evaluating that they point to the same url if they
        have different text variable values.
        """
        l4 = Link("http://www.example.com", text="test")
        l5 = Link("http://www.example.com", text="test2")

        self._assert_different_links(l4, l5)

    def test_eq_and_hash_6(self):
        """
        Tests if two instances of Link that point to the same url
        are evaluated that they point to the same url if they
        have the same text variable values.
        """
        l4 = Link("http://www.example.com", text="test")
        l6 = Link("http://www.example.com", text="test")
        self._assert_same_links(l4, l6)

    def test_eq_and_hash_7(self):
        """
        Tests if two instances of Link that point to the same url
        are evaluated that they point to the same url if they
        have the same text and fragment variable values and they both
        have the nofollow option set to False.
        """
        l7 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=False
        )
        l8 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=False
        )
        self._assert_same_links(l7, l8)

    def test_eq_and_hash_8(self):
        """
        Tests if two instances of Link that point to the same url
        are evaluated as different if they point to the same url and
        have the same text and fragment variable values but one is set
        to have the nofollow option set to False while the other to True.
        """
        l7 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=False
        )
        l9 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=True
        )
        self._assert_different_links(l7, l9)

    def test_eq_and_hash_9(self):
        """
        Tests if two instances of Link that point to the same url
        are evaluated as different if they point to the same url and
        have the same text variable values and both haves set the
        nofollow option to False but they have different fragment values.
        """
        l7 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=False
        )
        l10 = Link(
            "http://www.example.com", text="test", fragment="other", nofollow=False
        )
        self._assert_different_links(l7, l10)

    def test_repr(self):
        """
        Tests if the repr function successfully creates a similar copy of a Link
        instance.
        """
        l1 = Link(
            "http://www.example.com", text="test", fragment="something", nofollow=True
        )
        l2 = eval(repr(l1))
        self._assert_same_links(l1, l2)

    def test_bytes_url(self):
        """
        Tests if a wrong argument is passed in the initialization of
        a Link instance successfully raises a TypeError.
        """
        with self.assertRaises(TypeError):
            Link(b"http://www.example.com/\xc2\xa3")


if __name__ == "__main__":
    unittest.main()
