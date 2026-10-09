from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import CoverageType, Encounter, EncounterStatus, Patient, StudyType, WalkTest


class AgendaWalkTestQueryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="agenda-query-test", password="test-password")
        permission = Permission.objects.get(content_type__app_label="clinic", codename="manage_agenda")
        self.user.user_permissions.add(permission)
        self.client.force_login(self.user)

    def create_cyclometry_encounter(self, index, state):
        patient = Patient.objects.create(
            full_name=f"PACIENTE DE PRUEBA {index}",
            dni=f"900000{index:03d}",
        )
        encounter = Encounter.objects.create(
            patient=patient,
            encounter_date=timezone.localdate(),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )
        WalkTest.objects.create(
            encounter=encounter,
            completed=state[0],
            stopped=state[1],
            symptoms=state[2],
            distance_meters=state[3],
            borg_final=state[4],
        )
        return encounter

    def count_individual_walk_test_selects(self, captured_queries):
        table = connection.ops.quote_name(WalkTest._meta.db_table)
        prefix = f"FROM {table}"
        return sum(prefix in query["sql"] for query in captured_queries)

    def test_initial_agenda_query_count_stays_bounded_as_encounters_grow(self):
        self.create_cyclometry_encounter(1, (True, False, False, 200, 1))
        url = reverse("clinic:dashboard")
        with CaptureQueriesContext(connection) as one_encounter_queries:
            one_response = self.client.get(url)
        self.assertEqual(one_response.status_code, 200)

        states = [
            (True, False, True, 200, 4),
            (False, True, True, 100, 7),
            (True, False, False, 200, 2),
            (False, False, True, 100, 5),
            (True, True, True, 100, 8),
            (True, False, False, 200, 1),
            (False, True, False, 100, 6),
        ]
        for index, state in enumerate(states, start=2):
            self.create_cyclometry_encounter(index, state)

        with CaptureQueriesContext(connection) as many_encounter_queries:
            many_response = self.client.get(url)
        self.assertEqual(many_response.status_code, 200)

        one_walk_selects = self.count_individual_walk_test_selects(one_encounter_queries.captured_queries)
        many_walk_selects = self.count_individual_walk_test_selects(many_encounter_queries.captured_queries)
        self.assertLessEqual(
            many_walk_selects,
            one_walk_selects + 1,
            "walk_test SELECTs grew with the agenda: "
            f"one encounter={one_walk_selects} ({len(one_encounter_queries)} total queries), "
            f"eight encounters={many_walk_selects} ({len(many_encounter_queries)} total queries).",
        )
        self.assertLessEqual(
            len(many_encounter_queries) - len(one_encounter_queries),
            2,
            "The initial agenda should keep SQL query growth bounded as encounters increase.",
        )

    def test_poll_json_and_walk_test_values_are_unchanged_by_initial_page_load(self):
        encounters = [
            self.create_cyclometry_encounter(20, (True, False, False, 200, 1)),
            self.create_cyclometry_encounter(21, (False, True, True, 100, 7)),
            self.create_cyclometry_encounter(22, (True, False, True, 200, 4)),
        ]
        poll_url = reverse("clinic:dashboard_rows_state")
        before = self.client.get(poll_url)
        self.assertEqual(before.status_code, 200)
        before_payload = before.json()
        before_rows = {row["encounter_id"]: row for row in before_payload["rows"]}
        self.assertTrue({encounter.pk for encounter in encounters}.issubset(before_rows))
        self.assertTrue(all(before_rows[encounter.pk]["has_cycle_data"] for encounter in encounters))
        self.assertTrue(
            all(before_rows[encounter.pk]["status"] == EncounterStatus.PENDIENTE for encounter in encounters)
        )

        page = self.client.get(reverse("clinic:dashboard"))
        self.assertEqual(page.status_code, 200)

        after = self.client.get(poll_url)
        self.assertEqual(after.status_code, 200)
        after_payload = after.json()
        before_payload.pop("checked_at")
        after_payload.pop("checked_at")
        self.assertEqual(after_payload, before_payload)

        actual_walk_states = []
        for encounter in encounters:
            encounter.walk_test.refresh_from_db()
            actual_walk_states.append(
                (
                    encounter.walk_test.completed,
                    encounter.walk_test.stopped,
                    encounter.walk_test.symptoms,
                    encounter.walk_test.distance_meters,
                    encounter.walk_test.borg_final,
                )
            )
        self.assertEqual(
            actual_walk_states,
            [(True, False, False, 200, 1), (False, True, True, 100, 7), (True, False, True, 200, 4)],
        )

    def test_poll_still_requires_authentication(self):
        self.client.logout()

        response = self.client.get(reverse("clinic:dashboard_rows_state"))

        self.assertEqual(response.status_code, 302)
