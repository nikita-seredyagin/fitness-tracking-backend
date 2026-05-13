from django.contrib import admin
from .models import (
    SmartProgram, SmartDay, SmartDayExercise, SmartSet,
    SmartSession, SmartProgressionLog,
)


class SmartSetInline(admin.TabularInline):
    model = SmartSet
    extra = 0
    fields = ['order', 'weight', 'reps']
    verbose_name = 'Подход'
    verbose_name_plural = 'Подходы'


class SmartDayExerciseInline(admin.TabularInline):
    model = SmartDayExercise
    extra = 0
    show_change_link = True
    autocomplete_fields = ['exercise']
    verbose_name = 'Упражнение'
    verbose_name_plural = 'Упражнения'


class SmartDayInline(admin.TabularInline):
    model = SmartDay
    extra = 0
    show_change_link = True
    verbose_name = 'День'
    verbose_name_plural = 'Дни'


@admin.register(SmartProgram)
class SmartProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_active', 'created_at', 'days_count', 'sessions_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['created_at']
    inlines = [SmartDayInline]

    @admin.display(description='Дней')
    def days_count(self, obj):
        return obj.days.count()

    @admin.display(description='Тренировок')
    def sessions_count(self, obj):
        return obj.sessions.count()


@admin.register(SmartDay)
class SmartDayAdmin(admin.ModelAdmin):
    list_display = ['name', 'program', 'order', 'exercises_count']
    search_fields = ['name', 'program__name']
    list_filter = ['program']
    inlines = [SmartDayExerciseInline]

    @admin.display(description='Упражнений')
    def exercises_count(self, obj):
        return obj.exercises.count()


@admin.register(SmartDayExercise)
class SmartDayExerciseAdmin(admin.ModelAdmin):
    list_display = ['exercise', 'day', 'order', 'sets_count']
    search_fields = ['exercise__name', 'day__name', 'day__program__name']
    autocomplete_fields = ['exercise']
    inlines = [SmartSetInline]

    @admin.display(description='Подходов')
    def sets_count(self, obj):
        return obj.sets.count()


@admin.register(SmartSession)
class SmartSessionAdmin(admin.ModelAdmin):
    list_display = ['program', 'day', 'week_number', 'session_date', 'created_at']
    list_filter = ['program', 'week_number']
    search_fields = ['program__name', 'day__name']
    readonly_fields = ['created_at']

    @admin.display(description='Дата тренировки')
    def session_date(self, obj):
        return obj.session.date.strftime('%Y-%m-%d')


@admin.register(SmartProgressionLog)
class SmartProgressionLogAdmin(admin.ModelAdmin):
    list_display = [
        'exercise_name', 'program_name', 'reason',
        'old_weight', 'new_weight', 'weight_delta',
        'sets_completed', 'avg_reps', 'created_at',
    ]
    list_filter = ['reason', 'created_at']
    search_fields = ['day_exercise__exercise__name', 'day_exercise__day__program__name']
    readonly_fields = ['created_at']

    @admin.display(description='Упражнение')
    def exercise_name(self, obj):
        return obj.day_exercise.exercise.name

    @admin.display(description='Программа')
    def program_name(self, obj):
        return obj.day_exercise.day.program.name

    @admin.display(description='Δ вес')
    def weight_delta(self, obj):
        delta = obj.new_weight - obj.old_weight
        if delta > 0:
            return f'+{delta}'
        return str(delta)
