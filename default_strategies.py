__version__ = '3.0'
__author__ = 'Jason Ansel (jansel@jansel.net)'
__copyright__ = '(C) 2012-2014. GNU GPL 3.'

from lendingclub import SellStrategy
import logging
try:
  import marketmodel
except ImportError:
  marketmodel = None

log = logging.getLogger(__name__)


class SellImperfect(SellStrategy):
  def sale_price(self, note, markup=None):
    if marketmodel is None or marketmodel.MarketModel.instance() is None:
      return note.par_value() * markup
    model = marketmodel.MarketModel.instance()
    trading_row = note.to_trading_row_format()
    price = model.predict_sale_price_trading_row(trading_row,
                                                 confidence=0.4,
                                                 min_markup=0.98,
                                                 max_markup=1.25)
    try:
      log.info('Sale: %.2f markup=%.2f %s neverlate=%s rate=%s, '
               'credit_delta=%s sell_proba=%.2f',
               price, price / note.par_value(), trading_row['Status'],
               trading_row['NeverLate'], trading_row['Interest Rate'],
               note.creditdeltamin(),
               model.sell_proba_trading_row(trading_row, price=price))
    except Exception:
      log.exception('Eeek!')
    return price

  def initial_filter(self, note):
    return note.can_sell()

  def details_filter(self, note):
    """
    Sell all notes with any sort of imperfection
    """
    if not note.can_sell():
      self.reasons['cant sell'] += 1
      return False

    if len(note.collection_log) > 0:
      s = repr(note.collection_log).lower()
      if 'failed' in s:
        self.reasons['failed payment'] += 1
      else:
        self.reasons['collections log'] += 1
      return True

    late = note.get_late_payments()
    if late:
      if filter(lambda x: x.status not in ('Completed - in grace period',),
                late):
        self.reasons['late payment'] += 1
      else:
        self.reasons['payment in grace period'] += 1
      return True

    if note.credit_history:
      if note.creditdeltamin() < -120:
        self.reasons['credit score drop >120'] += 1
        return True
      elif note.creditdeltamin() < -80:
        self.reasons['credit score drop >80'] += 1
        return True

    return False

