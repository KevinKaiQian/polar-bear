#!/usr/bin/env python
from nova import exception
from nova import config



import sys
import six
#import nova.conf
from nova import config
from nova import exception
#from nova.i18n import _LE, _LW
import object
import service
import utils
#from nova import version


from oslo_config import cfg
CONF = cfg.CONF

from oslo_log import log as logging
LOG = logging.getLogger(__name__)




def main():
   
    logging.setup(CONF, "nova")
    utils.monkey_patch()


    log = logging.getLogger(__name__)

  

    launcher = service.process_launcher()
    started = 0
    for api in CONF.enabled_apis:
        should_use_ssl = api in CONF.enabled_ssl_apis
        try:
            server = service.WSGIService(api, use_ssl=should_use_ssl)
            launcher.launch_service(server, workers=server.workers or 1)
            started += 1
        except exception.PasteAppNotFound as ex:
            log.warning("%s. ``enabled_apis`` includes bad values. "
                    "Fix to remove this warning.", six.text_type(ex))

    if started == 0:
        log.error('No APIs were started. '
                      'Check the enabled_apis config option.')
        sys.exit(1)

    launcher.wait()



