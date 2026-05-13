from django import forms
from .models import WorkoutExercise, ExerciseSet, WorkoutTemplate, TemplateExercise, TemplateSet


class WorkoutExerciseForm(forms.ModelForm):
    class Meta:
        model = WorkoutExercise
        fields = ['exercise']


class ExerciseSetForm(forms.ModelForm):
    class Meta:
        model = ExerciseSet
        fields = ['weight', 'reps']


class WorkoutTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkoutTemplate
        fields = ['name']


class TemplateExerciseForm(forms.ModelForm):
    class Meta:
        model = TemplateExercise
        fields = ['exercise']


class TemplateSetForm(forms.ModelForm):
    class Meta:
        model = TemplateSet
        fields = ['weight', 'reps']