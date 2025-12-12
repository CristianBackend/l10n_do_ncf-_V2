# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import date


class NcfSequence(models.Model):
    _name = 'l10n_do_ncf.sequence'
    _description = 'Secuencia de Comprobantes Fiscales NCF'
    _order = 'ncf_type_id, id desc'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )
    ncf_type_id = fields.Many2one(
        'l10n_do_ncf.type',
        string='Tipo de NCF',
        required=True,
        ondelete='restrict'
    )
    prefix = fields.Char(
        string='Prefijo',
        related='ncf_type_id.prefix',
        store=True
    )
    range_from = fields.Integer(
        string='Desde',
        required=True,
        default=1,
        help='Numero inicial de la secuencia autorizada'
    )
    range_to = fields.Integer(
        string='Hasta',
        required=True,
        help='Numero final de la secuencia autorizada'
    )
    current_number = fields.Integer(
        string='Numero Actual',
        required=True,
        default=0,
        help='Ultimo numero utilizado'
    )
    next_number = fields.Integer(
        string='Proximo Numero',
        compute='_compute_next_number'
    )
    available_qty = fields.Integer(
        string='Disponibles',
        compute='_compute_available_qty'
    )
    usage_percent = fields.Float(
        string='Porcentaje Uso',
        compute='_compute_usage_percent',
        store=True
    )
    traffic_light = fields.Selection([
        ('green', 'Verde'),
        ('yellow', 'Amarillo'),
        ('red', 'Rojo'),
    ], string='Semaforo', compute='_compute_usage_percent', store=True)
    expiration_date = fields.Date(
        string='Fecha de Vencimiento',
        compute='_compute_expiration_date',
        store=True,
        readonly=False,
        help='Fecha de vencimiento de la secuencia'
    )
    authorization_date = fields.Date(
        string='Fecha de Autorizacion',
        required=True,
        default=fields.Date.today,
        help='Fecha en que la DGII autorizo esta secuencia'
    )
    aplica_vencimiento = fields.Boolean(
        string='Aplica Vencimiento',
        related='ncf_type_id.aplica_vencimiento',
        store=True
    )
    warning_threshold = fields.Integer(
        string='Umbral de Alerta',
        default=50,
        help='Alertar cuando queden menos de esta cantidad'
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('depleted', 'Agotada'),
        ('expired', 'Vencida'),
    ], string='Estado', default='draft', compute='_compute_state', store=True)
    active = fields.Boolean(
        string='Activo',
        default=True
    )

    @api.depends('ncf_type_id', 'range_from', 'range_to')
    def _compute_name(self):
        for record in self:
            if record.ncf_type_id:
                record.name = f"{record.ncf_type_id.prefix} ({record.range_from}-{record.range_to})"
            else:
                record.name = "Nueva Secuencia"

    @api.depends('current_number', 'range_from')
    def _compute_next_number(self):
        for record in self:
            if record.current_number == 0:
                record.next_number = record.range_from
            else:
                record.next_number = record.current_number + 1

    @api.depends('range_to', 'current_number', 'range_from')
    def _compute_available_qty(self):
        for record in self:
            if record.range_to == 0:
                record.available_qty = 0
            elif record.current_number == 0:
                record.available_qty = record.range_to - record.range_from + 1
            else:
                record.available_qty = record.range_to - record.current_number

    @api.depends('range_from', 'range_to', 'current_number', 'state')
    def _compute_usage_percent(self):
        for record in self:
            total = record.range_to - record.range_from + 1
            if total > 0:
                used = record.current_number - record.range_from + 1 if record.current_number > 0 else 0
                record.usage_percent = (used / total) * 100
                
                # Si esta agotada o vencida, siempre semaforo rojo
                if record.state in ('depleted', 'expired'):
                    record.traffic_light = 'red'
                else:
                    available_percent = 100 - record.usage_percent
                    if available_percent > 50:
                        record.traffic_light = 'green'
                    elif available_percent > 20:
                        record.traffic_light = 'yellow'
                    else:
                        record.traffic_light = 'red'
            else:
                record.usage_percent = 0
                record.traffic_light = 'green'

    @api.depends('authorization_date', 'ncf_type_id', 'ncf_type_id.aplica_vencimiento', 'ncf_type_id.vigencia_anos')
    def _compute_expiration_date(self):
        for record in self:
            if not record.ncf_type_id or not record.authorization_date:
                record.expiration_date = False
                continue

            if record.ncf_type_id.aplica_vencimiento:
                auth_year = record.authorization_date.year
                vigencia = record.ncf_type_id.vigencia_anos or 2
                expiry_year = auth_year + (vigencia - 1)
                record.expiration_date = date(expiry_year, 12, 31)
            else:
                record.expiration_date = False

    @api.depends('current_number', 'range_to', 'range_from', 'expiration_date', 'aplica_vencimiento')
    def _compute_state(self):
        today = date.today()
        for record in self:
            # Si no tiene rango final configurado, es borrador
            if record.range_to == 0:
                record.state = 'draft'
            # Si vencio
            elif record.aplica_vencimiento and record.expiration_date and record.expiration_date < today:
                record.state = 'expired'
            # Si se agoto (llego al limite)
            elif record.current_number > 0 and record.current_number >= record.range_to:
                record.state = 'depleted'
            # Si tiene rango valido configurado
            elif record.range_to > 0 and record.range_to > record.range_from:
                # Si ya se ha usado, esta activa
                if record.current_number > 0:
                    record.state = 'active'
                else:
                    # Leer estado actual de BD para mantener activacion manual
                    if record.id:
                        self.env.cr.execute(
                            "SELECT state FROM l10n_do_ncf_sequence WHERE id = %s",
                            (record.id,)
                        )
                        result = self.env.cr.fetchone()
                        if result and result[0] == 'active':
                            record.state = 'active'
                        else:
                            record.state = 'draft'
                    else:
                        record.state = 'draft'
            # Por defecto es borrador
            else:
                record.state = 'draft'

    def _get_last_ncf_number_used(self, ncf_type_id, company_id):
        """Obtener el ultimo numero NCF usado de este tipo en facturas"""
        ncf_type = self.env['l10n_do_ncf.type'].browse(ncf_type_id)
        if not ncf_type:
            return 0

        prefix = ncf_type.prefix

        # Buscar en facturas
        last_invoice = self.env['account.move'].search([
            ('company_id', '=', company_id),
            ('l10n_do_ncf_number', 'like', prefix + '%'),
            ('state', '!=', 'cancel'),
        ], order='l10n_do_ncf_number desc', limit=1)

        if last_invoice and last_invoice.l10n_do_ncf_number:
            try:
                # Extraer numero: B0100000005 -> 5
                ncf = last_invoice.l10n_do_ncf_number
                num_str = ncf[3:]  # Quitar prefijo (B01, B02, etc.)
                return int(num_str)
            except (ValueError, IndexError):
                pass

        return 0

    def _check_range_overlap(self, ncf_type_id, company_id, range_from, range_to, exclude_id=None):
        """Verificar si el rango se solapa con secuencias existentes"""
        domain = [
            ('ncf_type_id', '=', ncf_type_id),
            ('company_id', '=', company_id),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))

        existing_sequences = self.search(domain)

        for seq in existing_sequences:
            # Verificar solapamiento: (nuevo.desde <= viejo.hasta) AND (nuevo.hasta >= viejo.desde)
            if range_from <= seq.range_to and range_to >= seq.range_from:
                return seq

        return None

    @api.constrains('range_from', 'range_to', 'ncf_type_id', 'company_id')
    def _check_range(self):
        for record in self:
            # Validacion basica: rango inicial > 0
            if record.range_from <= 0:
                raise ValidationError(_('El rango inicial debe ser mayor a 0.'))

            # Si no tiene rango final, saltar otras validaciones (es borrador)
            if record.range_to == 0:
                continue

            # Validacion: rango final > rango inicial
            if record.range_to <= record.range_from:
                raise ValidationError(_('El rango final debe ser mayor al rango inicial.'))

            # Obtener prefijo para mensajes de error
            tipo_ncf = record.ncf_type_id.prefix if record.ncf_type_id else 'N/A'

            # VALIDACION #1: No permitir rangos que se solapen con secuencias existentes
            overlapping = self._check_range_overlap(
                record.ncf_type_id.id,
                record.company_id.id,
                record.range_from,
                record.range_to,
                exclude_id=record.id
            )

            if overlapping:
                raise ValidationError(_(
                    'ERROR: Rango Duplicado o Superpuesto [%s]\n\n'
                    'El rango ingresado (Del %s al %s) se solapa con un rango anterior:\n'
                    '- Secuencia: %s\n'
                    '- Rango: Del %s al %s\n\n'
                    'No se permiten rangos duplicados o superpuestos.\n'
                    'Esto podria generar NCF duplicados y problemas con DGII.'
                ) % (tipo_ncf, record.range_from, record.range_to, overlapping.name,
                     overlapping.range_from, overlapping.range_to))

            # VALIDACION #2: El nuevo rango debe iniciar DESPUES del ultimo NCF emitido
            last_ncf_used = self._get_last_ncf_number_used(
                record.ncf_type_id.id,
                record.company_id.id
            )

            if last_ncf_used > 0 and record.range_from <= last_ncf_used:
                # Obtener el ultimo NCF para mostrarlo en el mensaje
                prefix = record.ncf_type_id.prefix
                last_ncf_str = f"{prefix}{str(last_ncf_used).zfill(8)}"

                raise ValidationError(_(
                    'ERROR: Rango Invalido - Retroceso No Permitido [%s]\n\n'
                    'El rango inicial (%s) debe ser MAYOR al ultimo NCF emitido.\n\n'
                    '- Ultimo NCF generado: %s\n'
                    '- Ultimo numero usado: %s\n'
                    '- Rango minimo permitido: %s en adelante\n\n'
                    'No puede usar rangos que contengan numeros ya utilizados.\n'
                    'Esto causaria NCF duplicados y rechazo en reportes DGII (607).'
                ) % (tipo_ncf, record.range_from, last_ncf_str, last_ncf_used, last_ncf_used + 1))

            # VALIDACION #3: No permitir retrocesos respecto a secuencias anteriores
            max_range = self.search([
                ('ncf_type_id', '=', record.ncf_type_id.id),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id),
                ('range_to', '>', 0),
            ], order='range_to desc', limit=1)

            if max_range and record.range_from <= max_range.range_to:
                raise ValidationError(_(
                    'ERROR: Retroceso de Secuencia No Permitido [%s]\n\n'
                    'El rango inicial (%s) debe ser MAYOR al ultimo rango autorizado.\n\n'
                    '- Ultima secuencia: %s\n'
                    '- Rango anterior: Del %s al %s\n'
                    '- Nuevo rango debe iniciar en: %s o mayor\n\n'
                    'Los rangos NCF deben ser siempre consecutivos y ascendentes.'
                ) % (tipo_ncf, record.range_from, max_range.name, max_range.range_from,
                     max_range.range_to, max_range.range_to + 1))

    def action_activate(self):
        """Activar la secuencia manualmente"""
        for record in self:
            if record.range_to == 0:
                raise UserError(_('Debe configurar el rango final antes de activar la secuencia.'))
            if record.range_to <= record.range_from:
                raise UserError(_('El rango final debe ser mayor al rango inicial.'))
            record.write({'state': 'active'})

    def get_next_ncf(self):
        """
        Obtener el siguiente NCF de forma SEGURA (thread-safe).
        Usa FOR UPDATE para bloquear el registro durante la transaccion.
        """
        self.ensure_one()
        
        # Obtener prefijo para mensajes de error
        tipo_ncf = self.ncf_type_id.prefix if self.ncf_type_id else 'N/A'

        if self.state == 'expired':
            raise UserError(_('[%s] Esta secuencia de NCF ha vencido.') % tipo_ncf)
        if self.state == 'depleted':
            raise UserError(_('[%s] Esta secuencia de NCF se ha agotado. Solicite una nueva a DGII.') % tipo_ncf)
        if self.state == 'draft':
            raise UserError(_('[%s] Esta secuencia de NCF no esta activa. Debe activarla primero.') % tipo_ncf)

        if self.aplica_vencimiento and self.expiration_date and self.expiration_date < date.today():
            raise UserError(_('[%s] Esta secuencia de NCF ha vencido el %s.') % (tipo_ncf, self.expiration_date.strftime('%d/%m/%Y')))

        # BLOQUEO PARA CONCURRENCIA - SELECT FOR UPDATE
        self.env.cr.execute("""
            SELECT current_number, range_from, range_to
            FROM l10n_do_ncf_sequence
            WHERE id = %s
            FOR UPDATE NOWAIT
        """, (self.id,))

        result = self.env.cr.fetchone()
        if not result:
            raise UserError(_('[%s] Error al obtener la secuencia NCF.') % tipo_ncf)

        current_number, range_from, range_to = result

        if current_number == 0:
            next_num = range_from
        else:
            next_num = current_number + 1

        if next_num > range_to:
            raise UserError(_(
                '[%s] Se ha agotado la secuencia de NCF.\n\n'
                'Rango autorizado: %s - %s\n'
                'Ultimo usado: %s\n\n'
                'Debe solicitar una nueva secuencia a la DGII.'
            ) % (tipo_ncf, range_from, range_to, current_number))

        # Formatear NCF
        if self.ncf_type_id.is_electronic:
            ncf = f"{self.prefix}{str(next_num).zfill(10)}"
        else:
            ncf = f"{self.prefix}{str(next_num).zfill(8)}"

        # VALIDACION ADICIONAL: Verificar que este NCF no exista ya en facturas
        existing = self.env['account.move'].search([
            ('l10n_do_ncf_number', '=', ncf),
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'cancel'),
        ], limit=1)

        if existing:
            raise UserError(_(
                'ERROR CRITICO: NCF Duplicado Detectado [%s]\n\n'
                'El NCF %s ya existe en la factura %s.\n\n'
                'Esto indica un problema de sincronizacion en las secuencias.\n'
                'Contacte al administrador del sistema inmediatamente.'
            ) % (tipo_ncf, ncf, existing.name))

        # ACTUALIZAR con SQL directo para garantizar atomicidad
        self.env.cr.execute("""
            UPDATE l10n_do_ncf_sequence
            SET current_number = %s, write_date = NOW(), write_uid = %s
            WHERE id = %s AND current_number = %s
            RETURNING id
        """, (next_num, self.env.uid, self.id, current_number))

        updated = self.env.cr.fetchone()
        if not updated:
            raise UserError(_(
                '[%s] Error de concurrencia: Otro usuario genero un NCF al mismo tiempo.\n'
                'Por favor intente de nuevo.'
            ) % tipo_ncf)

        self.invalidate_recordset(['current_number'])

        return ncf

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('l10n_do_ncf_seq_id', '=', self.id)],
            'context': {'default_l10n_do_ncf_seq_id': self.id},
        }
