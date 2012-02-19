#!/usr/bin/python
import lendingclub
import argparse
import logging
import pickle
import smtplib
import datetime
import sys 
from StringIO import StringIO
from email.mime.text import MIMEText
from settings import smtp_server, smtp_username, smtp_password, login_email

notes_pickle_file = lendingclub.cachedir+'/notes.pk'

def load_active_notes(update, window):
  lc = lendingclub.LendingClubBrowser()
  if update:
    lc.fetch_notes()
    lc.fetch_trading_summary()
  active = lc.load_notes()
  
  sellingids = lc.get_already_selling_ids()
  active = filter(lambda x: x.note_id not in sellingids, active)
  active = filter(lambda x: x.want_update(window), active)

  logging.info("active notes = "+str(len(active)))

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

  lc.logout()

  pickle.dump(active, open(notes_pickle_file, 'w'))
  return active

def print_want_sell(active, o=sys.stdout):
  sell = filter(lendingclub.Note.want_sell, active)

  print >>o, "examined", len(active), 'notes,', len(sell), "sell suggestions:"
  print >>o
  for note in sell:
    note.debug(o)
    print >>o, 'sell reasons', note.sell_reasons()
    print >>o
  if sell:
    print >>o, "sell note ids:", map(lambda x: x.note_id, sell)

  return len(sell)

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

def main(args):
  if args.debug:
    logging.getLogger().setLevel(logging.DEBUG)
  elif args.quite:
    logging.getLogger().setLevel(logging.WARNING)
  else:
    logging.getLogger().setLevel(logging.INFO)

  if args.frompickle:
    active = pickle.load(open(notes_pickle_file))
  else:
    active = load_active_notes(args.update, args.window)

  if not args.quite:
    print
    print_want_sell(active)
  
  if args.email:
    body = StringIO()
    nsell = print_want_sell(active, body)
    today = str(datetime.date.today())
    subject = "[LendingClubChecker] %d sell suggestions for %s" % (nsell, today)
    send_email(args.emailfrom, args.emailto, subject, body.getvalue())

  if args.probtable:
    print
    print "payment prob table"
    print "ppt[due_day] = [(delay, prob), ...]"
    print "due_day is day of week (0=monday), delay is in days after due date, prob is from 0 to 1.0"
    lendingclub.build_payment_prob_table(active)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='check notes coming due soon for ones that should be sold')
  parser.add_argument('--window', '-w', default=4, type=int,
                      help='fetch notes we expect to be payed in the next N days')
  parser.add_argument('--noupdate', action='store_false', dest='update',
                      help="dont fetch details for notes we have cached data for")
  parser.add_argument('--frompickle', action='store_true',
                      help="read active notes from "+notes_pickle_file)
  parser.add_argument('--probtable', action='store_true',
                      help="print table of payment times based on due weekday, use with: -w 99 --noupdate -q")
  parser.add_argument('--debug', '-v', action='store_true',
                      help="print more debugging info")
  parser.add_argument('--quite', '-q', action='store_true',
                      help="print less debugging info")
  parser.add_argument('--emailfrom', default=login_email, help='report email from address')
  parser.add_argument('--emailto',   default=login_email, help='report email to address')
  parser.add_argument('--email', action='store_true', help="send an email report to "+login_email)
  args = parser.parse_args()
  main(args)



