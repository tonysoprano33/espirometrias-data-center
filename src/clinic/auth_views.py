from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.urls import reverse

from .roles import (
    ROLE_SESSION_USERS,
    fixed_work_mode_for_user,
    provision_role_session_accounts,
)


class RoleLoginView(LoginView):
    template_name = "registration/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            user_model = get_user_model()
            username_field = user_model.USERNAME_FIELD
            username = str(request.POST.get(username_field, "") or "").strip().lower()
            if username in ROLE_SESSION_USERS and not user_model._default_manager.filter(
                **{f"{username_field}__iexact": username}
            ).exists():
                provision_role_session_accounts()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        if fixed_work_mode_for_user(self.request.user) == "medico":
            return reverse("clinic:doctor_review_list")
        return reverse("clinic:dashboard")
