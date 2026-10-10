"""Public HTML fixtures for exact MyPrepod teacher identity and native ratings."""

import html
import json
import unittest

from shared_lib.services.teacher_rating_source import (
    CATALOGUE_URL,
    MAX_HTML_BYTES,
    AmbiguousTeacherError,
    SourceParseError,
    UnsafeSourceUrl,
    build_catalogue_url,
    display_teacher_name,
    is_full_teacher_name,
    normalize_teacher_name,
    parse_catalogue,
    parse_profile,
    validate_source_url,
)

NAME = "Чупреева Алёна Николаевна"
PROFILE = "https://myprepod.ru/fa/cupreeva-alena-nikolaevna-15271"
OTHER_PROFILE = "https://myprepod.ru/fa/cupreeva-alena-nikolaevna-25271"


def teacher(**changes):
    # The public page uses Organization for the teacher, not Person (2026-10-10).
    entity = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": NAME,
        "url": PROFILE,
        "parentOrganization": {
            "@type": "CollegeOrUniversity",
            "name": "Финансовый университет",
            "url": CATALOGUE_URL,
        },
        "knowsAbout": "Кафедра искусственного интеллекта",
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": 5,
            "bestRating": 100,
            "worstRating": 0,
            "ratingCount": 56,
            "reviewCount": 7,
        },
    }
    entity.update(changes)
    return entity


def structured(*entities):
    return (
        "<!doctype html><html><head>"
        + "".join(
            '<script type="application/ld+json">' + json.dumps(entity) + "</script>"
            for entity in entities
        )
        + "</head><body></body></html>"
    )


def card(name=NAME, url=PROFILE, title=None):
    return (
        f'<a href="{html.escape(url, quote=True)}" '
        f'title="{html.escape(title or name + " — отзывы студентов", quote=True)}">'
        f'<img alt="{html.escape(name)}"><div><h3>{html.escape(name)}</h3></div>'
        '<div data-teacher-rating data-rating="5"></div></a>'
    )


def catalogue(cards=None, *, found=None, query=NAME, next_url=None, **config_changes):
    cards = [card()] if cards is None else cards
    config = {
        "baseUrl": CATALOGUE_URL,
        "total": 2554,
        "found": len(cards) if found is None else found,
        "state": {"q": query, "dep": "", "reviews": False, "sort": "popular"},
    }
    config.update(config_changes)
    return (
        "<!doctype html><html><head>"
        + (f'<link rel="next" href="{html.escape(next_url)}">' if next_url else "")
        + '</head><body><div data-tutor-catalog data-config="'
        + html.escape(json.dumps(config), quote=True)
        + '"></div>'
        + "".join(cards)
        + "</body></html>"
    )


class TeacherNameTests(unittest.TestCase):
    def test_canonical_name_preserves_exact_full_identity(self):
        self.assertEqual(
            normalize_teacher_name("  Чупреева_АЛЁНА\tНиколаевна "), "чупреева алена николаевна"
        )
        self.assertEqual(display_teacher_name("Чупреева_Алёна\nНиколаевна"), NAME)
        self.assertTrue(is_full_teacher_name("Иванова-Петрова Анна Николаевна"))

    def test_initials_compound_names_and_missing_parts_are_unsupported(self):
        for name in (
            "Чупреева А. Н.",
            "Чупреева А Н",
            "Чупреева Алёна",
            NAME + "; " + NAME,
            "Чупреева/Иванова Алёна Николаевна",
            "Иван Иван Иван,",
            "A" * 201,
            None,
        ):
            with self.subTest(name=name):
                self.assertFalse(is_full_teacher_name(name))
                with self.assertRaises(SourceParseError):
                    build_catalogue_url(name)

    def test_fixed_public_search_url(self):
        from urllib.parse import parse_qs, urlsplit

        url = build_catalogue_url(" Чупреева_Алёна Николаевна ", 2)
        self.assertEqual(urlsplit(url).path, "/universiteti/fa/prepodavateli")
        self.assertEqual(parse_qs(urlsplit(url).query), {"q": [NAME], "page": ["2"]})
        for page in (0, -1, 10000, True, 1.5, "2"):
            with self.assertRaises(SourceParseError):
                build_catalogue_url(NAME, page)


class SourceUrlTests(unittest.TestCase):
    def test_accepts_only_public_university_catalogue_and_profile(self):
        for url in (
            CATALOGUE_URL,
            build_catalogue_url(NAME),
            build_catalogue_url(NAME, 9),
            PROFILE,
        ):
            self.assertEqual(validate_source_url(url), url)
        with self.assertRaises(UnsafeSourceUrl):
            validate_source_url(CATALOGUE_URL, profile_only=True)

    def test_rejects_redirect_ssrf_and_ambiguous_url_forms(self):
        for url in (
            "http://myprepod.ru/fa/name-1",
            "https://myprepod.ru.evil.test/fa/name-1",
            "https://evil.test/fa/name-1",
            "https://user:pass@myprepod.ru/fa/name-1",
            "https://myprepod.ru:443/fa/name-1",
            "https://MYPREPOD.RU/fa/name-1",
            "//myprepod.ru/fa/name-1",
            "/fa/name-1",
            PROFILE + "#x",
            PROFILE + "?next=https://evil.test",
            "https://myprepod.ru/api/search/suggestions?q=x",
            "https://myprepod.ru/legacy-tutor-redirect/15271",
            "https://myprepod.ru/fa/../api/name-1",
            "https://myprepod.ru/fa/%2e%2e/name-1",
            "https://myprepod.ru/fa/name-0",
            "https://myprepod.ru/mgu/name-1",
            "https://myprepod.ru\\@evil.test/fa/name-1",
            "\n" + PROFILE,
            CATALOGUE_URL + "?page=1&page=2",
            CATALOGUE_URL + "?q=Иванов",
            CATALOGUE_URL + "?sort=popular",
            CATALOGUE_URL + "?page=-1",
            CATALOGUE_URL + "?page=01",
            CATALOGUE_URL + "?page=99999",
            None,
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeSourceUrl):
                validate_source_url(url)


class CatalogueTests(unittest.TestCase):
    def test_observed_html_matches_exact_name_after_allowed_normalization(self):
        result = parse_catalogue(catalogue(), "чупреева_алена николаевна")
        self.assertEqual([(c.name, c.url) for c in result.candidates], [(NAME, PROFILE)])
        self.assertEqual(result.total_found, 1)
        self.assertTrue(result.search_complete)
        self.assertFalse(result.ambiguous)

    def test_similar_or_reordered_name_never_matches(self):
        cards = [
            card("Чупреева Алёна Александровна"),
            card("Алёна Чупреева Николаевна", OTHER_PROFILE),
        ]
        result = parse_catalogue(catalogue(cards, found=2), NAME)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.observed_urls, (PROFILE, OTHER_PROFILE))

    def test_duplicate_same_profile_is_deduplicated_but_two_profiles_ambiguous(self):
        same = parse_catalogue(catalogue([card(), card()], found=1), NAME)
        self.assertEqual(len(same.candidates), 1)
        self.assertFalse(same.ambiguous)
        self.assertEqual(same.observed_urls, (PROFILE,))
        distinct = parse_catalogue(catalogue([card(), card(url=OTHER_PROFILE)]), NAME)
        self.assertEqual(len(distinct.candidates), 2)
        self.assertTrue(distinct.ambiguous)

    def test_observed_urls_expose_skipped_or_repeated_pagination_cards(self):
        first = parse_catalogue(catalogue(found=3, next_url=build_catalogue_url(NAME, 3)), NAME)
        final = parse_catalogue(
            catalogue([card("Чупреева Алёна Александровна", OTHER_PROFILE)], found=3),
            NAME,
            build_catalogue_url(NAME, 3),
        )
        self.assertEqual(len(set(first.observed_urls) | set(final.observed_urls)), 2)
        self.assertNotEqual(
            len(set(first.observed_urls) | set(final.observed_urls)), first.total_found
        )
        repeated = parse_catalogue(catalogue(found=3), NAME, build_catalogue_url(NAME, 2))
        self.assertEqual(set(first.observed_urls) & set(repeated.observed_urls), {PROFILE})

    def test_observed_urls_exclude_unrelated_or_unsafe_profiles(self):
        document = catalogue(
            [card(), card("Иванов Иван Иванович", "https://evil.test/fa/person-1")], found=2
        )
        result = parse_catalogue(document, NAME)
        self.assertEqual(result.observed_urls, (PROFILE,))
        self.assertFalse(result.search_complete)

    def test_detects_pagination_and_does_not_claim_uniqueness_early(self):
        next_url = build_catalogue_url(NAME, 2)
        result = parse_catalogue(catalogue(found=13, next_url=next_url), NAME)
        self.assertFalse(result.search_complete)
        self.assertEqual(result.next_urls, (next_url,))
        final = parse_catalogue(catalogue(found=13), NAME, next_url)
        self.assertTrue(final.search_complete)

    def test_missing_pagination_or_cards_is_incomplete_not_not_found(self):
        for document in (catalogue(found=20), catalogue([], found=1)):
            self.assertFalse(parse_catalogue(document, NAME).search_complete)
        empty = parse_catalogue(catalogue([], found=0), NAME)
        self.assertTrue(empty.search_complete)
        self.assertEqual(empty.candidates, ())

    def test_rejects_missing_metadata_wrong_query_or_filters(self):
        for document in (
            card(),
            catalogue(query="Иванов Иван Иванович"),
            catalogue(baseUrl=CATALOGUE_URL + "/evil"),
            catalogue(state={"q": NAME, "dep": "faculty", "reviews": False}),
            catalogue(state={"q": NAME, "dep": "", "reviews": True}),
            catalogue(found=-1),
            catalogue(found=True),
            catalogue(found=1.5),
            catalogue(found=0),
        ):
            with self.subTest(document=document[:60]), self.assertRaises(SourceParseError):
                parse_catalogue(document, NAME)

    def test_rejects_changed_query_or_unsafe_pagination(self):
        for url in (
            build_catalogue_url("Иванов Иван Иванович", 2),
            CATALOGUE_URL + "?page=2",
            "https://evil.test/?page=2",
            "https://myprepod.ru/api/search?page=2",
            PROFILE,
            build_catalogue_url(NAME),
            build_catalogue_url(NAME) + "&page=1",
        ):
            with self.subTest(url=url), self.assertRaises(SourceParseError):
                parse_catalogue(catalogue(found=13, next_url=url), NAME)

    def test_one_profile_with_conflicting_catalogue_names_fails_closed(self):
        with self.assertRaises(SourceParseError):
            parse_catalogue(catalogue([card(), card("Чупреева Алёна Александровна")]), NAME)

    def test_rejects_exact_candidate_external_url_or_conflicting_title(self):
        for candidate in (
            card(url="https://evil.test/fa/name-1"),
            card(title="Иванов Иван Иванович — отзывы студентов"),
        ):
            with self.assertRaises(SourceParseError):
                parse_catalogue(catalogue([candidate]), NAME)


class ProfileTests(unittest.TestCase):
    def test_observed_organization_representation_with_native_scale(self):
        result = parse_profile(structured(teacher()), "чупреева алена николаевна", PROFILE)
        self.assertEqual((result.name, result.url), (NAME, PROFILE))
        self.assertEqual(
            (result.rating_percent, result.vote_count, result.review_count), (5, 56, 7)
        )
        self.assertEqual(result.department, "Кафедра искусственного интеллекта")

    def test_person_graph_and_nearby_department_do_not_mix_aggregates(self):
        person = teacher(**{"@type": "Person"})
        person["worksFor"] = person.pop("parentOrganization")
        department = teacher(
            name="Кафедра искусственного интеллекта", url=CATALOGUE_URL + "/department"
        )
        department["aggregateRating"]["ratingValue"] = 99
        result = parse_profile(structured({"@graph": [department, person]}), NAME, PROFILE)
        self.assertEqual(result.rating_percent, 5)

    def test_review_author_cannot_impersonate_teacher(self):
        review = {"@type": "Review", "author": teacher()}
        with self.assertRaises(SourceParseError):
            parse_profile(structured(review), NAME, PROFILE)

    def test_wrong_university_name_url_or_teacher_rejected(self):
        wrong_name = teacher()
        wrong_name["parentOrganization"]["name"] = "Другой университет"
        wrong_url = teacher()
        wrong_url["parentOrganization"]["url"] = (
            "https://myprepod.ru/universiteti/mgu/prepodavateli"
        )
        for entity in (wrong_name, wrong_url, teacher(name="Иванов Иван Иванович")):
            with self.assertRaises(SourceParseError):
                parse_profile(structured(entity), NAME, PROFILE)

    def test_malicious_profile_url_and_wrong_identity_rejected(self):
        for url in (
            "https://evil.test/fa/name-1",
            "https://user@myprepod.ru/fa/name-1",
            "https://myprepod.ru/legacy-tutor-redirect/15271",
            OTHER_PROFILE,
        ):
            with self.subTest(url=url), self.assertRaises(SourceParseError):
                parse_profile(structured(teacher(url=url)), NAME, PROFILE)

    def test_duplicate_identical_data_allowed_but_conflicting_values_ambiguous(self):
        self.assertEqual(
            parse_profile(structured(teacher(), teacher()), NAME, PROFILE).vote_count, 56
        )
        second = teacher()
        second["aggregateRating"]["ratingValue"] = 99
        with self.assertRaises(AmbiguousTeacherError):
            parse_profile(structured(teacher(), second), NAME, PROFILE)

    def test_missing_rating_and_missing_counts_remain_none(self):
        no_aggregate = teacher(aggregateRating=None)
        result = parse_profile(structured(no_aggregate), NAME, PROFILE)
        self.assertEqual(
            (result.rating_percent, result.vote_count, result.review_count), (None, None, None)
        )
        partial = teacher(aggregateRating={"@type": "AggregateRating", "ratingCount": 5})
        result = parse_profile(structured(partial), NAME, PROFILE)
        self.assertEqual(
            (result.rating_percent, result.vote_count, result.review_count), (None, 5, None)
        )

    def test_zero_rating_is_valid_but_zero_votes_does_not_invent_rating(self):
        entity = teacher()
        entity["aggregateRating"]["ratingValue"] = 0
        self.assertEqual(parse_profile(structured(entity), NAME, PROFILE).rating_percent, 0)
        entity["aggregateRating"]["ratingCount"] = 0
        self.assertIsNone(parse_profile(structured(entity), NAME, PROFILE).rating_percent)

    def test_invalid_rating_scale_numeric_values_and_counts_rejected(self):
        invalid = (
            ("ratingValue", -1),
            ("ratingValue", 101),
            ("ratingValue", "NaN"),
            ("ratingValue", float("inf")),
            ("ratingValue", True),
            ("ratingValue", {}),
            ("bestRating", 5),
            ("worstRating", 1),
            ("bestRating", None),
            ("ratingCount", -1),
            ("ratingCount", True),
            ("reviewCount", 3.2),
            ("ratingCount", 2**32),
            ("reviewCount", "-1"),
        )
        for key, value in invalid:
            with self.subTest(key=key, value=value), self.assertRaises(SourceParseError):
                entity = teacher()
                entity["aggregateRating"][key] = value
                parse_profile(structured(entity), NAME, PROFILE)

    def test_string_counts_supported_without_coercing_missing(self):
        entity = teacher()
        entity["aggregateRating"].update(ratingValue="5.5", ratingCount="56", reviewCount="0")
        result = parse_profile(structured(entity), NAME, PROFILE)
        self.assertEqual(
            (result.rating_percent, result.vote_count, result.review_count), (5.5, 56, 0)
        )

    def test_invalid_structured_data_and_oversized_html_fail_closed(self):
        for document in (
            '<script type="application/ld+json">{bad json}</script>',
            '<script type="application/ld+json">{"@type":"Person","@type":"Organization"}</script>',
            "<html>unavailable</html>",
            "x" * (MAX_HTML_BYTES + 1),
        ):
            with self.assertRaises(SourceParseError):
                parse_profile(document, NAME, PROFILE)


if __name__ == "__main__":
    unittest.main()
