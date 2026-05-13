import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_alter_exercise_id_alter_musclegroup_id'),
    ]

    operations = [
        # 1. Создаём through-таблицу
        migrations.CreateModel(
            name='ExerciseMuscleGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_primary', models.BooleanField(default=True)),
                ('exercise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='muscle_group_links', to='catalog.exercise')),
                ('muscle_group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exercise_links', to='catalog.musclegroup')),
            ],
            options={
                'unique_together': {('exercise', 'muscle_group')},
            },
        ),

        # 2. Переносим существующие M2M-связи в новую таблицу (is_primary=True),
        #    затем удаляем старую авто-созданную таблицу.
        migrations.RunSQL(
            sql="""
                INSERT OR IGNORE INTO catalog_exercisemusclegroup
                    (exercise_id, muscle_group_id, is_primary)
                SELECT exercise_id, musclegroup_id, 1
                FROM catalog_exercise_muscle_groups;

                DROP TABLE IF EXISTS catalog_exercise_muscle_groups;
            """,
            reverse_sql="""
                CREATE TABLE IF NOT EXISTS catalog_exercise_muscle_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exercise_id INTEGER NOT NULL REFERENCES catalog_exercise(id),
                    musclegroup_id INTEGER NOT NULL REFERENCES catalog_musclegroup(id)
                );
                INSERT OR IGNORE INTO catalog_exercise_muscle_groups
                    (exercise_id, musclegroup_id)
                SELECT exercise_id, muscle_group_id
                FROM catalog_exercisemusclegroup;
            """,
        ),

        # 3. Обновляем состояние модели в Django без касания БД
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='exercise',
                    name='muscle_groups',
                    field=models.ManyToManyField(through='catalog.ExerciseMuscleGroup', to='catalog.musclegroup'),
                ),
            ],
            database_operations=[],
        ),
    ]
