# Auditoria Next.js - 2026-07-28

## Alcance

Se revisaron las rutas y acciones de `frontend-next`, las migraciones de Supabase, los flujos de agenda, pacientes, revision medica, archivos, papelera, estadisticas e impresion. La version estable de Django/Vercel no se modifico.

La comparacion visual autenticada con la aplicacion estable no puede automatizarse desde el HTML publico: sus rutas devuelven la pantalla de acceso sin una sesion. Por eso las diferencias de interfaz se contrastan contra las capturas y requisitos existentes, y no se presentan como una equivalencia visual 1:1 no verificada.

## Hallazgos priorizados

### Criticos

- **Archivos historicos:** la migracion copia metadatos de adjuntos, pero no puede reconstruir binarios que no existan en Storage. La base actual tiene 41 adjuntos y los 41 tienen objeto en el bucket privado; los archivos antiguos que falten no deben marcarse como disponibles. La ficha mantiene el aviso y permite volver a subirlos.
- **Impresion:** la ruta de impresion de Next abre o combina PDFs ya almacenados. Todavia no reemplaza el generador de informes DOCX/PDF de la aplicacion original ni garantiza sus plantillas de mutual, ciclometria y espirometria. No se debe declarar la migracion lista para trabajo real hasta portar ese generador y probarlo con informes reales.
- **OCR/sugerencia:** Next almacena el archivo y muestra campos sugeridos migrados, pero no implementa aun una lectura OCR completa del PDF/foto. No se debe inventar un diagnostico cuando la lectura no existe; el medico debe confirmar el resultado.

### Altos

- **Papelera:** los botones visibles no tenian acciones. Se habilito restauracion de pacientes y atenciones mediante RPCs protegidas. El borrado definitivo sigue bloqueado hasta definir una purga segura y confirmacion explicita.
- **Migraciones:** las RPC de notas clinicas y restauracion de pacientes estaban en archivos pero no aplicadas. Se aplicaron `0011_clinical_notes_rpc.sql` y `0012_trash_restore_patient.sql`; tambien se verificaron las RPC operativas y el bucket privado `attachments`.
- **Validacion de archivos:** la carga valida extension, tamano, firma PDF y normaliza el nombre para Storage. El nombre original se conserva para mostrarlo al usuario; no se debe rechazar una `ñ` o espacios solo por el nombre.
- **Comandos de calidad:** `next lint` estaba obsoleto en Next 16. Se cambio el script `lint` a `tsc --noEmit` para que el chequeo sea ejecutable y verificable.

### Medios

- **Pacientes:** la lista tiene busqueda por nombre/DNI/telefono/codigo y paginacion de 20. Falta una pantalla completa para editar datos demograficos y una prevencion de duplicados basada primero en DNI y luego en telefono/fecha de nacimiento.
- **Estadisticas:** existen filtros mensuales, mutuales y resultados, pero faltan tiempos de espera/atencion/despacho porque esas marcas no se exponen en la consulta actual.
- **Estados:** agenda, revision y papelera usan estados relacionados pero no comparten aun un catalogo visual unico. Conviene mantener gris pendiente, naranja por revisar y verde resuelto antes de seguir agregando colores.
- **Codificacion:** quedan textos con caracteres rotos (`Ã`, `Â`) en varias vistas y mensajes heredados. Es un problema visual y de confianza, no de datos; debe corregirse por archivo y probarse con nombres reales.

## Verificaciones realizadas

- `npm run lint` pasa.
- `npm run build` pasa con Next 16.2.12 y TypeScript.
- Supabase: 107 pacientes, 131 atenciones, 41 adjuntos y 29 informes; no hay adjuntos del bucket `attachments` sin objeto correspondiente.
- Las RPC principales de agenda, asistencia, signos vitales, resultado medico, notas, edicion, eliminacion y restauracion existen.
- La produccion estable no fue reemplazada.

## Orden recomendado

1. Portar el generador de informes original y probar impresion individual y del dia con particular, mutual, ciclometria y espirometria.
2. Implementar OCR desacoplado con estado de archivo (`subido`, `leido`, `requiere revision`, `fallo`) y sin bloquear login ni despliegue.
3. Agregar edicion segura de paciente y deteccion de duplicados por DNI.
4. Corregir textos con codificacion rota y unificar estados visuales.
5. Medir y agregar tiempos operativos a estadisticas.
6. Solo despues migrar el trafico de produccion y probar rollback.
