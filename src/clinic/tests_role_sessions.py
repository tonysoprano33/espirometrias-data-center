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

        self.assertTrue(secretary.check_password("espirometriamarconi123"))
        self.assertTrue(doctor.check_password("espirometriamarconi123"))
        self.assertTrue(technician.check_password("espirometriamarconi123"))
        self.assertTrue(secretary.has_perm("clinic.manage_agenda"))
        self.assertFalse(secretary.has_perm("clinic.review_medically"))
        self.assertTrue(doctor.has_perm("clinic.review_medically"))
        self.assertFalse(doctor.has_perm("clinic.manage_agenda"))
        self.assertTrue(technician.has_perm("clinic.manage_agenda"))
        self.assertTrue(technician.has_perm("clinic.review_medically"))
        self.assertTrue(technician.has_perm("clinic.view_clinical_statistics"))

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

    def test_doctor_role_opens_medical_review_and_cannot_be_switched_by_post(self):
        login_response = self.client.post(
            reverse("login"),
            {"username": "medico", "password": "espirometriamarconi123"},
        )
        self.assertRedirects(login_response, reverse("clinic:doctor_review_list"))

        response = self.client.post(
            reverse("clinic:set_work_mode"),
            {"work_mode": "secretaria"},
        )
        self.assertRedirects(response, reverse("clinic:doctor_review_list"))

        dashboard_response = self.client.get(reverse("clinic:dashboard"))
        self.assertRedirects(dashboard_response, reverse("clinic:doctor_review_list"))
