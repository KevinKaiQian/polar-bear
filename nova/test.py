import sys
import os
sys.path.append(os.path.dirname(os.getcwd())) 

from oslo_service import service
from oslo_utils import importutils

from nova import objects

from nova import context

from nova import exception
from nova.i18n import _, _LE, _LI, _LW
from nova.objects import base as objects_base
from nova.objects import service as service_obj
from nova import rpc
from nova import utils
from nova import wsgi


from nova import config
class Service(service.Service):
    """Service object for binaries running on hosts.

    A service takes a manager and enables rpc by listening to queues based
    on topic. It also periodically runs tasks on the manager and reports
    its state to the database services table.
    """

    def __init__(self, host, binary, topic, manager, report_interval=None,
                 periodic_enable=None, periodic_fuzzy_delay=None,
                 periodic_interval_max=None, db_allowed=True,
                 *args, **kwargs):
        super(Service, self).__init__()
        self.host = host
        self.binary = binary
        self.topic = topic

def _create_service_ref(this_service, context):
    service = objects.Service(context)
    #print dir(service)
    #print "tttt" +str(this_service.host)
    #print type(service.host)
    service.host = this_service.host
    service.binary = this_service.binary
    service.topic = this_service.topic
    service.report_count = 0
    service.create()
    #print "kaiqian" + str(service.topic)
    return service
import pdb;pdb.set_trace()
_create_service_ref(Service('0.0.0.0','api','',''),"22")
