# Generated by Django 3.2.20 on 2023-10-12 14:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_auto_20230922_1431"),
    ]

    operations = [
        migrations.AddField(
            model_name="activation",
            name="latest_instance",
            field=models.IntegerField(default=None, null=True),
        ),
        migrations.AddField(
            model_name="activationinstance",
            name="log_read_at",
            field=models.DateTimeField(null=True),
        ),
    ]