# test_ratings.py - RMP name matching and sample-size weighting. No network.
# Usage: python -m unittest test_ratings -v

import unittest
from enrich import same_person
from rank import rmp_score


class SamePersonTest(unittest.TestCase):
    def test_real_matches(self):
        for banner, first, last in [("Karrie Saboe", "Karrie", "Saboe"),
                                    ("Steve Smith", "Steven", "Smith"),
                                    ("Billy VanDenburgh", "William", "VanDenburgh"),
                                    ("R. Roy Martin", "Roy", "Martin"),
                                    ("Kevin Lancaster", "Kevin", "Lancaster "),
                                    ("Vinny Paris", "Vincent", "Paris"),
                                    ("Suanne Ansari-Andrews", "Suanne", "Ansari"),
                                    ("Noelle Zeiner-Carmichael", "Noelle", "Zeiner"),
                                    ("Noelle Zeiner-Carmichael", "Noelle", "Carmichael")]:
            self.assertTrue(same_person(banner, first, last), banner)

    def test_wrong_people_seen_in_live_search(self):
        for banner, first, last in [("Shixuan Wang", "Mia", "Wang"),
                                    ("Shixuan Wang", "Weishen", "Wang"),
                                    ("Vinny Paris", "David", "Parisi"),
                                    ("R. Roy Martin", "Geoffrey", "Martin"),
                                    ("Donna Taylor", "Dawne", "Taylor"),
                                    ("Jun Li", "Steve", "Litvin"),
                                    ("Noelle Zeiner-Carmichael", "Tim", "Carmichael")]:
            self.assertFalse(same_person(banner, first, last), banner)

    def test_blank_names_do_not_match(self):
        self.assertFalse(same_person("", "Karrie", "Saboe"))
        self.assertFalse(same_person("Karrie Saboe", "", "Saboe"))


class RmpScoreTest(unittest.TestCase):
    def test_few_perfect_ratings_lose_to_many_good_ones(self):
        self.assertLess(rmp_score(5.0, 1.5, 100, 3), rmp_score(4.3, 2.5, 85, 100))

    def test_many_ratings_stay_near_raw_score(self):
        raw = 0.9 * 3.0 + (4.1 / 5) * 2.5 + (2.6 / 5) * 1.5
        self.assertAlmostEqual(rmp_score(4.1, 2.4, 90, 100000), raw, places=2)

    def test_unanswered_retake_is_not_a_penalty(self):
        self.assertGreater(rmp_score(4.0, 3.0, -1, 20), rmp_score(4.0, 3.0, 0, 20))


if __name__ == "__main__":
    unittest.main()
