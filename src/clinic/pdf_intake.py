import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path

from django.conf import settings
import pypdfium2 as pdfium

try:
    from rapidocr_onnxruntime import RapidOCR
    RAPIDOCR_IMPORT_ERROR = None
except Exception as error:  # pragma: no cover - fallback defensivo
    RapidOCR = None
    RAPIDOCR_IMPORT_ERROR = error


OCR_ROW_TOLERANCE = 18
SUGGESTION_PROBABILITY_CAP = 99


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
        detail = f" Detalle: {RAPIDOCR_IMPORT_ERROR}" if RAPIDOCR_IMPORT_ERROR else ""
        raise RuntimeError(f"No se pudo cargar el motor OCR para leer imagenes automaticamente.{detail}")
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


def extract_pdf_text_content(pdf_path: str) -> str:
    document = pdfium.PdfDocument(str(pdf_path))
    collected_pages = []
    try:
        for page_index in range(len(document)):
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    page_text = collapse_spaces(text_page.get_text_range())
                finally:
                    text_page.close()
            finally:
                page.close()
            if page_text:
                collected_pages.append(page_text)
    finally:
        document.close()
    return "\n".join(collected_pages).strip()


def build_text_from_browser_payload(raw_payload) -> tuple[str, str]:
    if not raw_payload:
        return "", ""
    if isinstance(raw_payload, str):
        payload = json.loads(raw_payload)
    else:
        payload = raw_payload

    if isinstance(payload, dict):
        source = collapse_spaces(payload.get("source", "browser"))
        lines = payload.get("lines") or []
        ordered_lines = []
        for item in lines:
            if not isinstance(item, dict):
                continue
            line_text = collapse_spaces(item.get("text", ""))
            if not line_text:
                continue
            ordered_lines.append(
                (
                    int(item.get("page", 1) or 1),
                    float(item.get("y", 0) or 0),
                    line_text,
                )
            )
        ordered_lines.sort(key=lambda value: (value[0], value[1], value[2]))
        if ordered_lines:
            return "\n".join(text for _, _, text in ordered_lines), source

        text = str(payload.get("text", "") or "")
        if text:
            return "\n".join(split_text_lines(text)), source

    return collapse_spaces(str(payload)), "browser"


def split_text_lines(raw_text: str) -> list[str]:
    return [collapse_spaces(line) for line in str(raw_text or "").splitlines() if collapse_spaces(line)]


def extract_line_for_labels(raw_text: str, labels: list[str]) -> str:
    normalized_labels = [normalize_for_match(label) for label in labels]
    for line in split_text_lines(raw_text):
        normalized_line = normalize_for_match(line)
        if any(label in normalized_line for label in normalized_labels):
            return line
    normalized_text = normalize_for_match(raw_text)
    if not normalized_text:
        return ""
    for label in normalized_labels:
        match = re.search(label + r"(.{0,180})", normalized_text)
        if match:
            return match.group(0)
    return ""


def extract_numbers_from_line(line: str) -> list[float]:
    sanitized_line = re.sub(r"(?i)\bFEV1/FVC\b", " ", str(line or ""))
    sanitized_line = re.sub(r"(?i)\bFEV1\b", " ", sanitized_line)
    sanitized_line = re.sub(r"(?i)\bFVC\b", " ", sanitized_line)
    return [
        value
        for value in (parse_measurement_number(token) for token in re.findall(r"\d+(?:[.,]\d+)?", sanitized_line))
        if value is not None
    ]


def infer_measurement_values_from_numbers(numbers: list[float]) -> dict:
    if not numbers:
        return {"lln": None, "predicted": None, "best": None, "percent": None}

    values = {"lln": None, "predicted": None, "best": None, "percent": None}
    decimal_candidates = [number for number in numbers if number < 20]
    percent_candidates = [number for number in numbers if 20 <= number <= 160]

    if len(decimal_candidates) >= 1:
        values["lln"] = decimal_candidates[0]
    if len(decimal_candidates) >= 2:
        values["predicted"] = decimal_candidates[1]
    if len(decimal_candidates) >= 3:
        values["best"] = decimal_candidates[2]
    elif len(decimal_candidates) == 2:
        values["best"] = decimal_candidates[1]

    if percent_candidates:
        values["percent"] = percent_candidates[-1]

    if values["percent"] is None and values["predicted"] and values["best"]:
        values["percent"] = round((values["best"] / values["predicted"]) * 100, 1)
    return values


def extract_spirometry_numbers_from_text(raw_text: str) -> dict:
    fvc_line = extract_line_for_labels(raw_text, ["FVC"])
    ratio_line = extract_line_for_labels(raw_text, ["FEV1/FVC", "FEV1FVC"])
    fev1_line = extract_line_for_labels(raw_text, ["FEV1"])

    fvc = infer_measurement_values_from_numbers(extract_numbers_from_line(fvc_line))
    fev1 = infer_measurement_values_from_numbers(extract_numbers_from_line(fev1_line))
    ratio = infer_measurement_values_from_numbers(extract_numbers_from_line(ratio_line))

    if ratio.get("best") is None and ratio.get("percent") is not None and ratio.get("predicted") is None:
        ratio["best"] = ratio["percent"]
        ratio["percent"] = None

    return {
        "fvc": fvc,
        "fev1": fev1,
        "fev1_fvc": ratio,
    }


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
    text_values = extract_spirometry_numbers_from_text(extract_pdf_text_content(pdf_path))
    enough_text_data = any(
        text_values.get(key, {}).get("best") is not None or text_values.get(key, {}).get("percent") is not None
        for key in ["fvc", "fev1", "fev1_fvc"]
    )
    if enough_text_data:
        return text_values

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


def build_suggestion_probability(values: dict, code: str) -> int:
    score = 40
    fvc = values.get("fvc", {})
    fev1 = values.get("fev1", {})
    ratio = values.get("fev1_fvc", {})

    if ratio.get("best") is not None:
        score += 18
    if ratio.get("lln") is not None:
        score += 14
    if fvc.get("best") is not None:
        score += 12
    if fvc.get("lln") is not None or fvc.get("percent") is not None:
        score += 10
    if fev1.get("percent") is not None:
        score += 8
    if fev1.get("best") is not None:
        score += 4
    if code == "N":
        score += 6
    return min(score, SUGGESTION_PROBABILITY_CAP)


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
        code = "R{}O{}".format(restriction_grade or "L", obstruction_grade or "L")
        reason = "Relacion FEV1/FVC debajo del LLN y FVC reducida."
        return code, reason, build_suggestion_probability(values, code)
    if has_obstruction:
        code = "O{}".format(obstruction_grade or "L")
        reason = "Relacion FEV1/FVC debajo del LLN."
        return code, reason, build_suggestion_probability(values, code)
    if has_restriction:
        code = "R{}".format(restriction_grade or "L")
        reason = "FVC debajo del LLN o menor al 80% del teorico."
        return code, reason, build_suggestion_probability(values, code)
    code = "N"
    reason = "FEV1/FVC y FVC no sugieren alteracion segun los valores leidos."
    return code, reason, build_suggestion_probability(values, code)


def build_spirometry_analysis(values: dict):
    code, reason, probability = suggest_result_code_from_spirometry(values)
    probability_phrase = f"{probability}% probable {code}"
    return {
        "code": code,
        "reason": reason,
        "probability": probability,
        "probability_phrase": probability_phrase,
        "summary": f"{probability_phrase}. {reason}",
        "values": values,
    }


def build_spirometry_suggestion_from_pdf(pdf_path: str, attachment_id: int | None = None):
    values = extract_spirometry_numbers_from_pdf(pdf_path, attachment_id=attachment_id)
    return build_spirometry_analysis(values)


def parse_date(text: str):
    raw_value = collapse_spaces(text)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    return None


def extract_patient_snapshot_from_text(raw_text: str):
    text_lines = split_text_lines(raw_text)
    compact_text = " ".join(text_lines)
    if not compact_text:
        return {}

    def find_value(patterns: list[str]):
        for line in text_lines:
            normalized_line = line.casefold()
            for pattern in patterns:
                if pattern.startswith("line:"):
                    label = pattern.split(":", 1)[1].casefold()
                    if normalized_line.startswith(label):
                        separator_match = re.split(r"[:\-]\s*", line, maxsplit=1)
                        if len(separator_match) == 2:
                            return collapse_spaces(separator_match[1])
        for pattern in patterns:
            if pattern.startswith("line:"):
                continue
            match = re.search(pattern, compact_text, flags=re.IGNORECASE)
            if match:
                return collapse_spaces(match.group(1))
        return ""

    snapshot = {
        "patient_code": find_value(
            [
                "line:codigo de paciente",
                "line:cod. paciente",
                r"Cod(?:igo|\.)?\s+de?\s*Paciente[:\s]+([A-Z0-9.\-]{6,})",
            ]
        ),
        "dni": find_value(["line:dni", "line:documento", r"\bDNI[:\s]+([0-9.\-]{6,})", r"\bDocumento[:\s]+([0-9.\-]{6,})"]),
        "last_name": find_value(["line:apellido", r"Apellido[:\s]+([A-ZÁÉÍÓÚÑ' ]{2,})"]),
        "first_name": find_value(["line:nombre", r"Nombre[:\s]+([A-ZÁÉÍÓÚÑ' ]{2,})"]),
        "birth_date": parse_date(find_value(["line:fecha de nac", r"Fecha\s+de\s+Nac(?:imiento)?[:\s]+([0-9/\-]{8,10})"])),
        "age_reported": parse_integer(find_value(["line:edad", r"Edad[:\s]+([0-9]{1,3})"])),
        "gender": find_value(["line:genero", "line:sexo", r"Genero[:\s]+([A-ZÁÉÍÓÚÑ ]{3,})", r"Sexo[:\s]+([A-ZÁÉÍÓÚÑ ]{3,})"]),
        "height_cm": parse_integer(find_value(["line:altura", r"Altura(?:\s*cm)?[:\s]+([0-9]{2,3})"])),
        "weight_kg": parse_decimal(find_value(["line:peso", r"Peso(?:\s*kg)?[:\s]+([0-9.,]{2,6})"])),
        "bmi": parse_decimal(find_value(["line:bmi", r"\bBMI[:\s]+([0-9.,]{2,6})"])),
        "ethnicity": find_value(["line:grupo etnico", r"Grupo\s+Etnico[:\s]+([A-ZÁÉÍÓÚÑ ]{3,})"]),
        "smoking_status": find_value(["line:fuma", r"Fuma[:\s]+([A-ZÁÉÍÓÚÑ ]{2,})"]),
        "pack_years": parse_decimal(find_value(["line:paquete año", "line:paquete anio", r"Paquete(?:\s*[- ]?\s*)?An(?:io|o)[:\s]+([0-9.,]{1,6})"])),
        "patient_group": find_value(["line:grupo paciente", r"Grupo\s+Paciente[s]?[:\s]+([A-ZÁÉÍÓÚÑ ]{3,})"]),
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


def extract_patient_snapshot_from_pdf(pdf_path: str, attachment_id: int | None = None):
    text_snapshot = extract_patient_snapshot_from_text(extract_pdf_text_content(pdf_path))
    if text_snapshot and any(text_snapshot.get(key) for key in ["patient_code", "dni", "full_name"]):
        return text_snapshot

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


def build_analysis_from_text(raw_text: str, source: str = "text"):
    text = "\n".join(split_text_lines(raw_text))
    if not text:
        return {}
    values = extract_spirometry_numbers_from_text(text)
    has_values = any(values.get(key, {}).get("best") is not None or values.get(key, {}).get("percent") is not None for key in values)
    snapshot = extract_patient_snapshot_from_text(text)
    analysis = {
        "source": source,
        "text": text,
        "snapshot": snapshot,
        "values": values,
    }
    if has_values:
        analysis.update(build_spirometry_analysis(values))
    return analysis


def build_analysis_from_browser_payload(raw_payload):
    text, source = build_text_from_browser_payload(raw_payload)
    return build_analysis_from_text(text, source=source or "browser")


def apply_snapshot_to_encounter_patient(encounter, snapshot: dict):
    patient = encounter.patient
    target_patient = find_existing_patient_for_snapshot(patient, snapshot) or patient
    changed_fields = []

    if target_patient.pk != patient.pk:
        encounter.patient = target_patient
        encounter.save(update_fields=["patient", "updated_at"])
        changed_fields.append("historia_clinica_unificada")

    changed_fields.extend(apply_snapshot_to_patient(target_patient, snapshot))
    return target_patient, sorted(set(changed_fields))


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
