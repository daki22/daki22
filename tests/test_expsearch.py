import unittest
from expsearch.importers import read_domains
from expsearch.cli import search
from expsearch.models import Domain
from expsearch.valuation import estimate


class T(unittest.TestCase):
    def test_import_and_filter(self):
        rows = search(read_domains("data/sample.csv"), 5000, words=set())
        names = [d.name for d in rows]
        self.assertIn("vpn.io", names)
        self.assertNotIn("qwzxv.info", names)
        self.assertNotIn("x7-dating-site-2.net", names)
        self.assertEqual(names, sorted(names, key=lambda n: -next(d.value_eur for d in rows if d.name == n)))

    def test_spam_penalty(self):
        a = estimate(Domain("foo.com", referring_domains=1000, authority=50), set())
        b = estimate(Domain("foo.com", referring_domains=1000, authority=50, spam=True), set())
        self.assertLess(b.value_eur, a.value_eur / 10)


if __name__ == "__main__":
    unittest.main()
