#!/usr/bin/python
"""lendingclub.py: API to access a lendingclub.com account from python"""
__version__ = "1.0"
__author__ = "Jason Ansel (jansel@csail.mit.edu)"
__copyright__ = "(C) 2012. GNU GPL 3."

import parsedatetime.parsedatetime as pdt
import datetime
import mechanize
try:
  from mechanize import ParseFile as ClientFormParseFile
except:
  from ClientForm import ParseFile as ClientFormParseFile
import sys
import re
import json
import csv
import os
import usfedhol
import random
from collections import defaultdict
from pprint import pprint
from BeautifulSoup import BeautifulSoup
from settings import login_email,login_password
from StringIO import StringIO
import logging

cachedir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cache')

notes_cache_path = cachedir+"/notes.csv"
login_uri        = "https://www.lendingclub.com/account/summary.action"
logout_uri       = 'https://www.lendingclub.com/account/logout.action'
notesrawcsv_uri  = 'https://www.lendingclub.com/account/notesRawData.action'
tradingacc_uri   = 'https://www.lendingclub.com/foliofn/tradingAccount.action'
withdraw_uri     = 'https://www.lendingclub.com/account/withdraw.action'

nobuy_reason_log = defaultdict(int)

if not os.path.isdir(cachedir):
  os.mkdir(cachedir)

def payment_prob(a, b):
  '''
  ppt[due_day] = [(delay, prob), ...]
  due_day is day of week (0=monday), delay is in days after due date, prob is from 0 to 1.0
  based on statistics for on time payments in my account
  '''
  if not usfedhol.contains_holiday(a, b):
    ppt = {0: [(4, 0.99)],
           1: [(6, 0.99)],
           2: [(6, 0.99)],
           3: [(6, 0.99)],
           4: [(6, 0.99)],
           5: [(5, 0.99)],
           6: [(4, 0.99)]}
  else:
    ppt = {0: [(4, 0.8077), (7, 0.1827)],
           1: [(6, 0.0120), (7, 0.9880)],
           2: [(6, 0.0275), (7, 0.9725)],
           3: [(6, 0.1638), (7, 0.8362)],
           4: [(6, 0.2143), (7, 0.7857)],
           5: [(6, 0.99)],
           6: [(5, 0.99)]}
  delta = (b-a).days
  return sum(map(lambda x: x[1],
                  filter(lambda x: x[0]<delta, ppt[a.weekday()])))

class LendingClubBrowser:
  def __init__(self):
    self.br = mechanize.Browser()
    self.br.set_handle_robots(False)
    self.logged_in = False

  def login(self):
    if not self.logged_in:
      logging.info('logging in as '+login_email)
      self.br.open(login_uri)
      self.br.select_form(nr=0)
      self.br['login_email'] = login_email
      self.br['login_password'] = login_password
      rsp = self.br.submit()
      open(cachedir+'/summary.html', 'wb').write(rsp.read())
      self.logged_in = True

  def logout(self):
    if self.logged_in:
      logging.info('logging out')
      self.br.open(logout_uri)
      self.logged_in = False

  def load_notes(self):
    self.notes = list()
    for row in csv.DictReader(open(notes_cache_path, 'rb')):
      try:
        self.notes.append(Note(row))
      except:
        logging.exception("loading note")
    return self.notes
  
  def load_all_details(self):
    for note in self.notes:
      note.load_details()
  
  def fetch_notes(self):
    self.login()
    logging.info('fetching notes list')
    open(notes_cache_path, 'wb').write(self.br.open(notesrawcsv_uri).read())

  def fetch_details(self, note):
    self.login()
    logging.debug('fetching note details '+str(note.note_id))
    open(note.cache_path(), 'wb').write(self.br.open(note.details_uri()).read())

  def fetch_trading_summary(self):
    self.login()
    logging.info('fetching trading summary')
    open(cachedir+'/tradingacc.html', 'wb').write(self.br.open(tradingacc_uri).read())

  def get_already_selling_ids(self):
    soup = BeautifulSoup(open(cachedir+'/tradingacc.html', 'rb'))
    #soup.findAll('table', {'id' : 'purchased-orders'})
    selling = extract_table(soup.findAll('table', {'id' : 'loans-1'})[0])
    sold = extract_table(soup.findAll('table', {'id' : 'sold-orders'})[0])
    def getnoteid(x):
      try:
        return int(x['Note ID'])
      except:
        return None
    return set(map(getnoteid, selling+sold))-set([None])

  def get_all_loan_ids(self):
    return map(lambda x: x.loan_id, self.notes)

  def scrape_all_details(self):
    self.fetch_notes()
    self.load_notes()
    for note in self.notes:
      self.fetch_details(note)

  def summary_plaintext(self):
    s = open(cachedir+'/summary.html', 'rb').read()
    s = re.sub('<[^>]+>', ' ', s)
    s = re.sub('[ \r\n\t]+', ' ', s)
    return s

  def available_cash(self):
    try:
      m = re.search("Available Cash [$]?([0-9,.]+)", self.summary_plaintext())
      return float(m.group(1).replace(',',''))
    except:
      logging.exception("failed to get available cash")
      return -1

  def sell_notes(self, notes, markup):
    if len(notes)==0:
      return
    self.login()
    logging.info("selling %d notes"%len(notes))
    self.br.open("https://www.lendingclub.com/foliofn/loans.action")
    self.br.form = make_form("https://www.lendingclub.com/foliofn/loans.action",
                             "https://www.lendingclub.com/account/loansAj.action",
                             {'namespace' : '/foliofn',
                              'method' : 'search',
                              'sortBy' : 'NoteStatus',
                              'dir' : 'asc',
                              'join_criteria' : 'all',
                              'status_criteria' : 'All',
                              'order_ids_criteria' : '0',
                              'r' : random.randint(0,90000000) })
    rs = self.br.submit()
    open(cachedir+'/sell_list.html', 'wb').write(rs.read())

    for note in notes:
      rs = self.br.open("https://www.lendingclub.com/account/updateLoanCheckBoxAj.action?note_id=%d&remove=false&namespace=/foliofn" % note.note_id)
      open(cachedir+'/sell0.html', 'wb').write(rs.read())


    rs = self.br.open("https://www.lendingclub.com/foliofn/selectLoansForSale.action")
    open(cachedir+'/sell1.html', 'wb').write(rs.read())

    self.br.select_form(name='submitLoansForSale')
    for i in xrange(len(notes)):
      try:
        for note in notes:
          if note.loan_id==int(self.br.form.find_control('loan_id', nr=i).value) \
              and note.order_id==int(self.br.form.find_control('order_id', nr=i).value):
            self.br.form.find_control('asking_price', nr=i).value = "%.2f" % (note.par_value()*markup)
        assert float(self.br.form.find_control('asking_price', nr=i).value)>0.0
      except Exception, e:
        logging.exception("fewer selling notes than expected %d" % i)
    rs = self.br.submit()
    open(cachedir+'/sell2.html', 'wb').write(rs.read())


  def fetch_trading_inventory(self,
                              remaining_payments = None,
                              from_rate          = None,
                              to_rate            = None,
                              status             = ['status_always_current'],
                              page               = 0):
    pagesize = 60
    startindex = pagesize * page
    self.login()
    logging.info("fetching trading inventory page %d"%page)
    self.br.open("https://www.lendingclub.com/foliofn/tradingInventory.action")
    self.br.select_form(nr=0)
    if from_rate is not None:
      try:
        self.br.form['search_from_rate'] = [str(from_rate)]
      except:
        log.warning("failed to set from rate %s",
                    str(self.br.form['search_from_rate']))
    if to_rate is not None:
      try:
        self.br.form['search_to_rate'] = [str(to_rate)]
      except:
        log.warning("failed to set to rate %s",
                     str(self.br.form['search_to_rate']))
    if status is not None:
      self.br.form['search_status'] = status
    if remaining_payments is not None:
      self.br.form['search_remaining_payments'] = [str(remaining_payments)]
    self.br.submit()
    rs = self.br.open('https://www.lendingclub.com/foliofn/browseNotesAj.action?'+
                      '&sortBy=markup_discount&dir=asc&startindex=%d&newrdnnum=%d&pagesize=%d'
                      % (startindex, random.randint(0,99999999), pagesize))
    open(cachedir+'/trading_inventory_page_%d.json' % page, 'wb').write(rs.read())

  def load_trading_inventory(self, page = 0):
    ti = json.load(open(cachedir+'/trading_inventory_page_%d.json' % page, 'rb'))
    assert ti['result']=='success'
    rv = list()
    for note in ti['searchresult']['loans']:
      try:
        rv.append(Note(json=note))
      except:
        logging.exception('failed to add trading note')
    rv.sort(key=Note.markup)
    return rv

  def fetch_new_inventory(self):
    self.login()
    logging.info("fetching new inventory")
    rs = self.br.open('https://www.lendingclub.com/browse/browseNotesRawDataV2.action')
    open(cachedir+'/browseNotesRawDataV2.csv', 'wb').write(rs.read())

  def load_new_inventory(self):
    rows = list()
    for row in csv.DictReader(open(cachedir+'/browseNotesRawDataV2.csv', 'rb')):
      rows.append(row)
    return rows

  def buy_new_notes(self, loan_ids, ammount_per_note):
    raise Exception("not working yet :(")
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
      rs = self.br.open("https://www.lendingclub.com/browse/updateLSRAj.action?loan_id=%d&investment_amount=%d&remove=false" % (loan_id, ammount_per_note))
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
    if len(notes)==0:
      return
    self.login()
    logging.info("buying %d trading notes"%len(notes))
    self.br.open("https://www.lendingclub.com/foliofn/tradingInventory.action")
    for si,note in enumerate(notes):
      rs = self.br.open("https://www.lendingclub.com/foliofn/noteAj.action?" +
                        "s=true&si=%d&ps=1&ni=%d&rnd=%d" %
                        (si, note.note_id, random.randint(0,2**31)))
      open(cachedir+'/buytrading0.html', 'wb').write(rs.read())

    rs = self.br.open("https://www.lendingclub.com/foliofn/completeLoanPurchase.action")
    open(cachedir+'/buytrading1.html', 'wb').write(rs.read())
    self.br.select_form(nr=0)
    rs = self.br.submit()
    open(cachedir+'/buytrading2.html', 'wb').write(rs.read())

  def transfer(self, amount):
    self.login()
    amount = str(amount)
    logging.info('Withdrawing ' + amount)
    self.br.open(withdraw_uri)
    self.br.select_form(nr=0)
    self.br['amount'] = amount
    rsp = self.br.submit()
    open(cachedir+'/transfersummary.html', 'wb').write(rsp.read())
    

class Note:
  def __init__(self, row=None, json=None):
    '''
    row = {'Accrual': '$0.00', 'AmountLent': '25.0', 'InterestRate': '0.1825',
     'LoanClass.name': 'D5', 'LoanId': '1130859', 'LoanMaturity.Maturity':
     '60', 'LoanType.Label': 'Personal', 'NextPaymentDate': 'null',
     'NoteId': '8580333', 'NoteType': '1', 'OrderId': '2283384',
     'PaymentsReceivedToDate': '0.0', 'PortfolioId': '491211', 'PortfolioName':
     'New', 'PrincipalRemaining': '25.0', 'Status': 'In Review', 'Trend':
     'FLAT'}
     json = {"accrued_interest": 0.32, "asking_price": 22.01, "checkboxes": false,
      "credit_score_trend": 0, "days_since_payment": 30, "loanClass": 60,
      "loanGUID": 684868, "loanGrade": "D", "loanRate": "16.02", "loan_status":
      "Current", "markup_discount": "0.84", "noteId": 3918723, "orderId":
      1318992, "outstanding_principal": "21.50", "remaining_pay": 48,
      "selfNote": 0, "title": "2011 debt consolidation", "ytm": "14.72"}
    '''
    if row is not None:
      assert json is None
      self.note_id      = int(row['NoteId'])
      self.loan_id      = int(row['LoanId'])
      self.order_id     = int(row['OrderId'])
      self.portfolio    = row['PortfolioName']
      self.status       = row['Status']
      self.accrual      = float(row['Accrual'].replace('$',''))
      self.principal    = float(row['PrincipalRemaining'].replace('$',''))
      self.rate         = float(row['InterestRate'])
      self.term         = int(row['LoanMaturity.Maturity'])
      self.mine         = True
      self.last_payment = None
      self.asking_price = None
      if row['NextPaymentDate'] != 'null' and self.principal > 0.0:
        self.next_payment = parsedate(row['NextPaymentDate'])
      else:
        self.next_payment = None
      self.days_since_payment = None
      self.payments_received = None
    else:
      assert json is not None
      self.note_id      = int(json['noteId'])
      self.loan_id      = int(json['loanGUID'])
      self.order_id     = int(json['orderId'])
      self.portfolio    = None
      self.status       = json['loan_status']
      self.accrual      = float(json['accrued_interest'])
      self.principal    = float(json['outstanding_principal'])
      self.asking_price = float(json['asking_price'])
      try:
        self.rate       = float(json['ytm'])
      except:
        logging.warning("could not parse rate: " +json['ytm'])
        self.rate       = 0.0
      self.term         = int(json['loanClass'])
      self.mine         = bool(json['selfNote'])
      self.next_payment = None
      try:
        self.days_since_payment = int(json['days_since_payment'])
      except:
        self.days_since_payment = None
      self.payments_received = int(json['loanClass'])-int(json['remaining_pay'])

    self.credit_history = None
    self.collection_log = None
    self.payment_history = None

  def par_value(self):
    return self.principal+self.accrual

  def details_uri(self):
    if self.mine:
      return 'https://www.lendingclub.com/account/loanPerf.action?loan_id=%d&order_id=%d&note_id=%d' % (
          self.loan_id, self.order_id, self.note_id )
    else:
      return 'https://www.lendingclub.com/foliofn/loanPerf.action?loan_id=%d&order_id=%d&note_id=%d' % (
          self.loan_id, self.order_id, self.note_id )

  def cache_path(self):
    return '%s/%d.html' % (cachedir, self.note_id)

  def load_details(self):
    soup=BeautifulSoup(open(self.cache_path(), 'rb').read())
    self.credit_history  = extract_credit_history(soup)
    self.collection_log  = extract_collection_log(soup)
    self.payment_history = extract_payment_history(soup)
    if self.next_payment is None and self.payment_history:
      if self.payment_history[0].status in ('Scheduled', 'Processing...'):
        self.next_payment = self.payment_history[0].due

  def can_sell(self):
    return self.status not in ('Fully Paid', 'Default', 'Charged Off')

  def sell_reasons(self):
    if self.status == 'Fully Paid':
      return []

    class RT:
      failed      = 'failed payment'
      collection  = 'collections log activity'
      graceperiod = 'payment in grace period'
      late        = 'late payment'
      credit120   = 'credit score drop >120 points'
      credit80    = 'credit score drop >80 points'
      credit40    = None# 'credit score drop >40 points'
      expected99  = 'expected a payment by now (>99%)'
      expected90  = 'expected a payment by now (>90%)'
    reasons = list()

    if len(self.collection_log)>0:
      s=repr(self.collection_log).lower()
      if 'failed' in s:
        reasons.append(RT.failed)
      else:
        reasons.append(RT.collection)

    if self.payment_history:
      late = filter(lambda x: x.status not in ('Completed - on time', 'Scheduled', 'Processing...'),
                    self.payment_history)
      if late:
        if filter(lambda x: x.status not in ('Completed - in grace period'), late):
          reasons.append(RT.late)
        else:
          reasons.append(RT.graceperiod)

    if self.credit_history:
      if self.creditdeltamin()  <-120:
        reasons.append(RT.credit120)
      elif self.creditdeltamin()<-80:
        reasons.append(RT.credit80)
      elif self.creditdeltamin()<-40:
        reasons.append(RT.credit40)

    if self.next_payment:
      if datetime.datetime.now().hour >= 18:
        p = payment_prob(self.next_payment, datetime.date.today()+datetime.timedelta(days=1))
      else:
        p = payment_prob(self.next_payment, datetime.date.today())
      if p>.99:
        reasons.append(RT.expected99)
      elif p>.90:
        reasons.append(RT.expected90)

    return filter(lambda x: x is not None, reasons)
  
  def want_sell(self):
    return len(self.sell_reasons())>0

  def want_update(self, days):
    return self.next_payment \
        and self.portfolio != 'Bad' \
        and payment_prob(self.next_payment, datetime.date.today()+datetime.timedelta(days=days)) > 0.5


  def want_buy_no_details(self,
                          days_since_payment,
                          from_rate,
                          to_rate,
                          price,
                          markup,
                          payments_received,
                          creditdelta=None,
                          reasonlog=nobuy_reason_log,
                          ):
    if self.mine:
      reasonlog['mine']+=1
      return False
    if self.status != 'Current':
      reasonlog['not current']+=1
      return False
    if not self.asking_price or self.markup()>markup:
      reasonlog['markup > %.4f' % markup]+=1
      return False
    if self.asking_price>price:
      reasonlog['price > %.2f' % price]+=1
      return False
    if not self.rate or self.rate<100.0*from_rate:
      reasonlog['rate < %.2f' % from_rate]+=1
      return False
    if not self.rate or self.rate>=100.0*to_rate:
      reasonlog['rate >= %.2f' % to_rate]+=1
      return False
    if not self.days_since_payment or self.days_since_payment>days_since_payment:
      reasonlog['payment soon']+=1
      return False
    if not self.payments_received or self.payments_received<payments_received:
      reasonlog['too new']+=1
      return False
    return True

  def want_buy(self, creditdelta, reasonlog=nobuy_reason_log, **kwargs):
    if not self.want_buy_no_details(reasonlog=reasonlog, **kwargs):
      return False
    if self.next_payment is None:
      reasonlog['no details']+=1
      return False
    if payment_prob(self.next_payment, datetime.date.today()+datetime.timedelta(days=5))>0.0:
      reasonlog['expecting payment soon']+=1
      return False
    if self.creditdeltamin()<creditdelta:
      reasonlog['credit score']+=1
      return False
    if self.want_sell():
      reasonlog[self.sell_reasons()[0]]+=1
      return False
    return True


  def markup(self):
    try:
      return self.asking_price/self.par_value()
    except:
      return 99999999.0

  def creditdeltamin(self):
    if self.credit_history[-1].high < self.credit_history[0].high:
      return self.credit_history[-1].high - self.credit_history[0].low
    if self.credit_history[-1].high > self.credit_history[0].high:
      return self.credit_history[-1].low - self.credit_history[0].high
    return 0

  def debug(self, o=sys.stderr, histn=5):
    print >>o, "note", self.note_id, self.portfolio, self.status, self.par_value()
    if self.asking_price:
      print >>o, "asking price", self.asking_price, "(%.2f%%)"%(self.asking_price/self.par_value()*100.0),'rate',self.rate
      print >>o, "days since payment", self.days_since_payment
    if self.credit_history:
      print >>o, "credit", str(self.credit_history[-1]), 'changed by at least', self.creditdeltamin()
    if self.payment_history:
      print >>o, "payment history (last %d of %d records)" % (len(self.payment_history[0:histn]), len(self.payment_history))
      print >>o, '> '+'\n> '.join(map(str, self.payment_history[0:histn]))
    if self.collection_log:
      print >>o, "collection log (%d events)" % len(self.collection_log)
      print >>o, '> '+'\n> '.join(map(str, self.collection_log))

  def payment_ammount(self):
    try:
      return self.payment_history[0].ammount()
    except:
      guess = self.principal*(self.rate/12.0)/(1-math.e**(-self.term*math.log(1+self.rate/12.0)))
      logging.debug("unknown payment amount, guessing %.2f for note %d" % (guess, self.note_id))
      return guess

  def payment_interest(self):
    try:
      return self.payment_history[1].interest()
    except:
      guess = self.principal*(self.rate/12.0)
      logging.debug("unknown interest amount, guessing %.2f for note %d" % (guess, self.note_id))
      return guess

  def paytime_stats(self, stats):
    for p in filter(PaymentHistoryItem.is_complete, self.payment_history):
      if usfedhol.contains_holiday(p.due, p.complete):
        stats[p.due.weekday()][(p.complete - p.due).days] += 1


class CreditPoint:
  def __init__(self, date, low, high):
    self.date = date
    self.low = low
    self.high = high

  def __repr__(self):
    return "CreditPoint(%s, %d, %d)" % (repr(self.date), self.low, self.high)
  
  def __str__(self):
    return "%d-%d" % (self.low, self.high)

class CollectionLogItem:
  def __init__(self, date, msg):
    self.date = date
    self.msg = msg
  
  def __repr__(self):
    return "CollectionLogItem(%s, '%s')" % (repr(self.date), self.msg)
  
  def __str__(self):
    return "%s %s" % (str(self.date), self.msg)

class PaymentHistoryItem:
  def __init__(self, due, complete, status, ammounts):
    self.due = due
    self.complete = complete
    self.status = status
    self.ammounts = ammounts

  def ammount(self):
    try:
      return float(self.ammounts[0])
    except:
      return 0.0
  
  def interest(self):
    try:
      return float(self.ammounts[2])
    except:
      return 0.0

  def __repr__(self):
    return "PaymentHistoryItem(%s, %s, '%s', %s)" % (
      repr(self.due), repr(self.complete), self.status, repr(self.ammounts)
      )

  def __str__(self):
    if self.complete:
      delta=(self.complete-self.due).days
      return "%s(+%d) %s" % (str(self.due), delta, self.status)
    return "%s     %s" % (str(self.due), self.status)

  def is_complete(self):
    return self.status == 'Completed - on time'

def parsedate(s):
  p=pdt.Calendar()
  if s=='--':
    return None
  return datetime.date(*p.parse(s)[0][0:3])

def extract_row(tr, tag='td'):
  rv = list()
  for td in tr.findAll(tag):
    s=' '.join(map(lambda x: str(x).strip(), td.findAll(text=True)))
    s=re.sub('[ \r\n\t]+', ' ', s)
    rv.append(s)
  return rv

def extract_table(table):
  headers = extract_row(table, tag='th')
  rv=list()
  for tr in table.findAll('tr'):
    row = extract_row(tr)
    if len(row) == len(headers):
      rv.append(dict(zip(headers, row)))
  return rv

def extract_credit_history(soup):
  def parsecredit(s):
    s=s.strip()
    if s == '780+':
      return 780,850
    if s == '499-':
      return 350,499
    l,h = map(int, s.split('-'))
    return l,h
  rv=list()
  for table in soup.findAll('table', {'id' : 'trend-data' } ):
    for tr in table.findAll('tr'):
      tds = extract_row(tr)
      if len(tds) == 2:
        rv.append(CreditPoint(*((parsedate(tds[1]),)+parsecredit(tds[0]))))
  return rv


def make_form(src, dest, values):
  req = StringIO()
  print >>req, '<form method="POST" action="%s">' % dest
  for k, v in values.items():
    print >>req, '<input type="text" name="%s"   value="%s">' % (str(k), str(v))
  print >>req, '</form>'
  return ClientFormParseFile(StringIO(req.getvalue()), src)[0]

def extract_collection_log(soup):
  rv=list()
  for table in soup.findAll('table', {'id' : 'lcLoanPerfTable2' } ):
    for tr in table.findAll('tr'):
      date, msg = extract_row(tr)
      date = parsedate(re.sub('[(].*[)]','',date))
      msg = str(msg)
      rv.append(CollectionLogItem(date,msg))
  return rv

def extract_payment_history(soup):
  rv=list()
  for table in soup.findAll('div', {'id' : 'lcLoanPerf1' } ):
    for tr in table.findAll('tr'):
      row = extract_row(tr)
      if len(row) > 3:
        rv.append(PaymentHistoryItem(parsedate(row[0]),
                                     parsedate(row[1]),
                                     row[-1],
                                     map(lambda x: re.sub('^[$]','',x), row[2:-1])))
  return rv

def build_payment_prob_table(notes):
  stats = defaultdict(lambda : defaultdict(int)) 
  for note in notes:
    note.paytime_stats(stats)
  def to_percents(m):
    v=float(sum(m.values()))
    return map(lambda x: (x[0], round(x[1]/v, 4)), m.items())
  pprint(dict(map(lambda x: (x[0], to_percents(x[1])), stats.items())))


