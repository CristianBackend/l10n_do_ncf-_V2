# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class L10nDoRetentionType(models.Model):
    _name = 'l10n_do_ncf.retention.type'
    _description = 'Tipos de Retencion RD'
    _order = 'sequence, code'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Codigo', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    retention_type = fields.Selection([
        ('isr', 'ISR - Impuesto Sobre la Renta'),
        ('itbis', 'ITBIS'),
    ], string='Tipo de Impuesto', required=True)

    rate = fields.Float(string='Tasa (%)', required=True,
                        help='Porcentaje de retencion')

    apply_on = fields.Selection([
        ('base', 'Sobre el monto base (sin ITBIS)'),
        ('itbis', 'Sobre el ITBIS facturado'),
    ], string='Aplicar sobre', default='base', required=True)

    partner_type = fields.Selection([
        ('all', 'Todos'),
        ('person', 'Solo Personas Fisicas'),
        ('company', 'Solo Empresas'),
    ], string='Aplica a', default='all')

    description = fields.Text(string='Descripcion',
                              help='Normativa o base legal')
    active = fields.Boolean(default=True)

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            existing = self.search([
                ('code', '=', record.code),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(_('El codigo de retencion debe ser unico'))


class AccountMoveRetention(models.Model):
    _name = 'l10n_do_ncf.move.retention'
    _description = 'Retenciones de Factura'

    move_id = fields.Many2one('account.move', string='Factura',
                              required=True, ondelete='cascade')
    retention_type_id = fields.Many2one('l10n_do_ncf.retention.type',
                                        string='Tipo de Retencion', required=True)

    base_amount = fields.Monetary(string='Monto Base', currency_field='currency_id')
    rate = fields.Float(string='Tasa (%)', related='retention_type_id.rate', store=True)
    retention_amount = fields.Monetary(string='Monto Retenido',
                                       compute='_compute_retention_amount',
                                       store=True, currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', related='move_id.currency_id')
    company_id = fields.Many2one('res.company', related='move_id.company_id')

    @api.depends('base_amount', 'rate')
    def _compute_retention_amount(self):
        for rec in self:
            rec.retention_amount = rec.base_amount * (rec.rate / 100)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campo simplificado: Tipo de Servicio
    l10n_do_service_type = fields.Selection([
        ('none', 'Sin Retencion'),
        ('professional', 'Servicios Profesionales (10% ISR + 30% ITBIS)'),
        ('technical', 'Servicios Tecnicos (2% ISR)'),
        ('rent_person', 'Alquiler Persona Fisica (10% ISR)'),
        ('goods', 'Compra de Bienes (Sin Retencion)'),
        ('manual', 'Configuracion Manual'),
    ], string='Tipo de Servicio', default='none',
       help='Seleccione el tipo de servicio para calcular retenciones automaticamente')

    # Retenciones
    l10n_do_retention_ids = fields.One2many(
        'l10n_do_ncf.move.retention', 'move_id',
        string='Retenciones',
        help='Retenciones aplicadas a esta factura'
    )

    l10n_do_total_isr_retention = fields.Monetary(
        string='Retencion ISR',
        compute='_compute_retention_totals',
        store=True,
        currency_field='currency_id'
    )

    l10n_do_total_itbis_retention = fields.Monetary(
        string='Retencion ITBIS',
        compute='_compute_retention_totals',
        store=True,
        currency_field='currency_id'
    )

    l10n_do_amount_to_pay = fields.Monetary(
        string='Monto a Pagar',
        compute='_compute_retention_totals',
        store=True,
        currency_field='currency_id',
        help='Total factura menos retenciones'
    )

    @api.depends('l10n_do_retention_ids', 'l10n_do_retention_ids.retention_amount', 'amount_total')
    def _compute_retention_totals(self):
        for move in self:
            isr_total = 0.0
            itbis_total = 0.0

            for ret in move.l10n_do_retention_ids:
                if ret.retention_type_id.retention_type == 'isr':
                    isr_total += ret.retention_amount
                elif ret.retention_type_id.retention_type == 'itbis':
                    itbis_total += ret.retention_amount

            move.l10n_do_total_isr_retention = isr_total
            move.l10n_do_total_itbis_retention = itbis_total
            move.l10n_do_amount_to_pay = move.amount_total - isr_total - itbis_total

    @api.onchange('l10n_do_service_type')
    def _onchange_service_type(self):
        """Calcular retenciones automaticamente al cambiar tipo de servicio"""
        if self.move_type not in ('in_invoice', 'in_refund'):
            return

        if self.l10n_do_service_type in ('none', 'goods', 'manual'):
            return

        # Limpiar retenciones anteriores
        self.l10n_do_retention_ids = [(5, 0, 0)]

        retentions = []
        base = self.amount_untaxed or 0
        itbis = self.amount_tax or 0

        if self.l10n_do_service_type == 'professional':
            # 10% ISR sobre base + 30% sobre ITBIS
            if base > 0:
                retentions.append((0, 0, {
                    'retention_type_id': self._get_retention_type('ISR_PROF'),
                    'base_amount': base,
                }))
            if itbis > 0:
                retentions.append((0, 0, {
                    'retention_type_id': self._get_retention_type('ITBIS_PROF'),
                    'base_amount': itbis,
                }))

        elif self.l10n_do_service_type == 'technical':
            # 2% ISR sobre base
            if base > 0:
                retentions.append((0, 0, {
                    'retention_type_id': self._get_retention_type('ISR_TEC'),
                    'base_amount': base,
                }))

        elif self.l10n_do_service_type == 'rent_person':
            # 10% ISR sobre base
            if base > 0:
                retentions.append((0, 0, {
                    'retention_type_id': self._get_retention_type('ISR_ALQ'),
                    'base_amount': base,
                }))

        if retentions:
            self.l10n_do_retention_ids = retentions

    def _get_retention_type(self, code):
        """Obtener ID del tipo de retencion por codigo"""
        retention = self.env['l10n_do_ncf.retention.type'].search([('code', '=', code)], limit=1)
        return retention.id if retention else False

    def action_add_retention(self):
        """Abrir wizard para agregar retencion manual"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Agregar Retencion'),
            'res_model': 'l10n_do_ncf.retention.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_base_amount': self.amount_untaxed,
                'default_itbis_amount': self.amount_tax,
            }
        }

    def action_clear_retentions(self):
        """Limpiar todas las retenciones"""
        self.ensure_one()
        self.l10n_do_retention_ids.unlink()
        self.l10n_do_service_type = 'none'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Retenciones Eliminadas'),
                'message': _('Se eliminaron todas las retenciones'),
                'type': 'success',
                'sticky': False,
            }
        }


class RetentionWizard(models.TransientModel):
    _name = 'l10n_do_ncf.retention.wizard'
    _description = 'Wizard para Agregar Retencion'

    move_id = fields.Many2one('account.move', string='Factura', required=True)
    retention_type_id = fields.Many2one('l10n_do_ncf.retention.type',
                                        string='Tipo de Retencion', required=True)

    base_amount = fields.Float(string='Monto Base Factura')
    itbis_amount = fields.Float(string='ITBIS Factura')

    apply_on = fields.Selection(related='retention_type_id.apply_on')
    rate = fields.Float(related='retention_type_id.rate')

    amount_to_retain = fields.Float(string='Monto a Aplicar',
                                    compute='_compute_amount_to_retain')
    retention_amount = fields.Float(string='Retencion Calculada',
                                    compute='_compute_retention_amount')

    @api.depends('retention_type_id', 'base_amount', 'itbis_amount')
    def _compute_amount_to_retain(self):
        for rec in self:
            if rec.retention_type_id:
                if rec.retention_type_id.apply_on == 'base':
                    rec.amount_to_retain = rec.base_amount
                else:
                    rec.amount_to_retain = rec.itbis_amount
            else:
                rec.amount_to_retain = 0

    @api.depends('amount_to_retain', 'rate')
    def _compute_retention_amount(self):
        for rec in self:
            rec.retention_amount = rec.amount_to_retain * (rec.rate / 100)

    def action_add(self):
        """Agregar la retencion a la factura"""
        self.ensure_one()

        self.env['l10n_do_ncf.move.retention'].create({
            'move_id': self.move_id.id,
            'retention_type_id': self.retention_type_id.id,
            'base_amount': self.amount_to_retain,
        })

        # Cambiar a modo manual
        self.move_id.l10n_do_service_type = 'manual'

        return {'type': 'ir.actions.act_window_close'}
