# -*- coding: UTF-8 -*-
from smtplib import SMTP
from email.header import Header
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import json

from nova import config
CONF = config.CONF

def send_mail(receiver='',summary='',attach=''):
    def format_json_to_html(message):
        mes = json.loads(message)
        seq = [int(key) for key in mes.keys()]
        seq.sort(key=lambda x: abs(x))
        html = '<table border="1" cellspacing="0" width="50%" height="150">'
        html += "<tr><th>TC ID</t> <th>Steps Status</th><th>Result</th> </tr>"
        for value in seq:
            resultflag = "PASS"
            rowspan=str(len(mes[str(value)]))
            count=0
            if rowspan >1 :html += "<tr><td rowspan=\"" + rowspan + "\">" + str(value) + '</td>'
            else:html += "<tr><td>" + str(value) + '</td>'
            for key, value1 in mes[str(value)].items():
                if value1 != "PASS": resultflag = "FAIL"
            for key, value in mes[str(value)].items():
                if count==0:
                    html += "<td>" + str(key) + " : " + str(value) + "</td>"
                    if rowspan >1 :
                        html += "<td rowspan=\"" + rowspan + "\">" + resultflag + '</td></tr>'
                    else:html += "<td>" + resultflag + '</td></tr>'
                else:
                    html += "<td>" + str(key) + " : " + str(value) + "</td>"
                count+=1
        html += "</table>"
        return html

    import pdb;pdb.set_trace()
    if receiver =='' or CONF.sender == '':
        return False
    if CONF.sender == '' or CONF.mail_password =='' or CONF.mail_server =='':
        return False
    receivers = [x for x in str(receiver).split(',')]
    sender = CONF.sender
    passwd= CONF.mail_password
    mail_server=CONF.mail_server

    message = MIMEMultipart()
    html = format_json_to_html(summary)
    text_content = MIMEText(html, 'html', 'utf-8')
    message['Subject'] = Header('Report', 'utf-8')

    message.attach(text_content)

    txt = MIMEText(attach, 'base64', 'utf-8')
    txt['Content-Type'] = 'text/plain'
    txt['Content-Disposition'] = 'attachment; filename=log.txt'
    message.attach(txt)

    smtper = SMTP(mail_server)
    #smtper.set_debuglevel(1)
    # smtper.starttls()
    smtper.login(sender, passwd)
    smtper.sendmail(sender, receivers, message.as_string())
    smtper.quit()
    return True


if __name__ == "__main__":
    res= u'{"1": {"Parallel-Step-1": "FAIL"}, "3": {"Serial-Step-1": "FAIL"}, "2": {"Serial-Step-1": "PASS", "Serial-Step-2": "PASS"}, "4": {"Serial-Step-1": "FAIL"}}'

    log= u'total 76\n-rw-------.  1 root root 12387 Jul 30 04:35 .bash_history\ndrwxr-xr-x. 21 root root  4096 Jul 30 02:35 polar-bear\ndr-xr-x---. 10 root root  4096 Jul 30 02:16 .\ndrwx------.  3 root root    17 Jul 30 02:16 .cache\ndrwxr-xr-x.  2 root root   184 Jul 29 05:28 mysql\ndrwxr-xr-x. 13 root root  4096 Jul 26 06:39 rook\n-rw-r--r--.  1 root root   479 Jul 26 04:34 nginx-deployment.yaml\ndrwxr-xr-x.  4 root root    51 Jul 26 02:54 .kube\n-rwxr-xr-x.  1 root root   213 Jul 26 02:47 modify_docker.sh\ndrwxr-----.  3 root root    19 Jul 26 02:46 .pki\n-rwxr--r--.  1 root root  3046 Jul 26 02:44 env_set.sh\ndrwx------.  3 root root    17 Jul 26 02:44 .ansible\ndrwx------.  2 root root    29 Feb  7  2018 .ssh\n-rw-------.  1 root root  6921 Oct 30  2017 anaconda-ks.cfg\n-rw-------.  1 root root  6577 Oct 30  2017 original-ks.cfg\ndr-xr-xr-x. 17 root root   224 Oct 30  2017 ..\n-rw-r--r--.  1 root root    18 Dec 29  2013 .bash_logout\n-rw-r--r--.  1 root root   176 Dec 29  2013 .bash_profile\n-rw-r--r--.  1 root root   176 Dec 29  2013 .bashrc\n-rw-r--r--.  1 root root   100 Dec 29  2013 .cshrc\n-rw-r--r--.  1 root root   129 Dec 29  2013 .tcshrc\nPING 135.251.149.81 (135.251.149.81) 56(84) bytes of data.\n64 bytes from 135.251.149.81: icmp_seq=1 ttl=64 time=2.81 ms\n64 bytes from 135.251.149.81: icmp_seq=2 ttl=64 time=0.270 ms\n64 bytes from 135.251.149.81: icmp_seq=3 ttl=64 time=1.78 ms\n64 bytes from 135.251.149.81: icmp_seq=4 ttl=64 time=0.242 ms\n64 bytes from 135.251.149.81: icmp_seq=5 ttl=64 time=4.66 ms\n64 bytes from 135.251.149.81: icmp_seq=6 ttl=64 time=0.231 ms\n64 bytes from 135.251.149.81: icmp_seq=7 ttl=64 time=0.170 ms\n\n--- 135.251.149.81 ping statistics ---\n7 packets transmitted, 7 received, 0% packet loss, time 6006ms\nrtt min/avg/max/mdev = 0.170/1.453/4.660/1.614 ms\n'

    send_mail(receiver='qinkai19870515@126.com',summary=res,attach=str(log))

