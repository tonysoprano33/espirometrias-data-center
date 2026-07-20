import calendar as month_calendar
import base64
from collections import Counter
from datetime import date, datetime, time as datetime_time, timedelta
import hashlib
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
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.core import signing
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    DoctorReviewForm,
    DrappImportForm,
    GRADE_TO_OBSTRUCTION_CODE,
    GRADE_TO_RESTRICTION_CODE,
    PatientForm,
    PatientDocumentUploadForm,
    QuickEncounterForm,
    ReferringPhysicianForm,
    RESULT_CODE_SUGGESTIONS,
    get_result_label_for_code,
    parse_result_code,
)
from .file_utils import local_field_file_path
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
    StudyType,
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
    extract_patient_snapshot_from_pdf,
    ingest_pdf_attachment_into_patient,
    looks_like_profile_data,
    normalize_for_match,
)
from .services import build_reports_for_encounter
from .services import (
    DEFAULT_DOCTOR,
    build_walk_measurement_rows,
    build_walk_test_assessment,
    construir_informe_espirometria,
    formatear_dni,
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


def require_any_clinic_permission(request, *permissions):
    if request.user.is_superuser or any(request.user.has_perm(permission) for permission in permissions):
        return
    raise PermissionDenied("No tenes permiso para realizar esta accion clinica.")


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

    with local_field_file_path(attachment.file) as attachment_path:
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


def safe_attachment_url(attachment) -> str:
    if not attachment or not getattr(attachment, "file", None):
        return ""
    file_field = attachment.file
    if not getattr(file_field, "name", ""):
        return ""
    try:
        return file_field.url
    except Exception:
        return ""


def build_result_preview_images(attachment):
    if not attachment or not getattr(attachment, "file", None):
        return []

    if is_result_image_attachment(attachment):
        url = safe_attachment_url(attachment)
        return [{"index": 1, "url": url}] if url else []
    return build_pdf_preview_images(attachment)


def normalize_identity_value(value: str) -> str:
    return normalize_for_match(collapse_spaces(value or ""))


def identity_digits(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def has_complete_identity_document(value: str) -> bool:
    return len(identity_digits(value)) >= 7


def can_autofill_missing_identity(patient, snapshot: dict) -> bool:
    snapshot_dni = normalize_identity_value(snapshot.get("dni") or "")
    patient_dni = normalize_identity_value(getattr(patient, "dni", "") or "")
    return bool(snapshot_dni) and not has_complete_identity_document(patient_dni)


def snapshot_matches_patient(patient, snapshot: dict) -> bool:
    if not patient or not snapshot:
        return True

    snapshot_dni = normalize_identity_value(snapshot.get("dni") or "")
    patient_dni = normalize_identity_value(getattr(patient, "dni", "") or "")
    if snapshot_dni and patient_dni and has_complete_identity_document(patient_dni):
        return snapshot_dni == patient_dni
    if snapshot_dni and not has_complete_identity_document(patient_dni):
        return True

    snapshot_code = normalize_identity_value(snapshot.get("patient_code") or "")
    patient_code = normalize_identity_value(getattr(patient, "patient_code", "") or "")
    if snapshot_code and patient_code:
        return snapshot_code == patient_code

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
        with local_field_file_path(attachment.file) as attachment_path:
            extracted_text = extract_pdf_text_content(str(attachment_path))
            analysis = (
                build_analysis_from_text(extracted_text, source="server-pdf-text")
                if extracted_text
                else {"source": "server-pdf-ocr"}
            )
            snapshot = extract_patient_snapshot_from_pdf(str(attachment_path), attachment_id=attachment.pk)
            if snapshot:
                analysis["snapshot"] = snapshot
            if not analysis.get("code"):
                suggestion = build_spirometry_suggestion_from_pdf(
                    str(attachment_path),
                    attachment_id=attachment.pk,
                )
                if suggestion:
                    analysis.update(suggestion)
                    analysis["source"] = "server-pdf-ocr"
            return analysis
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
    result.save()
    return result


def store_spirometry_analysis(encounter, analysis: dict):
    if not analysis:
        return None

    result, _ = SpirometryResult.objects.get_or_create(encounter=encounter)
    stored_values = dict(analysis.get("values") or {})
    bronchodilator_reason = analysis.get("bronchodilator_reason", "") or ""
    if bronchodilator_reason:
        stored_values["_bronchodilator_reason"] = bronchodilator_reason
    result.measured_values = stored_values
    result.suggested_code = analysis.get("code", "") or ""
    result.suggested_probability = analysis.get("probability")
    result.suggested_summary = analysis.get("summary", "") or ""
    result.extracted_source = analysis.get("source", "") or ""
    result.suggested_bronchodilator_positive = (
        bool(analysis.get("bronchodilator_positive")) if "bronchodilator_positive" in analysis else None
    )
    result.suggested_bronchodilator_reason = bronchodilator_reason
    result.save(
        update_fields=[
            "measured_values",
            "suggested_code",
            "suggested_probability",
            "suggested_summary",
            "extracted_source",
            "suggested_bronchodilator_positive",
            "suggested_bronchodilator_reason",
            "updated_at",
        ]
    )
    return result


def apply_profile_analysis_to_encounter(encounter, analysis: dict):
    snapshot = (analysis or {}).get("snapshot") or {}
    if not snapshot:
        return {}, [], False

    snapshot_full_name = normalize_identity_value(
        snapshot.get("full_name")
        or f"{snapshot.get('last_name', '')} {snapshot.get('first_name', '')}"
    )
    patient_full_name = normalize_identity_value(getattr(encounter.patient, "full_name", "") or "")
    name_mismatch = bool(snapshot_full_name and patient_full_name and snapshot_full_name != patient_full_name)
    should_update_full_name = not name_mismatch or can_autofill_missing_identity(encounter.patient, snapshot)
    extracted_dni = identity_digits(snapshot.get("dni") or "")
    duplicate_dni_conflict = bool(
        extracted_dni
        and Patient.all_objects.filter(dni=extracted_dni).exclude(pk=encounter.patient_id).exists()
    )
    patient_identity_mismatch = duplicate_dni_conflict or not snapshot_matches_patient(encounter.patient, snapshot)
    changed_fields = []
    if not patient_identity_mismatch:
        _, changed_fields = apply_snapshot_to_encounter_patient(
            encounter,
            snapshot,
            update_full_name=should_update_full_name,
        )
        encounter.refresh_from_db()
    return snapshot, changed_fields, patient_identity_mismatch


def build_stored_suggestion_context(spirometry_result):
    if not spirometry_result or not spirometry_result.suggested_code:
        return None
    stored_summary = spirometry_result.suggested_summary or ""
    probability_phrase = (
        f"Calidad de lectura automatica: {spirometry_result.suggested_probability}%"
        if spirometry_result.suggested_probability is not None
        else ""
    )
    reason = stored_summary
    legacy_probability_phrase = (
        f"{spirometry_result.suggested_probability}% probable {spirometry_result.suggested_code}"
        if spirometry_result.suggested_probability is not None
        else ""
    )
    if legacy_probability_phrase and stored_summary.startswith(legacy_probability_phrase):
        reason = stored_summary[len(legacy_probability_phrase):].lstrip(". ").strip()
    stored_values = spirometry_result.measured_values or {}
    return {
        "code": spirometry_result.suggested_code,
        "reason": reason,
        "summary": stored_summary,
        "probability": spirometry_result.suggested_probability,
        "probability_phrase": probability_phrase,
        "values": stored_values,
        "source": spirometry_result.extracted_source or "",
        "bronchodilator_positive": bool(spirometry_result.suggested_bronchodilator_positive),
        "bronchodilator_reason": (
            spirometry_result.suggested_bronchodilator_reason
            or stored_values.get("_bronchodilator_reason", "")
        ),
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


def get_status_badge_class(status: str) -> str:
    status = (status or "").strip()
    if status == EncounterStatus.PENDIENTE:
        return "pending"
    if status == EncounterStatus.CARGADA:
        return "waiting"
    if status == EncounterStatus.REVISADA:
        return "reviewed"
    if status == EncounterStatus.INFORME_GENERADO:
        return "generated"
    if status == EncounterStatus.ENTREGADA:
        return "done"
    if status == EncounterStatus.NO_LLEGO:
        return "missed"
    return "neutral"


def get_default_physician():
    return ReferringPhysician.objects.filter(is_default=True, active=True).first() or ReferringPhysician.objects.filter(
        active=True
    ).first()


def format_physician_display_name(raw_name: str) -> str:
    value = " ".join(str(raw_name or "").replace(".", " ").split()).strip(" ,")
    if not value:
        return ""
    upper_value = value.upper()
    prefix = "DR."
    if upper_value.startswith("DRA "):
        prefix = "DRA."
        value = value[4:].strip()
    elif upper_value.startswith("DR A "):
        prefix = "DRA."
        value = value[5:].strip()
    elif upper_value.startswith("DR "):
        value = value[3:].strip()
    lower_particles = {"de", "del", "la", "las", "los", "y"}

    def titlecase_piece(piece: str) -> str:
        return "-".join(part.capitalize() for part in piece.lower().split("-"))

    words = []
    for word in value.split():
        lowered = word.lower()
        if lowered in lower_particles:
            words.append(lowered)
        else:
            words.append(titlecase_piece(word))
    return f"{prefix} {' '.join(words)}"


def resolve_or_create_physician(raw_value: str):
    raw_text = collapse_spaces(raw_value)
    default_physician = get_default_physician()
    if not raw_text:
        return default_physician

    if raw_text.isdigit():
        physician = ReferringPhysician.objects.filter(pk=raw_text, active=True).first()
        if physician:
            return physician

    physician = ReferringPhysician.objects.filter(full_name__iexact=raw_text).first()
    if physician:
        if not physician.active:
            physician.active = True
            physician.save(update_fields=["active", "updated_at"])
        return physician

    formatted_name = format_physician_display_name(raw_text) or raw_text
    physician = ReferringPhysician.objects.filter(full_name__iexact=formatted_name).first()
    if physician:
        if not physician.active:
            physician.active = True
            physician.save(update_fields=["active", "updated_at"])
        return physician
    return ReferringPhysician.objects.create(full_name=formatted_name, active=True)


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


RECYCLE_BIN_RETENTION_DAYS = 30


def purge_expired_recycle_bin():
    if not getattr(settings, "AUTO_PURGE_RECYCLE_BIN", False):
        return {"encounters": 0, "patients": 0}
    cutoff = timezone.now() - timedelta(days=RECYCLE_BIN_RETENTION_DAYS)
    deleted_encounters = Encounter.all_objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
    deleted_patients = Patient.all_objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
    deleted_counts = {"encounters": deleted_encounters.count(), "patients": deleted_patients.count()}
    if deleted_encounters.exists():
        deleted_encounters.delete()
    if deleted_patients.exists():
        deleted_patients.delete()
    return deleted_counts


def soft_delete_encounter(encounter, *, actor=None, reason: str = "") -> bool:
    if not encounter or getattr(encounter, "deleted_at", None):
        return False
    record_encounter_event(
        encounter,
        EncounterEventType.UPDATED,
        "Atencion enviada a papelera",
        actor=actor,
        details=reason or "Se movio la atencion a la papelera.",
    )
    encounter.soft_delete(deleted_by=actor)
    return True


def soft_delete_patient(patient, *, actor=None, reason: str = "") -> bool:
    if not patient or getattr(patient, "deleted_at", None):
        return False
    for encounter in Encounter.all_objects.filter(patient=patient, deleted_at__isnull=True):
        record_encounter_event(
            encounter,
            EncounterEventType.UPDATED,
            "Atencion enviada a papelera",
            actor=actor,
            details=reason or f"Se movio a papelera junto con el paciente {patient.full_name}.",
        )
    patient.soft_delete(deleted_by=actor)
    return True


def restore_deleted_patient(patient) -> bool:
    if not patient or not getattr(patient, "deleted_at", None):
        return False
    patient.restore()
    return True


def restore_deleted_encounter(encounter) -> bool:
    if not encounter or not getattr(encounter, "deleted_at", None):
        return False
    if getattr(encounter.patient, "deleted_at", None):
        encounter.patient.restore(restore_batch=False)
    encounter.restore()
    return True


def sort_dashboard_encounters(encounters):
    attended_encounters = []
    pending_encounters = []

    for encounter in encounters:
        if encounter.attended and encounter.attended_at:
            attended_encounters.append(encounter)
        else:
            pending_encounters.append(encounter)

    attended_encounters.sort(
        key=lambda encounter: (
            encounter.attended_at,
            encounter.encounter_time or datetime_time(23, 59),
            encounter.created_at,
            encounter.pk,
        )
    )
    pending_encounters.sort(
        key=lambda encounter: (
            encounter.encounter_time or datetime_time(23, 59),
            encounter.created_at,
            encounter.pk,
        )
    )
    return attended_encounters + pending_encounters


def get_doctor_review_done_statuses():
    return {
        EncounterStatus.REVISADA,
        EncounterStatus.INFORME_GENERADO,
        EncounterStatus.ENTREGADA,
    }


def encounter_has_review_pdf(encounter) -> bool:
    return bool(get_latest_result_attachment(encounter))


def encounter_is_pending_doctor_review(encounter) -> bool:
    return encounter.attended and encounter_has_review_pdf(encounter) and encounter.status not in get_doctor_review_done_statuses()


def build_doctor_review_queue(reference_date, current_encounter=None):
    pending_encounters = []
    queue_qs = (
        Encounter.objects.select_related("patient")
        .prefetch_related("attachments")
        .filter(encounter_date=reference_date)
        .order_by("attended_at", "encounter_time", "created_at")
    )

    for encounter in queue_qs:
        if encounter_is_pending_doctor_review(encounter):
            pending_encounters.append(encounter)

    current_index = None
    if current_encounter is not None:
        for index, item in enumerate(pending_encounters):
            if item.pk == current_encounter.pk:
                current_index = index
                break

    next_encounter = None
    if current_index is not None and current_index + 1 < len(pending_encounters):
        next_encounter = pending_encounters[current_index + 1]
    elif current_index is None and pending_encounters:
        next_encounter = pending_encounters[0]

    previous_encounter = None
    if current_index is not None and current_index > 0:
        previous_encounter = pending_encounters[current_index - 1]

    remaining_after_current = len(pending_encounters)

    return {
        "pending_encounters": pending_encounters,
        "pending_total": len(pending_encounters),
        "current_index": current_index,
        "current_is_pending": current_index is not None,
        "remaining_after_current": remaining_after_current,
        "previous_encounter": previous_encounter,
        "next_encounter": next_encounter,
    }


def build_mutual_cvl_result(pattern: str, obstruction_grade: str, restriction_grade: str) -> str:
    obstruction_grade = (obstruction_grade or "").strip().lower()
    restriction_grade = (restriction_grade or "").strip().lower()
    if pattern == "Normal":
        return "Normal"
    if pattern == "Obstructivo":
        if obstruction_grade == "leve":
            return "Levemente disminuida"
        if obstruction_grade in {"moderado", "moderada"}:
            return "Moderadamente disminuida"
        if obstruction_grade == "moderadamente severa":
            return "Moderadamente a severamente disminuida"
        return "Severamente disminuida"
    if pattern == "Restrictivo":
        if restriction_grade == "leve":
            return "Levemente reducida"
        if restriction_grade in {"moderado", "moderada"}:
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


def vital_signs_have_data(vital_signs) -> bool:
    return any(
        getattr(vital_signs, field_name, None) is not None
        for field_name in ("so2_rest", "fc_rest", "so2_post", "fc_post")
    )


def rest_vital_signs_are_complete(vital_signs) -> bool:
    return getattr(vital_signs, "so2_rest", None) is not None and getattr(vital_signs, "fc_rest", None) is not None


def quick_form_has_clinical_data(cleaned_data) -> bool:
    has_complete_rest_vitals = cleaned_data.get("so2_rest") is not None and cleaned_data.get("fc_rest") is not None
    return has_complete_rest_vitals or bool(cleaned_data.get("respiratory_result"))


def mark_encounter_attended(encounter, request_user=None, details: str = "") -> bool:
    if encounter.attended and not encounter.no_show and encounter.status not in [
        EncounterStatus.PENDIENTE,
        EncounterStatus.NO_LLEGO,
    ]:
        return False
    previous_label = get_attendance_label(encounter)
    became_attended = not encounter.attended or encounter.no_show or encounter.attended_at is None
    encounter.attended = True
    encounter.no_show = False
    if became_attended:
        encounter.attended_at = timezone.now()
    sync_attendance_status(encounter)
    if request_user is not None:
        encounter.updated_by = request_user
    update_fields = ["attended", "attended_at", "no_show", "status", "updated_at"]
    if request_user is not None:
        update_fields.append("updated_by")
    encounter.save(update_fields=update_fields)

    if previous_label != get_attendance_label(encounter):
        record_encounter_event(
            encounter,
            EncounterEventType.ATTENDANCE,
            "Asistencia actualizada automaticamente",
            actor=request_user,
            details=details or f"Antes: {previous_label} | Ahora: {get_attendance_label(encounter)}",
        )
        return True
    return False


def assign_encounter_patient_by_dni(encounter, dni_value: str):
    dni = re.sub(r"\D", "", dni_value or "")
    patient = encounter.patient

    if not dni:
        if patient.dni:
            patient.dni = None
            patient.save(update_fields=["dni", "updated_at"])
        return patient, False

    existing_patient = Patient.all_objects.filter(dni=dni).exclude(pk=patient.pk).first()
    if existing_patient:
        raise ValueError(
            f"El DNI {formatear_dni(dni)} ya pertenece a {existing_patient.full_name}. "
            "No se modifico ni se movio esta atencion."
        )

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


def encounter_has_protected_history(encounter) -> bool:
    if encounter.status in {
        EncounterStatus.REVISADA,
        EncounterStatus.INFORME_GENERADO,
        EncounterStatus.ENTREGADA,
    }:
        return True
    return encounter.attachments.exists() or encounter.generated_reports.exists()


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
    latest_url = safe_attachment_url(latest_attachment)
    latest_name = latest_attachment.original_name if latest_attachment else latest_report.report_type
    complete_url = safe_attachment_url(complete_attachment)
    complete_name = complete_attachment.original_name if complete_attachment else ""
    mutual_url = safe_attachment_url(mutual_attachment)
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


def build_report_source_snapshot(encounter) -> dict:
    patient = encounter.patient
    vital = getattr(encounter, "vital_signs", None)
    walk = getattr(encounter, "walk_test", None)
    result = getattr(encounter, "spirometry_result", None)
    return {
        "patient": {
            "id": patient.pk,
            "full_name": patient.full_name,
            "dni": patient.dni or "",
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
            "gender": patient.gender,
        },
        "encounter": {
            "id": encounter.pk,
            "date": encounter.encounter_date.isoformat(),
            "time": encounter.encounter_time.isoformat() if encounter.encounter_time else None,
            "study_type": encounter.study_type,
            "coverage_type": encounter.coverage_type,
            "coverage_name": encounter.coverage_name,
            "referring_physician": getattr(encounter.referring_physician, "full_name", ""),
        },
        "vital_signs": {
            "so2_rest": getattr(vital, "so2_rest", None),
            "fc_rest": getattr(vital, "fc_rest", None),
            "so2_post": getattr(vital, "so2_post", None),
            "fc_post": getattr(vital, "fc_post", None),
        },
        "walk_test": {
            "distance_meters": getattr(walk, "distance_meters", None),
            "completed": getattr(walk, "completed", None),
            "stopped": getattr(walk, "stopped", None),
            "symptoms": getattr(walk, "symptoms", None),
            "borg_final": getattr(walk, "borg_final", None),
            "minute_readings": getattr(walk, "minute_readings", []) or [],
        },
        "spirometry": {
            "final_code": get_result_code_from_encounter(encounter),
            "pattern": getattr(result, "respiratory_pattern", ""),
            "obstruction_grade": getattr(result, "obstruction_grade", ""),
            "restriction_grade": getattr(result, "restriction_grade", ""),
            "bronchodilator_positive": bool(getattr(result, "bronchodilator_positive", False)),
            "suggested_code": getattr(result, "suggested_code", ""),
            "suggested_reading_quality": getattr(result, "suggested_probability", None),
            "measured_values": getattr(result, "measured_values", {}) or {},
        },
    }


def save_generated_report_artifacts(encounter, artifacts, user) -> int:
    generated_count = 0
    saved_attachments = []
    source_snapshot = build_report_source_snapshot(encounter)
    try:
        with transaction.atomic():
            for artifact in artifacts:
                attachment = Attachment(
                    encounter=encounter,
                    file_kind=artifact.file_kind,
                    original_name=artifact.filename,
                    mime_type=artifact.mime_type,
                    uploaded_by=user,
                )
                attachment.file.save(artifact.filename, ContentFile(artifact.bytes_content), save=False)
                saved_attachments.append(attachment)
                attachment.save()
                report_type = artifact.report_type
                if report_type not in [choice.value for choice in ReportType]:
                    report_type = ReportType.ESPIROMETRIA
                previous_report = (
                    GeneratedReport.objects.filter(encounter=encounter, report_type=report_type)
                    .order_by("-created_at")
                    .first()
                )
                GeneratedReport.objects.create(
                    encounter=encounter,
                    report_type=report_type,
                    attachment=attachment,
                    generated_by=user,
                    generator_version="web-v2-integrity",
                    source_snapshot=source_snapshot,
                    content_sha256=hashlib.sha256(artifact.bytes_content).hexdigest(),
                    supersedes=previous_report,
                )
                generated_count += 1
    except Exception:
        for attachment in saved_attachments:
            try:
                attachment.file.delete(save=False)
            except Exception:
                pass
        raise
    return generated_count


def build_report_artifacts_for_scope(encounter, scope: str):
    artifacts = build_reports_for_encounter(encounter, include_mutual=True if scope == "mutual" else None)
    if scope == "mutual":
        return [artifact for artifact in artifacts if artifact.report_type == ReportType.MUTUAL]
    return artifacts


def parse_optional_int(raw_value, *, min_value=0, max_value=None, label="Valor"):
    text = str(raw_value or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d+", text):
        raise ValueError(f"{label}: ingresa solo numeros enteros.")
    value = int(text)
    if value < min_value or (max_value is not None and value > max_value):
        upper = f" y {max_value}" if max_value is not None else ""
        raise ValueError(f"{label}: el valor debe estar entre {min_value}{upper}.")
    return value


def save_vitals_group_values(*, encounter_id, group_name, so2_raw, fc_raw, request_user):
    if group_name not in {"rest", "post"}:
        raise ValueError("Grupo de signos vitales invalido.")

    group_label = "reposo" if group_name == "rest" else "post caminata"
    so2_value = parse_optional_int(so2_raw, max_value=100, label=f"SO2 {group_label}")
    fc_value = parse_optional_int(fc_raw, max_value=300, label=f"FC {group_label}")

    with transaction.atomic():
        encounter = Encounter.objects.select_for_update().select_related("patient").get(pk=encounter_id)
        vital, _ = VitalSigns.objects.select_for_update().get_or_create(encounter=encounter)
        so2_field = f"so2_{group_name}"
        fc_field = f"fc_{group_name}"
        old_so2 = getattr(vital, so2_field)
        old_fc = getattr(vital, fc_field)
        setattr(vital, so2_field, so2_value)
        setattr(vital, fc_field, fc_value)
        vital.save(update_fields=[so2_field, fc_field, "updated_at"])

        encounter.updated_by = request_user
        encounter.save(update_fields=["updated_by", "updated_at"])
        if (old_so2, old_fc) != (so2_value, fc_value):
            record_encounter_event(
                encounter,
                EncounterEventType.UPDATED,
                f"SO2 y FC en {group_label} actualizados",
                actor=request_user,
                details=(
                    f"Antes: {old_so2 if old_so2 is not None else '-'} / "
                    f"{old_fc if old_fc is not None else '-'} | Ahora: "
                    f"{so2_value if so2_value is not None else '-'} / "
                    f"{fc_value if fc_value is not None else '-'}"
                ),
                metadata={"group": group_name, "so2": so2_value, "fc": fc_value},
            )

        if group_name == "rest" and rest_vital_signs_are_complete(vital):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al guardar SO2 y FC completos en reposo.",
            )
    return encounter


def parse_optional_time(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return None
    text = text.replace(".", ":")
    if re.fullmatch(r"\d{1,2}", text):
        text = f"{text}:00"
    elif re.fullmatch(r"\d{3,4}", text):
        text = f"{text[:-2]}:{text[-2:]}"

    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return datetime_time(hour, minute)


def get_row_state_payload(encounter):
    can_generate_report, report_block_reason = get_report_readiness(encounter)
    can_print_result, print_block_reason = get_print_readiness(encounter)
    inconsistency_flags = get_encounter_inconsistencies(encounter)
    vital = getattr(encounter, "vital_signs", None)
    current_physician = getattr(encounter, "referring_physician", None)
    default_physician = get_default_physician()
    payload = {
        "encounter_id": encounter.pk,
        "status": encounter.status,
        "status_css_class": get_status_badge_class(encounter.status),
        "attended": encounter.attended,
        "no_show": encounter.no_show,
        "attendance_label": get_attendance_label(encounter),
        "attended_at": encounter.attended_at.isoformat() if encounter.attended_at else "",
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
        "patient_dni_display": formatear_dni(encounter.patient.dni) if encounter.patient.dni else "Completar DNI",
        "patient_url": reverse("clinic:patient_detail", args=[encounter.patient_id]),
        "print_url": reverse("clinic:encounter_print", args=[encounter.pk]),
        "so2_rest": "" if getattr(vital, "so2_rest", None) is None else str(vital.so2_rest),
        "fc_rest": "" if getattr(vital, "fc_rest", None) is None else str(vital.fc_rest),
        "so2_post": "" if getattr(vital, "so2_post", None) is None else str(vital.so2_post),
        "fc_post": "" if getattr(vital, "fc_post", None) is None else str(vital.fc_post),
        "has_cycle_data": encounter_has_cycle_data(encounter),
        "can_generate_report": can_generate_report,
        "report_block_reason": report_block_reason,
        "can_print_result": can_print_result,
        "print_block_reason": print_block_reason,
        "inconsistencies": inconsistency_flags,
        "inconsistency_message": "Advertencias: " + " | ".join(inconsistency_flags) if inconsistency_flags else "",
        "has_generated_reports": encounter.generated_reports.exists(),
        "report_button_label": "Regenerar informe" if encounter.generated_reports.exists() else "Generar informe",
    }
    payload.update(get_latest_report_info(encounter))
    return payload


def get_operational_alerts(queryset):
    if hasattr(queryset, "select_related"):
        encounters = unique_encounters_by_patient_day(
            queryset.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
            .prefetch_related("attachments", "generated_reports")
        )
    else:
        encounters = unique_encounters_by_patient_day(queryset)
    pending_review = sum(1 for encounter in encounters if encounter.status == EncounterStatus.PENDIENTE)
    ready_for_report = 0
    missing_pdf = 0
    for encounter in encounters:
        can_generate, _ = get_report_readiness(encounter)
        if can_generate and not encounter.generated_reports.exists():
            ready_for_report += 1
        if encounter.study_type == "Espirometria" and not get_latest_result_attachment(encounter):
            missing_pdf += 1
    return {
        "pending_review": pending_review,
        "ready_for_report": ready_for_report,
        "missing_pdf": missing_pdf,
        "no_show": sum(1 for encounter in encounters if encounter.no_show),
    }


def update_inline_field(encounter, field_name: str, raw_value: str, request_user, manual_save: bool = False):
    patient = encounter.patient
    vital, _ = VitalSigns.objects.get_or_create(encounter=encounter)
    raw_text = (raw_value or "").strip()
    if field_name in {"so2_rest", "fc_rest", "so2_post", "fc_post"}:
        raise ValueError("SO2 y FC se guardan juntos con el boton Guardar.")

    if field_name == "patient_name":
        old_value = patient.full_name
        if not raw_text:
            return
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
        encounter.encounter_time = parse_optional_time(raw_value)
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
        encounter.referring_physician = resolve_or_create_physician(raw_value) if raw_value else get_default_physician()
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
        if manual_save and rest_vital_signs_are_complete(vital):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al completar SO2 y FC en reposo.",
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
        if manual_save and rest_vital_signs_are_complete(vital):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al completar SO2 y FC en reposo.",
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
        if manual_save and rest_vital_signs_are_complete(vital):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al completar SO2 y FC en reposo.",
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
        if manual_save and rest_vital_signs_are_complete(vital):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al completar SO2 y FC en reposo.",
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
        if get_result_code_from_encounter(encounter):
            mark_encounter_attended(
                encounter,
                request_user,
                details="Se marco como atendido al cargar resultado respiratorio.",
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
        encounter.attended_at = timezone.now()
    elif encounter.attended:
        encounter.attended = False
        encounter.no_show = True
        encounter.attended_at = None
    else:
        encounter.attended = False
        encounter.no_show = False
        encounter.attended_at = None

    sync_attendance_status(encounter)
    encounter.updated_by = request_user
    encounter.save(update_fields=["attended", "attended_at", "no_show", "status", "updated_by", "updated_at"])
    new_label = get_attendance_label(encounter)
    if previous_label != new_label:
        record_encounter_event(
            encounter,
            EncounterEventType.ATTENDANCE,
            "Asistencia actualizada",
            actor=request_user,
            details=f"Antes: {previous_label} | Ahora: {new_label}",
        )


@transaction.atomic
def save_quick_encounter(form: QuickEncounterForm, request_user, encounter=None):
    default_physician = get_default_physician()
    full_name = form.cleaned_data["patient_name"].strip().upper()
    patient_dni = (form.cleaned_data.get("patient_dni") or "").strip()
    selected_physician = resolve_or_create_physician(form.cleaned_data.get("referring_physician")) or default_physician

    patient = encounter.patient if encounter is not None else None
    matched_existing_by_dni = False
    if encounter is not None and patient_dni:
        conflicting_patient = Patient.all_objects.filter(dni=patient_dni).exclude(pk=patient.pk).first()
        if conflicting_patient:
            raise ValueError(
                f"El DNI {formatear_dni(patient_dni)} ya pertenece a {conflicting_patient.full_name}. "
                "No se modifico esta atencion."
            )
    if patient is None and patient_dni:
        patient = Patient.all_objects.filter(dni=patient_dni).first()
        if patient is not None and patient.deleted_at:
            patient.restore(restore_batch=False)
        matched_existing_by_dni = patient is not None
    if patient is None and full_name:
        patient = Patient.objects.filter(full_name=full_name).order_by("-updated_at").first()
    if patient is None:
        patient = Patient.objects.create(full_name=full_name, dni=patient_dni or None)
    else:
        if not matched_existing_by_dni or normalize_patient_identity_name(patient.full_name) == normalize_patient_identity_name(full_name):
            patient.full_name = full_name
        if patient_dni:
            patient.dni = patient_dni
        patient.save()

    is_new = encounter is None
    if encounter is None:
        encounter = Encounter(
            created_by=request_user,
        )

    has_clinical_data = quick_form_has_clinical_data(form.cleaned_data)
    attended = bool(form.cleaned_data.get("attended")) or has_clinical_data
    no_show = bool(form.cleaned_data.get("no_show"))
    if is_new and not attended:
        no_show = True
    if attended:
        no_show = False
    encounter_time = form.cleaned_data.get("encounter_time")
    if is_new and encounter_time is None:
        encounter_time = timezone.localtime().time().replace(second=0, microsecond=0)
    encounter.patient = patient
    if is_new:
        encounter.encounter_date = timezone.localdate()
    encounter.encounter_time = encounter_time
    encounter.study_type = form.cleaned_data["study_type"]
    if is_new:
        encounter.status = EncounterStatus.PENDIENTE
    encounter.coverage_type = form.cleaned_data["coverage_type"]
    encounter.referring_physician = selected_physician
    encounter.attended = attended
    encounter.no_show = no_show
    if attended and encounter.attended_at is None:
        encounter.attended_at = timezone.now()
    elif not attended:
        encounter.attended_at = None
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
            "stopped": bool(form.cleaned_data.get("stopped")),
            "symptoms": bool(form.cleaned_data.get("symptoms")),
            "borg_final": int(form.cleaned_data.get("borg_final") or 1),
        },
    )

    result_code = form.cleaned_data.get("respiratory_result") or ""
    result = apply_result_code_to_spirometry(encounter, result_code)
    result.bronchodilator_positive = bool(form.cleaned_data.get("bronchodilator_positive"))
    result.save(update_fields=["bronchodilator_positive", "updated_at"])
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
    prefix_match = re.match(
        r"^([A-ZÁÉÍÓÚÜÑ]{1,2})\s+([A-ZÁÉÍÓÚÜÑ' ]+, [A-ZÁÉÍÓÚÜÑ' ]+)$",
        normalized_upper,
    )
    if prefix_match and prefix_match.group(1) in {"O", "OR", "Q", "C"}:
        normalized_upper = prefix_match.group(2).strip()
    return normalized_upper


def infer_coverage_type(raw_coverage: str) -> str:
    text = (raw_coverage or "").strip().lower()
    if text == "particular":
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
DRAPP_COVERAGE_CANDIDATES = ["PARTICULAR", "PAMI", "DOSEP", "OSDE", "SWISS MEDICAL", "MEDIFE", "OSECAC", "IOSFA"]
DRAPP_NAME_NOISE_PATTERNS = [
    re.compile(r"\bHACE\s+\d+\s+(?:DIAS?|HORAS?|MINUTOS?)\b", re.IGNORECASE),
    re.compile(r"\bRESERVAD[OA]S?\b", re.IGNORECASE),
    re.compile(r"\bLINK\s+DE\s+PAGO\b", re.IGNORECASE),
    re.compile(r"\bCENTRO\s+RESPIRATORIO\s+INTEGRAL\b", re.IGNORECASE),
    re.compile(r"\bPIGUILLEM\s+GUSTAVO\b", re.IGNORECASE),
    re.compile(r"\bESPIROMETRIA\b", re.IGNORECASE),
    re.compile(r"\bCICLOESPIROMETRIA\b", re.IGNORECASE),
    re.compile(r"\bCICLO\s*ESPIROMETRIA\b", re.IGNORECASE),
    re.compile(r"\bCICLOMETRIA\b", re.IGNORECASE),
]
DRAPP_NAME_CUTOFF_TOKENS = (
    "ESPI",
    "CICLO",
    "PIG",
    "CENTRO",
    "RESP",
    "INTEG",
    "LINK",
    "PAGO",
    "PARTIC",
    "PAMI",
    "DOSEP",
    "OSDE",
    "SWISS",
    "MEDIFE",
    "OSECAC",
    "IOSFA",
)
DRAPP_INVALID_NAME_MARKERS = (
    "ESPIROMETRIA",
    "CICLOMETRIA",
    "CICLOESPIROMETRIA",
    "CENTRORESPIRATORIO",
    "PIGUILLEM",
    "LINKDEPAGO",
)


def normalize_document_number(raw_value: str) -> str:
    digits = re.sub(r"\D+", "", str(raw_value or ""))
    return digits


def normalize_patient_identity_name(raw_name: str) -> str:
    return normalize_for_match(normalize_imported_name(raw_name))


def is_plausible_imported_patient_name(raw_name: str) -> bool:
    name = normalize_imported_name(raw_name)
    normalized = normalize_for_match(name)
    if len(name) < 3 or len(re.findall(r"[A-Z]", normalized)) < 3:
        return False
    if any(marker in normalized for marker in DRAPP_INVALID_NAME_MARKERS):
        return False
    return len([part for part in re.split(r"[ ,]+", name) if len(part) >= 2]) >= 1


def encounter_matches_import_identity(encounter, parsed_dni: str, patient_name_key: str) -> bool:
    patient = getattr(encounter, "patient", None)
    if not patient:
        return False
    existing_dni = normalize_document_number(getattr(patient, "dni", "") or "")
    existing_name_key = normalize_patient_identity_name(getattr(patient, "full_name", "") or "")
    same_dni = bool(parsed_dni and existing_dni and parsed_dni == existing_dni)
    same_name = bool(patient_name_key and existing_name_key and patient_name_key == existing_name_key)
    return same_dni or same_name


def import_identity_exists_for_date(encounter_date, parsed_dni: str, patient_name: str) -> bool:
    patient_name_key = normalize_patient_identity_name(patient_name)
    existing_encounters = (
        Encounter.objects.select_related("patient")
        .filter(encounter_date=encounter_date)
        .only("patient__dni", "patient__full_name")
    )
    return any(
        encounter_matches_import_identity(encounter, parsed_dni, patient_name_key)
        for encounter in existing_encounters
    )


def _encounter_dedupe_rank(encounter):
    printable_ready, _ = get_report_readiness(encounter, ignore_attendance=True)
    vital = getattr(encounter, "vital_signs", None)
    result_code = get_result_code_from_encounter(encounter)
    has_reports = encounter.generated_reports.exists()
    status_rank = {
        EncounterStatus.ENTREGADA: 5,
        EncounterStatus.INFORME_GENERADO: 4,
        EncounterStatus.REVISADA: 3,
        EncounterStatus.CARGADA: 2,
        EncounterStatus.PENDIENTE: 1,
        EncounterStatus.NO_LLEGO: 0,
    }.get(encounter.status, 0)
    vital_completeness = sum(
        1
        for value in (
            getattr(vital, "so2_rest", None),
            getattr(vital, "fc_rest", None),
            getattr(vital, "so2_post", None),
            getattr(vital, "fc_post", None),
        )
        if value is not None
    )
    return (
        1 if printable_ready else 0,
        1 if has_reports else 0,
        1 if encounter.attended else 0,
        1 if not encounter.no_show else 0,
        1 if bool(result_code) else 0,
        vital_completeness,
        status_rank,
    )


def unique_encounters_by_patient_day(encounters):
    unique = []
    seen_identity_keys = {}
    for encounter in encounters:
        patient = getattr(encounter, "patient", None)
        if not patient:
            unique.append(encounter)
            continue
        day_key = encounter.encounter_date.isoformat() if encounter.encounter_date else ""
        dni = normalize_document_number(getattr(patient, "dni", "") or "")
        name_key = normalize_patient_identity_name(getattr(patient, "full_name", "") or "")
        identity_key = (day_key, "dni", dni) if dni else ((day_key, "name", name_key) if name_key else None)
        if not identity_key:
            unique.append(encounter)
            continue

        current_rank = _encounter_dedupe_rank(encounter)
        previous = seen_identity_keys.get(identity_key)
        if previous is None:
            seen_identity_keys[identity_key] = (current_rank, encounter)
            unique.append(encounter)
            continue

        previous_rank, previous_encounter = previous
        if current_rank > previous_rank:
            previous_index = unique.index(previous_encounter)
            unique[previous_index] = encounter
            seen_identity_keys[identity_key] = (current_rank, encounter)
    return unique


def summarize_encounter_list(encounters):
    total = len(encounters)
    mutual = sum(1 for encounter in encounters if encounter.coverage_type == CoverageType.MUTUAL)
    attended = sum(1 for encounter in encounters if encounter.attended)
    no_show = sum(1 for encounter in encounters if encounter.no_show)
    cyclometry = sum(1 for encounter in encounters if encounter.study_type == StudyType.CICLOMETRIA)
    spirometry = sum(1 for encounter in encounters if encounter.study_type == StudyType.ESPIROMETRIA)
    return {
        "total": total,
        "mutual": mutual,
        "particular": sum(1 for encounter in encounters if encounter.coverage_type == CoverageType.PARTICULAR),
        "attended": attended,
        "no_show": no_show,
        "pending": max(total - attended - no_show, 0),
        "cyclometry": cyclometry,
        "spirometry": spirometry,
        "mutual_percent": round((mutual / total) * 100) if total else 0,
        "attendance_percent": round((attended / total) * 100) if total else 0,
    }


def normalize_phone_number(raw_value: str) -> str:
    raw_text = collapse_spaces(raw_value)
    if not raw_text:
        return ""
    has_plus = raw_text.startswith("+")
    digits = re.sub(r"\D+", "", raw_text)
    if len(digits) < 8:
        return ""
    return f"+{digits}" if has_plus else digits


def extract_phone_and_dni_from_drapp_text(raw_text: str):
    combined_text = str(raw_text or "")
    normalized_phone = ""
    phone_match_text = ""
    attached_dni_candidates = []
    attached_dni_prefix = ""

    for raw_phone in re.findall(r"\+?\d[\d ]{7,16}", combined_text):
        candidate_phone = normalize_phone_number(raw_phone)
        digits_only = candidate_phone.replace("+", "")
        if candidate_phone.startswith("+54") and len(digits_only) > 12:
            attached_dni_prefix = digits_only[12:]
            if attached_dni_prefix:
                attached_dni_candidates.append(attached_dni_prefix)
            candidate_phone = f"+{digits_only[:12]}"
            digits_only = candidate_phone.replace("+", "")
        if 10 <= len(digits_only) <= 12:
            normalized_phone = candidate_phone
            phone_match_text = raw_phone
            break

    text_without_phone = combined_text.replace(phone_match_text, " ", 1) if phone_match_text else combined_text

    dni = ""
    dni_pattern = re.compile(r"\b\d{1,3}(?:[.\s]\d{3}){1,3}\b|\b\d{7,8}\b")
    extra_suffix = ""
    if phone_match_text:
        suffix_index = combined_text.find(phone_match_text)
        if suffix_index >= 0:
            extra_suffix = combined_text[suffix_index + len(phone_match_text): suffix_index + len(phone_match_text) + 24]
    dotted_suffix_match = re.match(r"\s*[.\s]*(\d{1,3}(?:[.\s]\d{3}){1,2})", extra_suffix)
    if dotted_suffix_match:
        dotted_candidate = dotted_suffix_match.group(1)
        if attached_dni_prefix:
            attached_dni_candidates.insert(0, f"{attached_dni_prefix}{dotted_candidate}")
        attached_dni_candidates.append(dotted_candidate)

    for candidate in attached_dni_candidates + dni_pattern.findall(text_without_phone):
        normalized_dni = normalize_document_number(candidate)
        if 7 <= len(normalized_dni) <= 8:
            dni = normalized_dni
            break

    return normalized_phone, dni


def clean_drapp_name_candidate(raw_value: str, coverage_raw: str = "", practice_raw: str = "") -> str:
    text = collapse_spaces(raw_value or "")
    if not text:
        return ""

    text = re.sub(r"\+?\d[\d ]{7,16}", " ", text)
    text = re.sub(r"\b\d{1,3}(?:[.\s]\d{3}){1,3}\b|\b\d{7,8}\b", " ", text)

    removable_chunks = [coverage_raw, practice_raw, "Link de Pago", "Centro Respiratorio Integral", "Piguillem Gustavo"]
    removable_chunks.extend(DRAPP_COVERAGE_CANDIDATES)
    for chunk in removable_chunks:
        if not chunk:
            continue
        text = re.sub(re.escape(chunk), " ", text, flags=re.IGNORECASE)

    for pattern in DRAPP_NAME_NOISE_PATTERNS:
        text = pattern.sub(" ", text)

    cutoff_match = re.search(
        r"\b(?:ESPI\w*|CICLO\w*|PIG\w*|CENTRO|RESP\w*|INTEG\w*|LINK|PAGO|PARTIC\w*|PAMI|DOSEP|OSDE|SWISS|MEDIFE|OSECAC|IOSFA)\b",
        text,
        flags=re.IGNORECASE,
    )
    if cutoff_match and cutoff_match.start() > 0:
        text = text[:cutoff_match.start()]

    text = text.replace("|", " ")
    cleaned = collapse_spaces(text)
    cleaned_upper = normalize_for_match(cleaned)
    if any(cleaned_upper.startswith(token) for token in DRAPP_NAME_CUTOFF_TOKENS):
        return ""
    return cleaned


def extract_patient_name_from_drapp_row(raw_lines, coverage_raw: str = "", practice_raw: str = "") -> str:
    best_name = ""
    best_score = -1

    for raw_line in raw_lines or []:
        cleaned_line = clean_drapp_name_candidate(raw_line, coverage_raw=coverage_raw, practice_raw=practice_raw)
        normalized_name = normalize_imported_name(cleaned_line)
        if not normalized_name:
            continue

        normalized_compact = normalize_for_match(normalized_name)
        if (
            normalized_compact in DRAPP_ROW_SKIP_WORDS
            or normalized_compact.startswith("HACE")
            or normalized_compact.startswith("LINKDEPAGO")
        ):
            continue

        word_count = len([token for token in re.split(r"[\s,]+", normalized_name) if token])
        if word_count < 2:
            continue
        tokens = [token for token in re.split(r"[\s,]+", normalized_name) if token]
        if "," not in normalized_name and tokens and max(len(token) for token in tokens) <= 3:
            continue
        if any(token.startswith(DRAPP_NAME_CUTOFF_TOKENS) for token in tokens):
            continue

        score = len(normalized_name)
        if "," in normalized_name:
            score += 20
        if word_count >= 3:
            score += 8
        if len(tokens) >= 2 and all(len(token) <= 3 for token in tokens[:2]):
            score -= 20
        if raw_line == (raw_lines[0] if raw_lines else ""):
            score += 2

        if score > best_score:
            best_score = score
            best_name = normalized_name

    return best_name


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


def looks_like_drapp_tabular_text(raw_text: str) -> bool:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    if not lines:
        return False
    return any(len([part for part in line.split("\t") if part.strip()]) >= 5 for line in lines)


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
    if rows:
        return rows

    ocr_like_lines = [
        {"text": line, "y": index * 30, "norm": normalize_for_match(line), "items": []}
        for index, line in enumerate(lines)
    ]
    return extract_drapp_rows_from_ocr_lines(ocr_like_lines)


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


def _estimate_ocr_canvas_width(lines):
    max_x = 0.0
    for line in lines or []:
        for item in line.get("items", []) or []:
            try:
                max_x = max(max_x, float(item.get("x", 0) or 0))
            except (TypeError, ValueError):
                continue
    return max_x


def _join_structured_items(items):
    ordered_items = sorted(items or [], key=lambda item: float(item.get("x", 0) or 0))
    return collapse_spaces(" ".join(str(item.get("text", "") or "") for item in ordered_items))


def _structured_zone_text(line, min_ratio, max_ratio=None, canvas_width=None):
    items = line.get("items", []) or []
    if not items or not canvas_width:
        return ""
    min_x = canvas_width * min_ratio
    max_x = canvas_width * max_ratio if max_ratio is not None else None
    zone_items = []
    for item in items:
        try:
            item_x = float(item.get("x", 0) or 0)
        except (TypeError, ValueError):
            continue
        if item_x < min_x:
            continue
        if max_x is not None and item_x >= max_x:
            continue
        zone_items.append(item)
    return _join_structured_items(zone_items)


def _extract_structured_drapp_row_fields(row, canvas_width):
    structured_lines = row.get("structured_lines") or []
    if not structured_lines or not canvas_width:
        return None

    patient_lines = []
    coverage_chunks = []
    practice_chunks = []
    patient_zone_texts = []

    for line in structured_lines:
        patient_zone = _structured_zone_text(line, 0.11, 0.42, canvas_width)
        coverage_zone = _structured_zone_text(line, 0.42, 0.60, canvas_width)
        practice_zone = _structured_zone_text(line, 0.60, None, canvas_width)
        if patient_zone:
            patient_lines.append(patient_zone)
            patient_zone_texts.append(patient_zone)
        if coverage_zone:
            coverage_chunks.append(coverage_zone)
        if practice_zone:
            practice_chunks.append(practice_zone)

    patient_zone_text = " | ".join(patient_zone_texts)
    coverage_text = " | ".join(coverage_chunks)
    practice_text = " | ".join(practice_chunks)
    upper_coverage = coverage_text.upper()
    upper_practice = practice_text.upper()

    coverage_raw = ""
    for candidate in DRAPP_COVERAGE_CANDIDATES:
        if candidate in upper_coverage:
            coverage_raw = candidate.title() if candidate == "PARTICULAR" else candidate
            break

    practice_raw = ""
    normalized_practice = normalize_for_match(upper_practice)
    if "CICLOESPIROMETRIA" in normalized_practice or ("CICLO" in upper_practice and "ESPIRO" in upper_practice):
        practice_raw = "Cicloespirometria"
    elif "ESPIRO" in upper_practice:
        practice_raw = "Espirometria"

    patient_name = extract_patient_name_from_drapp_row(
        patient_lines or row.get("raw_lines", []),
        coverage_raw=coverage_raw,
        practice_raw=practice_raw,
    )
    phone, dni = extract_phone_and_dni_from_drapp_text(patient_zone_text or " | ".join(row.get("raw_lines", [])))

    return {
        "patient_name": patient_name,
        "coverage_raw": coverage_raw,
        "practice_raw": practice_raw,
        "phone": phone,
        "dni": dni,
    }


def extract_drapp_rows_from_ocr_lines(lines):
    rows = []
    agenda_date = parse_drapp_agenda_date(" ".join(line.get("text", "") for line in lines[:8]))
    canvas_width = _estimate_ocr_canvas_width(lines)
    current = None
    time_pattern = re.compile(r"(?<!\d)(\d{1,2}:\d{2})(?!\d)")

    for line in lines:
        match = time_pattern.search(line["text"])
        if match:
            if current:
                rows.append(current)
            if line.get("items"):
                filtered_items = [
                    item for item in (line.get("items") or [])
                    if not time_pattern.search(str(item.get("text", "") or ""))
                ]
                line_without_time = _join_structured_items(filtered_items).strip(" -|")
                structured_line = {
                    "text": line_without_time,
                    "y": line.get("y", 0),
                    "items": filtered_items,
                }
            else:
                line_without_time = time_pattern.sub("", line["text"]).strip(" -|")
                structured_line = None
            current = {
                "datetime_raw": match.group(1),
                "patient_name": "",
                "coverage_raw": "",
                "practice_raw": "",
                "phone": "",
                "dni": "",
                "raw_lines": [line_without_time] if line_without_time else [],
                "structured_lines": [structured_line] if structured_line and line_without_time else [],
            }
            continue
        if current:
            current["raw_lines"].append(line["text"])
            if line.get("items"):
                current["structured_lines"].append(
                    {
                        "text": line.get("text", ""),
                        "y": line.get("y", 0),
                        "items": list(line.get("items") or []),
                    }
                )
    if current:
        rows.append(current)

    parsed_rows = []
    for row in rows:
        combined_text = " | ".join(row["raw_lines"])
        upper_text = combined_text.upper()
        structured_fields = _extract_structured_drapp_row_fields(row, canvas_width)

        phone = structured_fields.get("phone", "") if structured_fields else ""
        dni = structured_fields.get("dni", "") if structured_fields else ""
        if not phone or not dni:
            fallback_phone, fallback_dni = extract_phone_and_dni_from_drapp_text(combined_text)
            phone = phone or fallback_phone
            dni = dni or fallback_dni

        coverage_raw = structured_fields.get("coverage_raw", "") if structured_fields else ""
        if not coverage_raw:
            for candidate in DRAPP_COVERAGE_CANDIDATES:
                if candidate in upper_text:
                    coverage_raw = candidate.title() if candidate == "PARTICULAR" else candidate
                    break

        practice_raw = structured_fields.get("practice_raw", "") if structured_fields else ""
        if not practice_raw:
            if "CICLOESPIROMETRIA" in normalize_for_match(upper_text):
                practice_raw = "Cicloespirometria"
            elif "CICLO" in upper_text and "ESPIRO" in upper_text:
                practice_raw = "Cicloespirometria"
            elif "ESPIRO" in upper_text:
                practice_raw = "Espirometria"

        patient_name = structured_fields.get("patient_name", "") if structured_fields else ""
        if not patient_name:
            patient_name = extract_patient_name_from_drapp_row(
                row["raw_lines"],
                coverage_raw=coverage_raw,
                practice_raw=practice_raw,
            )
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
        line_items = []
        for part in item.get("items", []) or []:
            if not isinstance(part, dict):
                continue
            part_text = collapse_spaces(part.get("text", ""))
            if not part_text:
                continue
            try:
                part_x = float(part.get("x", 0) or 0)
            except (TypeError, ValueError):
                part_x = 0.0
            try:
                part_y = float(part.get("y", y_coord) or y_coord)
            except (TypeError, ValueError):
                part_y = y_coord
            line_items.append({"text": part_text, "x": part_x, "y": part_y})
        lines.append({"text": text, "y": y_coord, "norm": normalize_for_match(text), "items": line_items})
    return extract_drapp_rows_from_ocr_lines(lines)


def import_drapp_rows(rows, request_user):
    created = 0
    skipped = 0
    default_physician = get_default_physician()
    seen_identity_keys = set()

    for row in rows:
        patient_name = normalize_imported_name(row.get("patient_name", ""))
        if not is_plausible_imported_patient_name(patient_name):
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
        patient_name_key = normalize_patient_identity_name(patient_name)
        day_key = encounter_date.isoformat()
        identity_key = (
            (day_key, "dni", parsed_dni)
            if parsed_dni
            else ((day_key, "name", patient_name_key) if patient_name_key else None)
        )

        if identity_key and identity_key in seen_identity_keys:
            skipped += 1
            continue

        if import_identity_exists_for_date(encounter_date, parsed_dni, patient_name):
            skipped += 1
            if identity_key:
                seen_identity_keys.add(identity_key)
            continue

        patient = Patient.all_objects.filter(dni=parsed_dni).first() if parsed_dni else None
        if patient is not None and patient.deleted_at:
            patient.restore(restore_batch=False)
        if patient is None and not parsed_dni:
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

        if identity_key:
            seen_identity_keys.add(identity_key)

        created_encounter = Encounter.objects.create(
            patient=patient,
            encounter_date=encounter_date,
            encounter_time=when.time(),
            study_type=study_type,
            status=EncounterStatus.NO_LLEGO,
            coverage_type=infer_coverage_type(row.get("coverage_raw", "")),
            referring_physician=default_physician,
            attended=False,
            no_show=True,
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


DRAPP_IMPORT_SIGNING_SALT = "clinic.drapp-import-preview.v1"


def serialize_drapp_rows_for_preview(rows):
    serialized = []
    for row in rows[:100]:
        agenda_date = row.get("agenda_date")
        if isinstance(agenda_date, date):
            agenda_date = agenda_date.isoformat()
        serialized.append(
            {
                "patient_name": normalize_imported_name(row.get("patient_name", "")),
                "dni": normalize_document_number(row.get("dni", "")),
                "phone": normalize_phone_number(row.get("phone", "")),
                "coverage_raw": collapse_spaces(row.get("coverage_raw", "")),
                "practice_raw": collapse_spaces(row.get("practice_raw", "")),
                "datetime_raw": collapse_spaces(row.get("datetime_raw", "")),
                "agenda_date": str(agenda_date or ""),
            }
        )
    return serialized


def build_drapp_import_preview(rows):
    serialized = serialize_drapp_rows_for_preview(rows)
    preview = []
    for index, row in enumerate(serialized):
        patient_name = row["patient_name"]
        parsed_dni = row["dni"]
        date_detected = bool(row["agenda_date"])
        try:
            agenda_date = date.fromisoformat(row["agenda_date"]) if row["agenda_date"] else timezone.localdate()
        except ValueError:
            agenda_date = timezone.localdate()
            date_detected = False
        duplicate = (
            import_identity_exists_for_date(agenda_date, parsed_dni, patient_name)
            if patient_name and date_detected
            else False
        )
        valid_name = is_plausible_imported_patient_name(patient_name)
        preview.append(
            {
                "index": index,
                "patient_name": patient_name,
                "dni": parsed_dni,
                "phone": row["phone"],
                "coverage_raw": row["coverage_raw"],
                "coverage_type": infer_coverage_type(row["coverage_raw"]),
                "practice_raw": row["practice_raw"],
                "study_type": infer_study_type(row["practice_raw"]),
                "datetime_raw": row["datetime_raw"],
                "agenda_date": agenda_date,
                "date_detected": date_detected,
                "duplicate": duplicate,
                "valid": valid_name and date_detected and not duplicate,
                "warning": (
                    "Ya existe en esa fecha"
                    if duplicate
                    else (
                        "Fecha no detectada: completala y marca la fila"
                        if not date_detected
                        else ("Nombre invalido: revisalo antes de importar" if not valid_name else "")
                    )
                ),
            }
        )
    token = signing.dumps(serialized, salt=DRAPP_IMPORT_SIGNING_SALT, compress=True)
    return preview, token


def confirmed_drapp_rows_from_request(request):
    token = request.POST.get("import_preview_token", "")
    try:
        original_rows = signing.loads(token, salt=DRAPP_IMPORT_SIGNING_SALT, max_age=30 * 60)
    except signing.BadSignature as error:
        raise ValueError("La vista previa vencio o fue modificada. Volve a leer la captura.") from error

    confirmed = []
    for index, original in enumerate(original_rows[:100]):
        if request.POST.get(f"row_{index}_selected") != "1":
            continue
        raw_agenda_date = request.POST.get(f"row_{index}_date", original.get("agenda_date", ""))
        try:
            agenda_date = date.fromisoformat(str(raw_agenda_date or ""))
        except ValueError as error:
            raise ValueError(f"Fila {index + 1}: completa una fecha valida antes de importar.") from error
        confirmed.append(
            {
                **original,
                "patient_name": request.POST.get(f"row_{index}_patient_name", original.get("patient_name", "")),
                "dni": request.POST.get(f"row_{index}_dni", original.get("dni", "")),
                "coverage_raw": request.POST.get(f"row_{index}_coverage", original.get("coverage_raw", "")),
                "practice_raw": request.POST.get(f"row_{index}_study", original.get("practice_raw", "")),
                "datetime_raw": request.POST.get(f"row_{index}_time", original.get("datetime_raw", "")),
                "agenda_date": agenda_date,
            }
        )
    return confirmed


def format_month_label(value: date) -> str:
    return f"{SPANISH_MONTHS[value.month - 1]} {value.year}"


def format_day_label(value: date) -> str:
    weekday = SPANISH_WEEKDAYS[value.weekday()]
    return f"{weekday} {value.day:02d}/{value.month:02d}/{value.year}"


def get_period_summary(queryset):
    if hasattr(queryset, "select_related"):
        encounters = queryset.select_related("patient")
    else:
        encounters = queryset
    return summarize_encounter_list(unique_encounters_by_patient_day(encounters))


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
    if patient.birth_date:
        today = timezone.localdate()
        return today.year - patient.birth_date.year - (
            (today.month, today.day) < (patient.birth_date.month, patient.birth_date.day)
        )
    if patient.age_reported is not None:
        return int(patient.age_reported)
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
        if vital.so2_rest is not None and (vital.so2_rest < 50 or vital.so2_rest > 100):
            impossible_values.append("SO2 reposo")
        if vital.so2_post is not None and (vital.so2_post < 50 or vital.so2_post > 100):
            impossible_values.append("SO2 post")
        if vital.fc_rest is not None and (vital.fc_rest < 20 or vital.fc_rest > 300):
            impossible_values.append("FC reposo")
        if vital.fc_post is not None and (vital.fc_post < 20 or vital.fc_post > 300):
            impossible_values.append("FC post")
        if impossible_values:
            flags.append("Valores imposibles: " + ", ".join(impossible_values))

    return flags


def build_inconsistency_message(encounter):
    flags = get_encounter_inconsistencies(encounter)
    if not flags:
        return ""
    return "Advertencias: " + " | ".join(flags)


def get_report_readiness(encounter, *, ignore_attendance=False):
    if encounter.no_show and not ignore_attendance:
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


def get_print_readiness(encounter, *, ignore_attendance=False):
    if encounter.no_show and not ignore_attendance:
        return False, "No llego"

    patient = encounter.patient
    result_code = get_result_code_from_encounter(encounter)

    missing = []
    if not str(getattr(patient, "full_name", "") or "").strip():
        missing.append("nombre")
    if not str(getattr(patient, "dni", "") or "").strip():
        missing.append("DNI")
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
    if not get_result_code_from_encounter(encounter):
        raise ValueError("Falta el resultado final del medico.")

    patron = normalizar_patron(getattr(result, "respiratory_pattern", "Normal"))
    grado_obst = (getattr(result, "obstruction_grade", "") or "Leve").strip().lower()
    grado_rest = (getattr(result, "restriction_grade", "") or "Leve").strip().lower()
    informe = construir_informe_espirometria(patron, grado_obst, grado_rest)
    broncodilatador_positivo = bool(getattr(result, "bronchodilator_positive", False))

    so2 = limpiar_entero(getattr(vital, "so2_rest", ""), default="") if vital else ""
    fc = limpiar_entero(getattr(vital, "fc_rest", ""), default="") if vital else ""
    include_walk = encounter.study_type == "Ciclometria" and (vital is not None or walk is not None)
    walk_rows = []
    if include_walk:
        walk_rows = build_walk_measurement_rows(vital, walk)

    pdf_attachment = get_latest_result_attachment(encounter)
    try:
        pdf_preview_pages = build_result_preview_images(pdf_attachment) if pdf_attachment else []
    except Exception:
        pdf_preview_pages = []
    include_mutual_packet = encounter.coverage_type == CoverageType.MUTUAL and include_walk
    walk_assessment = (
        build_walk_test_assessment(
            getattr(vital, "so2_rest", None),
            getattr(vital, "so2_post", None),
            completed=bool(getattr(walk, "completed", True)),
            stopped=bool(getattr(walk, "stopped", False)),
            symptoms=bool(getattr(walk, "symptoms", False)),
        )
        if include_walk
        else None
    )

    return {
        "encounter": encounter,
        "patient_name": str(patient.full_name or "").strip().upper(),
        "dni": formatear_dni(patient.dni),
        "doctor_name": normalizar_medico(getattr(encounter.referring_physician, "full_name", DEFAULT_DOCTOR)),
        "print_date": encounter.encounter_date.strftime("%d/%m/%Y"),
        "so2": so2,
        "fc": fc,
        "report_text": informe,
        "is_normal": patron == "Normal",
        "bronchodilator_positive": broncodilatador_positivo,
        "pattern": patron,
        "include_walk": include_walk,
        "walk_rows": walk_rows,
        "distance": str(getattr(walk, "distance_meters", "") or "200"),
        "completed": bool(getattr(walk, "completed", True)),
        "stopped": bool(getattr(walk, "stopped", False)),
        "symptoms": bool(getattr(walk, "symptoms", False)),
        "walk_assessment": walk_assessment,
        "include_mutual_packet": include_mutual_packet,
        "mutual_cvl_result": build_mutual_cvl_result(patron, grado_obst, grado_rest),
        "pdf_preview_pages": pdf_preview_pages,
        "pdf_attachment": pdf_attachment,
        "pdf_attachment_url": safe_attachment_url(pdf_attachment),
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
    import_preview=None,
    import_preview_token="",
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
        "import_preview": import_preview or [],
        "import_preview_token": import_preview_token,
    }
    return render(request, "clinic/dashboard.html", context)


@login_required
def dashboard(request):
    purge_expired_recycle_bin()
    if request.method == "POST":
        require_any_clinic_permission(request, "clinic.manage_agenda")
    today = timezone.localdate()
    quick_initial = {
        "study_type": "Ciclometria",
        "coverage_type": "Particular",
        "distance_meters": 200,
        "completed": True,
        "borg_final": 1,
        "bronchodilator_positive": False,
        "attended": False,
        "no_show": True,
    }
    today_encounters = (
        Encounter.objects.select_related("patient", "referring_physician", "vital_signs", "spirometry_result")
        .prefetch_related("generated_reports__attachment")
        .filter(encounter_date=today)
        .order_by("encounter_time", "created_at")
    )
    today_encounters = unique_encounters_by_patient_day(today_encounters)
    today_encounters = sort_dashboard_encounters(today_encounters)
    for encounter in today_encounters:
        encounter.result_code = get_result_code_from_encounter(encounter)
        encounter.status_css_class = get_status_badge_class(encounter.status)
        encounter.can_generate_report, encounter.report_block_reason = get_report_readiness(encounter)
        encounter.has_generated_reports = len(encounter.generated_reports.all()) > 0
        encounter.has_cycle_data = encounter_has_cycle_data(encounter)
        latest_report_info = get_latest_report_info(encounter)
        encounter.latest_report_url = latest_report_info["latest_report_url"]
        encounter.latest_report_name = latest_report_info["latest_report_name"]
        encounter.complete_report_url = latest_report_info["complete_report_url"]
        encounter.mutual_report_url = latest_report_info["mutual_report_url"]
        encounter.detail_url = latest_report_info["detail_url"]
    stats_map = Counter(encounter.status for encounter in today_encounters)
    status_cards = [
        {"value": value, "label": label, "total": stats_map.get(value, 0), "css_class": get_status_badge_class(value)}
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
                browser_ocr_error = None
                screenshot_error = None
                if ocr_lines_json:
                    try:
                        imported_rows.extend(extract_drapp_rows_from_browser_ocr(ocr_lines_json))
                    except ValueError as error:
                        browser_ocr_error = error
                use_raw_text = bool(raw_text) and (not ocr_lines_json or looks_like_drapp_tabular_text(raw_text))
                if raw_text and not use_raw_text and ocr_lines_json:
                    # Cuando la captura ya trae OCR estructurado del navegador,
                    # evitamos reprocesar el texto plano autogenerado porque pierde
                    # la geometria de filas y puede mezclar estudios/clinica con nombres.
                    raw_text = ""
                if use_raw_text and (not imported_rows or looks_like_drapp_tabular_text(raw_text)):
                    imported_rows.extend(extract_drapp_rows_from_text(raw_text))
                if screenshot and not imported_rows:
                    try:
                        if hasattr(screenshot, "seek"):
                            screenshot.seek(0)
                        imported_rows.extend(extract_drapp_rows_from_screenshot(screenshot))
                    except Exception as error:
                        screenshot_error = error
                if not imported_rows:
                    if screenshot_error:
                        import_form.add_error(
                            "screenshot",
                            f"No se pudo leer la captura automaticamente: {screenshot_error}",
                        )
                        if browser_ocr_error:
                            import_form.add_error(
                                "ocr_lines_json",
                                f"El OCR del navegador tampoco se pudo interpretar: {browser_ocr_error}",
                            )
                        messages.warning(
                            request,
                            "La captura no se pudo leer automaticamente. Pega el texto de Drapp y volve a importar.",
                        )
                    elif browser_ocr_error:
                        import_form.add_error(
                            "ocr_lines_json",
                            f"El OCR del navegador devolvio un formato invalido: {browser_ocr_error}",
                        )
                        messages.warning(
                            request,
                            "El OCR del navegador no se pudo interpretar. Proba de nuevo con la captura o subi el archivo manualmente.",
                        )
                    else:
                        messages.warning(
                            request,
                            "Pude leer la captura, pero no encontre filas validas para importar. Proba con una captura donde se vean la hora, el nombre y la cobertura del paciente.",
                        )
                    messages.warning(
                        request,
                        "Si usaste captura desde notebook, ahora la app intenta el archivo original como respaldo cuando el OCR web no arma filas utiles.",
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
                import_preview, import_preview_token = build_drapp_import_preview(imported_rows)
                messages.info(request, "Revisa las filas detectadas antes de agregarlas a la agenda.")
                return render_dashboard_response(
                    request,
                    today=today,
                    quick_form=quick_form,
                    import_form=import_form,
                    physician_form=physician_form,
                    today_encounters=today_encounters,
                    status_cards=status_cards,
                    operation_alerts=operation_alerts,
                    import_preview=import_preview,
                    import_preview_token=import_preview_token,
                )
        elif action == "confirm_drapp_import":
            try:
                confirmed_rows = confirmed_drapp_rows_from_request(request)
            except ValueError as error:
                messages.error(request, str(error))
                return redirect("clinic:dashboard")
            if not confirmed_rows:
                messages.warning(request, "No seleccionaste ninguna fila valida para importar.")
                return redirect("clinic:dashboard")
            created, skipped = import_drapp_rows(confirmed_rows, request.user)
            messages.success(
                request,
                f"Drapp confirmado: {created} paciente(s) agregados, {skipped} fila(s) omitidas.",
            )
            return redirect("clinic:dashboard")
        elif action == "add_physician":
            physician_form = ReferringPhysicianForm(request.POST)
            quick_form = QuickEncounterForm(initial=quick_initial)
            import_form = DrappImportForm()
            if physician_form.is_valid():
                physician = physician_form.save(commit=False)
                physician.full_name = collapse_spaces(physician.full_name)
                physician.active = True
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
            try:
                patient, reassigned = assign_encounter_patient_by_dni(encounter, new_dni)
            except ValueError as error:
                if is_ajax_request(request):
                    return JsonResponse({"ok": False, "message": str(error)}, status=409)
                messages.error(request, str(error))
                return redirect("clinic:dashboard")
            encounter.refresh_from_db()
            if is_ajax_request(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "patient_dni": encounter.patient.dni or "",
                        "patient_dni_display": formatear_dni(encounter.patient.dni) if encounter.patient.dni else "Completar DNI",
                        "message": "Historia clinica unificada por DNI." if reassigned else "",
                        **get_row_state_payload(encounter),
                    }
                )
            if reassigned:
                messages.success(request, f"DNI actualizado. La atencion quedo unificada con la historia de {patient.full_name}.")
            else:
                messages.success(request, f"DNI actualizado para {patient.full_name}.")
            return redirect("clinic:dashboard")
        elif action == "save_vitals_group":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            try:
                save_vitals_group_values(
                    encounter_id=request.POST.get("encounter_id"),
                    group_name=request.POST.get("vitals_group", ""),
                    so2_raw=request.POST.get("so2", ""),
                    fc_raw=request.POST.get("fc", ""),
                    request_user=request.user,
                )
            except (Encounter.DoesNotExist, ValueError) as error:
                message = str(error) or "No se pudieron guardar los signos vitales."
                if is_ajax_request(request):
                    return JsonResponse({"ok": False, "message": message}, status=400)
                messages.error(request, message)
                return redirect("clinic:dashboard")

            encounter = get_object_or_404(
                Encounter.objects.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
                .prefetch_related("generated_reports__attachment"),
                pk=request.POST.get("encounter_id"),
            )
            payload = {
                "ok": True,
                "field_name": f"vitals_{request.POST.get('vitals_group', '')}",
                "message": "Signos vitales guardados.",
            }
            payload.update(get_row_state_payload(encounter))
            if is_ajax_request(request):
                return JsonResponse(payload)
            messages.success(request, payload["message"])
            return redirect("clinic:dashboard")
        elif action == "inline_update":
            physician_form = ReferringPhysicianForm(initial={"active": True})
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient", "spirometry_result", "vital_signs", "walk_test")
                .prefetch_related("generated_reports"),
                pk=request.POST.get("encounter_id"),
            )
            try:
                update_inline_field(
                    encounter=encounter,
                    field_name=request.POST.get("field_name", ""),
                    raw_value=request.POST.get("value", ""),
                    request_user=request.user,
                    manual_save=request.POST.get("manual_save") == "1",
                )
            except ValueError as error:
                if is_ajax_request(request):
                    return JsonResponse({"ok": False, "message": str(error)}, status=400)
                messages.error(request, str(error))
                return redirect("clinic:dashboard")
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
                Encounter.objects.select_related("patient").prefetch_related("attachments", "generated_reports"),
                pk=request.POST.get("encounter_id"),
            )
            encounter_id = encounter.pk
            patient_name = encounter.patient.full_name
            soft_delete_encounter(
                encounter,
                actor=request.user,
                reason=f"Se elimino la atencion del dia para {patient_name}.",
            )
            if is_ajax_request(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "deleted": True,
                        "encounter_id": encounter_id,
                        "message": f"Se envio a papelera {patient_name}.",
                    }
                )
            messages.success(request, f"Se envio a papelera {patient_name}.")
            return redirect("clinic:dashboard")
        else:
            quick_form = QuickEncounterForm(request.POST)
            import_form = DrappImportForm()
            physician_form = ReferringPhysicianForm(initial={"active": True})
            if quick_form.is_valid():
                try:
                    encounter = save_quick_encounter(quick_form, request.user)
                except ValueError as error:
                    quick_form.add_error("patient_dni", str(error))
                else:
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
    encounters = unique_encounters_by_patient_day(encounters)
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
    purge_expired_recycle_bin()
    if request.method == "POST":
        require_any_clinic_permission(request, "clinic.manage_agenda")
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

    if request.method == "POST":
        action = request.POST.get("action")
        redirect_month = request.POST.get("month") or selected_date.strftime("%Y-%m")
        redirect_date = request.POST.get("date") or selected_date.isoformat()
        if action == "delete_encounter":
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient").prefetch_related("attachments", "generated_reports"),
                pk=request.POST.get("encounter_id"),
            )
            patient_name = encounter.patient.full_name
            soft_delete_encounter(encounter, actor=request.user, reason=f"Se elimino la atencion de {patient_name}.")
            messages.success(request, f"Se envio a papelera {patient_name}.")
            return redirect(f"{reverse('clinic:calendar')}?month={redirect_month}&date={redirect_date}")
        if action == "update_encounter_field":
            encounter = get_object_or_404(
                Encounter.objects.select_related("patient"),
                pk=request.POST.get("encounter_id"),
            )
            field_name = (request.POST.get("field_name") or "").strip()
            raw_value = (request.POST.get("value") or "").strip()
            if field_name == "coverage_type" and raw_value in dict(CoverageType.choices):
                encounter.coverage_type = raw_value
                encounter.save(update_fields=["coverage_type", "updated_at"])
                messages.success(request, f"Cobertura actualizada para {encounter.patient.full_name}.")
            elif field_name == "study_type" and raw_value in dict(StudyType.choices):
                encounter.study_type = raw_value
                encounter.save(update_fields=["study_type", "updated_at"])
                messages.success(request, f"Estudio actualizado para {encounter.patient.full_name}.")
            else:
                messages.error(request, "No pude actualizar ese dato de la agenda.")
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
    calendar_encounters = unique_encounters_by_patient_day(calendar_encounters)

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
    selected_encounters = unique_encounters_by_patient_day(selected_encounters)
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
        "coverage_choices": CoverageType.choices,
        "study_choices": StudyType.choices,
    }
    return render(request, "clinic/calendar.html", context)


@login_required
@permission_required("clinic.view_clinical_statistics", raise_exception=True)
def statistics_view(request):
    purge_expired_recycle_bin()
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_param = (request.GET.get("month") or "").strip()
    current_month_start = today.replace(day=1)

    try:
        selected_month_start = (
            datetime.strptime(month_param, "%Y-%m").date().replace(day=1)
            if month_param
            else current_month_start
        )
    except ValueError:
        selected_month_start = current_month_start

    if selected_month_start > current_month_start:
        selected_month_start = current_month_start

    next_month_start = (selected_month_start + timedelta(days=32)).replace(day=1)
    selected_month_last_day = next_month_start - timedelta(days=1)
    selected_month_end = min(selected_month_last_day, today)
    previous_month_start = (selected_month_start - timedelta(days=1)).replace(day=1)
    can_go_next_month = selected_month_start < current_month_start

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
            "start": current_month_start,
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

    selected_month_qs = Encounter.objects.filter(encounter_date__range=(selected_month_start, selected_month_end))
    current_month_summary = get_period_summary(selected_month_qs)
    current_month_alerts = get_operational_alerts(selected_month_qs)
    status_rows = []
    for value, label in EncounterStatus.choices:
        status_rows.append(
            {
                "label": label,
                "total": selected_month_qs.filter(status=value).count(),
            }
        )

    profiled_patients = [
        patient
        for patient in Patient.objects.all().order_by("-updated_at")
        if looks_like_profile_data(patient)
    ]
    cohort_patients = list(
        Patient.objects.prefetch_related(
            Prefetch(
                "encounters",
                queryset=Encounter.objects.select_related("spirometry_result").order_by(
                    "-encounter_date", "-encounter_time", "-created_at"
                ),
            )
        )
    )
    month_patient_ids = set(selected_month_qs.values_list("patient_id", flat=True).distinct())
    current_month_profiled_patients = [patient for patient in profiled_patients if patient.id in month_patient_ids]
    profile_summary = build_patient_profile_summary(profiled_patients)
    month_profile_summary = build_patient_profile_summary(current_month_profiled_patients)
    cohort_rows, diagnosis_rows = build_cohort_statistics(cohort_patients)

    context = {
        "today": today,
        "period_cards": period_cards,
        "last_7_days": last_7_days,
        "month_label": format_month_label(selected_month_start),
        "selected_month_param": selected_month_start.strftime("%Y-%m"),
        "previous_month_param": previous_month_start.strftime("%Y-%m"),
        "next_month_param": next_month_start.strftime("%Y-%m"),
        "can_go_next_month": can_go_next_month,
        "selected_month_range_label": f"{selected_month_start:%d/%m/%Y} al {selected_month_end:%d/%m/%Y}",
        "is_current_month": selected_month_start == current_month_start,
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
    purge_expired_recycle_bin()
    query = request.GET.get("q", "").strip()
    date_filter = (request.GET.get("date") or "").strip()
    coverage_filter = (request.GET.get("coverage") or "").strip()
    diagnosis_filter = (request.GET.get("diagnosis") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    physician_filter = (request.GET.get("physician") or "").strip()
    patients = Patient.objects.annotate(
        encounter_count=Count(
            "encounters",
            filter=Q(encounters__deleted_at__isnull=True),
            distinct=True,
        ),
        last_encounter_date=Max(
            "encounters__encounter_date",
            filter=Q(encounters__deleted_at__isnull=True),
        ),
    )
    if query:
        patients = patients.filter(
            Q(full_name__icontains=query) | Q(dni__icontains=query) | Q(patient_code__icontains=query)
        )
    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            patients = patients.filter(
                encounters__encounter_date=parsed_date,
                encounters__deleted_at__isnull=True,
            )
        except ValueError:
            pass
    if coverage_filter:
        patients = patients.filter(
            encounters__coverage_type=coverage_filter,
            encounters__deleted_at__isnull=True,
        )
    if status_filter:
        patients = patients.filter(
            encounters__status=status_filter,
            encounters__deleted_at__isnull=True,
        )
    if physician_filter:
        patients = patients.filter(
            encounters__referring_physician_id=physician_filter,
            encounters__deleted_at__isnull=True,
        )
    if diagnosis_filter:
        parsed = parse_result_code(diagnosis_filter)
        if parsed:
            pattern = parsed["pattern"]
            patients = patients.filter(
                encounters__deleted_at__isnull=True,
                encounters__spirometry_result__respiratory_pattern=pattern,
            )
            if parsed["obstruction_grade"]:
                patients = patients.filter(
                    encounters__deleted_at__isnull=True,
                    encounters__spirometry_result__obstruction_grade=parsed["obstruction_grade"],
                )
            if parsed["restriction_grade"]:
                patients = patients.filter(
                    encounters__deleted_at__isnull=True,
                    encounters__spirometry_result__restriction_grade=parsed["restriction_grade"],
                )
        else:
            normalized = normalize_for_match(diagnosis_filter)
            if normalized:
                patients = patients.filter(
                    Q(encounters__deleted_at__isnull=True)
                    & (
                        Q(encounters__spirometry_result__respiratory_pattern__icontains=diagnosis_filter)
                        | Q(encounters__spirometry_result__obstruction_grade__icontains=diagnosis_filter)
                        | Q(encounters__spirometry_result__restriction_grade__icontains=diagnosis_filter)
                    )
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
    purge_expired_recycle_bin()
    if request.method == "POST":
        require_any_clinic_permission(request, "clinic.manage_agenda", "clinic.review_medically")
    patient = get_object_or_404(Patient, pk=pk)
    document_form = PatientDocumentUploadForm(request.POST or None, request.FILES or None, patient=patient)

    if request.method == "POST" and request.POST.get("action") == "generate_patient_report":
        scope = request.POST.get("report_scope", "complete")
        encounter_id = request.POST.get("encounter_id")
        encounter = get_object_or_404(
            patient.encounters.select_related(
                "patient",
                "referring_physician",
                "vital_signs",
                "walk_test",
                "spirometry_result",
            ),
            pk=encounter_id,
        )
        if scope not in {"complete", "mutual"}:
            messages.error(request, "Tipo de informe no valido.")
            return redirect("clinic:patient_detail", pk=patient.pk)

        can_generate_report, report_block_reason = get_report_readiness(encounter, ignore_attendance=True)
        if not can_generate_report:
            messages.error(request, f"No se puede generar el informe. {report_block_reason}.")
            return redirect("clinic:patient_detail", pk=patient.pk)

        inconsistency_flags = get_encounter_inconsistencies(encounter)
        if inconsistency_flags and request.POST.get("confirm_inconsistencies") != "1":
            messages.warning(
                request,
                "Revisa estas inconsistencias antes de generar: " + " | ".join(inconsistency_flags),
            )
            return redirect("clinic:patient_detail", pk=patient.pk)

        try:
            artifacts = build_report_artifacts_for_scope(encounter, scope)
        except Exception as error:
            messages.error(request, f"No se pudo generar el informe: {error}")
            return redirect("clinic:patient_detail", pk=patient.pk)

        if not artifacts:
            messages.error(request, "No hay informe de mutual para esta atencion. Revisar cobertura y datos de caminata.")
            return redirect("clinic:patient_detail", pk=patient.pk)

        try:
            generated_count = save_generated_report_artifacts(encounter, artifacts, request.user)
        except Exception as error:
            messages.error(request, f"No se pudo guardar el informe: {error}")
            return redirect("clinic:patient_detail", pk=patient.pk)

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
                details="Se marco como atendido despues de guardar el informe desde historia clinica.",
            )

        encounter.status = EncounterStatus.INFORME_GENERADO
        encounter.updated_by = request.user
        encounter.save(update_fields=["status", "updated_by", "updated_at"])
        report_label = "Informe mutual" if scope == "mutual" else "Informe completo"
        record_encounter_event(
            encounter,
            EncounterEventType.REPORT,
            f"{report_label} generado",
            actor=request.user,
            details=f"Se generaron {generated_count} archivo(s) desde historia clinica.",
            metadata={"generated_count": generated_count, "scope": scope},
        )
        messages.success(request, f"{report_label} generado correctamente.")
        return redirect("clinic:patient_detail", pk=patient.pk)

    if request.method == "POST" and request.POST.get("action") == "delete_encounter":
        encounter_id = request.POST.get("encounter_id")
        encounter = get_object_or_404(
            patient.encounters.select_related("patient").prefetch_related("attachments", "generated_reports"),
            pk=encounter_id,
        )
        patient_name = encounter.patient.full_name
        soft_delete_encounter(
            encounter,
            actor=request.user,
            reason=f"Se elimino la atencion desde historia clinica para {patient_name}.",
        )
        messages.success(request, f"Se envio a papelera la atencion de {patient_name}.")
        return redirect("clinic:patient_detail", pk=patient.pk)

    if request.method == "POST" and request.POST.get("action") == "upload_patient_document":
        if document_form.is_valid():
            encounter = document_form.cleaned_data["encounter"]
            uploaded = document_form.cleaned_data["file"]
            file_kind = document_form.cleaned_data["file_kind"]
            guessed_mime = str(getattr(uploaded, "content_type", "") or mimetypes.guess_type(uploaded.name)[0] or "")
            attachment = Attachment(
                encounter=encounter,
                file_kind=file_kind,
                original_name=str(getattr(uploaded, "name", "") or "archivo"),
                mime_type=guessed_mime,
                uploaded_by=request.user,
            )
            attachment.file.save(attachment.original_name, uploaded, save=True)
            record_encounter_event(
                encounter,
                EncounterEventType.DOCUMENT,
                "Documento agregado desde historia clinica",
                actor=request.user,
                details=f"Archivo: {attachment.original_name} | Tipo: {attachment.get_file_kind_display()}",
            )
            messages.success(request, "Documento agregado al paciente correctamente.")
            return redirect("clinic:patient_detail", pk=patient.pk)

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
        encounter.pdf_attachment_url = safe_attachment_url(encounter.pdf_attachment)
        encounter.progression = progression_map.get(encounter.pk, {"label": "Sin base", "tone": "muted", "detail": ""})
        encounter.suggestion = build_stored_suggestion_context(getattr(encounter, "spirometry_result", None))
        encounter.can_print_result, encounter.print_block_reason = get_print_readiness(encounter, ignore_attendance=True)
        encounter.walk_assessment = build_walk_test_assessment(
            getattr(getattr(encounter, "vital_signs", None), "so2_rest", None),
            getattr(getattr(encounter, "vital_signs", None), "so2_post", None),
            completed=bool(getattr(getattr(encounter, "walk_test", None), "completed", True)),
            stopped=bool(getattr(getattr(encounter, "walk_test", None), "stopped", False)),
            symptoms=bool(getattr(getattr(encounter, "walk_test", None), "symptoms", False)),
        ) if encounter.study_type == StudyType.CICLOMETRIA else None
        latest_report_info = get_latest_report_info(encounter)
        encounter.latest_report_url = latest_report_info["latest_report_url"]
        encounter.latest_report_name = latest_report_info["latest_report_name"]
        encounter.complete_report_url = latest_report_info["complete_report_url"]
        encounter.complete_report_name = latest_report_info["complete_report_name"]
        encounter.mutual_report_url = latest_report_info["mutual_report_url"]
        encounter.mutual_report_name = latest_report_info["mutual_report_name"]
        encounter.detail_url = latest_report_info["detail_url"]
        encounter.can_generate_report, encounter.report_block_reason = get_report_readiness(
            encounter,
            ignore_attendance=True,
        )
        encounter.can_print_result, encounter.print_block_reason = get_print_readiness(
            encounter,
            ignore_attendance=True,
        )
        encounter.inconsistency_message = build_inconsistency_message(encounter)
        encounter.timeline_preview = list(encounter.events.all()[:3])

    patient_documents = list(
        Attachment.objects.filter(encounter__patient=patient)
        .select_related("encounter", "uploaded_by")
        .order_by("-created_at")
    )
    for attachment in patient_documents:
        attachment.safe_url = safe_attachment_url(attachment)
    patient_events = (
        EncounterEvent.objects.filter(patient=patient)
        .select_related("actor", "encounter")
        .order_by("-created_at")[:25]
    )
    operational_summary = {
        "total_documents": len(patient_documents),
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
            "document_form": document_form,
        },
    )


@login_required
@permission_required("clinic.manage_agenda", raise_exception=True)
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
@permission_required("clinic.manage_agenda", raise_exception=True)
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
@permission_required("clinic.manage_agenda", raise_exception=True)
def patient_delete(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    if request.method == "POST":
        patient_name = patient.full_name
        soft_delete_patient(patient, actor=request.user, reason=f"Se envio a papelera el paciente {patient_name}.")
        messages.success(request, f"Se envio a papelera {patient_name}.")
        return redirect("clinic:patient_list")

    return render(request, "clinic/patient_confirm_delete.html", {"patient": patient})


@login_required
@permission_required("clinic.manage_agenda", raise_exception=True)
def recycle_bin_view(request):
    purge_expired_recycle_bin()

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        patient_id = request.POST.get("patient_id")
        encounter_id = request.POST.get("encounter_id")

        if action == "restore_patient" and patient_id:
            patient = get_object_or_404(Patient.all_objects, pk=patient_id, deleted_at__isnull=False)
            restore_deleted_patient(patient)
            messages.success(request, f"Se restauró {patient.full_name}.")
        elif action == "restore_encounter" and encounter_id:
            encounter = get_object_or_404(
                Encounter.all_objects.select_related("patient"),
                pk=encounter_id,
                deleted_at__isnull=False,
            )
            restore_deleted_encounter(encounter)
            messages.success(request, f"Se restauró la atención de {encounter.patient.full_name}.")
        elif action == "purge_patient" and patient_id:
            if not request.user.has_perm("clinic.purge_clinical_data"):
                raise PermissionDenied("No tenes permiso para eliminar datos clinicos definitivamente.")
            patient = get_object_or_404(Patient.all_objects, pk=patient_id, deleted_at__isnull=False)
            patient_name = patient.full_name
            patient.delete()
            messages.success(request, f"Se eliminó definitivamente a {patient_name}.")
        elif action == "purge_encounter" and encounter_id:
            if not request.user.has_perm("clinic.purge_clinical_data"):
                raise PermissionDenied("No tenes permiso para eliminar datos clinicos definitivamente.")
            encounter = get_object_or_404(
                Encounter.all_objects.select_related("patient"),
                pk=encounter_id,
                deleted_at__isnull=False,
            )
            patient_name = encounter.patient.full_name
            encounter.delete()
            messages.success(request, f"Se eliminó definitivamente la atención de {patient_name}.")
        elif action == "empty_trash":
            if not request.user.has_perm("clinic.purge_clinical_data"):
                raise PermissionDenied("No tenes permiso para vaciar la papelera.")
            Encounter.all_objects.filter(deleted_at__isnull=False).delete()
            Patient.all_objects.filter(deleted_at__isnull=False).delete()
            messages.success(request, "Se vació la papelera.")
        else:
            messages.error(request, "No entendí la acción de papelera.")
        return redirect("clinic:recycle_bin")

    deleted_patients = Patient.all_objects.filter(deleted_at__isnull=False).order_by("-deleted_at")
    deleted_encounters = Encounter.all_objects.select_related("patient").filter(deleted_at__isnull=False).order_by("-deleted_at")

    return render(
        request,
        "clinic/recycle_bin.html",
        {
            "deleted_patients": deleted_patients,
            "deleted_encounters": deleted_encounters,
            "deleted_patients_count": deleted_patients.count(),
            "deleted_encounters_count": deleted_encounters.count(),
            "trash_is_empty": not deleted_patients.exists() and not deleted_encounters.exists(),
            "retention_days": RECYCLE_BIN_RETENTION_DAYS,
        },
    )


@login_required
@permission_required("clinic.manage_agenda", raise_exception=True)
def encounter_create(request):
    if request.method == "POST":
        form = QuickEncounterForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                encounter = save_quick_encounter(form, request.user)
            except ValueError as error:
                form.add_error("patient_dni", str(error))
            else:
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
                "stopped": False,
                "symptoms": False,
                "borg_final": 1,
                "attended": False,
                "no_show": True,
            }
        )

    return render(
        request,
        "clinic/encounter_form.html",
        {"form": form, "result_code_suggestions": RESULT_CODE_SUGGESTIONS},
    )


@login_required
@permission_required("clinic.manage_agenda", raise_exception=True)
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
            try:
                save_quick_encounter(form, request.user, encounter=encounter)
            except ValueError as error:
                form.add_error("patient_dni", str(error))
            else:
                messages.success(request, "Atencion actualizada correctamente.")
                return_to = request.POST.get("return_to", "").strip()
                if return_to and url_has_allowed_host_and_scheme(return_to, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    return redirect(return_to)
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
                "stopped": getattr(walk, "stopped", False),
                "symptoms": getattr(walk, "symptoms", False),
                "borg_final": getattr(walk, "borg_final", 1),
                "respiratory_result": current_result,
                "bronchodilator_positive": bool(getattr(spirometry, "bronchodilator_positive", False)),
                "attended": encounter.attended,
                "no_show": encounter.no_show,
            }
        )

    return render(
        request,
        "clinic/encounter_form.html",
        {
            "form": form,
            "edit_mode": True,
            "encounter": encounter,
            "result_code_suggestions": RESULT_CODE_SUGGESTIONS,
            "return_to": request.GET.get("next", "").strip(),
        },
    )


@login_required
@permission_required("clinic.review_medically", raise_exception=True)
def doctor_review_list(request):
    purge_expired_recycle_bin()
    search_query = request.GET.get("q", "").strip()
    date_str = request.GET.get("date", "").strip()
    # Keep the doctor's queue on the same local calendar day as Inicio/Calendario.
    today = timezone.localdate()

    selected_date = today
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = today

    encounters_qs = (
        Encounter.objects.select_related("patient", "spirometry_result")
        .prefetch_related("attachments")
    )

    if search_query:
        # If searching, we search across all dates to find the patient
        encounters_qs = encounters_qs.filter(
            Q(patient__full_name__icontains=search_query) | Q(patient__dni__icontains=search_query)
        )
    else:
        # Default view: only selected date
        encounters_qs = encounters_qs.filter(encounter_date=selected_date)
    encounters_qs = unique_encounters_by_patient_day(encounters_qs.order_by("-encounter_date", "-created_at"))

    review_cards = []
    counters = {"pending": 0, "missing_pdf": 0, "done": 0}
    done_statuses = get_doctor_review_done_statuses()

    # System-wide counters for the selected date (or all if searching)
    counter_qs = Encounter.objects.prefetch_related("attachments")
    if not search_query:
        counter_qs = counter_qs.filter(encounter_date=selected_date)
    counter_qs = unique_encounters_by_patient_day(counter_qs.order_by("-encounter_date", "-created_at"))

    for enc in counter_qs:
        has_pdf = encounter_has_review_pdf(enc)
        is_done = enc.status in done_statuses
        if is_done:
            counters["done"] += 1
        elif enc.attended and has_pdf:
            counters["pending"] += 1
        else:
            counters["missing_pdf"] += 1

    for encounter in encounters_qs:
        pdf_attachment = get_latest_result_attachment(encounter)
        result_code = get_result_code_from_encounter(encounter)
        has_pdf = bool(pdf_attachment)
        is_done = encounter.status in done_statuses

        if is_done:
            review_state = "done"
            state_label = "Resultado listo"
            state_help = f"Resultado cargado: {result_code or 'N/A'}."
            action_label = "Ver revision"
            priority = 3
        elif encounter.attended and has_pdf:
            review_state = "pending"
            state_label = "Revisar ahora"
            state_help = "Paciente atendido con PDF cargado. Falta que el medico marque el resultado."
            action_label = "Revisar PDF"
            priority = 1
        else:
            review_state = "missing_pdf"
            state_label = "Sin PDF / no atendido"
            state_help = "Todavia no esta listo para revision medica."
            action_label = "Abrir ficha"
            priority = 2

        review_cards.append(
            {
                "encounter": encounter,
                "pdf_attachment": pdf_attachment,
                "result_code": result_code,
                "review_state": review_state,
                "state_label": state_label,
                "state_help": state_help,
                "action_label": action_label,
                "priority": priority,
            }
        )

    # Sort: pending with PDF first, then missing PDF, then done.
    review_cards.sort(
        key=lambda card: (
            card["priority"],
            -card["encounter"].encounter_date.toordinal(),
            -(card["encounter"].encounter_time.hour * 60 + card["encounter"].encounter_time.minute) if card["encounter"].encounter_time else 0,
        )
    )

    paginator = Paginator(review_cards, 20) # More per page if filtered
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "clinic/doctor_review_list.html",
        {
            "page_obj": page_obj,
            "review_counters": counters,
            "search_query": search_query,
            "selected_date": selected_date.strftime("%Y-%m-%d"),
            "display_date": selected_date,
            "today": today,
        },
    )


@login_required
@permission_required("clinic.review_medically", raise_exception=True)
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
                    snapshot, changed_fields, patient_identity_mismatch = apply_profile_analysis_to_encounter(encounter, analysis)
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
                mark_encounter_attended(
                    encounter,
                    request.user,
                    details="Se marco como atendido al cargar el resultado de espirometria.",
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
            else:
                pdf_attachment = get_latest_result_attachment(encounter)
                if pdf_attachment:
                    try:
                        analysis = build_analysis_for_uploaded_result(pdf_attachment, analysis_payload_json=analysis_payload_json)
                        snapshot, changed_fields, patient_identity_mismatch = apply_profile_analysis_to_encounter(encounter, analysis)
                        if analysis.get("values"):
                            store_spirometry_analysis(encounter, analysis)
                        if snapshot and not patient_identity_mismatch:
                            extracted_name = snapshot.get("full_name") or encounter.patient.full_name
                            extracted_code = snapshot.get("patient_code") or snapshot.get("dni") or "-"
                            extraction_message = f" PDF revisado: {extracted_name} / doc {extracted_code}."
                            if changed_fields:
                                extraction_message += f" Datos actualizados: {', '.join(changed_fields)}."
                    except Exception as error:
                        messages.warning(request, f"No se pudieron releer los datos del PDF ya cargado: {error}")

            result_code = form.cleaned_data.get("respiratory_result") or current_result or ""
            if not result_code:
                messages.success(
                    request,
                    "Archivo cargado y sugerencia preparada. Elegi el resultado medico o usa el boton sugerido y guarda la revision.",
                )
                return redirect("clinic:doctor_review_detail", pk=encounter.pk)
            spirometry_result = apply_result_code_to_spirometry(encounter, result_code)
            spirometry_result.bronchodilator_positive = bool(form.cleaned_data.get("bronchodilator_positive"))
            spirometry_result.save(update_fields=["bronchodilator_positive", "updated_at"])
            previous_attendance_label = get_attendance_label(encounter)
            encounter.attended = True
            if encounter.attended_at is None:
                encounter.attended_at = timezone.now()
            encounter.no_show = False
            encounter.status = EncounterStatus.REVISADA
            encounter.updated_by = request.user
            encounter.validated_by = request.user
            encounter.validated_at = timezone.now()
            encounter.save(
                update_fields=[
                    "attended",
                    "attended_at",
                    "no_show",
                    "status",
                    "updated_by",
                    "validated_by",
                    "validated_at",
                    "updated_at",
                ]
            )
            if previous_attendance_label != get_attendance_label(encounter):
                record_encounter_event(
                    encounter,
                    EncounterEventType.ATTENDANCE,
                    "Asistencia actualizada automaticamente",
                    actor=request.user,
                    details="Se marco como atendido al guardar la revision medica.",
                )
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
        form = DoctorReviewForm(
            initial={
                "respiratory_result": current_result,
                "bronchodilator_positive": bool(
                    getattr(getattr(encounter, "spirometry_result", None), "bronchodilator_positive", False)
                ),
            }
        )

    pdf_attachment = get_latest_result_attachment(encounter)
    pdf_attachment_url = safe_attachment_url(pdf_attachment)
    pdf_preview_pages = []
    preview_error = ""
    spirometry_suggestion = build_stored_suggestion_context(getattr(encounter, "spirometry_result", None))
    review_queue = build_doctor_review_queue(encounter.encounter_date, encounter)
    next_review_encounter = review_queue["next_encounter"]
    if pdf_attachment:
        try:
            pdf_preview_pages = build_result_preview_images(pdf_attachment)
        except Exception as error:
            preview_error = str(error)
        if pdf_attachment.file_kind == AttachmentKind.PDF_RESULTADO and not spirometry_suggestion:
            try:
                with local_field_file_path(pdf_attachment.file) as attachment_path:
                    generated_suggestion = build_spirometry_suggestion_from_pdf(
                        str(attachment_path),
                        attachment_id=pdf_attachment.pk,
                    )
                if generated_suggestion.get("code"):
                    spirometry_suggestion = generated_suggestion
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
            "current_result": current_result,
            "pdf_attachment": pdf_attachment,
            "pdf_attachment_url": pdf_attachment_url,
            "pdf_preview_pages": pdf_preview_pages,
            "preview_error": preview_error,
            "result_attachment_is_image": bool(pdf_attachment and is_result_image_attachment(pdf_attachment)),
            "result_code_suggestions": RESULT_CODE_SUGGESTIONS,
            "patient_profile_available": looks_like_profile_data(encounter.patient),
            "spirometry_suggestion": spirometry_suggestion,
            "inconsistency_flags": inconsistency_flags,
            "review_queue": review_queue,
            "previous_review_encounter": review_queue["previous_encounter"],
            "next_review_encounter": next_review_encounter,
        },
    )


@login_required
@permission_required("clinic.review_medically", raise_exception=True)
def doctor_review_queue_state(request, pk):
    encounter = get_object_or_404(Encounter, pk=pk)
    queue_info = build_doctor_review_queue(encounter.encounter_date, encounter)
    previous_encounter = queue_info["previous_encounter"]
    next_encounter = queue_info["next_encounter"]
    previous_label = ""
    next_label = ""
    if previous_encounter:
        previous_label = previous_encounter.patient.full_name
        if previous_encounter.encounter_time:
            previous_label = f"{previous_encounter.encounter_time.strftime('%H:%M')} - {previous_label}"
    if next_encounter:
        next_label = next_encounter.patient.full_name
        if next_encounter.encounter_time:
            next_label = f"{next_encounter.encounter_time.strftime('%H:%M')} - {next_label}"
    return JsonResponse(
        {
            "ok": True,
            "pending_total": queue_info["pending_total"],
            "current_is_pending": queue_info["current_is_pending"],
            "remaining_after_current": queue_info["remaining_after_current"],
            "current_index": queue_info["current_index"] + 1 if queue_info["current_index"] is not None else None,
            "previous_encounter_id": previous_encounter.pk if previous_encounter else None,
            "previous_encounter_name": previous_encounter.patient.full_name if previous_encounter else "",
            "previous_encounter_label": previous_label,
            "previous_encounter_url": reverse("clinic:doctor_review_detail", args=[previous_encounter.pk]) if previous_encounter else "",
            "next_encounter_id": next_encounter.pk if next_encounter else None,
            "next_encounter_name": next_encounter.patient.full_name if next_encounter else "",
            "next_encounter_label": next_label,
            "next_encounter_url": reverse("clinic:doctor_review_detail", args=[next_encounter.pk]) if next_encounter else "",
            "queue_date_label": encounter.encounter_date.strftime("%d/%m/%Y"),
            "pending_ids": [item.pk for item in queue_info["pending_encounters"]],
        }
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
        ).prefetch_related("attachments", "generated_reports__attachment", "events__actor"),
        pk=pk,
    )
    for attachment in encounter.attachments.all():
        attachment.safe_url = safe_attachment_url(attachment)
    for report in encounter.generated_reports.all():
        report.attachment_url = safe_attachment_url(report.attachment)
    can_generate_report, report_block_reason = get_report_readiness(encounter, ignore_attendance=True)
    can_print_result, print_block_reason = get_print_readiness(encounter, ignore_attendance=True)
    return render(
        request,
        "clinic/encounter_detail.html",
        {
            "encounter": encounter,
            "inconsistency_flags": get_encounter_inconsistencies(encounter),
            "can_generate_report": can_generate_report,
            "report_block_reason": report_block_reason,
            "can_print_result": can_print_result,
            "print_block_reason": print_block_reason,
        },
    )


@login_required
@permission_required("clinic.manage_agenda", raise_exception=True)
@require_POST
def encounter_technician_notes(request, pk):
    encounter = get_object_or_404(Encounter, pk=pk)
    notes = str(request.POST.get("technician_notes", "") or "").strip()
    if len(notes) > 2000:
        messages.error(request, "La nota puede tener hasta 2000 caracteres.")
        return redirect("clinic:doctor_review_detail", pk=encounter.pk)

    encounter.technician_notes = notes
    encounter.updated_by = request.user
    encounter.save(update_fields=["technician_notes", "updated_by", "updated_at"])
    record_encounter_event(
        encounter,
        EncounterEventType.UPDATED,
        "Nota del espirometrista actualizada",
        actor=request.user,
        details="Se actualizo la nota visible para la revision medica.",
    )
    messages.success(request, "Nota para el medico guardada.")
    return redirect("clinic:doctor_review_detail", pk=encounter.pk)


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
    can_print, block_reason = get_print_readiness(encounter, ignore_attendance=True)
    if not can_print:
        messages.error(request, f"No se puede imprimir esta atencion. {block_reason}.")
        return redirect("clinic:encounter_detail", pk=encounter.pk)
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
    encounters = unique_encounters_by_patient_day(encounters)
    encounters = sorted(
        encounters,
        key=lambda encounter: (
            encounter.encounter_time or datetime_time(23, 59),
            encounter.created_at,
            encounter.pk,
        ),
    )

    printable = []
    blocked = []
    for encounter in encounters:
        can_print, reason = get_print_readiness(encounter)
        if can_print:
            try:
                printable.append(build_print_context_for_encounter(encounter))
            except Exception as error:
                blocked.append({"encounter": encounter, "reason": f"No se pudo preparar: {error}"})
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

    require_any_clinic_permission(request, "clinic.manage_agenda", "clinic.review_medically")

    can_generate_report, report_block_reason = get_report_readiness(encounter, ignore_attendance=True)
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
        generated_count = save_generated_report_artifacts(encounter, artifacts, request.user)
    except Exception as error:
        if is_ajax_request(request):
            payload = {"ok": False, "message": f"No se pudo generar el informe: {error}"}
            payload.update(get_row_state_payload(encounter))
            return JsonResponse(payload, status=500)
        messages.error(request, f"No se pudo generar el informe: {error}")
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
            details="Se marco como atendido despues de generar el informe correctamente.",
        )

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
