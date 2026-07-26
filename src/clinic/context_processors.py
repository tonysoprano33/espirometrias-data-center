from .roles import fixed_work_mode_for_user, get_request_work_mode, work_mode_label


def current_work_mode(request):
    mode = get_request_work_mode(request)
    return {
        "current_work_mode": mode,
        "current_work_mode_label": work_mode_label(mode),
        "is_fixed_role_session": bool(fixed_work_mode_for_user(request.user)),
    }
