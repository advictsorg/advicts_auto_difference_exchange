# -*- coding: utf-8 -*-
{
    'name': 'Advicts Auto Difference Exchange',
    'version': '1.1',
    'summary': "Add auto difference handling for partial payments",
    'author': 'GhaithAhmed@Advicts',
    'category': 'Accounting',
    'website': 'http://www.advicts.com',
    'description': """
    This module adds a new payment difference handling option 'Full Paid with Auto Difference'
        that automatically handles payment differences using a configured account.
    """,
    'depends': ['base', 'account', 'account_accountant'],
    'data': [
        'security/security.xml',
        "security/ir.model.access.csv",
        'views/rate.xml',
        'views/views.xml',
    ],

}
