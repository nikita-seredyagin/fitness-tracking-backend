from django.db import models
from django.conf import settings
from catalog.models import Exercise, BaseProgram, BaseNamedOrderedItem, BaseWeightSet


class DefaultProgram(BaseProgram):
    pass


class DefaultProgramDay(BaseNamedOrderedItem):
    program = models.ForeignKey(
        DefaultProgram, on_delete=models.CASCADE, related_name='days'
    )

    def __str__(self):
        return f'{self.program.name} — {self.name}'


class DefaultProgramExercise(models.Model):
    day = models.ForeignKey(
        DefaultProgramDay, on_delete=models.CASCADE, related_name='exercises'
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.exercise.name} в {self.day}'


class DefaultProgramSet(BaseWeightSet):
    program_exercise = models.ForeignKey(
        DefaultProgramExercise, on_delete=models.CASCADE, related_name='default_program_sets'
    )


class TrainingSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return (
            f'Тренировка {self.user.username} '
            f'от {self.date.strftime("%Y-%m-%d")}'
        )


class SessionExercise(models.Model):
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name='session_exercises'
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.exercise.name} в тренировке {self.session.pk}'


class SessionSet(BaseWeightSet):
    session_exercise = models.ForeignKey(
        SessionExercise, on_delete=models.CASCADE, related_name='session_sets'
    )
    is_done = models.BooleanField(default=False)


class DefaultProgramSession(models.Model):
    day = models.ForeignKey(
        DefaultProgramDay, on_delete=models.CASCADE, related_name='sessions'
    )
    session = models.OneToOneField(
        TrainingSession, on_delete=models.CASCADE,
        related_name='default_program_session',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.day} — {self.session.date.strftime("%Y-%m-%d")}'
