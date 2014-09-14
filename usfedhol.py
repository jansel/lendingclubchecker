#/usr/bin/python
"""usfedhol.py: Test for United States federal holidays"""
__version__ = '3.0'
__author__ = 'Jason Ansel (jansel@jansel.net)'
__copyright__ = '(C) 2012-2014. GNU GPL 3.'

import datetime
import re
import urllib2

date_names = [
 (datetime.date(1999, 12, 31), 'New Year&rsquo;s Day'),
 (datetime.date(2000, 1, 17), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2000, 2, 21), 'Washington&rsquo;s Birthday'),
 (datetime.date(2000, 5, 29), 'Memorial Day'),
 (datetime.date(2000, 7, 4), 'Independence Day'),
 (datetime.date(2000, 9, 4), 'Labor Day'),
 (datetime.date(2000, 10, 9), 'Columbus Day'),
 (datetime.date(2000, 11, 10), 'Veterans Day'),
 (datetime.date(2000, 11, 23), 'Thanksgiving Day'),
 (datetime.date(2000, 12, 25), 'Christmas Day'),
 (datetime.date(2001, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2001, 1, 15), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2001, 2, 19), 'Washington&rsquo;s Birthday'),
 (datetime.date(2001, 5, 28), 'Memorial Day'),
 (datetime.date(2001, 7, 4), 'Independence Day'),
 (datetime.date(2001, 9, 3), 'Labor Day'),
 (datetime.date(2001, 10, 8), 'Columbus Day'),
 (datetime.date(2001, 11, 12), 'Veterans Day'),
 (datetime.date(2001, 11, 22), 'Thanksgiving Day'),
 (datetime.date(2001, 12, 25), 'Christmas Day'),
 (datetime.date(2002, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2002, 1, 21), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2002, 2, 18), 'Washington&rsquo;s Birthday'),
 (datetime.date(2002, 5, 27), 'Memorial Day'),
 (datetime.date(2002, 7, 4), 'Independence Day'),
 (datetime.date(2002, 9, 2), 'Labor Day'),
 (datetime.date(2002, 10, 14), 'Columbus Day'),
 (datetime.date(2002, 11, 11), 'Veterans Day'),
 (datetime.date(2002, 11, 28), 'Thanksgiving Day'),
 (datetime.date(2002, 12, 25), 'Christmas Day'),
 (datetime.date(2003, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2003, 1, 20), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2003, 2, 17), 'Washington&rsquo;s Birthday'),
 (datetime.date(2003, 5, 26), 'Memorial Day'),
 (datetime.date(2003, 7, 4), 'Independence Day'),
 (datetime.date(2003, 9, 1), 'Labor Day'),
 (datetime.date(2003, 10, 13), 'Columbus Day'),
 (datetime.date(2003, 11, 11), 'Veterans Day'),
 (datetime.date(2003, 11, 27), 'Thanksgiving Day'),
 (datetime.date(2003, 12, 25), 'Christmas Day'),
 (datetime.date(2004, 1, 1), "New Year's Day"),
 (datetime.date(2004, 1, 19), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2004, 2, 16), "Washington's Birthday"),
 (datetime.date(2004, 5, 31), 'Memorial Day'),
 (datetime.date(2004, 7, 5), 'Independence Day'),
 (datetime.date(2004, 9, 6), 'Labor Day'),
 (datetime.date(2004, 10, 11), 'Columbus Day'),
 (datetime.date(2004, 11, 11), 'Veterans Day'),
 (datetime.date(2004, 11, 25), 'Thanksgiving Day'),
 (datetime.date(2004, 12, 24), 'Christmas Day'),
 (datetime.date(2004, 12, 31), 'New Year&rsquo;s Day'),
 (datetime.date(2005, 1, 17), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2005, 2, 21), 'Washington&rsquo;s Birthday'),
 (datetime.date(2005, 5, 30), 'Memorial Day'),
 (datetime.date(2005, 7, 4), 'Independence Day'),
 (datetime.date(2005, 9, 5), 'Labor Day'),
 (datetime.date(2005, 10, 10), 'Columbus Day'),
 (datetime.date(2005, 11, 11), 'Veterans Day'),
 (datetime.date(2005, 11, 24), 'Thanksgiving Day'),
 (datetime.date(2005, 12, 26), 'Christmas Day'),
 (datetime.date(2006, 1, 2), 'New Year&rsquo;s Day'),
 (datetime.date(2006, 1, 16), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2006, 2, 20), 'Washington&rsquo;s Birthday'),
 (datetime.date(2006, 5, 29), 'Memorial Day'),
 (datetime.date(2006, 7, 4), 'Independence Day'),
 (datetime.date(2006, 9, 4), 'Labor Day'),
 (datetime.date(2006, 10, 9), 'Columbus Day'),
 (datetime.date(2006, 11, 10), 'Veterans Day'),
 (datetime.date(2006, 11, 23), 'Thanksgiving Day'),
 (datetime.date(2006, 12, 25), 'Christmas Day'),
 (datetime.date(2007, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2007, 1, 15), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2007, 2, 19), 'Washington&rsquo;s Birthday'),
 (datetime.date(2007, 5, 28), 'Memorial Day'),
 (datetime.date(2007, 7, 4), 'Independence Day'),
 (datetime.date(2007, 9, 3), 'Labor Day'),
 (datetime.date(2007, 10, 8), 'Columbus Day'),
 (datetime.date(2007, 11, 12), 'Veterans Day'),
 (datetime.date(2007, 11, 22), 'Thanksgiving Day'),
 (datetime.date(2007, 12, 25), 'Christmas Day'),
 (datetime.date(2008, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2008, 1, 21), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2008, 2, 18), 'Washington&rsquo;s Birthday'),
 (datetime.date(2008, 5, 26), 'Memorial Day'),
 (datetime.date(2008, 7, 4), 'Independence Day'),
 (datetime.date(2008, 9, 1), 'Labor Day'),
 (datetime.date(2008, 10, 13), 'Columbus Day'),
 (datetime.date(2008, 11, 11), 'Veterans Day'),
 (datetime.date(2008, 11, 27), 'Thanksgiving Day'),
 (datetime.date(2008, 12, 25), 'Christmas Day'),
 (datetime.date(2009, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2009, 1, 19), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2009, 2, 16), 'Washington&rsquo;s Birthday'),
 (datetime.date(2009, 5, 25), 'Memorial Day'),
 (datetime.date(2009, 7, 3), 'Independence Day'),
 (datetime.date(2009, 9, 7), 'Labor Day'),
 (datetime.date(2009, 10, 12), 'Columbus Day'),
 (datetime.date(2009, 11, 11), 'Veterans Day'),
 (datetime.date(2009, 11, 26), 'Thanksgiving Day'),
 (datetime.date(2009, 12, 25), 'Christmas Day'),
 (datetime.date(2010, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2010, 1, 18), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2010, 2, 15), 'Washington&rsquo;s Birthday'),
 (datetime.date(2010, 5, 31), 'Memorial Day'),
 (datetime.date(2010, 7, 5), 'Independence Day'),
 (datetime.date(2010, 9, 6), 'Labor Day'),
 (datetime.date(2010, 10, 11), 'Columbus Day'),
 (datetime.date(2010, 11, 11), 'Veterans Day'),
 (datetime.date(2010, 11, 25), 'Thanksgiving Day'),
 (datetime.date(2010, 12, 24), 'Christmas Day'),
 (datetime.date(2010, 12, 31), 'New Year&rsquo;s Day'),
 (datetime.date(2011, 1, 17), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2011, 2, 21), 'Washington&rsquo;s Birthday'),
 (datetime.date(2011, 5, 30), 'Memorial Day'),
 (datetime.date(2011, 7, 4), 'Independence Day'),
 (datetime.date(2011, 9, 5), 'Labor Day'),
 (datetime.date(2011, 10, 10), 'Columbus Day'),
 (datetime.date(2011, 11, 11), 'Veterans Day'),
 (datetime.date(2011, 11, 24), 'Thanksgiving Day'),
 (datetime.date(2011, 12, 26), 'Christmas Day'),
 (datetime.date(2012, 1, 2), "New Year's Day"),
 (datetime.date(2012, 1, 16), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2012, 2, 20), "Washington's Birthday"),
 (datetime.date(2012, 5, 28), 'Memorial Day'),
 (datetime.date(2012, 7, 4), 'Independence Day'),
 (datetime.date(2012, 9, 3), 'Labor Day'),
 (datetime.date(2012, 10, 8), 'Columbus Day'),
 (datetime.date(2012, 11, 12), 'Veterans Day'),
 (datetime.date(2012, 11, 22), 'Thanksgiving Day'),
 (datetime.date(2012, 12, 25), 'Christmas Day'),
 (datetime.date(2013, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2013, 1, 21), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2013, 2, 18), 'Washington&rsquo;s Birthday'),
 (datetime.date(2013, 5, 27), 'Memorial Day'),
 (datetime.date(2013, 7, 4), 'Independence Day'),
 (datetime.date(2013, 9, 2), 'Labor Day'),
 (datetime.date(2013, 10, 14), 'Columbus Day'),
 (datetime.date(2013, 11, 11), 'Veterans Day'),
 (datetime.date(2013, 11, 28), 'Thanksgiving Day'),
 (datetime.date(2013, 12, 25), 'Christmas Day'),
 (datetime.date(2014, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2014, 1, 20), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2014, 2, 17), 'Washington&rsquo;s Birthday'),
 (datetime.date(2014, 5, 26), 'Memorial Day'),
 (datetime.date(2014, 7, 4), 'Independence Day'),
 (datetime.date(2014, 9, 1), 'Labor Day'),
 (datetime.date(2014, 10, 13), 'Columbus Day'),
 (datetime.date(2014, 11, 11), 'Veterans Day'),
 (datetime.date(2014, 11, 27), 'Thanksgiving Day'),
 (datetime.date(2014, 12, 25), 'Christmas Day'),
 (datetime.date(2015, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2015, 1, 19), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2015, 2, 16), 'Washington&rsquo;s Birthday'),
 (datetime.date(2015, 5, 25), 'Memorial Day'),
 (datetime.date(2015, 7, 3), 'Independence Day'),
 (datetime.date(2015, 9, 7), 'Labor Day'),
 (datetime.date(2015, 10, 12), 'Columbus Day'),
 (datetime.date(2015, 11, 11), 'Veterans Day'),
 (datetime.date(2015, 11, 26), 'Thanksgiving Day'),
 (datetime.date(2015, 12, 25), 'Christmas Day'),
 (datetime.date(2016, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2016, 1, 18), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2016, 2, 15), 'Washington&rsquo;s Birthday'),
 (datetime.date(2016, 5, 30), 'Memorial Day'),
 (datetime.date(2016, 7, 4), 'Independence Day'),
 (datetime.date(2016, 9, 5), 'Labor Day'),
 (datetime.date(2016, 10, 10), 'Columbus Day'),
 (datetime.date(2016, 11, 11), 'Veterans Day'),
 (datetime.date(2016, 11, 24), 'Thanksgiving Day'),
 (datetime.date(2016, 12, 26), 'Christmas Day'),
 (datetime.date(2017, 1, 2), 'New Year&rsquo;s Day'),
 (datetime.date(2017, 1, 16), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2017, 2, 20), 'Washington&rsquo;s Birthday'),
 (datetime.date(2017, 5, 29), 'Memorial Day'),
 (datetime.date(2017, 7, 4), 'Independence Day'),
 (datetime.date(2017, 9, 4), 'Labor Day'),
 (datetime.date(2017, 10, 9), 'Columbus Day'),
 (datetime.date(2017, 11, 10), 'Veterans Day'),
 (datetime.date(2017, 11, 23), 'Thanksgiving Day'),
 (datetime.date(2017, 12, 25), 'Christmas Day'),
 (datetime.date(2018, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2018, 1, 15), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2018, 2, 19), 'Washington&rsquo;s Birthday'),
 (datetime.date(2018, 5, 28), 'Memorial Day'),
 (datetime.date(2018, 7, 4), 'Independence Day'),
 (datetime.date(2018, 9, 3), 'Labor Day'),
 (datetime.date(2018, 10, 8), 'Columbus Day'),
 (datetime.date(2018, 11, 12), 'Veterans Day'),
 (datetime.date(2018, 11, 22), 'Thanksgiving Day'),
 (datetime.date(2018, 12, 25), 'Christmas Day'),
 (datetime.date(2019, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2019, 1, 21), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2019, 2, 18), 'Washington&rsquo;s Birthday'),
 (datetime.date(2019, 5, 27), 'Memorial Day'),
 (datetime.date(2019, 7, 4), 'Independence Day'),
 (datetime.date(2019, 9, 2), 'Labor Day'),
 (datetime.date(2019, 10, 14), 'Columbus Day'),
 (datetime.date(2019, 11, 11), 'Veterans Day'),
 (datetime.date(2019, 11, 28), 'Thanksgiving Day'),
 (datetime.date(2019, 12, 25), 'Christmas Day'),
 (datetime.date(2020, 1, 1), 'New Year&rsquo;s Day'),
 (datetime.date(2020, 1, 20), 'Birthday of Martin Luther King, Jr.'),
 (datetime.date(2020, 2, 17), 'Washington&rsquo;s Birthday'),
 (datetime.date(2020, 5, 25), 'Memorial Day'),
 (datetime.date(2020, 7, 3), 'Independence Day'),
 (datetime.date(2020, 9, 7), 'Labor Day'),
 (datetime.date(2020, 10, 12), 'Columbus Day'),
 (datetime.date(2020, 11, 11), 'Veterans Day'),
 (datetime.date(2020, 11, 26), 'Thanksgiving Day'),
 (datetime.date(2020, 12, 25), 'Christmas Day')]

dates = sorted(map(lambda x: x[0], date_names))


def extract_row(tr, tag='td'):
  rv = list()
  for td in tr.findAll(tag):
    s = ' '.join(map(lambda x: str(x).strip(), td.findAll(text=True)))
    s = re.sub('[ \r\n\t]+', ' ', s)
    rv.append(s)
  return rv


def parsedate(s):
  import parsedatetime.parsedatetime as pdt
  p = pdt.Calendar()
  if s == '--':
    return None
  return datetime.date(*p.parse(s)[0][0:3])


def fetch_holidays(years=range(2000, 2021)):
  from BeautifulSoup import BeautifulSoup

  holidays = list()
  for year in years:
    _year = year
    soup = BeautifulSoup(urllib2.urlopen(
      'http://www.opm.gov/Operating_Status_Schedules/fedhol/%d.asp' % year))
    table = soup.findAll('table')[0]
    rows = map(extract_row, table.findAll('tr'))

    for date, name in rows:
      date = re.sub('[*]+$', '', date)
      try:
        weekday, date = map(str.strip, date.split(','))
        year = _year
      except:
        weekday, date, year = map(str.strip, date.split(','))
        year = int(year)

      date += ', %d' % year
      date = parsedate(date)
      holidays.append((date, name))

  return holidays


def is_holiday(d):
  assert dates[0] <= d and d <= dates[-1]
  return d in dates


def contains_holiday(a, b):
  assert dates[0] <= a and a <= dates[-1]
  assert dates[0] <= b and b <= dates[-1]
  if a <= b:
    return 0 < len(filter(lambda x: a <= x and x <= b, dates))
  else:
    return 0 < len(filter(lambda x: a >= x and x >= b, dates))

if __name__ == '__main__':
  from pprint import pprint
  pprint(fetch_holidays())
