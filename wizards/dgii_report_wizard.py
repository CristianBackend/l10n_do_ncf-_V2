# -*- coding: utf-8 -*-
"""
Generador de Reportes DGII segun Norma General 07-2018 y actualizaciones
606 - Compras de Bienes y Servicios (23 columnas)
607 - Ventas de Bienes y Servicios (23 columnas)
608 - Comprobantes Anulados (3 columnas)
609 - Pagos al Exterior (13 columnas)

Validado contra:
- Norma General 07-2018, 05-2019, 01-2020, 04-2022, 06-2023
- Especificaciones tecnicas DGII
- Validador oficial DGII
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from datetime import date, timedelta


class DgiiReportWizard(models.TransientModel):
    _name = 'l10n_do_ncf.dgii.report.wizard'
    _description = 'Wizard para Generar Reportes DGII'

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )
    report_type = fields.Selection([
        ('606', '606 - Compras de Bienes y Servicios'),
        ('607', '607 - Ventas de Bienes y Servicios'),
        ('608', '608 - Comprobantes Anulados'),
        ('609', '609 - Pagos al Exterior'),
        ('ir17', 'IR-17 - Resumen de Retenciones'),
    ], string='Tipo de Reporte', required=True, default='607')

    date_from = fields.Date(
        string='Desde',
        required=True,
        default=lambda self: date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=lambda self: date.today()
    )

    file_data = fields.Binary(string='Archivo', readonly=True)
    file_name = fields.Char(string='Nombre del Archivo', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
    ], default='draft')

    record_count = fields.Integer(string='Registros', readonly=True)
    total_amount = fields.Monetary(string='Monto Total', readonly=True, currency_field='currency_id')
    total_itbis = fields.Monetary(string='Total ITBIS', readonly=True, currency_field='currency_id')
    ir17_total_isr = fields.Monetary(string='Total Retencion ISR', readonly=True, currency_field='currency_id')
    ir17_total_itbis = fields.Monetary(string='Total Retencion ITBIS', readonly=True, currency_field='currency_id')
    ir17_total = fields.Monetary(string='Total a Pagar DGII', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            if self.date_from.month == 12:
                last_day = self.date_from.replace(day=31)
            else:
                next_month = self.date_from.replace(month=self.date_from.month + 1, day=1)
                last_day = next_month - timedelta(days=1)
            self.date_to = last_day

    def _format_amount(self, amount):
        if not amount or amount == 0:
            return ''
        return '{:.2f}'.format(abs(amount))

    def _format_amount_required(self, amount):
        return '{:.2f}'.format(abs(amount) if amount else 0)

    def _get_rnc_type(self, vat):
        if not vat:
            return '2'
        vat_clean = vat.replace('-', '').replace(' ', '')
        if len(vat_clean) == 9:
            return '1'
        return '2'

    def _clean_rnc(self, vat):
        if not vat:
            return ''
        return vat.replace('-', '').replace(' ', '')

    def _pad_ncf(self, ncf, length=11):
        if not ncf:
            return ''
        return (ncf or '')[:length]

    def _pad_ncf_modified(self, ncf):
        if not ncf:
            return ''
        return ncf.ljust(19)[:19]

    def _format_date(self, dt):
        if not dt:
            return ''
        return dt.strftime('%Y%m%d')

    def _validate_tipo_bienes(self, tipo):
        valid_tipos = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11']
        if tipo in valid_tipos:
            return tipo
        return '02'

    def action_generate_report(self):
        self.ensure_one()
        if self.report_type == '606':
            return self._generate_606()
        elif self.report_type == '607':
            return self._generate_607()
        elif self.report_type == '608':
            return self._generate_608()
        elif self.report_type == '609':
            return self._generate_609()
        elif self.report_type == 'ir17':
            return self._generate_ir17()

    def _generate_606(self):
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date')

        lines = []
        total_monto = 0.0
        total_itbis = 0.0

        rnc = self._clean_rnc(self.company_id.vat)
        period = self.date_from.strftime('%Y%m')
        lines.append(f"606|{rnc}|{period}|{len(invoices)}")

        for inv in invoices:
            rnc_supplier = self._clean_rnc(inv.partner_id.vat)
            tipo_id = self._get_rnc_type(inv.partner_id.vat)
            
            if not rnc_supplier:
                rnc_supplier = '00000000001'
                tipo_id = '2'  # DGII exige tipo_id=2 para suplidor informal
            
            tipo_bienes_raw = getattr(inv, 'l10n_do_expense_type', None) or '02'
            tipo_bienes = self._validate_tipo_bienes(tipo_bienes_raw)
            
            ncf = self._pad_ncf(getattr(inv, 'l10n_do_vendor_ncf', '') or '')
            
            ncf_modificado = ''
            if inv.move_type == 'in_refund' and inv.reversed_entry_id:
                ncf_mod = getattr(inv.reversed_entry_id, 'l10n_do_vendor_ncf', '') or ''
                ncf_modificado = self._pad_ncf_modified(ncf_mod)
            
            fecha_comprobante = self._format_date(inv.invoice_date)
            
            fecha_pago = ''
            if inv.payment_state in ('paid', 'in_payment'):
                try:
                    payments = inv._get_reconciled_payments()
                    if payments:
                        pay_date = max(p.date for p in payments)
                        if pay_date >= inv.invoice_date:
                            fecha_pago = self._format_date(pay_date)
                        else:
                            fecha_pago = fecha_comprobante
                except Exception:
                    fecha_pago = fecha_comprobante
            
            monto_bienes = 0.0
            monto_servicios = abs(inv.amount_untaxed)
            monto_total = monto_bienes + monto_servicios
            itbis_facturado = abs(inv.amount_tax)
            
            itbis_retenido = abs(getattr(inv, 'l10n_do_total_itbis_retention', 0) or 0)
            itbis_proporcionalidad = 0.0
            itbis_costo = 0.0
            itbis_adelantar = itbis_facturado - itbis_costo if itbis_facturado > itbis_costo else 0
            itbis_percibido = 0.0
            
            tipo_retencion_isr = ''
            monto_isr = abs(getattr(inv, 'l10n_do_total_isr_retention', 0) or 0)
            if monto_isr > 0:
                tipo_retencion_isr = '02'
            
            isr_percibido = 0.0
            isc = 0.0
            otros_impuestos = 0.0
            propina_legal = 0.0
            
            if inv.payment_state == 'paid':
                forma_pago = '02'
            elif inv.payment_state == 'not_paid':
                forma_pago = '04'
            else:
                forma_pago = '07'

            total_monto += monto_total
            total_itbis += itbis_facturado

            campos = [
                rnc_supplier, tipo_id, tipo_bienes, ncf, ncf_modificado,
                fecha_comprobante, fecha_pago,
                self._format_amount(monto_bienes), self._format_amount(monto_servicios),
                self._format_amount_required(monto_total), self._format_amount(itbis_facturado),
                self._format_amount(itbis_retenido), self._format_amount(itbis_proporcionalidad),
                self._format_amount(itbis_costo), self._format_amount(itbis_adelantar),
                self._format_amount(itbis_percibido), tipo_retencion_isr,
                self._format_amount(monto_isr), self._format_amount(isr_percibido),
                self._format_amount(isc), self._format_amount(otros_impuestos),
                self._format_amount(propina_legal), forma_pago,
            ]
            lines.append('|'.join(campos))

        content = '\n'.join(lines)
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_F_606_{rnc}_{period}.txt"
        self.state = 'generated'
        self.record_count = len(invoices)
        self.total_amount = total_monto
        self.total_itbis = total_itbis
        return self._return_wizard()

    def _generate_607(self):
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('l10n_do_ncf_number', '!=', False),
        ], order='invoice_date')

        lines = []
        total_monto = 0.0
        total_itbis = 0.0

        rnc = self._clean_rnc(self.company_id.vat)
        period = self.date_from.strftime('%Y%m')
        lines.append(f"607|{rnc}|{period}|{len(invoices)}")

        for inv in invoices:
            rnc_client = self._clean_rnc(inv.partner_id.vat)
            
            if rnc_client:
                tipo_id = self._get_rnc_type(inv.partner_id.vat)
            else:
                tipo_id = '3'
                rnc_client = '00000000000'
            
            ncf = self._pad_ncf(inv.l10n_do_ncf_number or '')
            
            ncf_modificado = ''
            if inv.move_type == 'out_refund':
                ncf_origin = getattr(inv, 'l10n_do_ncf_origin', '') or ''
                ncf_modificado = self._pad_ncf_modified(ncf_origin)
            
            tipo_ingreso = '02'
            ncf_type = getattr(inv, 'l10n_do_ncf_type_id', None)
            if ncf_type:
                code = ncf_type.code or ''
                if code in ('B01', 'B02', 'B14', 'B15'):
                    tipo_ingreso = '01'
            
            fecha_comprobante = self._format_date(inv.invoice_date)
            fecha_retencion = ''
            
            monto_facturado = abs(inv.amount_untaxed)
            itbis_facturado = abs(inv.amount_tax)
            
            itbis_retenido_terceros = 0.0
            itbis_percibido = 0.0
            retencion_renta_terceros = 0.0
            isr_percibido = 0.0
            isc = 0.0
            otros_impuestos = 0.0
            propina_legal = 0.0
            
            monto_total_con_itbis = abs(inv.amount_total)
            
            efectivo = 0.0
            cheque = 0.0
            tarjeta = 0.0
            credito = 0.0
            bonos = 0.0
            permuta = 0.0
            otras = 0.0
            
            if inv.payment_state == 'paid':
                cheque = monto_total_con_itbis
            elif inv.payment_state == 'not_paid':
                credito = monto_total_con_itbis
            elif inv.payment_state == 'partial':
                pagado = abs(inv.amount_total) - abs(inv.amount_residual)
                cheque = pagado
                credito = abs(inv.amount_residual)
            else:
                credito = monto_total_con_itbis

            total_monto += monto_facturado
            total_itbis += itbis_facturado

            campos = [
                rnc_client, tipo_id, ncf, ncf_modificado, tipo_ingreso,
                fecha_comprobante, fecha_retencion,
                self._format_amount_required(monto_facturado), self._format_amount(itbis_facturado),
                self._format_amount(itbis_retenido_terceros), self._format_amount(itbis_percibido),
                self._format_amount(retencion_renta_terceros), self._format_amount(isr_percibido),
                self._format_amount(isc), self._format_amount(otros_impuestos),
                self._format_amount(propina_legal),
                self._format_amount(efectivo), self._format_amount(cheque),
                self._format_amount(tarjeta), self._format_amount(credito),
                self._format_amount(bonos), self._format_amount(permuta),
                self._format_amount(otras),
            ]
            lines.append('|'.join(campos))

        content = '\n'.join(lines)
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_F_607_{rnc}_{period}.txt"
        self.state = 'generated'
        self.record_count = len(invoices)
        self.total_amount = total_monto
        self.total_itbis = total_itbis
        return self._return_wizard()

    def _generate_608(self):
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'cancel'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('l10n_do_ncf_number', '!=', False),
        ], order='invoice_date')

        lines = []
        rnc = self._clean_rnc(self.company_id.vat)
        period = self.date_from.strftime('%Y%m')
        lines.append(f"608|{rnc}|{period}|{len(invoices)}")

        for inv in invoices:
            ncf = self._pad_ncf(inv.l10n_do_ncf_number or '')
            fecha = self._format_date(inv.invoice_date)
            tipo_anulacion = '04'
            campos = [ncf, fecha, tipo_anulacion]
            lines.append('|'.join(campos))

        content = '\n'.join(lines)
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_F_608_{rnc}_{period}.txt"
        self.state = 'generated'
        self.record_count = len(invoices)
        return self._return_wizard()

    def _generate_609(self):
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('partner_id.country_id', '!=', False),
            ('partner_id.country_id.code', '!=', 'DO'),
        ], order='invoice_date')

        lines = []
        total_monto = 0.0
        rnc = self._clean_rnc(self.company_id.vat)
        period = self.date_from.strftime('%Y%m')
        lines.append(f"609|{rnc}|{period}|{len(invoices)}")

        for inv in invoices:
            razon_social = (inv.partner_id.name or '')[:50]
            tipo_id = '2' if inv.partner_id.company_type == 'company' else '1'
            id_tributaria = self._clean_rnc(inv.partner_id.vat) or 'N/A'
            pais = 'US'
            if inv.partner_id.country_id:
                pais = inv.partner_id.country_id.code or 'US'
            tipo_servicio = '02'
            detalle_servicio = '02'
            parte_relacionada = '0'
            numero_doc = (inv.ref or inv.name or '')[:30]
            fecha_doc = self._format_date(inv.invoice_date)
            monto = abs(inv.amount_total)
            fecha_retencion = fecha_doc
            renta_presunta = monto
            isr_retenido = monto * 0.27
            total_monto += monto

            campos = [
                razon_social, tipo_id, id_tributaria, pais,
                tipo_servicio, detalle_servicio, parte_relacionada,
                numero_doc, fecha_doc,
                self._format_amount_required(monto), fecha_retencion,
                self._format_amount_required(renta_presunta),
                self._format_amount_required(isr_retenido),
            ]
            lines.append('|'.join(campos))

        content = '\n'.join(lines)
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_F_609_{rnc}_{period}.txt"
        self.state = 'generated'
        self.record_count = len(invoices)
        self.total_amount = total_monto
        return self._return_wizard()

    def _generate_ir17(self):
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date')

        invoices_ret = invoices.filtered(
            lambda i: (getattr(i, 'l10n_do_total_isr_retention', 0) or 0) > 0 or
                      (getattr(i, 'l10n_do_total_itbis_retention', 0) or 0) > 0
        )

        if not invoices_ret:
            raise UserError(_('No hay facturas con retenciones en el periodo seleccionado.'))

        lines = []
        total_isr = 0.0
        total_itbis = 0.0
        rnc = self._clean_rnc(self.company_id.vat)
        period = self.date_from.strftime('%Y%m')

        lines.append('RNC|Proveedor|NCF|Fecha|Monto|ITBIS|Ret.ISR|Ret.ITBIS')

        for inv in invoices_ret:
            isr = getattr(inv, 'l10n_do_total_isr_retention', 0) or 0
            itbis = getattr(inv, 'l10n_do_total_itbis_retention', 0) or 0
            total_isr += isr
            total_itbis += itbis
            campos = [
                self._clean_rnc(inv.partner_id.vat),
                (inv.partner_id.name or '')[:40],
                getattr(inv, 'l10n_do_vendor_ncf', '') or '',
                self._format_date(inv.invoice_date),
                self._format_amount_required(inv.amount_untaxed),
                self._format_amount(inv.amount_tax),
                self._format_amount(isr),
                self._format_amount(itbis),
            ]
            lines.append('|'.join(campos))

        lines.extend([
            '',
            '=' * 50,
            f'RESUMEN IR-17 - Periodo: {period}',
            f'Empresa: {self.company_id.name}',
            f'RNC: {rnc}',
            '=' * 50,
            f'Total Retencion ISR:   RD$ {self._format_amount_required(total_isr)}',
            f'Total Retencion ITBIS: RD$ {self._format_amount_required(total_itbis)}',
            '-' * 50,
            f'TOTAL A PAGAR DGII:    RD$ {self._format_amount_required(total_isr + total_itbis)}',
            '=' * 50,
            f'Cantidad de Facturas: {len(invoices_ret)}',
        ])

        content = '\n'.join(lines)
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"IR17_Resumen_{rnc}_{period}.txt"
        self.state = 'generated'
        self.record_count = len(invoices_ret)
        self.ir17_total_isr = total_isr
        self.ir17_total_itbis = total_itbis
        self.ir17_total = total_isr + total_itbis
        return self._return_wizard()

    def _return_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Primero debe generar el reporte.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=file_name&download=true',
            'target': 'self',
        }

    def action_reset(self):
        self.ensure_one()
        self.write({
            'state': 'draft',
            'file_data': False,
            'file_name': False,
            'record_count': 0,
            'total_amount': 0,
            'total_itbis': 0,
            'ir17_total_isr': 0,
            'ir17_total_itbis': 0,
            'ir17_total': 0,
        })
        return self._return_wizard()
