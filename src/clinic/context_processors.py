WORK_MODES = {"secretaria", "medico", "espirometrista"}


def current_work_mode(request):
    saved_mode = str(request.session.get("clinic_work_mode", "") or "").strip()
    mode = saved_mode if saved_mode in WORK_MODES else "espirometrista"
    return {"current_work_mode": mode}
