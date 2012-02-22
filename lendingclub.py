#!/usr/bin/python
"""lendingclub.py: API to access a lendingclub.com account from python"""
__version__ = "1.0"
__author__ = "Jason Ansel (jansel@csail.mit.edu)"
__copyright__ = "(C) 2012. GNU GPL 3."

import parsedatetime.parsedatetime as pdt
import datetime
import mechanize
import sys
import re
import pickle
import csv
import os
import usfedhol
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
      self.br.submit()
      self.logged_in = True

  def logout(self):
    if self.logged_in:
      logging.info('logging out')
      self.br.open(logout_uri)
      self.logged_in = False

  def load_notes(self):
    self.notes = list()
    for row in csv.DictReader(open(notes_cache_path)):
      self.notes.append(Note(row))
    return self.notes
  
  def load_all_details(self):
    for note in self.notes:
      note.load_details()
  
  def fetch_notes(self):
    self.login()
    logging.info('fetching notes list')
    open(notes_cache_path, 'w').write(self.br.open(notesrawcsv_uri).read())

  def fetch_details(self, note):
    self.login()
    logging.info('fetching note details '+str(note.note_id))
    open(note.cache_path(), 'w').write(self.br.open(note.details_uri()).read())

  def fetch_trading_summary(self):
    self.login()
    logging.info('fetching trading summary')
    open(cachedir+'/tradingacc.html', 'w').write(self.br.open(tradingacc_uri).read())

  def get_already_selling_ids(self):
    soup = BeautifulSoup(open(cachedir+'/tradingacc.html'))
    #soup.findAll('table', {'id' : 'purchased-orders'})
    selling = extract_table(soup.findAll('table', {'id' : 'loans-1'})[0])
    sold = extract_table(soup.findAll('table', {'id' : 'sold-orders'})[0])
    return set(map(lambda x: int(x['Note ID']), selling+sold))

  def scrape_all_details(self):
    self.fetch_notes()
    self.load_notes()
    for note in self.notes:
      self.fetch_details(note)

class Note:
  def __init__(self, row):
    '''
    {'Accrual': '$0.00', 'AmountLent': '25.0', 'InterestRate': '0.1825',
     'LoanClass.name': 'D5', 'LoanId': '1130859', 'LoanMaturity.Maturity':
     '60', 'LoanType.Label': 'Personal', 'NextPaymentDate': 'null',
     'NoteId': '8580333', 'NoteType': '1', 'OrderId': '2283384',
     'PaymentsReceivedToDate': '0.0', 'PortfolioId': '491211', 'PortfolioName':
     'New', 'PrincipalRemaining': '25.0', 'Status': 'In Review', 'Trend':
     'FLAT'}
    '''
    self.row      = row
    self.note_id  = int(row['NoteId'])
    self.loan_id  = int(row['LoanId'])
    self.order_id = int(row['OrderId'])
    self.portfolio = row['PortfolioName']
    self.status   = row['Status']
    if row['NextPaymentDate'] != 'null':
      self.next_payment = parsedate(row['NextPaymentDate'])
    else:
      self.next_payment = None
    self.credit_history = None
    self.collection_log = None
    self.payment_history = None

  def details_uri(self):
    return 'https://www.lendingclub.com/account/loanPerf.action?loan_id=%d&order_id=%d&note_id=%d' % (
        self.loan_id, self.order_id, self.note_id )
  
  def cache_path(self):
    return '%s/%d.html' % (cachedir, self.note_id)

  def load_details(self):
    logging.debug("loading details for note "+str(self.note_id))
    soup=BeautifulSoup(open(self.cache_path()).read())
    self.credit_history  = extract_credit_history(soup)
    self.collection_log  = extract_collection_log(soup)
    self.payment_history = extract_payment_history(soup)

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
      expected75  = 'expected a payment by now (>75%)'
      expected65  = 'expected a payment by now (>65%)'
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
      elif p>.75:
        reasons.append(RT.expected75)
      elif p>.65:
        reasons.append(RT.expected65)

    return filter(lambda x: x is not None, reasons)
  
  def want_sell(self):
    return len(self.sell_reasons())>0

  def want_update(self, days):
    return self.next_payment \
        and self.portfolio != 'Bad' \
        and payment_prob(self.next_payment, datetime.date.today()+datetime.timedelta(days=days)) > 0.5

  def creditdeltamin(self):
    if self.credit_history[-1].high < self.credit_history[0].high:
      return self.credit_history[-1].high - self.credit_history[0].low
    if self.credit_history[-1].high > self.credit_history[0].high:
      return self.credit_history[-1].low - self.credit_history[0].high
    return 0

  def debug(self, o=sys.stderr, histn=5):
    print >>o, "note", self.note_id, self.portfolio, self.status
    if self.credit_history:
      print >>o, "credit", str(self.credit_history[-1]), 'changed by at least', self.creditdeltamin()
    if self.payment_history:
      print >>o, "payment history (last %d of %d records)" % (len(self.payment_history[0:histn]), len(self.payment_history))
      print >>o, '> '+'\n> '.join(map(str, self.payment_history[0:histn]))
    if self.collection_log:
      print >>o, "collection log (%d events)" % len(self.collection_log)
      print >>o, '> '+'\n> '.join(map(str, self.collection_log))

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


