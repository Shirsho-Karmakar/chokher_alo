from django.db import migrations


def normalize_blank_identifiers(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    User.objects.filter(email="").update(email=None)
    User.objects.filter(phone_number="").update(phone_number=None)


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0002_phoneotpchallenge_phoneotpthrottle",
        ),
    ]

    operations = [
        migrations.RunPython(
            normalize_blank_identifiers,
            migrations.RunPython.noop,
        ),
    ]
