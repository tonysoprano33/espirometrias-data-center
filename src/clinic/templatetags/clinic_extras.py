from django import template

from clinic.services import formatear_dni


register = template.Library()


@register.filter
def dni_format(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    return formatear_dni(raw)
