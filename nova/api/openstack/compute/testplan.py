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
from nova import objects
import json

ALIAS = 'testplan'

DEVICE_TAGGING_MIN_COMPUTE_VERSION = 14

CONF = config.CONF

LOG = logging.getLogger(__name__)



class InstantiationData(object):
    """The data to create or update a stack.

    The data accompanying a PUT or POST request.
    """

    PARAMS = (
        PARAM_TESTPLAN_NAME,
        PARAM_TESTPLAN,
        PARAM_ENVIRONMENT,

    ) = (
        'name',
        'testplan',
        'environment',
    )

    def __init__(self, data):
        """Initialise from the request object.

        If called from the PATCH api, insert a flag for the engine code
        to distinguish.
        """
        self.data = data


    def testplan_name(self):
        """Return the stack name."""
        if self.PARAM_TESTPLAN_NAME not in self.data:
            raise exc.HTTPBadRequest(_("No stack name specified"))
        return self.data[self.PARAM_TESTPLAN_NAME]

    def template(self):
        """Get template file contents.

        Get template file contents, either inline, from stack adopt data or
        from a URL, in JSON or YAML format.
        """
        template_data = None


        if self.PARAM_TESTPLAN in self.data:
            template_data = self.data[self.PARAM_TESTPLAN]
            if isinstance(template_data, dict):
                return template_data
            raise exc.HTTPBadRequest("testplan format is not correct")
        else:
            raise exc.HTTPBadRequest("body has not testplan")

    def environment(self):
        """Get the user-supplied environment for the stack in YAML format.

        If the user supplied Parameters then merge these into the
        environment global options.
        """

        if self.PARAM_ENVIRONMENT in self.data:
            env_data = self.data[self.PARAM_ENVIRONMENT]
            return env_data
        raise exc.HTTPBadRequest("body has not testplan")
        
    def args(self):
        """Get any additional arguments supplied by the user."""
        params = self.data.items()
        return dict((k, v) for k, v in params if k not in self.PARAMS)



class TestPlanController(wsgi.Controller):

    def __init__(self, **kwargs):
        self.compute_task_api = conductor.ComputeTaskAPI()

        # Look for API schema of server create extension

    @wsgi.response(202)
    @extensions.expected_errors((400, 403, 409))
    def create(self, req, body):
        try:
     
            context = req.environ['nova.context']

            data = InstantiationData(body)
            args = data.args()
            name = data.testplan_name()
            testplans=data.template()
            environment=data.environment()

            testplan=objects.TestPlan(context)
            testplan.status="initing"
            testplan.testplan_name= name
            testplan.create() 
            environment['id']= testplan['id']
            
            self.compute_task_api.handle_testplan(context,name=name,environment= environment,testplan=testplans)
            res={"TestPlan":environment['id']}
            return  jsonutils.dumps(res)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())

    @extensions.expected_errors(404)
    def show(self, req, id):
        try:
            #import pdb;pdb.set_trace()
            context = req.environ['nova.context']
            result ={}
            try:

                plan=objects.TestPlan.get_by_id(context,id)
                res=json.loads(plan['result'])
            except exception.CaseNotFound:
                result['message']="not find testplan through id = " + str(id)
                return jsonutils.dumps(result)

            return jsonutils.dumps(res)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())      
    

class Testplan(extensions.V21APIExtensionBase):
    """Servers."""

    name = "Testplan"
    alias = ALIAS
    version = 1

    def get_resources(self):

        member_actions = {'action': 'POST'}

        resources = [
            extensions.ResourceExtension(
                ALIAS,
                TestPlanController(extension_info=self.extension_info),
                member_name='Testplan',member_actions=member_actions)]

        return resources

    def get_controller_extensions(self):
        return []
