from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
import re
import unicodedata
import uuid


User = get_user_model()


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class StudyType(models.TextChoices):
    CICLOMETRIA = "Ciclometria", "Ciclometria"
    ESPIROMETRIA = "Espirometria", "Espirometria"


class EncounterStatus(models.TextChoices):
    PENDIENTE = "Pendiente", "Pendiente"
    CARGADA = "Cargada", "Cargada"
    REVISADA = "Revisada por medico", "Revisada por medico"
    INFORME_GENERADO = "Informe generado", "Informe generado"
    ENTREGADA = "Entregada", "Entregada"
    NO_LLEGO = "No llego", "No llego"


class CoverageType(models.TextChoices):
    MUTUAL = "Mutual", "Mutual"
    PARTICULAR = "Particular", "Particular"


class RespiratoryPattern(models.TextChoices):
    NORMAL = "Normal", "Normal"
    OBSTRUCTIVO = "Obstructivo", "Obstructivo"
    RESTRICTIVO = "Restrictivo", "Restrictivo"
    MIXTO = "Mixto", "Mixto"


class SeverityGrade(models.TextChoices):
    LEVE = "Leve", "Leve"
    MODERADA = "Moderada", "Moderada"
    MODERADAMENTE_SEVERA = "Moderadamente severa", "Moderadamente severa"
    SEVERA = "Severa", "Severa"


class AttachmentKind(models.TextChoices):
    PDF_RESULTADO = "pdf_resultado", "PDF resultado"
    FOTO_RESULTADO = "foto_resultado", "Foto resultado"
    INFORME_DOCX = "informe_docx", "Informe DOCX"
    INFORME_PDF = "informe_pdf", "Informe PDF"
    OTRO = "otro", "Otro"


class AttachmentAnalysisStatus(models.TextChoices):
    UPLOADED = "uploaded", "Archivo subido"
    DETECTED = "detected", "Datos detectados"
    FAILED = "failed", "Falló la lectura"


class ReportType(models.TextChoices):
    ESPIROMETRIA = "Espirometria", "Espirometria"
    COMPLETO = "Completo", "Completo"
    MUTUAL = "Mutual", "Mutual"


class EncounterEventType(models.TextChoices):
    CREATED = "created", "Creacion"
    UPDATED = "updated", "Actualizacion"
    ATTENDANCE = "attendance", "Asistencia"
    REVIEW = "review", "Revision medica"
    REPORT = "report", "Informe"
    DOCUMENT = "document", "Documento"
    IMPORT = "import", "Importacion"


class Patient(TimeStampedModel):
    objects = ActiveManager()
    all_objects = models.Manager()

    full_name = models.CharField("Apellido y nombre", max_length=150)
    patient_code = models.CharField("Codigo de paciente", max_length=40, blank=True, db_index=True)
    last_name = models.CharField("Apellido", max_length=150, blank=True)
    first_name = models.CharField("Nombre", max_length=150, blank=True)
    dni = models.CharField("DNI", max_length=20, unique=True, blank=True, null=True)
    birth_date = models.DateField("Fecha de nacimiento", blank=True, null=True)
    age_reported = models.PositiveSmallIntegerField("Edad informada", blank=True, null=True)
    gender = models.CharField("Genero", max_length=40, blank=True)
    ethnicity = models.CharField("Grupo etnico", max_length=120, blank=True)
    smoking_status = models.CharField("Fuma", max_length=80, blank=True)
    patient_group = models.CharField("Grupo paciente", max_length=120, blank=True)
    height_cm = models.PositiveSmallIntegerField("Altura cm", blank=True, null=True)
    weight_kg = models.DecimalField("Peso kg", max_digits=6, decimal_places=2, blank=True, null=True)
    bmi = models.DecimalField("BMI", max_digits=6, decimal_places=2, blank=True, null=True)
    pack_years = models.DecimalField("Paquete anio", max_digits=6, decimal_places=2, blank=True, null=True)
    phone = models.CharField("Telefono", max_length=50, blank=True)
    notes = models.TextField("Observaciones", blank=True)
    deleted_at = models.DateTimeField("Eliminado el", blank=True, null=True, db_index=True)
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="patients_deleted",
    )
    deletion_batch = models.UUIDField("Lote de eliminacion", blank=True, null=True, db_index=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"

    def __str__(self):
        return f"{self.full_name} ({self.dni or 'sin DNI'})"

    def soft_delete(self, *, deleted_by=None, deletion_batch=None):
        if self.deleted_at:
            return False
        now = timezone.now()
        deletion_batch = deletion_batch or uuid.uuid4()
        self.deleted_at = now
        self.deleted_by = deleted_by
        self.deletion_batch = deletion_batch
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_batch", "updated_at"])
        for encounter in Encounter.all_objects.filter(patient=self, deleted_at__isnull=True):
            encounter.soft_delete(deleted_by=deleted_by, deletion_batch=deletion_batch)
        return True

    def restore(self, *, restore_batch=True):
        if not self.deleted_at:
            return False
        deletion_batch = self.deletion_batch
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_batch = None
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_batch", "updated_at"])
        if restore_batch and deletion_batch:
            for encounter in Encounter.all_objects.filter(
                patient=self,
                deleted_at__isnull=False,
                deletion_batch=deletion_batch,
            ):
                encounter.restore()
        return True


class ReferringPhysician(TimeStampedModel):
    full_name = models.CharField("Nombre", max_length=150, unique=True)
    is_default = models.BooleanField("Por defecto", default=False)
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Medico derivante"
        verbose_name_plural = "Medicos derivantes"

    def __str__(self):
        return self.full_name


class Encounter(TimeStampedModel):
    objects = ActiveManager()
    all_objects = models.Manager()

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")
    encounter_date = models.DateField("Fecha de atencion")
    encounter_time = models.TimeField("Hora de atencion", blank=True, null=True)
    study_type = models.CharField(
        "Tipo de estudio",
        max_length=30,
        choices=StudyType.choices,
        default=StudyType.CICLOMETRIA,
    )
    status = models.CharField(
        "Estado",
        max_length=30,
        choices=EncounterStatus.choices,
        default=EncounterStatus.CARGADA,
    )
    coverage_type = models.CharField(
        "Cobertura",
        max_length=20,
        choices=CoverageType.choices,
        default=CoverageType.PARTICULAR,
    )
    coverage_name = models.CharField("Nombre mutual", max_length=120, blank=True)
    affiliate_number = models.CharField("Numero afiliado", max_length=80, blank=True)
    referring_physician = models.ForeignKey(
        ReferringPhysician,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="encounters",
        verbose_name="Medico derivante",
    )
    attended = models.BooleanField("Atendido", default=False)
    attended_at = models.DateTimeField("Atendido el", blank=True, null=True)
    no_show = models.BooleanField("No llego", default=False)
    technician_notes = models.TextField("Notas del espirometrista", blank=True)
    medical_control_today = models.BooleanField("Control medico hoy", default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True, related_name="encounters_created"
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True, related_name="encounters_updated"
    )
    validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True, related_name="encounters_validated"
    )
    validated_at = models.DateTimeField("Validado el", blank=True, null=True)
    deleted_at = models.DateTimeField("Eliminado el", blank=True, null=True, db_index=True)
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="encounters_deleted",
    )
    deletion_batch = models.UUIDField("Lote de eliminacion", blank=True, null=True, db_index=True)

    class Meta:
        ordering = ["-encounter_date", "-encounter_time", "-created_at"]
        verbose_name = "Atencion"
        verbose_name_plural = "Atenciones"
        indexes = [
            models.Index(fields=["encounter_date", "deleted_at"], name="clinic_enc_date_deleted_idx"),
            models.Index(fields=["status", "encounter_date"], name="clinic_enc_status_date_idx"),
            models.Index(fields=["patient", "encounter_date"], name="clinic_enc_patient_date_idx"),
        ]
        permissions = [
            ("manage_agenda", "Puede gestionar la agenda clinica"),
            ("review_medically", "Puede realizar revisiones medicas"),
            ("purge_clinical_data", "Puede eliminar datos clinicos definitivamente"),
            ("view_clinical_statistics", "Puede ver estadisticas clinicas"),
        ]

    def __str__(self):
        return f"{self.patient.full_name} - {self.encounter_date:%d/%m/%Y}"

    def soft_delete(self, *, deleted_by=None, deletion_batch=None):
        if self.deleted_at:
            return False
        now = timezone.now()
        self.deleted_at = now
        self.deleted_by = deleted_by
        self.deletion_batch = deletion_batch or uuid.uuid4()
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_batch", "updated_at"])
        return True

    def restore(self):
        if not self.deleted_at:
            return False
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_batch = None
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_batch", "updated_at"])
        return True


class VitalSigns(TimeStampedModel):
    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="vital_signs")
    so2_rest = models.PositiveSmallIntegerField("SO2 en reposo", blank=True, null=True)
    fc_rest = models.PositiveSmallIntegerField("FC en reposo", blank=True, null=True)
    ta_rest = models.CharField("TA en reposo", max_length=30, blank=True)
    so2_post = models.PositiveSmallIntegerField("SO2 post prueba", blank=True, null=True)
    fc_post = models.PositiveSmallIntegerField("FC post prueba", blank=True, null=True)

    class Meta:
        verbose_name = "Signos vitales"
        verbose_name_plural = "Signos vitales"

    def __str__(self):
        return f"Signos de {self.encounter}"


class WalkTest(TimeStampedModel):
    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="walk_test")
    distance_meters = models.PositiveSmallIntegerField(
        "Distancia",
        choices=((100, "100"), (200, "200")),
        default=200,
    )
    completed = models.BooleanField("Prueba concluida", default=True)
    stopped = models.BooleanField("Se detuvo", default=False)
    symptoms = models.BooleanField("Presento sintomas", default=False)
    borg_final = models.PositiveSmallIntegerField("Borg final", default=1)
    minute_readings = models.JSONField("Mediciones reales por minuto", blank=True, default=list)

    class Meta:
        verbose_name = "Prueba de caminata"
        verbose_name_plural = "Pruebas de caminata"

    def __str__(self):
        return f"Caminata de {self.encounter}"


class SpirometryResult(TimeStampedModel):
    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="spirometry_result")
    respiratory_pattern = models.CharField(
        "Patron respiratorio",
        max_length=20,
        choices=RespiratoryPattern.choices,
        blank=True,
    )
    obstruction_grade = models.CharField(
        "Grado de obstruccion",
        max_length=30,
        choices=SeverityGrade.choices,
        blank=True,
    )
    restriction_grade = models.CharField(
        "Grado de restriccion",
        max_length=30,
        choices=SeverityGrade.choices,
        blank=True,
    )
    bronchodilator_positive = models.BooleanField("Broncodilatador positivo", default=False)
    suggested_bronchodilator_positive = models.BooleanField(
        "Broncodilatador positivo sugerido",
        blank=True,
        null=True,
    )
    suggested_bronchodilator_reason = models.TextField("Motivo de sugerencia broncodilatadora", blank=True)
    physician_comment = models.TextField("Comentario medico", blank=True)
    measured_values = models.JSONField("Valores extraidos", blank=True, default=dict)
    suggested_code = models.CharField("Codigo sugerido", max_length=24, blank=True)
    suggested_probability = models.PositiveSmallIntegerField("Probabilidad sugerida", blank=True, null=True)
    suggested_summary = models.TextField("Resumen sugerido", blank=True)
    extracted_source = models.CharField("Fuente de extraccion", max_length=40, blank=True)

    class Meta:
        verbose_name = "Resultado espirometrico"
        verbose_name_plural = "Resultados espirometricos"

    def __str__(self):
        return f"Resultado de {self.encounter}"


def safe_attachment_filename(filename):
    raw_name = str(filename or "").strip().replace("\\", "/").split("/")[-1]
    if "." in raw_name:
        stem, extension = raw_name.rsplit(".", 1)
        extension = "." + re.sub(r"[^A-Za-z0-9]", "", extension.lower())
    else:
        stem, extension = raw_name, ""
    ascii_stem = (
        unicodedata.normalize("NFKD", stem or "archivo")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem).strip("._-")
    if not safe_stem:
        safe_stem = "archivo"
    return f"{safe_stem[:90]}{extension or ''}"


def attachment_upload_to(instance, filename):
    encounter_id = instance.encounter_id or "sin-atencion"
    return f"encounters/{encounter_id}/{safe_attachment_filename(filename)}"


class Attachment(TimeStampedModel):
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="attachments")
    file_kind = models.CharField("Tipo de archivo", max_length=30, choices=AttachmentKind.choices)
    original_name = models.CharField("Nombre original", max_length=255)
    file = models.FileField("Archivo", upload_to=attachment_upload_to)
    mime_type = models.CharField("Mime type", max_length=120, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    analysis_status = models.CharField(
        "Estado de lectura",
        max_length=20,
        choices=AttachmentAnalysisStatus.choices,
        blank=True,
        default="",
    )
    analysis_error = models.CharField("Detalle de lectura", max_length=280, blank=True)
    analysis_attempted_at = models.DateTimeField("Ultimo intento de lectura", blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Adjunto"
        verbose_name_plural = "Adjuntos"

    def __str__(self):
        return self.original_name


class GeneratedReport(TimeStampedModel):
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="generated_reports")
    report_type = models.CharField("Tipo de informe", max_length=30, choices=ReportType.choices)
    attachment = models.ForeignKey(
        Attachment, on_delete=models.SET_NULL, blank=True, null=True, related_name="reports"
    )
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    generator_version = models.CharField("Version del generador", max_length=50, blank=True)
    source_snapshot = models.JSONField("Datos fuente", blank=True, default=dict)
    content_sha256 = models.CharField("SHA-256", max_length=64, blank=True, db_index=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="superseded_by",
        verbose_name="Reemplaza a",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Informe generado"
        verbose_name_plural = "Informes generados"

    def __str__(self):
        return f"{self.report_type} - {self.encounter}"


class EncounterEvent(TimeStampedModel):
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="events")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="encounter_events")
    event_type = models.CharField("Tipo", max_length=20, choices=EncounterEventType.choices)
    title = models.CharField("Titulo", max_length=160)
    details = models.TextField("Detalle", blank=True)
    metadata = models.JSONField("Metadata", blank=True, default=dict)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Evento de atencion"
        verbose_name_plural = "Eventos de atencion"

    def __str__(self):
        return f"{self.patient.full_name} - {self.title}"
