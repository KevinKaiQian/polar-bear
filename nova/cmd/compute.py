# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

"""Starter script for Nova Compute."""

import shlex
import sys

import os
#sys.path.append(os.path.dirname(os.getcwd())) 
sys.path.append(os.path.dirname(os.path.dirname(os.getcwd())))

from oslo_log import log as logging
from oslo_privsep import priv_context
#import pdb;pdb.set_trace()
from nova.cmd import common as cmd_common
from nova.conductor import rpcapi as conductor_rpcapi
from nova import config

from nova.i18n import _LW
from nova import objects
from nova.objects import base as objects_base
from nova import service
from nova import utils
#from nova import version
from nova import rpc
from nova.db.sqlalchemy import api as sqlalchemy_api

CONF = config.CONF
LOG = logging.getLogger('nova.compute')


def main():
    #config.parse_args(sys.argv)
    logging.setup(CONF, 'nova')
    rpc.set_defaults(control_exchange='nova')
    rpc.init(CONF)
    sqlalchemy_api.configure(CONF)
    #priv_context.init(root_helper=shlex.split(utils.get_root_helper()))
    #utils.monkey_patch()
    objects.register_all()

    #gmr.TextGuruMeditation.setup_autorun(version)

    if not CONF.conductor.use_local:
        cmd_common.block_db_access('nova-compute')
        objects_base.NovaObject.indirection_api = \
            conductor_rpcapi.ConductorAPI()
    else:
        LOG.warning(_LW('Conductor local mode is deprecated and will '
                        'be removed in a subsequent release'))
    #import pdb;pdb.set_trace()
    server = service.Service.create(binary='nova-compute',
                                    topic=CONF.compute_topic,
                                    db_allowed=CONF.conductor.use_local)
    service.serve(server)
    service.wait()


if "__main__" == __name__:
    main()
