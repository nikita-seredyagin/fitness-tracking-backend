from django.db import models
from catalog.models import (
    Exercise, BaseProgram, BaseNamedOrderedItem, BaseWeightSet,
)
from diary.models import TrainingSession


class SmartProgram(BaseProgram):
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']


class SmartDay(BaseNamedOrderedItem):
    program = models.ForeignKey(
        SmartProgram,
        on_delete=models.CASCADE,
        related_name='days',
    )

    def __str__(self):
        return f'{self.program.name} — {self.name}'


class SmartDayExercise(models.Model):
    day = models.ForeignKey(
        SmartDay,
        on_delete=models.CASCADE,
        related_name='exercises',
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name='smart_day_exercises',
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = [('day', 'exercise')]

    def __str__(self):
        return self.exercise.name


class SmartSet(BaseWeightSet):
    day_exercise = models.ForeignKey(
        SmartDayExercise,
        on_delete=models.CASCADE,
        related_name='sets',
    )
    reps = models.PositiveIntegerField(default=10)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.day_exercise.exercise.name} — {self.weight} кг'


class SmartSession(models.Model):
    program = models.ForeignKey(
        SmartProgram,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    day = models.ForeignKey(
        SmartDay,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    session = models.OneToOneField(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='smart_session',
    )
    week_number = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f'{self.program.name} / {self.day.name}'
            f' — неделя {self.week_number}'
        )


class SmartProgressionLog(models.Model):
    REASON_CHOICES = [
        ('increase', 'Увеличение'),
        ('maintain', 'Сохранение'),
        ('decrease', 'Снижение'),
        ('deload', 'Разгрузка'),
    ]

    day_exercise = models.ForeignKey(
        SmartDayExercise,
        on_delete=models.CASCADE,
        related_name='progression_logs',
    )
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='smart_progression_logs',
    )
    old_weight = models.DecimalField(max_digits=5, decimal_places=1)
    new_weight = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    sets_completed = models.PositiveIntegerField()
    avg_reps = models.DecimalField(max_digits=4, decimal_places=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f'{self.day_exercise.exercise.name}: '
            f'{self.old_weight}→{self.new_weight} кг ({self.reason})'
        )
