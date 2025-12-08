# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class NCFAlertConfig(models.Model):
    _name = 'l10n_do_ncf.alert.config'
    _description = 'Configuracion de Alertas NCF'

    name = fields.Char(string='Nombre', default='Configuración de Alertas NCF')
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Configuración de alertas
    alert_low_stock = fields.Boolean(
        string='Alerta por NCF Agotándose',
        default=True,
        help='Enviar alerta cuando quedan pocos NCF disponibles'
    )
    low_stock_threshold = fields.Integer(
        string='Umbral de NCF Mínimos',
        default=50,
        help='Enviar alerta cuando queden menos de esta cantidad de NCF'
    )
    
    alert_expiring = fields.Boolean(
        string='Alerta por Vencimiento',
        default=True,
        help='Enviar alerta cuando una secuencia está por vencer'
    )
    expiring_days = fields.Integer(
        string='Días Antes de Vencimiento',
        default=30,
        help='Enviar alerta cuando falten estos días para el vencimiento'
    )
    
    # Destinatarios
    alert_email_ids = fields.Many2many(
        'res.users',
        'ncf_alert_user_rel',
        'alert_id',
        'user_id',
        string='Usuarios a Notificar',
        help='Usuarios que recibirán las alertas por email'
    )
    
    # Estado
    last_check = fields.Datetime(
        string='Última Verificación',
        readonly=True
    )
    active = fields.Boolean(default=True)

    @api.model
    def _cron_check_ncf_alerts(self):
        """Método ejecutado por cron para verificar alertas"""
        configs = self.search([('active', '=', True)])
        for config in configs:
            config._check_and_send_alerts()
    
    def _check_and_send_alerts(self):
        """Verificar secuencias y enviar alertas si es necesario"""
        self.ensure_one()
        alerts = []
        
        sequences = self.env['l10n_do_ncf.sequence'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'active')
        ])
        
        today = fields.Date.today()
        
        for seq in sequences:
            # Verificar stock bajo
            if self.alert_low_stock and seq.available_qty <= self.low_stock_threshold:
                alerts.append({
                    'type': 'low_stock',
                    'sequence': seq,
                    'message': _(
                        '⚠️ ALERTA: La secuencia %s (%s) tiene solo %d NCF disponibles.'
                    ) % (seq.name, seq.ncf_type_id.name, seq.available_qty)
                })
            
            # Verificar vencimiento próximo
            if self.alert_expiring and seq.expiration_date:
                days_to_expire = (seq.expiration_date - today).days
                if 0 < days_to_expire <= self.expiring_days:
                    alerts.append({
                        'type': 'expiring',
                        'sequence': seq,
                        'message': _(
                            '📅 ALERTA: La secuencia %s (%s) vence en %d días (%s).'
                        ) % (seq.name, seq.ncf_type_id.name, days_to_expire, 
                             seq.expiration_date.strftime('%d/%m/%Y'))
                    })
                elif days_to_expire <= 0:
                    alerts.append({
                        'type': 'expired',
                        'sequence': seq,
                        'message': _(
                            '🚨 URGENTE: La secuencia %s (%s) ha VENCIDO el %s.'
                        ) % (seq.name, seq.ncf_type_id.name, 
                             seq.expiration_date.strftime('%d/%m/%Y'))
                    })
        
        # Enviar alertas si hay
        if alerts:
            self._send_alert_email(alerts)
        
        # Actualizar última verificación
        self.write({'last_check': fields.Datetime.now()})
        
        return alerts
    
    def _send_alert_email(self, alerts):
        """Enviar email con las alertas"""
        self.ensure_one()
        
        if not self.alert_email_ids:
            _logger.warning('No hay usuarios configurados para recibir alertas NCF')
            return
        
        # Construir cuerpo del email
        body = _('''
        <h2>🔔 Alertas de Comprobantes Fiscales (NCF)</h2>
        <p>Se han detectado las siguientes alertas en las secuencias NCF de su empresa:</p>
        <hr/>
        ''')
        
        for alert in alerts:
            if alert['type'] == 'expired':
                color = '#dc3545'  # Rojo
            elif alert['type'] == 'low_stock':
                color = '#fd7e14'  # Naranja
            else:
                color = '#ffc107'  # Amarillo
            
            body += '''
            <div style="padding: 10px; margin: 10px 0; border-left: 4px solid %s; background: #f8f9fa;">
                <strong>%s</strong><br/>
                <small>Tipo: %s | Serie: %s | Disponibles: %d</small>
            </div>
            ''' % (
                color,
                alert['message'],
                alert['sequence'].ncf_type_id.name,
                alert['sequence'].prefix,
                alert['sequence'].available_qty
            )
        
        body += '''
        <hr/>
        <p><strong>Recomendaciones:</strong></p>
        <ul>
            <li>Para secuencias agotándose: Solicite nuevas secuencias en la DGII</li>
            <li>Para secuencias por vencer: Renueve sus secuencias antes de la fecha límite</li>
        </ul>
        <p><small>Este es un mensaje automático del sistema NCF de Odoo.</small></p>
        '''
        
        # Obtener emails de usuarios
        emails = self.alert_email_ids.mapped('email')
        emails = [e for e in emails if e]  # Filtrar vacíos
        
        if not emails:
            _logger.warning('Los usuarios configurados no tienen email')
            return
        
        # Crear y enviar email
        mail_values = {
            'subject': _('🔔 Alertas NCF - %s') % self.company_id.name,
            'body_html': body,
            'email_to': ','.join(emails),
            'email_from': self.company_id.email or self.env.user.email,
        }
        
        try:
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            _logger.info('Alerta NCF enviada a: %s', ','.join(emails))
        except Exception as e:
            _logger.error('Error enviando alerta NCF: %s', str(e))
    
    def action_test_alert(self):
        """Botón para probar envío de alertas"""
        self.ensure_one()
        alerts = self._check_and_send_alerts()
        
        if alerts:
            message = _('Se encontraron %d alertas y se envió el email.') % len(alerts)
        else:
            message = _('No se encontraron alertas. Sus secuencias están en buen estado.')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Verificación de Alertas'),
                'message': message,
                'type': 'success' if not alerts else 'warning',
                'sticky': False,
            }
        }
