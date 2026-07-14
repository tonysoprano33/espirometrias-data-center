from pathlib import Path
import re
import zipfile

from django import forms
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .models import (
    Attachment,
    AttachmentKind,
    CoverageType,
    Encounter,
    Patient,
    ReferringPhysician,
    StudyType,
    SpirometryResult,
    VitalSigns,
    WalkTest,
)


MAX_CLINICAL_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_CLINICAL_IMAGE_PIXELS = 40_000_000


def validate_clinical_upload(uploaded, *, allow_documents=False):
    if not uploaded:
        return uploaded
    if uploaded.size > MAX_CLINICAL_UPLOAD_BYTES:
        raise forms.ValidationError("El archivo supera el limite de 15 MB.")

    extension = Path(str(uploaded.name or "")).suffix.lower()
    uploaded.seek(0)
    header = uploaded.read(16)
    uploaded.seek(0)
    try:
        if extension == ".pdf":
            if not header.startswith(b"%PDF-"):
                raise forms.ValidationError("El archivo no es un PDF valido.")
        elif extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            try:
                image = Image.open(uploaded)
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_CLINICAL_IMAGE_PIXELS:
                    raise forms.ValidationError("La imagen tiene dimensiones demasiado grandes.")
                image.verify()
            except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
                raise forms.ValidationError("La imagen esta danada o no es valida.") from error
        elif allow_documents and extension in {".docx", ".odt"}:
            try:
                with zipfile.ZipFile(uploaded) as archive:
                    names = set(archive.namelist())
                    if extension == ".docx" and (
                        "[Content_Types].xml" not in names
                        or not any(name.startswith("word/") for name in names)
                    ):
                        raise forms.ValidationError("El archivo no es un documento DOCX valido.")
                    if extension == ".odt" and "mimetype" not in names:
                        raise forms.ValidationError("El archivo no es un documento ODT valido.")
            except (zipfile.BadZipFile, OSError) as error:
                raise forms.ValidationError("El documento esta danado o no es valido.") from error
        elif allow_documents and extension == ".doc":
            if not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
                raise forms.ValidationError("El archivo no es un documento DOC valido.")
        else:
            raise forms.ValidationError("Tipo de archivo no permitido.")
    finally:
        uploaded.seek(0)
    return uploaded


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class TimeInput(forms.TimeInput):
    input_type = "time"


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["full_name", "dni", "phone", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_full_name(self):
        return " ".join((self.cleaned_data.get("full_name") or "").split()).upper()

    def clean_dni(self):
        digits = re.sub(r"\D", "", self.cleaned_data.get("dni") or "")
        return digits or None


class ReferringPhysicianForm(forms.ModelForm):
    class Meta:
        model = ReferringPhysician
        fields = ["full_name", "is_default", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].widget.attrs.update(
            {
                "placeholder": "Ej: Dra. Maria Perez",
                "autocomplete": "off",
            }
        )


OBSTRUCTION_CODE_TO_GRADE = {
    "OL": "Leve",
    "OM": "Moderada",
    "OMS": "Moderadamente severa",
    "OS": "Severa",
}

RESTRICTION_CODE_TO_GRADE = {
    "RL": "Leve",
    "RM": "Moderada",
    "RMS": "Moderadamente severa",
    "RS": "Severa",
}

GRADE_TO_OBSTRUCTION_CODE = {value: key for key, value in OBSTRUCTION_CODE_TO_GRADE.items()}
GRADE_TO_RESTRICTION_CODE = {value: key for key, value in RESTRICTION_CODE_TO_GRADE.items()}

LEGACY_RESULT_CODE_MAP = {
    "NORMAL": "N",
    "N": "N",
    "OBSTRUCCIONLEVE": "OL",
    "OBSTRUCCIONMODERADA": "OM",
    "OBSTRUCCIONMODERADAMENTESEVERA": "OMS",
    "OBSTRUCCIONSEVERA": "OS",
    "RESTRICCIONLEVE": "RL",
    "RESTRICCIONMODERADA": "RM",
    "RESTRICCIONMODERADAMENTESEVERA": "RMS",
    "RESTRICCIONSEVERA": "RS",
    "MIXTO": "MIXTO",
    "OBSTRUCCION_LEVE": "OL",
    "OBSTRUCCION_MODERADA": "OM",
    "OBSTRUCCION_MODERADAMENTE_SEVERA": "OMS",
    "OBSTRUCCION_SEVERA": "OS",
    "RESTRICCION_LEVE": "RL",
    "RESTRICCION_MODERADA": "RM",
    "RESTRICCION_MODERADAMENTE_SEVERA": "RMS",
    "RESTRICCION_SEVERA": "RS",
}

RESULT_CODE_SUGGESTIONS = [
    ("N", "N - Normal"),
    ("OL", "OL - Obstruccion leve"),
    ("OM", "OM - Obstruccion moderada"),
    ("OMS", "OMS - Obstruccion moderadamente severa"),
    ("OS", "OS - Obstruccion severa"),
    ("RL", "RL - Restriccion leve"),
    ("RM", "RM - Restriccion moderada"),
    ("RMS", "RMS - Restriccion moderadamente severa"),
    ("RS", "RS - Restriccion severa"),
    ("RLOL", "RLOL - Mixto (restriccion leve + obstruccion leve)"),
    ("RLOM", "RLOM - Mixto (restriccion leve + obstruccion moderada)"),
    ("RLOMS", "RLOMS - Mixto (restriccion leve + obstruccion moderadamente severa)"),
    ("RLOS", "RLOS - Mixto (restriccion leve + obstruccion severa)"),
    ("RMOL", "RMOL - Mixto (restriccion moderada + obstruccion leve)"),
    ("RMOM", "RMOM - Mixto (restriccion moderada + obstruccion moderada)"),
    ("RMOMS", "RMOMS - Mixto (restriccion moderada + obstruccion moderadamente severa)"),
    ("RMOS", "RMOS - Mixto (restriccion moderada + obstruccion severa)"),
    ("RMSOL", "RMSOL - Mixto (restriccion moderadamente severa + obstruccion leve)"),
    ("RMSOM", "RMSOM - Mixto (restriccion moderadamente severa + obstruccion moderada)"),
    ("RMSOMS", "RMSOMS - Mixto (restriccion moderadamente severa + obstruccion moderadamente severa)"),
    ("RMSOS", "RMSOS - Mixto (restriccion moderadamente severa + obstruccion severa)"),
    ("RSOL", "RSOL - Mixto (restriccion severa + obstruccion leve)"),
    ("RSOM", "RSOM - Mixto (restriccion severa + obstruccion moderada)"),
    ("RSOMS", "RSOMS - Mixto (restriccion severa + obstruccion moderadamente severa)"),
    ("RSOS", "RSOS - Mixto (restriccion severa + obstruccion severa)"),
]

RESULT_CODE_LABELS = {code: label for code, label in RESULT_CODE_SUGGESTIONS}


def normalize_result_code(raw_value: str) -> str:
    text = str(raw_value or "").strip().upper()
    if not text:
        return ""
    compact = (
        text.replace(" ", "")
        .replace("-", "")
        .replace("/", "")
        .replace(".", "")
    )
    return LEGACY_RESULT_CODE_MAP.get(compact, compact)


def parse_result_code(raw_value: str):
    code = normalize_result_code(raw_value)
    if not code:
        return {
            "canonical_code": "",
            "pattern": "",
            "obstruction_grade": "",
            "restriction_grade": "",
        }

    if code == "N":
        return {
            "canonical_code": "N",
            "pattern": "Normal",
            "obstruction_grade": "",
            "restriction_grade": "",
        }

    if code in OBSTRUCTION_CODE_TO_GRADE:
        return {
            "canonical_code": code,
            "pattern": "Obstructivo",
            "obstruction_grade": OBSTRUCTION_CODE_TO_GRADE[code],
            "restriction_grade": "",
        }

    if code in RESTRICTION_CODE_TO_GRADE:
        return {
            "canonical_code": code,
            "pattern": "Restrictivo",
            "obstruction_grade": "",
            "restriction_grade": RESTRICTION_CODE_TO_GRADE[code],
        }

    for restriction_code in ["RMS", "RS", "RM", "RL"]:
        for obstruction_code in ["OMS", "OS", "OM", "OL"]:
            if code in [restriction_code + obstruction_code, obstruction_code + restriction_code]:
                return {
                    "canonical_code": restriction_code + obstruction_code,
                    "pattern": "Mixto",
                    "obstruction_grade": OBSTRUCTION_CODE_TO_GRADE[obstruction_code],
                    "restriction_grade": RESTRICTION_CODE_TO_GRADE[restriction_code],
                }

    if code == "MIXTO":
        return {
            "canonical_code": "MIXTO",
            "pattern": "Mixto",
            "obstruction_grade": "",
            "restriction_grade": "",
        }

    return None


def get_result_label_for_code(raw_value: str) -> str:
    code = normalize_result_code(raw_value)
    if not code:
        return "-"
    return code


class QuickEncounterForm(forms.Form):
    patient_name = forms.CharField(label="Nombre", max_length=150)
    patient_dni = forms.CharField(label="DNI (opcional)", max_length=20, required=False)
    encounter_time = forms.TimeField(label="Hora", widget=TimeInput(), required=False)
    study_type = forms.ChoiceField(label="Tipo de estudio", choices=StudyType.choices, initial=StudyType.CICLOMETRIA)
    coverage_type = forms.ChoiceField(label="Cobertura", choices=CoverageType.choices, initial=CoverageType.PARTICULAR)
    referring_physician = forms.CharField(label="Dr. deriva", required=False, max_length=150)
    so2_rest = forms.IntegerField(label="SO2 en reposo", required=False, min_value=0, max_value=100)
    fc_rest = forms.IntegerField(label="FC en reposo", required=False, min_value=0, max_value=300)
    so2_post = forms.IntegerField(label="SO2 despues de caminata", required=False, min_value=0, max_value=100)
    fc_post = forms.IntegerField(label="FC despues de caminata", required=False, min_value=0, max_value=300)
    distance_meters = forms.ChoiceField(label="Distancia caminata", choices=((100, "100"), (200, "200")), initial=200)
    completed = forms.BooleanField(label="Completada con exito", required=False, initial=True)
    stopped = forms.BooleanField(label="Se detuvo durante la marcha", required=False, initial=False)
    symptoms = forms.BooleanField(label="Presento sintomas al final", required=False, initial=False)
    borg_final = forms.ChoiceField(label="Borg final", choices=[(value, str(value)) for value in range(0, 11)], initial=1)
    respiratory_result = forms.CharField(label="Resultado", required=False, max_length=24)
    bronchodilator_positive = forms.BooleanField(label="Broncodilatador positivo", required=False, initial=False)
    attended = forms.BooleanField(label="Atendido", required=False, initial=False)
    no_show = forms.BooleanField(label="No llego", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        physician_queryset = ReferringPhysician.objects.filter(active=True).order_by("full_name")
        default_physician = physician_queryset.filter(is_default=True).first() or physician_queryset.first()
        if default_physician and not self.initial.get("referring_physician"):
            self.initial["referring_physician"] = default_physician.full_name
        self.fields["patient_name"].widget.attrs.update({"autocomplete": "off", "data-nav": "1"})
        self.fields["patient_dni"].widget.attrs.update({"autocomplete": "off", "data-nav": "2"})
        self.fields["encounter_time"].widget.attrs.update({"step": "60", "data-nav": "3"})
        self.fields["study_type"].widget.attrs.update({"data-nav": "4"})
        self.fields["coverage_type"].widget.attrs.update({"data-nav": "5"})
        self.fields["referring_physician"].widget.attrs.update({"data-nav": "6", "autocomplete": "off"})
        self.fields["so2_rest"].widget.attrs.update({"data-nav": "7", "max": "100", "inputmode": "numeric", "data-autoadvance-length": "3"})
        self.fields["fc_rest"].widget.attrs.update({"data-nav": "8", "max": "300", "inputmode": "numeric", "data-autoadvance-length": "3"})
        self.fields["so2_post"].widget.attrs.update({"data-nav": "9", "max": "100", "inputmode": "numeric", "data-autoadvance-length": "3"})
        self.fields["fc_post"].widget.attrs.update({"data-nav": "10", "max": "300", "inputmode": "numeric", "data-autoadvance-length": "3"})
        self.fields["distance_meters"].widget.attrs.update({"data-nav": "11"})
        self.fields["completed"].widget.attrs.update({"data-nav": "12"})
        self.fields["stopped"].widget.attrs.update({"data-nav": "13"})
        self.fields["symptoms"].widget.attrs.update({"data-nav": "14"})
        self.fields["borg_final"].widget.attrs.update({"data-nav": "15"})
        self.fields["respiratory_result"].widget.attrs.update(
            {
                "data-nav": "16",
                "list": "result-code-options",
                "placeholder": "N, OL, RL, RLOMS...",
                "autocomplete": "off",
                "data-result-code": "1",
            }
        )
        self.fields["bronchodilator_positive"].widget.attrs.update({"data-nav": "17"})
        self.fields["attended"].widget.attrs.update({"data-nav": "18"})
        self.fields["no_show"].widget.attrs.update({"data-nav": "19"})

    def clean_respiratory_result(self):
        value = self.cleaned_data.get("respiratory_result", "")
        parsed = parse_result_code(value)
        if parsed is None:
            raise forms.ValidationError(
                "Usa codigos como N, OL, OM, OMS, OS, RL, RM, RMS, RS o mixtos tipo RLOMS."
            )
        return parsed["canonical_code"]

    def clean_patient_dni(self):
        return re.sub(r"\D", "", self.cleaned_data.get("patient_dni") or "")

    def clean(self):
        cleaned_data = super().clean()
        attended = bool(cleaned_data.get("attended"))
        no_show = bool(cleaned_data.get("no_show"))
        if attended and no_show:
            cleaned_data["no_show"] = False
        return cleaned_data


class DoctorReviewForm(forms.Form):
    pdf_file = forms.FileField(
        label="Resultado original (PDF o foto)",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".pdf,.png,.jpg,.jpeg,.webp,image/*,application/pdf",
                "capture": "environment",
            }
        ),
    )
    respiratory_result = forms.CharField(label="Resultado", required=False, max_length=24)
    bronchodilator_positive = forms.BooleanField(label="Broncodilatador positivo", required=False, initial=False)
    analysis_payload_json = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["respiratory_result"].widget.attrs.update(
            {
                "list": "result-code-options",
                "placeholder": "N, OL, RL, RLOMS...",
                "autocomplete": "off",
                "data-result-code": "1",
            }
        )

    def clean_respiratory_result(self):
        value = self.cleaned_data.get("respiratory_result", "")
        parsed = parse_result_code(value)
        if parsed is None:
            raise forms.ValidationError(
                "Usa codigos como N, OL, OM, OMS, OS, RL, RM, RMS, RS o mixtos tipo RLOMS."
            )
        return parsed["canonical_code"]

    def clean_pdf_file(self):
        uploaded = self.cleaned_data.get("pdf_file")
        if not uploaded:
            return uploaded

        file_name = str(getattr(uploaded, "name", "") or "").lower()
        allowed_image_exts = (".png", ".jpg", ".jpeg", ".webp")
        is_pdf = file_name.endswith(".pdf")
        is_image = file_name.endswith(allowed_image_exts)
        if not (is_pdf or is_image):
            raise forms.ValidationError("Subi un PDF o una imagen JPG, PNG o WEBP.")
        return validate_clinical_upload(uploaded)


class PatientDocumentUploadForm(forms.Form):
    encounter = forms.ModelChoiceField(label="Atencion", queryset=Encounter.objects.none())
    file_kind = forms.ChoiceField(
        label="Tipo de archivo",
        choices=(
            (AttachmentKind.PDF_RESULTADO, "PDF resultado"),
            (AttachmentKind.FOTO_RESULTADO, "Foto resultado"),
            (AttachmentKind.INFORME_DOCX, "Word / DOCX"),
            (AttachmentKind.OTRO, "Otro"),
        ),
    )
    file = forms.FileField(label="Archivo")

    def __init__(self, *args, patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Encounter.objects.none()
        if patient is not None:
            queryset = patient.encounters.order_by("-encounter_date", "-encounter_time", "-created_at")
        self.fields["encounter"].queryset = queryset
        self.fields["file"].widget.attrs.update({"accept": ".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx,image/*,application/pdf,.odt"})

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded

        file_name = str(getattr(uploaded, "name", "") or "").lower()
        allowed_exts = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".odt")
        if not file_name.endswith(allowed_exts):
            raise forms.ValidationError("Subi un PDF, imagen o documento Word.")
        return validate_clinical_upload(uploaded, allow_documents=True)


class DrappImportForm(forms.Form):
    raw_text = forms.CharField(
        label="Texto del mail o tabla de Drapp",
        widget=forms.Textarea(attrs={"rows": 8}),
        required=False,
    )
    ocr_lines_json = forms.CharField(widget=forms.HiddenInput(), required=False)
    screenshot = forms.FileField(label="Captura de Drapp", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screenshot"].widget.attrs.update({"accept": ".png,.jpg,.jpeg,.webp,.bmp"})

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("raw_text") and not cleaned_data.get("ocr_lines_json") and not cleaned_data.get("screenshot"):
            raise forms.ValidationError("Pega texto de Drapp o subi una captura para importar.")
        return cleaned_data

    def clean_screenshot(self):
        uploaded = self.cleaned_data.get("screenshot")
        if not uploaded:
            return uploaded
        return validate_clinical_upload(uploaded)


class VitalSignsForm(forms.ModelForm):
    class Meta:
        model = VitalSigns
        fields = ["so2_rest", "fc_rest", "ta_rest", "so2_post", "fc_post"]


class WalkTestForm(forms.ModelForm):
    class Meta:
        model = WalkTest
        fields = ["distance_meters", "completed", "stopped", "symptoms", "borg_final"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["distance_meters"].initial = 200
        self.fields["completed"].initial = True
        self.fields["borg_final"].initial = 1
        self.fields["borg_final"].widget = forms.Select(choices=[(value, str(value)) for value in range(0, 11)])


class SpirometryResultForm(forms.ModelForm):
    class Meta:
        model = SpirometryResult
        fields = [
            "respiratory_pattern",
            "obstruction_grade",
            "restriction_grade",
            "bronchodilator_positive",
            "physician_comment",
        ]
        widgets = {
            "physician_comment": forms.Textarea(attrs={"rows": 3}),
        }


class PdfAttachmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = False

    class Meta:
        model = Attachment
        fields = ["file"]

    def save(self, commit=True, encounter=None, uploaded_by=None):
        instance = super().save(commit=False)
        instance.file_kind = AttachmentKind.PDF_RESULTADO
        instance.original_name = instance.file.name
        instance.mime_type = getattr(instance.file, "content_type", "") or "application/pdf"
        instance.encounter = encounter
        instance.uploaded_by = uploaded_by
        if commit:
            instance.save()
        return instance
