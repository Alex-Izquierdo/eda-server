# Generated by Django 3.2.18 on 2023-04-26 15:47

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_alter_activationinstance_activation"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rulebook",
            name="path",
        ),
    ]
