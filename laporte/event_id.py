# -*- coding: utf-8 -*-
'''
Store event/request ID in flask's G object
for better tracing in the log.
'''
import uuid
import logging

from flask import g
from flask import _app_ctx_stack as stack

# create logger
logging.getLogger(__name__).addHandler(logging.NullHandler())

_G_ATTR_EVENT_ID = 'event_id'
_G_ATTR_HTTP_REQUEST_ID = 'request_id'


class EventID():
    def __init__(self):
        self.event_cnt = 0

    def set(self, add_prefix="", add_suffix="", eid=None):
        '''
        Save event ID (of node update) into flask's G object.
        '''

        if eid is None:
            self.event_cnt += 1
            eid = '{:06x}'.format(self.event_cnt)

        setattr(g, _G_ATTR_EVENT_ID, add_prefix + eid + add_suffix)

    @staticmethod
    def get():
        '''
        Get event ID (of node update) from flask's G object.
        '''

        if stack.top is not None:
            return g.get(_G_ATTR_EVENT_ID, None)

        return None


class RequestID():
    @staticmethod
    def set(request_id=None):
        '''
        Save http request ID into flask's G object.
        '''

        if request_id is None:
            request_id = str(uuid.uuid4())

        setattr(g, _G_ATTR_HTTP_REQUEST_ID, request_id)

    @staticmethod
    def get():
        '''
        Get http request ID from flask's G object.
        '''

        if stack.top is not None:
            return g.get(_G_ATTR_HTTP_REQUEST_ID, None)

        return None


event_id = EventID()
request_id = RequestID()