
import copy

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
import  json


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

import requests
from oslo_log import log as logging
LOG = logging.getLogger(__name__)




class ComputeManager_http(base.Base):

    target = messaging.Target(namespace='http', version='4.0')
    
    def __init__(self):
        super(ComputeManager_http, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.compute_task_api = conductor.ComputeTaskAPI()
        

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()

    @compute_utils.mark_describe_task(namespace='http',
                                      describe="Http Get method interface",
                                      parameters={'url':"http request url ,default is none"})
    def get(self, context, parameters,topic):
        LOG.info(_LI("http request: %s"),
                 json.dumps(parameters))
        out,status,method = '','FAIL','get'
        url = parameters.get('url', None)
        stepid = parameters.get('stepid', None)
        try:
            response = requests.get(url=url)
            if response.status_code == 200:
                status = "PASS"
            else:
                status = "FAIL"
            out = response.text
            LOG.info("xx"+str(url))
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)
        except BaseException as e:
            status = "FAIL"
            out=str(e.message)
            LOG.info(_LI("http get fail reason: %s"),
                     e.message)
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)

    @compute_utils.mark_describe_task(namespace='http',
                                      describe="Http post method interface",
                                      parameters={'url':"http request url ,default is none"})
    def post(self, context, parameters, topic):
        LOG.info(_LI("http request: %s"),
                 json.dumps(parameters))
        out, status, method = '', 'FAIL', 'get'
        url = parameters.get('url', None)
        stepid = parameters.get('stepid', None)
        data = parameters.get('data', None)
        try:
            response = requests.post(url,json=data)
            if response.status_code == 200:
                status = "PASS"
            else:
                status = "FAIL"
            out = response.text
            LOG.info("xx" + str(url))
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)
        except BaseException as e:
            status = "FAIL"
            out = str(e.message)
            LOG.info(_LI("http post fail reason: %s"),
                     e.message)
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)




