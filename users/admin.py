from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'gender', 'date_of_birth', 'is_staff', 'is_active']
    list_filter = ['gender', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']
    fieldsets = UserAdmin.fieldsets + (
        ('Доп. информация', {'fields': ('date_of_birth', 'gender')}),
    )
