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
SUGGESTION_PROBABILITY_CAP = 90


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
                    raw_page_text = str(text_page.get_text_range() or "")
                    page_text = "\n".join(
                        collapse_spaces(line)
                        for line in raw_page_text.splitlines()
                        if collapse_spaces(line)
                    )
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


def line_matches_spirometry_label(line: str, label: str) -> bool:
    text = str(line or "")
    normalized = normalize_for_match(text)
    if label == "FEV1/FVC":
        return bool(re.search(r"\bFEV1\s*/?\s*FVC\b", text, flags=re.IGNORECASE)) or "FEV1FVC" in normalized
    if label == "FEV1":
        if re.search(r"\bFEV1\s*/?\s*FVC\b|\bFEV1\s*/?\s*VC\b|\bFEV1\s*%", text, flags=re.IGNORECASE):
            return False
        return bool(re.search(r"\bFEV1\b", text, flags=re.IGNORECASE)) or normalized.startswith("FEV1")
    if label == "FVC":
        return bool(re.search(r"\bFVC\b", text, flags=re.IGNORECASE)) or normalized.startswith("FVC")
    return False


def extract_line_for_labels(raw_text: str, labels: list[str]) -> str:
    canonical_labels = ["FEV1/FVC" if "FVC" in label and "FEV1" in label else normalize_for_match(label) for label in labels]
    candidates = []
    for line in split_text_lines(raw_text):
        for label in canonical_labels:
            if line_matches_spirometry_label(line, label):
                numbers = extract_numbers_from_line(line)
                if len(numbers) < 3:
                    continue
                normalized_line = normalize_for_match(line)
                starts_with_label = normalized_line.startswith(normalize_for_match(label))
                score = len(numbers) + (10 if starts_with_label else 0)
                candidates.append((score, line))
                break
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def extract_numbers_from_line(line: str) -> list[float]:
    sanitized_line = re.sub(r"(?i)\bFEV1/FVC\b", " ", str(line or ""))
    sanitized_line = re.sub(r"(?i)\bFEV1\b", " ", sanitized_line)
    sanitized_line = re.sub(r"(?i)\bFVC\b", " ", sanitized_line)
    return [
        value
        for value in (parse_measurement_number(token) for token in re.findall(r"[-+]?\d+(?:[.,]\d+)?", sanitized_line))
        if value is not None
    ]


def is_plausible_volume(value) -> bool:
    return value is not None and 0.2 <= float(value) <= 8.5


def is_plausible_ratio(value) -> bool:
    return value is not None and 20 <= float(value) <= 130


def infer_measurement_values_from_numbers(numbers: list[float]) -> dict:
    if not numbers:
        return {"lln": None, "predicted": None, "best": None, "percent": None, "post": None, "post_percent": None, "change_percent": None}

    values = {"lln": None, "predicted": None, "best": None, "percent": None, "post": None, "post_percent": None, "change_percent": None}
    if len(numbers) >= 3 and all(is_plausible_volume(number) for number in numbers[:3]):
        values["lln"], values["predicted"], values["best"] = numbers[:3]
        if len(numbers) >= 4 and 15 <= numbers[3] <= 180:
            values["percent"] = numbers[3]
    else:
        decimal_candidates = [number for number in numbers if is_plausible_volume(number)]
        if len(decimal_candidates) >= 1:
            values["lln"] = decimal_candidates[0]
        if len(decimal_candidates) >= 2:
            values["predicted"] = decimal_candidates[1]
        if len(decimal_candidates) >= 3:
            values["best"] = decimal_candidates[2]

    if values["percent"] is None and values["predicted"] and values["best"]:
        values["percent"] = round((values["best"] / values["predicted"]) * 100, 1)

    if len(numbers) >= 7:
        post_candidate = numbers[-3]
        post_percent_candidate = numbers[-2]
        change_candidate = numbers[-1]
        if is_plausible_volume(post_candidate):
            values["post"] = post_candidate
        if 15 <= post_percent_candidate <= 180:
            values["post_percent"] = post_percent_candidate
        if -100 <= change_candidate <= 200:
            values["change_percent"] = change_candidate
    return values


def infer_ratio_values_from_numbers(numbers: list[float]) -> dict:
    values = {"lln": None, "predicted": None, "best": None, "percent": None, "post": None, "post_percent": None, "change_percent": None}
    ratio_candidates = [number for number in numbers if is_plausible_ratio(number)]
    if len(ratio_candidates) >= 1:
        values["lln"] = ratio_candidates[0]
    if len(ratio_candidates) >= 2:
        values["predicted"] = ratio_candidates[1]
    if len(ratio_candidates) >= 3:
        values["best"] = ratio_candidates[2]
    elif len(ratio_candidates) == 2:
        values["best"] = ratio_candidates[1]
    if len(numbers) >= 4 and 20 <= numbers[3] <= 180:
        values["percent"] = numbers[3]
    if len(numbers) >= 7:
        post_candidate = numbers[-3]
        post_percent_candidate = numbers[-2]
        change_candidate = numbers[-1]
        if is_plausible_ratio(post_candidate):
            values["post"] = post_candidate
        if 20 <= post_percent_candidate <= 180:
            values["post_percent"] = post_percent_candidate
        if -100 <= change_candidate <= 200:
            values["change_percent"] = change_candidate
    return values


def spirometry_values_are_plausible(values: dict) -> bool:
    fvc = values.get("fvc", {})
    fev1 = values.get("fev1", {})
    ratio = values.get("fev1_fvc", {})
    volume_rows = [fvc, fev1]
    if not any(is_plausible_volume(row.get("best")) or is_plausible_volume(row.get("predicted")) for row in volume_rows):
        return False
    for row in volume_rows:
        for key in ["lln", "predicted", "best"]:
            value = row.get(key)
            if value is not None and not is_plausible_volume(value):
                return False
    for key in ["lln", "predicted", "best"]:
        value = ratio.get(key)
        if value is not None and not is_plausible_ratio(value):
            return False
    signatures = [
        tuple(values.get(key, {}).get(field) for field in ["lln", "predicted", "best", "percent"])
        for key in ["fvc", "fev1", "fev1_fvc"]
    ]
    if signatures[0] == signatures[1] == signatures[2]:
        return False
    return True


def extract_spirometry_numbers_from_text(raw_text: str) -> dict:
    fvc_line = extract_line_for_labels(raw_text, ["FVC"])
    ratio_line = extract_line_for_labels(raw_text, ["FEV1/FVC", "FEV1FVC"])
    fev1_line = extract_line_for_labels(raw_text, ["FEV1"])

    fvc = infer_measurement_values_from_numbers(extract_numbers_from_line(fvc_line))
    fev1 = infer_measurement_values_from_numbers(extract_numbers_from_line(fev1_line))
    ratio = infer_ratio_values_from_numbers(extract_numbers_from_line(ratio_line))

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
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
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
    enough_text_data = spirometry_values_are_plausible(text_values) and any(
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
    fvc_post = value_near_column(rows["fvc"], 1138, 0.3, 8)
    fvc_post_percent = value_near_column(rows["fvc"], 1242, 20, 160)
    fvc_change_percent = value_near_column(rows["fvc"], 1342, -100, 200)
    if fvc_percent is None and fvc_predicted and fvc_best:
        fvc_percent = round((fvc_best / fvc_predicted) * 100, 1)

    fev1_predicted = value_near_column(rows["fev1"], 436, 0.3, 8)
    fev1_best = value_near_column(rows["fev1"], 529, 0.3, 8)
    fev1_lln = value_near_column(rows["fev1"], 338, 0.3, 8)
    fev1_percent = value_near_column(rows["fev1"], 634, 20, 160)
    fev1_post = value_near_column(rows["fev1"], 1138, 0.3, 8)
    fev1_post_percent = value_near_column(rows["fev1"], 1242, 20, 160)
    fev1_change_percent = value_near_column(rows["fev1"], 1342, -100, 200)
    if fev1_percent is None and fev1_predicted and fev1_best:
        fev1_percent = round((fev1_best / fev1_predicted) * 100, 1)

    ratio_predicted = value_near_column(rows["fev1_fvc"], 436, 20, 120)
    ratio_best = value_near_column(rows["fev1_fvc"], 529, 20, 120)
    ratio_lln = value_near_column(rows["fev1_fvc"], 338, 20, 120)
    ratio_percent = value_near_column(rows["fev1_fvc"], 634, 20, 160)
    ratio_post = value_near_column(rows["fev1_fvc"], 1138, 20, 130)
    ratio_post_percent = value_near_column(rows["fev1_fvc"], 1242, 20, 160)
    ratio_change_percent = value_near_column(rows["fev1_fvc"], 1342, -100, 200)
    if ratio_percent is None and ratio_predicted and ratio_best:
        ratio_percent = round((ratio_best / ratio_predicted) * 100, 1)

    return {
        "fvc": {
            "lln": fvc_lln,
            "predicted": fvc_predicted,
            "best": fvc_best,
            "percent": fvc_percent,
            "post": fvc_post,
            "post_percent": fvc_post_percent,
            "change_percent": fvc_change_percent,
        },
        "fev1": {
            "lln": fev1_lln,
            "predicted": fev1_predicted,
            "best": fev1_best,
            "percent": fev1_percent,
            "post": fev1_post,
            "post_percent": fev1_post_percent,
            "change_percent": fev1_change_percent,
        },
        "fev1_fvc": {
            "lln": ratio_lln,
            "predicted": ratio_predicted,
            "best": ratio_best,
            "percent": ratio_percent,
            "post": ratio_post,
            "post_percent": ratio_post_percent,
            "change_percent": ratio_change_percent,
        },
    }


def detect_bronchodilator_response(values: dict) -> tuple[bool, str]:
    metrics = [
        ("FEV1", values.get("fev1", {})),
        ("FVC", values.get("fvc", {})),
    ]
    for label, metric in metrics:
        pre_value = metric.get("best")
        post_value = metric.get("post")
        change_percent = metric.get("change_percent")
        if pre_value is None or post_value is None:
            continue
        absolute_change = round(float(post_value) - float(pre_value), 2)
        predicted_value = metric.get("predicted")
        predicted_change_percent = None
        if predicted_value not in [None, 0]:
            predicted_change_percent = round((absolute_change / float(predicted_value)) * 100, 1)
        computed_change_percent = None
        if pre_value not in [None, 0]:
            computed_change_percent = round((absolute_change / float(pre_value)) * 100, 1)
        effective_change_percent = change_percent if change_percent is not None else computed_change_percent
        if effective_change_percent is None:
            continue
        if predicted_change_percent is not None and predicted_change_percent > 10:
            return True, (
                f"Broncodilatador positivo (criterio ERS/ATS 2022): {label} sube de "
                f"{pre_value} a {post_value} L ({predicted_change_percent}% del valor predicho)."
            )
        if absolute_change >= 0.2 and float(effective_change_percent) >= 12:
            return True, (
                f"Broncodilatador positivo (criterio clasico): {label} sube de {pre_value} a {post_value} L "
                f"({absolute_change:.2f} L; {effective_change_percent}% respecto del basal)."
            )
    return False, ""


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
        if ratio.get("lln") is None or fvc.get("lln") is None:
            score = min(score, 72)
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

    missing_for_pattern = []
    if ratio_best is None:
        missing_for_pattern.append("FEV1/FVC medido")
    if fvc_best is None:
        missing_for_pattern.append("FVC medida")
    if ratio_lln is None and ratio.get("predicted") is None:
        missing_for_pattern.append("LIN o teorico de FEV1/FVC")
    if fvc_lln is None and fvc_percent is None:
        missing_for_pattern.append("LIN o porcentaje teorico de FVC")
    if missing_for_pattern:
        return (
            "",
            "Lectura automatica incompleta: falta " + ", ".join(missing_for_pattern) + ". El medico debe revisar la tabla.",
            0,
        )

    if not spirometry_values_are_plausible(values):
        return "", "No lei filas validas de la tabla espirometrica para sugerir un resultado confiable.", 0

    has_obstruction = False
    if ratio_best is not None and ratio_lln is not None:
        has_obstruction = ratio_best < ratio_lln
    elif ratio_best is not None:
        has_obstruction = ratio_best < 70
    has_restriction = False
    if fvc_best is not None and fvc_lln is not None:
        has_restriction = fvc_best < fvc_lln
    elif fvc_percent is not None:
        has_restriction = fvc_percent < 80

    obstruction_grade = spirometry_grade_from_percent(fev1_percent)
    restriction_grade = spirometry_grade_from_percent(fvc_percent)
    if has_obstruction and has_restriction:
        if not obstruction_grade or not restriction_grade:
            return "", "Se detectan valores alterados, pero faltan porcentajes para graduar el patron mixto.", 0
        code = "R{}O{}".format(restriction_grade or "L", obstruction_grade or "L")
        reason = "Relacion FEV1/FVC debajo del LIN/LLN y FVC reducida."
        return code, reason, build_suggestion_probability(values, code)
    if has_obstruction:
        if not obstruction_grade:
            return "", "Se detecta obstruccion, pero falta FEV1 % teorico para graduarla.", 0
        code = "O{}".format(obstruction_grade or "L")
        reason = "Relacion FEV1/FVC debajo del LIN/LLN."
        return code, reason, build_suggestion_probability(values, code)
    if has_restriction:
        if not restriction_grade:
            return "", "La FVC esta reducida, pero falta su porcentaje teorico para graduarla.", 0
        code = "R{}".format(restriction_grade or "L")
        reason = (
            "FVC debajo del LIN/LLN; sugiere un posible patron restrictivo que requiere "
            "confirmacion clinica y, cuando corresponda, volumenes pulmonares."
        )
        return code, reason, build_suggestion_probability(values, code)
    code = "N"
    reason = "FEV1/FVC y FVC estan por encima del LIN/LLN segun los valores leidos."
    return code, reason, build_suggestion_probability(values, code)


def build_spirometry_analysis(values: dict):
    code, reason, probability = suggest_result_code_from_spirometry(values)
    bronchodilator_positive, bronchodilator_reason = detect_bronchodilator_response(values)
    if not code:
        return {
            "code": "",
            "reason": reason,
            "probability": None,
            "probability_phrase": "",
            "summary": reason,
            "values": values,
            "bronchodilator_positive": bronchodilator_positive,
            "bronchodilator_reason": bronchodilator_reason,
        }
    probability_phrase = f"Calidad de lectura automatica: {probability}%"
    return {
        "code": code,
        "reason": reason,
        "probability": probability,
        "probability_phrase": probability_phrase,
        "summary": reason,
        "values": values,
        "bronchodilator_positive": bronchodilator_positive,
        "bronchodilator_reason": bronchodilator_reason,
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


def value_after_any_label(text_lines: list[str], labels: list[str]) -> str:
    for line in text_lines:
        normalized_line = normalize_for_match(line)
        for label in labels:
            normalized_label = normalize_for_match(label)
            if not normalized_line.startswith(normalized_label):
                continue
            separator_match = re.split(r"[:\-]\s*", line, maxsplit=1)
            if len(separator_match) == 2:
                return collapse_spaces(separator_match[1])
            label_words = len(re.findall(r"[A-Za-z0-9]+", label))
            words = line.split()
            if len(words) > label_words:
                return collapse_spaces(" ".join(words[label_words:]))
    return ""


PROFILE_LABEL_PATTERNS = [
    ("visit_date", r"Fecha\s+de\s+visita"),
    ("patient_code", r"(?:C[oó]d\.?|Codigo|C[oó]digo)\s*(?:de\s*)?paciente"),
    ("dni", r"\b(?:DNI|Documento)\b"),
    ("last_name", r"\bApellido\b"),
    ("first_name", r"\b(?:Nom\.?|Nombre)\b"),
    ("birth_date", r"Fecha\s+de\s+nac(?:imien|imiento)?"),
    ("age_reported", r"\bEdad\b"),
    ("gender", r"\b(?:G[eé]nero|Genero|Sexo)\b"),
    ("height_cm", r"\bAltura\s*,?\s*cm\b|\bAltura\b"),
    ("weight_kg", r"\bPeso\s*,?\s*kg\b|\bPeso\b"),
    ("bmi", r"\bBMI\b"),
    ("ethnicity", r"Grupo\s+(?:[eé]tnico|etnico)"),
    ("smoking_status", r"\bFuma\b"),
    ("pack_years", r"Paquete\s*[- ]?\s*a(?:ñ|n)o|Paquete\s*[- ]?\s*anio"),
    ("patient_group", r"Grupo\s+pacientes?"),
]

PROFILE_STANDALONE_LABELS = [
    ("last_name", ["apellido"]),
    ("first_name", ["nom", "nombre"]),
    ("birth_date", ["fecha de nacimien", "fecha de nacimiento", "fecha de nac"]),
    ("ethnicity", ["grupo etnico"]),
    ("smoking_status", ["fuma"]),
    ("patient_group", ["grupo pacientes", "grupo paciente"]),
]

PROFILE_BLOCK_STOP_PREFIXES = [
    "FECHAPRUEBA",
    "PARAMETROS",
    "FVC",
    "FEV1",
    "PEF",
    "ELA",
    "FET",
    "INFORMEMEDICO",
]


def clean_profile_value(raw_value: str) -> str:
    return collapse_spaces(raw_value).strip(" :-;,.")


def parse_profile_field(field_name: str, raw_value: str):
    value = clean_profile_value(raw_value)
    if not value:
        return None
    if field_name in {"patient_code", "dni"}:
        match = re.search(r"[0-9][0-9.\-]{3,}", value)
        return match.group(0) if match else value
    if field_name in {"birth_date", "visit_date"}:
        return parse_date(value)
    if field_name in {"age_reported", "height_cm"}:
        return parse_integer(value)
    if field_name in {"weight_kg", "bmi", "pack_years"}:
        return parse_decimal(value)
    if field_name == "ethnicity" and normalize_for_match(value) in {"CAUCSICO", "CAUCASICO"}:
        return "Caucásico"
    return value


def extract_profile_values_from_line(line: str) -> dict:
    matches = []
    for field_name, pattern in PROFILE_LABEL_PATTERNS:
        for match in re.finditer(pattern, line, flags=re.IGNORECASE):
            matches.append((match.start(), match.end(), field_name))
    if not matches:
        return {}

    matches.sort(key=lambda item: item[0])
    found = {}
    for index, (_, label_end, field_name) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(line)
        value = parse_profile_field(field_name, line[label_end:next_start])
        if value not in [None, ""] and field_name not in found:
            found[field_name] = value
    return found


def extract_profile_values_from_labeled_text(text_lines: list[str]) -> dict:
    values = {}
    for line in text_lines:
        for field_name, value in extract_profile_values_from_line(line).items():
            if value not in [None, ""]:
                values[field_name] = value
    return values


def clean_profile_snapshot_values(snapshot: dict) -> dict:
    if not snapshot:
        return snapshot
    for field_name in ("dni", "patient_code"):
        if snapshot.get(field_name):
            digits = re.sub(r"\D+", "", str(snapshot[field_name]))
            snapshot[field_name] = digits if digits else ""
    patient_code = snapshot.get("patient_code", "")
    if not snapshot.get("dni") and 6 <= len(patient_code) <= 9:
        snapshot["dni"] = patient_code
    if snapshot.get("smoking_status"):
        normalized_smoking = normalize_for_match(snapshot["smoking_status"])
        normalized_names = {
            normalize_for_match(f"{snapshot.get('last_name', '')} {snapshot.get('first_name', '')}"),
            normalize_for_match(f"{snapshot.get('first_name', '')} {snapshot.get('last_name', '')}"),
        }
        if normalized_smoking.startswith("GRUPOPACIENTE") or normalized_smoking in normalized_names:
            snapshot["smoking_status"] = ""
    if snapshot.get("ethnicity") and normalize_for_match(snapshot["ethnicity"]) in {"CAUCSICO", "CAUCASICO"}:
        snapshot["ethnicity"] = "Caucásico"
    return snapshot


def profile_standalone_label_for_line(line: str):
    normalized_line = normalize_for_match(line)
    for field_name, label_options in PROFILE_STANDALONE_LABELS:
        if normalized_line in {normalize_for_match(label) for label in label_options}:
            return field_name
    return None


def should_stop_profile_value_block(line: str) -> bool:
    normalized_line = normalize_for_match(line)
    return any(normalized_line.startswith(prefix) for prefix in PROFILE_BLOCK_STOP_PREFIXES)


def extract_vertical_profile_values(text_lines: list[str]) -> dict:
    values = {}
    index = 0
    while index < len(text_lines):
        field_name = profile_standalone_label_for_line(text_lines[index])
        if not field_name:
            index += 1
            continue

        labels = []
        cursor = index
        while cursor < len(text_lines):
            label_field = profile_standalone_label_for_line(text_lines[cursor])
            if not label_field:
                break
            labels.append(label_field)
            cursor += 1

        raw_values = []
        value_cursor = cursor
        while value_cursor < len(text_lines) and len(raw_values) < len(labels):
            line = text_lines[value_cursor]
            if profile_standalone_label_for_line(line) or extract_profile_values_from_line(line) or should_stop_profile_value_block(line):
                break
            raw_values.append(line)
            value_cursor += 1

        if labels and raw_values:
            for label_field, raw_value in zip(labels, raw_values):
                parsed_value = parse_profile_field(label_field, raw_value)
                if parsed_value not in [None, ""]:
                    values[label_field] = parsed_value
            index = value_cursor
            continue

        index += 1
    return values


def fill_snapshot_from_labeled_lines(snapshot: dict, text_lines: list[str]) -> dict:
    fallback_fields = {
        "patient_code": (["codigo de paciente", "codigo paciente", "cod. paciente", "cod paciente"], str),
        "dni": (["dni", "documento"], str),
        "last_name": (["apellido"], str),
        "first_name": (["nom.", "nom", "nombre"], str),
        "birth_date": (["fecha de nacimien", "fecha de nacimiento", "fecha de nac"], parse_date),
        "age_reported": (["edad"], parse_integer),
        "gender": (["genero", "sexo"], str),
        "height_cm": (["altura, cm", "altura cm", "altura"], parse_integer),
        "weight_kg": (["peso, kg", "peso kg", "peso"], parse_decimal),
        "bmi": (["bmi"], parse_decimal),
        "ethnicity": (["grupo etnico"], str),
        "smoking_status": (["fuma"], str),
        "pack_years": (["paquete-ano", "paquete ano", "paquete-anio", "paquete anio"], parse_decimal),
        "patient_group": (["grupo pacientes", "grupo paciente"], str),
    }
    for field_name, (labels, parser) in fallback_fields.items():
        if snapshot.get(field_name) not in [None, ""]:
            continue
        raw_value = value_after_any_label(text_lines, labels)
        if not raw_value:
            continue
        value = parser(raw_value) if parser is not str else raw_value
        if value not in [None, ""]:
            snapshot[field_name] = value
    return snapshot


def extract_patient_snapshot_from_text(raw_text: str):
    text_lines = split_text_lines(raw_text)
    compact_text = " ".join(text_lines)
    if not compact_text:
        return {}

    def find_value(patterns: list[str]):
        for line in text_lines:
            normalized_line = normalize_for_match(line)
            for pattern in patterns:
                if pattern.startswith("line:"):
                    label = pattern.split(":", 1)[1]
                    normalized_label = normalize_for_match(label)
                    if normalized_line.startswith(normalized_label):
                        separator_match = re.split(r"[:\-]\s*", line, maxsplit=1)
                        if len(separator_match) == 2:
                            return collapse_spaces(separator_match[1])
                        label_words = len(re.findall(r"[A-Za-z0-9]+", normalized_label))
                        words = line.split()
                        if len(words) > label_words:
                            return collapse_spaces(" ".join(words[label_words:]))
        for pattern in patterns:
            if pattern.startswith("line:"):
                continue
            match = re.search(pattern, compact_text, flags=re.IGNORECASE)
            if match:
                return collapse_spaces(match.group(1))
        return ""

    snapshot = {
        "visit_date": parse_date(find_value([r"Fecha\s+de\s+visita[:\s]+([0-9/\-]{8,10})"])),
        "patient_code": find_value(
            [
                "line:codigo de paciente",
                "line:codigo paciente",
                "line:cod. paciente",
                "line:cod paciente",
                r"C[oó]d(?:igo|\.)?(?:\s+de)?\s*Paciente[:\s]+([A-Z0-9.\-]{6,})",
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
    for field_name, value in extract_profile_values_from_labeled_text(text_lines).items():
        if value not in [None, ""]:
            snapshot[field_name] = value
    for field_name, value in extract_vertical_profile_values(text_lines).items():
        if value not in [None, ""]:
            snapshot[field_name] = value
    snapshot = fill_snapshot_from_labeled_lines(snapshot, text_lines)
    if snapshot.get("patient_group") and snapshot.get("last_name") and snapshot.get("first_name"):
        normalized_group = normalize_for_match(snapshot["patient_group"])
        if normalized_group in {
            normalize_for_match(f"{snapshot['last_name']} {snapshot['first_name']}"),
            normalize_for_match(f"{snapshot['first_name']} {snapshot['last_name']}"),
        }:
            snapshot["patient_group"] = ""
    snapshot = clean_profile_snapshot_values(snapshot)

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
        "dni": "",
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


def apply_snapshot_to_patient(patient, snapshot: dict, *, update_full_name: bool = True):
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
        patient_manager = getattr(patient.__class__, "all_objects", patient.__class__.objects)
        duplicate_dni_exists = patient_manager.filter(dni=extracted_dni).exclude(pk=patient.pk).exists()
    if extracted_dni and not duplicate_dni_exists:
        if patient.dni != extracted_dni:
            patient.dni = extracted_dni
            changed_fields.append("dni")

    extracted_full_name = snapshot.get("full_name") if update_full_name else ""
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


def calculate_age_on_date(birth_date, reference_date):
    if not birth_date or not reference_date:
        return None
    years = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years if years >= 0 else None


def snapshot_with_computed_age(snapshot: dict, reference_date=None) -> dict:
    if not snapshot or not snapshot.get("birth_date"):
        return snapshot
    computed_age = calculate_age_on_date(snapshot.get("birth_date"), reference_date or snapshot.get("visit_date"))
    if computed_age is None:
        return snapshot
    updated_snapshot = dict(snapshot)
    updated_snapshot["age_reported"] = computed_age
    return updated_snapshot


def build_analysis_from_text(raw_text: str, source: str = "text"):
    text = "\n".join(split_text_lines(raw_text))
    if not text:
        return {}
    values = extract_spirometry_numbers_from_text(text)
    has_values = spirometry_values_are_plausible(values) and any(
        values.get(key, {}).get("best") is not None or values.get(key, {}).get("percent") is not None for key in values
    )
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


def apply_snapshot_to_encounter_patient(encounter, snapshot: dict, *, update_full_name: bool = True):
    snapshot = snapshot_with_computed_age(snapshot, getattr(encounter, "encounter_date", None))
    patient = encounter.patient
    changed_fields = apply_snapshot_to_patient(patient, snapshot, update_full_name=update_full_name)
    return patient, sorted(set(changed_fields))


def ingest_pdf_attachment_into_patient(attachment):
    if not attachment or not getattr(attachment, "file", None):
        return {}, []
    from .file_utils import local_field_file_path

    with local_field_file_path(attachment.file) as attachment_path:
        snapshot = extract_patient_snapshot_from_pdf(str(attachment_path), attachment_id=attachment.pk)
    encounter = attachment.encounter
    snapshot = snapshot_with_computed_age(snapshot, getattr(encounter, "encounter_date", None))
    patient = encounter.patient
    changed_fields = apply_snapshot_to_patient(patient, snapshot)
    return snapshot, changed_fields
