from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PartnerExchangeRate(models.Model):
    _name = 'partner.exchange.rate'
    _description = 'Partner Exchange Rate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char('Name', required=True, translate=True, tracking=True, copy=False, index=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company.id)
    rate_amount = fields.Float("Rate", required=True, tracking=True)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_exchange_rate_id = fields.Many2one('partner.exchange.rate', "Partner Exchange Rate", tracking=True,
                                               )
    rate_amount = fields.Float("Rate", related='partner_exchange_rate_id.rate_amount')
