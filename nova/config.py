

from oslo_config import cfg
from oslo_log import log as logging
import os

#import logging as py_logging
CONF = cfg.CONF


from nova.conf import api
from nova.conf import compute
from nova.conf import conductor
from nova.conf import database
from nova.conf import notifications
from nova.conf import wsgi
from nova.conf import service
from nova.conf import rpc
from nova.conf import notifications
from nova.conf import osapi_v21
from nova.conf import workarounds
from nova.conf import upgrade_levels
from nova.conf import servicegroup
from nova.conf import scheduler
from nova.conf import base
#from nova.conf import mail
#from nova.conf import netconf

from nova.conf import remote_debug



api.register_opts(CONF)
compute.register_opts(CONF)
conductor.register_opts(CONF)
database.register_opts(CONF)
notifications.register_opts(CONF)
wsgi.register_opts(CONF)
service.register_opts(CONF)
rpc.register_opts(CONF)
notifications.register_opts(CONF)
osapi_v21.register_opts(CONF)
workarounds.register_opts(CONF)
upgrade_levels.register_opts(CONF)
servicegroup.register_opts(CONF)
scheduler.register_opts(CONF)
base.register_opts(CONF)
#mail.register_opts(CONF)
#netconf.register_opts(CONF)

remote_debug.register_cli_opts(CONF)






LOG = logging.getLogger(__name__)
logging.register_options(CONF)

CONF(['--config-file='+str(os.path.join(os.getcwd(),'nova.ini'))],
     project='nova',
     version='1.1',
     default_config_files=None)

logging.setup(CONF, "nova")



'''

#https://blog.csdn.net/canxinghen/article/details/51711457
'''
