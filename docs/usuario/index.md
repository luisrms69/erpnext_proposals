# Manual de usuario — ERPNext Proposals

Este manual cubre la operación de **ERPNext Proposals**, módulo para elaborar y gestionar propuestas comerciales profesionales sobre ERPNext.

## Qué cubre este manual

- Configuración del catálogo de secciones y alcances (una sola vez)
- Creación de propuestas sobre Cotizaciones
- Flujo de revisión y aprobación interna
- Generación del PDF de propuesta
- Envío manual al cliente
- Qué ocurre cuando una propuesta se gana
- Creación del proyecto de ejecución desde la propuesta
- Limitaciones conocidas del release candidate

## Qué NO cubre este manual

- Instalación o configuración técnica del módulo
- Administración de roles y permisos del sistema
- Operación de ERPNext estándar (Cotizaciones, Items, Clientes, Sales Orders)
- Documentación técnica de integración — ver [docs/tecnico/](../tecnico/index.md)

## Roles del módulo

| Rol | Puede hacer |
|---|---|
| **Proposals User** | Crear propuestas, enviar a revisión, revisar propuestas rechazadas |
| **Proposals Manager** | Todo lo anterior + aprobar, rechazar, marcar como enviada al cliente, crear proyectos |
| **System Manager** | Acceso completo + configuración del catálogo |

## Archivos de este manual

| Archivo | Contenido |
|---|---|
| [Flujo operativo](flujo-operativo.md) | El proceso completo, etapa por etapa |
| [DocTypes del módulo](doctypes.md) | Qué es cada tipo de documento y cuándo se usa |
| [Campos principales](campos-principales.md) | Referencia de campos por documento |
| [Cómo crear una propuesta](crear-propuesta.md) | Instrucciones paso a paso |
| [Generar y enviar al cliente](generar-enviar-propuesta.md) | PDF, descarga y envío manual |
| [Propuesta ganada](propuesta-ganada.md) | Qué hacer cuando el cliente acepta |
| [Proyecto generado](proyecto-generado.md) | Qué pasa cuando se crea el proyecto |
| [Limitaciones del RC](limitaciones-rc.md) | Errores conocidos, pasos manuales, pendientes |
