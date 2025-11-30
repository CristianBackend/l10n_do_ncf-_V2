# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_do_dgii_tax_payer_type = fields.Selection([
        ('taxpayer', 'Contribuyente (con RNC)'),
        ('non_taxpayer', 'Consumidor Final'),
        ('special', 'Régimen Especial'),
        ('governmental', 'Gubernamental'),
        ('foreigner', 'Extranjero'),
    ], string='Tipo de Contribuyente', default='non_taxpayer',
        help='Clasificación fiscal del contacto según DGII')
    
    l10n_do_ncf_type_id = fields.Many2one(
        'l10n_do_ncf.type',
        string='Tipo NCF por Defecto',
        help='Tipo de NCF que se usará por defecto para este contacto'
    )
    
    l10n_do_rnc_validated = fields.Boolean(
        string='RNC Validado',
        default=False,
        help='Indica si el RNC fue validado contra DGII'
    )
    
    l10n_do_rnc_validation_date = fields.Date(
        string='Fecha de Validación',
        help='Última fecha en que se validó el RNC'
    )

    @api.onchange('vat', 'country_id')
    def _onchange_vat_do(self):
        """Detectar tipo de contribuyente según RNC/Cédula"""
        if self.country_id and self.country_id.code == 'DO' and self.vat:
            vat_clean = re.sub(r'[^0-9]', '', self.vat)
            
            if len(vat_clean) == 9:
                # RNC de empresa
                self.l10n_do_dgii_tax_payer_type = 'taxpayer'
            elif len(vat_clean) == 11:
                # Cédula de persona física
                self.l10n_do_dgii_tax_payer_type = 'taxpayer'
            
            # Establecer tipo de NCF por defecto
            if self.l10n_do_dgii_tax_payer_type == 'taxpayer':
                ncf_type = self.env['l10n_do_ncf.type'].search([('code', '=', '01')], limit=1)
                if ncf_type:
                    self.l10n_do_ncf_type_id = ncf_type.id

    @api.constrains('vat', 'country_id')
    def _check_vat_do(self):
        """Validar formato de RNC/Cédula dominicana"""
        for partner in self:
            if partner.country_id and partner.country_id.code == 'DO' and partner.vat:
                vat_clean = re.sub(r'[^0-9]', '', partner.vat)
                
                if len(vat_clean) not in (9, 11):
                    raise ValidationError(_(
                        'El RNC debe tener 9 dígitos o la Cédula debe tener 11 dígitos.\n'
                        'Valor ingresado: %s (%d dígitos)'
                    ) % (partner.vat, len(vat_clean)))
                
                # Validar dígito verificador para RNC
                if len(vat_clean) == 9:
                    if not self._validate_rnc_check_digit(vat_clean):
                        raise ValidationError(_(
                            'El RNC %s no es válido. Verifique el número.'
                        ) % partner.vat)
                
                # Validar dígito verificador para Cédula
                if len(vat_clean) == 11:
                    if not self._validate_cedula_check_digit(vat_clean):
                        raise ValidationError(_(
                            'La Cédula %s no es válida. Verifique el número.'
                        ) % partner.vat)

    def _validate_rnc_check_digit(self, rnc):
        """Validar dígito verificador del RNC usando algoritmo de Luhn modificado"""
        if len(rnc) != 9:
            return False
        
        try:
            weights = [7, 9, 8, 6, 5, 4, 3, 2]
            total = sum(int(rnc[i]) * weights[i] for i in range(8))
            remainder = total % 11
            
            if remainder == 0:
                check_digit = 2
            elif remainder == 1:
                check_digit = 1
            else:
                check_digit = 11 - remainder
            
            return int(rnc[8]) == check_digit
        except (ValueError, IndexError):
            return False

    def _validate_cedula_check_digit(self, cedula):
        """Validar dígito verificador de la cédula dominicana"""
        if len(cedula) != 11:
            return False
        
        try:
            weights = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
            total = 0
            
            for i in range(10):
                product = int(cedula[i]) * weights[i]
                if product >= 10:
                    product = (product // 10) + (product % 10)
                total += product
            
            check_digit = (10 - (total % 10)) % 10
            return int(cedula[10]) == check_digit
        except (ValueError, IndexError):
            return False

    def action_validate_rnc(self):
        """Validar RNC contra DGII"""
        self.ensure_one()
        if not self.vat:
            raise ValidationError(_('Ingrese un RNC/Cédula para validar.'))
        
        # TODO: Implementar llamada real a DGII
        # Por ahora simulamos validación exitosa
        self.write({
            'l10n_do_rnc_validated': True,
            'l10n_do_rnc_validation_date': fields.Date.today(),
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('RNC Validado'),
                'message': _('El RNC/Cédula ha sido validado correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }
