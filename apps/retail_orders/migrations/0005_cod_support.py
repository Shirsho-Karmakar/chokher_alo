from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("retail_orders", "0004_retailfulfillmentstatushistory_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="retailcheckoutpolicy",
            name="cod_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="retailorder",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("razorpay", "Online payment"),
                    ("cod", "Cash on delivery"),
                    ("pay_at_store", "Pay at store"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="retailpaymentattempt",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("razorpay", "Online payment"),
                    ("cod", "Cash on delivery"),
                    ("pay_at_store", "Pay at store"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="retailstockreservation",
            name="reason",
            field=models.CharField(
                choices=[
                    ("online_payment", "Online payment attempt"),
                    ("pay_at_store", "Pay-at-store order"),
                    ("cod", "Cash-on-delivery order"),
                    ("manual", "Manual reservation"),
                ],
                max_length=20,
            ),
        ),
    ]
