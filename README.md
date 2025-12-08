# Módulo NCF - Comprobantes Fiscales para República Dominicana

[![Odoo Version](https://img.shields.io/badge/Odoo-17.0-blue.svg)](https://www.odoo.com)
[![License](https://img.shields.io/badge/License-LGPL--3-green.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![DGII](https://img.shields.io/badge/DGII-Norma%2007--2018-orange.svg)](https://dgii.gov.do)

Módulo de localización dominicana para Odoo 17 que implementa la gestión completa de Comprobantes Fiscales (NCF) según las normativas de la Dirección General de Impuestos Internos (DGII).

![Dashboard NCF](static/description/dashboard.png)

## 🚀 Características Principales

### Gestión de NCF
- ✅ Secuencias automáticas por tipo de comprobante
- ✅ Validación de estructura NCF (B01, B02, B04, B14, B15, etc.)
- ✅ Control de vencimiento de secuencias
- ✅ Alertas de agotamiento de comprobantes
- ✅ Asignación automática según tipo de cliente/operación

### Validación RNC/Cédula
- ✅ Consulta en tiempo real a DGII
- ✅ Autocompletado de razón social
- ✅ Validación de formato (RNC 9 dígitos, Cédula 11 dígitos)
- ✅ Detección automática de tipo de identificación

### Reportes DGII
- ✅ **606** - Compras de Bienes y Servicios
- ✅ **607** - Ventas de Bienes y Servicios
- ✅ **608** - Comprobantes Anulados
- ✅ **609** - Pagos al Exterior
- ✅ **IR-17** - Resumen de Retenciones

Todos los reportes cumplen con la **Norma General 07-2018** y actualizaciones posteriores.

### Retenciones
- ✅ ISR (Impuesto Sobre la Renta)
- ✅ ITBIS Retenido
- ✅ Cálculo automático según tipo de proveedor
- ✅ Integración con reportes DGII

### Plantillas de Factura
- 📄 **Profesional** - Formato estándar con todos los datos fiscales
- 🧾 **Ticket** - Formato reducido para impresoras térmicas
- 📋 **Compacta** - Formato intermedio optimizado

### Dashboard
- 📊 Resumen de facturas del mes
- 📈 Estado de secuencias NCF
- ⚠️ Alertas de vencimiento
- 🔔 Recordatorios automáticos

## 📋 Requisitos

- Odoo 17.0 Community o Enterprise
- Módulo `l10n_do` (Localización Dominicana base)
- Módulo `account` (Contabilidad)
- Módulo `contacts` (Contactos)
- Módulo `mail` (Correo)
- Python 3.10+

## 🔧 Instalación

### Método 1: Desde ZIP

1. Descarga el archivo ZIP del módulo
2. Extrae en la carpeta de addons de Odoo: `/opt/odoo/addons/`
3. Reinicia Odoo
4. Ve a **Aplicaciones** → Actualizar lista de aplicaciones
5. Busca "NCF" e instala

### Método 2: Desde Git
```bash
cd /opt/odoo/addons
git clone https://github.com/tu-usuario/l10n_do_ncf.git
```

Reinicia Odoo y activa el módulo desde Aplicaciones.

## ⚙️ Configuración Inicial

### 1. Activar Licencia

1. Ve a **Contabilidad → Configuración → Licencia NCF**
2. Si no tienes licencia, haz clic en **"Comprar Licencia"**
3. Ingresa tu clave de licencia
4. Haz clic en **"Validar Licencia"**

### 2. Configurar Secuencias NCF

1. Ve a **Contabilidad → Configuración → Secuencias NCF**
2. Crea las secuencias según tu autorización DGII:
   - **B01** - Facturas de Crédito Fiscal
   - **B02** - Facturas de Consumo
   - **B04** - Notas de Crédito
   - **B14** - Regímenes Especiales
   - **B15** - Gubernamental

### 3. Configurar Empresa

1. Ve a **Ajustes → Compañías**
2. Asegúrate de tener configurado:
   - RNC de la empresa
   - Dirección completa
   - Logo (para facturas)

## 📊 Uso de Reportes DGII

### Generar Reportes

1. Ve a **Contabilidad → Reportes → Reportes DGII**
2. Selecciona el tipo de reporte (606, 607, 608, 609 o IR-17)
3. Selecciona el período
4. Haz clic en **"Generar Reporte"**
5. Descarga el archivo TXT

### Formato de Archivos

Los archivos generados cumplen con las especificaciones técnicas de DGII:
- Delimitador: `|` (pipe)
- Encoding: UTF-8
- Formato fechas: AAAAMMDD
- Formato montos: Decimal con punto (123.45)

## 🔔 Alertas Automáticas

El módulo incluye un sistema de alertas que notifica:
- **Día 10 de cada mes**: Recordatorio para enviar reportes DGII
- **Secuencias por agotarse**: Cuando quedan pocos comprobantes
- **Licencia por vencer**: 7 días antes del vencimiento

## 📄 Tipos de NCF Soportados

| Código | Descripción | Uso |
|--------|-------------|-----|
| B01 | Crédito Fiscal | Ventas a contribuyentes |
| B02 | Consumidor Final | Ventas a consumidores |
| B04 | Nota de Crédito | Devoluciones y descuentos |
| B14 | Regímenes Especiales | Zonas francas, etc. |
| B15 | Gubernamental | Ventas al gobierno |
| B16 | Exportaciones | Ventas al exterior |

## 🛠️ Soporte Técnico

- **Website:** https://www.newplain.com/
- **Comprar Licencia:** https://node-a1.newplain.com/buy/
- **Email:** soporte@newplain.com

## 📜 Normativas de Referencia

- Norma General 07-2018
- Norma General 05-2019
- Norma General 01-2020
- Norma General 04-2022
- Norma General 06-2023

## 📝 Changelog

### v17.0.1.8.0 (2025-12)
- ✨ Reportes DGII 606, 607, 608, 609, IR-17
- ✨ Sistema de alertas automáticas
- ✨ Dashboard mejorado con scroll
- ✨ Plantillas de factura optimizadas
- 🐛 Corrección validaciones DGII

### v17.0.1.7.0 (2025-11)
- ✨ Sistema de retenciones ISR/ITBIS
- ✨ Validación RNC en tiempo real
- ✨ Integración con API DGII

## 📄 Licencia

Este módulo está licenciado bajo LGPL-3.0. Ver archivo [LICENSE](LICENSE) para más detalles.

---

**Desarrollado por [NewPlain](https://www.newplain.com/)** | © 2025
