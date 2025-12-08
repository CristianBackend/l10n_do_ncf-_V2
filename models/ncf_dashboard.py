# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, timedelta


class NcfDashboard(models.Model):
    _name = 'l10n_do_ncf.dashboard'
    _description = 'Dashboard NCF'
    _auto = False

    @api.model
    def get_dashboard_data(self):
        """Obtener datos para el dashboard NCF"""
        company_id = self.env.company.id
        today = date.today()
        first_day_month = today.replace(day=1)
        
        # Secuencias NCF
        sequences = self.env['l10n_do_ncf.sequence'].search([
            ('company_id', '=', company_id),
            ('state', '=', 'active')
        ])
        
        # Alertas
        alerts = []
        for seq in sequences:
            # Alerta por pocas disponibles
            if seq.available_qty <= seq.warning_threshold:
                alerts.append({
                    'type': 'warning',
                    'icon': 'fa-exclamation-triangle',
                    'title': f'Pocas secuencias disponibles',
                    'message': f'{seq.ncf_type_id.name}: Solo quedan {seq.available_qty} NCF',
                    'action': 'sequence',
                    'id': seq.id
                })
            
            # Alerta por proxima a vencer
            if seq.expiration_date and seq.aplica_vencimiento:
                days_to_expire = (seq.expiration_date - today).days
                if 0 < days_to_expire <= 30:
                    alerts.append({
                        'type': 'danger',
                        'icon': 'fa-calendar-times-o',
                        'title': f'Secuencia por vencer',
                        'message': f'{seq.ncf_type_id.name}: Vence en {days_to_expire} dias',
                        'action': 'sequence',
                        'id': seq.id
                    })
                elif days_to_expire <= 0:
                    alerts.append({
                        'type': 'danger',
                        'icon': 'fa-times-circle',
                        'title': f'Secuencia VENCIDA',
                        'message': f'{seq.ncf_type_id.name}: Vencio el {seq.expiration_date}',
                        'action': 'sequence',
                        'id': seq.id
                    })
        
        # Estadisticas de secuencias
        sequence_stats = []
        for seq in sequences:
            percentage = (seq.available_qty / (seq.range_to - seq.range_from + 1)) * 100 if seq.range_to > seq.range_from else 0
            sequence_stats.append({
                'id': seq.id,
                'name': seq.ncf_type_id.name,
                'prefix': seq.prefix,
                'available': seq.available_qty,
                'total': seq.range_to - seq.range_from + 1,
                'percentage': round(percentage, 1),
                'expiration': seq.expiration_date.strftime('%d/%m/%Y') if seq.expiration_date else 'Sin vencimiento',
                'state': seq.state
            })
        
        # Facturas del mes
        invoices_month = self.env['account.move'].search_count([
            ('company_id', '=', company_id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('invoice_date', '>=', first_day_month),
            ('state', '=', 'posted'),
            ('l10n_do_ncf_number', '!=', False)
        ])
        
        # Facturas de compra del mes
        purchases_month = self.env['account.move'].search_count([
            ('company_id', '=', company_id),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('invoice_date', '>=', first_day_month),
            ('state', '=', 'posted')
        ])
        
        # NCF anulados del mes
        cancelled_month = self.env['account.move'].search_count([
            ('company_id', '=', company_id),
            ('state', '=', 'cancel'),
            ('invoice_date', '>=', first_day_month),
            ('l10n_do_ncf_number', '!=', False)
        ])
        
        # Estado de licencia
        license_config = self.env['l10n_do_ncf.license.config'].search([
            ('company_id', '=', company_id)
        ], limit=1)
        
        license_data = {
            'is_valid': license_config.is_valid if license_config else False,
            'status': license_config.status if license_config else 'not_configured',
            'days_remaining': license_config.days_remaining if license_config else 0,
            'expiration_date': license_config.expiration_date.strftime('%d/%m/%Y') if license_config and license_config.expiration_date else '',
            'company_name': license_config.licensed_company_name if license_config else ''
        }
        
        return {
            'alerts': alerts,
            'sequences': sequence_stats,
            'invoices_month': invoices_month,
            'purchases_month': purchases_month,
            'cancelled_month': cancelled_month,
            'license': license_data,
            'current_month': today.strftime('%B %Y')
        }
