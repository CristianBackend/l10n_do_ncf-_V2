# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from datetime import date
import io


class DgiiReportWizard(models.TransientModel):
    _name = 'l10n_do_ncf.dgii.report.wizard'
    _description = 'Wizard para Generar Reportes DGII'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    report_type = fields.Selection([
        ('606', '606 - Compras de Bienes y Servicios'),
        ('607', '607 - Ventas de Bienes y Servicios'),
        ('608', '608 - Comprobantes Anulados'),
        ('609', '609 - Pagos al Exterior'),
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
    
    # Campos para el archivo generado
    file_data = fields.Binary(string='Archivo', readonly=True)
    file_name = fields.Char(string='Nombre del Archivo', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
    ], default='draft')

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """Ajustar fecha hasta al fin del mes"""
        if self.date_from:
            # Calcular último día del mes
            if self.date_from.month == 12:
                last_day = self.date_from.replace(day=31)
            else:
                next_month = self.date_from.replace(month=self.date_from.month + 1, day=1)
                last_day = next_month.replace(day=1) - timedelta(days=1)
            self.date_to = last_day

    def action_generate_report(self):
        """Generar el reporte seleccionado"""
        self.ensure_one()
        
        if self.report_type == '606':
            return self._generate_606()
        elif self.report_type == '607':
            return self._generate_607()
        elif self.report_type == '608':
            return self._generate_608()
        elif self.report_type == '609':
            return self._generate_609()

    def _get_606_data(self):
        """Obtener datos para reporte 606 (Compras)"""
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ], order='invoice_date')
        
        return invoices

    def _get_607_data(self):
        """Obtener datos para reporte 607 (Ventas)"""
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('l10n_do_ncf_number', '!=', False),
        ], order='invoice_date')
        
        return invoices

    def _get_608_data(self):
        """Obtener datos para reporte 608 (Anulados)"""
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'cancel'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('l10n_do_ncf_number', '!=', False),
        ], order='invoice_date')
        
        return invoices

    def _generate_606(self):
        """Generar archivo 606"""
        invoices = self._get_606_data()
        
        # Generar contenido TXT
        lines = []
        
        # Encabezado
        rnc = (self.company_id.vat or '').replace('-', '')
        period = self.date_from.strftime('%Y%m')
        lines.append(f"606|{rnc}|{period}|{len(invoices)}")
        
        # Detalle
        for inv in invoices:
            rnc_supplier = (inv.partner_id.vat or '').replace('-', '')
            ncf = inv.l10n_do_vendor_ncf or ''
            amounts = inv._get_l10n_do_amounts()
            
            line = '|'.join([
                rnc_supplier,
                '1' if len(rnc_supplier) == 9 else '2',  # Tipo ID
                ncf,
                '',  # NCF modificado
                inv.invoice_date.strftime('%Y%m%d'),
                '',  # Fecha pago
                str(round(amounts['taxed_amount'], 2)),
                str(round(amounts['itbis_amount'], 2)),
                '',  # ITBIS retenido
                '',  # ITBIS sujeto proporcionalidad
                '',  # ITBIS llevado al costo
                '',  # ITBIS por adelantar
                '',  # ITBIS percibido compras
                inv.l10n_do_expense_type or '02',  # Tipo bienes/servicios
                '',  # ISR retenido
                '',  # ISC
                '',  # Otros impuestos
                '',  # Monto propina legal
                '01',  # Forma pago (efectivo por defecto)
            ])
            lines.append(line)
        
        content = '\n'.join(lines)
        
        # Crear archivo
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_606_{period}.txt"
        self.state = 'generated'
        
        return self._return_wizard()

    def _generate_607(self):
        """Generar archivo 607"""
        invoices = self._get_607_data()
        
        lines = []
        
        # Encabezado
        rnc = (self.company_id.vat or '').replace('-', '')
        period = self.date_from.strftime('%Y%m')
        lines.append(f"607|{rnc}|{period}|{len(invoices)}")
        
        # Detalle
        for inv in invoices:
            rnc_client = (inv.partner_id.vat or '').replace('-', '')
            ncf = inv.l10n_do_ncf_number or ''
            amounts = inv._get_l10n_do_amounts()
            
            # Tipo NCF
            ncf_type = '01'  # Default
            if inv.l10n_do_ncf_type_id:
                ncf_type = inv.l10n_do_ncf_type_id.code
            
            line = '|'.join([
                rnc_client or '000000000',
                '1' if len(rnc_client) == 9 else '2' if len(rnc_client) == 11 else '3',
                ncf,
                '',  # NCF modificado
                ncf_type,
                inv.invoice_date.strftime('%Y%m%d'),
                '',  # Fecha retención
                str(round(amounts['taxed_amount'], 2)),
                str(round(amounts['itbis_amount'], 2)),
                '',  # ITBIS retenido por terceros
                '',  # ITBIS percibido
                '',  # ISR percibido
                '',  # Impuesto selectivo consumo
                '',  # Otros impuestos/tasas
                '',  # Monto propina legal
                '01' if amounts['total_amount'] < 50000 else '02',  # Efectivo o transferencia
                str(round(amounts['exempt_amount'], 2)) if amounts['exempt_amount'] else '',
            ])
            lines.append(line)
        
        content = '\n'.join(lines)
        
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_607_{period}.txt"
        self.state = 'generated'
        
        return self._return_wizard()

    def _generate_608(self):
        """Generar archivo 608"""
        invoices = self._get_608_data()
        
        lines = []
        
        # Encabezado
        rnc = (self.company_id.vat or '').replace('-', '')
        period = self.date_from.strftime('%Y%m')
        lines.append(f"608|{rnc}|{period}|{len(invoices)}")
        
        # Detalle
        for inv in invoices:
            ncf = inv.l10n_do_ncf_number or ''
            
            # Tipo de anulación (por defecto: 02 - Deterioro)
            line = '|'.join([
                ncf,
                inv.invoice_date.strftime('%Y%m%d'),
                '02',  # Tipo anulación
            ])
            lines.append(line)
        
        content = '\n'.join(lines)
        
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_608_{period}.txt"
        self.state = 'generated'
        
        return self._return_wizard()

    def _generate_609(self):
        """Generar archivo 609"""
        invoices = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('l10n_do_fiscal_type', '=', 'exterior'),
        ], order='invoice_date')
        
        lines = []
        
        # Encabezado
        rnc = (self.company_id.vat or '').replace('-', '')
        period = self.date_from.strftime('%Y%m')
        lines.append(f"609|{rnc}|{period}|{len(invoices)}")
        
        # Detalle
        for inv in invoices:
            line = '|'.join([
                '01',  # Tipo bienes/servicios
                inv.invoice_date.strftime('%Y%m%d'),
                str(round(inv.amount_total, 2)),
                str(round(inv.amount_total * 0.27, 2)),  # Retención 27%
            ])
            lines.append(line)
        
        content = '\n'.join(lines)
        
        self.file_data = base64.b64encode(content.encode('utf-8'))
        self.file_name = f"DGII_609_{period}.txt"
        self.state = 'generated'
        
        return self._return_wizard()

    def _return_wizard(self):
        """Retornar la misma vista del wizard con el archivo generado"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        """Descargar el archivo generado"""
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Primero debe generar el reporte.'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=file_name&download=true',
            'target': 'self',
        }
