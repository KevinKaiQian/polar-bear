# Copyright 2010 OpenStack Foundation
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

from oslo_utils import strutils
import webob

from nova.api.openstack import common
from nova.api.openstack.compute.views import flavors as flavors_view
from nova.api.openstack import extensions
from nova.api.openstack import wsgi

from nova import exception
from nova.i18n import _
from nova import utils
from nova import objects
from oslo_serialization import jsonutils

ALIAS = 'slaves'


class FlavorsController(wsgi.Controller):
    """Flavor controller for the OpenStack API."""

    _view_builder_class = flavors_view.ViewBuilderV21

    @extensions.expected_errors(400)
    def index(self, req):
        """Return all flavors in brief."""
        context = req.environ['nova.context']
        compute_nodes=objects.ComputeNodeList.get_all(context)
        results = {}
        for node in compute_nodes: 
            results[node.uuid]={}
            results[node.uuid]["id"]=node.id
            results[node.uuid]["host"]=node.host
        return results

    @extensions.expected_errors(400)
    def detail(self, req):
        """Return all flavors in detail."""
        context = req.environ['nova.context']
        compute_nodes=objects.ComputeNodeList.get_all(context)
        results = {}
        for node in compute_nodes: 
            results[node.uuid]={}
            results[node.uuid]["compute_node_type"] =node.compute_node_type
            results[node.uuid]["compute_node_method"]=jsonutils.loads(node.compute_node_method)
            results[node.uuid]["host"]=node.host
            results[node.uuid]["id"]=node.id
        return results
    @extensions.expected_errors(404)
    def show(self, req, id):
        """Return data about the given flavor id."""
        context = req.environ['nova.context']
        try:
            node = objects.ComputeNode.get_by_id(context,compute_id=id)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.format_message())
        results = {}
        results["id"]=node.id
        results["uuid"]=node.uuid
        results["host"]=node.host
        results["compute_node_type"] =node.compute_node_type
        results["compute_node_method"]=jsonutils.loads(node.compute_node_method)

        return results




class Slaves(extensions.V21APIExtensionBase):
    """Slaves Extension."""
    name = "Slaves"
    alias = ALIAS
    version = 1

    def get_resources(self):
        collection_actions = {'detail': 'GET'}
        member_actions = {'action': 'POST'}

        resources = [
            extensions.ResourceExtension(ALIAS,
                                         FlavorsController(),
                                         member_name='flavor',
                                         collection_actions=collection_actions,
                                         member_actions=member_actions)
            ]
        return resources

    def get_controller_extensions(self):
        return []
