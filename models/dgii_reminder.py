# -*- coding: utf-8 -*-

from odoo import models, api, _
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class DgiiReminder(models.TransientModel):
    _name = 'l10n_do_ncf.dgii.reminder'
    _description = 'DGII Monthly Reminder'

    @api.model
    def send_monthly_reminder(self):
        """Envia recordatorio mensual para reportes DGII via mensaje interno"""
        _logger.info('Iniciando envio de recordatorios DGII...')
        
        companies = self.env['res.company'].search([
            ('vat', '!=', False),
        ])
        
        months = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        month_name = months.get(date.today().month, '')
        
        message_body = f'''
        <div style="padding: 15px; background: #fff3cd; border-left: 4px solid #ffc107; margin: 10px 0;">
            <h3 style="color: #856404; margin-top: 0;">⚠️ Recordatorio DGII - {month_name}</h3>
            <p style="color: #856404;">Los reportes DGII deben enviarse <strong>antes del dia 15</strong>:</p>
            <ul style="color: #856404;">
                <li><strong>606</strong> - Compras de Bienes y Servicios</li>
                <li><strong>607</strong> - Ventas de Bienes y Servicios</li>
                <li><strong>608</strong> - Comprobantes Anulados</li>
                <li><strong>609</strong> - Pagos al Exterior</li>
            </ul>
            <p style="color: #856404;">Accede a <strong>Contabilidad → Reportes → Reportes DGII</strong> para generarlos.</p>
        </div>
        '''
        
        sent_count = 0
        for company in companies:
            try:
                users = self.env['res.users'].search([
                    ('company_id', '=', company.id),
                    ('active', '=', True),
                    '|',
                    ('groups_id', 'in', self.env.ref('account.group_account_manager').id),
                    ('groups_id', 'in', self.env.ref('base.group_system').id),
                ])
                
                for user in users:
                    if user.partner_id:
                        # Enviar mensaje al canal de notificaciones del usuario
                        user.partner_id.message_post(
                            body=message_body,
                            subject=f'Recordatorio: Enviar Reportes DGII - {month_name}',
                            message_type='notification',
                            subtype_xmlid='mail.mt_note',
                        )
                        
                        # Tambien crear notificacion de bandeja
                        self.env['bus.bus']._sendone(
                            user.partner_id,
                            'simple_notification',
                            {
                                'title': 'Recordatorio DGII',
                                'message': f'Los reportes DGII deben enviarse antes del dia 15 de {month_name}',
                                'type': 'warning',
                                'sticky': True,
                            }
                        )
                        
                        sent_count += 1
                        _logger.info(f'Notificacion DGII enviada a {user.name}')
                        
            except Exception as e:
                _logger.error(f'Error enviando notificacion a {company.name}: {str(e)}')
                continue
        
        _logger.info(f'Notificaciones DGII enviadas: {sent_count}')
        return True

    @api.model
    def send_test_reminder(self):
        return self.send_monthly_reminder()
