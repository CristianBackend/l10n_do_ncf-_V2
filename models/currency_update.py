# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class ResCurrencyRateProvider(models.Model):
    _name = 'l10n_do_ncf.currency.rate.provider'
    _description = 'Historial de Tasas de Cambio RD'
    _order = 'date desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True)
    rate = fields.Float(string='Tasa', digits=(12, 4), required=True,
                        help='Tasa de cambio: 1 USD/EUR = X DOP')
    source = fields.Char(string='Fuente')
    applied = fields.Boolean(string='Aplicada', default=False)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    @api.depends('currency_id', 'date')
    def _compute_name(self):
        for rec in self:
            if rec.currency_id and rec.date:
                rec.name = f"{rec.currency_id.name} - {rec.date}"
            else:
                rec.name = "Nueva Tasa"

    def action_apply_rate(self):
        """Aplicar esta tasa a Odoo"""
        self.ensure_one()
        if not self.rate:
            raise UserError(_('No hay tasa para aplicar'))
        
        currency_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.currency_id.id),
            ('name', '=', self.date),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        
        # Odoo usa inversa: si 1 USD = 60 DOP, rate = 1/60
        inverse_rate = 1 / self.rate if self.rate else 0
        
        if currency_rate:
            currency_rate.write({'rate': inverse_rate})
        else:
            self.env['res.currency.rate'].create({
                'currency_id': self.currency_id.id,
                'name': self.date,
                'rate': inverse_rate,
                'company_id': self.company_id.id,
            })
        
        self.applied = True
        _logger.info('Tasa aplicada: %s = %.4f DOP', self.currency_id.name, self.rate)
        
        return True


class CurrencyRateAutoUpdate(models.Model):
    _name = 'l10n_do_ncf.currency.auto.update'
    _description = 'Configuracion de Actualizacion Automatica de Tasas'

    name = fields.Char(string='Nombre', default='Actualización Automática de Tasas')
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    
    update_usd = fields.Boolean(string='Actualizar USD', default=True)
    update_eur = fields.Boolean(string='Actualizar EUR', default=True)
    
    last_update = fields.Datetime(string='Última Actualización', readonly=True)
    last_status = fields.Text(string='Último Estado', readonly=True)
    
    alert_on_failure = fields.Boolean(string='Alertar si falla', default=True)
    alert_user_ids = fields.Many2many(
        'res.users',
        'currency_update_alert_user_rel',
        'config_id',
        'user_id',
        string='Usuarios a Alertar'
    )

    # =====================================================
    # FUENTES DE DATOS - MULTIPLES PARA NO FALLAR
    # =====================================================
    
    def _get_rate_source_1(self):
        """Fuente 1: ExchangeRate-API (gratuita, confiable)"""
        try:
            response = requests.get(
                'https://api.exchangerate-api.com/v4/latest/USD',
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if 'rates' in data:
                    return {
                        'USD_DOP': data['rates'].get('DOP'),
                        'EUR_USD': data['rates'].get('EUR'),
                        'source': 'ExchangeRate-API'
                    }
        except Exception as e:
            _logger.warning('Fuente 1 (ExchangeRate-API) falló: %s', str(e))
        return None

    def _get_rate_source_2(self):
        """Fuente 2: Open Exchange Rates (backup)"""
        try:
            response = requests.get(
                'https://open.er-api.com/v6/latest/USD',
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('result') == 'success' and 'rates' in data:
                    return {
                        'USD_DOP': data['rates'].get('DOP'),
                        'EUR_USD': data['rates'].get('EUR'),
                        'source': 'Open ER-API'
                    }
        except Exception as e:
            _logger.warning('Fuente 2 (Open ER-API) falló: %s', str(e))
        return None

    def _get_rate_source_3(self):
        """Fuente 3: Frankfurter API (Banco Central Europeo)"""
        try:
            response = requests.get(
                'https://api.frankfurter.app/latest?from=USD&to=DOP,EUR',
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if 'rates' in data:
                    return {
                        'USD_DOP': data['rates'].get('DOP'),
                        'EUR_USD': 1 / data['rates'].get('EUR', 1) if data['rates'].get('EUR') else None,
                        'source': 'Frankfurter (BCE)'
                    }
        except Exception as e:
            _logger.warning('Fuente 3 (Frankfurter) falló: %s', str(e))
        return None

    def _get_rate_source_4(self):
        """Fuente 4: Currency API (otro backup)"""
        try:
            response = requests.get(
                'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json',
                timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if 'usd' in data:
                    return {
                        'USD_DOP': data['usd'].get('dop'),
                        'EUR_USD': data['usd'].get('eur'),
                        'source': 'Currency-API CDN'
                    }
        except Exception as e:
            _logger.warning('Fuente 4 (Currency-API) falló: %s', str(e))
        return None

    def _fetch_rates_with_fallback(self):
        """Obtener tasas con múltiples fuentes de respaldo"""
        sources = [
            self._get_rate_source_1,
            self._get_rate_source_2,
            self._get_rate_source_3,
            self._get_rate_source_4,
        ]
        
        for i, source_func in enumerate(sources, 1):
            _logger.info('Intentando fuente %d de %d...', i, len(sources))
            result = source_func()
            if result and result.get('USD_DOP'):
                _logger.info('Éxito con fuente: %s', result.get('source'))
                return result
        
        _logger.error('TODAS las fuentes de tasas fallaron')
        return None

    def _calculate_rates(self, data):
        """Calcular tasas USD y EUR a DOP"""
        rates = {}
        
        # USD a DOP directo
        if data.get('USD_DOP'):
            rates['USD'] = float(data['USD_DOP'])
        
        # EUR a DOP (calculado via USD)
        if data.get('USD_DOP') and data.get('EUR_USD'):
            # EUR_USD es cuántos EUR por 1 USD
            # Para obtener EUR a DOP: USD_DOP / EUR_USD
            rates['EUR'] = float(data['USD_DOP']) / float(data['EUR_USD'])
        
        return rates

    def action_update_rates_now(self):
        """Actualizar tasas manualmente (botón)"""
        self.ensure_one()
        result = self._do_update_rates()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Actualización de Tasas'),
                'message': self.last_status,
                'type': 'success' if 'exitosamente' in (self.last_status or '') else 'warning',
                'sticky': False,
            }
        }

    def _do_update_rates(self):
        """Ejecutar la actualización de tasas"""
        self.ensure_one()
        today = fields.Date.today()
        status_messages = []
        success = False
        
        # Obtener tasas con fallback
        data = self._fetch_rates_with_fallback()
        
        if not data:
            status_messages.append('❌ No se pudieron obtener tasas de ninguna fuente')
            self._send_failure_alert(status_messages)
        else:
            rates = self._calculate_rates(data)
            source = data.get('source', 'Desconocida')
            
            # Guardar USD
            if self.update_usd and rates.get('USD'):
                usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                if usd:
                    # Verificar si ya existe para hoy
                    existing = self.env['l10n_do_ncf.currency.rate.provider'].search([
                        ('currency_id', '=', usd.id),
                        ('date', '=', today),
                        ('company_id', '=', self.company_id.id),
                    ], limit=1)
                    
                    if existing:
                        existing.write({'rate': rates['USD'], 'source': source})
                        existing.action_apply_rate()
                    else:
                        new_rate = self.env['l10n_do_ncf.currency.rate.provider'].create({
                            'date': today,
                            'currency_id': usd.id,
                            'rate': rates['USD'],
                            'source': source,
                            'company_id': self.company_id.id,
                        })
                        new_rate.action_apply_rate()
                    
                    status_messages.append('✅ USD: %.4f DOP' % rates['USD'])
                    success = True
            
            # Guardar EUR
            if self.update_eur and rates.get('EUR'):
                eur = self.env['res.currency'].search([('name', '=', 'EUR')], limit=1)
                if eur:
                    existing = self.env['l10n_do_ncf.currency.rate.provider'].search([
                        ('currency_id', '=', eur.id),
                        ('date', '=', today),
                        ('company_id', '=', self.company_id.id),
                    ], limit=1)
                    
                    if existing:
                        existing.write({'rate': rates['EUR'], 'source': source})
                        existing.action_apply_rate()
                    else:
                        new_rate = self.env['l10n_do_ncf.currency.rate.provider'].create({
                            'date': today,
                            'currency_id': eur.id,
                            'rate': rates['EUR'],
                            'source': source,
                            'company_id': self.company_id.id,
                        })
                        new_rate.action_apply_rate()
                    
                    status_messages.append('✅ EUR: %.4f DOP' % rates['EUR'])
                    success = True
            
            if success:
                status_messages.insert(0, '📊 Fuente: %s' % source)
                status_messages.append('✅ Tasas actualizadas exitosamente')
        
        # Actualizar estado
        self.write({
            'last_update': fields.Datetime.now(),
            'last_status': '\n'.join(status_messages),
        })
        
        return success

    def _send_failure_alert(self, messages):
        """Enviar alerta si falla la actualización"""
        if not self.alert_on_failure or not self.alert_user_ids:
            return
        
        emails = self.alert_user_ids.mapped('email')
        emails = [e for e in emails if e]
        
        if not emails:
            return
        
        body = '''
        <h2>⚠️ Error en Actualización de Tasas de Cambio</h2>
        <p>No se pudieron actualizar las tasas de cambio automáticamente.</p>
        <hr/>
        <p><strong>Detalles:</strong></p>
        <ul>
            %s
        </ul>
        <hr/>
        <p><strong>Acción requerida:</strong></p>
        <p>Por favor actualice las tasas manualmente o verifique la conectividad.</p>
        <p>Puede consultar las tasas oficiales en: 
           <a href="https://dgii.gov.do/estadisticas/tasaCambio">DGII - Tasas de Cambio</a>
        </p>
        ''' % '\n'.join(['<li>%s</li>' % m for m in messages])
        
        try:
            mail = self.env['mail.mail'].sudo().create({
                'subject': '⚠️ Error en Tasas de Cambio - %s' % self.company_id.name,
                'body_html': body,
                'email_to': ','.join(emails),
            })
            mail.send()
        except Exception as e:
            _logger.error('Error enviando alerta de tasas: %s', str(e))

    @api.model
    def _cron_update_rates(self):
        """Cron: Actualizar tasas automáticamente"""
        configs = self.search([('active', '=', True)])
        for config in configs:
            try:
                config._do_update_rates()
            except Exception as e:
                _logger.error('Error en cron de tasas para %s: %s', 
                            config.company_id.name, str(e))


class CurrencyRateManualWizard(models.TransientModel):
    _name = 'l10n_do_ncf.currency.manual.wizard'
    _description = 'Ingresar Tasas Manualmente'

    date = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    usd_rate = fields.Float(string='USD (1 USD = X DOP)', digits=(12, 4))
    eur_rate = fields.Float(string='EUR (1 EUR = X DOP)', digits=(12, 4))

    def action_save(self):
        """Guardar tasas manuales"""
        self.ensure_one()
        saved = []
        
        if self.usd_rate:
            usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            if usd:
                rate = self.env['l10n_do_ncf.currency.rate.provider'].create({
                    'date': self.date,
                    'currency_id': usd.id,
                    'rate': self.usd_rate,
                    'source': 'Manual (DGII)',
                    'company_id': self.env.company.id,
                })
                rate.action_apply_rate()
                saved.append('USD: %.4f' % self.usd_rate)
        
        if self.eur_rate:
            eur = self.env['res.currency'].search([('name', '=', 'EUR')], limit=1)
            if eur:
                rate = self.env['l10n_do_ncf.currency.rate.provider'].create({
                    'date': self.date,
                    'currency_id': eur.id,
                    'rate': self.eur_rate,
                    'source': 'Manual (DGII)',
                    'company_id': self.env.company.id,
                })
                rate.action_apply_rate()
                saved.append('EUR: %.4f' % self.eur_rate)
        
        message = 'Tasas guardadas: %s' % ', '.join(saved) if saved else 'No se guardaron tasas'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tasas de Cambio'),
                'message': message,
                'type': 'success' if saved else 'warning',
                'sticky': False,
            }
        }
