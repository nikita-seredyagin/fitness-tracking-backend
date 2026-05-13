from django.contrib import admin
from django.utils.html import format_html
from .models import MuscleGroup, Exercise, ExerciseMuscleGroup


class ExerciseMuscleGroupInline(admin.TabularInline):
    model = ExerciseMuscleGroup
    extra = 1
    autocomplete_fields = ['muscle_group']
    verbose_name = 'Мышечная группа'
    verbose_name_plural = 'Мышечные группы'


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'exercise_count', 'description']
    search_fields = ['name']

    @admin.display(description='Упражнений')
    def exercise_count(self, obj):
        return obj.exercise_links.count()


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ['name', 'primary_muscles', 'secondary_muscles', 'image_preview']
    search_fields = ['name']
    inlines = [ExerciseMuscleGroupInline]

    @admin.display(description='Основные мышцы')
    def primary_muscles(self, obj):
        links = obj.muscle_group_links.filter(is_primary=True).select_related('muscle_group')
        return ', '.join(link.muscle_group.name for link in links) or '—'

    @admin.display(description='Вспомогательные мышцы')
    def secondary_muscles(self, obj):
        links = obj.muscle_group_links.filter(is_primary=False).select_related('muscle_group')
        return ', '.join(link.muscle_group.name for link in links) or '—'

    @admin.display(description='Фото')
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px; border-radius:4px;" />', obj.image.url)
        return '—'
