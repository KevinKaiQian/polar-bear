
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
import rpclient

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ComputeManager_linux_system(base.Base):

    target = messaging.Target(namespace='linux_system', version='4.0')
    
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
                                      describe="parameters is dict. address is target address ,count is count of ping . interval is time of two packet")
    def ping(self, context, parameters,topic):

        address=parameters.get('address',None)
        count= "-c "+str(parameters.get('count',4))
        interval="-i "+str( parameters.get('interval',1))
        err=-1
        if address == None:
            result={
                "out":"has not cmd parameters, can not run",
                "status": "FAIL",
                "method":"ping"
            }       
            if topic:
                rpclient.RPCClient(topic=topic).result(ctxt=context, result=result) 
        else:
            ca_dir="/root"
            try:
                out, err =utils.execute('ping', address,count ,interval, cwd=ca_dir,run_as_root=True)
            except Exception as e:
                out=e.message
            if err == '':res= "PASS"
            else:res = "FAIL"

            result={
                "out":out,
                "status": res,
                "method":"ping"
            }
            if topic:
                rpclient.RPCClient(topic=topic).result(ctxt=context, result=result)        
        
    @compute_utils.mark_describe_task(namespace='linux_system',
                                      describe="parameters is dict. cmd is command line. args is parameter")
    def run_shell(self, context, parameters,topic):
        cmd= parameters.get('cmd',None)
        arg= parameters.get('args',None)

        if cmd == None:
            result={
                "out":"has not cmd parameters, can not run",
                "status": "FAIL",
                "method":"run_shell"
            }       
            if topic:
                rpclient.RPCClient(topic=topic).result(ctxt=context, result=result) 
        else:
            ca_dir="/root"
            if arg == None:arg=""
            out, err =utils.execute(cmd, arg , cwd=ca_dir,run_as_root=True)
            if err == '':res= "PASS"
            else:res = "FAIL"
            result={
                "out":out,
                "status": res,
                "method":"run_shell"
            }
            if topic:
                rpclient.RPCClient(topic=topic).result(ctxt=context, result=result)



        

    

