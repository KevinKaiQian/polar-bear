import six
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.getcwd()))) 

from nova import exception
from nova.i18n import _LE, _LW
from nova import service
from nova import utils
from nova.db.sqlalchemy import api as sqlalchemy_api
from nova import rpc
from nova import objects
from oslo_config import cfg
CONF = cfg.CONF

from oslo_log import log as logging
#LOG = logging.getLogger(__name__)

def main():
    #logging.setup(CONF, "nova")
    #import pdb;pdb.set_trace()

    rpc.set_defaults(control_exchange='nova')
    rpc.init(CONF)
    objects.register_all()
    sqlalchemy_api.configure(CONF)
    log = logging.getLogger(__name__)
    launcher = service.process_launcher()
    started = 0
    for api in CONF.enabled_apis:
        should_use_ssl = api in CONF.enabled_ssl_apis
        try:
            server = service.WSGIService(api, use_ssl=should_use_ssl)
	    #import pdb;pdb.set_trace()
            launcher.launch_service(server, workers=server.workers or 1)
            started += 1
        except exception.PasteAppNotFound as ex:
            log.warning(
                _LW("%s. ``enabled_apis`` includes bad values. "
                    "Fix to remove this warning."), six.text_type(ex))

    if started == 0:
        log.error(_LE('No APIs were started. '
                      'Check the enabled_apis config option.'))
        sys.exit(1)

    launcher.wait()
        
if __name__ == "__main__":
    main()
