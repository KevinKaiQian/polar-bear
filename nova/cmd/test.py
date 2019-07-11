import sys
import os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.getcwd())))

import eventlet
eventlet.monkey_patch()

from oslo_config import cfg
import oslo_messaging
import time

class ServerControlEndpoint(object):

    target = oslo_messaging.Target(namespace='control',
                                   version='2.0')

    def __init__(self, server):
        self.server = server

    def stop(self, ctx):
        if self.server:
            self.server.stop()

class TestEndpoint(object):

    def test(self, ctx, arg):
        return arg

transport = oslo_messaging.get_transport(cfg.CONF)
target = oslo_messaging.Target(topic='test', server='135.251.149.80')
endpoints = [
    ServerControlEndpoint(None),
    TestEndpoint(),
]
server = oslo_messaging.get_rpc_server(transport, target, endpoints,
                                       executor='eventlet')
try:
    server.start()
    while True:
        time.sleep(100)
except KeyboardInterrupt:
    print("Stopping server")

server.stop()
server.wait()



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
