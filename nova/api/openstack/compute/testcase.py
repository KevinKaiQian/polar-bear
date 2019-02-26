# Copyright 2010 OpenStack Foundation
# Copyright 2011 Piston Cloud Computing, Inc
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

import re
from oslo_log import log as logging

import stevedore
from webob import exc

from nova.api.openstack import common
from nova.api.openstack.compute import helpers

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute
from nova import config
from nova import exception
from nova.i18n import _
from nova.i18n import _LW
from nova import utils
from nova import conductor
from oslo_serialization import jsonutils

ALIAS = 'testcases'

DEVICE_TAGGING_MIN_COMPUTE_VERSION = 14

CONF = config.CONF

LOG = logging.getLogger(__name__)


class CaseController(wsgi.Controller):

    def __init__(self, **kwargs):
        self.compute_task_api = conductor.ComputeTaskAPI()

        # Look for API schema of server create extension

    @extensions.expected_errors((400, 403))
    def index(self, req):
        """Returns a list of server names and ids for a given user."""
        context = req.environ['nova.context']
        try:
            servers = {'servers':'testbed'}
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())
        return servers


    @extensions.expected_errors(404)
    def show(self, req, id):
        """Returns server details by server id."""
        context = req.environ['nova.context']
        instance = self._get_server(context, req, id, is_detail=True)
        return self._view_builder.show(req, instance)

    @wsgi.response(202)
    @extensions.expected_errors((400, 403, 409))
    def create(self, req, body):
        try:
            #import pdb;pdb.set_trace()
            context = req.environ['nova.context']
            body_data = body
            self.compute_task_api.handle_cases(context,body_data)
            return  jsonutils.dumps(body_data)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())


    @extensions.expected_errors((400, 404))
    def update(self, req, id, body):
        """Update server then pass on to version-specific controller."""

        ctxt = req.environ['nova.context']
        server = body['server']
        print server


    @wsgi.response(204)
    @extensions.expected_errors((404, 409))
    def delete(self, req, id):
        """Destroys a server."""
        try:
            self._delete(req.environ['nova.context'], req, id)
        except exception.InstanceNotFound:
            msg = _("Instance could not be found")
            raise exc.HTTPNotFound(explanation=msg)
        except exception.InstanceUnknownCell as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except exception.InstanceIsLocked as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.InstanceInvalidState as state_error:
            common.raise_http_conflict_for_instance_invalid_state(state_error,
                    'delete', id)

class Testcase(extensions.V21APIExtensionBase):
    """Servers."""

    name = "Testcase"
    alias = ALIAS
    version = 1

    def get_resources(self):
        member_actions = {'action': 'POST'}
        collection_actions = {'detail': 'GET'}
        resources = [
            extensions.ResourceExtension(
                ALIAS,
                CaseController(extension_info=self.extension_info),
                member_name='Testcase', collection_actions=collection_actions,
                member_actions=member_actions)]

        return resources

    def get_controller_extensions(self):
        return []
