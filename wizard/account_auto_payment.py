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


class account_auto_payment(osv.osv_memory):
    _name = 'account.auto.payment'
    _description = 'Make payment'

    _columns = {
        'type': fields.selection([('sale', 'Sale'), ('purchase', 'Purchase'), ('cash', 'Cash'), ('general', 'General'), ('situation', 'Situation'), ('traite', 'Traite'), ('cheque', 'Cheque')], 'Display type', required=True, help="View only in the moves in this journal type"),
        'maturity_date': fields.date('Maturity date', required=True, help="Date max of maturity"),
        'payment_date': fields.date('Payment date', required=True, help="Date of the payment"),
        'journal_id': fields.many2one('account.journal', 'Journal', required=True, help="Jounal to make payment"),
        'bank_journal_id': fields.many2one('account.journal', 'Bank journal', required=True, domain=[('type', '=', 'cash')], help="Journal where make the payment"),
    }

    def select_moves(self, cr, uid, ids, context=None):
        """
        return an action with the good move
        """
        this = self.browse(cr, uid, ids[0], context=context)
        account_move_type_obj = self.pool.get('account.move.type')
        account_move_line_obj = self.pool.get('account.move.line')
        account_move_type_ids = account_move_type_obj.search(cr, uid, [('type', '=', this.type)], context=context)
        account_ids = []
        account_op = 'in'
        for type in account_move_type_obj.browse(cr, uid, account_move_type_ids, context=context):
            if type.account == 'debit':
                account_id = this.journal_id.default_debit_account_id and this.journal_id.default_debit_account_id.id or False
            elif type.account == 'credit':
                account_id = this.journal_id.default_credit_account_id and this.journal_id.default_credit_account_id.id or False
            elif type.account == 'custom':
                account_id = type.account_id.id
                account_op = 'child_of'

            if account_id and account_id not in account_ids:
                account_ids.append(account_id)

        domain = [
            ('journal_id', '=', this.journal_id.id),
            ('account_id', account_op, account_ids),
            ('reconcile_id', '=', False),
        ]
        if this.maturity_date:
            domain.extend(['|', ('date_maturity', '<=', this.maturity_date), ('date_maturity', '=', False)])

        account_move_line_ids = account_move_line_obj.search(cr, uid, domain, context=context)
        vals = {
            'journal_id': this.journal_id.id,
            'maturity_date': this.maturity_date,
            'payment_date': this.payment_date,
            'bank_journal_id': this.bank_journal_id.id,
            'account_move_line_ids': [(4, id) for id in account_move_line_ids],
        }
        group_id = self.pool.get('account.move.line.group').create(cr, uid, vals, context=context)
        ir_model_data_obj = self.pool.get('ir.model.data')
        ir_model_data_id = ir_model_data_obj._get_id(cr, uid, 'account_auto_payment', 'act_open_account_move_line_group_view')
        action_id = ir_model_data_obj.read(cr, uid, ir_model_data_id, ['res_id'], context=context)['res_id']
        result = self.pool.get('ir.actions.act_window').read(cr, uid, action_id, [], context=context)
        result['res_id'] = group_id
        result['context'] = {'journal_id': this.journal_id.id}
        return result

account_auto_payment()


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
