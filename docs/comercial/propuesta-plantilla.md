# Propuesta comercial · CashFlow Manager (plantilla)

> Plantilla según spec §15: **instalación, soporte y costos AWS por separado**.
> Completar los campos `[ ]`. Los importes son a definir por el proveedor.

**Cliente:** [Razón social] · **CUIT:** [ ] · **Contacto:** [ ]
**Fecha:** [ ] · **Validez de la oferta:** 15 días

## 1. Qué incluye

- Aplicación de escritorio para Windows 10/11 (instalador) para [N] usuarios.
- Dashboard web privado con indicadores de cobranza, accesible por HTTPS.
- Servidor en AWS (región San Pablo) con base de datos, copias diarias cifradas y
  restauración probada.
- Carga inicial: importación de hasta [5.000] facturas desde Excel/CSV y alta de usuarios.
- Capacitación remota de [2] horas y manual de uso.

**No incluye** (posibles ampliaciones): facturación electrónica AFIP/ARCA, conciliación
bancaria, envíos por WhatsApp o email, múltiples empresas, monedas extranjeras, app móvil.

## 2. Inversión

| Concepto | Modalidad | Importe |
|---|---|---|
| Licencia de uso + implementación (instalación del servidor, dominio, HTTPS, carga inicial, capacitación) | Pago único | $ [ ] |
| Soporte y mantenimiento (actualizaciones, monitoreo de backups, consultas en horario hábil, respuesta en [8] h hábiles) | Mensual | $ [ ] |
| Infraestructura AWS (a cargo del cliente en su cuenta, o facturada al costo + [ ] %) | Mensual, en USD | ~USD 33 estimados* |
| Firma digital del instalador (certificado de firma de código, opcional) | Anual | ~USD [ ] |

\* Estimación octubre 2026 para región San Pablo (EC2 t3.small, disco 30 GB, IP pública,
S3 y KMS); varía con el tipo de cambio y el uso. Detalle en `docs/runbook/despliegue-aws.md`.

## 3. Plan de trabajo

| Semana | Hito |
|---|---|
| 1 | Relevamiento, alta de dominio y servidor, carga inicial de clientes y facturas |
| 2 | Instalación en las PCs, capacitación, puesta en marcha acompañada |
| 3-4 | Ajustes menores y cierre |

## 4. Condiciones

- **Datos**: los datos pertenecen al cliente. Se alojan en [la cuenta AWS del cliente /
  la cuenta del proveedor] con acceso restringido. No se comparten con terceros ni se usan
  con servicios de IA sin autorización escrita (spec §11). Se firma un acuerdo de
  confidencialidad y de tratamiento de datos personales (Ley 25.326).
- **Copias de seguridad**: diarias, cifradas, con 90 días de retención y prueba de
  restauración semanal.
- **Credenciales**: se entregan credenciales iniciales que el cliente cambia en el primer uso.
- **Baja del servicio**: al finalizar se entrega un backup completo y una exportación CSV.

[Firma proveedor] · [Firma cliente]
