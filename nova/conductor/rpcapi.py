#    Copyright 2013 IBM Corp.
#    Copyright 2013 Red Hat, Inc.
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

"""Client side of the conductor RPC API."""

import oslo_messaging as messaging
from oslo_serialization import jsonutils
from oslo_versionedobjects import base as ovo_base

from nova import config
from nova.objects import base as objects_base
from nova import rpc

CONF = config.CONF


class ConductorAPI(object):


    VERSION_ALIASES = {
        'grizzly': '1.48',
        'havana': '1.58',
        'icehouse': '2.0',
        'juno': '2.0',
        'kilo': '2.1',
        'liberty': '3.0',
        'mitaka': '3.0',
    }

    def __init__(self):
        super(ConductorAPI, self).__init__()
        target = messaging.Target(topic=CONF.conductor.topic, version='3.0')
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.conductor,
                                               CONF.upgrade_levels.conductor)
        serializer = objects_base.NovaObjectSerializer()
        self.client = rpc.get_client(target,
                                     version_cap=version_cap,
                                     serializer=serializer)

    # TODO(hanlind): This method can be removed once oslo.versionedobjects
    # has been converted to use version_manifests in remotable_classmethod
    # operations, which will use the new class action handler.
    def object_class_action(self, context, objname, objmethod, objver,
                            args, kwargs):
        versions = ovo_base.obj_tree_get_versions(objname)
        return self.object_class_action_versions(context,
                                                 objname,
                                                 objmethod,
                                                 versions,
                                                 args, kwargs)

    def object_class_action_versions(self, context, objname, objmethod,
                                     object_versions, args, kwargs):
        cctxt = self.client.prepare()
        return cctxt.call(context, 'object_class_action_versions',
                          objname=objname, objmethod=objmethod,
                          object_versions=object_versions,
                          args=args, kwargs=kwargs)

    def object_action(self, context, objinst, objmethod, args, kwargs):
        cctxt = self.client.prepare()
        return cctxt.call(context, 'object_action', objinst=objinst,
                          objmethod=objmethod, args=args, kwargs=kwargs)

    def object_backport_versions(self, context, objinst, object_versions):
        cctxt = self.client.prepare()
        return cctxt.call(context, 'object_backport_versions', objinst=objinst,
                          object_versions=object_versions)


class ComputeTaskAPI(object):


    def __init__(self):
        super(ComputeTaskAPI, self).__init__()
        target = messaging.Target(topic=CONF.conductor.topic,
                                  namespace='compute_task',
                                  version='1.0')
        serializer = objects_base.NovaObjectSerializer()
        self.client = rpc.get_client(target, serializer=serializer)
        
    def handle_cases(self, context,data):

        version = '1.10'
        kw = {'data': data}
        cctxt = self.client.prepare(version=version)
        cctxt.cast(context, 'handle_cases', **kw)

    
    def report_cases_result(self, context,Caseid,output="",status="fail"):

        version = '1.10'
        kw = {'output':output,
              'status':status,
              'Caseid':Caseid}
        cctxt = self.client.prepare(version=version)
        cctxt.cast(context, 'report_cases_result', **kw)


