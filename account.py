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
from StringIO import StringIO
import base64
from tools.translate import _


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
        reconcile = []
        account_id = False
        move_id = self.pool.get('account.move').create(cr, uid, {'date': payment_date, 'journal_id': bank_journal.id, 'period_id':period_id}, context=ctx)
        for move in account_move_line_obj.browse(cr, uid, move_ids, context=ctx):
            debit += move.debit
            credit += move.credit
            if journal.type in ('traite', 'cheque') and not account_id:
                account_id = journal.default_debit_account_id and journal.default_debit_account_id.id or False
            elif journal.type == 'purchase':
                vals = {
		            'date': payment_date,
                    'journal_id': bank_journal.id,
                    'debit': move.credit,
                    'credit': move.debit,
                    'period_id': period_id,
                    'move_type_id': False,
                    'move_id': move_id,
                    'journal_type': 'cash',
                    'journal_required_fields': False,
                    'account_move_line_group_id': False,
                    'select_to_payment': False,
                }
                reconcile.append([move.id, account_move_line_obj.copy(cr, uid, move.id, vals, context=ctx)])

        if journal.type == 'purchase':
            credit = credit - debit
            debit = 0
        elif journal.type in ('traite', 'cheque'):
            if not account_id:
                raise osv.except_osv(_('Error'), _('Pas de type définis'))
            debit = debit - credit
            credit = 0
            vals = {
                'name':journal.name,
		        'date': payment_date,
                'journal_id': bank_journal.id,
                'debit': credit,
                'credit': debit,
                'period_id': period_id,
                'move_type_id': False,
                'move_id': move_id,
                'journal_type': 'cash',
                'journal_required_fields': False,
                'account_id': account_id,
                'account_move_line_group_id': False,
                'select_to_payment': False,
            }
            move_ids.append(account_move_line_obj.create(cr, uid, vals, context=ctx))

        account_id = journal.type == 'purchase' and bank_journal.default_credit_account_id.id or bank_journal.default_debit_account_id.id
        vals = {
	    'date': payment_date,
            'name': bank_journal.name,
            'journal_id': bank_journal.id,
            'debit': debit,
            'credit': credit,
            'period_id': period_id,
            'move_type_id': False,
            'account_id': account_id,
            'move_id': move_id,
            'journal_type': 'cash',
            'journal_required_fields': False,
            'account_move_line_group_id': False,
            'select_to_payment': False,
        }
        account_move_line_obj.create(cr, uid, vals, context=ctx)

        if journal.type == 'purchase':
            for line_ids in reconcile:
                account_move_line_obj.reconcile(cr, uid, line_ids, context=context)
        elif journal.type in ('traite', 'cheque'):
            account_move_line_obj.reconcile(cr, uid, move_ids, context=context)

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
        'etebac': fields.binary('Etebac', help="ETEBAC file"),
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
                account_move_line_obj.write(cr, uid, [id], {'select_to_payment': select}, context=context, update_check=False)

        return super(account_move_line_group, self).create(cr, uid, values, context=context)

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context={}, toolbar=False):
        if context:
            context['display_select'] = True
        result = super(osv.osv, self).fields_view_get(cr, uid, view_id,view_type,context,toolbar=toolbar)
        if context.get('journal_id'):
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
                    line.write({'account_move_line_group_id': False}, context=context, update_check=False)
                    continue

                if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                    if not line.partner_bank:
                        raise osv.except_osv(_('Error'), _('No account number define'))
                    if not date_move.get(line.date_maturity, False):
                        date_move[line.date_maturity] = {line.partner_bank.id: [line]}
                    elif not date_move[line.date_maturity].get(line.partner_bank.id, False):
                        date_move[line.date_maturity][line.partner_bank.id] = [line]
                    else:
                        date_move[line.date_maturity][line.partner_bank.id].append(line)

                if not account_move.get(line.account_id.id, False):
                    account_move[line.account_id.id] = [line.id]
                else:
                    account_move[line.account_id.id].append(line.id)

            for account_id, move_ids in account_move.items():
                account_journal_obj.make_auto_payment(cr, uid, this.journal_id, this.bank_journal_id, move_ids, this.payment_date, context=context)

            if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                buf = StringIO()
                for date, accounts in date_move.items():
                    self.export_bank_transfert(cr, uid, this, buf, date, accounts, context=context)

                etebac = base64.encodestring(buf.getvalue())
                buf.close()
                this.write({'etebac': etebac}, context=context)

            wf_service.trg_validate(uid, 'account.move.line.group', this.id, 'signal_done', cr)
        return True

    def button_remake_etebac(self, cr, uid, ids, context):
        account_journal_obj = self.pool.get('account.journal')
        for this in self.browse(cr, uid, ids, context=context):
            date_move = {}
            for line in this.account_move_line_ids:
                if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                    if not line.partner_bank:
                        raise osv.except_osv(_('Error'), _('No account number define'))
                    if not date_move.get(line.date_maturity, False):
                        date_move[line.date_maturity] = {line.partner_bank.id: [line]}
                    elif not date_move[line.date_maturity].get(line.partner_bank.id, False):
                        date_move[line.date_maturity][line.partner_bank.id] = [line]
                    else:
                        date_move[line.date_maturity][line.partner_bank.id].append(line)

            if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                buf = StringIO()
                for date, accounts in date_move.items():
                    self.export_bank_transfert(cr, uid, this, buf, date, accounts, context=context)

                etebac = base64.encodestring(buf.getvalue())
                buf.close()
                this.write({'etebac': etebac}, context=context)

        return True

    def name_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, ['journal_id', 'payment_date'], context=context)
        res = []
        for read in reads:
            res.append(( read['id'], read['journal_id'][1] + "/" + read['payment_date']))
        return res

    def export_bank_transfert(self, cr, uid, this, buf, date, accounts, context=None):
        """ select account.move.lines to export
            @params etbac : browse on current wizard id
        """
       def f_str(number):
            # Format the line 
            return ('%.2f' % number).replace('.', '')

        amount = 0
        if this.journal_id.type == 'purchase':
            self.etbac_format_move_emetteur(cr, uid, this, buf, '02', date, context=context)
            for account_id, lines in accounts.items():
                bank = lines[0].partner_bank
                amount_lines = 0
                for line in lines:
                    amount_lines += line.credit - line.debit
               amount_lines = int(f_str(amount_lines))
                if amount_lines > 0:
                    self.etbac_format_move_destinataire(cr, uid, bank, lines[0], amount_lines, this, buf, context=context)
                    amount += amount_lines
                elif amount_lines < 0:
                    raise osv.except_osv(_('Error'), _('No amount < 0 is allowed for etebac'))
            self.etbac_format_move_total(cr, uid, this, buf, amount, '02', context=context)
        elif this.journal_id.type == 'traite':
            num = 2
            self.etbac_format_move_emetteur_traite(cr, uid, this, buf, '60', date, context=context)
            for account_id, lines in accounts.items():
                for line in lines:
                    amount += self.etbac_format_move_destinataire_traite(cr, uid, line, this, buf, num, context=context)
                    num += 1
            self.etbac_format_move_total_traite(cr, uid, this, buf, amount, '60', num, context=context)

    def etbac_format_move_emetteur(self, cr, uid, etbac, buf, mode, date, context=None):
        """ Create 'emetteur' segment of ETBAC French Format for record type 03
        """
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        rib = user.company_id.partner_id.bank_ids and user.company_id.partner_id.bank_ids[0] or False
        if not rib:
            raise osv.except_osv('Information de banque', 'Le partenaire de la societe %s ne dispose d\'aucune banque' % user.company_id.name)
        if not rib.guichet or not rib.compte or not rib.banque:
            raise osv.except_osv(_('Erreur'), _('Informations RIB manquantes !'))
        A = '03'
        B1 = mode.ljust(2)
        B2 = ' ' * 8
        B3 = ' ' * 6  #emeteur
        C1_1 = ' '
        C1_2 = ' ' * 5
        C1_3 = str(date[8:10] + date[5:7] + date[2:4]).ljust(6)
        C2 = user.company_id.name.encode('ascii', 'replace')[:24].ljust(24).upper()
        D1_1 = ' ' * 7
        D1_2 = ' ' * 17
        D2_1 = ' ' * 2
        D2_2 = 'E'
        D2_3 = ' ' * 5
        D3 = str(rib.guichet).ljust(5).upper()
        D4 = str(rib.compte).ljust(11).upper()
        E = ' ' * 16
        F = ' ' * 31
        G1 = str(rib.banque).ljust(5).upper()
        G2 = ' ' * 6
        str_etbac = A + B1 + B2 + B3 + C1_1 + C1_2 + C1_3 + C2 + D1_1 + D1_2 + D2_1 + D2_2 + D2_3 + D3 + D4 + E + F + G1 + G2
        if len(str_etbac) != 160:
            raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\n emetteur %s ') % len(str_etbac))
        buf.write(str(str_etbac) + '\n')

    def etbac_format_move_emetteur_traite(self, cr, uid, etbac, buf, mode, date, context=None):
        """ Create 'emetteur' segment of ETBAC French Format for record type 03
        """
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        rib = user.company_id.partner_id.bank_ids and user.company_id.partner_id.bank_ids[0] or False
        if not rib:
            raise osv.except_osv('Information de banque', 'Le partenaire de la societe %s ne dispose d\'aucune banque' % user.company_id.name)
        if not rib.guichet or not rib.compte or not rib.banque:
            raise osv.except_osv(_('Erreur'), _('Informations RIB manquantes !'))
        A = '03'
        B1 = mode.ljust(2)
        B2 = '00000001'
        B3 = ' ' * 6  #emeteur
        C1 = ' ' * 6
        C2 = str(date[8:10] + date[5:7] + date[2:4]).ljust(6)
        C3 = user.company_id.name.encode('ascii', 'replace')[:24].ljust(24).upper()
        D1 = ' ' * 24
        D2_1 = '3'
        D2_2 = ' '
        D2_3 = 'E'
        D3 = str(rib.banque).ljust(5).upper()
        D4 = str(rib.guichet).ljust(5).upper()
        D5 = str(rib.compte).ljust(11).upper()
        E = ' ' * 16
        F1 = ' ' * 6
        F2 = ' ' * 10
        F3 = ' ' * 15
        G = ' ' * 11
        str_etbac = A + B1 + B2 + B3 + C1 + C2 + C3 + D1 + D2_1 + D2_2 + D2_3 + D3 + D4 + D5 + E + F1 + F2 + F3 + G
        if len(str_etbac) != 160:
            raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\n emetteur traite %s') % len(str_etbac))
        buf.write(str(str_etbac) + '\n')

    def etbac_format_move_destinataire(self, cr, uid, bank, line, amount, etbac, buf, context=None):
        """ Create 'destinataire' segment of ETBAC French Format.
            @params P (string) :
            @return (string)
        """
        A = '06'
        B1 = line.move_type_id and line.move_type_id.code.ljust(2) or '02'
        B2 = ' ' * 8
        B3 = ' ' * 6
        C1 = ' ' * 12
        C2 = str(line.partner_id.name).ljust(24)[:24].upper()
        D1 = str(bank.bank and bank.bank.name or '')[:24].ljust(24).upper()
        D2 = ' ' * 8
        D3 = str(bank.guichet).rjust(5, '0')
        D4 = str(bank.compte).rjust(11, '0')
        E = str(amount).zfill(16)
        F = str(line.name or ' ')[:31].ljust(31).upper()
        G1 = str(bank.banque).rjust(5, '0')
        G2 = ' ' * 6
        str_etbac = A + B1 + B2 + B3 + C1 + C2 + D1 + D2 + D3 + D4 + E + F + G1 + G2
        if len(str_etbac) != 160:
            raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\n destinataire %s') % line.partner_id.name)
        buf.write(str(str_etbac) + '\n')

    def etbac_format_move_destinataire_traite(self, cr, uid, line, etbac, buf, num, context=None):
        """ Create 'destinataire' segment of ETBAC French Format.
            @params P (string) :
            @return (string)
        """
       def f_str(number):
            # Format the line 
            return ('%.2f' % number).replace('.', '')

        if line.debit > 0.0:
            bank = line.partner_bank
            if not bank:
                raise osv.except_osv('Information de banque', 'Le partenaire de la societe %s ne dispose d\'aucune banque' % line.partner_id.name)
            A = '06'
            B1 = line.move_type_id and line.move_type_id.code.ljust(2) or '60'
            B2 = str(num).ljust(8, '0').upper()
            B3 = ' ' * 6
            C1_1 = ' ' * 2
            C1_2 = str(line.ref or ' ')[:10].ljust(10).upper()
            C2 = str(line.partner_id.name)[:24].ljust(24).upper()
            D1 = str(bank.bank and bank.bank.name or bank.name or ' ')[:24].ljust(24).upper()
            D2_1 = line.move_type_id and line.move_type_id.traite_code.ljust(1) or '0'
            D2_2 = ' ' * 2
            D3 = str(bank.banque).rjust(5, '0')
            D4 = str(bank.guichet).rjust(5, '0')
            D5 = str(bank.compte).rjust(11, '0')
            E1 = f_str(line.debit).zfill(12)
            E2 = ' ' * 4
            date = line.date_maturity
            F1 = str(date[8:10] + date[5:7] + date[2:4]).ljust(6)
            date = etbac.payment_date
            F2_1 = str(date[8:10] + date[5:7] + date[2:4]).ljust(6)
            F2_2 = ' ' * 4
            F3_1 = ' ' * 1
            F3_2 = ' ' * 3
            F3_3 = ' ' * 3
            F3_4 = ' ' * 9
            G = ' ' * 10
            str_etbac = A + B1 + B2 + B3 + C1_1 + C1_2 + C2 + D1 + D2_1 + D2_2 + D3 + D4 + D5 + E1 + E2 + F1 + F2_1 + F2_2 + F3_1 + F3_2 + F3_3 + F3_4 + G
            if len(str_etbac) != 160:
                raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\n destinataire traite %s') % len(str_etbac))
            buf.write(str(str_etbac) + '\n')
        return f_str(line.debit)

    def etbac_format_move_total(self, cr, uid, etbac, buf, montant, mode, context=None):
        """ Create 'total' segment of ETBAC French Format.
        """
        A = '08'
        B1 = mode.ljust(2)
        B2 = ' ' * 8
        B3 = ' ' * 6
        C1 = ' ' * 12
        C2 = ' ' * 24
        D1 = ' ' * 24
        D2 = ' ' * 8
        D3 = ' ' * 5
        D4 = ' ' * 11
        E = str(montant).zfill(16)
        F = ' ' * 31
        G1 = ' ' * 5
        G2 = ' ' * 6
        str_etbac = A + B1 + B2 + B3 + C1 + C2 + D1 + D2 + D3 + D4 + E + F + G1 + G2
        if len(str_etbac) != 160:
            raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\n total : %s') % len(str_etbac))
        buf.write(str(str_etbac) + '\n')

    def etbac_format_move_total_traite(self, cr, uid, etbac, buf, montant, mode, num, context=None):
        """ Create 'total' segment of ETBAC French Format.
        """
        A = '08'
        B1 = mode.ljust(2)
        B2 = str(num).ljust(8, '0').upper()
        B3 = ' ' * 6
        C1 = ' ' * 12
        C2 = ' ' * 24
        D1 = ' ' * 24
        D2_1 = ' ' * 1
        D2_2 = ' ' * 2
        D3 = ' ' * 5
        D4 = ' ' * 5
        D5 = ' ' * 11
        E1 = str(montant).zfill(12)
        E2 = ' ' * 4
        F1 = ' ' * 6
        F2 = ' ' * 10
        F3 = ' ' * 15
        G1 = ' ' * 5
        G2 = ' ' * 6
        str_etbac = A + B1 + B2 + B3 + C1 + C2 + D1 + D2_1 + D2_2 + D3 + D4 + D5 + E1 + E2 + F1 + F2 + F3 + G1 + G2
        if len(str_etbac) != 160:
            raise osv.except_osv(_('Error !'), _('Exception during ETBAC formatage !\ntotal traite %s') % len(str_etbac))
        buf.write(str(str_etbac) + '\n')

account_move_line_group()


class account_move_line(osv.osv):
    _inherit = 'account.move.line'

    _columns = {
        'journal_type': fields.selection([('sale', 'Sale'), ('purchase', 'Purchase'), ('cash', 'Cash'), ('general', 'General'), ('situation', 'Situation'), ('traite', 'Traite'), ('cheque', 'Cheque')], 'Display type', help="View only in the moves in this journal type"),
        'journal_required_fields': fields.boolean('Journal required fields', help="If check and account required field check, the fields Partner, Maturity date and move type will be required"),
        'account_required_fields': fields.boolean('Account required fields', help="If check, the fields Partner, Maturity date and move type will be required"),
        'move_type_id': fields.many2one('account.move.type', 'Type', help="type of payment"),
        'account_move_line_group_id': fields.many2one('account.move.line.group', 'Group of line', help="All the line with this group have send in the same bank as the same time"),
        'select_to_payment': fields.boolean('Select', help="If check, the move will be paid"),
    }

    _defaults = {
         'journal_type': lambda *a: 'cash',
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
                xml += '''<field name="partner_bank" domain="[('partner_id', '=', partner_id)]"/>\n'''
                fields.append('partner_bank')

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
            if 'account_required_fields' not in fields_list:
                fields_list.append(('account_required_fields', False))
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
                    if context.get('display_select', False) and field.field != 'date_maturity':
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
                    elif field.field=='partner_bank':
                        attrs.append('domain="[(\'partner_id\', \'=\', \'partner_id\')]"')
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
                    elif field == 'journal_required_fields':
                        xml += '''<field name="journal_required_fields" invisible="1"/>\n'''
                    elif field == 'account_required_fields':
                        xml += '''<field name="account_required_fields" invisible="1"/>\n'''
                    elif field == 'journal_id':
                        xml += '''<field name="journal_type" invisible="1"/>\n'''
                    elif field == 'move_type_id':
                        if context.get('display_select', False):
                            xml += '''<field name="move_type_id" readonly="1"/>'''
                        else:
                            xml += '''<field name="move_type_id" domain="[('type', '=', journal_type)]" attrs="{'required': [('journal_required_fields', '=', True), ('account_required_fields', '=', True)]}"/>'''

            xml += '''</tree>'''
            result['arch'] = xml
            result['fields'] = self.fields_get(cr, uid, fields, context)
        return result

    def onchange_account_id(self, cr, uid, ids, account_id=False, partner_id=False):
        res = super(account_move_line, self).onchange_account_id(cr, uid, ids, account_id=account_id, partner_id=partner_id)
        if account_id:
            account = self.pool.get('account.account').browse(cr, uid, account_id)
            res['value']['account_required_fields'] = account.user_type.required_fields
        return res

    def onchange_partner_id(self, cr, uid, ids, move_id, partner_id, account_id=None, debit=0, credit=0, date=False, journal=False):
        values = super(account_move_line, self).onchange_partner_id(cr, uid, ids, move_id, partner_id, account_id=account_id, debit=debit, credit=credit, date=date, journal=journal)
        if values['value'].get('account_id', None) is not None:
            account = self.pool.get('account.account').browse(cr, uid, values['value'].get('account_id'))
            values['value']['account_required_fields'] = account.user_type.required_fields
        if partner_id:
            partner_bank_obj = self.pool.get('res.partner.bank')
            partner_banks = partner_bank_obj.search(cr, uid, [('partner_id', '=', partner_id), ('default_bank', '=', True)])
            if not partner_banks:
                tmp_partner_banks = partner_bank_obj.search(cr, uid, [('partner_id', '=', partner_id)])
                if len(tmp_partner_banks) == 1:
                    partner_banks = tmp_partner_banks
            if partner_banks:
                values['value']['partner_bank'] = partner_banks[0]

        return values

    def write(self, cr, uid, ids, values, context=None, check=True, update_check=True):
        if context is None:
            context = {}
        if context.get('update_check', None) is not None:
            update_check=context['update_check']
        return super(account_move_line, self).write(cr, uid, ids, values, context=context, check=check, update_check=update_check)

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


class account_account_type(osv.osv):
    _inherit = 'account.account.type'

    _columns = {
        'required_fields': fields.boolean('Required fields', help="If check, the fields Partner, Maturity date and move type will be required"),
    }

    _defaults = {
         'required_fields': lambda *a: False,
    }

account_account_type()


class account_model_line(osv.osv):
    _inherit = 'account.model.line'

    _columns = {
        'move_type_id': fields.many2one('account.move.type', 'Type', help="type of payment"),
    }

account_model_line()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
