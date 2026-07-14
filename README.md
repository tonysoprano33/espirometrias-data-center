# Clinica Automatizador Espiro

![Django](https://img.shields.io/badge/Django-6.0-092e20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-Deploy-000000?style=for-the-badge&logo=vercel&logoColor=white)

**Clinica Automatizador Espiro** es una plataforma integral diseñada para modernizar y automatizar el flujo de trabajo en clínicas de neumonología. Resuelve la transición de agendas en papel y procesos manuales hacia un ecosistema digital centralizado que automatiza la extracción de datos médicos y la generación de informes clínicos.

## 🚀 Problemas que Resuelve

### 1. Centralización de la Información Clinica
- Elimina la dispersión de datos entre papeles y archivos locales.
- Base de datos unificada de pacientes con historial completo de estudios (Espirometrías, Ciclometrías, Caminatas de 6 minutos).

### 2. Automatización de Ingreso de Datos (OCR)
- Integra un motor de **OCR (RapidOCR)** que procesa automáticamente los PDFs generados por los equipos de estudio (ej. espirómetros).
- Extrae valores biométricos y demográficos directamente del documento, minimizando errores de carga manual y acelerando el proceso de recepción.

### 3. Generación Inteligente de Informes
- Automatiza la creación de informes médicos en formato `.docx` y `.pdf`.
- Traduce clasificaciones médicas (Patrón Obstructivo, Restrictivo, Mixto) y grados de severidad en texto clínico redactado profesionalmente.
- Maneja diferentes formatos: Informe Médico Completo, Informe para Mutual e Informes de Ciclometría.

### 4. Flujo de Trabajo Colaborativo (Roles)
- **Recepción/Secretaría**: Gestión de turnos (agenda diaria), carga de signos vitales (SO2, FC, TA) y subida de estudios.
- **Médico**: Bandeja de revisión para validar estudios, clasificar resultados y autorizar informes.
- **Administración**: Gestión de usuarios, catálogos de médicos derivantes y auditoría.

### 5. Trazabilidad y Auditoría
- Registro detallado de eventos por cada atención: quién creó el turno, quién subió el archivo, cuándo lo validó el médico y cuándo se generó el informe.

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12 + Django 6.0
- **Base de Datos**: PostgreSQL (vía Supabase) con fallback a SQLite para desarrollo.
- **Procesamiento de Documentos**:
    - `python-docx`: Generación de informes Word.
    - `pypdfium2`: Renderizado y manipulación de PDFs.
    - `rapidocr_onnxruntime`: Motor de OCR para extracción de datos.
- **Frontend**: Django Templates con integración de componentes modernos para visualización de PDFs.
- **Despliegue**: Optimizado para Vercel.

## 📋 Características Técnicas Destacadas

- **Gestión de Signos Vitales**: Seguimiento pre y post prueba (Saturación O2, Frecuencia Cardíaca).
- **Prueba de Caminata (6MWT)**: Registro de distancia, escala de Borg y síntomas.
- **Previsualización de Documentos**: Generación automática de miniaturas de los estudios cargados para una revisión rápida.
- **Arquitectura de Servicios**: Lógica de negocio desacoplada en `services.py` y procesamiento de archivos en `pdf_intake.py`.

## ⚙️ Configuración y Uso

### Instalación

1. Clonar el repositorio.
2. Crear y activar un entorno virtual: `python -m venv .venv`
3. Instalar dependencias: `pip install -r requirements.txt`
4. Configurar variables de entorno en `.env` (ver `.env.example`).

### Ejecución Local

```powershell
# Migraciones
python src/manage.py migrate

# Iniciar servidor
python src/manage.py runserver
```

## 📈 Próximos Pasos

- Integración directa con el sistema de archivos de equipos médicos antiguos (Legacy Bridge).
- Análisis estadístico avanzado de tendencias por paciente.
- Firma digital de informes médicos.

---
*Desarrollado para optimizar la atención médica y reducir la carga administrativa.*
