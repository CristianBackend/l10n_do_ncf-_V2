# -*- coding: utf-8 -*-
{
    'name': 'República Dominicana - Comprobantes Fiscales (NCF)',
    'version': '17.0.1.1.0',
    'summary': 'Gestión de NCF para República Dominicana según normativa DGII',
    'description': """
        Módulo de Comprobantes Fiscales para República Dominicana
        ==========================================================
        
        Este módulo implementa:
        - Gestión de secuencias NCF (B01-B17, E31-E47)
        - Tipos de comprobantes fiscales según DGII
        - Validación de RNC y Cédula
        - Generación de reportes 606, 607, 608
        - Formato de factura según Norma General 06-2018
        - Control de vencimiento configurable por tipo de NCF
        - Excepción de vencimiento para B02, B04, B12 según Guía DGII
        
        Normativa:
        - Decreto 254-06
        - Norma General 06-2018
        - Norma General 05-2019
        - Norma General 07-2018
        - Guía del Contribuyente No. 5 (Mayo 2022)
        
        IMPORTANTE sobre vencimiento:
        - La Norma 06-2018 establece vencimiento de 2 años para todos los NCF
        - Las Guías DGII (sin validez legal) exceptúan B02, B04, B12
        - Este módulo permite configurar ambas políticas por tipo de NCF
    """,
    'author': 'ByChrixDev',
    'website': 'https://github.com/CristianBackend',
    'category': 'Accounting/Localizations',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'l10n_do',
        'contacts',
    ],
    'data': [
        # Security
        'security/ncf_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ncf_type_data.xml',
        'data/ir_sequence_data.xml',
        # Views
        'views/ncf_type_views.xml',
        'views/ncf_sequence_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_company_views.xml',
        'views/menu_views.xml',
        # Wizards
        'wizards/dgii_report_wizard_views.xml',
        # Reports
        'reports/invoice_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
