
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

__all__ = ['AMQPDriverBase']

import logging
import threading
import time
import uuid

import cachetools
from oslo_utils import timeutils
from six import moves

import oslo_messaging
from oslo_messaging._drivers import amqp as rpc_amqp
from oslo_messaging._drivers import base
from oslo_messaging._drivers import common as rpc_common
from oslo_messaging._i18n import _
from oslo_messaging._i18n import _LE
from oslo_messaging._i18n import _LI
from oslo_messaging._i18n import _LW

LOG = logging.getLogger(__name__)

# Minimum/Maximum sleep between a poll and ack/requeue
# Maximum should be small enough to not get rejected ack,
# minimum should be big enough to not burn the CPU.
ACK_REQUEUE_EVERY_SECONDS_MIN = 0.001
ACK_REQUEUE_EVERY_SECONDS_MAX = 1.0


class MessageOperationsHandler(object):
    """Queue used by message operations to ensure that all tasks are
    serialized and run in the same thread, since underlying drivers like kombu
    are not thread safe.
    """
    def __init__(self, name):
        self.name = "%s (%s)" % (name, hex(id(self)))
        self._tasks = moves.queue.Queue()

        self._shutdown = threading.Event()
        self._shutdown_thread = threading.Thread(
            target=self._process_in_background)
        self._shutdown_thread.daemon = True

        # HACK(sileht): this is set by the server.Server temporary
        # to not have to rewrite the entire internal API to pass
        # executor everywhere to make Listener aware of the server
        # executor. All this hack is only for the blocking executor.
        # And it's deprecated so...
        self._executor = None

    def stop(self):
        self._shutdown.set()

    def process_in_background(self):
        """Run all pending tasks queued by do() in an thread during the
        shutdown process.
        """
        self._shutdown_thread.start()

    def _process_in_background(self):
        while not self._shutdown.is_set():
            self.process()
            time.sleep(ACK_REQUEUE_EVERY_SECONDS_MIN)

    def process(self):
        "Run all pending tasks queued by do()."

        while True:
            try:
                task, event = self._tasks.get(block=False)
            except moves.queue.Empty:
                break
            try:
                task()
            finally:
                event.set()

    def do(self, task):
        "Put the task in the queue and waits until the task is completed."
        if self._executor is None:
            raise RuntimeError("Unexpected error, no executor is setuped")
        elif self._executor == "blocking":
            # NOTE(sileht): Blocking will hang forever if we waiting the
            # polling thread
            task()
        else:
            event = threading.Event()
            self._tasks.put((task, event))
            event.wait()


class AMQPIncomingMessage(base.RpcIncomingMessage):

    def __init__(self, listener, ctxt, message, unique_id, msg_id, reply_q,
                 obsolete_reply_queues, message_operations_handler):
        super(AMQPIncomingMessage, self).__init__(ctxt, message)
        self.listener = listener

        self.unique_id = unique_id
        self.msg_id = msg_id
        self.reply_q = reply_q
        self._obsolete_reply_queues = obsolete_reply_queues
        self._message_operations_handler = message_operations_handler
        self.stopwatch = timeutils.StopWatch()
        self.stopwatch.start()

    def _send_reply(self, conn, reply=None, failure=None):
        if not self._obsolete_reply_queues.reply_q_valid(self.reply_q,
                                                         self.msg_id):
            return

        if failure:
            failure = rpc_common.serialize_remote_exception(failure)
        # NOTE(sileht): ending can be removed in N*, see Listener.wait()
        # for more detail.
        msg = {'result': reply, 'failure': failure, 'ending': True,
               '_msg_id': self.msg_id}
        rpc_amqp._add_unique_id(msg)
        unique_id = msg[rpc_amqp.UNIQUE_ID]

        LOG.debug("sending reply msg_id: %(msg_id)s "
                  "reply queue: %(reply_q)s "
                  "time elapsed: %(elapsed)ss", {
                      'msg_id': self.msg_id,
                      'unique_id': unique_id,
                      'reply_q': self.reply_q,
                      'elapsed': self.stopwatch.elapsed()})
        conn.direct_send(self.reply_q, rpc_common.serialize_msg(msg))

    def reply(self, reply=None, failure=None):
        if not self.msg_id:
            # NOTE(Alexei_987) not sending reply, if msg_id is empty
            #    because reply should not be expected by caller side
            return

        # NOTE(sileht): return without hold the a connection if possible
        if not self._obsolete_reply_queues.reply_q_valid(self.reply_q,
                                                         self.msg_id):
            return

        # NOTE(sileht): we read the configuration value from the driver
        # to be able to backport this change in previous version that
        # still have the qpid driver
        duration = self.listener.driver.missing_destination_retry_timeout
        timer = rpc_common.DecayingTimer(duration=duration)
        timer.start()

        while True:
            try:
                with self.listener.driver._get_connection(
                        rpc_common.PURPOSE_SEND) as conn:
                    self._send_reply(conn, reply, failure)
                return
            except rpc_amqp.AMQPDestinationNotFound:
                if timer.check_return() > 0:
                    LOG.debug(("The reply %(msg_id)s cannot be sent  "
                               "%(reply_q)s reply queue don't exist, "
                               "retrying..."), {
                                   'msg_id': self.msg_id,
                                   'reply_q': self.reply_q})
                    time.sleep(0.25)
                else:
                    self._obsolete_reply_queues.add(self.reply_q, self.msg_id)
                    LOG.info(_LI("The reply %(msg_id)s cannot be sent  "
                                 "%(reply_q)s reply queue don't exist after "
                                 "%(duration)s sec abandoning..."), {
                                     'msg_id': self.msg_id,
                                     'reply_q': self.reply_q,
                                     'duration': duration})
                    return

    def acknowledge(self):
        self._message_operations_handler.do(self.message.acknowledge)
        self.listener.msg_id_cache.add(self.unique_id)

    def requeue(self):
        # NOTE(sileht): In case of the connection is lost between receiving the
        # message and requeing it, this requeue call fail
        # but because the message is not acknowledged and not added to the
        # msg_id_cache, the message will be reconsumed, the only difference is
        # the message stay at the beginning of the queue instead of moving to
        # the end.
        self._message_operations_handler.do(self.message.requeue)


class ObsoleteReplyQueuesCache(object):
    """Cache of reply queue id that doesn't exists anymore.

    NOTE(sileht): In case of a broker restart/failover
    a reply queue can be unreachable for short period
    the IncomingMessage.send_reply will block for 60 seconds
    in this case or until rabbit recovers.

    But in case of the reply queue is unreachable because the
    rpc client is really gone, we can have a ton of reply to send
    waiting 60 seconds.
    This leads to a starvation of connection of the pool
    The rpc server take to much time to send reply, other rpc client will
    raise TimeoutError because their don't receive their replies in time.

    This object cache stores already known gone client to not wait 60 seconds
    and hold a connection of the pool.
    Keeping 200 last gone rpc client for 1 minute is enough
    and doesn't hold to much memory.
    """

    SIZE = 200
    TTL = 60

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = cachetools.TTLCache(self.SIZE, self.TTL)

    def reply_q_valid(self, reply_q, msg_id):
        if reply_q in self._cache:
            self._no_reply_log(reply_q, msg_id)
            return False
        return True

    def add(self, reply_q, msg_id):
        with self._lock:
            self._cache.update({reply_q: msg_id})
        self._no_reply_log(reply_q, msg_id)

    def _no_reply_log(self, reply_q, msg_id):
        LOG.warning(_LW("%(reply_queue)s doesn't exists, drop reply to "
                        "%(msg_id)s"), {'reply_queue': reply_q,
                                        'msg_id': msg_id})


class AMQPListener(base.PollStyleListener):

    def __init__(self, driver, conn):
        super(AMQPListener, self).__init__(driver.prefetch_size)
        self.driver = driver
        self.conn = conn
        self.msg_id_cache = rpc_amqp._MsgIdCache()
        self.incoming = []
        self._shutdown = threading.Event()
        self._shutoff = threading.Event()
        self._obsolete_reply_queues = ObsoleteReplyQueuesCache()
        self._message_operations_handler = MessageOperationsHandler(
            "AMQPListener")
        self._current_timeout = ACK_REQUEUE_EVERY_SECONDS_MIN

    def __call__(self, message):
        ctxt = rpc_amqp.unpack_context(message)
        unique_id = self.msg_id_cache.check_duplicate_message(message)
	#import pdb;pdb.set_trace()
        if ctxt.msg_id:
            LOG.debug("received message msg_id: %(msg_id)s reply to "
                      "%(queue)s", {'queue': ctxt.reply_q,
                                    'msg_id': ctxt.msg_id})
        else:
            LOG.debug("received message with unique_id: %s", unique_id)
	print message
        self.incoming.append(AMQPIncomingMessage(
            self,
            ctxt.to_dict(),
            message,
            unique_id,
            ctxt.msg_id,
            ctxt.reply_q,
            self._obsolete_reply_queues,
            self._message_operations_handler))

    @base.batch_poll_helper
    def poll(self, timeout=None):
        stopwatch = timeutils.StopWatch(duration=timeout).start()

        while not self._shutdown.is_set():
            self._message_operations_handler.process()

            if self.incoming:
                return self.incoming.pop(0)

            left = stopwatch.leftover(return_none=True)
            if left is None:
                left = self._current_timeout
            if left <= 0:
                return None

            try:
                self.conn.consume(timeout=min(self._current_timeout, left))
            except rpc_common.Timeout:
                self._current_timeout = max(self._current_timeout * 2,
                                            ACK_REQUEUE_EVERY_SECONDS_MAX)
            else:
                self._current_timeout = ACK_REQUEUE_EVERY_SECONDS_MIN

        # NOTE(sileht): listener is stopped, just processes remaining messages
        # and operations
        self._message_operations_handler.process()
        if self.incoming:
            return self.incoming.pop(0)

        self._shutoff.set()

    def stop(self):
        self._shutdown.set()
        self.conn.stop_consuming()
        self._shutoff.wait()

        # NOTE(sileht): Here, the listener is stopped, but some incoming
        # messages may still live on server side, because callback is still
        # running and message is not yet ack/requeue. It's safe to do the ack
        # into another thread, side the polling thread is now terminated.
        self._message_operations_handler.process_in_background()

    def cleanup(self):
        # NOTE(sileht): server executor is now stopped, we are sure that no
        # more incoming messages in live, we can acknowledge
        # remaining messages and stop the thread
        self._message_operations_handler.stop()
        # Closes listener connection
        self.conn.close()


class ReplyWaiters(object):

    WAKE_UP = object()

    def __init__(self):
        self._queues = {}
        self._wrn_threshold = 10

    def get(self, msg_id, timeout):
        try:
            return self._queues[msg_id].get(block=True, timeout=timeout)
        except moves.queue.Empty:
            raise oslo_messaging.MessagingTimeout(
                'Timed out waiting for a reply '
                'to message ID %s' % msg_id)

    def put(self, msg_id, message_data):
        queue = self._queues.get(msg_id)
        if not queue:
            LOG.info(_LI('No calling threads waiting for msg_id : %s'), msg_id)
            LOG.debug(' queues: %(queues)s, message: %(message)s',
                      {'queues': len(self._queues), 'message': message_data})
        else:
            queue.put(message_data)

    def add(self, msg_id):
        self._queues[msg_id] = moves.queue.Queue()
        if len(self._queues) > self._wrn_threshold:
            LOG.warning(_LW('Number of call queues is greater than warning '
                            'threshold: %(old_threshold)s. There could be a '
                            'leak. Increasing threshold to: %(threshold)s'),
                        {'old_threshold': self._wrn_threshold,
                         'threshold': self._wrn_threshold * 2})
            self._wrn_threshold *= 2

    def remove(self, msg_id):
        del self._queues[msg_id]


class ReplyWaiter(object):
    def __init__(self, reply_q, conn, allowed_remote_exmods):
        self.conn = conn
        self.allowed_remote_exmods = allowed_remote_exmods
        self.msg_id_cache = rpc_amqp._MsgIdCache()
        self.waiters = ReplyWaiters()

        self.conn.declare_direct_consumer(reply_q, self)

        self._thread_exit_event = threading.Event()
        self._thread = threading.Thread(target=self.poll)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        if self._thread:
            self._thread_exit_event.set()
            self.conn.stop_consuming()
            self._thread.join()
            self._thread = None

    def poll(self):
        current_timeout = ACK_REQUEUE_EVERY_SECONDS_MIN
        while not self._thread_exit_event.is_set():
            try:
                # ack every ACK_REQUEUE_EVERY_SECONDS_MAX seconds
                self.conn.consume(timeout=current_timeout)
            except rpc_common.Timeout:
                current_timeout = max(current_timeout * 2,
                                      ACK_REQUEUE_EVERY_SECONDS_MAX)
            except Exception:
                LOG.exception(_LE("Failed to process incoming message, "
                              "retrying..."))
            else:
                current_timeout = ACK_REQUEUE_EVERY_SECONDS_MIN

    def __call__(self, message):
        # NOTE(sileht): __call__ is running within the polling thread,
        # (conn.consume -> conn.conn.drain_events() -> __call__ callback)
        # it's threadsafe to acknowledge the message here, no need to wait
        # the next polling
        message.acknowledge()
        incoming_msg_id = message.pop('_msg_id', None)
        if message.get('ending'):
            LOG.debug("received reply msg_id: %s", incoming_msg_id)
        self.waiters.put(incoming_msg_id, message)

    def listen(self, msg_id):
        self.waiters.add(msg_id)

    def unlisten(self, msg_id):
        self.waiters.remove(msg_id)

    @staticmethod
    def _raise_timeout_exception(msg_id):
        raise oslo_messaging.MessagingTimeout(
            _('Timed out waiting for a reply to message ID %s.') % msg_id)

    def _process_reply(self, data):
        self.msg_id_cache.check_duplicate_message(data)
        if data['failure']:
            failure = data['failure']
            result = rpc_common.deserialize_remote_exception(
                failure, self.allowed_remote_exmods)
        else:
            result = data.get('result', None)

        ending = data.get('ending', False)
        return result, ending

    def wait(self, msg_id, timeout):
        # NOTE(sileht): for each msg_id we receive two amqp message
        # first one with the payload, a second one to ensure the other
        # have finish to send the payload
        # NOTE(viktors): We are going to remove this behavior in the N
        # release, but we need to keep backward compatibility, so we should
        # support both cases for now.
        timer = rpc_common.DecayingTimer(duration=timeout)
        timer.start()
        final_reply = None
        ending = False
        while not ending:
            timeout = timer.check_return(self._raise_timeout_exception, msg_id)
            try:
                message = self.waiters.get(msg_id, timeout=timeout)
            except moves.queue.Empty:
                self._raise_timeout_exception(msg_id)

            reply, ending = self._process_reply(message)
            if reply is not None:
                # NOTE(viktors): This can be either first _send_reply() with an
                # empty `result` field or a second _send_reply() with
                # ending=True and no `result` field.
                final_reply = reply
        return final_reply


class AMQPDriverBase(base.BaseDriver):
    missing_destination_retry_timeout = 0

    def __init__(self, conf, url, connection_pool,
                 default_exchange=None, allowed_remote_exmods=None):
        super(AMQPDriverBase, self).__init__(conf, url, default_exchange,
                                             allowed_remote_exmods)

        self._default_exchange = default_exchange

        self._connection_pool = connection_pool

        self._reply_q_lock = threading.Lock()
        self._reply_q = None
        self._reply_q_conn = None
        self._waiter = None

    def _get_exchange(self, target):
        return target.exchange or self._default_exchange

    def _get_connection(self, purpose=rpc_common.PURPOSE_SEND):
        return rpc_common.ConnectionContext(self._connection_pool,
                                            purpose=purpose)

    def _get_reply_q(self):
        with self._reply_q_lock:
            if self._reply_q is not None:
                return self._reply_q

            reply_q = 'reply_' + uuid.uuid4().hex

            conn = self._get_connection(rpc_common.PURPOSE_LISTEN)

            self._waiter = ReplyWaiter(reply_q, conn,
                                       self._allowed_remote_exmods)

            self._reply_q = reply_q
            self._reply_q_conn = conn

        return self._reply_q

    def _send(self, target, ctxt, message,
              wait_for_reply=None, timeout=None,
              envelope=True, notify=False, retry=None):

        # FIXME(markmc): remove this temporary hack
        class Context(object):
            def __init__(self, d):
                self.d = d

            def to_dict(self):
                return self.d

        context = Context(ctxt)
        msg = message

        if wait_for_reply:
            msg_id = uuid.uuid4().hex
            msg.update({'_msg_id': msg_id})
            msg.update({'_reply_q': self._get_reply_q()})

        rpc_amqp._add_unique_id(msg)
        unique_id = msg[rpc_amqp.UNIQUE_ID]

        rpc_amqp.pack_context(msg, context)

        if envelope:
            msg = rpc_common.serialize_msg(msg)

        if wait_for_reply:
            self._waiter.listen(msg_id)
            log_msg = "CALL msg_id: %s " % msg_id
        else:
            log_msg = "CAST unique_id: %s " % unique_id

        try:
            with self._get_connection(rpc_common.PURPOSE_SEND) as conn:
                if notify:
                    exchange = self._get_exchange(target)
                    log_msg += "NOTIFY exchange '%(exchange)s'" \
                               " topic '%(topic)s'" % {
                                   'exchange': exchange,
                                   'topic': target.topic}
                    LOG.debug(log_msg)
                    conn.notify_send(exchange, target.topic, msg, retry=retry)
                elif target.fanout:
                    log_msg += "FANOUT topic '%(topic)s'" % {
                        'topic': target.topic}
                    LOG.debug(log_msg)
                    conn.fanout_send(target.topic, msg, retry=retry)
                else:
                    topic = target.topic
                    exchange = self._get_exchange(target)
                    if target.server:
                        topic = '%s.%s' % (target.topic, target.server)
                    log_msg += "exchange '%(exchange)s'" \
                               " topic '%(topic)s'" % {
                                   'exchange': exchange,
                                   'topic': topic}
                    LOG.debug(log_msg)
                    conn.topic_send(exchange_name=exchange, topic=topic,
                                    msg=msg, timeout=timeout, retry=retry)

            if wait_for_reply:
                result = self._waiter.wait(msg_id, timeout)
                if isinstance(result, Exception):
                    raise result
                return result
        finally:
            if wait_for_reply:
                self._waiter.unlisten(msg_id)

    def send(self, target, ctxt, message, wait_for_reply=None, timeout=None,
             retry=None):
        return self._send(target, ctxt, message, wait_for_reply, timeout,
                          retry=retry)

    def send_notification(self, target, ctxt, message, version, retry=None):
        return self._send(target, ctxt, message,
                          envelope=(version == 2.0), notify=True, retry=retry)

    def listen(self, target, batch_size, batch_timeout):
        conn = self._get_connection(rpc_common.PURPOSE_LISTEN)

        listener = AMQPListener(self, conn)

        conn.declare_topic_consumer(exchange_name=self._get_exchange(target),
                                    topic=target.topic,
                                    callback=listener)
        conn.declare_topic_consumer(exchange_name=self._get_exchange(target),
                                    topic='%s.%s' % (target.topic,
                                                     target.server),
                                    callback=listener)
        conn.declare_fanout_consumer(target.topic, listener)

        return base.PollStyleListenerAdapter(listener, batch_size,
                                             batch_timeout)

    def listen_for_notifications(self, targets_and_priorities, pool,
                                 batch_size, batch_timeout):
        conn = self._get_connection(rpc_common.PURPOSE_LISTEN)

        listener = AMQPListener(self, conn)
        for target, priority in targets_and_priorities:
            conn.declare_topic_consumer(
                exchange_name=self._get_exchange(target),
                topic='%s.%s' % (target.topic, priority),
                callback=listener, queue_name=pool)
        return base.PollStyleListenerAdapter(listener, batch_size,
                                             batch_timeout)

    def cleanup(self):
        if self._connection_pool:
            self._connection_pool.empty()
        self._connection_pool = None

        with self._reply_q_lock:
            if self._reply_q is not None:
                self._waiter.stop()
                self._reply_q_conn.close()
                self._reply_q_conn = None
                self._reply_q = None
                self._waiter = None
