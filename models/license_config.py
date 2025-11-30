# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class NCFLicenseConfig(models.Model):
    _name = 'l10n_do_ncf.license.config'
    _description = 'Configuracion de Licencia NCF'
    _rec_name = 'license_key'

    license_key = fields.Char(string='Clave de Licencia', required=True)
    company_rnc = fields.Char(string='RNC de la Empresa', required=True)
    company_id = fields.Many2one('res.company', string='Compania', required=True, default=lambda self: self.env.company)
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

    _sql_constraints = [
        ('unique_company_license', 'UNIQUE(company_id)', 'Ya existe una licencia para esta compania.')
    ]

    def action_validate_license(self):
        self.ensure_one()
        try:
            response = requests.post(
                "http://ncf-api:5000/api/v1/validate",
                json={'license_key': self.license_key, 'rnc': self.company_rnc, 'database': self.env.cr.dbname},
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
                'validation_message': data.get('message', ''),
            })
            if data.get('valid'):
                return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'Licencia Valida', 'message': 'Licencia activa. %s dias restantes.' % data.get('days_remaining', 0), 'type': 'success', 'sticky': False}}
            else:
                return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'Licencia Invalida', 'message': data.get('message', 'Error'), 'type': 'danger', 'sticky': True}}
        except Exception as e:
            self.write({'validation_message': str(e), 'last_validation': fields.Datetime.now()})
            raise UserError('No se pudo conectar al servidor de licencias.')

    @api.model
    def is_license_valid(self):
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            return False
        return config.is_valid
