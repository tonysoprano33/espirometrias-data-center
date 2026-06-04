from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import CoverageType, Encounter, EncounterStatus, Patient, StudyType
from .pdf_intake import build_spirometry_analysis, extract_spirometry_numbers_from_text
from .views import (
    extract_drapp_rows_from_ocr_lines,
    extract_drapp_rows_from_text,
    import_drapp_rows,
    unique_encounters_by_patient_day,
)


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
