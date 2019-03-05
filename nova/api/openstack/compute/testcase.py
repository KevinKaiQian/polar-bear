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

ALIAS = 'testcases'

DEVICE_TAGGING_MIN_COMPUTE_VERSION = 14

CONF = config.CONF

LOG = logging.getLogger(__name__)


class CaseController(wsgi.Controller):

    def __init__(self, **kwargs):
        self.compute_task_api = conductor.ComputeTaskAPI()

        # Look for API schema of server create extension

    @extensions.expected_errors(404)
    def show(self, req, id):
        try:
            
            context = req.environ['nova.context']
            result ={}
            try:
                case=objects.TestCase.get_by_id(context,id)
            except exception.CaseNotFound:
                result['message']="not find testcase through id = " + str(id)
                return jsonutils.dumps(result)
    
            result['Message']=case["message"]
            result['CaseId']=case["id"]
            result['Status']=case['status']
            return jsonutils.dumps(result)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())

    @wsgi.response(202)
    @extensions.expected_errors((400, 403, 409))
    def create(self, req, body):
        try:
            #import pdb;pdb.set_trace()
            context = req.environ['nova.context']
            data = body

            case=objects.TestCase(context)
            case.host=data['host']
            case.status="initing"
            case.case_name= data['method']
            case.create() 
            data['id']= case['id']
            self.compute_task_api.handle_cases(context,data)
            res={"CaseId":case['id']}
            return  jsonutils.dumps(res)
        except exception.Invalid as err:
            raise exc.HTTPBadRequest(explanation=err.format_message())

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
