
import copy

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging


from nova.compute import rpcapi as compute_rpcapi

from nova.db import base
from nova import exception
from nova.i18n import _, _LE, _LI, _LW

from nova import servicegroup
from nova import utils
from nova.compute import utils as compute_utils
from nova import conductor

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ComputeManager_linux_system(base.Base):

    target = messaging.Target(namespace='linux_system', version='4.0')
    
    #import pdb;pdb.set_trace()
    def __init__(self):
        super(ComputeManager_linux_system, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.compute_task_api = conductor.ComputeTaskAPI()
        

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()

    @compute_utils.mark_describe_task(namespace='linux_system',
                                      describe="parameters is dict. \
address is target address \
count is count of ping . \
interval is time of two packet")
    def ping(self, context, parameters):
        #import pdb;pdb.set_trace()
        address=parameters.get('address',4)
        count= "-c "+str(parameters.get('count',4))
        interval="-i "+str( parameters.get('interval',1))
        Caseid= parameters.get('id',None)
        ca_dir="/root"
        out, err =utils.execute('ping', address,count ,interval, cwd=ca_dir,run_as_root=True)
        self.report_result(context, Caseid=Caseid, out=out, status=err)
    
    @compute_utils.mark_describe_task(namespace='linux_system',
                                      describe="parameters is dict. \
cmd is command line. \
args is parameter")
    def run_shell(self, context, parameters):
        cmd= parameters.get('cmd',None)
        arg= parameters.get('args',None)
        Caseid= parameters.get('id',None)
        ca_dir="/root"
        out, err =utils.execute(cmd, arg , cwd=ca_dir,run_as_root=True)
        
        self.report_result(context, Caseid=Caseid, out=out, status=err)

    def report_result(self,context,Caseid=None,out=None,status=None):
        #import pdb;pdb.set_trace()
        if Caseid is None or out is None or status is None:pass
        else:
            status = "fail"
            output = "not stdout "
            if status != 1:status ="successfully"
            if out :output = out
            self.compute_task_api.report_cases_result(context, Caseid=Caseid,output=output,status=status)
        

    

