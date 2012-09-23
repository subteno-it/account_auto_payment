# -*- coding: utf-8 -*-
##############################################################################
#
#    account_auto_payment module for OpenERP, add wizard to make the payment auto
#    Copyright (C) 2011 SYLEAM Info Services (<http://www.syleam.fr/>)
#              Jean-Sébastien SUZANNE <jean-sebastien.suzanne@syleam.fr>
#              Sébastien LANGE <sebastien.lange@syleam.fr>
#
#    This file is a part of account_auto_payment
#
#    account_auto_payment is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    account_auto_payment is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Account Auto Payment',
    'version': '1.0',
    'category': 'Custom',
    'description': """Add wizard to make the payment auto""",
    'author': 'SYLEAM',
    'website': 'http://www.syleam.fr/',
    'depends': [
        'account',
        'base',
    ],
    'init_xml': [],
    'update_xml': [
        'security/ir.model.access.csv',
        'account_view.xml',
        'account_data.xml',
        'wizard/account_auto_payment.xml',
        'account_workflow.xml',
    ],
    'demo_xml': [],
    'installable': True,
    'active': False,
    'license': 'GPL-3',
}


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
