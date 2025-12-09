# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import re


class NCFSetupWizard(models.TransientModel):
    _name = 'l10n_do_ncf.setup.wizard'
    _description = 'Wizard de Configuracion Inicial NCF'

    # Control de pasos
    state = fields.Selection([
        ('step1', 'Datos Empresa'),
        ('step2', 'Secuencias NCF'),
        ('step3', 'Notificaciones'),
        ('done', 'Completado'),
    ], default='step1', string='Paso')

    # Campo para controlar si se puede avanzar
    can_proceed = fields.Boolean(compute='_compute_can_proceed', store=False)
    is_already_configured = fields.Boolean(compute='_compute_is_already_configured', store=False)

    # ===== PASO 1: Datos Empresa =====
    company_id = fields.Many2one('res.company', string='Empresa',
                                  default=lambda self: self.env.company)
    company_rnc = fields.Char(string='RNC de la Empresa', size=11,
                              help='RNC sin guiones, solo numeros')
    company_name_dgii = fields.Char(string='Nombre segun DGII')
    rnc_validated = fields.Boolean(string='RNC Validado', default=False)

    # ===== PASO 2: Secuencias NCF =====
    create_b01 = fields.Boolean(string='B01 - Credito Fiscal', default=True,
                                help='Para clientes con RNC que requieren credito fiscal')
    b01_start = fields.Integer(string='Inicio B01', default=1)
    b01_end = fields.Integer(string='Fin B01', default=500)

    create_b02 = fields.Boolean(string='B02 - Consumidor Final', default=True,
                                help='Para ventas a consumidores sin RNC')
    b02_start = fields.Integer(string='Inicio B02', default=1)
    b02_end = fields.Integer(string='Fin B02', default=1000)

    create_b14 = fields.Boolean(string='B14 - Regimen Especial', default=False,
                                help='Para zonas francas y regimenes especiales')
    b14_start = fields.Integer(string='Inicio B14', default=1)
    b14_end = fields.Integer(string='Fin B14', default=100)

    create_b15 = fields.Boolean(string='B15 - Gubernamental', default=False,
                                help='Para ventas al gobierno')
    b15_start = fields.Integer(string='Inicio B15', default=1)
    b15_end = fields.Integer(string='Fin B15', default=100)

    # ===== PASO 3: Notificaciones =====
    enable_alerts = fields.Boolean(string='Activar Alertas por Email', default=True)
    alert_email = fields.Char(string='Email para Alertas')
    low_stock_threshold = fields.Integer(string='Alertar cuando queden', default=50,
                                         help='NCF disponibles')

    @api.depends('state', 'company_rnc', 'rnc_validated', 'create_b01', 'create_b02', 'create_b14', 'create_b15')
    def _compute_can_proceed(self):
        """Determinar si se puede avanzar al siguiente paso"""
        for wizard in self:
            if wizard.state == 'step1':
                # Paso 1: Debe tener RNC ingresado
                wizard.can_proceed = bool(wizard.company_rnc and len(wizard.company_rnc) >= 9)
            elif wizard.state == 'step2':
                # Paso 2: Debe tener al menos un tipo de NCF seleccionado
                wizard.can_proceed = wizard.create_b01 or wizard.create_b02 or wizard.create_b14 or wizard.create_b15
            elif wizard.state == 'step3':
                # Paso 3: Siempre puede avanzar
                wizard.can_proceed = True
            else:
                wizard.can_proceed = False

    @api.depends('company_id')
    def _compute_is_already_configured(self):
        """Verificar si ya existe configuracion"""
        for wizard in self:
            NCFSequence = self.env['l10n_do_ncf.sequence']
            existing = NCFSequence.search([
                ('company_id', '=', wizard.company_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            wizard.is_already_configured = bool(existing)

    def _reload_wizard(self):
        """Recargar el wizard para mostrar cambios"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_validate_rnc(self):
        """Validar RNC en DGII usando la API interna"""
        self.ensure_one()

        if not self.company_rnc:
            raise UserError(_('Ingrese el RNC de la empresa'))

        rnc = re.sub(r'[^0-9]', '', self.company_rnc)

        if len(rnc) not in [9, 11]:
            raise UserError(_('El RNC debe tener 9 u 11 digitos'))

        try:
            url = f"http://ncf-api:5000/api/v1/rnc/{rnc}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('found'):
                    self.company_name_dgii = data.get('name', 'Validado')
                    self.rnc_validated = True
                    self.company_id.write({'vat': rnc})
                    return self._reload_wizard()
                else:
                    raise UserError(_('RNC no encontrado en DGII'))
            else:
                raise UserError(_('Error consultando DGII. Codigo: %s') % response.status_code)

        except requests.exceptions.RequestException as e:
            raise UserError(_('Error de conexion: %s') % str(e))

    def action_next(self):
        """Ir al siguiente paso"""
        self.ensure_one()

        if self.state == 'step1':
            if not self.company_rnc:
                raise UserError(_('Debe ingresar el RNC de la empresa'))
            rnc = re.sub(r'[^0-9]', '', self.company_rnc)
            if len(rnc) not in [9, 11]:
                raise UserError(_('El RNC debe tener 9 u 11 digitos'))
            self.state = 'step2'

        elif self.state == 'step2':
            if not (self.create_b01 or self.create_b02 or self.create_b14 or self.create_b15):
                raise UserError(_('Debe seleccionar al menos un tipo de comprobante'))
            self._create_sequences()
            self.state = 'step3'

        elif self.state == 'step3':
            self._setup_notifications()
            self.state = 'done'

        return self._reload_wizard()

    def action_previous(self):
        """Volver al paso anterior"""
        self.ensure_one()

        if self.state == 'step2':
            self.state = 'step1'
        elif self.state == 'step3':
            self.state = 'step2'

        return self._reload_wizard()

    def _create_sequences(self):
        """Crear las secuencias NCF seleccionadas"""
        NCFSequence = self.env['l10n_do_ncf.sequence']
        NCFType = self.env['l10n_do_ncf.type']

        # (campo_crear, codigo_tipo_dgii, campo_inicio, campo_fin)
        sequences_config = [
            ('create_b01', '01', 'b01_start', 'b01_end'),
            ('create_b02', '02', 'b02_start', 'b02_end'),
            ('create_b14', '14', 'b14_start', 'b14_end'),
            ('create_b15', '15', 'b15_start', 'b15_end'),
        ]

        for create_field, type_code, start_field, end_field in sequences_config:
            if getattr(self, create_field):
                # Buscar el tipo NCF por su codigo (01, 02, 14, 15)
                ncf_type = NCFType.search([('code', '=', type_code)], limit=1)
                if ncf_type:
                    # Verificar si ya existe una secuencia con este tipo
                    existing = NCFSequence.search([
                        ('ncf_type_id', '=', ncf_type.id),
                        ('company_id', '=', self.company_id.id),
                    ], limit=1)

                    if not existing:
                        new_seq = NCFSequence.create({
                            'ncf_type_id': ncf_type.id,
                            'range_from': getattr(self, start_field),
                            'range_to': getattr(self, end_field),
                            'company_id': self.company_id.id,
                        })
                        new_seq.action_activate()

    def _setup_notifications(self):
        """Configurar alertas"""
        if self.enable_alerts:
            AlertConfig = self.env['l10n_do_ncf.alert.config']
            alert_config = AlertConfig.search([], limit=1)

            if not alert_config:
                alert_vals = {
                    'alert_low_stock': True,
                    'low_stock_threshold': self.low_stock_threshold,
                    'alert_expiring': True,
                    'expiring_days': 30,
                }

                if self.alert_email:
                    user = self.env['res.users'].search([
                        '|',
                        ('login', '=', self.alert_email),
                        ('email', '=', self.alert_email),
                    ], limit=1)
                    if user:
                        alert_vals['alert_email_ids'] = [(4, user.id)]

                AlertConfig.create(alert_vals)

    def action_finish(self):
        """Cerrar wizard y mostrar dashboard"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuracion Completada'),
                'message': _('El modulo NCF ha sido configurado exitosamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def action_open_setup_wizard(self):
        """Abrir el wizard de configuracion"""
        # Verificar si ya esta configurado
        NCFSequence = self.env['l10n_do_ncf.sequence']
        existing = NCFSequence.search([
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'active'),
        ], limit=1)

        if existing:
            raise UserError(_('El modulo NCF ya esta configurado para esta empresa. Si necesita agregar mas secuencias, vaya a Configuracion > Secuencias NCF.'))

        wizard = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Configuracion Inicial NCF'),
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
