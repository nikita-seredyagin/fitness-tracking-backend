from django.contrib import admin
from .models import (
    TrainingSession, SessionExercise, SessionSet,
    DefaultProgram, DefaultProgramDay, DefaultProgramExercise,
    DefaultProgramSet, DefaultProgramSession,
)


class SessionSetInline(admin.TabularInline):
    model = SessionSet
    extra = 0
    fields = ['weight', 'reps', 'is_done']
    verbose_name = 'Подход'
    verbose_name_plural = 'Подходы'


class SessionExerciseInline(admin.TabularInline):
    model = SessionExercise
    extra = 0
    show_change_link = True
    fields = ['exercise']
    verbose_name = 'Упражнение'
    verbose_name_plural = 'Упражнения'


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'user', 'date', 'status', 'duration_display', 'exercises_count']
    list_filter = ['is_active', 'date']
    search_fields = ['user__username']
    date_hierarchy = 'date'
    readonly_fields = ['date']
    inlines = [SessionExerciseInline]

    @admin.display(description='Статус', boolean=False)
    def status(self, obj):
        return 'Активна' if obj.is_active else 'Завершена'

    @admin.display(description='Длительность')
    def duration_display(self, obj):
        if obj.duration_seconds is None:
            return '—'
        minutes = obj.duration_seconds // 60
        seconds = obj.duration_seconds % 60
        return f'{minutes}м {seconds}с'

    @admin.display(description='Упражнений')
    def exercises_count(self, obj):
        return obj.session_exercises.count()


@admin.register(SessionExercise)
class SessionExerciseAdmin(admin.ModelAdmin):
    list_display = ['exercise', 'session', 'sets_count', 'done_sets_count']
    search_fields = ['exercise__name', 'session__user__username']
    autocomplete_fields = ['exercise', 'session']
    inlines = [SessionSetInline]

    @admin.display(description='Подходов')
    def sets_count(self, obj):
        return obj.session_sets.count()

    @admin.display(description='Выполнено')
    def done_sets_count(self, obj):
        return obj.session_sets.filter(is_done=True).count()


class DefaultProgramDayInline(admin.TabularInline):
    model = DefaultProgramDay
    extra = 0
    show_change_link = True
    verbose_name = 'День'
    verbose_name_plural = 'Дни'


@admin.register(DefaultProgram)
class DefaultProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at', 'days_count']
    search_fields = ['name', 'user__username']
    list_filter = ['created_at']
    readonly_fields = ['created_at']
    inlines = [DefaultProgramDayInline]

    @admin.display(description='Дней')
    def days_count(self, obj):
        return obj.days.count()


class DefaultProgramExerciseInline(admin.TabularInline):
    model = DefaultProgramExercise
    extra = 0
    autocomplete_fields = ['exercise']
    verbose_name = 'Упражнение'
    verbose_name_plural = 'Упражнения'


@admin.register(DefaultProgramDay)
class DefaultProgramDayAdmin(admin.ModelAdmin):
    list_display = ['name', 'program', 'order', 'exercises_count']
    list_filter = ['program']
    search_fields = ['name', 'program__name']
    inlines = [DefaultProgramExerciseInline]

    @admin.display(description='Упражнений')
    def exercises_count(self, obj):
        return obj.exercises.count()


class DefaultProgramSetInline(admin.TabularInline):
    model = DefaultProgramSet
    extra = 0
    verbose_name = 'Подход'
    verbose_name_plural = 'Подходы'


@admin.register(DefaultProgramExercise)
class DefaultProgramExerciseAdmin(admin.ModelAdmin):
    list_display = ['exercise', 'day', 'order', 'sets_count']
    search_fields = ['exercise__name', 'day__name', 'day__program__name']
    autocomplete_fields = ['exercise']
    inlines = [DefaultProgramSetInline]

    @admin.display(description='Подходов')
    def sets_count(self, obj):
        return obj.default_program_sets.count()


@admin.register(DefaultProgramSession)
class DefaultProgramSessionAdmin(admin.ModelAdmin):
    list_display = ['day', 'session', 'created_at']
    list_filter = ['created_at']
    readonly_fields = ['created_at']
