# Generated by Django 4.2.7 on 2024-01-10 17:02

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_auto_20240103_0502"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="activation",
            name="is_valid",
        ),
        migrations.RemoveField(
            model_name="activation",
            name="status",
        ),
        migrations.RemoveField(
            model_name="activation",
            name="status_message",
        ),
        migrations.RemoveField(
            model_name="activation",
            name="status_updated_at",
        ),
        migrations.RemoveField(
            model_name="source",
            name="listener_activation",
        ),
        migrations.AddField(
            model_name="activationinstance",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="source_processes",
                to="core.source",
            ),
        ),
        migrations.AddField(
            model_name="activationinstance",
            name="status_updated_at",
            field=models.DateTimeField(null=True),
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
            name="extra_var",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="core.extravar",
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="failure_count",
            field=models.IntegerField(default=0),
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
            name="rulebook",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="core.rulebook",
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="rulebook_name",
            field=models.TextField(
                default="", help_text="Name of the referenced rulebook"
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="rulebook_rulesets",
            field=models.TextField(
                default="", help_text="Content of the last referenced rulebook"
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="ruleset_stats",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="activationinstance",
            name="activation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="activation_processes",
                to="core.activation",
            ),
        ),
    ]
