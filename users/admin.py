from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'username', 'role', 'role_verified', 'is_accessible', 'is_staff', 'is_active'
    )

    search_fields = ('username',)

    list_filter = ('role', 'role_verified', 'is_accessible', 'is_staff', 'is_active')
    
    ordering = ('username',)

    # ฟิลด์ที่แสดงในหน้าฟอร์มสร้าง/แก้ไข user
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('role', 'intended_role', 'role_verified')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_accessible', 'groups', 'user_permissions')}),
        ('Resource Limits', {'fields': ('mem_limit', 'memswap_limit', 'storage_limit', 'cpu_limit', 'gpu_access')}),
        ('Active Container', {'fields': ('active_container',)}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role', 'is_active', 'is_staff', 'is_superuser', 'is_accessible'),
        }),
    )

# Register your models here.
