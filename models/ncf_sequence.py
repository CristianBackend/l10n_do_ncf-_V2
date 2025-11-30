# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import date
from dateutil.relativedelta import relativedelta


class NcfSequence(models.Model):
    _name = 'l10n_do_ncf.sequence'
    _description = 'Secuencia de Comprobantes Fiscales NCF'
    _order = 'ncf_type_id, id desc'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    ncf_type_id = fields.Many2one(
        'l10n_do_ncf.type',
        string='Tipo de NCF',
        required=True,
        ondelete='restrict'
    )
    prefix = fields.Char(
        string='Prefijo',
        related='ncf_type_id.prefix',
        store=True
    )
    range_from = fields.Integer(
        string='Desde',
        required=True,
        default=1,
        help='Número inicial de la secuencia autorizada'
    )
    range_to = fields.Integer(
        string='Hasta',
        required=True,
        help='Número final de la secuencia autorizada'
    )
    current_number = fields.Integer(
        string='Número Actual',
        required=True,
        default=0,
        help='Último número utilizado'
    )
    next_number = fields.Integer(
        string='Próximo Número',
        compute='_compute_next_number'
    )
    available_qty = fields.Integer(
        string='Disponibles',
        compute='_compute_available_qty'
    )
    expiration_date = fields.Date(
        string='Fecha de Vencimiento',
        compute='_compute_expiration_date',
        store=True,
        readonly=False,
        help='Fecha de vencimiento de la secuencia. Se calcula automáticamente según el tipo de NCF.'
    )
    authorization_date = fields.Date(
        string='Fecha de Autorización',
        required=True,
        default=fields.Date.today,
        help='Fecha en que la DGII autorizó esta secuencia'
    )
    aplica_vencimiento = fields.Boolean(
        string='Aplica Vencimiento',
        related='ncf_type_id.aplica_vencimiento',
        store=True,
        help='Indica si este tipo de NCF está sujeto a vencimiento'
    )
    warning_threshold = fields.Integer(
        string='Umbral de Alerta',
        default=50,
        help='Alertar cuando queden menos de esta cantidad'
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('depleted', 'Agotada'),
        ('expired', 'Vencida'),
    ], string='Estado', default='draft', compute='_compute_state', store=True)
    active = fields.Boolean(
        string='Activo',
        default=True
    )

    @api.depends('ncf_type_id', 'range_from', 'range_to')
    def _compute_name(self):
        for record in self:
            if record.ncf_type_id:
                record.name = f"{record.ncf_type_id.prefix} ({record.range_from}-{record.range_to})"
            else:
                record.name = "Nueva Secuencia"

    @api.depends('current_number')
    def _compute_next_number(self):
        for record in self:
            if record.current_number == 0:
                record.next_number = record.range_from
            else:
                record.next_number = record.current_number + 1

    @api.depends('range_to', 'current_number')
    def _compute_available_qty(self):
        for record in self:
            if record.current_number == 0:
                record.available_qty = record.range_to - record.range_from + 1
            else:
                record.available_qty = record.range_to - record.current_number

    @api.depends('authorization_date', 'ncf_type_id', 'ncf_type_id.aplica_vencimiento', 'ncf_type_id.vigencia_anos')
    def _compute_expiration_date(self):
        """
        Calcula la fecha de vencimiento según las reglas de DGII:
        
        - Para tipos CON vencimiento: 31 de diciembre del año siguiente al de autorización
          (Norma General 06-2018, Art. 6: "hasta dos años calendario")
        
        - Para tipos SIN vencimiento (B02, B04, B12 y sus electrónicos): Sin fecha
          (Según Guía del Contribuyente No. 5 - DGII Mayo 2022)
        """
        for record in self:
            if not record.ncf_type_id or not record.authorization_date:
                record.expiration_date = False
                continue
            
            if record.ncf_type_id.aplica_vencimiento:
                # Vence el 31 de diciembre del año siguiente
                # Ejemplo: Autorizado en 2025 → Vence 31/12/2026
                auth_year = record.authorization_date.year
                vigencia = record.ncf_type_id.vigencia_anos or 2
                expiry_year = auth_year + (vigencia - 1)  # -1 porque incluye el año actual
                record.expiration_date = date(expiry_year, 12, 31)
            else:
                # No aplica vencimiento (B02, B04, B12 y electrónicos E32, E34)
                record.expiration_date = False

    @api.depends('current_number', 'range_to', 'expiration_date', 'aplica_vencimiento')
    def _compute_state(self):
        today = date.today()
        for record in self:
            # Solo verificar vencimiento si aplica
            if record.aplica_vencimiento and record.expiration_date and record.expiration_date < today:
                record.state = 'expired'
            elif record.current_number >= record.range_to:
                record.state = 'depleted'
            elif record.current_number > 0 or record.state == 'active':
                record.state = 'active'
            else:
                record.state = 'draft'

    @api.constrains('range_from', 'range_to')
    def _check_range(self):
        for record in self:
            if record.range_from <= 0:
                raise ValidationError(_('El rango inicial debe ser mayor a 0.'))
            if record.range_to <= record.range_from:
                raise ValidationError(_('El rango final debe ser mayor al rango inicial.'))

    @api.constrains('expiration_date', 'aplica_vencimiento')
    def _check_expiration_date(self):
        for record in self:
            # Solo validar si aplica vencimiento y tiene fecha
            if record.aplica_vencimiento and record.expiration_date:
                if record.expiration_date < date.today():
                    raise ValidationError(_('La fecha de vencimiento no puede ser en el pasado.'))

    def action_activate(self):
        """Activar la secuencia"""
        for record in self:
            if record.state == 'draft':
                record.state = 'active'

    def get_next_ncf(self):
        """Obtener el próximo NCF disponible"""
        self.ensure_one()
        
        # Validar estado
        if self.state == 'expired':
            raise UserError(_('Esta secuencia de NCF ha vencido.'))
        if self.state == 'depleted':
            raise UserError(_('Esta secuencia de NCF se ha agotado.'))
        if self.state == 'draft':
            raise UserError(_('Esta secuencia de NCF no está activa.'))
        
        # Verificar vencimiento solo si aplica
        if self.aplica_vencimiento and self.expiration_date and self.expiration_date < date.today():
            raise UserError(_('Esta secuencia de NCF ha vencido el %s.') % self.expiration_date.strftime('%d/%m/%Y'))
        
        # Calcular próximo número
        if self.current_number == 0:
            next_num = self.range_from
        else:
            next_num = self.current_number + 1
        
        # Validar que no exceda el rango
        if next_num > self.range_to:
            raise UserError(_('Se ha agotado la secuencia de NCF. Solicite una nueva a la DGII.'))
        
        # Generar NCF completo
        if self.ncf_type_id.is_electronic:
            # e-NCF: E + 2 dígitos tipo + 10 dígitos secuencia = 13 caracteres
            ncf = f"{self.prefix}{str(next_num).zfill(10)}"
        else:
            # NCF físico: B + 2 dígitos tipo + 8 dígitos secuencia = 11 caracteres
            ncf = f"{self.prefix}{str(next_num).zfill(8)}"
        
        # Actualizar número actual
        self.current_number = next_num
        
        # Verificar umbral de alerta
        if self.available_qty <= self.warning_threshold:
            # TODO: Enviar notificación de alerta
            pass
        
        return ncf

    def action_view_invoices(self):
        """Ver facturas que usan esta secuencia"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('l10n_do_ncf_seq_id', '=', self.id)],
            'context': {'default_l10n_do_ncf_seq_id': self.id},
        }
