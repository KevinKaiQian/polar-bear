
import copy

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_utils import excutils
from oslo_utils import versionutils
import six

from nova.compute import rpcapi as compute_rpcapi
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute.utils import wrap_instance_event
from nova.compute import vm_states
from nova.conductor.tasks import live_migrate
from nova.conductor.tasks import migrate
from nova.db import base
from nova import exception
from nova.i18n import _, _LE, _LI, _LW

from nova import manager

from nova import objects
from nova.objects import base as nova_object
from nova import rpc
from nova.scheduler import client as scheduler_client
from nova.scheduler import utils as scheduler_utils
from nova import servicegroup
from nova import utils
from nova.compute import utils as nova_utils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ComputeManager_build_server(base.Base):

    target = messaging.Target(namespace='build_server', version='4.0')
    
    #import pdb;pdb.set_trace()
    def __init__(self):
        super(ComputeManager_build_server, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()


    @nova_utils.add_task_describe(describe="parameters is dict. command key is linux cmd. args key is parameters of linux cmd")       
    @nova_utils.mark_task_status(namespace='build_server',method_mark=True)
    def system_information(self, context, parameters):
        #import pdb;pdb.set_trace()
        print parameters    

    @nova_utils.add_task_describe(describe="parameters is dict. command key is linux cmd. args key is parameters of linux cmd")      
    @nova_utils.mark_task_status(namespace='build_server',method_mark=True)
    def run_shell(self, context, parameters):
        #import pdb;pdb.set_trace()
        print parameters
    

