
这个项目是基于openstack框架重构的测试框架。保留了api conductor 和 compute 模块。

目标：以api模块为对外交互通道。conductor角色转化成 controller 角色，负责所有逻辑和引擎解析。
     compute 模块抽象成测试设备，抽象的方式是以plugin的形式完成的。
     比如现在有编译插件 部署插件 测试用例插件 。一个compute可以拥有其中一个或者多个。
    
现状：主体结构调试完成（从发消息到api - conductor - compute 最终执行）。现在 compute 执行的log 还没有上报。

计划：
    log 处理
    类似openstack heat engine （testplan 模式）。现在使用的是testcase 模式，只能调试单个case
    抽闲组的概念。把computes 绑到组上面。 做到隔离compute节点。
    
安装步骤：

安装rabbitmq 组件

	yum install centos-release-openstack-queens -y
	yum install rabbitmq-server -y
	systemctl enable rabbitmq-server.service
	systemctl start rabbitmq-server.service
	rabbitmqctl add_user openstack Newsys@1234
	rabbitmqctl set_user_tags openstack  administrator
	rabbitmqctl set_permissions openstack ".*" ".*" ".*"
	rabbitmq-plugins enable rabbitmq_management
	systemctl restart rabbitmq-server.service
	
	systemctl disable firewalld
	systemctl stop firewalld

安装 MySQL 数据库 Python 标准数据库接口 和 fping 工具

     yum install MySQL-python fping -y

安装 python 第三方库 ：

     pip install babel monotonic enum34 stevedore eventlet fasteners PasteDeploy Paste routes microversion_parse debtcollector netaddr rfc3986  python-dateutil positional iso8601 flask_sqlalchemy prettytable netifaces pymysql webob kombu cachetools paramiko futurist jsonschema cffi msgpack pytz cryptography

使用方法：

查询所有的slave节概况：
	
curl -s http://135.251.149.80:8774/v2.1/slaves/detail | python -m json.tool
	{
		"b16059f4-4000-4c02-b222-22cfc62108de": {
			"compute_node_method": {
				"linux_system": {
					"run_shell": "params is one dict     one key command  and the second one is args (command=mkdir : args=test)"
				}
			},
			"compute_node_type": "linux_system",
			"host": "135.251.149.80",
			"id": 6
		}
	}
查询所有的slave节点具体的信息：

curl -s http://135.251.149.80:8774/v2.1/slaves/detail | python -m json.tool
	{
		"5b9e675c-728d-4eb7-9b9f-cc76ebdd4381": {
			"compute_node_method": {
				"linux_system": {
					"run_shell": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd",
					"system_information": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd"
				}
			},
			"compute_node_type": "linux_system",
			"host": "135.251.149.81",
			"id": 7
		},
		"b16059f4-4000-4c02-b222-22cfc62108de": {
			"compute_node_method": {
				"build_server": {
					"run_shell": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd",
					"system_information": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd"
				},
				"linux_system": {
					"run_shell": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd",
					"system_information": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd"
				}
			},
			"compute_node_type": "linux_system,build_server",
			"host": "135.251.149.80",
			"id": 6
		}
	}

查询单个slave节点具体的信息：

	curl -s http://135.251.149.80:8774/v2.1/slaves/6 | python -m json.tool
	{
		"compute_node_method": {
			"build_server": {
				"run_shell": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd",
				"system_information": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd"
			},
			"linux_system": {
				"run_shell": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd",
				"system_information": "parameters is dict. command key is linux cmd. args key is parameters of linux cmd"
			}
		},
		"compute_node_type": "linux_system,build_server",
		"host": "135.251.149.80",
		"id": 6,
		"uuid": "b16059f4-4000-4c02-b222-22cfc62108de"
	}

执行一个case：

curl -s http://135.251.149.80:8774/v2.1/testcases -X POST -H "Content-Type:application/json" -d '{"plugin":"linux_system","host":"135.251.149.80","method":"run_shell","parameters":{"command":"ls","args":"-alt"}}' | python -m json.tool

上面命令中的 "plugin":"linux_system" 是插件的名字。 一个slave有多少插件可以在nova/cmd/nova.ini 中配置：

compute_plugin=nova.compute.manager_linux_system.ComputeManager_linux_system,nova.compute.manager_build_server.ComputeManager_build_server


上面命令中的 "parameters":{"command":"ls","args":"-alt"}} . 框架不帮忙处理parameters 的参数的异常处理，余下的异常框架都会处理


class ComputeManager_linux_system(base.Base):

    target = messaging.Target(namespace='linux_system', version='4.0')
    
    #import pdb;pdb.set_trace()
    def __init__(self):
        super(ComputeManager_linux_system, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()

    @nova_utils.add_task_describe(describe="parameters is dict. command key is linux cmd. args key is parameters of linux cmd")      
    @nova_utils.mark_task_status(namespace='linux_system',method_mark=True)
    def run_shell(self, context, parameters):
        cmd= parameters.get('command',None)
        arg= parameters.get('args',None)
        ca_dir="/root"
        out, err =utils.execute(cmd, arg , cwd=ca_dir,run_as_root=True)
        print out
    
