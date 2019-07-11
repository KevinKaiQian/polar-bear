

import eventlet
eventlet.monkey_patch()


from nova import reportrpc
import oslo_messaging as messaging
from nova.i18n import _LW

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class RPCClient(object):

    def __init__(self, topic=None):
        self.report_rpcapi = reportrpc.ReportAPI(topic=topic)
        

    def result(self, ctxt, result):
        try:
            self.report_rpcapi.result(ctxt, arg=result,timeout=120)
        except messaging.MessagingTimeout:

            LOG.warning(_LW('Timed out waiting for nova-conductor.  '
                            'Is it running? Or did this service start '
                            'before nova-conductor?  '
                            'Reattempting establishment of '
                            'nova-conductor connection...'))      
    

'''
class RPCClient(object):

    def __init__(self, topic=None):
        transport = oslo_messaging.get_transport(cfg.CONF)
        target = oslo_messaging.Target(topic=topic, version='2.0')
        #serializer = objects_base.NovaObjectSerializer()
        self._client = oslo_messaging.RPCClient(transport=transport, target=target)
        


    def result(self, ctxt, result):
        return self._client.call(ctxt, 'result', result=result)
    
'''

    
    