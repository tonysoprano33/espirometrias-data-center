from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .roles import provision_role_session_accounts


class FixedRoleSessionTests(TestCase):
    def setUp(self):
        provision_role_session_accounts()
        self.User = get_user_model()

    def test_reserved_accounts_share_the_configured_password_and_only_their_permissions(self):
        secretary = self.User.objects.get(username="secretaria")
        doctor = self.User.objects.get(username="medico")
        technician = self.User.objects.get(username="espirometro")

        self.assertTrue(secretary.check_password("123"))
        self.assertTrue(doctor.check_password("123"))
        self.assertTrue(technician.check_password("123"))
        self.assertTrue(secretary.has_perm("clinic.manage_agenda"))
        self.assertFalse(secretary.has_perm("clinic.review_medically"))
        self.assertTrue(doctor.has_perm("clinic.review_medically"))
        self.assertFalse(doctor.has_perm("clinic.manage_agenda"))
        self.assertTrue(technician.has_perm("clinic.manage_agenda"))
        self.assertTrue(technician.has_perm("clinic.review_medically"))
        self.assertTrue(technician.has_perm("clinic.view_clinical_statistics"))

    def test_login_page_does_not_reprovision_reserved_accounts(self):
        with patch("clinic.auth_views.provision_role_session_accounts") as provision_accounts:
            response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        provision_accounts.assert_not_called()

    def test_login_repairs_a_missing_reserved_account(self):
        self.User.objects.get(username="medico").delete()

        with patch(
            "clinic.auth_views.provision_role_session_accounts",
            wraps=provision_role_session_accounts,
        ) as provision_accounts:
            response = self.client.post(
                reverse("login"),
                {"username": "medico", "password": "123"},
            )

        self.assertRedirects(response, reverse("clinic:doctor_review_list"))
        provision_accounts.assert_called_once_with()

    def test_secretary_role_ignores_a_stale_browser_mode_after_reload(self):
        self.client.force_login(self.User.objects.get(username="secretaria"))
        session = self.client.session
        session["clinic_work_mode"] = "medico"
        session.save()

        response = self.client.get(reverse("clinic:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secretaría")
        self.assertContains(response, "secretary-agenda")
        self.assertNotContains(response, "Pegar Drapp")
        self.assertContains(response, 'data-logout-dialog-open')
        self.assertContains(response, 'id="session-logout-dialog"')

    def test_doctor_role_opens_medical_review_and_cannot_be_switched_by_post(self):
        login_response = self.client.post(
            reverse("login"),
            {"username": "medico", "password": "123"},
        )
        self.assertRedirects(login_response, reverse("clinic:doctor_review_list"))

        response = self.client.post(
            reverse("clinic:set_work_mode"),
            {"work_mode": "secretaria"},
        )
        self.assertRedirects(response, reverse("clinic:doctor_review_list"))

        dashboard_response = self.client.get(reverse("clinic:dashboard"))
        self.assertRedirects(dashboard_response, reverse("clinic:doctor_review_list"))
