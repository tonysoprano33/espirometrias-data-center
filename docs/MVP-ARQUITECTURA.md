# MVP tecnico recomendado

## Decision principal

La mejor base para este proyecto es una app web en Python con un backend que reutilice el motor actual de `E:\espiro`, pero sin depender de compatibilidad con Windows XP para el frontend.

## Stack recomendado

### Backend

- `Django`
- `PostgreSQL`
- almacenamiento de archivos en disco o blob storage
- generacion de informes con la misma logica de `python-docx`

### Frontend

- interfaz web moderna
- HTML server-side como base solida
- CSS cuidado y orientado a uso diario
- JavaScript para mejorar la carga rapida, la revision y la impresion

## Motivo de esta eleccion

- Tu sistema actual ya esta en Python.
- Reusar la logica de informes es mucho mas facil en Python.
- Django trae auth, sesiones, permisos y panel admin.
- Ya no hace falta frenar UX o tecnologia por culpa del navegador de XP.
- El rendimiento y la mantenibilidad pasan a ser prioridad real.

## Rol de la PC con XP

La PC con `Windows XP Professional` queda fuera del alcance de la web.

Su rol queda limitado a:

- generar el resultado del estudio;
- exportar o descargar el PDF;
- seguir siendo la maquina conectada al equipo si hace falta.

La web principal se usa desde notebook o PCs modernas.

## Riesgo operativo actual

El problema principal ya no es el navegador.

El problema principal es el traslado del PDF desde la maquina del estudio a la notebook.

### Alternativas a evaluar

- carpeta compartida local;
- pendrive como solucion transitoria;
- importacion automatica desde una carpeta observada;
- carga masiva de PDFs;
- integracion directa futura con el output del software del estudio.

## Alcance del MVP

### Incluye

- login con usuario y clave;
- roles `admin`, `secretaria`, `medico`;
- agenda diaria;
- alta y busqueda de pacientes;
- carga de estudio;
- upload de PDF;
- clasificacion medica;
- generacion de informe `.docx`;
- impresion individual y del dia;
- historial.

### No incluye en la primera etapa

- firma digital avanzada;
- integracion con WhatsApp;
- OCR total del PDF;
- app mobile nativa;
- reemplazo completo del software del equipo.

## Plan de construccion

### Fase 0

- congelar campos reales;
- conseguir ejemplos reales de PDF;
- conseguir ejemplos reales de informes de salida;
- definir como se va a mover el PDF en la operatoria diaria.

### Fase 1

- consolidar agenda web;
- consolidar pacientes;
- consolidar atenciones;
- subir PDF;
- guardar clasificacion medica.

### Fase 2

- consolidar el generador actual desde la web;
- mejorar impresion;
- mejorar historia clinica por paciente;
- ordenar archivos completos, mutual y PDF adjunto.

### Fase 3

- deploy remoto;
- almacenamiento seguro;
- automatizacion del ingreso de PDFs;
- mejoras visuales y de productividad.

## Punto clave de producto

La web no debe competir con `espiro`.

La web debe convertirse en:

- agenda;
- base de datos clinica;
- bandeja de revision medica;
- historial longitudinal del paciente;
- y puerta de entrada al mismo motor de informes.
