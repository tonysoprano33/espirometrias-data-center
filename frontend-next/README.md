# Frontend Next.js en migracion gradual

Esta carpeta es una nueva agenda aislada. No modifica el despliegue Django ni las rutas actuales.

1. En una terminal, iniciar Django: `python src/manage.py runserver`.
2. En otra terminal: `cd frontend-next; npm install; npm run dev`.
3. Abrir `http://127.0.0.1:3000/login/`, iniciar sesion y luego volver a la
   portada de Next.

Usar siempre `127.0.0.1` (no `localhost`) para que Django y el preview de Next
compartan la misma cookie durante las pruebas.

La configuracion de `next.config.mjs` reenvia `/api/v1/*` a Django. La primera API es de solo lectura para validar rendimiento y actualizaciones silenciosas antes de migrar las acciones de agenda.
