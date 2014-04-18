#!/usr/bin/python
"""lendingclub.py: API to access a lendingclub.com account from python"""
__version__ = '2.1'
__author__ = 'Jason Ansel (jasonansel@jasonansel.com)'
__copyright__ = '(C) 2012-2014. GNU GPL 3.'

import abc
import collections
import csv
import datetime
import gzip
import json
import logging
import math
import mechanize
import os
import random
import re
import shutil
import sys
import time
import urllib
import urlparse
from BeautifulSoup import BeautifulSoup
from pprint import pprint
from pprint import pformat
from StringIO import StringIO

import usfedhol
from settings import login_email
from settings import login_password


try:
  from mechanize import ParseFile as ClientFormParseFile
except ImportError:
  from ClientForm import ParseFile as ClientFormParseFile

try:
    import parsedatetime.parsedatetime as pdt
except ImportError:
    import parsedatetime as pdt


log = logging.getLogger(__name__)


class LendingClubBrowser(object):
  def __init__(self, cache_dir=None):
    if cache_dir is None:
      cache_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                               'cache')
    self.cache_dir = cache_dir
    if not os.path.isdir(self.cache_dir):
      os.mkdir(self.cache_dir)
    self.browser = mechanize.Browser()
    self.browser.set_handle_robots(False)
    self.logged_in = False
    self.notes = None

  def login(self):
    if not self.logged_in:
      log.info('logging in as ' + login_email)
      self.browser.open('https://www.lendingclub.com/account/summary.action')
      self.browser.select_form(nr=0)
      self.browser['login_email'] = login_email
      self.browser['login_password'] = login_password
      rsp = self.browser.submit()
      open(self.cache_dir + '/summary.html', 'wb').write(rsp.read())
      self.logged_in = True

  def logout(self):
    if self.logged_in:
      log.info('logging out')
      self.browser.open('https://www.lendingclub.com/account/logout.action')
      self.logged_in = False

  def fetch_notes(self):
    self.login()
    log.info('fetching notes list (csv)')
    with open(self.cache_dir + '/notes.csv', 'wb') as fd:
      fd.write(self.browser.open(
        'https://www.lendingclub.com/account/notesRawData.action').read())

  def load_notes(self):
    self.notes = list()
    for row in csv.DictReader(open(self.cache_dir + '/notes.csv', 'rb')):
      try:
        self.notes.append(Note(row, lendingclub=self))
      except:
        log.exception('loading note')
    return self.notes

  def load_all_details(self):
    for note in self.notes:
      note.load_details()

  def fetch_details(self, note):
    self.login()
    log.debug('fetching note details ' + str(note.note_id))
    open(note.cache_path(), 'wb').write(
      self.browser.open(note.details_uri()).read())

  def fetch_trading_summary(self):
    self.login()
    log.info('fetching trading summary')
    open(self.cache_dir + '/tradingacc.html', 'wb').write(
      self.browser.open(
        'https://www.lendingclub.com/foliofn/tradingAccount.action').read())

  def get_already_selling_ids(self):
    soup = BeautifulSoup(open(self.cache_dir + '/tradingacc.html', 'rb'))
    # soup.findAll('table', {'id' : 'purchased-orders'})
    selling = extract_table(soup.findAll('table', {'id': 'loans-1'})[0])
    sold = extract_table(soup.findAll('table', {'id': 'sold-orders'})[0])

    def getnoteid(x):
      try:
        return int(x['Note ID'])
      except:
        return None

    return set(map(getnoteid, selling + sold)) - set([None])

  def get_buying_loan_ids(self):
    rv = list()
    try:
      soup = BeautifulSoup(open(self.cache_dir + '/tradingacc.html', 'rb'))
      table = soup.findAll('table',
                           {'id': 'purchased-orders'})[0]
      for row in table.findAll('tr'):
        for a in row.findAll('a'):
          try:
            rv.append(int(urlparse.parse_qs(
              urlparse.urlparse(
                urllib.unquote(a['href'])).query)['loan_id'][0]))
          except:
            log.exception('failed to parse buying loan id')
    except:
      log.exception('failed to load tradingacc.html')
    return rv

  def get_all_loan_ids(self):
    buying = self.get_buying_loan_ids()
    owned = map(lambda x: x.loan_id, self.notes)
    return set(owned + buying)

  def scrape_all_details(self):
    self.fetch_notes()
    self.load_notes()
    for note in self.notes:
      self.fetch_details(note)

  def summary_plaintext(self):
    s = open(self.cache_dir + '/summary.html', 'rb').read()
    s = re.sub('<[^>]+>', ' ', s)
    s = re.sub('[ \r\n\t]+', ' ', s)
    return s

  def available_cash(self):
    try:
      m = re.search('Available Cash [$]?([0-9,.]+)', self.summary_plaintext())
      return float(m.group(1).replace(',', ''))
    except:
      log.exception('failed to get available cash')
      return -1

  def compute_can_sell_ids(self):
    """
    Example of note data returned
    {"currPayStatus": 11, "portfolioName": "New", "portfolioId": 491211,
     "status": "Issued", "principalRemaining": "25.00",
     "purpose": "Other", "noteId": 44777646, "loanLength": 60,
     "accrual": "0.00", "loanAmt": "$20,000", "rate": "G3 : 25.89%",
     "amountLent": 25, "credit_score_trend": 1, "alreadySelected": False,
     "noteType": 1, "loanType": "Personal", "nextPayment": "May 14, 2014",
     "paymentReceived": "0.00", "isInBankruptcy": False,
     "orderId": 21100971, "loanId": 14588413}
    """
    try:
      with open(self.cache_dir + '/sell1.json', 'rb') as fd:
        data = json.load(fd)
      loans = data['searchresult']['loans']

      can_sell = []
      for note in loans:
        if note['isInBankruptcy']:
          continue
        if note['status'] in ('Default', 'Charged Off', 'Fully Paid'):
          continue
        if note['currPayStatus'] == 13:
          continue
        can_sell.append(note['noteId'])

      log.info('can_sell data for %s loans, %s sellable', len(loans),
               len(can_sell))
      return set(can_sell)
    except KeyboardInterrupt:
      raise
    except Exception:
      log.exception('unhandled error while finding notes that can be sold')
    return set()

  def sell_notes(self, notes, markup):
    if len(notes) == 0:
      return
    self.login()
    log.info('selling %d notes' % len(notes))
    rs = self.browser.open(
      'https://www.lendingclub.com/foliofn/sellNotes.action')
    open(self.cache_dir + '/sell0.html', 'wb').write(rs.read())

    rs = self.browser.open((
      'https://www.lendingclub.com/foliofn/sellNotesAj.action' +
      '?sortBy=nextPayment&dir=desc&startindex=0&pagesize=10000' +
      '&namespace=/foliofn&r={0}&join_criteria=all' +
      '&status_criteria=All&order_ids_criteria=0').format(random.random()))
    # server insists on sending us gziped data for this, extract it...
    open(self.cache_dir + '/sell1.gz', 'wb').write(rs.read())
    try:
      gz = gzip.GzipFile(self.cache_dir + '/sell1.gz', 'rb')
      data = gz.read()
      gz.close()
      rs.set_data(data)
      self.browser.set_response(rs)
      open(self.cache_dir + '/sell1.json', 'wb').write(rs.read())
    except:
      log.warning('error extracting notes list', exc_info=True)
      shutil.copy(self.cache_dir + '/sell1.gz', self.cache_dir + '/sell1.json')

    rs = self.browser.open(
      'https://www.lendingclub.com/foliofn/getSelectedNoteCountAj.action'
      '?rnd=%d' % random.randint(0, 999999999))
    open(self.cache_dir + '/sell2.html', 'wb').write(rs.read())

    can_sell = self.compute_can_sell_ids()  # reads sell1.json

    # These cookies may be needed by server:
    # loans.isFromServer=; loans.sortBy=nextPayment; loans.sortDir=desc;
    # loans.pageSize=10000; loans.sIndex=0;')

    notes_for_sale = []
    for note in notes:
      if note.note_id not in can_sell:
        log.warning('Trying to sell a note that cant be sold %s', note.note_id)
        continue
      rs = self.browser.open(
        'https://www.lendingclub.com/foliofn/updateLoanCheckBoxAj.action' +
        '?note_id={0}&remove=false&namespace=/foliofn'.format(note.note_id))
      open(self.cache_dir + '/sell3.html', 'wb').write(rs.read())
      notes_for_sale.append(note)

    notes = notes_for_sale
    if not notes:
      log.info('nothing for sale')
      return

    rs = self.browser.open(
      'https://www.lendingclub.com/foliofn/selectLoansForSale.action')
    open(self.cache_dir + '/sell4.html', 'wb').write(rs.read())

    self.browser.select_form(name='submitLoansForSale')
    for i in xrange(len(notes)):
      try:
        for note in notes:
          if note.loan_id == int(
              self.browser.form.find_control('loan_id', nr=i).value) \
            and note.order_id == int(
                  self.browser.form.find_control('order_id', nr=i).value):
            self.browser.form.find_control('asking_price',
                                           nr=i).value = '%.2f' % (
              note.par_value() * markup)
        assert float(self.browser.form.find_control(
          'asking_price', nr=i).value) > 0.0
      except Exception, e:
        log.exception('fewer selling notes than expected %d' % i)
    rs = self.browser.submit()
    open(self.cache_dir + '/sell5.html', 'wb').write(rs.read())
    log.info(extract_msg_from_html(
      self.cache_dir + '/sell5.html',
      r'(You have made .* available for sale)'))

  def fetch_trading_inventory(self, **options_given):
    # defaults are generated by loading the page, clicking search, and copying
    # the query string from the url
    defaults = urlparse.parse_qs(
      'mode=search&search_from_rate=0.04&search_to_rate=0.27&'
      'loan_status=loan_status_issued&loan_status=loan_status_current&'
      'never_late=true&fil_search_term=term_36&fil_search_term=term_60&'
      'search_loan_term=term_36&search_loan_term=term_60&remp_min=1&'
      'remp_max=60&askp_min=0.00&askp_max=Any&markup_dis_min=-100&'
      'markup_dis_max=15&opr_min=0.00&opr_max=Any&ona_min=25&ona_max=Any&'
      'ytm_min=0&ytm_max=Any&credit_score_min=600&credit_score_max=850&'
      'credit_score_trend=UP&credit_score_trend=DOWN&credit_score_trend=FLAT&'
      'exclude_invested_loans=false')
    options = dict()
    for name, default in defaults.iteritems():
      options[name] = options_given.pop(name, default)
    if options_given:
      log.error('unknown options: %s', str(options_given))
    options_url = (
      'https://www.lendingclub.com/foliofn/tradingInventory.action?{0}'
      .format(urllib.urlencode(sorted(options.items()), True)))
    self.login()
    log.info('fetching: %s', options_url)
    rs = self.browser.open(
      'https://www.lendingclub.com/foliofn/tradingInventory.action')
    open(self.cache_dir + '/inventory0.html', 'wb').write(rs.read())
    rs = self.browser.open(options_url)
    open(self.cache_dir + '/inventory1.html', 'wb').write(rs.read())
    #rs = self.br.open('https://www.lendingclub.com/foliofn/browseNotesAj.action'
    #                  '?sortBy=markup_discount&dir=asc&startindex=0'
    #                  '&newrdnnum=46907133&pagesize=1000')
    #open(cachedir + '/inventory2.json', 'wb').write(rs.read())
    with open(os.path.join(self.cache_dir, 'tradinginventory.csv'), 'wb') as fd:
      fd.write(self.browser.open(
        'https://www.lendingclub.com/foliofn/notesRawData.action').read())
    log.info('fetching trading notes list csv done')

  def load_trading_inventory(self):
    rv = list()
    for row in csv.DictReader(open(os.path.join(self.cache_dir,
                                                'tradinginventory.csv'), 'rb')):
      try:
        rv.append(Note(trading_row=row, lendingclub=self))
      except KeyboardInterrupt:
        raise
      except:
        log.exception('loading trading note')
    return rv

  def fetch_new_inventory(self):
    self.login()
    log.info('fetching new inventory')
    rs = self.browser.open(
      'https://www.lendingclub.com/browse/browseNotesRawDataV2.action')
    open(self.cache_dir + '/browseNotesRawDataV2.csv', 'wb').write(rs.read())

  def load_new_inventory(self):
    rows = list()
    for row in csv.DictReader(
        open(self.cache_dir + '/browseNotesRawDataV2.csv', 'rb')):
      rows.append(row)
    return rows

  def buy_new_notes(self, loan_ids, amount_per_note):
    raise Exception('not working yet :(')
    '''
    if len(loan_ids)==0:
      return
    self.login()
    logging.info("buying %d new notes"%len(loan_ids))
    # 1 https://www.lendingclub.com/browse/browse.action
    rs = self.br.open("https://www.lendingclub.com/browse/browse.action")
    rs = self.br.open("https://www.lendingclub.com/browse/getDefaultFilterAj.action?a1=a&rnd=%d" % random.randint(0, 2**31))
    rs = self.br.open("https://www.lendingclub.com/browse/cashBalanceAj.action?rnd=%d" % random.randint(0, 2**31))
    rs = self.br.open("https://www.lendingclub.com/data/portfolio?method=getPortfolioSummary&rnd=%d" % random.randint(0, 2**31))
    rs = self.br.open("https://www.lendingclub.com/browse/browseNotesAj.action?method=getResultsInitial&startindex=0&pagesize=15&r=%d" % random.randint(0, 2**31))
    open(cachedir+'/buynew1.html', 'wb').write(rs.read())

    # 2 https://www.lendingclub.com/browse/updateLSRAj.action?loan_id=1463534&investment_amount=25&remove=false
    for loan_id in loan_ids:
      rs = self.br.open("https://www.lendingclub.com/browse/updateLSRAj.action?loan_id=%d&investment_amount=%d&remove=false" % (loan_id, amount_per_note))
      open(cachedir+'/buynew2.html', 'wb').write(rs.read())
      if json.load(open(cachedir+'/buynew2.html'))["result"] != "success":
        logging.error("error while trying to select note")
        return

    # 3 https://www.lendingclub.com/data/portfolio?method=addToPortfolioNew&rnd=1344314408656
    rs = self.br.open("https://www.lendingclub.com/data/portfolio?method=addToPortfolioNew&rnd=%d" % random.randint(0, 2**31))
    open(cachedir+'/buynew3.html', 'wb').write(rs.read())

    # 4 https://www.lendingclub.com/portfolio/viewOrder.action
    rs = self.br.open("https://www.lendingclub.com/portfolio/viewOrder.action")
    open(cachedir+'/buynew4.html', 'wb').write(rs.read())

    # 5 https://www.lendingclub.com/portfolio/placeOrder.action
    rs = self.br.open("https://www.lendingclub.com/portfolio/placeOrder.action")
    open(cachedir+'/buynew5.html', 'wb').write(rs.read())

    # 6 submit form (notes are now purchased)
    self.br.select_form(nr=0)
    rs = self.br.submit()
    open(cachedir+'/buynew6.html', 'wb').write(rs.read())
    '''

  def buy_trading_notes(self, notes):
    if len(notes) == 0:
      return
    self.login()
    log.info('buying %d trading notes' % len(notes))
    self.browser.open(
      'https://www.lendingclub.com/foliofn/tradingInventory.action')
    for si, note in enumerate(notes):
      rs = self.browser.open(
        'https://www.lendingclub.com/foliofn/noteAj.action?' +
        's=true&si=%d&ps=1&ni=%d&rnd=%d' %
        (si, note.note_id, random.randint(0, 2 ** 31)))
      open(self.cache_dir + '/buytrading0.json', 'wb').write(rs.read())

    rs = self.browser.open(
      'https://www.lendingclub.com/foliofn/addToCartAj.action?rnd=%d' %
      random.randint(0, 2 ** 31))
    open(self.cache_dir + '/buytrading1.json', 'wb').write(rs.read())
    log.info('trading cart: %s',
             open(self.cache_dir + '/buytrading1.json').read())

    rs = self.browser.open('https://www.lendingclub.com/foliofn/cart.action')
    open(self.cache_dir + '/buytrading2.html', 'wb').write(rs.read())
    self.browser.select_form(nr=0)
    rs = self.browser.submit()
    open(self.cache_dir + '/buytrading3.html', 'wb').write(rs.read())
    log.info(extract_msg_from_html(
      self.cache_dir + '/buytrading3.html',
      r'(We have received your order to buy [^.]*)'))

  def withdraw(self, amount):
    """
    Transfer money out of lendingclub into the default bank account
    """
    self.login()
    amount = str(amount)
    log.info('Withdrawing ' + amount)
    self.browser.open('https://www.lendingclub.com/account/withdraw.action')
    self.browser.select_form(nr=0)
    self.browser['amount'] = amount
    rsp = self.browser.submit()
    open(self.cache_dir + '/transfersummary.html', 'wb').write(rsp.read())

  def due_date_payed_fraction(self, date):
    """
    Return fraction of notes due on date that are payed as a tuple
    """
    payed = 0
    count = 0
    for note in self.notes:
      if note.next_payment and note.next_payment.day == date.day:
        if note.next_payment == date:
          count += 1
        elif note.next_payment > date:
          payed += 1
          count += 1
    return payed, count

  def buy_trading_with_strategy(self, strategy):
    """Examine the trading inventory buy the notes indicated by strategy"""
    assert isinstance(strategy, BuyTradingStrategy)
    if not self.notes:
      self.load_notes()
    cash = self.available_cash()
    if cash + strategy.reserve_cash < 25:
      log.info('Not enough cash, skipping buying step %s', cash)
      return []
    else:
      log.info('Running buy strategy %s with %s cash',
               strategy.__class__.__name__, cash)
    all_loan_ids = set(self.get_all_loan_ids())
    buy = list()
    count_total = 0
    count_fetched = 0
    self.fetch_trading_inventory(**strategy.search_options)
    notes = self.load_trading_inventory()
    notes.sort(key=strategy.sort_key)
    for note in notes:
      try:
        count_total += 1
        if note.loan_id in all_loan_ids:
          strategy.reasons['already invested in loan'] += 1
          continue
        if note.asking_price + strategy.reserve_cash > cash:
          strategy.reasons['not enough cash'] += 1
          continue
        if not strategy.initial_filter(note):
          continue
        if note.last_updated() < (datetime.datetime.now() -
                                    datetime.timedelta(days=14)):
          time.sleep(1)
          self.fetch_details(note)
          count_fetched += 1
        note.load_details()
        if not strategy.initial_filter(note):
          continue
        if strategy.details_filter(note):
          buy.append(note)
          all_loan_ids.add(note.loan_id)
          cash -= note.asking_price
      except KeyboardInterrupt:
        raise
      except:
        log.exception('failed to load trading note')
        strategy.reasons['error'] += 1
    log.info('examined %s of %s trading nodes, buying %s cash left: %s',
             count_fetched, count_total, len(buy), cash)
    log.info('will automatically buy ids: %s',
             str(map(lambda x: x.note_id, buy)))
    log.info('buy reasons: \n%s',
             pformat(sorted(strategy.reasons.items(), key=lambda x: -x[1]),
                     indent=2, width=100))
    self.buy_trading_notes(buy)

    with open(os.path.join(self.cache_dir, 'buy_log.txt'), 'w') as o:
      for note in buy:
        note.debug(o)
        print >> o

    return buy

  def sell_with_strategy(self, strategy, markup, fraction):
    """Examine fraction of all notes and sell those found by strategy"""
    assert isinstance(strategy, SellStrategy)
    assert 0 <= fraction <= 1.0
    assert 0.5 <= markup <= 1.5
    all_notes = self.load_notes()
    if fraction == 0:
      return
    already_selling_ids = self.get_already_selling_ids()
    can_sell = filter(lambda x: x.note_id not in already_selling_ids, all_notes)
    can_sell = filter(Note.can_sell, can_sell)
    can_sell.sort(key=Note.last_updated)
    count = int(round(fraction * len(can_sell)))
    in_window = can_sell[:count]
    if not can_sell:
      return
    log.info('total range %s to %s', can_sell[0].last_updated(),
             can_sell[-1].last_updated())
    if not in_window:
      return
    log.info('check range %s to %s', in_window[0].last_updated(),
             in_window[-1].last_updated())
    log.info('checking %s notes of %s sellable and %s total',
             len(in_window), len(can_sell), len(all_notes))
    sell = []
    for note in in_window:
      try:
        if not strategy.initial_filter(note):
          continue
        time.sleep(1)
        self.fetch_details(note)
        note.load_details()
        if not note.can_sell():
          continue
        if not strategy.initial_filter(note):
          continue
        if not strategy.details_filter(note):
          continue
        sell.append(note)
      except KeyboardInterrupt:
        raise
      except:
        log.exception('failed to load note')
        strategy.reasons['error'] += 1
    log.info('will automatically sell %s ids: %s', len(sell),
             str(map(lambda x: x.note_id, sell)))
    log.info('sell reasons: %s',
             pformat(sorted(strategy.reasons.items(), key=lambda x: -x[1]),
                     indent=2, width=100))
    if len(sell) > 0:
      self.sell_notes(sell, markup)

    with open(os.path.join(self.cache_dir, 'sell_log.txt'), 'w') as o:
      for note in sell:
        note.debug(o)
        strategy.reset_reasons()
        strategy.initial_filter(note)
        strategy.details_filter(note)
        print >> o, 'sell reasons', strategy.reasons.items()
        print >> o

    return sell

  def sell_duplicate_notes(self, markup):
    already_selling_ids = set(self.get_already_selling_ids())
    active = self.load_notes()
    active = list(
      filter(lambda x: x.note_id not in already_selling_ids, active))
    active.sort(key=lambda x: x.loan_id)
    dups = list()
    last_id = None
    for note in active:
      if note.loan_id == last_id:
        dups.append(note)
      last_id = note.loan_id
    log.info('selling %d duplicate notes' % len(dups))
    self.sell_notes(dups, markup)


class Note:
  def __init__(self, row=None, trading_row=None, lendingclub=None):
    self.lendingclub = lendingclub
    if row is not None:
      """
      row = {'Accrual': '$0.00', 'AmountLent': '25.0', 'InterestRate':
      '0.1825',
       'LoanClass.name': 'D5', 'LoanId': '1130859', 'LoanMaturity.Maturity':
       '60', 'LoanType.Label': 'Personal', 'NextPaymentDate': 'null',
       'NoteId': '8580333', 'NoteType': '1', 'OrderId': '2283384',
       'PaymentsReceivedToDate': '0.0', 'PortfolioId': '491211',
       'PortfolioName': 'New', 'PrincipalRemaining': '25.0', 'Status':
       'In Review', 'Trend': 'FLAT'}
      """
      assert trading_row is None
      self.note_id = int(row['NoteId'])
      self.loan_id = int(row['LoanId'])
      self.order_id = int(row['OrderId'])
      self.portfolio = row['PortfolioName']
      self.status = row['Status']
      self.accrual = float(row['Accrual'].replace('$', ''))
      self.principal = float(row['PrincipalRemaining'].replace('$', ''))
      self.rate = float(row['InterestRate'])
      self.term = int(row['LoanMaturity.Maturity'])
      self.mine = True
      self.last_payment = None
      self.asking_price = None
      if row['NextPaymentDate'] != 'null' and self.principal > 0.0:
        self.next_payment = parsedate(row['NextPaymentDate'])
      else:
        self.next_payment = None
      self.days_since_payment = None
      self.never_late = None
    else:
      """
      {'OrderId': '12760991', 'Status': 'IN_LISTING', 'Date/Time Listed':
      '11/07/2013', 'Markup/Discount': '-$1.43', 'AskPrice': '0.69', 'LoanId':
      '780797', 'OutstandingPrincipal': '0.69', 'CreditScoreTrend': 'DOWN',
      'DaysSinceLastPayment': '4', 'YTM': '0.01%', 'AccruedInterest': '0.0',
      ' FICO End Range': '715-719', 'NeverLate': 'False', 'NoteId': '5100247'}
      """

      assert trading_row is not None
      self.note_id = int(trading_row['NoteId'])
      self.loan_id = int(trading_row['LoanId'])
      self.order_id = int(trading_row['OrderId'])
      self.portfolio = None
      self.status = trading_row['Status']
      self.accrual = float(trading_row['AccruedInterest'])
      self.principal = float(trading_row['OutstandingPrincipal'])
      self.asking_price = float(trading_row['AskPrice'])
      try:
        self.rate = float(trading_row['YTM'].replace('%', ''))
      except:
        self.rate = 0.0
      if trading_row['NeverLate'].lower() not in ('true', 'false'):
        log.warning('unknown value for NeverLate: %s', trading_row['NeverLate'])
      self.never_late = (trading_row['NeverLate'].lower() == 'true')
      self.mine = self.note_id in [x.note_id for x in lendingclub.notes]
      self.term = None
      self.next_payment = None
      try:
        self.days_since_payment = int(trading_row['DaysSinceLastPayment'])
      except:
        self.days_since_payment = None

    self.credit_history = None
    self.collection_log = None
    self.payment_history = None

  def par_value(self):
    return self.principal + self.accrual

  def details_uri(self):
    if self.mine:
      return ('https://www.lendingclub.com/account/loanPerf.action'
              '?loan_id=%d&order_id=%d&note_id=%d' % (
                self.loan_id, self.order_id, self.note_id))
    else:
      return ('https://www.lendingclub.com/foliofn/loanPerf.action'
              '?loan_id=%d&order_id=%d&note_id=%d' % (
                self.loan_id, self.order_id, self.note_id))

  def cache_path(self):
    return '%s/%d.html' % (self.lendingclub.cache_dir, self.note_id)

  def last_updated(self):
    try:
      return datetime.datetime.fromtimestamp(
        os.path.getmtime(self.cache_path()))
    except OSError:
      return datetime.datetime(2000, 1, 1)

  def load_details(self):
    soup = BeautifulSoup(open(self.cache_path(), 'rb').read())
    self.credit_history = extract_credit_history(soup)
    self.collection_log = extract_collection_log(soup)
    self.payment_history = extract_payment_history(soup)
    if self.next_payment is None and self.payment_history:
      if ('Scheduled' in self.payment_history[0].status or
              'Processing' in self.payment_history[0].status):
        self.next_payment = self.payment_history[0].due

  def can_sell(self):
    if self.status in ('Fully Paid', 'Default', 'Charged Off'):
      return False
    if self.next_payment is None:
      return False
    if (self.collection_log and
            any(item.is_bankruptcy() for item in self.collection_log)):
      return False
    return (self.next_payment > datetime.date.today() or
            self.next_payment < datetime.date.today() - datetime.timedelta(days=7))

  def markup(self):
    if self.par_value() == 0:
      return 99999999.0
    try:
      return self.asking_price / self.par_value()
    except:
      log.exception('error computing markup value')
      return 99999999.0

  def creditdeltamin(self):
    if self.credit_history[-1].high < self.credit_history[0].high:
      return self.credit_history[-1].high - self.credit_history[0].low
    if self.credit_history[-1].high > self.credit_history[0].high:
      return self.credit_history[-1].low - self.credit_history[0].high
    return 0

  def debug(self, o=sys.stderr, histn=5):
    print >> o, 'note', self.note_id, self.portfolio, self.status, self.par_value(
    )
    if self.asking_price:
      print >> o, 'asking price', self.asking_price, '(%.2f%%)' % (
        self.asking_price / self.par_value() * 100.0), 'rate', self.rate
      print >> o, 'days since payment', self.days_since_payment
    if self.credit_history:
      print >> o, 'credit', str(
        self.credit_history[-1]), 'changed by at least', self.creditdeltamin()
    if self.payment_history:
      print >> o, 'payment history (last %d of %d records)' % (
        len(self.payment_history[0:histn]), len(self.payment_history))
      print >> o, '> ' + '\n> '.join(map(str, self.payment_history[0:histn]))
    if self.collection_log:
      print >> o, 'collection log (%d events)' % len(self.collection_log)
      print >> o, '> ' + '\n> '.join(map(str, self.collection_log))

  def payment_amount(self):
    try:
      return self.payment_history[0].amount()
    except:
      guess = self.principal * (self.rate / 12.0) / (
        1 - math.e ** (-self.term * math.log(1 + self.rate / 12.0)))
      log.debug('unknown payment amount, guessing %.2f for note %d' %
                (guess, self.note_id))
      return guess

  def payment_interest(self):
    try:
      return self.payment_history[1].interest()
    except:
      guess = self.principal * (self.rate / 12.0)
      log.debug('unknown interest amount, guessing %.2f for note %d' %
                (guess, self.note_id))
      return guess

  def paytime_stats(self, stats):
    for p in filter(PaymentHistoryItem.is_complete, self.payment_history):
      if usfedhol.contains_holiday(p.due, p.complete):
        stats[p.due.weekday()][(p.complete - p.due).days] += 1


class CreditPoint(object):
  def __init__(self, date, low, high):
    self.date = date
    self.low = low
    self.high = high

  def __repr__(self):
    return 'CreditPoint(%s, %d, %d)' % (repr(self.date), self.low, self.high)

  def __str__(self):
    return '%d-%d' % (self.low, self.high)


class CollectionLogItem(object):
  def __init__(self, date, msg):
    self.date = date
    self.msg = msg

  def __repr__(self):
    return "CollectionLogItem(%s, '%s')" % (repr(self.date), self.msg)

  def __str__(self):
    return '%s %s' % (str(self.date), self.msg)

  def is_bankruptcy(self):
    return re.search(r'Bankruptcy', self.msg, re.IGNORECASE) is not None


class PaymentHistoryItem(object):
  def __init__(self, due, complete, status, amounts):
    self.due = due
    self.complete = complete
    self.status = status
    self.amounts = amounts

  def amount(self):
    try:
      return float(self.amounts[0])
    except:
      return 0.0

  def interest(self):
    try:
      return float(self.amounts[2])
    except:
      return 0.0

  def __repr__(self):
    return "PaymentHistoryItem(%s, %s, '%s', %s)" % (
      repr(self.due), repr(self.complete), self.status, repr(self.amounts)
    )

  def __str__(self):
    if self.complete:
      delta = (self.complete - self.due).days
      return '%s(+%d) %s' % (str(self.due), delta, self.status)
    return '%s     %s' % (str(self.due), self.status)

  def is_complete(self):
    return self.status == 'Completed - on time'


class Strategy(object):
  __metaclass__ = abc.ABCMeta

  def __init__(self):
    self.reset_reasons()

  def reset_reasons(self):
    self.reasons = collections.defaultdict(int)

  @abc.abstractmethod
  def initial_filter(self, note):
    """
    Filter notes based on summary data (before details are loaded)
    Returns true if note details should be loaded
    """
    pass

  @abc.abstractmethod
  def details_filter(self, note):
    """
    Filter notes after details are loaded
    Returns true if note should be sold/purchased
    """
    pass


class BuyTradingStrategy(Strategy):
  @property
  def search_options(self):
    """Options to pass to search filters"""
    return {}

  @property
  def reserve_cash(self):
    """Dont buy notes that would push cash below this value"""
    return 0.0

  def sort_key(self, note):
    """tuple to sort (prioritize) buying decisions by"""
    assert isinstance(note, Note)
    return note.markup(),


class SellStrategy(Strategy):
  pass


def parsedate(s):
  p = pdt.Calendar()
  if s == '--':
    return None
  return datetime.date(*p.parse(s)[0][0:3])


def extract_row(tr, tag='td'):
  rv = list()
  for td in tr.findAll(tag):
    s = ' '.join(map(lambda x: str(x).strip(), td.findAll(text=True)))
    s = re.sub('[ \r\n\t]+', ' ', s)
    rv.append(s)
  return rv


def extract_table(table):
  headers = extract_row(table, tag='th')
  rv = list()
  for tr in table.findAll('tr'):
    row = extract_row(tr)
    if len(row) == len(headers):
      rv.append(dict(zip(headers, row)))
  return rv


def extract_credit_history(soup):
  def parsecredit(s):
    s = s.strip()
    if s == '780+':
      return 780, 850
    if s == '499-':
      return 350, 499
    l, h = map(int, s.split('-'))
    return l, h

  rv = list()
  for table in soup.findAll('table', {'id': 'trend-data'}):
    for tr in table.findAll('tr'):
      tds = extract_row(tr)
      if len(tds) == 2:
        rv.append(CreditPoint(*((parsedate(tds[1]),) + parsecredit(tds[0]))))
  return rv


def make_form(src, dest, values):
  req = StringIO()
  print >> req, '<form method="POST" action="%s">' % dest
  for k, v in values.items():
    print >> req, '<input type="text" name="%s"   value="%s">' % (
      str(k), str(v))
  print >> req, '</form>'
  return ClientFormParseFile(StringIO(req.getvalue()), src)[0]


def extract_collection_log(soup):
  rv = list()
  for table in soup.findAll('table', {'id': 'lcLoanPerfTable2'}):
    for tr in table.findAll('tr'):
      date, msg = extract_row(tr)
      date = parsedate(re.sub('[(].*[)]', '', date))
      msg = str(msg)
      rv.append(CollectionLogItem(date, msg))
  return rv


def extract_payment_history(soup):
  rv = list()
  for table in soup.findAll('div', {'id': 'lcLoanPerf1'}):
    for tr in table.findAll('tr'):
      row = extract_row(tr)
      if len(row) > 3:
        rv.append(PaymentHistoryItem(parsedate(row[0]), parsedate(
          row[1]), row[-1], map(lambda x: re.sub('^[$]', '', x), row[2:-1])))
  return rv


def extract_msg_from_html(filename, regexp):
  try:
    html = open(filename).read()
    html = re.sub(r'<[^<]+>', '', html)
    html = re.sub(r'\s+', ' ', html)
    m = re.search(regexp, html)
    if m:
      return m.group(1)
    else:
      return 'No confirmation found'
  except:
    log.exception('failed to extract message')
    return ''


def build_payment_prob_table(notes):
  stats = collections.defaultdict(lambda: collections.defaultdict(int))
  for note in notes:
    note.paytime_stats(stats)

  def to_percents(m):
    v = float(sum(m.values()))
    return map(lambda x: (x[0], round(x[1] / v, 4)), m.items())

  pprint(dict(map(lambda x: (x[0], to_percents(x[1])), stats.items())))


def payment_prob(a, b):
  """
  ppt[due_day] = [(delay, prob), ...]
  due_day is day of week (0=monday), delay is in days after due date, prob is from 0 to 1.0
  based on statistics for on time payments in my account
  """
  if not usfedhol.contains_holiday(a, b):
    ppt = {0: [(7, 0.99)],
           1: [(6, 0.99)],
           2: [(6, 0.99)],
           3: [(6, 0.99)],
           4: [(6, 0.99)],
           5: [(5, 0.99)],
           6: [(5, 0.99)]}
  else:
    ppt = {0: [(4, 0.8077), (7, 0.1827)],
           1: [(6, 0.0120), (7, 0.9880)],
           2: [(6, 0.0275), (7, 0.9725)],
           3: [(6, 0.1638), (7, 0.8362)],
           4: [(6, 0.2143), (7, 0.7857)],
           5: [(6, 0.99)],
           6: [(5, 0.99)]}
  delta = (b - a).days
  return sum(map(lambda x: x[1],
                 filter(lambda x: x[0] < delta, ppt[a.weekday()])))

