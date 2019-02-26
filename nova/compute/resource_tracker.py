# Copyright (c) 2012 OpenStack Foundation
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

"""
Track resources like memory and disk for a compute host.  Provides the
scheduler with useful information about availability through the ComputeNode
model.
"""
import copy

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import importutils


from nova.compute import monitors
from nova.compute import task_states
from nova.compute import vm_states

from nova import config
from nova import exception
from nova.i18n import _, _LI, _LW
from nova import objects
from nova.objects import base as obj_base



from nova import rpc
from nova.scheduler import client as scheduler_client
from nova import utils
from oslo_utils import importutils


CONF =config.CONF

LOG = logging.getLogger(__name__)
COMPUTE_RESOURCE_SEMAPHORE = "compute_resources"



class ResourceTracker(object):

    def __init__(self, host):
        self.host = host
        self.compute_node_type = set()
        self.compute_node_method = {}
       
        for plugin in CONF.compute_plugin:
            class_name=importutils.import_class(plugin)
            for  name ,func in class_name.__dict__.items():
 
                if getattr(func,'_namespace',False) and getattr(func,'_method_mark',False) :
                    self.compute_node_type.add(getattr(func,'_namespace',False))
                    if  self.compute_node_method.has_key(getattr(func,'_namespace',False)):
                        self.compute_node_method[getattr(func,'_namespace',False)][name] =getattr(func,'_describe',"None")
                    else:
                        self.compute_node_method[getattr(func,'_namespace',False)]={}
                        self.compute_node_method[getattr(func,'_namespace',False)][name]=getattr(func,'_describe',"None")
                    

        self.old_resources = objects.ComputeNode()

    @property
    def disabled(self):
        return self.compute_node is None

    def _init_compute_node(self, context, resources):

        #import pdb;pdb.set_trace()
        self.compute_node = self._get_compute_node(context)
        if self.compute_node:
            if cmp(str(self.compute_node.compute_node_method),jsonutils.dumps(self.compute_node_method)) or\
            ','.join(self.compute_node_type)==self.compute_node.compute_node_type:
                self._update(context,self.compute_node.id,resources)
                return
            return
        self.compute_node = objects.ComputeNode(context)
        self.compute_node.host = self.host
        self._copy_resources()
        self.compute_node.create()
        LOG.info(_LI('Compute_service record created for '
                     '%(host)s'),
                 {'host': self.host})
    def _copy_resources(self):

        self.compute_node.compute_node_type = ','.join(self.compute_node_type)
        self.compute_node.compute_node_method = jsonutils.dumps(self.compute_node_method)

    def update_available_resource(self, context):

        LOG.info(_LI("Auditing locally available compute resources for "
                     "node %(node)s"),
                 {'node': self.host})
        resources = {}
        resources['compute_node_type']= ','.join(self.compute_node_type)
        resources['compute_node_method']= jsonutils.dumps(self.compute_node_method)
    
        self._update_available_resource(context, resources)


    @utils.synchronized(COMPUTE_RESOURCE_SEMAPHORE)
    def _update_available_resource(self, context, resources):

        # initialize the compute node object, creating it
        # if it does not already exist.
        self._init_compute_node(context, resources)


    def _get_compute_node(self, context):
        """Returns compute node for the host and nodename."""
        try:
            #import pdb;pdb.set_trace()
            return objects.ComputeNode.get_by_host_and_nodename(
                context, self.host, self.compute_node_type)
        except exception.NotFound:
            LOG.warning(_LW("No compute node record for %(host)s"),
                        {'host': self.host})
            
    def _resource_change(self):
        """Check to see if any resources have changed."""
        if not obj_base.obj_equal_prims(self.compute_node, self.old_resources):
            self.old_resources = copy.deepcopy(self.compute_node)
            return True
        return False

    def _update(self, context,compute_id,values):
        """Update partial stats locally and populate them to Scheduler."""
        self.compute_node.compute_node_type=','.join(self.compute_node_type)
        self.compute_node.compute_node_method=jsonutils.dumps(self.compute_node_method)
        self.compute_node.save()







    