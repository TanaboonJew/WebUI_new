from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def role_verified_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login') 

        if request.user.role == 'none' or not request.user.role_verified:
            messages.warning(request, "กรุณายืนยันบทบาทก่อนเข้าถึงหน้านี้")
            return redirect('home')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
