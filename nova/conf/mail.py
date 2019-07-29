
import socket

from oslo_config import cfg

from nova.conf import paths

mail_opts = [


    # TODO(aunnam): This option needs to be deprecated
    cfg.StrOpt('sender',
               default='',
               help="",
	       deprecated_for_removal=True
),



    cfg.StrOpt('mail_server',
               default='',
               help=""),
    # TODO(aunnam): This option needs to be deprecated
    cfg.StrOpt('mail_password',
               default='',
               help=""),
   ]





netconf_opts = [
    cfg.StrOpt("sender",
               default="111",
               help="""
The IP address which the host is using to connect to the management network.

""")

]

def register_opts(conf):
    #conf.register_opts(mail_opts)
    conf.register_opts(netconf_opts)


def list_opts():
    return {'DEFAULT': mail_opts}
