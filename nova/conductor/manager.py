#    Copyright 2013 IBM Corp.
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

"""Handles database requests from other nova services."""

import copy

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_utils import excutils
from oslo_utils import versionutils
import six

from nova.compute import rpcapi as compute_rpcapi
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute.utils import wrap_instance_event
from nova.compute import vm_states
from nova.conductor.tasks import live_migrate
from nova.conductor.tasks import migrate
from nova.db import base
from nova import exception
from nova.i18n import _, _LE, _LI, _LW

from nova import manager

from nova import objects
from nova.objects import base as nova_object
from nova import rpc
from nova.scheduler import client as scheduler_client
from nova.scheduler import utils as scheduler_utils
from nova import servicegroup
from nova import utils
from oslo_serialization import jsonutils
import contextlib
import eventlet.event
from eventlet import greenthread
import eventlet.semaphore
import eventlet.timeout
import time

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


@contextlib.contextmanager
def wait_for_case_status(context=None,case_name=None, case_id=None,deadline=300):

    try:
        LOG.info(_LI("execute case : %(name)s  %(id)s "), {'name':case_name,'id':case_id})
    except exception.NovaException:
        raise exception.NovaException(_('case failed'))
        deadline = 0
    yield
    with eventlet.timeout.Timeout(deadline):
        while True:
            case=objects.TestCase.get_by_id(context,case_id)
            if case['status']=='successfully':
                break
            time.sleep(5)

class ConductorManager(manager.Manager):


    target = messaging.Target(version='3.0')

    def __init__(self, *args, **kwargs):
        super(ConductorManager, self).__init__(service_name='conductor',
                                               *args, **kwargs)
        self.compute_task_mgr = ComputeTaskManager()
        self.additional_endpoints.append(self.compute_task_mgr)

    # NOTE(hanlind): This can be removed in version 4.0 of the RPC API
    def provider_fw_rule_get_all(self, context):
        # NOTE(hanlind): Simulate an empty db result for compat reasons.
        return []

    def _object_dispatch(self, target, method, args, kwargs):
        """Dispatch a call to an object method.

        This ensures that object methods get called and any exception
        that is raised gets wrapped in an ExpectedException for forwarding
        back to the caller (without spamming the conductor logs).
        """
        #import pdb;pdb.set_trace()
        try:
            # NOTE(danms): Keep the getattr inside the try block since
            # a missing method is really a client problem
            return getattr(target, method)(*args, **kwargs)
        except Exception:
            raise messaging.ExpectedException()

    def object_class_action_versions(self, context, objname, objmethod,
                                     object_versions, args, kwargs):
        objclass = nova_object.NovaObject.obj_class_from_name(
            objname, object_versions[objname])
        args = tuple([context] + list(args))
        result = self._object_dispatch(objclass, objmethod, args, kwargs)
        # NOTE(danms): The RPC layer will convert to primitives for us,
        # but in this case, we need to honor the version the client is
        # asking for, so we do it before returning here.
        # NOTE(hanlind): Do not convert older than requested objects,
        # see bug #1596119.
        if isinstance(result, nova_object.NovaObject):
            target_version = object_versions[objname]
            requested_version = versionutils.convert_version_to_tuple(
                target_version)
            actual_version = versionutils.convert_version_to_tuple(
                result.VERSION)
            do_backport = requested_version < actual_version
            other_major_version = requested_version[0] != actual_version[0]
            if do_backport or other_major_version:
                result = result.obj_to_primitive(
                    target_version=target_version,
                    version_manifest=object_versions)
        return result

    def object_action(self, context, objinst, objmethod, args, kwargs):
        """Perform an action on an object."""
        oldobj = objinst.obj_clone()
        result = self._object_dispatch(objinst, objmethod, args, kwargs)
        updates = dict()
        # NOTE(danms): Diff the object with the one passed to us and
        # generate a list of changes to forward back
        for name, field in objinst.fields.items():
            if not objinst.obj_attr_is_set(name):
                # Avoid demand-loading anything
                continue
            if (not oldobj.obj_attr_is_set(name) or
                    getattr(oldobj, name) != getattr(objinst, name)):
                updates[name] = field.to_primitive(objinst, name,
                                                   getattr(objinst, name))
        # This is safe since a field named this would conflict with the
        # method anyway
        updates['obj_what_changed'] = objinst.obj_what_changed()
        return updates, result

    def object_backport_versions(self, context, objinst, object_versions):
        target = object_versions[objinst.obj_name()]
        LOG.debug('Backporting %(obj)s to %(ver)s with versions %(manifest)s',
                  {'obj': objinst.obj_name(),
                   'ver': target,
                   'manifest': ','.join(
                       ['%s=%s' % (name, ver)
                       for name, ver in object_versions.items()])})
        return objinst.obj_to_primitive(target_version=target,
                                        version_manifest=object_versions)

    def reset(self):
        objects.Service.clear_min_version_cache()


class ComputeTaskManager(base.Base):


    target = messaging.Target(namespace='compute_task', version='1.15')
    
    #import pdb;pdb.set_trace()
    def __init__(self):
        super(ComputeTaskManager, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeCaseAPI()

        self.servicegroup_api = servicegroup.API()
        self.scheduler_client = scheduler_client.SchedulerClient()
        self.notifier = rpc.get_notifier('compute', CONF.host)

    def reset(self,namespace):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeCaseAPI(namespace)
        
    def handle_cases(self, context, data):
        # TODO(ndipanov): Remove block_device_mapping and legacy_bdm in version
        #                 2.0 of the RPC API.
        # TODO(danms): Remove this in version 2.0 of the RPC API
    
        plugin=data.get("plugin",None)
        host = data.get("host",None)
        method = data.get("method",None)
        if plugin and host:
            obj=objects.ComputeNode.get_by_host_and_nodename(
                context, host, plugin)
            if obj.host!= host and obj.compute_node_type != plugin:
                raise exception.NotFound(message="host not match")
            if plugin not in obj.compute_node_type :
                raise exception.NotFound(message="plugin not match")
            if not jsonutils.loads(obj.compute_node_method)[plugin].has_key(method):
                raise exception.NotFound(message="method not match")
        else:
            return "input host and pulgin is wrong"
        
        self.reset(plugin)
        try:
            parameters = data.get("parameters",None)
            parameters['id']= data['id']

        except exception as e:
            raise exception.NovaException(_(str(e)))  
        try:
            
            with wait_for_case_status(context=context,case_name=method,case_id=parameters['id'],deadline=30):
                case=objects.TestCase.get_by_id(context,parameters['id'])
                case['status']='execute'
                case.save()
                self.compute_rpcapi.run(context,host=host,method=method, parameters= parameters)
       
        except exception:
            LOG.warning(_LW('Timeout waiting for case execute. set status to fail'))
            case=objects.TestCase.get_by_id(context,parameters['id'])
            case['status']='fail'
            case.save()

    
    def report_cases_result(self, context, Caseid,output,status):
        if output and status and Caseid:
            cases=objects.TestCase.get_by_id(context,Caseid)
            cases.message= output
            cases.status= status
            cases.save()

 
