import api.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0003_auto_20200317_1719")]

    operations = [
        migrations.AlterField(
            model_name="usersettings",
            name="settings",
            field=models.JSONField(default=api.models.default_user_settings),
        )
    ]
