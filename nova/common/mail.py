# -*- coding: UTF-8 -*-
from smtplib import SMTP
from email.header import Header
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

from nova import config
CONF = config.CONF

def send_mail(receiver='',summary='',attach=''):

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

    text_content = MIMEText(str(summary), 'plain', 'utf-8')
    message['Subject'] = Header('report', 'utf-8')

    message.attach(text_content)

    #txt = MIMEText('166161616', 'base64', 'utf-8')
    #txt['Content-Type'] = 'text/plain'
    #txt['Content-Disposition'] = 'attachment; filename=log.txt'
    #message.attach(txt)

    smtper = SMTP(mail_server)
    smtper.set_debuglevel(1)

    # smtper.starttls()

    smtper.login(sender, passwd)

    smtper.sendmail(sender, receivers, message.as_string())
    smtper.quit()
    return True

