# Pendientes de paridad con la app Django estable

## DX: EPOC en el informe

- Persistir `dx_epoc` como booleano clínico asociado al resultado espirométrico.
- Exponerlo en la edición de atención para Espirometría.
- Mostrar `DX: EPOC` en la primera hoja del informe clínico y en la impresión directa solo cuando esté marcado.

## Recordatorio de broncodilatador

- El botón `Bronco` inicia una cuenta regresiva visual persistida de 10 minutos.
- El contador debe sobrevivir una recarga y terminar en `Bronco listo para el post`.
- Es un recordatorio operativo: nunca bloquea la carga de signos, la revisión ni la impresión.
