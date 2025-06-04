from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    intended_role = forms.ChoiceField(
        choices=CustomUser.ROLE_CHOICES,
        label="เลือกบทบาทที่คุณต้องการ",
        help_text="ระบบจะตั้งค่าบทบาทเป็น 'ปริญญาตรี' โดยอัตโนมัติ จนกว่าแอดมินจะอนุมัติ"
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password1', 'password2', 'intended_role']

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'ram_limit', 'storage_limit', 'cpu_limit', 'gpu_access')