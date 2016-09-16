# -*- coding: utf-8 -*-
from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from django.contrib.auth.models import User
from django_723e.models.currency.models import Currency
from django_723e.models.accounts.models import Account
from django_723e.models.categories.models import Category
from django.utils.translation import ugettext as _
from django.db.models import Sum
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver

from colorfield.fields import ColorField

import calendar
import datetime

def getExchangeRate(transaction, currency, previous_exchange_rate = 1):
    """
        This function return the exchangeRate for a transaction with defined currency
        Will try multi exchange rate with a recursive algorithm
        (Jump from EUR > CHF to CHF > THB to THB > USD to calculate EUR > USD exchange rate)
    """
    # Look for change object with X > Y
    list = Change.objects.filter(new_currency=transaction.currency, date__lte=transaction.date).order_by('-date')
    for item in list:
        if item.currency == transaction.currency or item.currency == currency:
            return item.exchange_rate() * previous_exchange_rate
        else:
            return getExchangeRate(item, currency, previous_exchange_rate * item.exchange_rate())

    # Look for reverse change object like Y > X
    list = Change.objects.filter(currency=transaction.currency, date__lte=transaction.date).order_by('-date')
    for item in list:
        if item.currency == transaction.currency or item.currency == currency:
            return previous_exchange_rate / item.exchange_rate()
        else:
            return getExchangeRate(item, currency, previous_exchange_rate / item.exchange_rate())

    return None


class AbstractTransaction(models.Model):
    """
        Money transaction.
    """
    account          = models.ForeignKey(Account, related_name='transactions')
    currency         = models.ForeignKey(Currency, related_name='transactions')
    name             = models.CharField(_(u'Name'), max_length=255)
    amount           = models.FloatField(_(u'Amount'), null=False, blank=False, help_text=_(u"Credit and debit are represented by positive and negative value."))
    reference_amount = models.FloatField(_(u'Reference Amount'), null=True, blank=True, editable=False, help_text=_(u"Value based on account curency."))
    date             = models.DateField(_(u'Date'), editable=True, default=timezone.now)
    active           = models.BooleanField(_(u'Enable'), default=True, help_text=_(u"A disabled transaction will be save as a draft and not use in any report."))
    category         = models.ForeignKey(Category, related_name='transactions', blank=True, null=True)

    def __unicode__(self):
        return u"(%d) %s %s" % (self.pk, self.name, self.currency.verbose(self.amount))

    def update_amount(self, *args, **kwargs):
        if type(self) is DebitsCredits:
            # If same currency as acount, no calculation needed
            if self.currency == self.account.currency:
                self.reference_amount = self.amount
            else:
                exchange_rate = getExchangeRate(self, self.account.currency)

                if exchange_rate:
                    self.reference_amount = float("{0:.2f}".format(self.amount/exchange_rate))
                else:
                    self.reference_amount = None

    def save(self, *args, **kwargs):
        self.update_amount(*args, **kwargs)
        super(AbstractTransaction, self).save(*args, **kwargs) # Call the "real" save() method

    def value(self):
        return self.currency.verbose(self.amount)

    def isForeignCurrency(self):
        return not self.currency == self.account.currency


class DebitsCredits(AbstractTransaction):

    def __unicode__(self):
        return u"%s" % (self.name)

class Change(AbstractTransaction):
    """
        Change money in a new currency.
    """
    new_amount   = models.FloatField(_(u'New Amount'), null=False, blank=False, help_text=_(u"Amount of cash in the new currency"))
    new_currency = models.ForeignKey(Currency, related_name="change", blank= True, null= True)

    def __unicode__(self):
        return u"%d %s (%s -> %s)" % (self.pk, self.name, self.currency.verbose(self.amount), self.new_currency.verbose(self.new_amount))

    def force_save(self, *args, **kwargs):
        super(Change, self).save(*args, **kwargs) # Call the "real" save() method

    def save(self, *args, **kwargs):
        # First save to have correct value
        super(Change, self).save(*args, **kwargs) # Call the "real" save() method
        # Select closest same change pattern
        c = Change.objects.filter(date__gt=self.date, new_currency=self.new_currency).order_by("-date");
        # Select all debitsCredits transaction between this and newest one which no longer need to be updated
        if len(c) > 0:
            change = c[0]
            # Update reference_amount based on this new Change value
            list_debitscredits = DebitsCredits.objects.filter(date__gte=self.date, date__lt=change.date);
            for d in list_debitscredits:
                d.update_amount()
                d.save()
        else:
            list_debitscredits = DebitsCredits.objects.filter(date__gte=self.date);
            for d in list_debitscredits:
                d.update_amount()
                d.save()

    def exchange_rate(self):
        return float(self.new_amount) / float(self.amount)

    def new_value(self):
        return self.new_currency.verbose(self.new_amount)
