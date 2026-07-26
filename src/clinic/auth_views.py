from django.contrib.auth.views import LoginView
from django.urls import reverse

from .roles import fixed_work_mode_for_user, provision_role_session_accounts


class RoleLoginView(LoginView):
    template_name = "registration/login.html"

    def dispatch(self, request, *args, **kwargs):
        provision_role_session_accounts()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        if fixed_work_mode_for_user(self.request.user) == "medico":
            return reverse("clinic:doctor_review_list")
        return reverse("clinic:dashboard")
