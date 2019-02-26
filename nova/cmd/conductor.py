#    Copyright 2012 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Starter script for Nova Conductor."""

import sys
import os
#sys.path.append(os.path.dirname(os.getcwd())) 
sys.path.append(os.path.dirname(os.path.dirname(os.getcwd())))
#import pdb;pdb.set_trace()
from oslo_concurrency import processutils
from oslo_log import log as logging


from nova import config
from nova import objects
from nova import service
from nova import utils
from nova import rpc
from nova.db.sqlalchemy import api as sqlalchemy_api

CONF = config.CONF


def main():

    rpc.set_defaults(control_exchange='nova')
    rpc.init(CONF)
    sqlalchemy_api.configure(CONF)
    logging.setup(CONF, "nova")
    objects.register_all()
    #import pdb;pdb.set_trace()
    server = service.Service.create(binary='nova-conductor',
                                    topic=CONF.conductor.topic,
                                    manager=CONF.conductor.manager)
    workers = CONF.conductor.workers or processutils.get_worker_count()
    service.serve(server, workers=workers)
    service.wait()

if "__main__" == __name__:
    main()
