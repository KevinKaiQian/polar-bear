import copy
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
import six
from nova.compute import rpcapi as compute_rpcapi
from nova.db import base
from nova import exception
from nova.i18n import _, _LE, _LI, _LW
from nova import manager
from nova.compute import utils as compute_utils
from nova import utils
from nova import rpc
from nova import servicegroup

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
import json
import os
import shlex
import docker
import rpclient

def get_docker_client():
    return docker.APIClient


class DockerWorker(object):

    def __init__(self, parameters):
        self.params = parameters
        self.changed = False
        # Use this to store arguments to pass to exit_json().
        self.result = {}

        # TLS not fully implemented
        # tls_config = self.generate_tls()

        options = {
            'version': self.params.get('api_version')
        }

        self.dc = get_docker_client()(**options)
    def stop_container(self):
        name = self.params.get('name')
        graceful_timeout = self.params.get('graceful_timeout')
        if not graceful_timeout:
            graceful_timeout = 10
        container = self.check_container()
        if not container:
            raise ("No such container: {} to stop".format(name))
        elif not container['Status'].startswith('Exited '):
            self.changed = True
            self.dc.stop(name, timeout=graceful_timeout)
    def pull_image(self):
        if self.params.get('auth_username'):
            self.dc.login(
                username=self.params.get('auth_username'),
                password=self.params.get('auth_password'),
                registry=self.params.get('auth_registry'),
                email=self.params.get('auth_email')
            )

        image, tag = self.parse_image()
        old_image_id = self.get_image_id()

        statuses = [
            json.loads(line.strip().decode('utf-8')) for line in self.dc.pull(
                repository=image, tag=tag, stream=True
            )
        ]

        for status in reversed(statuses):
            if 'error' in status:
                if status['error'].endswith('not found'):
                    self.module.fail_json(
                        msg="The requested image does not exist: {}:{}".format(
                            image, tag),
                        failed=True
                    )
                else:
                    self.module.fail_json(
                        msg="Unknown error message: {}".format(
                            status['error']),
                        failed=True
                    )

        new_image_id = self.get_image_id()
        self.changed = old_image_id != new_image_id
    def remove_container(self):
        if self.check_container():
            self.changed = True
            # NOTE(jeffrey4l): in some case, docker failed to remove container
            # filesystem and raise error.  But the container info is
            # disappeared already. If this happens, assume the container is
            # removed.
            try:
                self.dc.remove_container(
                    container=self.params.get('name'),
                    force=True
                )
            except docker.errors.APIError:
                if self.check_container():
                    raise
    def check_container(self):
        find_name = '/{}'.format(self.params.get('name'))
        for cont in self.dc.containers(all=True):
            if find_name in cont['Names']:
                return cont

    def generate_volumes(self):
        volumes = self.params.get('volumes')
        if not volumes:
            return None, None

        vol_list = list()
        vol_dict = dict()

        for vol in volumes:
            if len(vol) == 0:
                continue

            if ':' not in vol:
                vol_list.append(vol)
                continue

            split_vol = vol.split(':')

            if (len(split_vol) == 2
               and ('/' not in split_vol[0] or '/' in split_vol[1])):
                split_vol.append('rw')

            vol_list.append(split_vol[1])
            vol_dict.update({
                split_vol[0]: {
                    'bind': split_vol[1],
                    'mode': split_vol[2]
                }
            })

        return vol_list, vol_dict

    def parse_image(self):
        full_image = self.params.get('image')

        if '/' in full_image:
            registry, image = full_image.split('/', 1)
        else:
            image = full_image

        if ':' in image:
            return full_image.rsplit(':', 1)
        else:
            return full_image, 'latest'

    def check_image(self):
        find_image = ':'.join(self.parse_image())
        for image in self.dc.images():
            repo_tags = image.get('RepoTags')
            if not repo_tags:
                continue
            for image_name in repo_tags:
                if image_name == find_image:
                    return image

    def build_container_options(self):
        volumes, binds = self.generate_volumes()
        self.params['tty'] = bool(self.params['tty'])
        self.params['detach'] = bool(self.params['detach'])
        self.params['privileged'] = bool(self.params['privileged'] )
        self.params['remove_on_exit'] = bool(self.params['remove_on_exit'])
        if self.params.get('command')=="None":
            self.params['command']=None
        return {
            'command': self.params.get('command'),
            'detach': self.params.get('detach'),
            'environment': self.params.get('environment'),
            'host_config': self.build_host_config(binds),
            'labels': self.params.get('labels'),
            'image': self.params.get('image'),
            'name': self.params.get('name'),
            'volumes': volumes,
            'tty': self.params.get('tty'),
        }
    def build_host_config(self, binds):
        if self.params.get('volumes_from') == "None":
            self.params['volumes_from']=None
        options = {
            'network_mode': 'host',
            'ipc_mode': self.params.get('ipc_mode'),
            'cap_add': self.params.get('cap_add'),
            'security_opt': self.params.get('security_opt'),
            'pid_mode': self.params.get('pid_mode'),
            'privileged': self.params.get('privileged'),
            'volumes_from': self.params.get('volumes_from')
        }

        if self.params.get('restart_policy') in ['on-failure',
                                                 'always',
                                                 'unless-stopped']:
            policy = {'Name': self.params.get('restart_policy')}
            # NOTE(Jeffrey4l): MaximumRetryCount is only needed for on-failure
            # policy
            if self.params.get('restart_policy') == 'on-failure':
                retries = self.params.get('restart_retries')
                policy['MaximumRetryCount'] = retries
            options['restart_policy'] = policy

        if binds:
            options['binds'] = binds

        return self.dc.create_host_config(**options)

    def _inject_env_var(self, environment_info):
        newenv = {
            'KOLLA_SERVICE_NAME': self.params.get('name').replace('_', '-')
        }
        environment_info.update(newenv)
        return environment_info

    def _format_env_vars(self):
        env = self._inject_env_var(self.params.get('environment'))
        return {k: "" if env[k] is None else env[k] for k in env}

    def create_container(self):
        self.changed = True
        options = self.build_container_options()
        self.dc.create_container(**options)

    def recreate_or_restart_container(self):
        self.changed = True
        container = self.check_container()

        if not container:
            self.start_container()
            return

    def start_container(self):
        if not self.check_image():
            self.pull_image()

        container = self.check_container()
        if container and self.check_container_differs():
            self.stop_container()
            self.remove_container()
            container = self.check_container()

        if not container:
            self.create_container()
            container = self.check_container()

        if not container['Status'].startswith('Up '):
            self.changed = True
            self.dc.start(container=self.params.get('name'))

        # We do not want to detach so we wait around for container to exit
        if not self.params.get('detach'):
            rc = self.dc.wait(self.params.get('name'))
            # NOTE(jeffrey4l): since python docker package 3.0, wait return a
            # dict all the time.
            if isinstance(rc, dict):
                rc = rc['StatusCode']
            # Include container's return code, standard output and error in the
            # result.
            self.result['rc'] = rc
            self.result['stdout'] = self.dc.logs(self.params.get('name'),
                                                 stdout=True, stderr=False)
            self.result['stderr'] = self.dc.logs(self.params.get('name'),
                                                 stdout=False, stderr=True)
            if self.params.get('remove_on_exit'):
                self.stop_container()
                self.remove_container()
            if rc != 0:
                raise ("Container exited with non-zero return code %s" % rc)


class ComputeManager_docker(base.Base):

    target = messaging.Target(namespace='docker', version='4.0')
    def __init__(self):
        super(ComputeManager_docker, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()


    @compute_utils.mark_describe_task(namespace='docker',
                                      describe="operate on the container",
                                      parameters={'action':"docker action method",
                                                  'image':'docker image name'})
    def start_container(self, context, parameters,topic):
        LOG.info(_LI("docker operate: %s"),json.dumps(parameters))
        out,status,method = '','FAIL','get'
        stepid = parameters.get('stepid', None)
        try:
            dw = DockerWorker(parameters)
            dw.start_container()
            out="start container successfully"
            status="PASS"
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)
        except BaseException as e:
            status = "FAIL"
            out=e.message
            LOG.info(str(e.message))
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)




    def remove_container(self, context, parameters,topic):
        LOG.info(_LI("docker operate: %s"),json.dumps(parameters))
        out,status,method = '','FAIL','get'
        stepid = parameters.get('stepid', None)
        try:
            dw = DockerWorker(parameters)
            dw.remove_container()
            out="start container successfully"
            status="PASS"
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)
        except BaseException as e:
            status = "FAIL"
            out=e.message
            LOG.info(str(e.message))
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)

    def docker_command(self, context, parameters,topic):
        name=parameters.get('name')
        command=parameters.get('command')
        out, status, method = '', 'FAIL', 'docker_command'
        stepid = parameters.get('stepid', None)
        try:
            dc = get_docker_client()(version='auto')
            con = dc.containers(filters=dict(name=name,
                                                 status='running'))
            if not con:raise ("container is not running")
            con = con[0]
            job = dc.exec_create(con, command)
            out = dc.exec_start(job)
            status = "PASS"
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)
        except BaseException as e:
            status = "FAIL"
            out=e.message
            LOG.info(str(e.message))
            rpclient.RPCClient(topic=topic).result(ctxt=context, method=method, out=out, status=status, stepid=stepid)







