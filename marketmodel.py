#!/usr/bin/python
__version__ = '3.0'
__author__ = 'Jason Ansel (jansel@jansel.net)'
__copyright__ = '(C) 2012-2014. GNU GPL 3.'

import argparse
import collections
import csv
import datetime
import logging
import numpy
import os
import pickle
import random
import re
import sklearn.ensemble
import sklearn.metrics
import time

from pprint import pprint

log = logging.getLogger(__name__)

MARKETMODEL_PK_FILE = 'cache/marketmodel.pk'
SOLD_TIMEOUT_HOURS = 24
CHECK_FREQUENCY = 2


def normalize_feature_vector(feature_vector):
  feature_vector[IDX_MARKUP] = (feature_vector[IDX_ASK] /
                                feature_vector[IDX_VALUE] * 100.0 - 100.0)


class TradingNoteHistory(object):
  def __init__(self, timestamp, properties, feature_vector, raw_row):
    self.always_the_same = True
    self.feature_vector = feature_vector
    self.first_timestamp = timestamp
    self.last_timestamp = timestamp
    self.properties = properties
    self.raw_row = raw_row

  def merge(self, timestamp, properties, feature_vector):
    # noinspection PyStatementEffect
    feature_vector  # unused
    self.first_timestamp = min(self.first_timestamp, timestamp)
    self.last_timestamp = max(self.last_timestamp, timestamp)
    if (properties['AskPrice'] != self.properties['AskPrice']
            and self.get_seconds_listed() <= 3600 * SOLD_TIMEOUT_HOURS):
      self.always_the_same = False

  def get_seconds_listed(self):
    return self.last_timestamp - self.first_timestamp

  def should_include(self):
    if not self.always_the_same:
      return False
    if (self.first_timestamp > time.time() - 3600 * (SOLD_TIMEOUT_HOURS +
                                                     2 * CHECK_FREQUENCY)):
      return False
    if self.properties['DaysSinceLastPayment'] == -1:
      return False  # First payment
    if self.properties['DaysSinceLastPayment'] >= 20:
      return False  # Too close to due date
    return True


def make_dict_decoder(mapping):
  return lambda value: mapping[value]


def yield_decoder(value):
  if value == '--':
    return 0.0
  return float(value)


def days_since_last_payment_decoder(value):
  if value == 'null':
    return -1  # First payment
  else:
    return int(value)


def loan_class_decoder(value):
  m = re.match(r'^([A-Z])([0-9]+)$', value)
  return 10 * (ord(m.group(1)) - ord('A')) + int(m.group(2))


def fico_range_decoder(value):
  if value == '499-':
    return [300, 499]
  m = re.match(r'^([0-9]+)-([0-9]+)$', value)
  return [int(m.group(1)), int(m.group(2))]


def fico_range_decoder1(value):
  return fico_range_decoder(value)[0]


def fico_range_decoder2(value):
  return fico_range_decoder(value)[1]


def date_decoder(value):
  m = re.match(r'^([0-9]+)/([0-9]+)/([0-9]+)$', value)
  return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))


PROPERTY_DECODERS = {
    'NoteId': int,
    'OrderId': int,
    'LoanId': int,
    'Date/Time Listed': date_decoder,
    'YTM': yield_decoder,
}
PROPERTY_DECODERS = sorted([(intern(k), v)
                            for k, v in PROPERTY_DECODERS.iteritems()])

FEATURE_DECODERS = {
    'Status': make_dict_decoder({'Issued': 0,
                                 'Current': 1,
                                 'In Grace Period': 2,
                                 'Late (16-30 days)': 3,
                                 'Late (31-120 days)': 4}),
    'FICO End Range': fico_range_decoder1,
    # 'FICO End Range_': None,  # Extra slot fo indexing is right
    'Markup/Discount': float,
    'AskPrice': float,
    #'Loan Class': loan_class_decoder,
    #'Original Note Amount': float,
    #'OutstandingPrincipal': float,
    'CreditScoreTrend': make_dict_decoder({'DOWN': -1, 'FLAT': 0, 'UP': 1}),
    'DaysSinceLastPayment': days_since_last_payment_decoder,
    #'Loan Maturity': int,
    'Principal + Interest': float,
    #'AccruedInterest': float,
    'Interest Rate': float,
    'NeverLate': make_dict_decoder({'true': 1, 'false': 0}),
    'Remaining Payments': int,
}
FEATURE_DECODERS = sorted([(intern(k), v)
                           for k, v in FEATURE_DECODERS.iteritems()])
FEATURE_DECORERS_NAMES = [k for k, v in FEATURE_DECODERS]
IDX_MARKUP = FEATURE_DECORERS_NAMES.index('Markup/Discount')
IDX_ASK = FEATURE_DECORERS_NAMES.index('AskPrice')
IDX_VALUE = FEATURE_DECORERS_NAMES.index('Principal + Interest')


class BadLine(RuntimeError):
  pass


def decode_inventory_field(decoder, row, key, filename, lineno):
  value = row[key]
  if value is None:
    raise BadLine('{}:{} line too long'.format(filename, lineno))
  value = decoder(value)
  return value


def load_inventory_row(row, filename='unknown', lineno=0):
  if None in row:
    raise BadLine('{}:{} line too short'.format(filename, lineno))

  feature_vector = []
  properties = {}
  key = None
  value = None
  try:
    for key, decoder in FEATURE_DECODERS:
      if decoder is None:
        continue
      value = decode_inventory_field(decoder, row, key, filename, lineno)
      properties[key] = value
      if isinstance(value, list):
        feature_vector.extend(value)
      else:
        feature_vector.append(value)
    for key, decoder in PROPERTY_DECODERS:
      if key in row:
        properties[key] = decode_inventory_field(decoder, row, key, filename,
                                                 lineno)
  except (TypeError, ValueError, AttributeError, KeyError):
    raise BadLine('{}:{} failed to parse {}:{}'.format(filename, lineno, key,
                                                       value))
  normalize_feature_vector(feature_vector)
  return properties, feature_vector


def load_inventory(trading_history, timestamp, filename):
  all_notes = set()
  for lineno, row in enumerate(csv.DictReader(open(filename))):
    try:
      properties, feature_vector = load_inventory_row(row, filename, lineno + 2)
    except BadLine, e:
      log.error('BadLine: %s', e)
      continue
    note_id = properties['NoteId']
    if note_id in trading_history:
      trading_history[note_id].merge(timestamp, properties, feature_vector)
    else:
      trading_history[note_id] = TradingNoteHistory(timestamp, properties,
                                                    feature_vector, row)
    all_notes.add(trading_history[note_id])

    # grouped_notes = collections.defaultdict(list)
    # for note in all_notes:
    # grouped_notes[(note.properties['NeverLate'],
    #                  note.properties['Status'],
    #  #                note.properties['Loan Class']
    #   )].append(note)
    # for group in grouped_notes.values():
    #   group.sort(key=lambda x: x.properties['Markup/Discount'])
    #   for idx, note in enumerate(group):
    #     if len(note.feature_vector) == len(FEATURE_DECODERS):
    #       note.feature_vector += [idx]


def load_trading_history(args):
  filenames = os.listdir(args.directory)
  matches = [re.match(r'^([0-9]+)[.]csv$', filename) for filename in filenames]
  timestamps = [int(m.group(1)) for m in matches if m is not None]
  trading_history = dict()
  for timestamp in sorted(timestamps):
    print 'Processing', timestamp
    filename = os.path.join(args.directory, '{}.csv'.format(timestamp))
    load_inventory(trading_history, timestamp, filename)
  return trading_history


def reprice_feature_vector(row, ask_price=None, markup=None):
  row_copy = list(row)
  if ask_price is not None:
    row_copy[IDX_ASK] = round(ask_price, 2)
  elif markup is not None:
    row_copy[IDX_ASK] = round(row_copy[IDX_VALUE] * markup, 2)
  else:
    assert False
  normalize_feature_vector(row_copy)
  return row_copy


def print_classifier_report(clf, thresh, test_data, test_target):
  market_model = MarketModel(clf)
  print 'Threshold', thresh
  preds = []
  for row in test_data:
    sell_proba = market_model.sell_proba_features(row)
    preds.append(1 if sell_proba > thresh else 0)
  print sklearn.metrics.classification_report(test_target, preds)


def print_resell_opportunities(clf, thresh, test_notes):
  market_model = MarketModel(clf)
  stats = collections.Counter()
  row_fmt = '{:15} ' * len(FEATURE_DECORERS_NAMES)
  print row_fmt.format(*FEATURE_DECORERS_NAMES)
  for note in test_notes:
    sell_proba = market_model.sell_proba_trading_row(note.raw_row)
    if sell_proba > thresh:
      features = note.feature_vector
      price = market_model.predict_sale_price(
          features,
          confidence=thresh,
          min_price=features[IDX_ASK],
          max_markup=1.25)
      profit = round((price - features[IDX_ASK]) / features[IDX_ASK], 4)
      if profit >= 0.05:
        print row_fmt.format(*features), profit
        stats['profit'] += 1
      else:
        stats['no_profit'] += 1
    else:
      stats['no_sale'] += 1
  pprint(stats.most_common())


def load_train_test_notes(args):
  if args.cached:
    trading_history = pickle.load(open('cache/trading_history.pk', 'rb'))
  else:
    trading_history = load_trading_history(args)
    pickle.dump(trading_history, open('cache/trading_history.pk', 'wb'), 2)
  notes = filter(TradingNoteHistory.should_include, trading_history.values())
  # notes.sort(key=lambda x: x.first_timestamp)
  random.shuffle(notes)
  data = []
  target = []
  for note in notes:
    data.append(note.feature_vector)
    target.append(1 if note.get_seconds_listed() <= SOLD_TIMEOUT_HOURS * 3600.0
                  else 0)
  data = numpy.array(data)
  target = numpy.array(target)
  cutoff = int(len(data) * 0.8)
  train_data = data[:cutoff]
  train_target = target[:cutoff]
  test_data = data[cutoff:]
  test_target = target[cutoff:]
  test_notes = notes[cutoff:]
  return test_data, test_notes, test_target, train_data, train_target


class MarketModel(object):
  _instance = None

  @classmethod
  def instance(cls):
    if cls._instance is None:
      if not os.path.exists(MARKETMODEL_PK_FILE):
        return None
      log.info('Loading market model')
      cls._instance = cls(pickle.load(open(MARKETMODEL_PK_FILE, 'rb')))
    return cls._instance

  def __init__(self, clf):
    self.clf = clf

  def sell_proba_features(self, features, price=None):
    if price is not None:
      features[IDX_ASK] = price
      normalize_feature_vector(features)
    return self.clf.predict_proba([features])[0][1]

  def sell_proba_trading_row(self, row, price=None):
    features = load_inventory_row(row)[1]
    return self.sell_proba_features(features, price=price)

  def predict_sale_price(self, features, confidence=0.5,
                         min_markup=0.5, max_markup=1.5, step=0.01,
                         min_price=None, max_price=None):
    if min_price is None:
      min_price = round(min_markup * features[IDX_VALUE], 2)
      if min_price / features[IDX_VALUE] < min_markup:
        min_price += 0.01
      assert min_price / features[IDX_VALUE] >= min_markup
    if max_price is None:
      max_price = round(max_markup * features[IDX_VALUE], 2)
      if max_price / features[IDX_VALUE] > max_markup:
        max_price -= 0.01
      assert max_price / features[IDX_VALUE] <= max_markup
    rows = []
    price = min_price
    while price <= max_price:
      rows.append(reprice_feature_vector(features, ask_price=price))
      price += step
    price = min_price
    if rows:
      for row, proba in zip(rows, self.clf.predict_proba(rows)):
        if proba[1] < confidence:
          break
        price = row[IDX_ASK]
    return price

  def predict_sale_price_trading_row(self, row, **kwargs):
    features = load_inventory_row(row)[1]
    return self.predict_sale_price(features, **kwargs)


def train():
  clfs = [sklearn.ensemble.RandomForestClassifier(100, max_features=None)]
  logging.basicConfig(level=logging.DEBUG)
  parser = argparse.ArgumentParser()
  parser.add_argument('--directory', default='trading_history')
  parser.add_argument('--cached', action='store_true')
  args = parser.parse_args()
  (test_data, test_notes, test_target,
   train_data, train_target) = load_train_test_notes(args)
  for n, clf in enumerate(clfs):
    filename = 'cache/marketmodel_{}.pk'.format(n)
    print
    print clf.__class__.__name__, filename
    clf.fit(train_data, train_target)
    pickle.dump(clf, open(filename, 'wb'), 2)
    if hasattr(clf, 'feature_importances_'):
      pprint(sorted(zip(clf.feature_importances_, FEATURE_DECORERS_NAMES)))
    for i in range(1, 10):
      thresh = i / 10.0
      print_classifier_report(clf, thresh, test_data, test_target)
    print_resell_opportunities(clf, 0.65, test_notes)


if __name__ == '__main__':
  train()






