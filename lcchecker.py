#!/usr/bin/python
"""lcchecker.py: Create a list of sell recommendations based on recent notes"""
__version__ = '3.0'
__author__ = 'Jason Ansel (jansel@jansel.net)'
__copyright__ = '(C) 2012-2014. GNU GPL 3.'

import argparse
import datetime
import default_strategies
import inspect
import lendingclub
import logging
import os
import re
import smtplib
import time
from email.mime.text import MIMEText
from settings import login_email
from settings import smtp_password
from settings import smtp_server
from settings import smtp_username
from StringIO import StringIO

try:
  from settings import smtp_port
except:
  smtp_port = 587

try:
  import custom_strategies
except ImportError:
  custom_strategies = object()


def send_email(me, you, subject, body):
  logging.info("sending email '%s' to %s" % (subject, you))
  msg = MIMEText(body)
  msg['Subject'] = subject
  msg['From'] = me
  msg['To'] = you
  s = smtplib.SMTP(smtp_server, smtp_port)
  s.ehlo()
  s.starttls()
  s.ehlo()
  if smtp_username:
    s.login(smtp_username, smtp_password)
  s.sendmail(me, [you], msg.as_string())
  s.close()


def clean_cache_dir(cache_dir):
  """
  delete files older than 45 days in cache dir
  """
  for name in os.listdir(cache_dir):
    if re.search('[.]html', name):
      path = os.path.join(cache_dir, name)
      st = os.stat(path)
      day_sold = (time.time() - max(st.st_atime, st.st_mtime)) / 3600 / 24
      if day_sold > 45:
        logging.debug('deleting %s, %.0f days old' % (name, day_sold))
        os.unlink(path)


def setup_logging(args):
  stream = StringIO()
  if args.debug:
    level = logging.DEBUG
  elif args.quiet:
    level = logging.WARNING
  else:
    level = logging.INFO
  if not args.email and not args.quiet:
    logging.basicConfig(level=level)
  else:
    logging.basicConfig(level=level, stream=stream)
    if not args.quiet:
      logging.getLogger().addHandler(logging.StreamHandler())
  return stream


def main(args):
  log_stream = setup_logging(args)
  sell = []
  buy = []
  possible_actions = {'dedup': None}
  for module in (default_strategies, custom_strategies):
    for name in dir(module):
      obj = getattr(module, name)
      if inspect.isclass(obj) and not inspect.isabstract(obj):
        possible_actions[name.lower()] = obj
  if len(args.actions) == 0:
    parser.print_help()
    print
    print "ERROR: Must select one of the following actions"
    print possible_actions.keys()
    return
  try:
    lc = lendingclub.LendingClubBrowser()
    lc.fetch_notes()
    lc.fetch_trading_summary()
    for action in args.actions:
      strategy = possible_actions[action.lower()]
      if strategy is not None:
        strategy = strategy()
      if isinstance(strategy, lendingclub.SellStrategy):
        sell += lc.sell_with_strategy(strategy, markup=args.markup,
                                      fraction=args.fraction)
      elif isinstance(strategy, lendingclub.BuyTradingStrategy):
        buy += lc.buy_trading_with_strategy(strategy)
      elif action.lower() == 'dedup':
        lc.sell_duplicate_notes(args.markup)
      else:
        assert False
    lc.logout()
    clean_cache_dir(lc.cache_dir)
  except KeyboardInterrupt:
    raise
  except:
    logging.exception('unknown error')
  finally:
    log = log_stream.getvalue()
    print log
    if log and args.email:
      today = str(datetime.date.today())
      subject = '[LendingClubChecker] buy %d sell %d on %s' % (len(buy),
                                                               len(sell),
                                                               today)
      send_email(args.emailfrom, args.emailto, subject, log)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--debug', '-v', action='store_true',
                      help='print more debugging info')
  parser.add_argument('--quiet', '-q', action='store_true',
                      help='print less debugging info')
  parser.add_argument('--emailfrom', default=login_email,
                      help='report email from address')
  parser.add_argument('--emailto', default=login_email,
                      help='report email to address')
  parser.add_argument('--email', action='store_true',
                      help='send an email report to ' + login_email)
  parser.add_argument('--markup', default=0.997, type=float,
                      help='markup when selling notes (default 0.997)')
  parser.add_argument('--fraction', default=0.2, type=float,
                      help='fraction of notes to check per run (default 0.2)')
  parser.add_argument('actions', nargs='*', help='List of strategies to run')
  main(parser.parse_args())
