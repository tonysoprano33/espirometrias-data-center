# Campos exactos propuestos para la agenda web

## Objetivo

La agenda web debe reemplazar la hoja de papel sin perder ninguno de los datos que despues usas para armar el informe.

## Supuesto de trabajo

Tomo como base lo que describiste:

- la agenda maneja pacientes por fecha;
- puede registrar `Espirometria` o `Ciclometria`;
- por defecto el tipo queda en `Ciclometria`;
- y la clasificacion final la completa el medico.

Si despues vemos que `Ciclometria` y `Prueba de caminata` no son exactamente lo mismo en tu flujo real, ajustamos el formulario sin romper el resto del sistema.

## Campos de agenda

### 1. Datos de turno o atencion

- `fecha_atencion` obligatorio
- `hora_atencion` opcional
- `tipo_estudio` obligatorio
  - `Ciclometria` por defecto
  - `Espirometria`
- `estado_atencion` obligatorio
  - `Pendiente`
  - `Cargada`
  - `Revisada por medico`
  - `Informe generado`
  - `Entregada`

### 2. Datos del paciente

- `apellido_nombre` obligatorio
- `dni` obligatorio
- `fecha_nacimiento` opcional
- `telefono` opcional
- `observaciones_paciente` opcional

### 3. Cobertura

- `tipo_cobertura` obligatorio
  - `Mutual`
  - `Particular`
- `nombre_mutual` opcional
- `numero_afiliado` opcional

### 4. Derivacion

- `medico_derivante` obligatorio
- valor inicial sugerido: `DR. GUSTAVO PIGUILLEM`

### 5. Signos en reposo

- `so2_reposo` obligatorio
- `fc_reposo` obligatorio
- `ta_reposo` opcional

### 6. Datos posteriores a prueba

- `so2_post_prueba` opcional
- `fc_post_prueba` opcional
- `distancia_metros` opcional
  - `100`
  - `200`
- `prueba_concluida` opcional
- `se_detuvo` opcional
- `presento_sintomas` opcional
- `borg_final` opcional

### 7. Resultado respiratorio

- `patron_respiratorio` obligatorio para espirometria validada
  - `Normal`
  - `Obstructivo`
  - `Restrictivo`
  - `Mixto`
- `grado_obstruccion` opcional
  - `Leve`
  - `Moderada`
  - `Moderadamente severa`
  - `Severa`
- `grado_restriccion` opcional
  - `Leve`
  - `Moderada`
  - `Moderadamente severa`
  - `Severa`
- `broncodilatador_positivo` opcional
- `comentario_medico` opcional

## Archivos asociados

- `pdf_resultado_original`
- `foto_resultado` opcional
- `informe_generado_docx`
- `informe_generado_pdf` opcional

## Campos de auditoria

- `creado_por`
- `creado_en`
- `actualizado_por`
- `actualizado_en`
- `validado_por_medico`
- `validado_en`

## Que ve cada usuario

### Recepcion o secretaria

- fecha
- paciente
- estudio
- cobertura
- signos
- PDF
- estado

### Medico

- PDF
- datos clinicos
- clasificacion final
- comentario
- boton generar informe

## Reglas utiles

- Si `tipo_cobertura = Mutual`, mostrar `nombre_mutual`.
- Si `tipo_estudio = Espirometria`, pedir resultado respiratorio.
- Si hay datos post prueba, permitir generar informe completo.
- Si se marca `Mutual` y no hay datos de caminata o equivalentes, avisar antes de generar el informe mutual.
