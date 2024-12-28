from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    currency_name = fields.Char(related='currency_id.name')
    expense_currency_exchange_account_id = fields.Many2one(
        'account.account',
        string='Loss Exchange Rate Account',
        default=lambda self: self.env.company.expense_currency_exchange_account_id,
    )
    income_currency_exchange_account_id = fields.Many2one(
        'account.account',
        string='Gain Exchange Rate Account',
        default=lambda self: self.env.company.income_currency_exchange_account_id,
    )
    exchange_rate = fields.Float('Exchange Rate', compute='_compute_partner_exchange_rate', store=True)
    partner_exchange_rate_id = fields.Many2one('partner.exchange.rate', "Partner Exchange Rate",
                                               compute='_compute_partner_exchange_rate', store=True)
    exchange_rate_difference = fields.Float('Exchange Rate Difference', compute='_compute_exchange_rate_differences',
                                            store=True)

    @api.depends('amount', 'currency_id', 'exchange_rate')
    def _compute_exchange_rate_differences(self):
        for wizard in self:
            _logger.info('Computing exchange rate differences for payment ID: %s', wizard.id)
            company_currency = wizard.company_id.currency_id
            if wizard.exchange_rate and wizard.currency_id != company_currency:
                # Calculate the payment amount in company currency using standard rate
                standard_company_amount = wizard.currency_id._convert(
                    wizard.amount,
                    company_currency,
                    wizard.company_id,
                    wizard.date
                )
                _logger.info('Standard company amount: %s %s', standard_company_amount, company_currency.name)

                # Calculate the payment amount in company currency using custom exchange rate
                custom_company_amount = wizard.amount / wizard.exchange_rate
                _logger.info('Custom company amount: %s %s', custom_company_amount, company_currency.name)

                # Calculate the difference
                exchange_rate_difference = standard_company_amount - custom_company_amount
                _logger.info('Exchange rate difference: %s %s', exchange_rate_difference, company_currency.name)

                wizard.exchange_rate_difference = exchange_rate_difference
            else:
                wizard.exchange_rate_difference = 0.0

    @api.depends('partner_id')
    def _compute_partner_exchange_rate(self):
        for rec in self:
            _logger.info('Computing partner exchange rate for payment ID: %s', rec.id)
            if rec.partner_id:
                rec.partner_exchange_rate_id = rec.partner_id.partner_exchange_rate_id
                rec.exchange_rate = rec.partner_id.rate_amount
                _logger.info('Partner exchange rate: %s', rec.exchange_rate)
            else:
                rec.partner_exchange_rate_id = False
                rec.exchange_rate = 0.0
                _logger.info('No partner set, exchange rate set to 0.0')

    @api.model
    def create(self, vals):
        _logger.info('Creating payment with values: %s', vals)
        payment = super(AccountPayment, self).create(vals)
        if payment.partner_type == 'customer' and payment.currency_id.name == 'IQD' \
                and not payment.is_internal_transfer and payment.payment_type == 'inbound':
            _logger.info('Processing IQD customer payment ID: %s', payment.id)
            if payment.partner_exchange_rate_id and payment.exchange_rate and payment.exchange_rate_difference:
                _logger.info('Exchange rate difference detected: %s', payment.exchange_rate_difference)
                if payment.exchange_rate_difference > 0:
                    account_id = payment.income_currency_exchange_account_id
                    _logger.info('Using income exchange account: %s', account_id.name)
                else:
                    account_id = payment.expense_currency_exchange_account_id
                    _logger.info('Using expense exchange account: %s', account_id.name)
                custom_exchange = round(payment.amount / payment.exchange_rate, 2)
                debit_line = payment.move_id.line_ids.filtered(lambda l: l.debit > 0)
                credit_line = payment.move_id.line_ids.filtered(lambda l: l.credit > 0)
                if debit_line:
                    # payment_amount = debit_line.debit
                    exchange_amount = round(abs(payment.exchange_rate_difference), 2)
                    reduced_amount = round(custom_exchange - exchange_amount, 2)

                    line_vals = [
                        (1, debit_line[0].id, {
                            'debit': reduced_amount,
                            'credit': 0.0,
                        }),
                        (1, credit_line.id, {
                            'credit': custom_exchange,
                            'debit': 0.0,
                        }),
                        (0, 0, {
                            'move_id': payment.move_id.id,
                            'account_id': account_id.id,
                            'credit': 0.0,
                            'debit': exchange_amount,
                            'name': 'Exchange Difference',
                            'currency_id': payment.move_id.currency_id.id,
                        })
                    ]
                    _logger.info('Updating move lines with values: %s', line_vals)
                    payment.move_id.write({'line_ids': line_vals})
        return payment

    def write(self, vals):
        _logger.info('Writing payment with values: %s', vals)
        res = super(AccountPayment, self).write(vals)
        for payment in self:
            if payment.partner_type == 'customer' and payment.currency_id.name == 'IQD' \
                    and not payment.is_internal_transfer and payment.payment_type == 'inbound':
                _logger.info('Processing IQD customer payment ID: %s', payment.id)
                if payment.partner_exchange_rate_id and payment.exchange_rate and payment.exchange_rate_difference:
                    _logger.info('Exchange rate difference detected: %s', payment.exchange_rate_difference)
                    if payment.exchange_rate_difference > 0:
                        account_id = payment.income_currency_exchange_account_id
                        _logger.info('Using income exchange account: %s', account_id.name)
                    else:
                        account_id = payment.expense_currency_exchange_account_id
                        _logger.info('Using expense exchange account: %s', account_id.name)

                    custom_exchange = round(payment.amount / payment.exchange_rate, 2)
                    debit_line = payment.move_id.line_ids.filtered(lambda l: l.debit > 0)
                    credit_line = payment.move_id.line_ids.filtered(lambda l: l.credit > 0)
                    exchange_line = payment.move_id.line_ids.filtered(lambda l: l.name == 'Exchange Difference')
                    if exchange_line and len(debit_line) == 1:
                        # payment_amount = debit_line.debit
                        exchange_amount = round(abs(payment.exchange_rate_difference), 2)
                        reduced_amount = round(custom_exchange - exchange_amount, 2)

                        line_vals = [
                            (1, debit_line[0].id, {
                                'debit': reduced_amount,
                                'credit': 0.0,
                            }),
                            (1, credit_line.id, {
                                'credit': custom_exchange,
                                'debit': 0.0,
                            }),
                            (0, 0, {
                                'move_id': payment.move_id.id,
                                'account_id': account_id.id,
                                'credit': 0.0,
                                'debit': exchange_amount,
                                'name': 'Exchange Difference',
                                'currency_id': payment.move_id.currency_id.id,
                            })
                        ]
                        _logger.info('____________if len(debit_line) == 1:_______________________', )
                        for i in payment.move_id.line_ids:
                            _logger.info('before: %s %s %s', i.name, i.debit, i.credit)
                        _logger.info('Updating move lines with values: %s', line_vals)
                        _logger.info('__________________________________________', )
                        payment.move_id.write({'line_ids': line_vals})
                    elif exchange_line and len(debit_line) > 1:
                        # payment_amount = debit_line.debit
                        exchange_amount = round(abs(payment.exchange_rate_difference), 2)
                        reduced_amount = round(custom_exchange - exchange_amount, 2)

                        line_vals = [
                            (1, debit_line[0].id, {
                                'debit': reduced_amount,
                                'credit': 0.0,
                            }),
                            (1, credit_line.id, {
                                'credit': custom_exchange,
                                'debit': 0.0,
                            }),
                            (1, debit_line[1].id, {
                                'credit': 0.0,
                                'debit': exchange_amount,
                                'name': 'Exchange Difference',
                            })
                        ]
                        _logger.info('____________if len(debit_line) == 1:_______________________', )
                        for i in payment.move_id.line_ids:
                            _logger.info('before: %s %s %s', i.name, i.debit, i.credit)
                        _logger.info('Updating move lines with values: %s', line_vals)
                        _logger.info('__________________________________________', )
                        payment.move_id.write({'line_ids': line_vals})
        return res


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    currency_name = fields.Char(related='currency_id.name')
    expense_currency_exchange_account_id = fields.Many2one(
        'account.account',
        string='Loss Exchange Rate Account',
        default=lambda self: self.env.company.expense_currency_exchange_account_id,
    )
    income_currency_exchange_account_id = fields.Many2one(
        'account.account',
        string='Gain Exchange Rate Account',
        default=lambda self: self.env.company.income_currency_exchange_account_id,
    )
    exchange_rate = fields.Float('Exchange Rate', compute='_compute_partner_exchange_rate', store=True)
    partner_exchange_rate_id = fields.Many2one('partner.exchange.rate', "Partner Exchange Rate",
                                               compute='_compute_partner_exchange_rate', store=True)
    exchange_rate_difference = fields.Float('Exchange Rate Difference', compute='_compute_exchange_rate_differences',
                                            store=True)

    @api.depends('amount', 'currency_id', 'exchange_rate')
    def _compute_exchange_rate_differences(self):
        for wizard in self:
            _logger.info('Computing exchange rate differences for payment register ID: %s', wizard.id)
            company_currency = wizard.company_id.currency_id
            if wizard.exchange_rate and wizard.currency_id != company_currency:
                standard_company_amount = wizard.currency_id._convert(
                    wizard.amount,
                    company_currency,
                    wizard.company_id,
                    wizard.payment_date
                )
                _logger.info('Standard company amount: %s %s', standard_company_amount, company_currency.name)

                custom_company_amount = wizard.amount / wizard.exchange_rate
                _logger.info('Custom company amount: %s %s', custom_company_amount, company_currency.name)

                exchange_rate_difference = standard_company_amount - custom_company_amount
                _logger.info('Exchange rate difference: %s %s', exchange_rate_difference, company_currency.name)

                wizard.exchange_rate_difference = exchange_rate_difference
            else:
                wizard.exchange_rate_difference = 0.0

    @api.depends('partner_id')
    def _compute_partner_exchange_rate(self):
        for rec in self:
            _logger.info('Computing partner exchange rate for payment register ID: %s', rec.id)
            if rec.partner_id:
                rec.partner_exchange_rate_id = rec.partner_id.partner_exchange_rate_id
                rec.exchange_rate = rec.partner_id.rate_amount
                _logger.info('Partner exchange rate: %s', rec.exchange_rate)
            else:
                rec.partner_exchange_rate_id = False
                rec.exchange_rate = 0.0
                _logger.info('No partner set, exchange rate set to 0.0')
