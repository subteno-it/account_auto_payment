# -*- coding: utf-8 -*-
##############################################################################
#
#    account_auto_payment module for OpenERP, add wizard to make the payment auto
#    Copyright (C) 2011 SYLEAM Info Services (<http://www.syleam.fr/>)
#              Jean-Sébastien SUZANNE <jean-sebastien.suzanne@syleam.fr>
#
#    This file is a part of account_auto_payment
#
#    account_auto_payment is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    account_auto_payment is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import osv
from osv import fields


class account_journal(osv.osv):
    _inherit = 'account.journal'

    _columns = {
        'required_fields': fields.boolean('Required fields', help="If check, the fields Partner, Maturity date and move type will be required"),
        'make_etebac': fields.boolean('Make etebac', help="If check, an etebac file will be generate"),
    }

    _defaults = {
         'required_fields': lambda *a: False,
         'make_etebac': lambda *a: False,
    }


    def __init__(self, pool, cr):
        """
        Add new type of journal
        """
        super(account_journal, self).__init__(pool, cr)
        res = self._columns['type'].selection
        if 'traite' not in [k for k, v in res]:
            self._columns['type'].selection.append(('traite', 'Traite'))
        if 'cheque' not in [k for k, v in res]:
            self._columns['type'].selection.append(('cheque', 'Cheque'))

account_journal()


class account_move_type(osv.osv):
    _name = 'account.move.type'
    _description = 'Type of account moves'

    _columns = {
        'name': fields.char('Name', size=64, required=True, help="Name of the account moves type"),
        'type': fields.selection([('sale', 'Sale'), ('purchase', 'Purchase'), ('cash', 'Cash'), ('general', 'General'), ('situation', 'Situation'), ('traite', 'Traite'), ('cheque', 'Cheque')], 'Display type', required=True, help="View only in the moves in this journal type"),
        'code': fields.char('Code', size=2, required=True, help="Code of the operation"),
        'traite_code': fields.char('Traite Code', size=1, help="use for the traite"),
        'account': fields.selection([('credit','Journal credit account'), ('debit','Journal debit account'), ('custom','Account on type')], 'Account parent', required=True, help="Select the account parent for find move\nJournal credit account: take the credit account of the journal\n Journal debit account: take the debit journal account\nAccount on type: take the account on this type"),
        'account_id': fields.many2one('account.account', 'Parent account', help="Use for get the moves line for automatique payment"),
    }

    _defaults = {
         'code': lambda *a: '00',
         'traite_code': lambda *a: '',
    }

    _sql_constraints = [
        ('name_type_uniq', 'unique (name,type)', 'The name and the type of the Account moves type must be unique !'),
    ]

account_move_type()


class account_move_line(osv.osv):
    _inherit = 'account.move.line'

    _columns = {
        'journal_type': fields.selection([('sale', 'Sale'), ('purchase', 'Purchase'), ('cash', 'Cash'), ('general', 'General'), ('situation', 'Situation'), ('traite', 'Traite'), ('cheque', 'Cheque')], 'Display type', required=True, help="View only in the moves in this journal type"),
        'journal_required_fields': fields.boolean('Required fields', help="If check, the fields Partner, Maturity date and move type will be required"),
        'move_type_id': fields.many2one('account.move.type', 'Type', help="type of payment"),
    }

    def onchange_journal_id(self, cr, uid, ids, journal_id, context=None):
        """
        return information of journall
        """
        res = {}
        if journal_id:
            data = self.pool.get('account.journal').read(cr, uid, journal_id, ['type', 'required_fields'], context=context)
            res['value'] = {
                'journal_type': data['type'],
                'journal_required_fields': data['required_fields'],
            }

        return res

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context={}, toolbar=False):
        result = super(osv.osv, self).fields_view_get(cr, uid, view_id,view_type,context,toolbar=toolbar)
        if view_type=='tree' and context.get('journal_id',False):
            title = self.view_header_get(cr, uid, view_id, view_type, context)
            journal = self.pool.get('account.journal').browse(cr, uid, context['journal_id'])

            state = ''
            if journal.view_id.color:
                state = ' colors="' + journal.view_id.color + '"'

            xml = '''<?xml version="1.0"?>\n<tree string="%s" editable="top" refresh="5" on_write="_on_create_write"%s>\n\t''' % (title, state)
            fields = []

            widths = {
                'ref': 50,
                'statement_id': 50,
                'state': 60,
                'tax_code_id': 50,
                'move_id': 40,
            }
            fields_list = []
            for field in journal.view_id.columns_id:
                fields_list.append((field, True))
            fields_name = [field.field for field in journal.view_id.columns_id]
            if 'journal_id' not in fields_list:
                fields_list.append(('journal_id', False))
            if 'journal_required_fields' not in fields_list:
                fields_list.append(('journal_required_fields', False))
            if 'journal_type' not in fields_list:
                fields_list.append(('journal_type', False))
            if 'move_type_id' not in fields_list:
                fields_list.append(('move_type_id', False))

            for field, column in fields_list:
                if column:
                    fields.append(field.field)
                    attrs = []
                    if field.field=='debit':
                        attrs.append('sum="Total debit"')
                    elif field.field=='credit':
                        attrs.append('sum="Total credit"')
                    elif field.field=='account_tax_id':
                        attrs.append('domain="[(\'parent_id\',\'=\',False)]"')
                    elif field.field=='account_id' and journal.id:
                        attrs.append('domain="[(\'journal_id\', \'=\', '+str(journal.id)+'),(\'type\',\'&lt;&gt;\',\'view\'), (\'type\',\'&lt;&gt;\',\'closed\')]" on_change="onchange_account_id(account_id, partner_id)"')
                    elif field.field == 'partner_id':
                        attrs.append('on_change="onchange_partner_id(move_id,partner_id,account_id,debit,credit,date,((\'journal_id\' in context) and context[\'journal_id\']) or {})"')
                        attrs.append('attrs="{\'required\': [(\'journal_required_fields\', \'=\', True)]}"')
                    elif field.field == 'journal_id':
                        attrs.append('on_change="onchange_journal_id(journal_id)"')
                    elif field.field == 'move_type_id':
                        attrs.append('domain="[(\'type\', \'=\', journal_type)]"')
                        attrs.append('attrs="{\'required\': [(\'journal_required_fields\', \'=\', True)]}"')
                    elif field.field == 'date_maturity':
                        attrs.append('attrs="{\'required\': [(\'journal_required_fields\', \'=\', True)]}"')
                    if field.readonly:
                        attrs.append('readonly="1"')
                    if field.required:
                        attrs.append('required="1"')
                    else:
                        attrs.append('required="0"')
                    if field.field in ('amount_currency','currency_id'):
                        attrs.append('on_change="onchange_currency(account_id,amount_currency,currency_id,date,((\'journal_id\' in context) and context[\'journal_id\']) or {})"')

                    if field.field in widths:
                        attrs.append('width="'+str(widths[field.field])+'"')
                    xml += '''<field name="%s" %s/>\n''' % (field.field,' '.join(attrs))
                else:
                    fields.append(field)
                    if field == 'journal_id':
                        xml += '''<field name="journal_id" on_change="onchange_journal_id(journal_id)" invisible="1"/>\n'''
                    if field == 'journal_required_fields':
                        xml += '''<field name="journal_required_fields" invisible="1"/>\n'''
                    if field == 'journal_id':
                        xml += '''<field name="journal_type" invisible="1"/>\n'''
                    if field == 'move_type_id':
                        xml += '''<field name="move_type_id" domain="[('type', '=', journal_type)]" attrs="{'required': [('journal_required_fields', '=', True)]}"/>'''

            xml += '''</tree>'''
            result['arch'] = xml
            result['fields'] = self.fields_get(cr, uid, fields, context)
        return result


account_move_line()


class account_journal_view(osv.osv):
    _inherit = 'account.journal.view'

    _columns = {
        'color': fields.char('Color', size=64, help="define the colors of line"),
    }

    _defaults = {
         'color': lambda *a: "red:state=='draft'",
    }

account_journal_view()


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
