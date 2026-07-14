from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import Http404
from django.http import FileResponse
from django.urls import include, path


FAVICON_CONTENT_TYPES = {
    "favicon.svg": "image/svg+xml",
    "favicon-32.png": "image/png",
    "favicon.ico": "image/x-icon",
}


def favicon_file(request, filename):
    content_type = FAVICON_CONTENT_TYPES.get(filename)
    if not content_type:
        raise Http404("Favicon no encontrado")
    file_path = settings.PROJECT_DIR / "static" / filename
    if not file_path.exists():
        raise Http404("Favicon no encontrado")
    return FileResponse(file_path.open("rb"), content_type=content_type)


urlpatterns = [
    path("favicon.svg", favicon_file, {"filename": "favicon.svg"}),
    path("favicon-32.png", favicon_file, {"filename": "favicon-32.png"}),
    path("favicon.ico", favicon_file, {"filename": "favicon.ico"}),
    path("static/favicon.svg", favicon_file, {"filename": "favicon.svg"}),
    path("static/favicon-32.png", favicon_file, {"filename": "favicon-32.png"}),
    path("static/favicon.ico", favicon_file, {"filename": "favicon.ico"}),
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("clinic.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
