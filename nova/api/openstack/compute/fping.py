# Copyright 2011 Grid Dynamics
# Copyright 2011 OpenStack Foundation
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

import itertools
import os

import six
from webob import exc

from nova.api.openstack.api_version_request \
    import MAX_PROXY_API_SUPPORT_VERSION
from nova.api.openstack import common
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute
from nova import config
from nova.i18n import _

from nova import utils

ALIAS = "os-fping"

CONF = config.CONF


class FpingController(wsgi.Controller):

    def __init__(self, network_api=None):
        self.compute_api = compute.API()
        self.last_call = {}
        self.host_api = compute.HostAPI()

    def check_fping(self):
        if not os.access(CONF.fping_path, os.X_OK):
            raise exc.HTTPServiceUnavailable(
                explanation=_("fping utility is not found."))

    @staticmethod
    def fping(ips):
        fping_ret = utils.execute(CONF.fping_path, *ips,
                                  check_exit_code=False)
        if not fping_ret:
            return set()
        alive_ips = set()
        for line in fping_ret[0].split("\n"):
            ip = line.split(" ", 1)[0]
            if "alive" in line:
                alive_ips.add(ip)
        return alive_ips

    @staticmethod
    def _get_instance_ips(context, instance):
        ret = []
        for network in common.get_networks_for_instance(
                context, instance).values():
            all_ips = itertools.chain(network["ips"], network["floating_ips"])
            ret += [ip["address"] for ip in all_ips]
        return ret

    @wsgi.Controller.api_version("2.1", MAX_PROXY_API_SUPPORT_VERSION)
    @extensions.expected_errors(503)
    def index(self, req):
        context = req.environ["nova.context"]
        search_opts = dict(deleted=False)
        if "all_tenants" in req.GET:
            pass
        else:
            if context.project_id:
                search_opts["project_id"] = context.project_id
            else:
                search_opts["user_id"] = context.user_id
        self.check_fping()
        include = req.GET.get("include", None)
        if include:
            include = set(include.split(","))
            exclude = set()
        else:
            include = None
            exclude = req.GET.get("exclude", None)
            if exclude:
                exclude = set(exclude.split(","))
            else:
                exclude = set()



        ip_list = []
        instance_ips = {}
        instance_projects = {}

        _services = [
           s
           for s in self.host_api.service_get_all(context, set_zones=True)
        ]


        for service in _services:
            binary = service.binary
            if binary is None :
                continue
            ips = str(service.host)
            service_binary=str(str(service.id)+" : ") + str(service.binary)
            instance_ips[service_binary] = ips
            instance_projects[service_binary] = service_binary
            ip_list.append(ips)

        alive_ips = self.fping(ip_list)
        res = []
        for sr, ips in six.iteritems(instance_ips):
            res.append({
                "service": sr,
                "ip": ips,
                "alive": bool(set(ips) & alive_ips),
            })
        return {"services": res}


    @wsgi.Controller.api_version("2.1", MAX_PROXY_API_SUPPORT_VERSION)
    @extensions.expected_errors((404, 503))
    def show(self, req, id):
        context = req.environ["nova.context"]
        self.check_fping()
        instance = common.get_instance(self.compute_api, context, id)
        ips = [str(ip) for ip in self._get_instance_ips(context, instance)]
        alive_ips = self.fping(ips)
        return {
            "server": {
                "id": instance.uuid,
                "project_id": instance.project_id,
                "alive": bool(set(ips) & alive_ips),
            }
        }


class Fping(extensions.V21APIExtensionBase):
    """Fping Management Extension."""

    name = "Fping"
    alias = ALIAS
    version = 1

    def get_resources(self):
        res = extensions.ResourceExtension(ALIAS, FpingController())
        return [res]

    def get_controller_extensions(self):
        return []
