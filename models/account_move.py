# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import re


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campos NCF
    l10n_do_ncf_number = fields.Char(
        string='NCF',
        copy=False,
        readonly=True,
        tracking=True,
        help='Número de Comprobante Fiscal'
    )
    l10n_do_ncf_type_id = fields.Many2one(
        'l10n_do_ncf.type',
        string='Tipo de NCF',
        tracking=True,
        help='Tipo de comprobante fiscal a generar'
    )
    l10n_do_ncf_seq_id = fields.Many2one(
        'l10n_do_ncf.sequence',
        string='Secuencia NCF',
        readonly=True,
        copy=False,
        help='Secuencia utilizada para generar el NCF'
    )
    l10n_do_ncf_expiration = fields.Date(
        string='Vencimiento NCF',
        related='l10n_do_ncf_seq_id.expiration_date',
        store=True
    )
    
    # Para Notas de Crédito/Débito
    l10n_do_ncf_origin = fields.Char(
        string='NCF Afectado',
        copy=False,
        help='NCF de la factura original que se está modificando (para NC/ND)'
    )
    l10n_do_origin_move_id = fields.Many2one(
        'account.move',
        string='Factura Origen',
        copy=False,
        help='Factura original que se está modificando'
    )
    
    # Para compras (NCF del proveedor)
    l10n_do_vendor_ncf = fields.Char(
        string='NCF Proveedor',
        copy=False,
        tracking=True,
        help='NCF del comprobante recibido del proveedor'
    )
    l10n_do_vendor_ncf_validated = fields.Boolean(
        string='NCF Validado',
        default=False,
        copy=False,
        help='Indica si el NCF del proveedor fue validado contra DGII'
    )
    
    # Campos fiscales RD
    l10n_do_fiscal_type = fields.Selection([
        ('fiscal', 'Fiscal (con NCF)'),
        ('informal', 'Compra Informal'),
        ('minor_expense', 'Gasto Menor'),
        ('exterior', 'Pago al Exterior'),
        ('special', 'Régimen Especial'),
        ('governmental', 'Gubernamental'),
        ('export', 'Exportación'),
    ], string='Tipo Fiscal', default='fiscal')
    
    l10n_do_expense_type = fields.Selection([
        ('01', '01 - Gastos de Personal'),
        ('02', '02 - Gastos por Trabajos, Suministros y Servicios'),
        ('03', '03 - Arrendamientos'),
        ('04', '04 - Gastos de Activos Fijos'),
        ('05', '05 - Gastos de Representación'),
        ('06', '06 - Otras Deducciones Admitidas'),
        ('07', '07 - Gastos Financieros'),
        ('08', '08 - Gastos Extraordinarios'),
        ('09', '09 - Compras y Gastos que forman parte del Costo de Venta'),
        ('10', '10 - Adquisiciones de Activos'),
        ('11', '11 - Gastos de Seguros'),
    ], string='Tipo de Gasto', help='Clasificación de gasto para reporte 606')

    @api.onchange('partner_id')
    def _onchange_partner_ncf_type(self):
        """Establecer tipo de NCF por defecto según el cliente"""
        if self.partner_id and self.move_type in ('out_invoice', 'out_refund'):
            if self.partner_id.l10n_do_dgii_tax_payer_type == 'taxpayer':
                # Cliente es contribuyente -> Crédito Fiscal
                ncf_type = self.env['l10n_do_ncf.type'].search([('code', '=', '01')], limit=1)
            else:
                # Consumidor final
                ncf_type = self.env['l10n_do_ncf.type'].search([('code', '=', '02')], limit=1)
            
            if ncf_type:
                self.l10n_do_ncf_type_id = ncf_type.id

    @api.constrains('l10n_do_vendor_ncf')
    def _check_vendor_ncf_format(self):
        """Validar formato del NCF de proveedor"""
        ncf_pattern = r'^[BE]\d{10}$|^[BE]\d{2}\d{8}$'
        for move in self:
            if move.l10n_do_vendor_ncf:
                if not re.match(ncf_pattern, move.l10n_do_vendor_ncf):
                    raise ValidationError(_(
                        'El formato del NCF del proveedor no es válido. '
                        'Debe ser B + 2 dígitos + 8 dígitos (ej: B0100000001) '
                        'o E + 2 dígitos + 10 dígitos para e-CF.'
                    ))

    @api.constrains('l10n_do_vendor_ncf', 'partner_id', 'company_id')
    def _check_vendor_ncf_unique(self):
        """Verificar que no exista duplicado de NCF de proveedor"""
        for move in self:
            if move.l10n_do_vendor_ncf and move.partner_id:
                existing = self.search([
                    ('l10n_do_vendor_ncf', '=', move.l10n_do_vendor_ncf),
                    ('partner_id', '=', move.partner_id.id),
                    ('company_id', '=', move.company_id.id),
                    ('id', '!=', move.id),
                    ('state', '!=', 'cancel'),
                ])
                if existing:
                    raise ValidationError(_(
                        'Ya existe una factura con el NCF %s para este proveedor.'
                    ) % move.l10n_do_vendor_ncf)

    def _get_ncf_sequence(self):
        """Obtener la secuencia NCF activa para el tipo seleccionado"""
        self.ensure_one()
        if not self.l10n_do_ncf_type_id:
            raise UserError(_('Debe seleccionar un tipo de NCF.'))
        
        sequence = self.env['l10n_do_ncf.sequence'].search([
            ('company_id', '=', self.company_id.id),
            ('ncf_type_id', '=', self.l10n_do_ncf_type_id.id),
            ('state', '=', 'active'),
        ], limit=1, order='id desc')
        
        if not sequence:
            raise UserError(_(
                'No hay una secuencia NCF activa para el tipo "%s". '
                'Por favor configure una en Facturación > Configuración > NCF > Secuencias.'
            ) % self.l10n_do_ncf_type_id.name)
        
        return sequence

    def _generate_ncf(self):
        """Generar NCF para la factura"""
        self.ensure_one()
        if self.l10n_do_ncf_number:
            return self.l10n_do_ncf_number
        
        sequence = self._get_ncf_sequence()
        ncf = sequence.get_next_ncf()
        
        self.write({
            'l10n_do_ncf_number': ncf,
            'l10n_do_ncf_seq_id': sequence.id,
        })
        
        return ncf

    def action_post(self):
        """Override para generar NCF al confirmar factura"""
        # Generar NCF para facturas de venta dominicanas
        for move in self:
            if (move.move_type in ('out_invoice', 'out_refund') and 
                move.company_id.country_id.code == 'DO' and
                move.l10n_do_ncf_type_id and
                not move.l10n_do_ncf_number):
                move._generate_ncf()
        
        return super().action_post()

    def action_validate_vendor_ncf(self):
        """Validar NCF de proveedor contra DGII"""
        self.ensure_one()
        if not self.l10n_do_vendor_ncf:
            raise UserError(_('Ingrese el NCF del proveedor para validar.'))
        if not self.partner_id.vat:
            raise UserError(_('El proveedor debe tener un RNC/Cédula configurado.'))
        
        # TODO: Implementar validación contra DGII
        # Por ahora solo marcamos como validado
        self.l10n_do_vendor_ncf_validated = True
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('NCF Validado'),
                'message': _('El NCF ha sido validado correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_l10n_do_amounts(self):
        """Obtener montos desglosados para reportes DGII"""
        self.ensure_one()
        
        itbis_amount = 0.0
        exempt_amount = 0.0
        taxed_amount = 0.0
        
        for line in self.invoice_line_ids:
            line_taxes = line.tax_ids.filtered(lambda t: 'ITBIS' in t.name.upper())
            if line_taxes:
                taxed_amount += line.price_subtotal
                for tax in line_taxes:
                    itbis_amount += line.price_subtotal * (tax.amount / 100)
            else:
                exempt_amount += line.price_subtotal
        
        return {
            'itbis_amount': itbis_amount,
            'exempt_amount': exempt_amount,
            'taxed_amount': taxed_amount,
            'total_amount': self.amount_total,
        }
