from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Attachment, AttachmentKind, CoverageType, Encounter, EncounterStatus, Patient, SpirometryResult, StudyType, VitalSigns, WalkTest
from .pdf_intake import (
    build_analysis_from_text,
    build_spirometry_analysis,
    snapshot_with_computed_age,
    extract_patient_snapshot_from_text,
    extract_spirometry_numbers_from_text,
)
from .services import construir_informe_espirometria
from .views import (
    extract_drapp_rows_from_browser_ocr,
    extract_drapp_rows_from_ocr_lines,
    extract_drapp_rows_from_text,
    infer_coverage_type,
    import_drapp_rows,
    unique_encounters_by_patient_day,
)


class SpirometryReportTextTests(SimpleTestCase):
    def test_mixed_pattern_mentions_small_airways(self):
        text = construir_informe_espirometria("Mixto", "leve", "moderada")

        self.assertIn("peque", text.lower())
        self.assertIn("restric", text.lower())
        self.assertIn("obstru", text.lower())

    def test_restrictive_pattern_keeps_general_airways_text(self):
        text = construir_informe_espirometria("Restrictivo", "", "moderada")

        self.assertIn("respiratorias", text.lower())
        self.assertNotIn("peque", text.lower())


class CoverageInferenceTests(SimpleTestCase):
    def test_only_particular_stays_particular(self):
        self.assertEqual(infer_coverage_type("Particular"), "Particular")

    def test_any_other_coverage_becomes_mutual(self):
        self.assertEqual(infer_coverage_type("grassi"), "Mutual")
        self.assertEqual(infer_coverage_type("DOSEP"), "Mutual")
        self.assertEqual(infer_coverage_type(""), "Mutual")


class DrappImportParsingTests(SimpleTestCase):
    def test_extracts_patient_when_status_lines_come_before_name(self):
        rows = extract_drapp_rows_from_ocr_lines(
            [
                {"text": "Jueves 4 - junio 2026", "y": 0},
                {"text": "15:00", "y": 40},
                {"text": "hace 2 dias", "y": 70},
                {"text": "Reservado", "y": 100},
                {"text": "Oruetta , Ramona", "y": 130},
                {"text": "+54 2657 61 3457", "y": 160},
                {"text": "Particular", "y": 190},
                {"text": "Link de Pago", "y": 220},
                {"text": "Centro Respiratorio Integral", "y": 250},
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["patient_name"], "ORUETTA, RAMONA")
        self.assertEqual(rows[0]["coverage_raw"], "Particular")
        self.assertEqual(rows[0]["agenda_date"], date(2026, 6, 4))

    def test_keeps_importing_when_study_column_is_not_visible(self):
        rows = extract_drapp_rows_from_ocr_lines(
            [
                {"text": "Jueves 4 - junio 2026", "y": 0},
                {"text": "16:15", "y": 40},
                {"text": "Reservado", "y": 70},
                {"text": "Chavez9/144, Marcelo", "y": 100},
                {"text": "+542664648159", "y": 130},
                {"text": "DOSEP", "y": 160},
                {"text": "29.936.370", "y": 190},
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["patient_name"], "CHAVEZ, MARCELO")
        self.assertEqual(rows[0]["coverage_raw"], "DOSEP")
        self.assertEqual(rows[0]["practice_raw"], "")
        self.assertEqual(rows[0]["dni"], "29936370")

    def test_extracts_all_rows_from_notebook_screenshot_ocr(self):
        rows = extract_drapp_rows_from_ocr_lines(
            [
                {"text": "Viernes 5 - junio 2026 - Todos 5 Reservados 5 En Espera 0 En consulta 0 Atendidos 0 Ausentes 0 Cancelados 0 Pendiente 0", "y": 0},
                {"text": "@ 09:20 hace 2 dias ?+542657555332 Avila3/915, Maria Del Carmen 16.133.118 Particular Link de Pago Espirometria Espirometria Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 40},
                {"text": "Reservado", "y": 64},
                {"text": "@ 09:40 hace 15 horas +542658 40 7539 PERALTA, MARCELA 22.822.428 Particular Link de Pago Cicloespirometria Espirometria Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 98},
                {"text": "Reservado", "y": 124},
                {"text": "\u246010:00 Fredes, Josefa PAMI 6/535 Cicloespirometria Espirometria", "y": 160},
                {"text": "Reservado hace 6 dias +542657610914 5.182.672 Link de Pago Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 186},
                {"text": "\u2460 11:00 hace 3 dias Bigner, Maria Estela +5426575809643.697.049 DOSEP Link de Pago Cicloespirometria Espirometria Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 220},
                {"text": "Reservado", "y": 246},
                {"text": "\u246011:15 hace 1 dia +542657 65 4467 PAREDES, CARLOS FENIX 10.705.164 Particular Link de Pago Cicloespirometria Espirometria Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 282},
                {"text": "Reservado", "y": 308},
            ]
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [(row["datetime_raw"], row["patient_name"]) for row in rows],
            [
                ("09:20", "AVILA, MARIA DEL CARMEN"),
                ("09:40", "PERALTA, MARCELA"),
                ("10:00", "FREDES, JOSEFA"),
                ("11:00", "BIGNER, MARIA ESTELA"),
                ("11:15", "PAREDES, CARLOS FENIX"),
            ],
        )
        self.assertEqual(rows[2]["coverage_raw"], "PAMI")
        self.assertEqual(rows[2]["dni"], "5182672")
        self.assertEqual(rows[3]["coverage_raw"], "DOSEP")
        self.assertEqual(rows[3]["dni"], "3697049")
        self.assertEqual(rows[4]["dni"], "10705164")
        self.assertEqual(rows[0]["agenda_date"], date(2026, 6, 5))

    def test_ocr_like_raw_text_falls_back_to_capture_parser(self):
        rows = extract_drapp_rows_from_text(
            "\n".join(
                [
                    "Viernes 5 - junio 2026",
                    "@ 09:20 hace 2 dias +542657555332 Avila3/915, Maria Del Carmen 16.133.118 Particular",
                    "@ 09:40 hace 15 horas +542658 40 7539 PERALTA, MARCELA 22.822.428 Particular",
                    "\u246010:00 Fredes, Josefa PAMI 6/535 Cicloespirometria",
                    "Reservado hace 6 dias +542657610914 5.182.672",
                    "\u2460 11:00 hace 3 dias Bigner, Maria Estela +5426575809643.697.049 DOSEP",
                    "\u246011:15 hace 1 dia +542657 65 4467 PAREDES, CARLOS FENIX 10.705.164 Particular",
                ]
            )
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2]["patient_name"], "FREDES, JOSEFA")
        self.assertEqual(rows[3]["dni"], "3697049")

    def test_trims_study_fragments_and_false_prefixes_from_patient_name(self):
        rows = extract_drapp_rows_from_ocr_lines(
            [
                {"text": "Jueves 11 - junio 2026", "y": 0},
                {"text": "15:55 ORTIZ, MARTA LILIANA 16.484.284 Link de Pago Cicloespirometria Espirometria Espirometria, Piguillem Gustavo Centro Respiratorio Integral", "y": 40},
                {"text": "Reservado hace 6 horas Particular", "y": 64},
                {"text": "16:30 SUAREZ, RODRIGO ESPI 37.797.996 Particular", "y": 98},
                {"text": "16:55 OR DEVIA, CARLOS EVA 13.435.809 PAMI ESPIROMETRIA", "y": 130},
                {"text": "17:15 ESPIROMETRIA, DIM CE 6.484.284 Particular", "y": 160},
                {"text": "18:00 Mercado, Rosario 54.002.437 DOSEP 8/11 Cicloespirometria Espirometria", "y": 190},
            ]
        )

        self.assertEqual(
            [(row["datetime_raw"], row["patient_name"]) for row in rows],
            [
                ("15:55", "ORTIZ, MARTA LILIANA"),
                ("16:30", "SUAREZ, RODRIGO"),
                ("16:55", "DEVIA, CARLOS EVA"),
                ("18:00", "MERCADO, ROSARIO"),
            ],
        )
        self.assertEqual(rows[0]["dni"], "16484284")
        self.assertEqual(rows[1]["dni"], "37797996")
        self.assertEqual(rows[2]["dni"], "13435809")

    def test_browser_ocr_structured_columns_keep_name_dni_and_coverage_clean(self):
        payload = [
            {
                "text": "15:55 ORTIZ, MARTA LILIANA Link de Pago Cicloespirometria",
                "y": 40,
                "items": [
                    {"text": "15:55", "x": 60, "y": 40},
                    {"text": "ORTIZ,", "x": 210, "y": 40},
                    {"text": "MARTA", "x": 290, "y": 40},
                    {"text": "LILIANA", "x": 370, "y": 40},
                    {"text": "Link", "x": 700, "y": 40},
                    {"text": "de", "x": 745, "y": 40},
                    {"text": "Pago", "x": 780, "y": 40},
                    {"text": "Cicloespirometria", "x": 980, "y": 40},
                ],
            },
            {
                "text": "16.484.284",
                "y": 68,
                "items": [
                    {"text": "16.484.284", "x": 420, "y": 68},
                ],
            },
            {
                "text": "16:30 Suarez , Rodrigo +54 2657 29 0348 37.797.996 Particular",
                "y": 110,
                "items": [
                    {"text": "16:30", "x": 60, "y": 110},
                    {"text": "Suarez", "x": 210, "y": 110},
                    {"text": ",", "x": 300, "y": 110},
                    {"text": "Rodrigo", "x": 325, "y": 110},
                    {"text": "+54", "x": 215, "y": 138},
                    {"text": "2657", "x": 255, "y": 138},
                    {"text": "29", "x": 320, "y": 138},
                    {"text": "0348", "x": 355, "y": 138},
                    {"text": "37.797.996", "x": 430, "y": 138},
                    {"text": "Particular", "x": 710, "y": 110},
                ],
            },
            {
                "text": "16:55 OR DEVIA, CARLOS EVARISTO PAMI",
                "y": 180,
                "items": [
                    {"text": "16:55", "x": 60, "y": 180},
                    {"text": "OR", "x": 190, "y": 180},
                    {"text": "DEVIA,", "x": 220, "y": 180},
                    {"text": "CARLOS", "x": 320, "y": 180},
                    {"text": "EVARISTO", "x": 405, "y": 180},
                    {"text": "PAMI", "x": 710, "y": 180},
                    {"text": "+54", "x": 215, "y": 208},
                    {"text": "2657", "x": 255, "y": 208},
                    {"text": "44", "x": 320, "y": 208},
                    {"text": "8093", "x": 355, "y": 208},
                    {"text": "13.435.809", "x": 430, "y": 208},
                ],
            },
        ]

        rows = extract_drapp_rows_from_browser_ocr(__import__("json").dumps(payload))

        self.assertEqual(
            [(row["datetime_raw"], row["patient_name"], row["dni"], row["coverage_raw"]) for row in rows],
            [
                ("15:55", "ORTIZ, MARTA LILIANA", "16484284", ""),
                ("16:30", "SUAREZ, RODRIGO", "37797996", "Particular"),
                ("16:55", "DEVIA, CARLOS EVARISTO", "13435809", "PAMI"),
            ],
        )


class DrappImportViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="drapp-test", password="secret123")

    def test_falls_back_to_uploaded_screenshot_when_browser_ocr_returns_no_rows(self):
        self.client.force_login(self.user)
        screenshot = SimpleUploadedFile("drapp.png", b"fake image bytes", content_type="image/png")
        screenshot_rows = [
            {
                "patient_name": "PERALTA, MARCELA",
                "coverage_raw": "Particular",
                "practice_raw": "Cicloespirometria",
                "datetime_raw": "09:40",
                "phone": "+542658407539",
                "dni": "22822428",
                "agenda_date": date(2026, 6, 5),
            }
        ]

        with (
            patch("clinic.views.extract_drapp_rows_from_text", return_value=[]),
            patch("clinic.views.extract_drapp_rows_from_browser_ocr", return_value=[]),
            patch("clinic.views.extract_drapp_rows_from_screenshot", return_value=screenshot_rows) as screenshot_mock,
            patch("clinic.views.import_drapp_rows", return_value=(1, 0)) as import_mock,
        ):
            response = self.client.post(
                reverse("clinic:dashboard"),
                {
                    "action": "import_drapp",
                    "raw_text": "texto pobre del OCR del navegador",
                    "ocr_lines_json": '[{"text":"ruido","y":0}]',
                    "screenshot": screenshot,
                },
            )

        self.assertRedirects(response, reverse("clinic:dashboard"))
        screenshot_mock.assert_called_once()
        self.assertEqual(import_mock.call_args[0][0], screenshot_rows)
        self.assertEqual(import_mock.call_args[0][1], self.user)

    def test_prefers_browser_ocr_rows_over_plain_raw_text_from_same_capture(self):
        self.client.force_login(self.user)
        browser_rows = [
            {
                "patient_name": "ORTIZ, MARTA LILIANA",
                "coverage_raw": "Particular",
                "practice_raw": "Cicloespirometria",
                "datetime_raw": "15:55",
                "phone": "",
                "dni": "16484284",
                "agenda_date": date(2026, 6, 11),
            },
            {
                "patient_name": "SUAREZ, RODRIGO",
                "coverage_raw": "Particular",
                "practice_raw": "Cicloespirometria",
                "datetime_raw": "16:30",
                "phone": "+542657292348",
                "dni": "37797896",
                "agenda_date": date(2026, 6, 11),
            },
        ]

        with (
            patch(
                "clinic.views.extract_drapp_rows_from_text",
                return_value=[
                    {
                        "patient_name": "ESPIROMETRIA, DINOS CENTRO I RESPIRATORIO CL INTEGRAL I",
                        "coverage_raw": "Particular",
                        "practice_raw": "Cicloespirometria",
                        "datetime_raw": "15:55",
                        "phone": "",
                        "dni": "",
                        "agenda_date": date(2026, 6, 11),
                    }
                ],
            ) as text_mock,
            patch("clinic.views.extract_drapp_rows_from_browser_ocr", return_value=browser_rows),
            patch("clinic.views.import_drapp_rows", return_value=(2, 0)) as import_mock,
        ):
            response = self.client.post(
                reverse("clinic:dashboard"),
                {
                    "action": "import_drapp",
                    "raw_text": "15:55 ORTIZ, MARTA LILIANA Particular Espirometria Centro Respiratorio Integral",
                    "ocr_lines_json": '[{"text":"15:55 ORTIZ, MARTA LILIANA","y":40}]',
                },
            )

        self.assertRedirects(response, reverse("clinic:dashboard"))
        text_mock.assert_not_called()
        self.assertEqual(import_mock.call_args[0][0], browser_rows)


class DashboardInlineUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="agenda-test", password="secret123")
        self.client.force_login(self.user)
        self.patient = Patient.objects.create(full_name="SUAREZ, MARIA JESUS", dni="10731742")
        self.encounter = Encounter.objects.create(
            patient=self.patient,
            encounter_date=date(2026, 6, 5),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_inline_time_update_persists_and_returns_normalized_value(self):
        response = self.client.post(
            reverse("clinic:dashboard"),
            {
                "action": "inline_update",
                "encounter_id": self.encounter.pk,
                "field_name": "encounter_time",
                "value": "15:30",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.encounter_time, time(15, 30))
        payload = response.json()
        self.assertEqual(payload["value"], "15:30")
        self.assertEqual(payload["encounter_time"], "15:30")

    def test_inline_time_update_accepts_compact_manual_value(self):
        response = self.client.post(
            reverse("clinic:dashboard"),
            {
                "action": "inline_update",
                "encounter_id": self.encounter.pk,
                "field_name": "encounter_time",
                "value": "1530",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.encounter_time, time(15, 30))
        self.assertEqual(response.json()["value"], "15:30")


class DoctorReviewViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="review-test", password="secret123")
        self.patient = Patient.objects.create(full_name="SIPOLLONI, FELISA", dni=None)
        self.encounter = Encounter.objects.create(
            patient=self.patient,
            encounter_date=date(2026, 6, 4),
            encounter_time=time(16, 35),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_upload_suggestion_does_not_become_medical_result(self):
        self.client.force_login(self.user)
        pdf_file = SimpleUploadedFile("felisa.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        analysis = {
            "source": "browser-pdf-text",
            "code": "RM",
            "probability": 99,
            "summary": "99% probable RM. FVC debajo del LIN/LLN.",
            "values": {
                "fvc": {"lln": 1.75, "predicted": 2.69, "best": 1.65, "percent": 61},
                "fev1": {"lln": 1.36, "predicted": 1.98, "best": 1.58, "percent": 80},
                "fev1_fvc": {"lln": 65.5, "predicted": 77.1, "best": 95.8, "percent": 124},
            },
        }

        with patch("clinic.views.build_analysis_for_uploaded_result", return_value=analysis):
            response = self.client.post(
                reverse("clinic:doctor_review_detail", args=[self.encounter.pk]),
                {
                    "pdf_file": pdf_file,
                    "respiratory_result": "",
                    "analysis_payload_json": "{}",
                },
            )

        self.assertRedirects(response, reverse("clinic:doctor_review_detail", args=[self.encounter.pk]))
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, EncounterStatus.PENDIENTE)
        self.assertEqual(self.encounter.spirometry_result.suggested_code, "RM")
        self.assertEqual(self.encounter.spirometry_result.respiratory_pattern, "")

    def test_upload_autofills_missing_document_profile_and_replaces_random_name(self):
        self.client.force_login(self.user)
        self.patient.full_name = "ASDASDAS"
        self.patient.dni = None
        self.patient.save(update_fields=["full_name", "dni", "updated_at"])
        pdf_file = SimpleUploadedFile("palermo.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        analysis = {
            "source": "browser-pdf-text",
            "code": "N",
            "probability": 99,
            "summary": "99% probable N.",
            "values": {
                "fvc": {"lln": 1.79, "predicted": 2.50, "best": 2.37, "percent": 95},
                "fev1": {"lln": 1.48, "predicted": 2.11, "best": 2.34, "percent": 111},
                "fev1_fvc": {"lln": 67.9, "predicted": 78.6, "best": 98.7, "percent": 125},
            },
            "snapshot": {
                "patient_code": "12345678",
                "dni": "12345678",
                "last_name": "MARTIN",
                "first_name": "PALERMO",
                "full_name": "MARTIN, PALERMO",
                "birth_date": date(1970, 11, 23),
                "age_reported": 23,
                "gender": "Femenino",
                "height_cm": 154,
                "weight_kg": "100",
                "bmi": "42.17",
                "ethnicity": "Caucasico",
                "smoking_status": "No fumador",
            },
        }

        with patch("clinic.views.build_analysis_for_uploaded_result", return_value=analysis):
            response = self.client.post(
                reverse("clinic:doctor_review_detail", args=[self.encounter.pk]),
                {
                    "pdf_file": pdf_file,
                    "respiratory_result": "",
                    "analysis_payload_json": "{}",
                },
            )

        self.assertRedirects(response, reverse("clinic:doctor_review_detail", args=[self.encounter.pk]))
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.full_name, "MARTIN, PALERMO")
        self.assertEqual(self.patient.dni, "12345678")
        self.assertEqual(self.patient.patient_code, "12345678")
        self.assertEqual(self.patient.last_name, "MARTIN")
        self.assertEqual(self.patient.first_name, "PALERMO")
        self.assertEqual(self.patient.birth_date, date(1970, 11, 23))
        self.assertEqual(self.patient.age_reported, 55)
        self.assertEqual(self.patient.gender, "Femenino")
        self.assertEqual(self.patient.height_cm, 154)
        self.assertEqual(str(self.patient.bmi), "42.17")

    def test_save_review_re_reads_existing_pdf_and_autofills_profile(self):
        self.client.force_login(self.user)
        Attachment.objects.create(
            encounter=self.encounter,
            file_kind=AttachmentKind.PDF_RESULTADO,
            original_name="castro.pdf",
            file="encounters/45/castro.pdf",
            mime_type="application/pdf",
            uploaded_by=self.user,
        )
        analysis = {
            "source": "server-pdf-text",
            "code": "RS",
            "probability": 99,
            "summary": "99% probable RS.",
            "values": {
                "fvc": {"lln": 1.96, "predicted": 2.90, "best": 0.68, "percent": 23},
                "fev1": {"lln": 1.62, "predicted": 2.23, "best": 0.59, "percent": 26},
                "fev1_fvc": {"lln": 66.1, "predicted": 77.7, "best": 86.8, "percent": 112},
            },
            "snapshot": {
                "patient_code": "12231324",
                "dni": "12231324",
                "last_name": "CASTRO",
                "first_name": "ARGENTINA",
                "full_name": "CASTRO, ARGENTINA",
                "birth_date": date(1955, 12, 25),
                "age_reported": 70,
                "gender": "Femenino",
                "height_cm": 165,
                "weight_kg": "63",
                "bmi": "23.14",
                "ethnicity": "Caucásico",
            },
        }

        self.patient.full_name = "CASTRO ARGENTINA"
        self.patient.dni = "12231324"
        self.patient.save(update_fields=["full_name", "dni", "updated_at"])
        with patch("clinic.views.build_analysis_for_uploaded_result", return_value=analysis):
            response = self.client.post(
                reverse("clinic:doctor_review_detail", args=[self.encounter.pk]),
                {
                    "pdf_file": "",
                    "respiratory_result": "RS",
                    "analysis_payload_json": "",
                },
            )

        self.assertRedirects(response, reverse("clinic:doctor_review_detail", args=[self.encounter.pk]))
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.gender, "Femenino")
        self.assertEqual(self.patient.birth_date, date(1955, 12, 25))
        self.assertEqual(self.patient.age_reported, 70)
        self.assertEqual(self.patient.height_cm, 165)
        self.assertEqual(str(self.patient.bmi), "23.14")


class DrappImportDeduplicationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dedupe-test", password="secret123")

    def create_encounter(self, full_name="ORUETTA, RAMONA", dni="", encounter_date=date(2026, 6, 4)):
        patient = Patient.objects.create(full_name=full_name, dni=dni or None)
        return Encounter.objects.create(
            patient=patient,
            encounter_date=encounter_date,
            encounter_time=time(15, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_skips_same_name_on_same_day_even_if_time_changes(self):
        self.create_encounter()

        created, skipped = import_drapp_rows(
            [
                {
                    "patient_name": "Oruetta, Ramona",
                    "coverage_raw": "Particular",
                    "practice_raw": "Espirometria",
                    "datetime_raw": "16:30",
                    "phone": "",
                    "dni": "",
                    "agenda_date": date(2026, 6, 4),
                }
            ],
            self.user,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(Encounter.objects.filter(encounter_date=date(2026, 6, 4)).count(), 1)

    def test_skips_same_dni_on_same_day_even_if_name_has_ocr_prefix(self):
        self.create_encounter(full_name="ORUETTA, RAMONA", dni="42999801")

        created, skipped = import_drapp_rows(
            [
                {
                    "patient_name": "O ORUETTA, RAMONA",
                    "coverage_raw": "Particular",
                    "practice_raw": "Cicloespirometria",
                    "datetime_raw": "17:00",
                    "phone": "",
                    "dni": "42.999.801",
                    "agenda_date": date(2026, 6, 4),
                }
            ],
            self.user,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(Encounter.objects.filter(patient__dni="42999801").count(), 1)

    def test_allows_same_patient_on_another_day(self):
        self.create_encounter(full_name="ORUETTA, RAMONA", dni="42999801")

        created, skipped = import_drapp_rows(
            [
                {
                    "patient_name": "ORUETTA, RAMONA",
                    "coverage_raw": "Particular",
                    "practice_raw": "Cicloespirometria",
                    "datetime_raw": "15:00",
                    "phone": "",
                    "dni": "42999801",
                    "agenda_date": date(2026, 6, 5),
                }
            ],
            self.user,
        )

        self.assertEqual(created, 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(Encounter.objects.filter(patient__dni="42999801").count(), 2)

    def test_display_uniques_existing_duplicate_encounters(self):
        patient = Patient.objects.create(full_name="O ORUETTA, RAMONA", dni="42999801")
        first = Encounter.objects.create(
            patient=patient,
            encounter_date=date(2026, 6, 4),
            encounter_time=time(15, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
        )
        Encounter.objects.create(
            patient=patient,
            encounter_date=date(2026, 6, 4),
            encounter_time=time(16, 0),
            study_type=StudyType.ESPIROMETRIA,
            coverage_type=CoverageType.MUTUAL,
            status=EncounterStatus.PENDIENTE,
        )

        unique = unique_encounters_by_patient_day(
            Encounter.objects.select_related("patient").order_by("encounter_time")
        )

        self.assertEqual(unique, [first])


class SpirometryPdfParsingTests(SimpleTestCase):
    def test_restrictive_pdf_table_is_not_called_normal(self):
        analysis = build_analysis_from_text(
            "\n".join(
                [
                    "FVC FEV1 FEV1%",
                    "Fecha de visita 04/06/2026",
                    "Cod. paciente 5999253",
                    "Apellido SIPOLLONI",
                    "Nom. FELISA",
                    "Genero Femenino",
                    "Altura, cm 164",
                    "Peso, kg 88",
                    "BMI 32,72",
                    "Parametros LLN Teor. Best %Teor. Z-score PRE #1 PRE #2 PRE #3 POST %Teor. %Cam",
                    "FVC L 1,75 2,69 1,65* 61 -1,82 1,65 1,54* 57 -7",
                    "FEV1 L 1,36 1,98 1,58* 80 -1,07 1,58 1,49* 75 -6",
                    "FEV1/FVC % 65,5 77,1 95,8* 124 2,66 95,8 96,8* 126 1",
                ]
            ),
            source="browser-pdf-text",
        )

        self.assertEqual(analysis["values"]["fvc"]["lln"], 1.75)
        self.assertEqual(analysis["values"]["fvc"]["best"], 1.65)
        self.assertEqual(analysis["values"]["fvc"]["percent"], 61)
        self.assertEqual(analysis["values"]["fev1_fvc"]["best"], 95.8)
        self.assertEqual(analysis["code"], "RM")

    def test_uses_distinct_fev1_and_ratio_lines_for_mixed_pattern(self):
        values = extract_spirometry_numbers_from_text(
            "\n".join(
                [
                    "FVC 2.50 3.20 1.80 56",
                    "FEV1 1.80 2.60 1.00 38",
                    "FEV1/FVC 70 81 55",
                ]
            )
        )
        analysis = build_spirometry_analysis(values)

        self.assertEqual(values["fev1_fvc"]["lln"], 70)
        self.assertEqual(values["fev1_fvc"]["best"], 55)
        self.assertEqual(analysis["code"], "RMSOS")

    def test_does_not_call_normal_when_key_values_are_missing(self):
        analysis = build_spirometry_analysis(
            {
                "fvc": {"lln": None, "predicted": None, "best": None, "percent": None},
                "fev1": {"lln": None, "predicted": None, "best": None, "percent": None},
                "fev1_fvc": {"lln": None, "predicted": None, "best": None, "percent": None},
            }
        )

        self.assertEqual(analysis["code"], "")
        self.assertIsNone(analysis["probability"])

    def test_rejects_physically_impossible_repeated_rows(self):
        analysis = build_spirometry_analysis(
            {
                "fvc": {"lln": 4.0, "predicted": None, "best": 16.0, "percent": 77.0},
                "fev1": {"lln": 4.0, "predicted": None, "best": 16.0, "percent": 77.0},
                "fev1_fvc": {"lln": 4.0, "predicted": None, "best": 16.0, "percent": 77.0},
            }
        )

        self.assertEqual(analysis["code"], "")
        self.assertIsNone(analysis["probability"])

    def test_reads_patient_profile_without_colons(self):
        snapshot = extract_patient_snapshot_from_text(
            "\n".join(
                [
                    "Cod. paciente 5999253",
                    "Apellido SIPOLLONI",
                    "Nom. FELISA",
                    "Fecha de nacimien 16/10/1949",
                    "Edad 76",
                    "Genero Femenino",
                    "Altura, cm 164",
                    "Peso, kg 88",
                    "BMI 32,72",
                ]
            )
        )

        self.assertEqual(snapshot["patient_code"], "5999253")
        self.assertEqual(snapshot["full_name"], "SIPOLLONI, FELISA")
        self.assertEqual(snapshot["gender"], "Femenino")
        self.assertEqual(snapshot["height_cm"], 164)

    def test_reads_patient_profile_when_pdf_joins_left_and_right_columns(self):
        snapshot = extract_patient_snapshot_from_text(
            "\n".join(
                [
                    "Fecha de visita 04/06/2026",
                    "Cod. paciente 5999253 Edad 76",
                    "Apellido SIPOLLONI Genero Femenino",
                    "Nom. FELISA Altura, cm 164",
                    "Fecha de nacimien 16/10/1949 Peso, kg 88",
                    "Grupo etnico Caucasico BMI 32,72",
                    "Fuma Paquete-ano",
                ]
            )
        )

        self.assertEqual(snapshot["patient_code"], "5999253")
        self.assertEqual(snapshot["dni"], "5999253")
        self.assertEqual(snapshot["full_name"], "SIPOLLONI, FELISA")
        self.assertEqual(snapshot["birth_date"], date(1949, 10, 16))
        self.assertEqual(snapshot["age_reported"], 76)
        self.assertEqual(snapshot["gender"], "Femenino")
        self.assertEqual(snapshot["height_cm"], 164)
        self.assertEqual(snapshot["weight_kg"], 88)
        self.assertEqual(str(snapshot["bmi"]), "32.72")
        self.assertEqual(snapshot["ethnicity"], "Caucásico")

    def test_reads_vertical_patient_profile_block_and_computes_age_from_birth_date(self):
        snapshot = extract_patient_snapshot_from_text(
            "\n".join(
                [
                    "Fecha de visita 04/06/2026",
                    "Cod. paciente 12345678 Edad 23",
                    "Apellido",
                    "Nom.",
                    "Fecha de nacimien",
                    "Grupo etnico",
                    "Fuma",
                    "Grupo pacientes",
                    "MARTIN",
                    "PALERMO",
                    "23/11/1970",
                    "Caucasico",
                    "No fumador",
                    "Genero Femenino",
                    "Altura, cm 154",
                    "Peso:, kg 100",
                    "BMI 42,17",
                    "Paquete-ano",
                ]
            )
        )
        snapshot = snapshot_with_computed_age(snapshot, date(2026, 6, 5))

        self.assertEqual(snapshot["patient_code"], "12345678")
        self.assertEqual(snapshot["dni"], "12345678")
        self.assertEqual(snapshot["last_name"], "MARTIN")
        self.assertEqual(snapshot["first_name"], "PALERMO")
        self.assertEqual(snapshot["full_name"], "MARTIN, PALERMO")
        self.assertEqual(snapshot["birth_date"], date(1970, 11, 23))
        self.assertEqual(snapshot["age_reported"], 55)
        self.assertEqual(snapshot["gender"], "Femenino")
        self.assertEqual(snapshot["height_cm"], 154)
        self.assertEqual(snapshot["weight_kg"], 100)
        self.assertEqual(str(snapshot["bmi"]), "42.17")
        self.assertEqual(snapshot["ethnicity"], "Caucásico")
        self.assertEqual(snapshot["smoking_status"], "No fumador")


class PrintReportViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="print-test", password="secret123")
        self.client.force_login(self.user)
        self.patient = Patient.objects.create(full_name="FONTANARI ALICIA NOEMI", dni="129")
        self.encounter = Encounter.objects.create(
            patient=self.patient,
            encounter_date=date(2026, 6, 4),
            encounter_time=time(15, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.MUTUAL,
            status=EncounterStatus.REVISADA,
            created_by=self.user,
            updated_by=self.user,
        )
        VitalSigns.objects.create(
            encounter=self.encounter,
            so2_rest=88,
            fc_rest=64,
            so2_post=65,
            fc_post=117,
        )
        WalkTest.objects.create(
            encounter=self.encounter,
            distance_meters=100,
            completed=False,
            stopped=False,
            symptoms=False,
            borg_final=1,
        )
        SpirometryResult.objects.create(
            encounter=self.encounter,
            respiratory_pattern="Restrictivo",
            restriction_grade="Moderada",
        )

    def test_mutual_patient_print_includes_mutual_packet(self):
        response = self.client.get(reverse("clinic:encounter_print", args=[self.encounter.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Capacidad Vital Lenta", html)
        self.assertIn("PRUEBA DE LOS 6 Y 12 MINUTOS", html)
        self.assertIn("Resultado Espirometria Computarizada", html)
        self.assertIn("Moderadamente reducida", html)
        self.assertIn("dni-value", html)
        self.assertIn("PRUEBA NO NORMAL", html)
        self.assertNotIn("desaturacion al esfuerzo", html.lower())

    def test_daily_print_uses_same_mutual_packet(self):
        with patch("clinic.views.timezone.localdate", return_value=date(2026, 6, 4)):
            response = self.client.get(reverse("clinic:daily_print"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("@page { size: Letter; margin: 0; }", html)
        self.assertIn("sheet-pdf", html)
        self.assertIn("Capacidad Vital Lenta", html)
        self.assertIn("Moderadamente reducida", html)
        self.assertIn("PRUEBA NO NORMAL", html)


class PatientHistoryActionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="history-test", password="secret123")
        self.client.force_login(self.user)
        self.patient = Patient.objects.create(full_name="TEST, PACIENTE", dni="12345678")
        self.encounter = Encounter.objects.create(
            patient=self.patient,
            encounter_date=date(2026, 6, 11),
            encounter_time=time(16, 30),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )
        VitalSigns.objects.create(encounter=self.encounter, so2_rest=88, fc_rest=64, so2_post=66, fc_post=117)
        WalkTest.objects.create(encounter=self.encounter, distance_meters=100, completed=False, stopped=False, symptoms=False, borg_final=1)

    def test_patient_detail_shows_walk_assessment_and_edit_action(self):
        response = self.client.get(reverse("clinic:patient_detail", args=[self.patient.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("PRUEBA NO NORMAL", html)
        self.assertIn("Editar atencion", html)
        self.assertIn("Subir documento", html)

    def test_patient_detail_can_upload_document_to_specific_encounter(self):
        upload = SimpleUploadedFile(
            "otro-estudio.pdf",
            b"%PDF-1.4 extra",
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("clinic:patient_detail", args=[self.patient.pk]),
            {
                "action": "upload_patient_document",
                "encounter": self.encounter.pk,
                "file_kind": AttachmentKind.PDF_RESULTADO,
                "file": upload,
            },
        )

        self.assertRedirects(response, reverse("clinic:patient_detail", args=[self.patient.pk]))
        self.assertTrue(
            Attachment.objects.filter(encounter=self.encounter, original_name="otro-estudio.pdf").exists()
        )

    def test_encounter_edit_can_return_to_patient_history(self):
        response = self.client.post(
            reverse("clinic:encounter_edit", args=[self.encounter.pk]),
            {
                "patient_name": "TEST, PACIENTE",
                "patient_dni": "12345678",
                "encounter_time": "16:30",
                "study_type": "Ciclometria",
                "coverage_type": "Particular",
                "referring_physician": "",
                "so2_rest": 90,
                "fc_rest": 70,
                "so2_post": 85,
                "fc_post": 120,
                "distance_meters": 100,
                "completed": "on",
                "stopped": "",
                "symptoms": "",
                "borg_final": 1,
                "respiratory_result": "N",
                "attended": "",
                "no_show": "",
                "return_to": reverse("clinic:patient_detail", args=[self.patient.pk]),
            },
        )

        self.assertRedirects(response, reverse("clinic:patient_detail", args=[self.patient.pk]))


class CalendarEditingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="calendar-edit", password="secret123")
        self.client.force_login(self.user)
        self.patient = Patient.objects.create(full_name="ARRIETA, LIDIA", dni="17124122")
        self.encounter = Encounter.objects.create(
            patient=self.patient,
            encounter_date=date(2026, 6, 12),
            encounter_time=time(10, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_calendar_allows_updating_coverage(self):
        response = self.client.post(
            reverse("clinic:calendar"),
            {
                "action": "update_encounter_field",
                "encounter_id": self.encounter.pk,
                "field_name": "coverage_type",
                "value": "Mutual",
                "month": "2026-06",
                "date": "2026-06-12",
            },
        )

        self.assertRedirects(response, f"{reverse('clinic:calendar')}?month=2026-06&date=2026-06-12")
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.coverage_type, CoverageType.MUTUAL)

    def test_calendar_detail_renders_inline_edit_selects(self):
        response = self.client.get(f"{reverse('clinic:calendar')}?month=2026-06&date=2026-06-12")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="field_name" value="coverage_type"', html)
        self.assertIn('name="field_name" value="study_type"', html)
        self.assertIn("Editar ficha", html)


class StatisticsMonthNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="stats-months", password="secret123")
        self.client.force_login(self.user)
        patient = Patient.objects.create(full_name="MES, PRUEBA", dni="11111111")
        Encounter.objects.create(
            patient=patient,
            encounter_date=date(2026, 5, 20),
            encounter_time=time(9, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.MUTUAL,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )
        Encounter.objects.create(
            patient=patient,
            encounter_date=date(2026, 6, 10),
            encounter_time=time(10, 0),
            study_type=StudyType.CICLOMETRIA,
            coverage_type=CoverageType.PARTICULAR,
            status=EncounterStatus.PENDIENTE,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_statistics_allows_browsing_previous_month(self):
        response = self.client.get(f"{reverse('clinic:statistics')}?month=2026-05")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("mayo 2026", html.lower())
        self.assertIn("Mes elegido", html)

    def test_statistics_caps_future_month_to_current(self):
        response = self.client.get(f"{reverse('clinic:statistics')}?month=2099-01")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Mes actual", html)
