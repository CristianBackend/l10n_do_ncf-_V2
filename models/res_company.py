# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_do_ncf_next_expiration_alert = fields.Integer(
        string='Días Alerta Vencimiento NCF',
        default=30,
        help='Días antes del vencimiento para alertar sobre secuencias NCF'
    )
    
    l10n_do_ncf_low_sequence_alert = fields.Integer(
        string='Alerta Secuencia Baja',
        default=50,
        help='Alertar cuando queden menos de esta cantidad de NCF'
    )
    
    l10n_do_fiscal_journal_id = fields.Many2one(
        'account.journal',
        string='Diario Fiscal por Defecto',
        domain=[('type', '=', 'sale')],
        help='Diario de ventas por defecto para facturas fiscales'
    )
    
    l10n_do_informal_vendor_journal_id = fields.Many2one(
        'account.journal',
        string='Diario Compras Informales',
        domain=[('type', '=', 'purchase')],
        help='Diario para compras a proveedores informales'
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_do_ncf_next_expiration_alert = fields.Integer(
        related='company_id.l10n_do_ncf_next_expiration_alert',
        readonly=False
    )
    
    l10n_do_ncf_low_sequence_alert = fields.Integer(
        related='company_id.l10n_do_ncf_low_sequence_alert',
        readonly=False
    )
    
    l10n_do_fiscal_journal_id = fields.Many2one(
        related='company_id.l10n_do_fiscal_journal_id',
        readonly=False
    )
    
    l10n_do_informal_vendor_journal_id = fields.Many2one(
        related='company_id.l10n_do_informal_vendor_journal_id',
        readonly=False
    )
