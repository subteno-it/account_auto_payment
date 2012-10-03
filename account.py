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
from osv import orm
import netsvc
from StringIO import StringIO
import base64
from tools.translate import _
from lxml import etree
from operator import itemgetter


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

        move_id = self.pool.get('account.move').create(cr, uid, {'date': payment_date, 'journal_id': bank_journal.id, 'period_id': period_id}, context=ctx)

        if journal.type in ('traite', 'cheque'):
            account_id = journal.default_debit_account_id and journal.default_debit_account_id.id or False

        # Stockage temporaire pour regrouper les lignes d'écriture par compte fournisseur
        groupir = {}
        for move in account_move_line_obj.browse(cr, uid, move_ids, context=ctx):
            debit += move.debit
            credit += move.credit
            if journal.type == 'purchase':
                if groupir.get(move.account_id.id):
                    groupir[move.account_id.id].append(move.id)
                else:
                    groupir[move.account_id.id] = [move.id]

        # Pour chaque compte comptable, on a regrouper les lignes d'écritures, on crée 1 seul ecriture de banque
        if journal.type == 'purchase':
            for acc_id, m_ids in groupir.items():
                tmp_ids = m_ids
                tdebit = 0
                gdebit = 0
                gcredit = 0
                for gmove in account_move_line_obj.browse(cr, uid, m_ids, context=ctx):
                    gdebit += gmove.debit
                    gcredit += gmove.credit

                # Si nous avons des factures et des avoirs, nosu faisons un seul mouvement avec les 2
                if gcredit > gdebit:
                    tcredit = gcredit - gdebit
                    tdebit = 0
                else:
                    tcredit = 0
                    tdebit = tdebit - tcredit

                vals = {
                    'date': payment_date,
                    'journal_id': bank_journal.id,
                    'debit': tcredit,
                    'credit': tdebit,
                    'period_id': period_id,
                    'move_type_id': False,
                    'move_id': move_id,
                    'journal_type': 'cash',
                    'journal_required_fields': False,
                    'account_move_line_group_id': False,
                    'select_to_payment': False,
                }
                # On ajoute l'écriture fournisseur du journal de banque aux écritures du journal d'achat
                # pour les réconciliés à la fin
                tmp_ids.append(account_move_line_obj.copy(cr, uid, m_ids[0], vals, context=ctx))
                reconcile.append(tmp_ids)

        if journal.type == 'purchase':
            credit = credit - debit
            debit = 0
        elif journal.type in ('traite', 'cheque'):
            if not account_id:
                raise osv.except_osv(_('Error'), _('Pas de type définis'))
            debit = debit - credit
            credit = 0
            vals = {
                'name': journal.name,
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

        # Creation du mouvement de banque associé
        vals = {
            'date': payment_date,
            'name': bank_journal.name,
            'journal_id': bank_journal.id,
            'debit': debit,
            'credit': credit,
            'period_id': period_id,
            'move_type_id': False,
            'account_id': journal.type == 'purchase' and bank_journal.default_credit_account_id.id or bank_journal.default_debit_account_id.id,
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
        'account': fields.selection([('credit', 'Journal credit account'), ('debit', 'Journal debit account'), ('custom', 'Account on type')], 'Account parent', required=True, help="Select the account parent for find move\nJournal credit account: take the credit account of the journal\n Journal debit account: take the debit journal account\nAccount on type: take the account on this type"),
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
        'state': fields.selection([('draft', 'Draft'), ('done', 'Done')], 'State', help="Use by workflow"),
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
            line_ids = []
            for x, line_id in values['account_move_line_ids']:
                line_ids.append(line_id)

            for id, select in account_move_line_obj.get_select_to_payment(cr, uid, line_ids, context=context).items():
                account_move_line_obj.write(cr, uid, [id], {'select_to_payment': select}, context=context, update_check=False)

        return super(account_move_line_group, self).create(cr, uid, values, context=context)

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if context:
            context['display_select'] = True
        result = super(osv.osv, self).fields_view_get(cr, uid, view_id, view_type, context, toolbar=toolbar, submenu=submenu)
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
        account_move_line_obj = self.pool.get('account.move.line')
        wf_service = netsvc.LocalService("workflow")
        free_line_ids = []  # Une seule requete pour liberer les ecritures non coché
        for this in self.browse(cr, uid, ids, context=context):
            account_move = {}
            date_move = {}
            for line in this.account_move_line_ids:
                if not line.select_to_payment:
                    free_line_ids.append(line.id)
                    continue

                if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                    if not line.partner_bank_id:
                        raise osv.except_osv(_('Error'), _('No account number define'))
                    if not date_move.get(line.date_maturity, False):
                        date_move[line.date_maturity] = {line.partner_bank_id.id: [line]}
                    elif not date_move[line.date_maturity].get(line.partner_bank_id.id, False):
                        date_move[line.date_maturity][line.partner_bank_id.id] = [line]
                    else:
                        date_move[line.date_maturity][line.partner_bank_id.id].append(line)

                if not account_move.get(line.account_id.id, False):
                    account_move[line.account_id.id] = [line.id]
                else:
                    account_move[line.account_id.id].append(line.id)

            # liberation de toute les lignes non traité en une seul fois
            if free_line_ids:
                account_move_line_obj.write(cr, uid, free_line_ids, {'account_move_line_group_id': False}, context=context, update_check=False)

            # Pour chaque compte comptable
            for account_id, move_ids in account_move.items():
                account_journal_obj.make_auto_payment(cr, uid, this.journal_id, this.bank_journal_id, move_ids, this.payment_date, context=context)

            if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                buf = StringIO()
                for date, accounts in date_move.items():
                    if date:
                        self.export_bank_transfert(cr, uid, this, buf, date, accounts, context=context)

                etebac = base64.encodestring(buf.getvalue())
                buf.close()
                this.write({'etebac': etebac}, context=context)

            wf_service.trg_validate(uid, 'account.move.line.group', this.id, 'signal_done', cr)
        return True

    def button_remake_etebac(self, cr, uid, ids, context):
        for this in self.browse(cr, uid, ids, context=context):
            date_move = {}
            for line in this.account_move_line_ids:
                if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                    if not line.partner_bank_id:
                        raise osv.except_osv(_('Error'), _('No account number define'))
                    if not date_move.get(line.date_maturity, False):
                        date_move[line.date_maturity] = {line.partner_bank_id.id: [line]}
                    elif not date_move[line.date_maturity].get(line.partner_bank_id.id, False):
                        date_move[line.date_maturity][line.partner_bank_id.id] = [line]
                    else:
                        date_move[line.date_maturity][line.partner_bank_id.id].append(line)

            if this.journal_id.make_etebac and this.bank_journal_id.make_etebac:
                buf = StringIO()
                for date, accounts in date_move.items():
                    if date:
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
            res.append((read['id'], read['journal_id'][1] + "/" + read['payment_date']))
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
                bank = lines[0].partner_bank_id
                amount_lines = 0
                for line in lines:
                    amount_lines += line.credit - line.debit
                amount_lines = int(f_str(amount_lines))
                if amount_lines > 0:
                    self.etbac_format_move_destinataire(cr, uid, bank, lines[0], amount_lines, this, buf, context=context)
                amount += amount_lines
            if amount < 0:
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
        B3 = ' ' * 6  # emeteur
        C1_1 = ' '
        C1_2 = ' ' * 6
        C1_3 = str(date[8:10] + date[5:7] + date[3]).ljust(5)
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
        B3 = ' ' * 6  # emeteur
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
            bank = line.partner_bank_id
            if not bank:
                raise osv.except_osv('Information de banque', 'Le partenaire de la societe %s ne dispose d\'aucune banque' % line.partner_id.name)
            A = '06'
            B1 = line.move_type_id and line.move_type_id.code.ljust(2) or '60'
            B2 = str(num).rjust(8, '0').upper()
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
        return int(f_str(line.debit))

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
        B2 = str(num).rjust(8, '0').upper()
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
        'partner_bank_id': fields.many2one('res.partner.bank','Bank Account'),
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

    def onchange_select_to_payment(self, cr, uid, ids, partner_id, context=None):
        """
        #TODO make doc string
        Comment this/compute new values from the db/system
        """
        res = {}
        if partner_id:
            partner_obj = self.pool.get('res.partner')
            partner = partner_obj.browse(cr, uid, partner_id, context=context)
            res['value'] = {'partner_bank_id': partner.bank_ids and len(partner.bank_ids) == 1 and partner.bank_ids[0].id or False}
        return res

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        journal_pool = self.pool.get('account.journal')
        if context is None:
            context = {}
        result = super(account_move_line, self).fields_view_get(cr, uid, view_id, view_type, context=context, toolbar=toolbar, submenu=submenu)
        if view_type != 'tree':
            #Remove the toolbar from the form view
            if view_type == 'form':
                if result.get('toolbar', False):
                    result['toolbar']['action'] = []
            #Restrict the list of journal view in search view
            if view_type == 'search' and result['fields'].get('journal_id', False):
                result['fields']['journal_id']['selection'] = journal_pool.name_search(cr, uid, '', [], context=context)
                ctx = context.copy()
                #we add the refunds journal in the selection field of journal
                if context.get('journal_type', False) == 'sale':
                    ctx.update({'journal_type': 'sale_refund'})
                    result['fields']['journal_id']['selection'] += journal_pool.name_search(cr, uid, '', [], context=ctx)
                elif context.get('journal_type', False) == 'purchase':
                    ctx.update({'journal_type': 'purchase_refund'})
                    result['fields']['journal_id']['selection'] += journal_pool.name_search(cr, uid, '', [], context=ctx)
            return result
        if context.get('view_mode', False):
            return result
        fld = []
        fields = {}
        flds = []
        title = _("Accounting Entries") #self.view_header_get(cr, uid, view_id, view_type, context)

        ids = journal_pool.search(cr, uid, [])
        journals = journal_pool.browse(cr, uid, ids, context=context)
        all_journal = [None]
        common_fields = {}
        total = len(journals)
        for journal in journals:
            all_journal.append(journal.id)
            for field in journal.view_id.columns_id:
                if not field.field in fields:
                    fields[field.field] = [journal.id]
                    fld.append((field.field, field.sequence))
                    flds.append(field.field)
                    common_fields[field.field] = 1
                else:
                    fields.get(field.field).append(journal.id)
                    common_fields[field.field] = common_fields[field.field] + 1
        fld.append(('period_id', 3))
        fld.append(('journal_id', 10))
        fld.append(('journal_type', 50))
        fld.append(('journal_required_fields', 60))
        fld.append(('account_required_fields', 70))
        fld.append(('move_type_id', 80))
        fld.append(('select_to_payment', 90))
        fld.append(('partner_bank_id', 90))
        flds.append('period_id')
        flds.append('journal_id')
        flds.append(('journal_type'))
        flds.append(('journal_required_fields'))
        flds.append(('account_required_fields'))
        flds.append(('move_type_id'))
        flds.append(('select_to_payment'))
        flds.append(('partner_bank_id'))
        fields['period_id'] = all_journal
        fields['journal_id'] = all_journal
        fields['journal_type'] = all_journal
        fields['journal_required_fields'] = all_journal
        fields['account_required_fields'] = all_journal
        fields['move_type_id'] = all_journal
        fields['select_to_payment'] = all_journal
        fields['partner_bank_id'] = all_journal
        fld = sorted(fld, key=itemgetter(1))
        widths = {
            'statement_id': 50,
            'state': 60,
            'tax_code_id': 50,
            'move_id': 40,
        }

        document = etree.Element('tree', string=title, editable="top",
                                 refresh="5", on_write="on_create_write",
                                 colors="red:state=='draft';black:state=='valid'")
        fields_get = self.fields_get(cr, uid, flds, context)
        for field, _seq in fld:
            if common_fields.get(field) == total:
                fields.get(field).append(None)
            # if field=='state':
            #     state = 'colors="red:state==\'draft\'"'
            f = etree.SubElement(document, 'field', name=field)

            if field == 'debit':
                f.set('sum', _("Total debit"))

            elif field == 'credit':
                f.set('sum', _("Total credit"))

            elif field == 'move_id':
                f.set('required', 'False')

            elif field == 'account_tax_id':
                f.set('domain', "[('parent_id', '=' ,False)]")
                f.set('context', "{'journal_id': journal_id}")

            elif field == 'account_id' and journal.id:
                f.set('domain', "[('journal_id', '=', journal_id),('type','!=','view'), ('type','!=','closed')]")
                f.set('on_change', 'onchange_account_id(account_id, partner_id)')

            elif field == 'partner_id':
                f.set('on_change', 'onchange_partner_id(move_id, partner_id, account_id, debit, credit, date, journal_id)')

            elif field == 'journal_id':
                f.set('context', "{'journal_id': journal_id}")
                f.set('on_change', 'onchange_journal_id(journal_id)')

            elif field == 'statement_id':
                f.set('domain', "[('state', '!=', 'confirm'),('journal_id.type', '=', 'bank')]")
                f.set('invisible', 'True')

            elif field == 'date':
                f.set('on_change', 'onchange_date(date)')

            elif field == 'analytic_account_id':
                # Currently it is not working due to being executed by superclass's fields_view_get
                # f.set('groups', 'analytic.group_analytic_accounting')
                pass

            #elif field in ('journal_type', 'journal_required_fields', 'account_required_fields', 'select_to_payment', 'move_type_id', 'partner_bank_id'):
            #    f.set('invisible', 'True')

            elif field == 'select_to_payment':
                f.set('on_change', 'onchange_select_to_payment(partner_id)')

            if field in ('amount_currency', 'currency_id'):
                f.set('on_change', 'onchange_currency(account_id, amount_currency, currency_id, date, journal_id)')
                f.set('attrs', "{'readonly': [('state', '=', 'valid')]}")

            if field in widths:
                f.set('width', str(widths[field]))

            if field in ('journal_id',):
                f.set("invisible", "context.get('journal_id', False)")
            elif field in ('period_id',):
                f.set("invisible", "context.get('period_id', False)")

            orm.setup_modifiers(f, fields_get[field], context=context,
                                in_tree_view=True)

        result['arch'] = etree.tostring(document, pretty_print=True)
        result['fields'] = fields_get
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
                values['value']['partner_bank_id'] = partner_banks[0]

        return values

    def write(self, cr, uid, ids, values, context=None, check=True, update_check=True):
        if context is None:
            context = {}
        if context.get('update_check', None) is not None:
            update_check = context['update_check']
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


class account_payment_term(osv.osv):
    _inherit = 'account.payment.term'

    _columns = {
        'bank_transfer': fields.boolean('Bank Transfer', help='If checked, this partner will be used for bank transfer'),
    }

    _defaults = {
        'bank_transfer': lambda *a: False,
    }

account_payment_term()


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
