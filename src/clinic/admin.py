from django.contrib import admin

from .models import (
    Attachment,
    Encounter,
    EncounterEvent,
    GeneratedReport,
    Patient,
    ReferringPhysician,
    SpirometryResult,
    VitalSigns,
    WalkTest,
)


class VitalSignsInline(admin.StackedInline):
    model = VitalSigns
    extra = 0


class WalkTestInline(admin.StackedInline):
    model = WalkTest
    extra = 0


class SpirometryResultInline(admin.StackedInline):
    model = SpirometryResult
    extra = 0


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


class EncounterEventInline(admin.TabularInline):
    model = EncounterEvent
    extra = 0
    readonly_fields = ("event_type", "title", "details", "actor", "created_at")


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "dni", "patient_code", "gender", "age_reported", "created_at")
    search_fields = ("full_name", "dni", "patient_code", "last_name", "first_name")


@admin.register(ReferringPhysician)
class ReferringPhysicianAdmin(admin.ModelAdmin):
    list_display = ("full_name", "is_default", "active")
    list_filter = ("is_default", "active")
    search_fields = ("full_name",)


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ("patient", "encounter_date", "study_type", "status", "coverage_type")
    list_filter = ("study_type", "status", "coverage_type")
    search_fields = ("patient__full_name", "patient__dni", "coverage_name")
    autocomplete_fields = ("patient", "referring_physician", "created_by", "updated_by", "validated_by")
    inlines = (VitalSignsInline, WalkTestInline, SpirometryResultInline, AttachmentInline, EncounterEventInline)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "encounter", "file_kind", "uploaded_by", "created_at")
    list_filter = ("file_kind",)
    search_fields = ("original_name", "encounter__patient__full_name", "encounter__patient__dni")


@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ("report_type", "encounter", "generated_by", "created_at")
    list_filter = ("report_type",)


@admin.register(EncounterEvent)
class EncounterEventAdmin(admin.ModelAdmin):
    list_display = ("patient", "encounter", "event_type", "title", "actor", "created_at")
    list_filter = ("event_type",)
    search_fields = ("patient__full_name", "patient__dni", "title", "details")
