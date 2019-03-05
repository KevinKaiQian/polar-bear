
import copy

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

import six

from nova.compute import rpcapi as compute_rpcapi

from nova.db import base
from nova import exception
from nova.i18n import _, _LE, _LI, _LW

from nova import manager
from nova.compute import utils as compute_utils
from nova import utils



from nova import rpc

from nova import servicegroup



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


    @compute_utils.mark_describe_task(namespace='build_server',
                                      describe="parameters is dict. \
address is target address \
count is count of ping . \
interval is time of two packet")
    def ping(self, context, parameters):
        count= parameters.get('count',4)
        interval= parameters.get('interval',1)
        Caseid= parameters.get('id',None)
        ca_dir="/root"
        out, err =utils.execute('ping', count ,interval, cwd=ca_dir,run_as_root=True)
        self.report_result(context, Caseid=Caseid, out=out, status=err)

