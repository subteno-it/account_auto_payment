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
import netsvc


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

    def make_auto_payment(self, cr, uid, journal, bank_journal, move_ids, payment_date, context=None):
        if context is None:
            context = {}
        ctx = context.copy()
        if ctx.get('default_type'):
            del ctx['default_type']
        if ctx.get('journal_id'):
            del ctx['journal_id']
        account_move_line_obj = self.pool.get('account.move.line')
        account_period_obj = self.pool.get('account.period')
        debit = 0
        credit = 0
        period_id = account_period_obj.find(cr, uid, payment_date, context=context)[0]
        for move in account_move_line_obj.read(cr, uid, move_ids, ['credit', 'debit'], context=context):
            debit += move['debit']
            credit += move['credit']
            vals = {
                'journal_id': bank_journal.id,
                'debit': move['credit'],
                'credit': move['debit'],
                'period_id': period_id,
                'move_type_id': False,
                'move_id': False,
                'journal_type': 'cash',
                'journal_required_fields': False,
                'account_move_line_group_id': False,
                'select_to_payment': False,
            }
            bank_line_id = account_move_line_obj.copy(cr, uid, move['id'], vals, context=ctx)
            account_move_line_obj.reconcile(cr, uid, [move['id'], bank_line_id], context=context)

        account_id = journal.type == 'purchase' and bank_journal.default_credit_account_id.id or bank_journal.default_debit_account_id.id
        vals = {
            'name': bank_journal.name,
            'journal_id': bank_journal.id,
            'debit': debit,
            'credit': credit,
            'period_id': period_id,
            'move_type_id': False,
            'account_id': account_id,
            'move_id': False,
            'journal_type': 'cash',
            'journal_required_fields': False,
            'account_move_line_group_id': False,
            'select_to_payment': False,
        }
        account_move_line_obj.create(cr, uid, vals, context=ctx)

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


class account_move_line_group(osv.osv):
    _name = 'account.move.line.group'
    _description = 'Group the move line'

    _columns = {
        'journal_id': fields.many2one('account.journal', 'Journal', help="journal of move"),
        'maturity_date': fields.date('Maturity date', help="Date max of maturity"),
        'payment_date': fields.date('Payment date', help="Date of the payment"),
        'bank_journal_id': fields.many2one('account.journal', 'Bank journal', domain=[('type', '=', 'cash')], help="Journal where make the payment"),
        'account_move_line_ids': fields.one2many('account.move.line', 'account_move_line_group_id', 'Move Lines', ),
        'state': fields.selection([('draft','Draft'), ('done', 'Done')], 'State', help="Use by workflow"),
    }

    _defaults = {
         'state': lambda *a: 'draft',
    }

    def create(self, cr, uid, values, context=None):
        """
        genere date and default select
        """
        if values.get('account_move_line_ids'):
            account_move_line_obj = self.pool.get('account.move.line')
            dates = []
            line_ids = []
            for x, line_id in values['account_move_line_ids']:
                line_ids.append(line_id)

            for id, select in account_move_line_obj.get_select_to_payment(cr, uid, line_ids, context=context).items():
                account_move_line_obj.write(cr, uid, [id], {'select_to_payment': select}, context=context)

        return super(account_move_line_group, self).create(cr, uid, values, context=context)

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context={}, toolbar=False):
        if context:
            context['display_select'] = True
        result = super(osv.osv, self).fields_view_get(cr, uid, view_id,view_type,context,toolbar=toolbar)
        res = self.pool.get('account.move.line').fields_view_get(cr, uid, view_type='tree', context=context)
        result['fields']['account_move_line_ids']['views'] = {
            'tree': {
                'arch': res['arch'],
                'fields': res['fields'],
            },
        }
        return result

    def button_done(self, cr, uid, ids, context):
        account_journal_obj = self.pool.get('account.journal')
        wf_service = netsvc.LocalService("workflow")
        for this in self.browse(cr, uid, ids, context=context):
            account_move = {}
            date_move = {}
            for line in this.account_move_line_ids:
                if not line.select_to_payment:
                    line.write({'account_move_line_group_id': False}, context=context)
                    continue
                if not date_move.get(line.date_maturity, False):
                    date_move[line.date_maturity] = [line.id]
                else:
                    date_move[line.date_maturity].append(line.id)

                if not account_move.get(line.account_id.id, False):
                    account_move[line.account_id.id] = [line.id]
                else:
                    account_move[line.account_id.id].append(line.id)
            #TODO uncomment me
            #for account_id, move_ids in account_move.items():
            #    account_journal_obj.make_auto_payment(cr, uid, this.journal_id, this.bank_journal_id, move_ids, this.payment_date, context=context)

            #TODO uncomment me
            #wf_service.trg_validate(uid, 'account.move.line.group', id, 'signal_done', cr)
        return True

    def name_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, ['journal_id', 'payment_date'], context=context)
        res = []
        for read in reads:
            res.append(( read['id'], read['journal_id'][1] + "/" + read['payment_date']))
        return res

account_move_line_group()


class account_move_line(osv.osv):
    _inherit = 'account.move.line'

    _columns = {
        'journal_type': fields.selection([('sale', 'Sale'), ('purchase', 'Purchase'), ('cash', 'Cash'), ('general', 'General'), ('situation', 'Situation'), ('traite', 'Traite'), ('cheque', 'Cheque')], 'Display type', required=True, help="View only in the moves in this journal type"),
        'journal_required_fields': fields.boolean('Required fields', help="If check, the fields Partner, Maturity date and move type will be required"),
        'move_type_id': fields.many2one('account.move.type', 'Type', help="type of payment"),
        'account_move_line_group_id': fields.many2one('account.move.line.group', 'Group of line', help="All the line with this group have send in the same bank as the same time"),
        'select_to_payment': fields.boolean('Select', help="If check, the move will be paid"),
    }

    def get_select_to_payment(self, cr, uid, ids, context=None):
        res = {}
        for id in ids:
            res[id] = True
        return res

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

            xml = '''<tree string="%s" editable="top" refresh="5" on_write="_on_create_write"%s>\n\t''' % (title, state)
            fields = []
            if context.get('display_select', False):
                xml += '''<field name="select_to_payment"/>\n'''
                fields.append('select_to_payment')

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
                    if context.get('display_select', False):
                        attrs.append('readonly="1"')

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
                        if context.get('display_select', False):
                            xml += '''<field name="move_type_id" readonly="1"/>'''
                        else:
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
