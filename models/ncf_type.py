# -*- coding: utf-8 -*-

from odoo import models, fields, api


class NcfType(models.Model):
    _name = 'l10n_do_ncf.type'
    _description = 'Tipo de Comprobante Fiscal NCF'
    _order = 'code'

    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre del tipo de comprobante fiscal'
    )
    code = fields.Char(
        string='Código',
        required=True,
        size=2,
        help='Código de 2 dígitos del tipo de NCF (ej: 01, 02, 11)'
    )
    prefix = fields.Char(
        string='Prefijo NCF',
        required=True,
        size=3,
        help='Prefijo del NCF (ej: B01, E31)'
    )
    is_electronic = fields.Boolean(
        string='Es Electrónico (e-CF)',
        default=False,
        help='Indica si es un comprobante fiscal electrónico'
    )
    requires_rnc = fields.Boolean(
        string='Requiere RNC',
        default=True,
        help='Indica si requiere RNC del cliente'
    )
    for_sale = fields.Boolean(
        string='Para Ventas',
        default=True,
        help='Disponible para facturas de venta'
    )
    for_purchase = fields.Boolean(
        string='Para Compras',
        default=False,
        help='Disponible para facturas de compra'
    )
    aplica_vencimiento = fields.Boolean(
        string='Aplica Vencimiento',
        default=True,
        help='Indica si las secuencias de este tipo de NCF están sujetas a vencimiento de 2 años. '
             'Según las guías operativas de DGII, las Facturas de Consumo (B02/E32), '
             'Notas de Crédito (B04/E34) y Registro Único de Ingresos (B12) NO aplican vencimiento. '
             'NOTA: Esta excepción está en las guías DGII (sin validez legal), no en la Norma 06-2018.'
    )
    vigencia_anos = fields.Integer(
        string='Años de Vigencia',
        default=2,
        help='Cantidad de años de vigencia para las secuencias (por defecto 2 años según Norma 06-2018)'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    description = fields.Text(
        string='Descripción',
        help='Descripción detallada del uso de este tipo de NCF'
    )
    sequence_ids = fields.One2many(
        'l10n_do_ncf.sequence',
        'ncf_type_id',
        string='Secuencias'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'El código del tipo de NCF debe ser único.'),
        ('prefix_unique', 'UNIQUE(prefix)', 'El prefijo del NCF debe ser único.'),
    ]

    @api.depends('prefix', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.prefix}] {record.name}"
