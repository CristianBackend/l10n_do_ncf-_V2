# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import re
from datetime import datetime


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_do_dgii_tax_payer_type = fields.Selection([
        ('taxpayer', 'Contribuyente'),
        ('non_taxpayer', 'No Contribuyente'),
        ('final_consumer', 'Consumidor Final'),
        ('special_regime', 'Regimen Especial'),
        ('governmental', 'Gubernamental'),
    ], string='Tipo de Contribuyente', default='final_consumer',
       help='Determina el tipo de NCF a generar automaticamente')

    l10n_do_rnc_validated = fields.Boolean(
        string='RNC Validado',
        default=False,
        help='Indica si el RNC fue validado contra DGII'
    )

    l10n_do_rnc_validation_date = fields.Datetime(
        string='Fecha de Validacion',
        readonly=True,
        help='Fecha en que se valido el RNC contra DGII'
    )

    l10n_do_dgii_status = fields.Char(
        string='Estado DGII',
        readonly=True,
        help='Estado del contribuyente en DGII'
    )

    l10n_do_dgii_activity = fields.Char(
        string='Actividad Economica',
        readonly=True,
        help='Actividad economica registrada en DGII'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'country_id' in fields_list:
            do_country = self.env['res.country'].search([('code', '=', 'DO')], limit=1)
            if do_country:
                res['country_id'] = do_country.id
        return res

    @api.onchange('vat')
    def _onchange_vat_dgii(self):
        """Auto-consultar DGII cuando se ingresa RNC/Cedula"""
        if self.vat:
            rnc = re.sub(r'[^0-9]', '', self.vat)
            if len(rnc) == 9 or len(rnc) == 11:
                self._consultar_rnc_dgii(rnc)
                self._auto_set_taxpayer_type(rnc)

    def _auto_set_taxpayer_type(self, rnc):
        """Asignar tipo de contribuyente automaticamente segun el RNC"""
        rnc_clean = re.sub(r'[^0-9]', '', rnc)

        if len(rnc_clean) == 11:
            # Cedula - persona fisica contribuyente
            if self.l10n_do_dgii_tax_payer_type not in ('special_regime', 'governmental'):
                self.l10n_do_dgii_tax_payer_type = 'taxpayer'
        elif len(rnc_clean) == 9:
            # RNC que empiezan con 4 son gubernamentales
            if rnc_clean.startswith('4'):
                self.l10n_do_dgii_tax_payer_type = 'governmental'
            elif self.l10n_do_dgii_tax_payer_type not in ('special_regime', 'governmental'):
                self.l10n_do_dgii_tax_payer_type = 'taxpayer'

    def _consultar_rnc_dgii(self, rnc):
        """Consultar RNC en la API de DGII"""
        try:
            url = f"http://ncf-api:5000/api/v1/rnc/{rnc}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('found'):
                    nombre_dgii = data.get('name', '')
                    if nombre_dgii and not self.name:
                        self.name = nombre_dgii
                    self.l10n_do_dgii_status = data.get('status', '')
                    self.l10n_do_dgii_activity = data.get('activity', '')
                    self.l10n_do_rnc_validated = True
                    self.l10n_do_rnc_validation_date = datetime.now()
                    return True
        except Exception:
            pass
        return False

    def action_validate_rnc(self):
        """Boton para validar RNC manualmente"""
        self.ensure_one()
        if not self.vat:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Debe ingresar un RNC/Cedula primero'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        rnc = re.sub(r'[^0-9]', '', self.vat)

        try:
            url = f"http://ncf-api:5000/api/v1/rnc/{rnc}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('found'):
                    vals = {
                        'l10n_do_dgii_status': data.get('status', ''),
                        'l10n_do_dgii_activity': data.get('activity', ''),
                        'l10n_do_rnc_validated': True,
                        'l10n_do_rnc_validation_date': datetime.now(),
                    }

                    nombre_dgii = data.get('name', '')
                    if nombre_dgii:
                        vals['name'] = nombre_dgii

                    # Auto-asignar tipo
                    if len(rnc) == 9 and rnc.startswith('4'):
                        vals['l10n_do_dgii_tax_payer_type'] = 'governmental'
                    elif data.get('status') == 'ACTIVO':
                        if self.l10n_do_dgii_tax_payer_type not in ('special_regime', 'governmental'):
                            vals['l10n_do_dgii_tax_payer_type'] = 'taxpayer'

                    self.write(vals)

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('RNC Validado'),
                            'message': _('Nombre: %s\nEstado: %s') % (
                                nombre_dgii,
                                data.get("status", "")
                            ),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('RNC No Encontrado'),
                            'message': _('El RNC no fue encontrado en DGII'),
                            'type': 'warning',
                            'sticky': False,
                        }
                    }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error conectando a DGII: %s') % str(e),
                    'type': 'danger',
                    'sticky': False,
                }
            }

    @api.model
    def create_quick_from_rnc(self, rnc, name=None, email=None):
        """Crear cliente rapido desde RNC - usado en facturacion rapida"""
        rnc_clean = re.sub(r'[^0-9]', '', rnc)

        # Buscar si ya existe
        existing = self.search(['|', ('vat', '=', rnc_clean), ('vat', '=', rnc)], limit=1)
        if existing:
            return existing

        vals = {
            'vat': rnc_clean,
            'name': name or f'Cliente {rnc_clean}',
            'is_company': len(rnc_clean) == 9,
            'l10n_do_dgii_tax_payer_type': 'final_consumer',
        }

        if email:
            vals['email'] = email

        try:
            url = f"http://ncf-api:5000/api/v1/rnc/{rnc_clean}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('found'):
                    vals['name'] = data.get('name', vals['name'])
                    vals['l10n_do_dgii_status'] = data.get('status', '')
                    vals['l10n_do_dgii_activity'] = data.get('activity', '')
                    vals['l10n_do_rnc_validated'] = True
                    vals['l10n_do_rnc_validation_date'] = datetime.now()

                    if data.get('status') == 'ACTIVO':
                        vals['l10n_do_dgii_tax_payer_type'] = 'taxpayer'

                    if len(rnc_clean) == 9 and rnc_clean.startswith('4'):
                        vals['l10n_do_dgii_tax_payer_type'] = 'governmental'
        except Exception:
            pass

        if len(rnc_clean) == 9:
            vals['is_company'] = True
        elif len(rnc_clean) == 11:
            vals['is_company'] = False

        return self.create(vals)

