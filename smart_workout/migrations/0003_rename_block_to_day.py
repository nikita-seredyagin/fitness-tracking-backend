from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('smart_workout', '0002_alter_smartprogram_user'),
    ]

    operations = [
        migrations.RenameModel('SmartBlock', 'SmartDay'),
        migrations.RenameModel('SmartBlockExercise', 'SmartDayExercise'),
        migrations.RenameField(
            model_name='smartdayexercise',
            old_name='block',
            new_name='day',
        ),
        migrations.RenameField(
            model_name='smartsession',
            old_name='block',
            new_name='day',
        ),
        migrations.RenameField(
            model_name='smartset',
            old_name='block_exercise',
            new_name='day_exercise',
        ),
        migrations.RenameField(
            model_name='smartprogressionlog',
            old_name='block_exercise',
            new_name='day_exercise',
        ),
    ]
