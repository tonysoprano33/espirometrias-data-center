# Relevamiento funcional de `E:\espiro`

## Conclusion

El sistema actual no es solo un `.exe`: en `E:\espiro\main.py` ya existe una logica bastante clara para generar informes respiratorios en Word. La web debe apuntar a paridad funcional con esta logica y no a reemplazarla a ciegas.

## Lo que hoy hace el sistema actual

### Datos generales

- Fecha del informe: actual o manual.
- Nombre completo del paciente.
- DNI.
- Medico derivante.
- Medico por defecto: `DR. GUSTAVO PIGUILLEM`.

### Espirometria

- SO2 en reposo.
- FC en reposo.
- Patron respiratorio:
  - `Normal`
  - `Obstructivo`
  - `Restrictivo`
  - `Mixto`
- Grado obstructivo:
  - `leve`
  - `moderado`
  - `moderadamente severa`
  - `severo`
- Grado restrictivo:
  - `leve`
  - `moderado`
  - `moderadamente severa`
  - `severo`
- Opcion `Broncodilatador positivo`.

### Caminata de 6 minutos

- Se puede incluir o no.
- SO2 al regresar.
- FC maxima.
- Distancia:
  - `100`
  - `200`
- Indica si la prueba:
  - concluyo correctamente;
  - se detuvo;
  - presento sintomas.
- Escala de Borg final.

### Mutual

- Opcion para generar informe de mutual.
- Solo genera el documento mutual si tambien se incluye caminata.

### Salidas

- Genera un informe Word principal.
- Puede generar un segundo Word para mutual.
- Guarda archivos en carpeta por fecha.
- Puede procesar carga manual o por lote desde Excel.
- Puede exportar plantilla Excel de carga masiva.

## Comportamiento que debemos conservar en la web

### Paridad obligatoria para el MVP

- Carga manual de paciente y estudio.
- Generacion de informe Word con la misma estructura clinica.
- Soporte para patron `Normal`, `Obstructivo`, `Restrictivo`, `Mixto`.
- Soporte para caminata de 6 minutos.
- Soporte para informe de mutual.
- Medico derivante por defecto.
- Clasificacion y grados controlados por lista.

### Paridad importante, pero puede entrar en segunda etapa

- Carga masiva desde Excel.
- Exportacion de plantilla Excel.
- Apertura automatica de carpeta local.
- Comportamientos puramente de escritorio.

## Diferencia entre el sistema actual y la nueva web

El sistema actual genera informe desde datos ingresados manualmente.

La nueva web ademas debe:

- guardar pacientes;
- guardar estudios;
- subir PDF del resultado;
- permitir revision medica;
- guardar la clasificacion final;
- auditar quien cargo y quien valido;
- y mantener historial.

## Regla de oro de migracion

No reemplazar la logica de `E:\espiro` al principio.

Primero hay que encapsularla para que la web la use como motor de generacion.

## Recomendacion tecnica

Conviene separar:

- `motor de informe`
- `base de datos`
- `web`

Asi, si algun dia cambia el formato del informe, cambiamos el motor sin romper la agenda ni el historial.
