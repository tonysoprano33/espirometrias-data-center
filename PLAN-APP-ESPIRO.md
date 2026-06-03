# Plan actual para la app de agenda + espirometria

## Objetivo

Pasar de una agenda en papel y un generador local de informes a una solucion mas ordenada que:

- permita cargar pacientes y estudios desde la notebook o una PC moderna;
- guarde los datos de forma segura;
- deje al medico marcar el resultado final;
- conserve el PDF del estudio y los informes generados;
- y siga reutilizando la logica del sistema actual de `E:\espiro` mientras sea util.

## Decision actual importante

La PC con `Windows XP Professional` ya no es objetivo del frontend.

Desde ahora:

1. la PC con XP queda solo para generar el resultado del estudio;
2. la web principal corre en un entorno moderno;
3. la notebook o una PC actual se usa para agenda, revision, historial e impresion;
4. la UX ya no se limita por compatibilidad extrema con XP.

## Recomendacion principal

La mejor opcion ahora es esta:

1. mantener el output del estudio en la PC del equipo;
2. centralizar agenda, pacientes, revision medica e informes en la web;
3. guardar tanto los datos estructurados como el PDF del resultado;
4. mejorar el flujo de ingreso del PDF para no depender tanto del pendrive.

## Por que esta opcion es la mejor

- El proyecto actual en `E:\espiro` ya tiene la logica de negocio separada de la interfaz.
- El generador actual trabaja con datos estructurados y crea `.docx`, asi que se puede reaprovechar.
- La web puede usar tecnologia moderna sin quedar atada a navegadores viejos.
- XP queda aislado y no expuesto a internet.
- Mantener una base de datos de pacientes exige priorizar seguridad antes que compatibilidad extrema.

## Problema operativo principal actual

El cuello de botella principal ya no es el navegador de XP.

El cuello de botella es este flujo:

1. generar el resultado en la PC del estudio;
2. descargar o exportar el PDF;
3. moverlo con pendrive;
4. volver a cargarlo en la notebook.

Esto enlentece la operatoria diaria.

### Soluciones futuras a evaluar

- carpeta compartida en red local entre la PC del estudio y la notebook;
- watcher de carpeta que importe automaticamente nuevos PDFs;
- exportacion directa a una carpeta sincronizada;
- carga por lote de varios PDFs juntos;
- integracion posterior mas directa con el output del software del estudio si el equipo lo permite.

## Que conviene guardar

No conviene guardar solamente el resultado final.

Conviene guardar ambas cosas:

- el resultado estructurado;
- y el documento adjunto.

### Datos estructurados minimos

- fecha;
- nombre y documento;
- tipo de estudio: `Ciclometria` por defecto y `Espirometria` como alternativa;
- mutual o particular;
- medico derivante;
- SO2 y FC en reposo;
- SO2 y FC post prueba cuando corresponda;
- clasificacion final del medico;
- observaciones;
- usuario que cargo el estudio;
- fecha y hora de carga.

### Archivos a conservar

- PDF original de la espirometria;
- informe completo generado;
- informe mutual cuando corresponda;
- opcionalmente imagen o foto enviada al medico.

## Flujo ideal de trabajo

1. Recepcion carga el turno o la atencion en la agenda web.
2. Se completa paciente, mutual, tipo de estudio, medico derivante y signos.
3. Se sube el PDF del resultado o se importa desde una carpeta compartida.
4. El medico entra con su usuario, revisa el estudio y marca clasificacion y grado.
5. El sistema guarda la decision y genera los informes necesarios.
6. El informe queda disponible para imprimir, descargar o reenviar.

## Que hacer con el sistema actual de `E:\espiro`

Segun el codigo revisado, hoy el sistema ya:

- recibe nombre, DNI, medico, SO2, FC y patron;
- contempla caminata de 6 minutos;
- contempla mutual;
- genera uno o mas `.docx`.

Eso sugiere esta estrategia:

### Fase 1

Reutilizar la logica de generacion del informe desde la web actual.

### Fase 2

Ordenar el deploy remoto y el almacenamiento seguro.

### Fase 3

Resolver una forma mas rapida de mover el PDF desde la maquina del estudio a la notebook.

## Arquitectura recomendada

### Frontend

Una web moderna con:

- login;
- agenda diaria;
- formulario de carga;
- lista de pacientes;
- detalle del estudio;
- visor de PDF;
- pantalla del medico para clasificar;
- boton de generar informe;
- impresion diaria;
- historial clinico por paciente.

### Backend

Un servicio con:

- autenticacion por roles;
- base de datos;
- almacenamiento de archivos;
- generacion de informes;
- auditoria basica.

### Roles

- `Recepcion/secretaria`: agenda, carga, subida de PDF.
- `Medico`: revisa, clasifica y valida criterio.
- `Admin`: usuarios, catalogos y configuracion.

## Modelo minimo de datos

### Paciente

- id
- nombre
- dni
- fecha_nacimiento opcional
- observaciones opcional

### Atencion

- id
- fecha
- paciente_id
- tipo_estudio
- mutual_tipo
- medico_derivante
- so2_reposo
- fc_reposo
- so2_post
- fc_post
- pdf_original_path
- estado

### Resultado medico

- atencion_id
- patron
- grado_obstruccion
- grado_restriccion
- broncodilatador_positivo
- comentario
- medico_id
- fecha_validacion

### Informe

- atencion_id
- archivo_generado_path
- version
- fecha_generacion

## Orden de construccion recomendado

1. Consolidar agenda diaria, revision e impresion en la web.
2. Mejorar UI/UX y velocidad de carga.
3. Resolver el ingreso del PDF sin pendrive o, al menos, con menos pasos.
4. Reusar el generador actual para emitir el informe desde la web.
5. Construir historial clinico mas robusto por paciente.
6. Recien despues evaluar si conviene integrar mas a fondo la salida del equipo del estudio.

## Alcance del MVP actual

El MVP deberia cubrir:

- login;
- agenda diaria;
- alta de pacientes;
- registrar `Espirometria` o `Ciclometria`;
- guardar signos, cobertura y medico derivante;
- subir PDF;
- permitir al medico marcar resultado;
- generar informe;
- imprimir o descargar;
- mantener archivos separados cuando una atencion mutual necesita informe completo + mutual + PDF del estudio.

## Decision sobre el producto

La web no debe competir con `espiro`.

La web debe convertirse en:

- agenda;
- base de datos clinica;
- bandeja de revision medica;
- historial por paciente;
- y puerta de entrada al mismo motor de informes.

## Siguiente paso sugerido

El siguiente foco practico deberia ser:

- modernizar mas la experiencia visual;
- preparar el deploy remoto;
- y buscar una forma mas comoda de mover el PDF desde la PC del estudio a la notebook.
