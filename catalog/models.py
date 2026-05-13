from django.db import models
from django.conf import settings


class BaseProgram(models.Model):
    """
    Общая база для программ тренировок.
    Используется в: DefaultProgram (diary), SmartProgram (smart_workout).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class BaseNamedOrderedItem(models.Model):
    """
    Именованный элемент с порядковым номером.
    Используется в: DefaultProgramDay (diary), SmartDay (smart_workout).
    """
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ['order']

    def __str__(self):
        return self.name


class BaseWeightSet(models.Model):
    """
    Подход с весом и повторениями.
    Используется в: SessionSet, DefaultProgramSet (diary), SmartSet (smart_workout).
    """
    weight = models.DecimalField(max_digits=5, decimal_places=1)
    reps = models.PositiveIntegerField()

    class Meta:
        abstract = True

    def __str__(self):
        return f'{self.weight} кг × {self.reps} повт.'


class MuscleGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class ExerciseMuscleGroup(models.Model):
    exercise = models.ForeignKey(
        'Exercise', on_delete=models.CASCADE, related_name='muscle_group_links'
    )
    muscle_group = models.ForeignKey(
        MuscleGroup, on_delete=models.CASCADE, related_name='exercise_links'
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        unique_together = ('exercise', 'muscle_group')

    def __str__(self):
        role = 'primary' if self.is_primary else 'assistant'
        return f'{self.exercise} — {self.muscle_group} ({role})'


class Exercise(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    muscle_groups = models.ManyToManyField(
        MuscleGroup, through='ExerciseMuscleGroup'
    )
    image = models.ImageField(upload_to='exercises/', blank=True, null=True)

    def __str__(self):
        return self.name
