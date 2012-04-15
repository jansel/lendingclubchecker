#!/usr/bin/python
"""lcchecker.py: Create a list of sell recommendations based on recent notes"""
__version__ = "1.0"
__author__ = "Jason Ansel (jansel@csail.mit.edu)"
__copyright__ = "(C) 2012. GNU GPL 3."

import lendingclub
import argparse
import logging
import smtplib
import datetime
import sys 
import time
import os
import re
from pprint import pprint
from email.mime.text import MIMEText
from collections import defaultdict
from settings import smtp_server, smtp_username, smtp_password, login_email

try:
  from cStringIO import StringIO
except:
  from StringIO import StringIO

try:
  import cPickle as pickle
except:
  import pickle

buy_options = {
  'days_since_payment' : 24,
  'markup'             : 1.001,
  'payments_received'  : 4,
  'from_rate'          : 0.17,
  'price'              : 25.0,
  'creditdelta'        : -10,
  }

notes_pickle_file = lendingclub.cachedir+'/notes.pk'

def load_active_notes(lc, update, window):
  if update:
    lc.fetch_notes()
    lc.fetch_trading_summary()
  active = lc.load_notes()
  
  sellingids = lc.get_already_selling_ids()
  active = filter(lambda x: x.note_id not in sellingids, active)
  active = filter(lambda x: x.want_update(window), active)

  logging.debug("active notes = "+str(len(active)))

  for note in active:
    if update:
      lc.fetch_details(note)
    try:
      note.load_details()
    except:
      if not update:
        lc.fetch_details(note)
        note.load_details()
      else:
        logging.exception("failed to load note "+str(note.id)) 


  pickle.dump(active, open(notes_pickle_file, 'wb'), pickle.HIGHEST_PROTOCOL)
  return active

def create_msg(lc, sell, active, args, o):
  print >>o, "examined", len(active), 'notes,', len(sell), "sell suggestions:"
  print >>o
  for note in sell:
    note.debug(o)
    print >>o, 'sell reasons', note.sell_reasons()
    print >>o
  if sell:
    if args.sell:
      print >>o, "will automatically sell note ids:",
    else:
      print >>o, "suggested sell note ids:",
    print >>o,  map(lambda x: x.note_id, sell)

  print >>o
  v1 = 0.0
  i1 = 0.0
  print >>o, "available cash %.2f" % lc.available_cash()
  for days in xrange(1,33):
    s = filter(lambda x: x.want_update(days), active)
    v2 = sum(map(lendingclub.Note.payment_ammount, s))
    i2 = sum(map(lendingclub.Note.payment_interest, s))
    v = v2-v1
    iv = i2-i1
    v1=v2
    i1=i2
    if v>0:
      day = (datetime.date.today()+datetime.timedelta(days=days-1)).strftime("%a, %b %d")
      print >>o, "expecting %5.2f (%5.2f interest) on" % (v,iv), day
    if len(s)==len(active):
      break

  print >>o

def send_email(me, you, subject, body):
  logging.info("sending email '%s' to %s" % (subject, you))
  msg = MIMEText(body)
  msg['Subject'] = subject
  msg['From'] = me
  msg['To'] = you
  s = smtplib.SMTP(smtp_server)
  s.starttls()
  if smtp_username:
    s.login(smtp_username, smtp_password)
  s.sendmail(me, [you], msg.as_string())
  s.quit()

def get_buy_suggestions(lc, args, o):
  if args.update:
    lc.fetch_trading_inventory(from_rate=float(buy_options['from_rate'])-0.01,
                               remaining_payments=60-int(buy_options['payments_received']))
  all_loan_ids = set(lc.get_all_loan_ids())
  invall = lc.load_trading_inventory()
  inv = filter(lambda x: x.want_buy_no_details(**buy_options), invall)
  buy = list()
  cash = lc.available_cash()
  nfetched = 0
  for note in inv:
    try:
      if note.loan_id in all_loan_ids:
        continue
      if note.asking_price > cash:
        continue
      if args.update:
        lc.fetch_details(note)
      nfetched += 1
      note.load_details()
      if note.want_buy(**buy_options):
        buy.append(note)
        all_loan_ids.add(note.loan_id)
        cash -= note.asking_price
    except:
      logging.exception("failed to load trading note")

  print >>o
  print >>o, "examined",nfetched,"of",len(inv),"trading notes,", len(buy),"buy suggestions:"
  print >>o
  for note in buy:
    note.debug(o)
    print >>o

  if buy:
    if args.buy:
      print >>o,"will automatically buy ids:",map(lambda x: x.note_id, buy)
    else:
      print >>o,"suggested buy ids:",map(lambda x: x.note_id, buy)


  print >>o
  print >>o,"nobuy_reason_log %d/%d:"%(len(invall)-len(inv),len(invall))
  pprint(sorted(lendingclub.nobuy_reason_log.items(), key=lambda x: -x[1]),
         stream=o, indent=2, width=100)

  return buy

def main(args):
  o = StringIO()
  logstream = StringIO()
  if args.debug:
    loglevel = logging.DEBUG
  elif args.quiet:
    loglevel = logging.WARNING
  else:
    loglevel = logging.INFO
  logging.basicConfig(level=loglevel, stream=logstream)

  try:

    if args.weekday and datetime.date.today().weekday() in (5,6):
      logging.info("aborting due to it not being a weekday")
      return

    lc = lendingclub.LendingClubBrowser()

    if args.frompickle:
      active = pickle.load(open(notes_pickle_file, 'rb'))
    else:
      active = load_active_notes(lc, args.update, args.window)

    sell = filter(lendingclub.Note.want_sell, active)

    if len(sell)>0 and args.sell:
      lc.sell_notes(sell, args.sellmarkup)

    create_msg(lc, sell, active, args, o)

    buy = get_buy_suggestions(lc, args, o)

    if len(buy)>0 and args.buy:
      lc.buy_trading_notes(buy)

    lc.logout()

    #clean cache dir:
    for fname in os.listdir(lendingclub.cachedir):
      if re.search("[.]html", fname):
        fpath = os.path.join(lendingclub.cachedir, fname)
        st = os.stat(fpath)
        daysold = (time.time()-max(st.st_atime, st.st_mtime))/3600/24
        if daysold>45:
          logging.info("deleting %s, %.0f days old"%(fname,daysold))
          os.unlink(fpath)

  except:
    logging.exception("unknown error")
  finally:
    body = o.getvalue()
    log = logstream.getvalue()
    if log:
      body+="\n\nlog:\n"+log

    if not args.quiet:
      print
      print body
    elif log:
      print
      print "log:"
      print log

    if body and args.email:
      today = str(datetime.date.today())
      subject = "[LendingClubChecker] sell %d, buy %d on %s" % (len(sell), len(buy), today)
      send_email(args.emailfrom, args.emailto, subject, body)
    

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='check notes coming due soon for ones that should be sold')
  parser.add_argument('--window', '-w', default=5, type=int,
                      help='fetch notes we expect to be payed in the next N days')
  parser.add_argument('--noupdate', '-n', action='store_false', dest='update',
                      help="dont fetch details for notes we have cached data for")
  parser.add_argument('--frompickle', action='store_true',
                      help="read active notes from last run cache")
  parser.add_argument('--debug', '-v', action='store_true',
                      help="print more debugging info")
  parser.add_argument('--quiet', '-q', action='store_true',
                      help="print less debugging info")
  parser.add_argument('--emailfrom', default=login_email, help='report email from address')
  parser.add_argument('--emailto',   default=login_email, help='report email to address')
  parser.add_argument('--email', action='store_true', help="send an email report to "+login_email)
  parser.add_argument('--weekday', action='store_true', help="abort the script if run on the weekend")
  parser.add_argument('--sell', action='store_true', help="automatically sell all suggestions")
  parser.add_argument('--sellmarkup', default=0.993,
                      type=float, help='markup for --sell (default 0.993)')
  parser.add_argument('--buy', action='store_true', help="automatically buy all suggestions")
  parser.add_argument('--buyopt', nargs=2, action='append', help="set option for buying notes")
  parser.add_argument('--buyoptlist', action='store_true', help="print buyopts and exit")
  args = parser.parse_args()
  assert args.sellmarkup>0.4
  assert args.sellmarkup<1.6

  if args.buyopt:
    for k,v in map(tuple, args.buyopt):
      assert buy_options.has_key(k)
      buy_options[k] = type(buy_options[k])(v)

  if args.buyoptlist:
    pprint(buy_options)
  else:
    main(args)



