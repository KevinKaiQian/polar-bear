urls = ["http://www.google.com/intl/en_ALL/images/logo.gif",
     "http://us.i1.yimg.com/us.yimg.com/i/ww/beta/y3.gif"]

import eventlet
from eventlet.green import urllib2  
import time
def fetch(url):
  print "opening", url
  body = urllib2.urlopen(url).read()
  print "done with", url
  return url, body

pool = eventlet.GreenPool(200)
for url, body in pool.imap(fetch, urls):
  print "got body from", url, "of length", len(body)
