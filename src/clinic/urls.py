from django.urls import path

from . import views


app_name = "clinic"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("modo-trabajo/", views.set_work_mode, name="set_work_mode"),
    path("agenda/estado/", views.dashboard_rows_state, name="dashboard_rows_state"),
    path("api/v1/agenda/hoy/", views.agenda_today_api, name="agenda_today_api"),
    path("api/v1/agenda/hoy/nueva/", views.agenda_quick_add_api, name="agenda_quick_add_api"),
    path("api/v1/agenda/<int:pk>/asistencia/", views.agenda_attendance_api, name="agenda_attendance_api"),
    path("api/v1/agenda/<int:pk>/signos/", views.agenda_vitals_api, name="agenda_vitals_api"),
    path("api/v1/agenda/<int:pk>/campo/", views.agenda_inline_field_api, name="agenda_inline_field_api"),
    path("api/v1/agenda/<int:pk>/control-medico/", views.agenda_medical_control_api, name="agenda_medical_control_api"),
    path("api/v1/calendario/", views.calendar_month_api, name="calendar_month_api"),
    path("api/v1/estadistica/", views.month_statistics_api, name="month_statistics_api"),
    path("api/v1/pacientes/", views.patient_search_api, name="patient_search_api"),
    path("api/v1/revision-medica/", views.doctor_review_queue_api, name="doctor_review_queue_api"),
    path("api/v1/revision-medica/<int:pk>/", views.doctor_review_detail_api, name="doctor_review_detail_api"),
    path("api/v1/revision-medica/<int:pk>/resultado/", views.doctor_review_result_api, name="doctor_review_result_api"),
    path("calendario/", views.calendar_view, name="calendar"),
    path("estadistica/", views.statistics_view, name="statistics"),
    path("pacientes/", views.patient_list, name="patient_list"),
    path("pacientes/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("pacientes/nuevo/", views.patient_create, name="patient_create"),
    path("pacientes/<int:pk>/editar/", views.patient_edit, name="patient_edit"),
    path("pacientes/<int:pk>/eliminar/", views.patient_delete, name="patient_delete"),
    path("papelera/", views.recycle_bin_view, name="recycle_bin"),
    path("atenciones/nueva/", views.encounter_create, name="encounter_create"),
    path("atenciones/<int:pk>/", views.encounter_detail, name="encounter_detail"),
    path("atenciones/<int:pk>/editar/", views.encounter_edit, name="encounter_edit"),
    path("atenciones/<int:pk>/notas-espirometrista/", views.encounter_technician_notes, name="encounter_technician_notes"),
    path("atenciones/<int:pk>/imprimir/", views.encounter_print_view, name="encounter_print"),
    path("atenciones/<int:pk>/generar-informe/", views.encounter_generate_report, name="encounter_generate_report"),
    path("imprimir-dia/", views.daily_print_view, name="daily_print"),
    path("revision-medica/", views.doctor_review_list, name="doctor_review_list"),
    path("revision-medica/<int:pk>/cola/", views.doctor_review_queue_state, name="doctor_review_queue_state"),
    path("revision-medica/<int:pk>/", views.doctor_review_detail, name="doctor_review_detail"),
]
