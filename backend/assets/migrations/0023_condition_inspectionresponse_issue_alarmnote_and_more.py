import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0022_alarm_workorderchecklistresponse_personnel_stations_and_more'),
    ]

    operations = [
        # Condition
        migrations.CreateModel(
            name='Condition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('asset_category', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='conditions',
                    to='assets.assetcategory',
                )),
            ],
            options={'ordering': ['name']},
        ),

        # InspectionResponse
        migrations.CreateModel(
            name='InspectionResponse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('issues_found', models.BooleanField(blank=True, null=True)),
                ('comments', models.TextField(blank=True)),
                ('done', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('asset', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='inspection_responses',
                    to='assets.asset',
                )),
                ('conditions', models.ManyToManyField(
                    blank=True,
                    related_name='inspection_responses',
                    to='assets.condition',
                )),
                ('work_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inspection_responses',
                    to='assets.workorder',
                )),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='inspectionresponse',
            unique_together={('work_order', 'asset')},
        ),

        # Issue
        migrations.CreateModel(
            name='Issue',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('description', models.TextField()),
                ('severity', models.CharField(
                    choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')],
                    max_length=10,
                )),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('inspection_response', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='issues',
                    to='assets.inspectionresponse',
                )),
                ('promoted_work_order', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='source_issues',
                    to='assets.workorder',
                )),
            ],
        ),

        # AlarmNote
        migrations.CreateModel(
            name='AlarmNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('alarm', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notes',
                    to='assets.alarm',
                )),
            ],
            options={'ordering': ['created']},
        ),

        # WorkOrder new fields
        migrations.AddField(
            model_name='workorder',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workorder',
            name='ended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workorder',
            name='submitted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='workorder',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workorder',
            name='geofence_verified',
            field=models.BooleanField(default=False),
        ),

        # WorkOrderChecklistResponse — swap work_order FK for inspection_response FK
        migrations.AlterUniqueTogether(
            name='workorderchecklistresponse',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='workorderchecklistresponse',
            name='work_order',
        ),
        migrations.AddField(
            model_name='workorderchecklistresponse',
            name='inspection_response',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='checklist_responses',
                to='assets.inspectionresponse',
                default=None,
            ),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='workorderchecklistresponse',
            unique_together={('inspection_response', 'question')},
        ),
    ]
