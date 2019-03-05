
这个项目是基于openstack框架重构的测试框架。保留了api conductor 和 compute 模块。

目标：以api模块为对外交互通道。conductor角色转化成 controller 角色，负责所有逻辑和引擎解析。
     compute 模块抽象成测试设备，抽象的方式是以plugin的形式完成的。
     比如现在有编译插件 部署插件 测试用例插件 。一个compute可以拥有其中一个或者多个。
    
现状：主体结构调试完成（从发消息到api - conductor - compute 最终执行）。现在 compute 执行的log 还没有上报。 guide 还没有写具体，现在是安装不起来的。

计划：
    log 处理
    类似openstack heat engine （testplan 模式）。现在使用的是testcase 模式，只能调试单个case
    抽闲组的概念。把computes 绑到组上面。 做到隔离compute节点。
    
安装步骤：

安装rabbitmq 组件

	yum install centos-release-openstack-queens -y
	yum install rabbitmq-server -y

	systemctl enable rabbitmq-server.service && systemctl start rabbitmq-server.service

	rabbitmqctl add_user openstack Newsys@1234 && rabbitmqctl set_user_tags openstack  administrator && rabbitmqctl set_permissions openstack ".*" ".*" ".*"

	rabbitmq-plugins enable rabbitmq_management && systemctl restart rabbitmq-server.service

	systemctl disable firewalld && systemctl stop firewalld


安装 MySQL 数据库 Python 标准数据库接口 和 fping 工具

     yum install MySQL-python fping -y

安装 python 第三方库 ：
     easy_install pip

     pip install babel monotonic enum34 stevedore eventlet fasteners PasteDeploy Paste routes microversion_parse debtcollector netaddr rfc3986  python-dateutil positional iso8601 flask_sqlalchemy prettytable netifaces pymysql webob kombu cachetools paramiko futurist jsonschema cffi msgpack pytz cryptography

下载代码： 
git clone https://github.com/KevinKaiQian/polar-bear.git

创建数据库nova：

	数据库自己创建。没有脚本

创建数据库表：

	使用项目目录下的polar-bear/syncdb.py 文件。 需要修改下syncdb.py 文件中数据库的配置并执行这个python 脚本。
	engine = create_engine('mysql+mysqldb://root:t-span@192.168.1.99/nova?charset=utf8')

修改配置文件：

	配置文件在项目目录polar-bear/nova/cmd/nova.ini .

	[DEFAULT]
	debug = true
	verbose = true
	#log_file =/root/api/nova/nova.log
	log_dir = /root/test/polar-bear/nova(log目录)
	fping_path=/usr/sbin/fping
	compute_plugin=nova.compute.manager_linux_system.ComputeManager_linux_system,nova.compute.manager_build_server.ComputeManager_build_server（这里面配置了两个插件）
	osapi_compute_workers=1
	my_ip=192.168.1.181（主机地址）
	host=192.168.1.181（主机地址）
	enabled_apis=osapi_compute
	rpc_backend=rabbit
	compute_driver=libvirt.LibvirtDriver
	default_publisher_id=192.168.1.181（主机地址）
	scheduler_max_attempts=3
	[database]
	connection=mysql+pymysql://root:t-span@192.168.1.99/nova（数据库配置）
	[oslo_messaging_amqp]
	[oslo_messaging_notifications]
	driver=messagingv2
	[oslo_messaging_rabbit]
	kombu_ssl_keyfile=
	kombu_ssl_certfile=
	kombu_ssl_ca_certs=
	rabbit_host=192.168.1.181（rabbitmq 地址。）
	rabbit_port=5672
	rabbit_use_ssl=False
	rabbit_userid=openstack
	rabbit_password=Newsys@1234

	[oslo_messaging_zmq]
	[oslo_middleware]
	[conductor]
	workers=1

	#[formatters]


使用方法：


查询所有的slave节概况：

	
curl -s http://192.168.1.181:8774/v2.1/slaves| python -m json.tool

	{
	    "850c5dc5-a007-47f6-a513-1924576e6050": {
		"host": "192.168.1.181",
		"id": 1
	    }
	}

	
查询所有的slave节点具体的信息：

curl -s http://192.168.1.181:8774/v2.1/slaves/detail | python -m json.tool

	{
	    "850c5dc5-a007-47f6-a513-1924576e6050": {
		"compute_node_method": {
		    "build_server": {
			"ping": "parameters is dict. address is target address count is count of ping . interval is time of two packet"
		    },
		    "linux_system": {
			"ping": "parameters is dict. address is target address count is count of ping . interval is time of two packet",
			"run_shell": "parameters is dict. cmd is command line. args is parameter"
		    }
		},
		"compute_node_type": "linux_system,build_server",
		"host": "192.168.1.181",
		"id": 1
	    }
	}


查询单个slave节点具体的信息：

curl -s http://192.168.1.181:8774/v2.1/slaves/1 | python -m json.tool

	{
	    "compute_node_method": {
		"build_server": {
		    "ping": "parameters is dict. address is target address count is count of ping . interval is time of two packet"
		},
		"linux_system": {
		    "ping": "parameters is dict. address is target address count is count of ping . interval is time of two packet",
		    "run_shell": "parameters is dict. cmd is command line. args is parameter"
		}
	    },
	    "compute_node_type": "linux_system,build_server",
	    "host": "192.168.1.181",
	    "id": 1,
	    "uuid": "850c5dc5-a007-47f6-a513-1924576e6050"
	}

执行一个case：

curl -s http://192.168.1.181:8774/v2.1/testcases -X POST -H "Content-Type:application/json" -d '{"plugin":"linux_system","host":"192.168.1.181","method":"run_shell","parameters":{"cmd":"ls","args":"-alt"}}' | python -m json.tool
	
	{
	    "CaseId": 1
	}

查询case执行结果：


 curl -s http://192.168.1.181:8774/v2.1/testcases/4 | python -m json.tool


	{
	    "CaseId": 4,
	    "Message": "total 28\ndr-xr-x---.  6 root root  188 Mar  4 22:38 .\ndrwxr-----.  3 root root   19 Mar  4 22:38 .pki\ndrwxr-xr-x.  3 root root   24 Mar  4 22:38 test\ndrwxr-xr-x.  4 root root   29 Mar  4 22:28 .cache\n-rw-------.  1 root root   64 Jan  5 12:46 .bash_history\ndrwxr-xr-x.  3 root root   18 Nov 16 22:56 .config\n-rw-------.  1 root root 1900 Nov 16 22:54 anaconda-ks.cfg\ndr-xr-xr-x. 17 root root  224 Nov 16 22:54 ..\n-rw-r--r--.  1 root root   18 Dec 29  2013 .bash_logout\n-rw-r--r--.  1 root root  176 Dec 29  2013 .bash_profile\n-rw-r--r--.  1 root root  176 Dec 29  2013 .bashrc\n-rw-r--r--.  1 root root  100 Dec 29  2013 .cshrc\n-rw-r--r--.  1 root root  129 Dec 29  2013 .tcshrc\n",
	    "Status": "successfully"
	}

请求分析：
	{
		"host": "192.168.1.181",
		"method": "run_shell",
		"parameters": {
			"args": "-alt",
			"cmd": "ls"
		},
		"plugin": "linux_system"
	}

上面json中的 "plugin":"linux_system" 是插件的名字。 一个slave有多少插件可以在nova/cmd/nova.ini 中配置：

compute_plugin=nova.compute.manager_linux_system.ComputeManager_linux_system,nova.compute.manager_build_server.ComputeManager_build_server

host 和 method 也都是框架处理的必要元素。

parameters 的参数的异常处理是plugin处理的。框架负责传递参数。


下面是一个插件定义的类：

class ComputeManager_linux_system(base.Base):

    target = messaging.Target(namespace='linux_system', version='4.0')
    
    #import pdb;pdb.set_trace()
    def __init__(self):
        super(ComputeManager_linux_system, self).__init__()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        self.compute_task_api = conductor.ComputeTaskAPI()
        

    def reset(self):
        LOG.info(_LI('Reloading compute RPC API'))
        compute_rpcapi.LAST_VERSION = None
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()

    @compute_utils.mark_describe_task(namespace='linux_system',
                                      describe="parameters is dict. \
address is target address \
count is count of ping . \
interval is time of two packet")
    def ping(self, context, parameters):

        address=parameters.get('address',4)
        count= "-c "+str(parameters.get('count',4))
        interval="-i "+str( parameters.get('interval',1))
        Caseid= parameters.get('id',None)
        ca_dir="/root"
        out, err =utils.execute('ping', address,count ,interval, cwd=ca_dir,run_as_root=True)
        self.report_result(context, Caseid=Caseid, out=out, status=err)
    
    @compute_utils.mark_describe_task(namespace='linux_system',
                                      describe="parameters is dict. \
cmd is command line. \
args is parameter")
    def run_shell(self, context, parameters):
        cmd= parameters.get('cmd',None)
        arg= parameters.get('args',None)
        Caseid= parameters.get('id',None)
        ca_dir="/root"
        out, err =utils.execute(cmd, arg , cwd=ca_dir,run_as_root=True)
        
        self.report_result(context, Caseid=Caseid, out=out, status=err)

    def report_result(self,context,Caseid=None,out=None,status=None):
        import pdb;pdb.set_trace()
        if Caseid is None or out is None or status is None:pass
        else:
            status = "fail"
            output = "not stdout "
            if status != 1:status ="successfully"
            if out :output = out
            self.compute_task_api.report_cases_result(context, Caseid=Caseid,output=output,status=status)
