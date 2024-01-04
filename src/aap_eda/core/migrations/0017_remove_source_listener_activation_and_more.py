# Generated by Django 4.2.7 on 2024-01-04 20:03

import django.db.models.deletion
from django.db import migrations, models

import aap_eda.core.enums


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_auto_20240103_0502"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="source",
            name="listener_activation",
        ),
        migrations.AddField(
            model_name="source",
            name="current_job_id",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="source",
            name="description",
            field=models.TextField(default=""),
        ),
        migrations.AddField(
            model_name="source",
            name="failure_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="source",
            name="is_valid",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="source",
            name="latest_instance",
            field=models.OneToOneField(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="core.activationinstance",
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="restart_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="source",
            name="status",
            field=models.TextField(
                choices=[
                    ("starting", "starting"),
                    ("running", "running"),
                    ("pending", "pending"),
                    ("failed", "failed"),
                    ("stopping", "stopping"),
                    ("stopped", "stopped"),
                    ("deleting", "deleting"),
                    ("completed", "completed"),
                    ("unresponsive", "unresponsive"),
                    ("error", "error"),
                ],
                default=aap_eda.core.enums.ActivationStatus["PENDING"],
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="status_message",
            field=models.TextField(default=None, null=True),
        ),
        migrations.AddField(
            model_name="source",
            name="status_updated_at",
            field=models.DateTimeField(null=True),
        ),
    ]
