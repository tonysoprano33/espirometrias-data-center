import calendar as month_calendar
import base64
from datetime import date, datetime, timedelta
import json
import mimetypes
from pathlib import Path
import re
from statistics import mean
from tempfile import NamedTemporaryFile
import unicodedata

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Max
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    DoctorReviewForm,
    DrappImportForm,
    GRADE_TO_OBSTRUCTION_CODE,
    GRADE_TO_RESTRICTION_CODE,
    PatientForm,
    QuickEncounterForm,
    ReferringPhysicianForm,
    RESULT_CODE_SUGGESTIONS,
    get_result_label_for_code,
    parse_result_code,
)
from .models import (
    Attachment,
    AttachmentKind,
    CoverageType,
    Encounter,
    EncounterEvent,
    EncounterEventType,
    EncounterStatus,
    GeneratedReport,
    Patient,
    ReferringPhysician,
    ReportType,
    SpirometryResult,
    VitalSigns,
    WalkTest,
)
from .pdf_intake import (
    apply_snapshot_to_encounter_patient,
    build_analysis_from_browser_payload,
    build_analysis_from_text,
    build_spirometry_suggestion_from_pdf,
    collapse_spaces,
    extract_pdf_text_content,
    get_ocr_engine,
    ensure_pdf_preview_pages,
    ingest_pdf_attachment_into_patient,
    looks_like_profile_data,
    normalize_for_match,
)
from .services import build_reports_for_encounter
from .services import (
    DEFAULT_DOCTOR,
    construir_informe_espirometria,
    formatear_dni,
    interpolar_valores,
    limpiar_entero,
    normalizar_medico,
    normalizar_patron,
)


SPANISH_MONTHS = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]
SPANISH_WEEKDAYS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


def media_url_prefix() -> str:
    media_url = str(settings.MEDIA_URL or "/media/")
    return media_url if media_url.startswith("/") else f"/{media_url}"


def is_result_image_attachment(attachment) -> bool:
    if not attachment or not getattr(attachment, "file", None):
        return False

    mime_type = str(getattr(attachment, "mime_type", "") or "").lower()
    extension = Path(str(getattr(attachment.file, "name", "") or "")).suffix.lower()
    return mime_type.startswith("image/") or extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def build_pdf_preview_images(attachment):
    if not attachment or not getattr(attachment, "file", None):
        return []

    attachment_path = Path(attachment.file.path)
    if not attachment_path.exists():
        return []
    existing = ensure_pdf_preview_pages(str(attachment_path), attachment_id=attachment.pk)

    if settings.USE_SUPABASE_STORAGE:
        return [
            {
                "index": index + 1,
                "url": f"data:image/png;base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}",
            }
            for index, image_path in enumerate(existing)
        ]

    prefix = media_url_prefix().rstrip("/")
    return [
        {
            "index": index + 1,
            "url": f"{prefix}/previews/attachment_{attachment.pk}/{image_path.name}",
        }
        for index, image_path in enumerate(existing)
    ]


def build_result_preview_images(attachment):
    if not attachment or not getattr(attachment, "file", None):
        return []

    if is_result_image_attachment(attachment):
        return [{"index": 1, "url": attachment.file.url}]
    return build_pdf_preview_images(attachment)


def normalize_identity_value(value: str) -> str:
    return normalize_for_match(collapse_spaces(value or ""))


def snapshot_matches_patient(patient, snapshot: dict) -> bool:
    if not patient or not snapshot:
        return True

    snapshot_dni = normalize_identity_value(snapshot.get("dni") or snapshot.get("patient_code") or "")
    patient_dni = normalize_identity_value(getattr(patient, "dni", "") or getattr(patient, "patient_code", "") or "")
    if snapshot_dni and patient_dni:
        return snapshot_dni == patient_dni

    snapshot_full_name = normalize_identity_value(
        snapshot.get("full_name")
        or f"{snapshot.get('last_name', '')} {snapshot.get('first_name', '')}"
    )
    patient_full_name = normalize_identity_value(getattr(patient, "full_name", "") or "")
    if snapshot_full_name and patient_full_name:
        return snapshot_full_name == patient_full_name
    return True


def get_latest_result_attachment(encounter):
    return (
        encounter.attachments.filter(file_kind__in=[AttachmentKind.PDF_RESULTADO, AttachmentKind.FOTO_RESULTADO])
        .order_by("-created_at")
        .first()
    )


def classify_result_upload(uploaded_file):
    content_type = str(getattr(uploaded_file, "content_type", "") or "").lower()
    file_name = str(getattr(uploaded_file, "name", "") or "")
    extension = Path(file_name).suffix.lower()
    guessed_content_type = mimetypes.guess_type(file_name)[0] or ""

    is_pdf = content_type == "application/pdf" or extension == ".pdf" or guessed_content_type == "application/pdf"
    if is_pdf:
        return AttachmentKind.PDF_RESULTADO, "application/pdf"

    is_image = content_type.startswith("image/") or guessed_content_type.startswith("image/")
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        is_image = True
    if is_image:
        return AttachmentKind.FOTO_RESULTADO, content_type or guessed_content_type or "image/jpeg"

    raise ValueError("Subi un PDF o una imagen JPG, PNG o WEBP.")


def build_analysis_for_uploaded_result(attachment, analysis_payload_json: str = ""):
    if analysis_payload_json:
        analysis = build_analysis_from_browser_payload(analysis_payload_json)
        if analysis:
            return analysis

    if not attachment or not getattr(attachment, "file", None):
        return {}

    if attachment.file_kind == AttachmentKind.PDF_RESULTADO:
        extracted_text = extract_pdf_text_content(attachment.file.path)
        if extracted_text:
            return build_analysis_from_text(extracted_text, source="server-pdf-text")
    return {}


def apply_result_code_to_spirometry(encounter, result_code: str):
    parsed = parse_result_code(result_code)
    pattern = ""
    obstruction_grade = ""
    restriction_grade = ""

    if parsed:
        pattern = parsed["pattern"]
        obstruction_grade = parsed["obstruction_grade"]
        restriction_grade = parsed["restriction_grade"]

    result, _ = SpirometryResult.objects.get_or_create(encounter=encounter)
    result.respiratory_pattern = pattern
    result.obstruction_grade = obstruction_grade
    result.restriction_grade = restriction_grade
    result.bronchodilator_positive = False
    result.save()
    return result


def store_spirometry_analysis(encounter, analysis: dict):
    if not analysis:
        return None

    result, _ = SpirometryResult.objects.get_or_create(encounter=encounter)
    result.measured_values = analysis.get("values") or {}
    result.suggested_code = analysis.get("code", "") or ""
    result.suggested_probability = analysis.get("probability")
    result.suggested_summary = analysis.get("summary", "") or ""
    result.extracted_source = analysis.get("source", "") or ""
    result.save(
        update_fields=[
            "measured_values",
            "suggested_code",
            "suggested_probability",
            "suggested_summary",
            "extracted_source",
            "updated_at",
        ]
    )
    return result


def build_stored_suggestion_context(spirometry_result):
    if not spirometry_result or not spirometry_result.suggested_code:
        return None
    stored_summary = spirometry_result.suggested_summary or ""
    probability_phrase = (
        f"{spirometry_result.suggested_probability}% probable {spirometry_result.suggested_code}"
        if spirometry_result.suggested_probability is not None
        else ""
    )
    reason = stored_summary
    if probability_phrase and stored_summary.startswith(probability_phrase):
        reason = stored_summary[len(probability_phrase):].lstrip(". ").strip()
    return {
        "code": spirometry_result.suggested_code,
        "reason": reason,
        "summary": stored_summary,
        "probability": spirometry_result.suggested_probability,
        "probability_phrase": probability_phrase,
        "values": spirometry_result.measured_values or {},
        "source": spirometry_result.extracted_source or "",
    }


def get_result_code_from_encounter(encounter) -> str:
    spirometry_result = getattr(encounter, "spirometry_result", None)
    if not spirometry_result:
        return ""
    if spirometry_result.respiratory_pattern == "Normal":
        return "N"
    if spirometry_result.respiratory_pattern == "Obstructivo":
        return GRADE_TO_OBSTRUCTION_CODE.get(spirometry_result.obstruction_grade, "")
    if spirometry_result.respiratory_pattern == "Restrictivo":
        return GRADE_TO_RESTRICTION_CODE.get(spirometry_result.restriction_grade, "")
    if spirometry_result.respiratory_pattern == "Mixto":
        restriction_code = GRADE_TO_RESTRICTION_CODE.get(spirometry_result.restriction_grade, "")
        obstruction_code = GRADE_TO_OBSTRUCTION_CODE.get(spirometry_result.obstruction_grade, "")
        if restriction_code and obstruction_code:
            return restriction_code + obstruction_code
        return "MIXTO"
    return ""


def get_result_label_from_encounter(encounter) -> str:
    return get_result_label_for_code(get_result_code_from_encounter(encounter))


def get_attendance_label(encounter) -> str:
    if encounter.attended:
        return "Atendido"
    if encounter.no_show:
        return "No llego"
    return "Esperado"


def get_default_physician():
    return ReferringPhysician.objects.filter(is_default=True, active=True).first() or ReferringPhysician.objects.filter(
        active=True
    ).first()


def record_encounter_event(encounter, event_type: str, title: str, actor=None, details: str = "", metadata=None):
    if not encounter or not getattr(encounter, "patient_id", None):
        return None
    return EncounterEvent.objects.create(
        encounter=encounter,
        patient=encounter.patient,
        actor=actor,
        event_type=event_type,
        title=title[:160],
        details=details,
        metadata=metadata or {},
    )


def build_mutual_cvl_result(pattern: str, obstruction_grade: str, restriction_grade: str) -> str:
    if pattern == "Normal":
        return "Normal"
    if pattern == "Obstructivo":
        if obstruction_grade == "leve":
            return "Levemente disminuida"
        if obstruction_grade == "moderado":
            return "Moderadamente disminuida"
        if obstruction_grade == "moderadamente severa":
            return "Moderadamente a severamente disminuida"
        return "Severamente disminuida"
    if pattern == "Restrictivo":
        if restriction_grade == "leve":
            return "Levemente reducida"
        if restriction_grade == "moderado":
            return "Moderadamente reducida"
        if restriction_grade == "moderadamente severa":
            return "Moderadamente a severamente reducida"
        return "Severamente reducida"
    return "Reducida (patron mixto)"


def is_ajax_request(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def sync_attendance_status(encounter):
    if encounter.attended:
        encounter.no_show = False
        if encounter.status in [EncounterStatus.PENDIENTE, EncounterStatus.NO_LLEGO]:
            encounter.status = EncounterStatus.CARGADA
    elif encounter.no_show:
        encounter.status = EncounterStatus.NO_LLEGO
    else:
        if encounter.status == EncounterStatus.NO_LLEGO:
            encounter.status = EncounterStatus.PENDIENTE


def assign_encounter_patient_by_dni(encounter, dni_value: str):
    dni = (dni_value or "").strip()
    patient = encounter.patient

    if not dni:
        if patient.dni:
            patient.dni = None
            patient.save(update_fields=["dni", "updated_at"])
        return patient, False

    existing_patient = Patient.objects.filter(dni=dni).exclude(pk=patient.pk).first()
    if existing_patient:
        encounter.patient = existing_patient
        encounter.save(update_fields=["patient", "updated_at"])
        return existing_patient, True

    if patient.dni != dni:
        patient.dni = dni
        patient.save(update_fields=["dni", "updated_at"])
    return patient, False


def encounter_has_cycle_data(encounter) -> bool:
    vital = getattr(encounter, "vital_signs", None)
    return any(
        [
            getattr(vital, "so2_post", None) is not None,
            getattr(vital, "fc_post", None) is not None,
            bool(getattr(encounter, "walk_test", None)),
        ]
    )


def get_latest_report_info(encounter):
    reports = list(encounter.generated_reports.all())
    if not reports:
        return {
            "latest_report_url": "",
            "latest_report_name": "",
            "complete_report_url": "",
            "complete_report_name": "",
            "mutual_report_url": "",
            "mutual_report_name": "",
            "detail_url": reverse("clinic:encounter_detail", args=[encounter.pk]),
        }

    complete_report = next((report for report in reports if report.report_type == ReportType.COMPLETO), None)
    mutual_report = next((report for report in reports if report.report_type == ReportType.MUTUAL), None)
    latest_report = next((report for report in reports if report.report_type == ReportType.COMPLETO), reports[0])
    latest_attachment = getattr(latest_report, "attachment", None)
    complete_attachment = getattr(complete_report, "attachment", None)
    mutual_attachment = getattr(mutual_report, "attachment", None)
    latest_url = latest_attachment.file.url if latest_attachment and getattr(latest_attachment, "file", None) else ""
    latest_name = latest_attachment.original_name if latest_attachment else latest_report.report_type
    complete_url = complete_attachment.file.url if complete_attachment and getattr(complete_attachment, "file", None) else ""
    complete_name = complete_attachment.original_name if complete_attachment else ""
    mutual_url = mutual_attachment.file.url if mutual_attachment and getattr(mutual_attachment, "file", None) else ""
    mutual_name = mutual_attachment.original_name if mutual_attachment else ""
    return {
        "latest_report_url": latest_url,
        "latest_report_name": latest_name,
        "complete_report_url": complete_url,
        "complete_report_name": complete_name,
        "mutual_report_url": mutual_url,
        "mutual_report_name": mutual_name,
        "detail_url": reverse("clinic:encounter_detail", args=[encounter.pk]),
    }


def parse_optional_int(raw_value, max_value=None):
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except (TypeError, ValueError):
        return None
    if value < 0:
        value = 0
    if max_value is not None and value > max_value:
        value = max_value
    return value


def get_row_state_payload(encounter):
    can_generate_report, report_block_reason = get_report_readiness(encounter)
    inconsistency_flags = get_encounter_inconsistencies(encounter)
    vital = getattr(encounter, "vital_signs", None)
    current_physician = getattr(encounter, "referring_physician", None)
    default_physician = get_default_physician()
    payload = {
        "encounter_id": encounter.pk,
        "status": encounter.status,
        "attended": encounter.attended,
        "no_show": encounter.no_show,
        "attendance_label": get_attendance_label(encounter),
        "result_label": get_result_label_from_encounter(encounter),
        "result_code": get_result_code_from_encounter(encounter),
        "study_type": encounter.study_type,
        "coverage_type": encounter.coverage_type,
        "referring_physician": str(current_physician.pk) if current_physician else "",
        "referring_physician_name": current_physician.full_name if current_physician else "",
        "referring_physician_display": (
            current_physician.full_name if current_physician else getattr(default_physician, "full_name", DEFAULT_DOCTOR)
        ),
        "encounter_time": encounter.encounter_time.strftime("%H:%M") if encounter.encounter_time else "",
        "patient_name": encounter.patient.full_name,
        "patient_dni": encounter.patient.dni or "",
        "patient_dni_display": encounter.patient.dni or "Completar DNI",
        "patient_url": reverse("clinic:patient_detail", args=[encounter.patient_id]),
        "so2_rest": "" if getattr(vital, "so2_rest", None) is None else str(vital.so2_rest),
        "fc_rest": "" if getattr(vital, "fc_rest", None) is None else str(vital.fc_rest),
        "so2_post": "" if getattr(vital, "so2_post", None) is None else str(vital.so2_post),
        "fc_post": "" if getattr(vital, "fc_post", None) is None else str(vital.fc_post),
        "has_cycle_data": encounter_has_cycle_data(encounter),
        "can_generate_report": can_generate_report,
        "report_block_reason": report_block_reason,
        "inconsistencies": inconsistency_flags,
        "inconsistency_message": "Advertencias: " + " | ".join(inconsistency_flags) if inconsistency_flags else "",
        "has_generated_reports": encounter.generated_reports.exists(),
        "report_button_label": "Regenerar informe" if encounter.generated_reports.exists() else "Generar informe",
    }
    payload.update(get_latest_report_info(encounter))
    return payload


def get_operational_alerts(queryset):
    pending_review = queryset.filter(status=EncounterStatus.PENDIENTE).count()
    ready_for_report = 0
    missing_pdf = 0
    for encounter in queryset.select_related("spirometry_result", "vital_signs", "walk_test").prefetch_related("attachments", "generated_reports"):
        can_generate, _ = get_report_readiness(encounter)
        if can_generate and not encounter.generated_reports.exists():
            ready_for_report += 1
        if encounter.study_type == "Espirometria" and not get_latest_result_attachment(encounter):
            missing_pdf += 1
    return {
        "pending_review": pending_review,
        "ready_for_report": ready_for_report,
        "missing_pdf": missing_pdf,
        "no_show": queryset.filter(no_show=True).count(),
    }


def update_inline_field(encounter, field_name: str, raw_value: str, request_user):
    patient = encounter.patient
    vital, _ = VitalSigns.objects.get_or_create(encounter=encounter)
    raw_text = (raw_value or "").strip()

    if field_name == "patient_name":
        old_value = patient.full_name
        patient.full_name = raw_text.upper()
        patient.save(update_fields=["full_name", "updated_at"])
        if old_value != patient.full_name:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "Nombre del paciente actualizado",
                actor=request_user,
                details=f"Antes: {old_value} | Ahora: {patient.full_name}",
            )
        return

    if field_name == "patient_dni":
        old_dni = patient.dni or ""
        assign_encounter_patient_by_dni(encounter, raw_value)
        encounter.refresh_from_db()
        new_dni = encounter.patient.dni or ""
        if old_dni != new_dni:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "DNI actualizado",
                actor=request_user,
                details=f"Antes: {old_dni or '-'} | Ahora: {new_dni or '-'}",
            )
        return

    if field_name == "encounter_time":
        old_label = encounter.encounter_time.strftime("%H:%M") if encounter.encounter_time else "-"
        encounter.encounter_time = raw_value or None
        new_label = encounter.encounter_time.strftime("%H:%M") if encounter.encounter_time else "-"
    elif field_name == "study_type":
        old_label = encounter.study_type
        encounter.study_type = raw_value or encounter.study_type
        new_label = encounter.study_type
    elif field_name == "coverage_type":
        old_label = encounter.coverage_type
        encounter.coverage_type = raw_value or encounter.coverage_type
        new_label = encounter.coverage_type
    elif field_name == "referring_physician":
        old_label = encounter.referring_physician.full_name if encounter.referring_physician else DEFAULT_DOCTOR
        encounter.referring_physician = (
            ReferringPhysician.objects.filter(pk=raw_value, active=True).first() if raw_value else get_default_physician()
        )
        new_label = encounter.referring_physician.full_name if encounter.referring_physician else DEFAULT_DOCTOR
    elif field_name == "so2_rest":
        encounter.updated_by = request_user
        old_value = vital.so2_rest
        vital.so2_rest = parse_optional_int(raw_value, max_value=99)
        vital.save()
        if old_value != vital.so2_rest:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "SO2 en reposo actualizado",
                actor=request_user,
                details=f"Antes: {old_value if old_value is not None else '-'} | Ahora: {vital.so2_rest if vital.so2_rest is not None else '-'}",
            )
        return
    elif field_name == "fc_rest":
        encounter.updated_by = request_user
        old_value = vital.fc_rest
        vital.fc_rest = parse_optional_int(raw_value, max_value=999)
        vital.save()
        if old_value != vital.fc_rest:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "FC en reposo actualizada",
                actor=request_user,
                details=f"Antes: {old_value if old_value is not None else '-'} | Ahora: {vital.fc_rest if vital.fc_rest is not None else '-'}",
            )
        return
    elif field_name == "so2_post":
        encounter.updated_by = request_user
        old_value = vital.so2_post
        vital.so2_post = parse_optional_int(raw_value, max_value=99)
        vital.save()
        if old_value != vital.so2_post:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "SO2 post caminata actualizada",
                actor=request_user,
                details=f"Antes: {old_value if old_value is not None else '-'} | Ahora: {vital.so2_post if vital.so2_post is not None else '-'}",
            )
        return
    elif field_name == "fc_post":
        encounter.updated_by = request_user
        old_value = vital.fc_post
        vital.fc_post = parse_optional_int(raw_value, max_value=999)
        vital.save()
        if old_value != vital.fc_post:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "FC post caminata actualizada",
                actor=request_user,
                details=f"Antes: {old_value if old_value is not None else '-'} | Ahora: {vital.fc_post if vital.fc_post is not None else '-'}",
            )
        return
    elif field_name == "respiratory_result":
        old_label = get_result_code_from_encounter(encounter) or "-"
        apply_result_code_to_spirometry(encounter, raw_value or "")
        encounter.updated_by = request_user
        encounter.save(update_fields=["updated_by", "updated_at"])
        new_label = get_result_code_from_encounter(encounter) or "-"
        if old_label != new_label:
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "Resultado respiratorio actualizado",
                actor=request_user,
                details=f"Antes: {old_label} | Ahora: {new_label}",
            )
        return
    else:
        return

    encounter.updated_by = request_user
    encounter.save(
        update_fields=["encounter_time", "study_type", "coverage_type", "referring_physician", "updated_by", "updated_at"]
    )
    if old_label != new_label:
        labels = {
            "encounter_time": "Hora actualizada",
            "study_type": "Tipo de estudio actualizado",
            "coverage_type": "Cobertura actualizada",
            "referring_physician": "Doctor derivante actualizado",
        }
        record_encounter_event(
            encounter,
            EncounterEventType.UPDATED,
            labels.get(field_name, "Dato actualizado"),
            actor=request_user,
            details=f"Antes: {old_label} | Ahora: {new_label}",
        )


def cycle_attendance(encounter, request_user):
    previous_label = get_attendance_label(encounter)
    if not encounter.attended and not encounter.no_show:
        encounter.attended = True
        encounter.no_show = False
    elif encounter.attended:
        encounter.attended = False
        encounter.no_show = True
    else:
        encounter.attended = False
        encounter.no_show = False

    sync_attendance_status(encounter)
    encounter.updated_by = request_user
    encounter.save(update_fields=["attended", "no_show", "status", "updated_by", "updated_at"])
    new_label = get_attendance_label(encounter)
    if previous_label != new_label:
        record_encounter_event(
            encounter,
            EncounterEventType.ATTENDANCE,
            "Asistencia actualizada",
            actor=request_user,
            details=f"Antes: {previous_label} | Ahora: {new_label}",
        )


def save_quick_encounter(form: QuickEncounterForm, request_user, encounter=None):
    default_physician = get_default_physician()
    full_name = form.cleaned_data["patient_name"].strip().upper()
    patient_dni = (form.cleaned_data.get("patient_dni") or "").strip()
    selected_physician = form.cleaned_data.get("referring_physician") or default_physician

    patient = None
    if patient_dni:
        patient = Patient.objects.filter(dni=patient_dni).first()
    if patient is None and encounter is not None:
        patient = encounter.patient
    if patient is None and full_name:
        patient = Patient.objects.filter(full_name=full_name).order_by("-updated_at").first()
    if patient is None:
        patient = Patient.objects.create(full_name=full_name, dni=patient_dni or None)
    else:
        patient.full_name = full_name
        if patient_dni:
            patient.dni = patient_dni
        patient.save()

    is_new = encounter is None
    if encounter is None:
        encounter = Encounter(
            created_by=request_user,
        )

    attended = bool(form.cleaned_data.get("attended"))
    no_show = bool(form.cleaned_data.get("no_show"))
    encounter.patient = patient
    encounter.encounter_date = timezone.localdate()
    encounter.encounter_time = form.cleaned_data.get("encounter_time")
    encounter.study_type = form.cleaned_data["study_type"]
    encounter.status = EncounterStatus.PENDIENTE
    encounter.coverage_type = form.cleaned_data["coverage_type"]
    encounter.referring_physician = selected_physician
    encounter.attended = attended
    encounter.no_show = no_show
    encounter.updated_by = request_user
    if encounter.pk is None:
        encounter.created_by = request_user
    sync_attendance_status(encounter)
    encounter.save()

    VitalSigns.objects.update_or_create(
        encounter=encounter,
        defaults={
            "so2_rest": form.cleaned_data.get("so2_rest"),
            "fc_rest": form.cleaned_data.get("fc_rest"),
            "so2_post": form.cleaned_data.get("so2_post"),
            "fc_post": form.cleaned_data.get("fc_post"),
        },
    )

    WalkTest.objects.update_or_create(
        encounter=encounter,
        defaults={
            "distance_meters": int(form.cleaned_data.get("distance_meters") or 200),
            "completed": bool(form.cleaned_data.get("completed")),
            "stopped": False,
            "symptoms": False,
            "borg_final": int(form.cleaned_data.get("borg_final") or 0),
        },
    )

    result_code = form.cleaned_data.get("respiratory_result") or ""
    apply_result_code_to_spirometry(encounter, result_code)
    record_encounter_event(
        encounter,
        EncounterEventType.CREATED if is_new else EncounterEventType.UPDATED,
        "Atencion creada" if is_new else "Atencion editada",
        actor=request_user,
        details=(
            f"Estudio: {encounter.study_type} | Cobertura: {encounter.coverage_type} | "
            f"Asistencia: {get_attendance_label(encounter)}"
        ),
    )
    return encounter


def normalize_imported_name(raw_name: str) -> str:
    normalized = collapse_spaces(str(raw_name or ""))
    normalized = normalized.replace("@", " ")
    normalized = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])\d[\d/.\-]*", "", normalized)
    normalized = re.sub(r"\b\d[\d/.\-]*\b", " ", normalized)
    normalized = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ, ]+", " ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r",\s*,+", ", ", normalized)
    normalized = collapse_spaces(normalized.replace(" ,", ","))
    normalized = normalized.strip(" ,")
    normalized_upper = normalized.upper()
    if re.match(r"^O [A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ' ]+, [A-ZÁÉÍÓÚÜÑ' ]+$", normalized_upper):
        normalized_upper = normalized_upper[2:].strip()
    return normalized_upper


def infer_coverage_type(raw_coverage: str) -> str:
    text = (raw_coverage or "").strip().lower()
    if not text or text == "particular":
        return "Particular"
    return "Mutual"


def infer_study_type(raw_practice: str) -> str:
    text = (raw_practice or "").strip().lower()
    if "ciclo" in text:
        return "Ciclometria"
    if "espiro" in text:
        return "Espirometria"
    return "Ciclometria"


DRAPP_ROW_SKIP_WORDS = {
    "RESERVADO",
    "RESERVADOS",
    "LINKDEPAGO",
    "ENESPERA",
    "ENCONSULTA",
    "ATENDIDOS",
    "AUSENTES",
    "CANCELADOS",
    "PENDIENTE",
    "CENTRORESPIRATORIOINTEGRAL",
}
DRAPP_PRACTICE_HINTS = ("CICLO", "ESPIRO")
DRAPP_WEEKDAY_NAMES = ("LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO")
DRAPP_MONTH_MAP = {normalize_for_match(month): index + 1 for index, month in enumerate(SPANISH_MONTHS)}


def normalize_document_number(raw_value: str) -> str:
    digits = re.sub(r"\D+", "", str(raw_value or ""))
    return digits


def normalize_phone_number(raw_value: str) -> str:
    raw_text = collapse_spaces(raw_value)
    if not raw_text:
        return ""
    has_plus = raw_text.startswith("+")
    digits = re.sub(r"\D+", "", raw_text)
    if len(digits) < 8:
        return ""
    return f"+{digits}" if has_plus else digits


def parse_drapp_agenda_date(raw_value: str):
    normalized_text = unicodedata.normalize("NFKD", collapse_spaces(raw_value or ""))
    normalized_text = normalized_text.encode("ascii", "ignore").decode("ascii").upper()
    normalized_text = re.sub(r"[^A-Z0-9 -]+", " ", normalized_text)
    normalized_text = collapse_spaces(normalized_text.replace("-", " "))
    if not normalized_text:
        return None

    pattern = re.compile(
        r"\b(?:"
        + "|".join(DRAPP_WEEKDAY_NAMES)
        + r")?\s*(\d{1,2})(?:\s+DE)?\s+([A-Z]+)\s+(\d{4})\b"
    )
    match = pattern.search(normalized_text)
    if not match:
        return None

    day_value = int(match.group(1))
    month_value = DRAPP_MONTH_MAP.get(match.group(2))
    year_value = int(match.group(3))
    if not month_value:
        return None
    try:
        return date(year_value, month_value, day_value)
    except ValueError:
        return None


def extract_drapp_rows_from_text(raw_text: str):
    rows = []
    agenda_date = parse_drapp_agenda_date(raw_text)
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith("profesional\tpaciente\tcobertura"):
            continue
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 5:
            continue
        _, patient_raw, coverage_raw, practice_raw, datetime_raw, *_ = parts + [""] * (6 - len(parts))
        rows.append(
            {
                "patient_name": normalize_imported_name(patient_raw),
                "coverage_raw": coverage_raw,
                "practice_raw": practice_raw,
                "datetime_raw": datetime_raw,
                "phone": "",
                "dni": "",
                "agenda_date": agenda_date,
            }
        )
    return rows


def build_ocr_lines_from_image(image_path: str):
    result, _ = get_ocr_engine()(str(image_path))
    items = []
    for box, text, score in result or []:
        x = sum(point[0] for point in box) / 4
        y = sum(point[1] for point in box) / 4
        cleaned_text = collapse_spaces(text)
        if not cleaned_text:
            continue
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
    lines = []
    tolerance = 24
    for item in items:
        if not lines or abs(lines[-1]["y"] - item["y"]) > tolerance:
            lines.append({"y": item["y"], "items": [item]})
        else:
            lines[-1]["items"].append(item)
    for line in lines:
        line["items"].sort(key=lambda item: item["x"])
        line["text"] = collapse_spaces(" ".join(item["text"] for item in line["items"]))
        line["norm"] = normalize_for_match(line["text"])
    return lines


def extract_drapp_rows_from_ocr_lines(lines):
    rows = []
    agenda_date = parse_drapp_agenda_date(" ".join(line.get("text", "") for line in lines[:8]))
    current = None
    time_pattern = re.compile(r"\b(\d{1,2}:\d{2})\b")
    dni_pattern = re.compile(r"\b\d{1,3}(?:[.\s]\d{3}){1,3}\b|\b\d{7,8}\b")

    for line in lines:
        match = time_pattern.search(line["text"])
        if match:
            if current:
                rows.append(current)
            line_without_time = time_pattern.sub("", line["text"]).strip(" -|")
            current = {
                "datetime_raw": match.group(1),
                "patient_name": "",
                "coverage_raw": "",
                "practice_raw": "",
                "phone": "",
                "dni": "",
                "raw_lines": [line_without_time] if line_without_time else [],
            }
            continue
        if current:
            current["raw_lines"].append(line["text"])
    if current:
        rows.append(current)

    parsed_rows = []
    for row in rows:
        combined_text = " | ".join(row["raw_lines"])
        upper_text = combined_text.upper()
        if not any(hint in normalize_for_match(upper_text) for hint in DRAPP_PRACTICE_HINTS):
            continue

        phone = ""
        phone_match_text = ""
        for raw_phone in re.findall(r"\+?\d[\d ]{7,16}", combined_text):
            normalized_phone = normalize_phone_number(raw_phone)
            if 10 <= len(normalized_phone.replace("+", "")) <= 13:
                phone = normalized_phone
                phone_match_text = raw_phone
                break

        text_without_phone = combined_text.replace(phone_match_text, " ") if phone_match_text else combined_text
        dni = ""
        for candidate in dni_pattern.findall(text_without_phone):
            normalized_dni = normalize_document_number(candidate)
            if 7 <= len(normalized_dni) <= 8:
                dni = normalized_dni
                break

        coverage_raw = ""
        coverage_candidates = ["PARTICULAR", "PAMI", "DOSEP", "OSDE", "SWISS MEDICAL", "MEDIFE", "OSECAC", "IOSFA"]
        for candidate in coverage_candidates:
            if candidate in upper_text:
                coverage_raw = candidate.title() if candidate == "PARTICULAR" else candidate
                break

        practice_raw = ""
        if "CICLOESPIROMETRIA" in normalize_for_match(upper_text):
            practice_raw = "Cicloespirometria"
        elif "CICLO" in upper_text and "ESPIRO" in upper_text:
            practice_raw = "Cicloespirometria"
        elif "ESPIRO" in upper_text:
            practice_raw = "Espirometria"

        patient_name = ""
        first_line = row["raw_lines"][0] if row["raw_lines"] else ""
        first_line = re.sub(r"\b\d{1,2}:\d{2}\b", "", first_line).strip(" -|")
        if coverage_raw:
            coverage_index = first_line.upper().find(coverage_raw.upper())
            if coverage_index > 0:
                patient_name = first_line[:coverage_index].strip(" -|,")
        if not patient_name and practice_raw:
            practice_index = normalize_for_match(first_line).find(normalize_for_match(practice_raw))
            if practice_index > 0:
                patient_name = first_line[:practice_index].strip(" -|,")
        if not patient_name:
            second_line = row["raw_lines"][1] if len(row["raw_lines"]) > 1 else ""
            patient_name = first_line or second_line
        patient_name = normalize_imported_name(patient_name)
        if not patient_name or normalize_for_match(patient_name) in DRAPP_ROW_SKIP_WORDS:
            continue

        parsed_rows.append(
            {
                "patient_name": patient_name,
                "coverage_raw": coverage_raw,
                "practice_raw": practice_raw,
                "datetime_raw": row["datetime_raw"],
                "phone": phone,
                "dni": dni,
                "agenda_date": agenda_date,
            }
        )
    return parsed_rows


def extract_drapp_rows_from_screenshot(uploaded_file):
    suffix = Path(uploaded_file.name or "drapp.png").suffix or ".png"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name
    try:
        lines = build_ocr_lines_from_image(temp_path)
        return extract_drapp_rows_from_ocr_lines(lines)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def extract_drapp_rows_from_browser_ocr(raw_payload: str):
    try:
        payload = json.loads(raw_payload or "[]")
    except json.JSONDecodeError as error:
        raise ValueError(f"El OCR del navegador devolvio un formato invalido: {error}") from error

    lines = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        text = collapse_spaces(item.get("text", ""))
        if not text:
            continue
        try:
            y_coord = float(item.get("y", index * 30))
        except (TypeError, ValueError):
            y_coord = float(index * 30)
        lines.append({"text": text, "y": y_coord, "norm": normalize_for_match(text), "items": []})
    return extract_drapp_rows_from_ocr_lines(lines)


def import_drapp_rows(rows, request_user):
    created = 0
    skipped = 0
    default_physician = get_default_physician()
    seen_keys = set()

    for row in rows:
        patient_name = normalize_imported_name(row.get("patient_name", ""))
        if not patient_name:
            skipped += 1
            continue

        try:
            raw_datetime = str(row.get("datetime_raw", "") or "").strip()
            if re.match(r"^\d{1,2}:\d{2}$", raw_datetime):
                when = datetime.strptime(raw_datetime, "%H:%M")
                encounter_date = row.get("agenda_date") or timezone.localdate()
            else:
                when = datetime.strptime(raw_datetime.replace(" - ", " "), "%Y-%m-%d %H:%M")
                encounter_date = when.date()
        except ValueError:
            skipped += 1
            continue

        study_type = infer_study_type(row.get("practice_raw", ""))
        parsed_dni = normalize_document_number(row.get("dni", ""))
        patient = Patient.objects.filter(dni=parsed_dni).first() if parsed_dni else None
        if patient is None:
            patient = Patient.objects.filter(full_name=patient_name).order_by("-updated_at").first()
        if patient is None:
            patient = Patient.objects.create(
                full_name=patient_name,
                dni=parsed_dni or None,
                phone=normalize_phone_number(row.get("phone", "")),
            )
        else:
            updated_fields = []
            if parsed_dni and patient.dni != parsed_dni:
                patient.dni = parsed_dni
                updated_fields.append("dni")
            incoming_phone = normalize_phone_number(row.get("phone", ""))
            if incoming_phone and patient.phone != incoming_phone:
                patient.phone = incoming_phone
                updated_fields.append("phone")
            if updated_fields:
                updated_fields.append("updated_at")
                patient.save(update_fields=updated_fields)

        identity_key = parsed_dni or normalize_for_match(getattr(patient, "full_name", "") or patient_name)
        duplicate_key = (
            encounter_date.isoformat(),
            when.time().isoformat(),
            study_type,
            identity_key,
        )
        if duplicate_key in seen_keys:
            skipped += 1
            continue
        seen_keys.add(duplicate_key)

        duplicate_queryset = Encounter.objects.filter(
            encounter_date=encounter_date,
            encounter_time=when.time(),
            study_type=study_type,
        )
        if parsed_dni:
            duplicate_queryset = duplicate_queryset.filter(patient__dni=parsed_dni)
        else:
            duplicate_queryset = duplicate_queryset.filter(patient=patient)
        duplicate = duplicate_queryset.exists()
        if duplicate:
            skipped += 1
            continue

        created_encounter = Encounter.objects.create(
            patient=patient,
            encounter_date=encounter_date,
            encounter_time=when.time(),
            study_type=study_type,
            status=EncounterStatus.PENDIENTE,
            coverage_type=infer_coverage_type(row.get("coverage_raw", "")),
            referring_physician=default_physician,
            attended=False,
            no_show=False,
            created_by=request_user,
            updated_by=request_user,
        )
        if created_encounter:
            record_encounter_event(
                created_encounter,
                EncounterEventType.IMPORT,
                "Paciente importado desde Drapp",
                actor=request_user,
                details=(
                    f"Fecha agenda: {encounter_date:%d/%m/%Y} | Hora: {when.time():%H:%M} | "
                    f"Cobertura: {infer_coverage_type(row.get('coverage_raw', ''))}"
                ),
                metadata={
                    "source": "drapp",
                    "practice_raw": row.get("practice_raw", ""),
                    "coverage_raw": row.get("coverage_raw", ""),
                },
            )
        created += 1

    return created, skipped


def format_month_label(value: date) -> str:
    return f"{SPANISH_MONTHS[value.month - 1]} {value.year}"


def format_day_label(value: date) -> str:
    weekday = SPANISH_WEEKDAYS[value.weekday()]
    return f"{weekday} {value.day:02d}/{value.month:02d}/{value.year}"


def get_period_summary(queryset):
    total = queryset.count()
    mutual = queryset.filter(coverage_type=CoverageType.MUTUAL).count()
    attended = queryset.filter(attended=True).count()
    no_show = queryset.filter(no_show=True).count()
    cyclometry = queryset.filter(study_type="Ciclometria").count()
    spirometry = queryset.filter(study_type="Espirometria").count()
    return {
        "total": total,
        "mutual": mutual,
        "particular": queryset.filter(coverage_type=CoverageType.PARTICULAR).count(),
        "attended": attended,
        "no_show": no_show,
        "pending": max(total - attended - no_show, 0),
        "cyclometry": cyclometry,
        "spirometry": spirometry,
        "mutual_percent": round((mutual / total) * 100) if total else 0,
        "attendance_percent": round((attended / total) * 100) if total else 0,
    }


def percent(part: int, total: int) -> int:
    return round((part / total) * 100) if total else 0


def format_average(number, digits: int = 1) -> str:
    if number is None:
        return "-"
    return f"{number:.{digits}f}".replace(".", ",")


def normalize_gender_bucket(raw_value: str) -> str:
    text = str(raw_value or "").strip().lower()
    if not text:
        return "Sin dato"
    if "femen" in text or text == "mujer":
        return "Femenino"
    if "mascul" in text or text == "hombre":
        return "Masculino"
    return collapse_spaces(raw_value)


def normalize_smoking_bucket(raw_value: str) -> str:
    text = str(raw_value or "").strip().lower()
    if not text:
        return "Sin dato"
    if "ex" in text and "fum" in text:
        return "Ex fumador"
    if "no" in text and "fum" in text:
        return "No fumador"
    if "fum" in text:
        return "Fumador"
    return collapse_spaces(raw_value)


def build_count_rows(values):
    counter = {}
    for value in values:
        counter[value] = counter.get(value, 0) + 1
    return [
        {"label": label, "total": total}
        for label, total in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_patient_profile_summary(patients):
    patients = list(patients)
    total = len(patients)
    if total == 0:
        return {
            "total": 0,
            "women": 0,
            "men": 0,
            "smokers": 0,
            "with_birth_date": 0,
            "women_percent": 0,
            "men_percent": 0,
            "smokers_percent": 0,
            "avg_age": "-",
            "avg_height": "-",
            "avg_weight": "-",
            "avg_bmi": "-",
            "avg_pack_years": "-",
            "gender_rows": [],
            "smoking_rows": [],
            "ethnicity_rows": [],
            "profile_completion_percent": 0,
        }

    genders = [normalize_gender_bucket(patient.gender) for patient in patients]
    smoking = [normalize_smoking_bucket(patient.smoking_status) for patient in patients]
    ethnicities = [collapse_spaces(patient.ethnicity) or "Sin dato" for patient in patients]

    women = sum(1 for value in genders if value == "Femenino")
    men = sum(1 for value in genders if value == "Masculino")
    smokers = sum(1 for value in smoking if value == "Fumador")

    ages = [patient.age_reported for patient in patients if patient.age_reported is not None]
    heights = [patient.height_cm for patient in patients if patient.height_cm is not None]
    weights = [float(patient.weight_kg) for patient in patients if patient.weight_kg is not None]
    bmis = [float(patient.bmi) for patient in patients if patient.bmi is not None]
    pack_years = [float(patient.pack_years) for patient in patients if patient.pack_years is not None]

    completed_profiles = 0
    for patient in patients:
        required_points = [
            bool(patient.patient_code or patient.dni),
            bool(patient.full_name),
            patient.birth_date is not None or patient.age_reported is not None,
            bool(patient.gender),
            patient.height_cm is not None,
            patient.weight_kg is not None,
        ]
        if sum(1 for point in required_points if point) >= 5:
            completed_profiles += 1

    return {
        "total": total,
        "women": women,
        "men": men,
        "smokers": smokers,
        "with_birth_date": sum(1 for patient in patients if patient.birth_date is not None),
        "women_percent": percent(women, total),
        "men_percent": percent(men, total),
        "smokers_percent": percent(smokers, total),
        "avg_age": format_average(mean(ages), 1) if ages else "-",
        "avg_height": format_average(mean(heights), 1) if heights else "-",
        "avg_weight": format_average(mean(weights), 1) if weights else "-",
        "avg_bmi": format_average(mean(bmis), 2) if bmis else "-",
        "avg_pack_years": format_average(mean(pack_years), 1) if pack_years else "-",
        "gender_rows": build_count_rows(genders),
        "smoking_rows": build_count_rows(smoking),
        "ethnicity_rows": build_count_rows(ethnicities)[:6],
        "profile_completion_percent": percent(completed_profiles, total),
    }


SEVERITY_RANK = {
    "Leve": 1,
    "Moderada": 2,
    "Moderadamente severa": 3,
    "Severa": 4,
}


def get_result_severity_score(encounter) -> int | None:
    code = get_result_code_from_encounter(encounter)
    parsed = parse_result_code(code)
    if not parsed:
        return None
    if parsed["canonical_code"] == "N":
        return 0
    restriction_score = SEVERITY_RANK.get(parsed["restriction_grade"], 0)
    obstruction_score = SEVERITY_RANK.get(parsed["obstruction_grade"], 0)
    if parsed["pattern"] == "Mixto":
        return max(restriction_score, obstruction_score) + min(restriction_score, obstruction_score)
    return max(restriction_score, obstruction_score)


def get_measured_metric(result, metric_name: str, key: str):
    if not result:
        return None
    values = result.measured_values or {}
    metric_values = values.get(metric_name, {})
    try:
        value = metric_values.get(key)
    except AttributeError:
        return None
    return value


def describe_progression(previous_encounter, current_encounter):
    previous_result = getattr(previous_encounter, "spirometry_result", None)
    current_result = getattr(current_encounter, "spirometry_result", None)
    if not previous_result or not current_result:
        return {"label": "Sin base", "tone": "muted", "detail": "Todavia no hay dos estudios comparables."}

    previous_score = get_result_severity_score(previous_encounter)
    current_score = get_result_severity_score(current_encounter)
    previous_fev1 = get_measured_metric(previous_result, "fev1", "percent")
    current_fev1 = get_measured_metric(current_result, "fev1", "percent")

    if previous_score is not None and current_score is not None and current_score < previous_score:
        return {"label": "Mejoro", "tone": "ok", "detail": "El patron actual es menos severo que el estudio previo."}
    if previous_score is not None and current_score is not None and current_score > previous_score:
        return {"label": "Empeoro", "tone": "warn", "detail": "El patron actual es mas severo que el estudio previo."}
    if previous_fev1 is not None and current_fev1 is not None:
        delta = float(current_fev1) - float(previous_fev1)
        if delta >= 8:
            return {
                "label": "Mejoro",
                "tone": "ok",
                "detail": f"FEV1 % subio {delta:.1f} puntos frente al estudio previo.",
            }
        if delta <= -8:
            return {
                "label": "Empeoro",
                "tone": "warn",
                "detail": f"FEV1 % bajo {abs(delta):.1f} puntos frente al estudio previo.",
            }
    return {"label": "Estable", "tone": "muted", "detail": "No hay cambios clinicos marcados respecto del estudio previo."}


def get_patient_age_value(patient) -> int | None:
    if patient.age_reported is not None:
        return int(patient.age_reported)
    if patient.birth_date:
        today = timezone.localdate()
        return today.year - patient.birth_date.year - (
            (today.month, today.day) < (patient.birth_date.month, patient.birth_date.day)
        )
    return None


def get_latest_coded_encounter(patient):
    encounters = sorted(
        [
            encounter
            for encounter in patient.encounters.all()
            if get_result_code_from_encounter(encounter)
        ],
        key=lambda encounter: (
            encounter.encounter_date or date.min,
            encounter.encounter_time or datetime.min.time(),
            encounter.created_at,
        ),
        reverse=True,
    )
    return encounters[0] if encounters else None


def build_diagnosis_distribution(encounters):
    rows = []
    counter = {}
    for encounter in encounters:
        code = get_result_code_from_encounter(encounter) or "Sin carga"
        counter[code] = counter.get(code, 0) + 1
    total = sum(counter.values())
    for code, quantity in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "code": code,
                "label": get_result_label_for_code(code),
                "total": quantity,
                "percent": percent(quantity, total),
            }
        )
    return rows


def build_cohort_statistics(patients):
    latest_encounters = []
    for patient in patients:
        latest = get_latest_coded_encounter(patient)
        if latest:
            latest_encounters.append(latest)

    cohorts = [
        ("Hombres 60+", lambda patient: normalize_gender_bucket(patient.gender) == "Masculino" and (get_patient_age_value(patient) or -1) >= 60),
        ("Mujeres 60+", lambda patient: normalize_gender_bucket(patient.gender) == "Femenino" and (get_patient_age_value(patient) or -1) >= 60),
        ("40 a 59 años", lambda patient: 40 <= (get_patient_age_value(patient) or -1) <= 59),
        ("Menores de 40", lambda patient: 0 <= (get_patient_age_value(patient) or -1) < 40),
        ("Fumadores", lambda patient: normalize_smoking_bucket(patient.smoking_status) == "Fumador"),
        ("No fumadores", lambda patient: normalize_smoking_bucket(patient.smoking_status) == "No fumador"),
    ]

    rows = []
    for label, matcher in cohorts:
        encounters = [encounter for encounter in latest_encounters if matcher(encounter.patient)]
        total = len(encounters)
        diagnosis_rows = build_diagnosis_distribution(encounters)
        top_row = diagnosis_rows[0] if diagnosis_rows else None
        abnormal = sum(1 for encounter in encounters if (get_result_code_from_encounter(encounter) or "") not in {"", "N"})
        rows.append(
            {
                "label": label,
                "total": total,
                "abnormal_percent": percent(abnormal, total),
                "top_code": top_row["code"] if top_row else "-",
                "top_percent": top_row["percent"] if top_row else 0,
                "top_label": top_row["label"] if top_row else "Sin datos",
            }
        )
    return rows, build_diagnosis_distribution(latest_encounters)


def get_encounter_inconsistencies(encounter):
    patient = encounter.patient
    vital = getattr(encounter, "vital_signs", None)
    attachments = encounter.attachments.all() if hasattr(encounter, "attachments") else []
    flags = []

    if encounter.study_type == "Espirometria":
        result_attachment = next(
            (item for item in attachments if item.file_kind in [AttachmentKind.PDF_RESULTADO, AttachmentKind.FOTO_RESULTADO]),
            None,
        )
        if result_attachment and not (patient.dni or patient.patient_code or patient.birth_date):
            flags.append("Resultado incompleto: faltan identificadores del paciente")

    if vital:
        impossible_values = []
        if vital.so2_rest is not None and (vital.so2_rest < 50 or vital.so2_rest > 99):
            impossible_values.append("SO2 reposo")
        if vital.so2_post is not None and (vital.so2_post < 50 or vital.so2_post > 99):
            impossible_values.append("SO2 post")
        if vital.fc_rest is not None and (vital.fc_rest < 20 or vital.fc_rest > 250):
            impossible_values.append("FC reposo")
        if vital.fc_post is not None and (vital.fc_post < 20 or vital.fc_post > 250):
            impossible_values.append("FC post")
        if impossible_values:
            flags.append("Valores imposibles: " + ", ".join(impossible_values))

    return flags


def build_inconsistency_message(encounter):
    flags = get_encounter_inconsistencies(encounter)
    if not flags:
        return ""
    return "Advertencias: " + " | ".join(flags)


def get_report_readiness(encounter):
    if encounter.no_show:
        return False, "No llego"

    patient = encounter.patient
    vital = getattr(encounter, "vital_signs", None)
    result_code = get_result_code_from_encounter(encounter)

    missing = []
    if not str(getattr(patient, "full_name", "") or "").strip():
        missing.append("nombre")
    if not str(getattr(patient, "dni", "") or "").strip():
        missing.append("DNI")
    if getattr(vital, "so2_rest", None) is None:
        missing.append("SO2 reposo")
    if getattr(vital, "fc_rest", None) is None:
        missing.append("FC reposo")
    if encounter.study_type == "Ciclometria":
        if getattr(vital, "so2_post", None) is None:
            missing.append("SO2 post")
        if getattr(vital, "fc_post", None) is None:
            missing.append("FC post")
    if not result_code:
        missing.append("resultado")

    if missing:
        return False, "Completar: " + ", ".join(missing)
    return True, ""


def build_print_context_for_encounter(encounter):
    patient = encounter.patient
    vital = getattr(encounter, "vital_signs", None)
    walk = getattr(encounter, "walk_test", None)
    result = getattr(encounter, "spirometry_result", None)

    patron = normalizar_patron(getattr(result, "respiratory_pattern", "Normal"))
    grado_obst = (getattr(result, "obstruction_grade", "") or "Leve").strip().lower()
    grado_rest = (getattr(result, "restriction_grade", "") or "Leve").strip().lower()
    informe = construir_informe_espirometria(patron, grado_obst, grado_rest)
    broncodilatador_positivo = bool(getattr(result, "bronchodilator_positive", False))

    so2 = limpiar_entero(getattr(vital, "so2_rest", "0"))
    fc = limpiar_entero(getattr(vital, "fc_rest", "0"))
    include_walk = encounter.study_type == "Ciclometria"
    walk_rows = []
    if include_walk:
        so2_reposo = int(so2)
        so2_regreso = int(limpiar_entero(getattr(vital, "so2_post", "100"), "100"))
        fc_reposo = int(fc)
        fc_maximo = int(limpiar_entero(getattr(vital, "fc_post", "120"), "120"))
        borg_final = int(getattr(walk, "borg_final", 0) or 0)
        so2_vals = interpolar_valores(so2_reposo, so2_regreso, 7)
        fc_vals = interpolar_valores(fc_reposo, fc_maximo, 7)
        borg_vals = interpolar_valores(0, borg_final, 7) if borg_final > 0 else [0, 0, 0, 0, 0, 0, 1]
        walk_rows = [
            {
                "minute": minute,
                "so2": so2_vals[minute],
                "fc": fc_vals[minute],
                "borg": borg_vals[minute],
            }
            for minute in range(7)
        ]

    pdf_attachment = get_latest_result_attachment(encounter)
    pdf_preview_pages = build_result_preview_images(pdf_attachment) if pdf_attachment else []
    include_mutual_packet = encounter.coverage_type == CoverageType.MUTUAL and include_walk

    return {
        "encounter": encounter,
        "patient_name": str(patient.full_name or "").strip().upper(),
        "dni": formatear_dni(patient.dni),
        "doctor_name": normalizar_medico(getattr(encounter.referring_physician, "full_name", DEFAULT_DOCTOR)),
        "print_date": encounter.encounter_date.strftime("%d/%m/%Y"),
        "so2": so2,
        "fc": fc,
        "report_text": informe,
        "bronchodilator_positive": broncodilatador_positivo,
        "pattern": patron,
        "include_walk": include_walk,
        "walk_rows": walk_rows,
        "distance": str(getattr(walk, "distance_meters", "") or "200"),
        "completed": bool(getattr(walk, "completed", True)),
        "stopped": bool(getattr(walk, "stopped", False)),
        "symptoms": bool(getattr(walk, "symptoms", False)),
        "include_mutual_packet": include_mutual_packet,
        "mutual_cvl_result": build_mutual_cvl_result(patron, grado_obst, grado_rest),
        "pdf_preview_pages": pdf_preview_pages,
        "pdf_attachment": pdf_attachment,
    }


def render_dashboard_response(
    request,
    *,
    today,
    quick_form,
    import_form,
    physician_form,
    today_encounters,
    status_cards,
    operation_alerts,
):
    context = {
        "today": today,
        "today_encounters": today_encounters,
        "status_cards": status_cards,
        "quick_form": quick_form,
        "import_form": import_form,
        "physician_form": physician_form,
        "study_choices": [choice for choice in QuickEncounterForm.base_fields["study_type"].choices],
        "coverage_choices": [("Mutual", "Mutual"), ("Particular", "Particular")],
        "physician_choices": ReferringPhysician.objects.filter(active=True).order_by("full_name"),
        "result_code_suggestions": RESULT_CODE_SUGGESTIONS,
        "operation_alerts": operation_alerts,
    }
    return render(request, "clinic/dashboard.html", context)


@login_required
def dashboard(request):
    today = timezone.localdate()
    quick_initial = {
        "study_type": "Ciclometria",
        "coverage_type": "Particular",
        "distance_meters": 200,
        "completed": True,
        "borg_final": 0,
        "attended": False,
        "no_show": False,
    }
    today_encounters = (
        Encounter.objects.select_related("patient", "referring_physician", "vital_signs", "spirometry_result")
        .prefetch_related("generated_reports__attachment")
        .filter(encounter_date=today)
        .order_by("created_at")
    )
    for encounter in today_encounters:
        encounter.result_code = get_result_code_from_encounter(encounter)
        encounter.can_generate_report, encounter.report_block_reason = get_report_readiness(encounter)
        encounter.has_generated_reports = len(encounter.generated_reports.all()) > 0
        encounter.has_cycle_data = encounter_has_cycle_data(encounter)
        latest_report_info = get_latest_report_info(encounter)
        encounter.latest_report_url = latest_report_info["latest_report_url"]
        encounter.latest_report_name = latest_report_info["latest_report_name"]
        encounter.complete_report_url = latest_report_info["complete_report_url"]
        encounter.mutual_report_url = latest_report_info["mutual_report_url"]
        encounter.detail_url = latest_report_info["detail_url"]
    stats = Encounter.objects.filter(encounter_date=today).values("status").annotate(total=Count("id"))
    stats_map = {item["status"]: item["total"] for item in stats}
    status_cards = [
        {"value": value, "label": label, "total": stats_map.get(value, 0)}
        for value, label in EncounterStatus.choices
    ]
    operation_alerts = get_operational_alerts(Encounter.objects.filter(encounter_date=today))

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "import_drapp":
            import_form = DrappImportForm(request.POST, request.FILES)
            quick_form = QuickEncounterForm(initial=quick_initial)
            physician_form = ReferringPhysicianForm(initial={"active": True})
            if import_form.is_valid():
                imported_rows = []
                raw_text = import_form.cleaned_data.get("raw_text", "")
                ocr_lines_json = import_form.cleaned_data.get("ocr_lines_json", "")
                screenshot = import_form.cleaned_data.get("screenshot")
                if raw_text:
                    imported_rows.extend(extract_drapp_rows_from_text(raw_text))
                if ocr_lines_json:
                    imported_rows.extend(extract_drapp_rows_from_browser_ocr(ocr_lines_json))
                elif screenshot:
                    try:
                        imported_rows.extend(extract_drapp_rows_from_screenshot(screenshot))
                    except Exception as error:
                        import_form.add_error(
                            "screenshot",
                            f"No se pudo leer la captura automaticamente: {error}",
                        )
                        messages.warning(
                            request,
                            "La captura no se pudo leer automaticamente. Pega el texto de Drapp y volve a importar.",
                        )
                        return render_dashboard_response(
                            request,
                            today=today,
                            quick_form=quick_form,
                            import_form=import_form,
                            physician_form=physician_form,
                            today_encounters=today_encounters,
                            status_cards=status_cards,
                            operation_alerts=operation_alerts,
                        )
                created, skipped = import_drapp_rows(imported_rows, request.user)
                messages.success(
                    request,
                    f"Drapp importado: {created} paciente(s) agregados, {skipped} fila(s) omitidas.",
                )
                return redirect("clinic:dashboard")
        elif action == "add_physician":
            physician_form = ReferringPhysicianForm(request.POST)
            quick_form = QuickEncounterForm(initial=quick_initial)
            import_form = DrappImportForm()
            if physician_form.is_valid():
                physician = physician_form.save(commit=False)
                physician.full_name = collapse_spaces(physician.full_name)
                if physician.is_default:
                    ReferringPhysician.objects.filter(is_default=True).update(is_default=False)
                physician.save()
                messages.success(request, f"Doctor derivante agregado: {physician.full_name}")
                return redirect("clinic:dashboard")
        elif action == "update_dni":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            encounter_id = request.POST.get("encounter_id")
            new_dni = (request.POST.get("patient_dni") or "").strip()
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
                .prefetch_related("generated_reports"),
                pk=encounter_id,
            )
            patient, reassigned = assign_encounter_patient_by_dni(encounter, new_dni)
            encounter.refresh_from_db()
            if is_ajax_request(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "patient_dni": encounter.patient.dni or "",
                        "patient_dni_display": encounter.patient.dni or "Completar DNI",
                        "message": "Historia clinica unificada por DNI." if reassigned else "",
                        **get_row_state_payload(encounter),
                    }
                )
            if reassigned:
                messages.success(request, f"DNI actualizado. La atencion quedo unificada con la historia de {patient.full_name}.")
            else:
                messages.success(request, f"DNI actualizado para {patient.full_name}.")
            return redirect("clinic:dashboard")
        elif action == "inline_update":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
                .prefetch_related("generated_reports"),
                pk=request.POST.get("encounter_id"),
            )
            update_inline_field(
                encounter=encounter,
                field_name=request.POST.get("field_name", ""),
                raw_value=request.POST.get("value", ""),
                request_user=request.user,
            )
            encounter.refresh_from_db()
            if is_ajax_request(request):
                payload = {
                    "ok": True,
                    "field_name": request.POST.get("field_name", ""),
                    "value": request.POST.get("value", ""),
                }
                payload.update(get_row_state_payload(encounter))
                if payload["field_name"] == "patient_name":
                    payload["value"] = encounter.patient.full_name
                elif payload["field_name"] == "coverage_type":
                    payload["value"] = encounter.coverage_type
                elif payload["field_name"] == "referring_physician":
                    payload["value"] = str(encounter.referring_physician_id or "")
                elif payload["field_name"] == "encounter_time":
                    payload["value"] = encounter.encounter_time.strftime("%H:%M") if encounter.encounter_time else ""
                elif payload["field_name"] == "study_type":
                    payload["value"] = encounter.study_type
                elif payload["field_name"] == "respiratory_result":
                    payload["value"] = get_result_code_from_encounter(encounter)
                elif payload["field_name"] == "patient_dni":
                    payload["value"] = encounter.patient.dni or ""
                elif payload["field_name"] in ["so2_rest", "fc_rest", "so2_post", "fc_post"]:
                    payload["value"] = payload.get(payload["field_name"], "")
                return JsonResponse(payload)
            return redirect("clinic:dashboard")
        elif action == "toggle_attendance":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
                .prefetch_related("generated_reports"),
                pk=request.POST.get("encounter_id"),
            )
            cycle_attendance(encounter, request.user)
            if is_ajax_request(request):
                payload = {"ok": True, "attended": encounter.attended, "no_show": encounter.no_show}
                payload.update(get_row_state_payload(encounter))
                return JsonResponse(payload)
            return redirect("clinic:dashboard")
        elif action == "delete_encounter":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient"),
                pk=request.POST.get("encounter_id"),
            )
            encounter_id = encounter.pk
            patient_name = encounter.patient.full_name
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                "Atencion eliminada de la agenda",
                actor=request.user,
                details=f"Se elimino la atencion del dia para {patient_name}.",
            )
            encounter.delete()
            if is_ajax_request(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "deleted": True,
                        "encounter_id": encounter_id,
                        "message": f"Se elimino {patient_name} de la agenda.",
                    }
                )
            messages.success(request, f"Se elimino {patient_name} de la agenda.")
            return redirect("clinic:dashboard")
        else:
            quick_form = QuickEncounterForm(request.POST)
            import_form = DrappImportForm()
            physician_form = ReferringPhysicianForm(initial={"active": True})
            if quick_form.is_valid():
                encounter = save_quick_encounter(quick_form, request.user)
                messages.success(request, f"Paciente agendado: {encounter.patient.full_name}")
                return redirect("clinic:dashboard")
    else:
        quick_form = QuickEncounterForm(initial=quick_initial)
        import_form = DrappImportForm()
        physician_form = ReferringPhysicianForm(initial={"active": True})

    return render_dashboard_response(
        request,
        today=today,
        quick_form=quick_form,
        import_form=import_form,
        physician_form=physician_form,
        today_encounters=today_encounters,
        status_cards=status_cards,
        operation_alerts=operation_alerts,
    )


@login_required
def dashboard_rows_state(request):
    today = timezone.localdate()
    encounters = (
        Encounter.objects.select_related("patient", "referring_physician", "spirometry_result", "vital_signs", "walk_test")
        .prefetch_related("generated_reports__attachment")
        .filter(encounter_date=today)
        .order_by("created_at")
    )
    rows = [get_row_state_payload(encounter) for encounter in encounters]
    return JsonResponse(
        {
            "ok": True,
            "date": today.isoformat(),
            "rows": rows,
            "checked_at": timezone.now().isoformat(),
        }
    )


@login_required
def calendar_view(request):
    today = timezone.localdate()
    default_off_weekdays = {0, 2, 5, 6}
    month_param = (request.GET.get("month") or "").strip()
    date_param = (request.GET.get("date") or "").strip()

    try:
        if month_param:
            current_month = datetime.strptime(month_param, "%Y-%m").date().replace(day=1)
        else:
            current_month = today.replace(day=1)
    except ValueError:
        current_month = today.replace(day=1)

    try:
        selected_date = datetime.strptime(date_param, "%Y-%m-%d").date() if date_param else today
    except ValueError:
        selected_date = today

    if request.method == "POST" and request.POST.get("action") == "delete_encounter":
        encounter = get_object_or_404(
            Encounter.objects.select_related("patient"),
            pk=request.POST.get("encounter_id"),
        )
        patient_name = encounter.patient.full_name
        encounter.delete()
        messages.success(request, f"Se elimino {patient_name} de la agenda.")
        redirect_month = request.POST.get("month") or selected_date.strftime("%Y-%m")
        redirect_date = request.POST.get("date") or selected_date.isoformat()
        return redirect(f"{reverse('clinic:calendar')}?month={redirect_month}&date={redirect_date}")

    previous_month = (current_month - timedelta(days=1)).replace(day=1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)

    calendar_weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(
        current_month.year,
        current_month.month,
    )
    range_start = calendar_weeks[0][0]
    range_end = calendar_weeks[-1][-1]

    calendar_encounters = (
        Encounter.objects.select_related("patient", "vital_signs", "spirometry_result")
        .filter(encounter_date__range=(range_start, range_end))
        .order_by("encounter_date", "encounter_time", "created_at")
    )

    encounters_by_date = {}
    for encounter in calendar_encounters:
        day_bucket = encounters_by_date.setdefault(
            encounter.encounter_date,
            {"encounters": [], "total": 0, "attended": 0, "no_show": 0, "mutual": 0},
        )
        day_bucket["encounters"].append(encounter)
        day_bucket["total"] += 1
        if encounter.attended:
            day_bucket["attended"] += 1
        if encounter.no_show:
            day_bucket["no_show"] += 1
        if encounter.coverage_type == "Mutual":
            day_bucket["mutual"] = day_bucket.get("mutual", 0) + 1

    weeks = []
    for week in calendar_weeks:
        week_days = []
        for day_value in week:
            info = encounters_by_date.get(
                day_value,
                {"encounters": [], "total": 0, "attended": 0, "no_show": 0, "mutual": 0},
            )
            pending_total = max(info["total"] - info["attended"] - info["no_show"], 0)
            week_days.append(
                {
                    "date": day_value,
                    "day_number": day_value.day,
                    "iso": day_value.isoformat(),
                    "month_param": day_value.strftime("%Y-%m"),
                    "in_month": day_value.month == current_month.month,
                    "is_today": day_value == today,
                    "is_selected": day_value == selected_date,
                    "is_default_offday": day_value.weekday() in default_off_weekdays,
                    "total": info["total"],
                    "attended": info["attended"],
                    "no_show": info["no_show"],
                    "mutual": info["mutual"],
                    "pending": pending_total,
                    "all_attended": info["total"] > 0 and info["attended"] == info["total"],
                }
            )
        weeks.append(week_days)

    selected_encounters = (
        Encounter.objects.select_related("patient", "vital_signs", "spirometry_result")
        .filter(encounter_date=selected_date)
        .order_by("encounter_time", "created_at")
    )
    for encounter in selected_encounters:
        encounter.result_label = get_result_label_from_encounter(encounter)
        encounter.attendance_label = get_attendance_label(encounter)

    selected_summary = get_period_summary(Encounter.objects.filter(encounter_date=selected_date))
    selected_summary["pending"] = max(
        selected_summary["total"] - selected_summary["attended"] - selected_summary["no_show"],
        0,
    )
    selected_summary["is_default_offday"] = selected_date.weekday() in default_off_weekdays

    context = {
        "today": today,
        "current_month": current_month,
        "current_month_label": format_month_label(current_month),
        "current_month_param": current_month.strftime("%Y-%m"),
        "previous_month_param": previous_month.strftime("%Y-%m"),
        "next_month_param": next_month.strftime("%Y-%m"),
        "selected_date": selected_date,
        "selected_date_label": format_day_label(selected_date),
        "weekday_labels": SPANISH_WEEKDAYS,
        "calendar_weeks": weeks,
        "selected_encounters": selected_encounters,
        "selected_summary": selected_summary,
        "default_offday_labels": ["Lunes", "Miercoles", "Sabado", "Domingo"],
    }
    return render(request, "clinic/calendar.html", context)


@login_required
def statistics_view(request):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    periods = [
        {
            "key": "today",
            "label": "Hoy",
            "start": today,
            "end": today,
        },
        {
            "key": "week",
            "label": "Semana",
            "start": week_start,
            "end": today,
        },
        {
            "key": "month",
            "label": "Mes",
            "start": month_start,
            "end": today,
        },
    ]

    period_cards = []
    for period in periods:
        queryset = Encounter.objects.filter(encounter_date__range=(period["start"], period["end"]))
        summary = get_period_summary(queryset)
        summary.update(
            {
                "label": period["label"],
                "range_label": (
                    f"{period['start']:%d/%m/%Y}"
                    if period["start"] == period["end"]
                    else f"{period['start']:%d/%m/%Y} al {period['end']:%d/%m/%Y}"
                ),
            }
        )
        period_cards.append(summary)

    last_7_days = []
    for offset in range(6, -1, -1):
        day_value = today - timedelta(days=offset)
        summary = get_period_summary(Encounter.objects.filter(encounter_date=day_value))
        summary.update(
            {
                "date": day_value,
                "label": format_day_label(day_value),
            }
        )
        last_7_days.append(summary)

    current_month_qs = Encounter.objects.filter(encounter_date__range=(month_start, today))
    current_month_summary = get_period_summary(current_month_qs)
    current_month_alerts = get_operational_alerts(current_month_qs)
    status_rows = []
    for value, label in EncounterStatus.choices:
        status_rows.append(
            {
                "label": label,
                "total": current_month_qs.filter(status=value).count(),
            }
        )

    profiled_patients = [
        patient
        for patient in Patient.objects.all().order_by("-updated_at")
        if looks_like_profile_data(patient)
    ]
    cohort_patients = list(
        Patient.objects.prefetch_related(
            "encounters__spirometry_result"
        ).all()
    )
    month_patient_ids = list(current_month_qs.values_list("patient_id", flat=True).distinct())
    current_month_profiled_patients = [patient for patient in profiled_patients if patient.id in month_patient_ids]
    profile_summary = build_patient_profile_summary(profiled_patients)
    month_profile_summary = build_patient_profile_summary(current_month_profiled_patients)
    cohort_rows, diagnosis_rows = build_cohort_statistics(cohort_patients)

    context = {
        "today": today,
        "period_cards": period_cards,
        "last_7_days": last_7_days,
        "month_label": format_month_label(month_start),
        "current_month_summary": current_month_summary,
        "current_month_alerts": current_month_alerts,
        "status_rows": status_rows,
        "profile_summary": profile_summary,
        "month_profile_summary": month_profile_summary,
        "latest_profiled_patients": profiled_patients[:10],
        "cohort_rows": cohort_rows,
        "diagnosis_rows": diagnosis_rows,
    }
    return render(request, "clinic/statistics.html", context)


@login_required
def patient_list(request):
    query = request.GET.get("q", "").strip()
    date_filter = (request.GET.get("date") or "").strip()
    coverage_filter = (request.GET.get("coverage") or "").strip()
    diagnosis_filter = (request.GET.get("diagnosis") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    physician_filter = (request.GET.get("physician") or "").strip()
    patients = Patient.objects.annotate(
        encounter_count=Count("encounters"),
        last_encounter_date=Max("encounters__encounter_date"),
    )
    if query:
        patients = patients.filter(
            Q(full_name__icontains=query) | Q(dni__icontains=query) | Q(patient_code__icontains=query)
        )
    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            patients = patients.filter(encounters__encounter_date=parsed_date)
        except ValueError:
            pass
    if coverage_filter:
        patients = patients.filter(encounters__coverage_type=coverage_filter)
    if status_filter:
        patients = patients.filter(encounters__status=status_filter)
    if physician_filter:
        patients = patients.filter(encounters__referring_physician_id=physician_filter)
    if diagnosis_filter:
        parsed = parse_result_code(diagnosis_filter)
        if parsed:
            pattern = parsed["pattern"]
            patients = patients.filter(encounters__spirometry_result__respiratory_pattern=pattern)
            if parsed["obstruction_grade"]:
                patients = patients.filter(encounters__spirometry_result__obstruction_grade=parsed["obstruction_grade"])
            if parsed["restriction_grade"]:
                patients = patients.filter(encounters__spirometry_result__restriction_grade=parsed["restriction_grade"])
        else:
            normalized = normalize_for_match(diagnosis_filter)
            if normalized:
                patients = patients.filter(
                    Q(encounters__spirometry_result__respiratory_pattern__icontains=diagnosis_filter)
                    | Q(encounters__spirometry_result__obstruction_grade__icontains=diagnosis_filter)
                    | Q(encounters__spirometry_result__restriction_grade__icontains=diagnosis_filter)
                )
    patients = patients.distinct().order_by("full_name")
    return render(
        request,
        "clinic/patient_list.html",
        {
            "patients": patients,
            "query": query,
            "filters": {
                "date": date_filter,
                "coverage": coverage_filter,
                "diagnosis": diagnosis_filter,
                "status": status_filter,
                "physician": physician_filter,
            },
            "coverage_choices": CoverageType.choices,
            "status_choices": EncounterStatus.choices,
            "physician_choices": ReferringPhysician.objects.filter(active=True).order_by("full_name"),
        },
    )


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    encounters = list(
        patient.encounters.select_related("vital_signs", "walk_test", "spirometry_result", "referring_physician")
        .prefetch_related("attachments", "generated_reports__attachment", "events")
        .order_by("-encounter_date", "-encounter_time", "-created_at")
    )
    ordered_for_progression = list(reversed(encounters))
    previous_encounter = None
    progression_map = {}
    for encounter in ordered_for_progression:
        progression_map[encounter.pk] = describe_progression(previous_encounter, encounter) if previous_encounter else {
            "label": "Base",
            "tone": "muted",
            "detail": "Primer estudio disponible para comparar.",
        }
        previous_encounter = encounter
    for encounter in encounters:
        encounter.result_code = get_result_code_from_encounter(encounter)
        encounter.result_label = get_result_label_from_encounter(encounter)
        encounter.attendance_label = get_attendance_label(encounter)
        encounter.pdf_attachment = get_latest_result_attachment(encounter)
        encounter.progression = progression_map.get(encounter.pk, {"label": "Sin base", "tone": "muted", "detail": ""})
        encounter.suggestion = build_stored_suggestion_context(getattr(encounter, "spirometry_result", None))
        latest_report_info = get_latest_report_info(encounter)
        encounter.latest_report_url = latest_report_info["latest_report_url"]
        encounter.latest_report_name = latest_report_info["latest_report_name"]
        encounter.detail_url = latest_report_info["detail_url"]
        encounter.timeline_preview = list(encounter.events.all()[:3])

    patient_documents = (
        Attachment.objects.filter(encounter__patient=patient)
        .select_related("encounter", "uploaded_by")
        .order_by("-created_at")
    )
    patient_events = (
        EncounterEvent.objects.filter(patient=patient)
        .select_related("actor", "encounter")
        .order_by("-created_at")[:25]
    )
    operational_summary = {
        "total_documents": patient_documents.count(),
        "reports_generated": GeneratedReport.objects.filter(encounter__patient=patient).count(),
        "pending_encounters": patient.encounters.filter(status=EncounterStatus.PENDIENTE).count(),
        "reviewed_encounters": patient.encounters.filter(status=EncounterStatus.REVISADA).count(),
    }
    latest_comparison = progression_map.get(encounters[0].pk) if encounters else None

    profile_items = [
        ("DNI", patient.dni or "-"),
        ("Codigo paciente", patient.patient_code or "-"),
        ("Telefono", patient.phone or "-"),
        ("Fecha nacimiento", patient.birth_date.strftime("%d/%m/%Y") if patient.birth_date else "-"),
        ("Edad", patient.age_reported if patient.age_reported is not None else "-"),
        ("Genero", patient.gender or "-"),
        ("Altura", f"{patient.height_cm} cm" if patient.height_cm else "-"),
        ("Peso", f"{patient.weight_kg} kg" if patient.weight_kg else "-"),
        ("BMI", patient.bmi if patient.bmi is not None else "-"),
        ("Fuma", patient.smoking_status or "-"),
        ("Paquete anio", patient.pack_years if patient.pack_years is not None else "-"),
    ]
    return render(
        request,
        "clinic/patient_detail.html",
        {
            "patient": patient,
            "encounters": encounters,
            "profile_items": profile_items,
            "patient_documents": patient_documents,
            "patient_events": patient_events,
            "operational_summary": operational_summary,
            "latest_comparison": latest_comparison,
        },
    )


@login_required
def patient_create(request):
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save()
            messages.success(request, "Paciente creado correctamente.")
            return redirect("clinic:patient_detail", pk=patient.pk)
    else:
        form = PatientForm()
    return render(
        request,
        "clinic/patient_form.html",
        {
            "form": form,
            "form_title": "Nuevo paciente",
            "form_pill": "Alta de paciente",
            "submit_label": "Guardar paciente",
        },
    )


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Paciente actualizado correctamente.")
            return redirect("clinic:patient_detail", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)

    return render(
        request,
        "clinic/patient_form.html",
        {
            "form": form,
            "patient": patient,
            "form_title": "Editar paciente",
            "form_pill": "Correccion de datos",
            "submit_label": "Guardar cambios",
        },
    )


@login_required
def patient_delete(request, pk):
    patient = get_object_or_404(
        Patient.objects.annotate(encounter_count=Count("encounters")),
        pk=pk,
    )

    if request.method == "POST":
        patient_name = patient.full_name
        encounter_count = patient.encounter_count
        patient.delete()
        if encounter_count:
            messages.success(
                request,
                f"Se elimino {patient_name} junto con {encounter_count} atencion(es) de su historia clinica.",
            )
        else:
            messages.success(request, f"Se elimino {patient_name}.")
        return redirect("clinic:patient_list")

    return render(request, "clinic/patient_confirm_delete.html", {"patient": patient})


@login_required
def encounter_create(request):
    if request.method == "POST":
        form = QuickEncounterForm(request.POST, request.FILES)
        if form.is_valid():
            encounter = save_quick_encounter(form, request.user)
            messages.success(request, "Atencion creada correctamente.")
            return redirect("clinic:encounter_detail", pk=encounter.pk)
    else:
        form = QuickEncounterForm(
            initial={
                "encounter_date": timezone.localdate(),
                "study_type": "Ciclometria",
                "coverage_type": "Particular",
                "distance_meters": 200,
                "completed": True,
                "borg_final": 0,
            }
        )

    return render(
        request,
        "clinic/encounter_form.html",
        {"form": form, "result_code_suggestions": RESULT_CODE_SUGGESTIONS},
    )


@login_required
def encounter_edit(request, pk):
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient", "vital_signs", "walk_test", "spirometry_result"),
        pk=pk,
    )
    patient = encounter.patient
    vital = getattr(encounter, "vital_signs", None)
    walk = getattr(encounter, "walk_test", None)
    spirometry = getattr(encounter, "spirometry_result", None)

    current_result = get_result_code_from_encounter(encounter)

    if request.method == "POST":
        form = QuickEncounterForm(request.POST)
        if form.is_valid():
            save_quick_encounter(form, request.user, encounter=encounter)
            messages.success(request, "Atencion actualizada correctamente.")
            return redirect("clinic:dashboard")
    else:
        form = QuickEncounterForm(
            initial={
                "patient_name": patient.full_name,
                "patient_dni": patient.dni or "",
                "encounter_time": encounter.encounter_time,
                "study_type": encounter.study_type,
                "coverage_type": encounter.coverage_type,
                "so2_rest": getattr(vital, "so2_rest", None),
                "fc_rest": getattr(vital, "fc_rest", None),
                "so2_post": getattr(vital, "so2_post", None),
                "fc_post": getattr(vital, "fc_post", None),
                "distance_meters": getattr(walk, "distance_meters", 200),
                "completed": getattr(walk, "completed", True),
                "borg_final": getattr(walk, "borg_final", 0),
                "respiratory_result": current_result,
                "attended": encounter.attended,
                "no_show": encounter.no_show,
            }
        )

    return render(
        request,
        "clinic/encounter_form.html",
        {"form": form, "edit_mode": True, "encounter": encounter, "result_code_suggestions": RESULT_CODE_SUGGESTIONS},
    )


@login_required
def doctor_review_list(request):
    encounters = (
        Encounter.objects.select_related("patient", "spirometry_result")
        .prefetch_related("attachments")
        .order_by("-encounter_date", "-created_at")
    )
    return render(request, "clinic/doctor_review_list.html", {"encounters": encounters})


@login_required
def doctor_review_detail(request, pk):
    encounter = get_object_or_404(
        Encounter.objects.select_related(
            "patient",
            "spirometry_result",
            "vital_signs",
            "walk_test",
        ).prefetch_related("attachments"),
        pk=pk,
    )

    current_result = get_result_code_from_encounter(encounter)

    if request.method == "POST":
        form = DoctorReviewForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data.get("pdf_file")
            analysis_payload_json = form.cleaned_data.get("analysis_payload_json", "")
            extraction_message = ""
            analysis = {}
            if pdf_file:
                file_kind, mime_type = classify_result_upload(pdf_file)
                attachment = Attachment(
                    encounter=encounter,
                    file_kind=file_kind,
                    original_name=pdf_file.name,
                    mime_type=mime_type,
                    uploaded_by=request.user,
                )
                attachment.file.save(pdf_file.name, pdf_file, save=True)
                snapshot, changed_fields = {}, []
                patient_identity_mismatch = False
                try:
                    analysis = build_analysis_for_uploaded_result(attachment, analysis_payload_json=analysis_payload_json)
                    snapshot = analysis.get("snapshot") or {}
                    if snapshot:
                        patient_identity_mismatch = not snapshot_matches_patient(encounter.patient, snapshot)
                        if not patient_identity_mismatch:
                            _, changed_fields = apply_snapshot_to_encounter_patient(encounter, snapshot)
                            encounter.refresh_from_db()
                    if analysis.get("values"):
                        store_spirometry_analysis(encounter, analysis)
                except Exception as error:
                    messages.warning(request, f"El archivo se subio, pero no se pudieron leer datos automaticos: {error}")
                record_encounter_event(
                    encounter,
                    EncounterEventType.DOCUMENT,
                    "Resultado de espirometria cargado",
                    actor=request.user,
                    details=f"Archivo: {pdf_file.name}",
                    metadata={
                        "analysis_source": analysis.get("source", "") if analysis else "",
                        "suggested_code": analysis.get("code", "") if analysis else "",
                    },
                )
                if snapshot and patient_identity_mismatch:
                    extracted_name = snapshot.get("full_name") or "-"
                    extracted_code = snapshot.get("patient_code") or snapshot.get("dni") or "-"
                    mismatch_message = (
                        f" El PDF parece corresponder a otra persona ({extracted_name} / doc {extracted_code}). "
                        "Se leyo para sugerencia, pero no se actualizaron datos del paciente actual."
                    )
                    extraction_message = mismatch_message
                    messages.warning(request, mismatch_message.strip())
                elif snapshot:
                    extracted_name = snapshot.get("full_name") or encounter.patient.full_name
                    extracted_code = snapshot.get("patient_code") or snapshot.get("dni") or "-"
                    extraction_message = f" PDF leido: {extracted_name} / doc {extracted_code}."
                    if changed_fields:
                        extraction_message += f" Datos actualizados: {', '.join(changed_fields)}."
                elif analysis.get("code"):
                    extraction_message = f" Sugerencia automatica: {analysis.get('summary')}."
                elif file_kind == AttachmentKind.FOTO_RESULTADO:
                    extraction_message = " Foto cargada correctamente."

            result_code = form.cleaned_data.get("respiratory_result") or analysis.get("code") or current_result or ""
            apply_result_code_to_spirometry(encounter, result_code)
            encounter.status = EncounterStatus.REVISADA
            encounter.updated_by = request.user
            encounter.validated_by = request.user
            encounter.validated_at = timezone.now()
            encounter.save(update_fields=["status", "updated_by", "validated_by", "validated_at", "updated_at"])
            record_encounter_event(
                encounter,
                EncounterEventType.REVIEW,
                "Revision medica validada",
                actor=request.user,
                details=f"Resultado validado: {get_result_code_from_encounter(encounter) or '-'}",
            )

            messages.success(request, "Revision medica guardada correctamente." + extraction_message)
            return redirect("clinic:doctor_review_detail", pk=encounter.pk)
    else:
        form = DoctorReviewForm(initial={"respiratory_result": current_result})

    pdf_attachment = get_latest_result_attachment(encounter)
    pdf_preview_pages = []
    preview_error = ""
    spirometry_suggestion = build_stored_suggestion_context(getattr(encounter, "spirometry_result", None))
    if pdf_attachment:
        try:
            pdf_preview_pages = build_result_preview_images(pdf_attachment)
        except Exception as error:
            preview_error = str(error)
        if pdf_attachment.file_kind == AttachmentKind.PDF_RESULTADO and not spirometry_suggestion:
            try:
                spirometry_suggestion = build_spirometry_suggestion_from_pdf(
                    pdf_attachment.file.path,
                    attachment_id=pdf_attachment.pk,
                )
                store_spirometry_analysis(encounter, {**spirometry_suggestion, "source": "server-pdf-text"})
            except Exception as error:
                if not preview_error:
                    preview_error = str(error)
    inconsistency_flags = get_encounter_inconsistencies(encounter)
    return render(
        request,
        "clinic/doctor_review_detail.html",
        {
            "encounter": encounter,
            "form": form,
            "pdf_attachment": pdf_attachment,
            "pdf_preview_pages": pdf_preview_pages,
            "preview_error": preview_error,
            "result_attachment_is_image": bool(pdf_attachment and is_result_image_attachment(pdf_attachment)),
            "result_code_suggestions": RESULT_CODE_SUGGESTIONS,
            "patient_profile_available": looks_like_profile_data(encounter.patient),
            "spirometry_suggestion": spirometry_suggestion,
            "inconsistency_flags": inconsistency_flags,
        },
    )


@login_required
def encounter_detail(request, pk):
    encounter = get_object_or_404(
        Encounter.objects.select_related(
            "patient",
            "referring_physician",
            "vital_signs",
            "walk_test",
            "spirometry_result",
        ).prefetch_related("attachments", "generated_reports", "events__actor"),
        pk=pk,
    )
    return render(
        request,
        "clinic/encounter_detail.html",
        {
            "encounter": encounter,
            "inconsistency_flags": get_encounter_inconsistencies(encounter),
        },
    )


@login_required
def encounter_print_view(request, pk):
    encounter = get_object_or_404(
        Encounter.objects.select_related(
            "patient",
            "referring_physician",
            "vital_signs",
            "walk_test",
            "spirometry_result",
        ).prefetch_related("attachments"),
        pk=pk,
    )
    context = build_print_context_for_encounter(encounter)
    return render(request, "clinic/encounter_print.html", context)


@login_required
def daily_print_view(request):
    today = timezone.localdate()
    encounters = (
        Encounter.objects.select_related(
            "patient",
            "referring_physician",
            "vital_signs",
            "walk_test",
            "spirometry_result",
        )
        .prefetch_related("attachments")
        .filter(encounter_date=today)
        .order_by("encounter_time", "created_at")
    )

    printable = []
    blocked = []
    for encounter in encounters:
        can_print, reason = get_report_readiness(encounter)
        if can_print:
            printable.append(build_print_context_for_encounter(encounter))
        else:
            blocked.append({"encounter": encounter, "reason": reason})

    context = {
        "today": today,
        "printable_packets": printable,
        "blocked_encounters": blocked,
    }
    return render(request, "clinic/daily_print.html", context)


@login_required
def encounter_generate_report(request, pk):
    encounter = get_object_or_404(
        Encounter.objects.select_related(
            "patient",
            "referring_physician",
            "vital_signs",
            "walk_test",
            "spirometry_result",
        ),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("clinic:encounter_detail", pk=encounter.pk)

    if not encounter.attended:
        encounter.attended = True
        encounter.no_show = False
        sync_attendance_status(encounter)
        encounter.updated_by = request.user
        encounter.save(update_fields=["attended", "no_show", "status", "updated_by", "updated_at"])
        record_encounter_event(
            encounter,
            EncounterEventType.ATTENDANCE,
            "Asistencia actualizada automaticamente",
            actor=request.user,
            details="Se marco como atendido al generar el informe.",
        )

    can_generate_report, report_block_reason = get_report_readiness(encounter)
    inconsistency_flags = get_encounter_inconsistencies(encounter)
    confirm_inconsistencies = request.POST.get("confirm_inconsistencies") == "1"
    if not can_generate_report:
        if is_ajax_request(request):
            payload = {"ok": False, "message": f"No se puede generar el informe. {report_block_reason}."}
            payload.update(get_row_state_payload(encounter))
            return JsonResponse(payload, status=400)
        messages.error(request, f"No se puede generar el informe. {report_block_reason}.")
        next_url = request.POST.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("clinic:encounter_detail", pk=encounter.pk)
    if inconsistency_flags and not confirm_inconsistencies:
        warning_message = "Hay inconsistencias para revisar antes de generar: " + " | ".join(inconsistency_flags)
        if is_ajax_request(request):
            payload = {
                "ok": False,
                "requires_confirmation": True,
                "message": warning_message,
            }
            payload.update(get_row_state_payload(encounter))
            return JsonResponse(payload, status=409)
        messages.warning(request, warning_message)
        return redirect("clinic:encounter_detail", pk=encounter.pk)

    try:
        artifacts = build_reports_for_encounter(encounter)
    except Exception as error:
        if is_ajax_request(request):
            payload = {"ok": False, "message": f"No se pudo generar el informe: {error}"}
            payload.update(get_row_state_payload(encounter))
            return JsonResponse(payload, status=500)
        messages.error(request, f"No se pudo generar el informe: {error}")
        return redirect("clinic:encounter_detail", pk=encounter.pk)

    generated_count = 0
    for artifact in artifacts:
        attachment = Attachment(
            encounter=encounter,
            file_kind=artifact.file_kind,
            original_name=artifact.filename,
            mime_type=artifact.mime_type,
            uploaded_by=request.user,
        )
        attachment.file.save(artifact.filename, ContentFile(artifact.bytes_content), save=True)
        report_type = artifact.report_type
        if report_type not in [choice.value for choice in ReportType]:
            report_type = ReportType.ESPIROMETRIA
        GeneratedReport.objects.create(
            encounter=encounter,
            report_type=report_type,
            attachment=attachment,
            generated_by=request.user,
            generator_version="web-v1-espiro",
        )
        generated_count += 1

    encounter.status = EncounterStatus.INFORME_GENERADO
    encounter.updated_by = request.user
    encounter.save(update_fields=["status", "updated_by", "updated_at"])
    record_encounter_event(
        encounter,
        EncounterEventType.REPORT,
        "Informe generado",
        actor=request.user,
        details=f"Se generaron {generated_count} archivo(s) de informe.",
        metadata={"generated_count": generated_count},
    )

    messages.success(request, f"Se generaron {generated_count} informe(s) correctamente.")
    if is_ajax_request(request):
        encounter.refresh_from_db()
        payload = {"ok": True, "message": f"Se generaron {generated_count} informe(s) correctamente."}
        payload.update(get_row_state_payload(encounter))
        return JsonResponse(payload)
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("clinic:encounter_detail", pk=encounter.pk)
