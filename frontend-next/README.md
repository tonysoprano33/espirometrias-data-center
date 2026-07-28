# Preview Next.js aislado

Este directorio inicia la migracion real a Next.js + Supabase. No redirige ni
depende de Django. La aplicacion Django productiva permanece intacta hasta que
las fases de migracion se aprueben y validen.

## Desarrollo local

1. Copiar `.env.example` como `.env.local` y completar solo las variables
   publicas del proyecto Supabase de **staging**.
2. Aplicar `supabase/migrations/20260728_0001_foundation_auth.sql` en staging.
3. Crear una cuenta de prueba en Supabase Auth y activar/asignar su perfil.
4. Ejecutar `npm install` y `npm run dev` dentro de `frontend-next`.
5. Abrir `http://127.0.0.1:3000`.

No agregar claves secretas (`service_role`/`sb_secret`) a este frontend ni a
variables `NEXT_PUBLIC_*`.
