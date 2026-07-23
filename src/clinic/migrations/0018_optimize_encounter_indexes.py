# Generated to keep agenda, statistics, and patient-history queries responsive.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinic", "0017_attachment_analysis_status"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="encounter",
            index=models.Index(fields=["encounter_date", "deleted_at"], name="clinic_enc_date_deleted_idx"),
        ),
        migrations.AddIndex(
            model_name="encounter",
            index=models.Index(fields=["status", "encounter_date"], name="clinic_enc_status_date_idx"),
        ),
        migrations.AddIndex(
            model_name="encounter",
            index=models.Index(fields=["patient", "encounter_date"], name="clinic_enc_patient_date_idx"),
        ),
    ]
