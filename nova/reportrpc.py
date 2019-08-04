#
# Copyright 2013 Red Hat, Inc.
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
#

"""
Base RPC client and server common to all services.
"""

import oslo_messaging as messaging
from oslo_serialization import jsonutils

from nova import config
from nova import rpc
from nova import objects
import json

CONF = config.CONF

_NAMESPACE = 'reportapi'


class ReportAPI(object):
    """Client side of the base rpc API.

    API version history:

        1.0 - Initial version.
        1.1 - Add get_backdoor_port
    """

    VERSION_ALIASES = {
        # baseapi was added in havana
    }

    def __init__(self, topic):
        super(ReportAPI, self).__init__()
        target = messaging.Target(topic=topic,
                                  namespace=_NAMESPACE,
                                  version='1.0')
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.baseapi,
                                               CONF.upgrade_levels.baseapi)
        self.client = rpc.get_client(target, version_cap=version_cap)

    def result(self, context, arg, timeout=None):
        arg_p = jsonutils.to_primitive(arg)
        cctxt = self.client.prepare(timeout=timeout)
        return cctxt.call(context, 'result', arg=arg_p)



class ReportRPCAPI(object):
    """Server side of the base RPC API."""

    target = messaging.Target(namespace=_NAMESPACE, version='1.1')

    def __init__(self,finish_flag,PlanId=None,CaseId=None,description=None):
        self.finish_flag = finish_flag
        self.Plan_Id=PlanId
        self.CaseId= CaseId
        self.description=description
    def result(self, context, arg):
        self.finish_flag= self.finish_flag-1
        status = arg.get("status",None)

        out = arg.get("out",None)


        if status:
            self.report_result(context,status=status,out=out)

        
    def report_result(self,context,status,out):
        
        def summary(template):
            total ,failure, sucessfully = 0,0,0
            for key ,value in template.items():

                try:
                    if isinstance(int(key),(int,)):
                        total+=1
                        summary_result = True
                        if isinstance(value,(dict,)):
                            for k,v in value.items():
                                if v == "FAIL":summary_result = False
                        if summary_result == False: failure +=1
                        else:sucessfully+=1
                except Exception :
                    print (Exception)


            return total ,failure, sucessfully


        plan=objects.TestPlan.get_by_id(context,self.Plan_Id)
        
        res=json.loads(plan['result'])
        res[self.CaseId][self.description]=status
        
        plan['message']=plan['message']+out
        
        summary_result=json.loads(plan['summary'])

        summary_result['total'],summary_result['failure'],summary_result['sucessfully']=summary(res)
        summary_result['passratio']=int((float(summary_result['sucessfully'])/float(summary_result['total']))*100)
        plan['summary']=json.dumps(summary_result)
        
        plan['result']=json.dumps(res)

        plan.save()


