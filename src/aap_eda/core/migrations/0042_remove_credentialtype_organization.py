# Generated by Django 4.2.7 on 2024-07-30 16:40

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_alter_credentialtype_options_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="credentialtype",
            name="organization",
        ),
    ]
