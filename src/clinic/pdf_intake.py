import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from django.conf import settings
import pypdfium2 as pdfium

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover - fallback defensivo
    RapidOCR = None


OCR_ROW_TOLERANCE = 18


def collapse_spaces(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "", ascii_value.upper())


def looks_like_profile_data(patient) -> bool:
    return any(
        [
            bool(patient.patient_code),
            bool(patient.last_name),
            bool(patient.first_name),
            bool(patient.dni),
            patient.birth_date is not None,
            patient.age_reported is not None,
            bool(patient.gender),
            bool(patient.ethnicity),
            bool(patient.smoking_status),
            bool(patient.patient_group),
            patient.height_cm is not None,
            patient.weight_kg is not None,
            patient.bmi is not None,
            patient.pack_years is not None,
        ]
    )


@lru_cache(maxsize=1)
def get_ocr_engine():
    if RapidOCR is None:
        raise RuntimeError("Falta instalar rapidocr_onnxruntime para leer PDFs automaticamente.")
    return RapidOCR()


def ensure_first_page_preview(pdf_path: str, attachment_id: int | None = None) -> Path:
    output_dir_name = f"attachment_{attachment_id}" if attachment_id else "adhoc"
    preview_dir = Path(settings.MEDIA_ROOT) / "previews" / output_dir_name
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "page-1.png"
    if preview_path.exists():
        return preview_path

    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[0]
        try:
            bitmap = page.render(scale=2.4)
            image = bitmap.to_pil()
            image.save(preview_path)
        finally:
            page.close()
    finally:
        document.close()
    return preview_path


def ensure_pdf_preview_pages(pdf_path: str, attachment_id: int | None = None) -> list[Path]:
    output_dir_name = f"attachment_{attachment_id}" if attachment_id else "adhoc"
    preview_dir = Path(settings.MEDIA_ROOT) / "previews" / output_dir_name
    preview_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(preview_dir.glob("page-*.png"))
    if existing:
        return existing

    document = pdfium.PdfDocument(str(pdf_path))
    try:
        for page_index in range(len(document)):
            page = document[page_index]
            try:
                bitmap = page.render(scale=2.4)
                image = bitmap.to_pil()
                image.save(preview_dir / f"page-{page_index + 1}.png")
            finally:
                page.close()
    finally:
        document.close()
    return sorted(preview_dir.glob("page-*.png"))


def ocr_items_from_pdf(pdf_path: str, attachment_id: int | None = None):
    preview_path = ensure_first_page_preview(pdf_path, attachment_id=attachment_id)
    result, _ = get_ocr_engine()(str(preview_path))
    items = []
    for box, text, score in result or []:
        x = sum(point[0] for point in box) / 4
        y = sum(point[1] for point in box) / 4
        cleaned_text = collapse_spaces(text)
        items.append(
            {
                "text": cleaned_text,
                "norm": normalize_for_match(cleaned_text),
                "score": float(score or 0),
                "x": float(x),
                "y": float(y),
            }
        )
    items.sort(key=lambda item: (item["y"], item["x"]))
    return items


def find_first_text(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None


def value_to_right(items, label_matchers, min_gap: int = 20, min_x=None, max_x=None):
    labels = [
        item
        for item in items
        if any(matcher in item["norm"] for matcher in label_matchers)
    ]
    if not labels:
        return ""

    label = labels[0]
    same_row = [
        item
        for item in items
        if abs(item["y"] - label["y"]) <= OCR_ROW_TOLERANCE and item["x"] > label["x"] + min_gap
    ]
    if min_x is not None:
        same_row = [item for item in same_row if item["x"] >= min_x]
    if max_x is not None:
        same_row = [item for item in same_row if item["x"] <= max_x]
    if not same_row:
        return ""
    same_row.sort(key=lambda item: item["x"])
    return collapse_spaces(" ".join(item["text"] for item in same_row))


def parse_integer(text: str):
    digits = re.findall(r"\d+", str(text or ""))
    if not digits:
        return None
    try:
        return int(digits[0])
    except ValueError:
        return None


def parse_decimal(text: str):
    match = re.search(r"\d+(?:[.,]\d+)?", str(text or ""))
    if not match:
        return None
    value = match.group(0).replace(",", ".")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def parse_measurement_number(text: str):
    cleaned = str(text or "").strip().replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    return value


def row_items_for_parameter(items, parameter_norm: str):
    parameter = find_first_text(items, lambda item: item["norm"] == parameter_norm and item["y"] > 1100)
    if not parameter:
        return []
    return [
        item
        for item in items
        if abs(item["y"] - parameter["y"]) <= OCR_ROW_TOLERANCE and item["x"] > parameter["x"] + 40
    ]


def value_near_column(row_items, target_x: int, min_value=None, max_value=None, max_distance: int = 70):
    candidates = []
    for item in row_items:
        number = parse_measurement_number(item["text"])
        if number is None:
            continue
        if abs(item["x"] - target_x) > max_distance:
            continue
        if min_value is not None and number < min_value:
            continue
        if max_value is not None and number > max_value:
            continue
        candidates.append((abs(item["x"] - target_x), number))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def spirometry_grade_from_percent(percent_value):
    if percent_value is None:
        return ""
    if percent_value >= 70:
        return "L"
    if percent_value >= 60:
        return "M"
    if percent_value >= 50:
        return "MS"
    return "S"


def extract_spirometry_numbers_from_pdf(pdf_path: str, attachment_id: int | None = None):
    items = ocr_items_from_pdf(pdf_path, attachment_id=attachment_id)
    rows = {
        "fvc": row_items_for_parameter(items, "FVC"),
        "fev1": row_items_for_parameter(items, "FEV1"),
        "fev1_fvc": row_items_for_parameter(items, "FEV1FVC"),
    }

    fvc_predicted = value_near_column(rows["fvc"], 436, 0.3, 8)
    fvc_best = value_near_column(rows["fvc"], 529, 0.3, 8)
    fvc_lln = value_near_column(rows["fvc"], 338, 0.3, 8)
    fvc_percent = value_near_column(rows["fvc"], 634, 20, 160)
    if fvc_percent is None and fvc_predicted and fvc_best:
        fvc_percent = round((fvc_best / fvc_predicted) * 100, 1)

    fev1_predicted = value_near_column(rows["fev1"], 436, 0.3, 8)
    fev1_best = value_near_column(rows["fev1"], 529, 0.3, 8)
    fev1_lln = value_near_column(rows["fev1"], 338, 0.3, 8)
    fev1_percent = value_near_column(rows["fev1"], 634, 20, 160)
    if fev1_percent is None and fev1_predicted and fev1_best:
        fev1_percent = round((fev1_best / fev1_predicted) * 100, 1)

    ratio_predicted = value_near_column(rows["fev1_fvc"], 436, 20, 120)
    ratio_best = value_near_column(rows["fev1_fvc"], 529, 20, 120)
    ratio_lln = value_near_column(rows["fev1_fvc"], 338, 20, 120)
    ratio_percent = value_near_column(rows["fev1_fvc"], 634, 20, 160)
    if ratio_percent is None and ratio_predicted and ratio_best:
        ratio_percent = round((ratio_best / ratio_predicted) * 100, 1)

    return {
        "fvc": {"lln": fvc_lln, "predicted": fvc_predicted, "best": fvc_best, "percent": fvc_percent},
        "fev1": {"lln": fev1_lln, "predicted": fev1_predicted, "best": fev1_best, "percent": fev1_percent},
        "fev1_fvc": {
            "lln": ratio_lln,
            "predicted": ratio_predicted,
            "best": ratio_best,
            "percent": ratio_percent,
        },
    }


def suggest_result_code_from_spirometry(values: dict):
    fvc = values.get("fvc", {})
    fev1 = values.get("fev1", {})
    ratio = values.get("fev1_fvc", {})

    ratio_best = ratio.get("best")
    ratio_lln = ratio.get("lln")
    fvc_best = fvc.get("best")
    fvc_lln = fvc.get("lln")
    fvc_percent = fvc.get("percent")
    fev1_percent = fev1.get("percent")

    has_obstruction = bool(ratio_best is not None and ratio_lln is not None and ratio_best < ratio_lln)
    has_restriction = False
    if fvc_best is not None and fvc_lln is not None:
        has_restriction = fvc_best < fvc_lln
    elif fvc_percent is not None:
        has_restriction = fvc_percent < 80

    obstruction_grade = spirometry_grade_from_percent(fev1_percent)
    restriction_grade = spirometry_grade_from_percent(fvc_percent)
    if has_obstruction and has_restriction:
        return "R{}O{}".format(restriction_grade or "L", obstruction_grade or "L"), (
            "Relacion FEV1/FVC debajo del LLN y FVC reducida."
        )
    if has_obstruction:
        return "O{}".format(obstruction_grade or "L"), "Relacion FEV1/FVC debajo del LLN."
    if has_restriction:
        return "R{}".format(restriction_grade or "L"), "FVC debajo del LLN o menor al 80% del teorico."
    return "N", "FEV1/FVC y FVC no sugieren alteracion segun los valores leidos."


def build_spirometry_suggestion_from_pdf(pdf_path: str, attachment_id: int | None = None):
    values = extract_spirometry_numbers_from_pdf(pdf_path, attachment_id=attachment_id)
    code, reason = suggest_result_code_from_spirometry(values)
    return {
        "code": code,
        "reason": reason,
        "values": values,
    }


def parse_date(text: str):
    raw_value = collapse_spaces(text)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    return None


def extract_patient_snapshot_from_pdf(pdf_path: str, attachment_id: int | None = None):
    items = ocr_items_from_pdf(pdf_path, attachment_id=attachment_id)
    if not items:
        return {}

    patient_code = ""
    patient_code_item = find_first_text(items, lambda item: "CODPACIENTE" in item["norm"])
    if patient_code_item:
        code_match = re.search(r"(\d{6,})", patient_code_item["text"])
        if code_match:
            patient_code = code_match.group(1)

    gender_item = find_first_text(
        items,
        lambda item: item["norm"] in {"FEMENINO", "MASCULINO", "MUJER", "HOMBRE"},
    )

    snapshot = {
        "patient_code": patient_code,
        "dni": patient_code,
        "last_name": value_to_right(items, ["APELLIDO"], max_x=1050),
        "first_name": value_to_right(items, ["NOM"], max_x=1050),
        "birth_date": parse_date(value_to_right(items, ["FECHADENAC"], max_x=1050)),
        "age_reported": parse_integer(value_to_right(items, ["EDAD"], min_x=1200)),
        "gender": gender_item["text"] if gender_item else "",
        "height_cm": parse_integer(value_to_right(items, ["ALTURACM"], min_x=1200)),
        "weight_kg": parse_decimal(value_to_right(items, ["PESOKG"], min_x=1200)),
        "bmi": parse_decimal(value_to_right(items, ["BMI"], min_x=1200)),
        "ethnicity": value_to_right(items, ["GRUPOETNICO"], max_x=1050),
        "smoking_status": value_to_right(items, ["FUMA"], max_x=1050),
        "pack_years": parse_decimal(value_to_right(items, ["PAQUETEAFIO", "PAQUETEANO"], min_x=1200)),
        "patient_group": value_to_right(items, ["GRUPOPACIENTES"], max_x=1050),
    }

    if snapshot["last_name"] and snapshot["first_name"]:
        snapshot["full_name"] = f"{snapshot['last_name']}, {snapshot['first_name']}"
    elif snapshot["last_name"]:
        snapshot["full_name"] = snapshot["last_name"]
    elif snapshot["first_name"]:
        snapshot["full_name"] = snapshot["first_name"]
    else:
        snapshot["full_name"] = ""

    return snapshot


def apply_snapshot_to_patient(patient, snapshot: dict):
    if not snapshot:
        return []

    changed_fields = []
    for field_name in [
        "patient_code",
        "last_name",
        "first_name",
        "birth_date",
        "age_reported",
        "gender",
        "height_cm",
        "weight_kg",
        "bmi",
        "ethnicity",
        "smoking_status",
        "pack_years",
        "patient_group",
    ]:
        value = snapshot.get(field_name)
        if value in [None, ""]:
            continue
        if getattr(patient, field_name) != value:
            setattr(patient, field_name, value)
            changed_fields.append(field_name)

    extracted_dni = snapshot.get("dni")
    duplicate_dni_exists = False
    if extracted_dni:
        duplicate_dni_exists = patient.__class__.objects.filter(dni=extracted_dni).exclude(pk=patient.pk).exists()
    if extracted_dni and not duplicate_dni_exists:
        if patient.dni != extracted_dni:
            patient.dni = extracted_dni
            changed_fields.append("dni")

    extracted_full_name = snapshot.get("full_name")
    if extracted_full_name and patient.full_name != extracted_full_name:
        patient.full_name = extracted_full_name
        changed_fields.append("full_name")

    if changed_fields:
        patient.save(update_fields=sorted(set(changed_fields + ["updated_at"])))
    return sorted(set(changed_fields))


def find_existing_patient_for_snapshot(current_patient, snapshot: dict):
    from .models import Patient

    if not snapshot:
        return None

    extracted_dni = snapshot.get("dni")
    if extracted_dni:
        existing_patient = Patient.objects.filter(dni=extracted_dni).exclude(pk=current_patient.pk).first()
        if existing_patient:
            return existing_patient

    patient_code = snapshot.get("patient_code")
    if patient_code:
        existing_patient = Patient.objects.filter(patient_code=patient_code).exclude(pk=current_patient.pk).first()
        if existing_patient:
            return existing_patient

    return None


def ingest_pdf_attachment_into_patient(attachment):
    if not attachment or not getattr(attachment, "file", None):
        return {}, []
    snapshot = extract_patient_snapshot_from_pdf(attachment.file.path, attachment_id=attachment.pk)
    encounter = attachment.encounter
    patient = encounter.patient
    target_patient = find_existing_patient_for_snapshot(patient, snapshot) or patient
    changed_fields = []

    if target_patient.pk != patient.pk:
        encounter.patient = target_patient
        encounter.save(update_fields=["patient", "updated_at"])
        attachment.encounter = encounter
        changed_fields.append("historia_clinica_unificada")

    changed_fields.extend(apply_snapshot_to_patient(target_patient, snapshot))
    return snapshot, changed_fields
