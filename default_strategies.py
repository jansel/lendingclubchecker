from lendingclub import SellStrategy


class SellImperfect(SellStrategy):
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

    if note.payment_history:
      late = filter(lambda x: x.status not in ('Completed - on time',
                                               'Scheduled', 'Processing...'),
                    note.payment_history)
      late = [x for x in late
              if 'Recurring payment date changed' not in x.status]
      if late:
        if filter(lambda x: x.status not in ('Completed - in grace period'),
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

