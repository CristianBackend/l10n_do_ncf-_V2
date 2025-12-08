# -*- coding: utf-8 -*-

from odoo import models, api


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _prepare_default_reversal(self, move):
        """Agregar tipo NCF y NCF afectado a la nota de credito"""
        values = super()._prepare_default_reversal(move)
        
        # Si la factura original tiene NCF
        if move.l10n_do_ncf_number:
            # Buscar tipo Nota de Credito (04)
            ncf_type = self.env['l10n_do_ncf.type'].search([('code', '=', '04')], limit=1)
            
            values.update({
                'l10n_do_ncf_type_id': ncf_type.id if ncf_type else False,
                'l10n_do_ncf_origin': move.l10n_do_ncf_number,
                'l10n_do_origin_move_id': move.id,
            })
        
        return values
