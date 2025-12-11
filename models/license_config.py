k# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import logging

_logger = logging.getLogger(__name__)


class NCFLicenseConfig(models.Model):
    _name = 'l10n_do_ncf.license.config'
    _description = 'Configuracion de Licencia NCF'
    _rec_name = 'license_key'

    license_key = fields.Char(string='Clave de Licencia', required=True)
    company_rnc = fields.Char(string='RNC de la Empresa', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )
    is_valid = fields.Boolean(string='Licencia Valida', default=False, readonly=True)
    status = fields.Selection([
        ('pending', 'Pendiente'),
        ('active', 'Activa'),
        ('grace_period', 'Periodo de Gracia'),
        ('expired', 'Expirada'),
        ('invalid', 'Invalida'),
        ('blocked', 'Bloqueada'),
    ], string='Estado', default='pending', readonly=True)
    licensed_company_name = fields.Char(string='Empresa Licenciada', readonly=True)
    days_remaining = fields.Integer(string='Dias Restantes', readonly=True)
    expiration_date = fields.Date(string='Fecha de Vencimiento', readonly=True)
    last_validation = fields.Datetime(string='Ultima Validacion', readonly=True)
    validation_message = fields.Text(string='Mensaje', readonly=True)

    @api.constrains('company_id')
    def _check_unique_company_license(self):
        for record in self:
            existing = self.search([
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(_('Ya existe una licencia para esta compania.'))

    def action_validate_license(self):
        """Validar licencia contra el servidor"""
        self.ensure_one()
        try:
            response = requests.post(
                "https://node-a1.newplain.com/api/validate.php",
                json={
                    'license_key': self.license_key,
                    'rnc': self.company_rnc,
                    'database': self.env.cr.dbname
                },
                timeout=10
            )
            data = response.json()

            self.write({
                'is_valid': data.get('valid', False),
                'status': data.get('status', 'invalid'),
                'licensed_company_name': data.get('company_name', ''),
                'days_remaining': data.get('days_remaining', 0),
                'expiration_date': data.get('expiration_date', False),
                'last_validation': fields.Datetime.now(),
                'validation_message': '' if data.get('valid') else data.get('message', ''),
            })

            if data.get('valid'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Licencia Valida'),
                        'message': _('Licencia activa. %s dias restantes.') % data.get('days_remaining', 0),
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Licencia Invalida'),
                        'message': data.get('message', 'Error de validacion'),
                        'type': 'danger',
                        'sticky': True,
                        'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                    }
                }

        except requests.exceptions.RequestException as e:
            _logger.error('Error conectando al servidor de licencias: %s', str(e))
            self.write({
                'validation_message': 'Error de conexion: ' + str(e),
                'last_validation': fields.Datetime.now(),
                'status': 'invalid',
                'is_valid': False,
            })
            raise UserError(_('No se pudo conectar al servidor de licencias. Verifique su conexion a internet.'))

    def action_buy_license(self):
        """Abrir pagina de compra/renovacion de licencia"""
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://node-a1.newplain.com/buy/',
            'target': 'new',
        }

    @api.model
    def is_license_valid(self):
        """Verificar si la licencia de la compania actual es valida"""
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            return False
        return config.is_valid

    @api.model
    def get_or_create_config(self):
        """Obtener o crear configuracion de licencia para la compania actual"""
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            config = self.create({
                'license_key': '',
                'company_rnc': self.env.company.vat or '',
                'company_id': self.env.company.id,
            })
        return config
