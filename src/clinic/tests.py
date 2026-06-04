from datetime import date

from django.test import SimpleTestCase

from .views import extract_drapp_rows_from_ocr_lines


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
