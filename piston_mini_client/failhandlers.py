# -*- coding: utf-8 -*-
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Lesser General Public License version 3 (see the file LICENSE).

"""A fail handler is passed the raw httplib2 response and body, and has a
chance to raise an exception, modify the body or return it unaltered, or
even return a completely different object.  It's up to the client (and
possibly decorators) to know what to do with these returned objects.
"""

__all__ = [
    'APIError',
    'BaseFailHandler',
    'ExceptionFailHandler',
    'DictFailHandler',
    'NoneFailHandler',
    'MultiExceptionFailHandler',
]

import os

class APIError(Exception):
    def __init__(self, msg, body=None):
        self.msg = msg
        self.body = body
        self.debug = os.environ.get('PISTON_MINI_CLIENT_DEBUG', False)
    def __str__(self):
        if self.debug:
            return "%s\nReceived body:\n%s" % (self.msg, self.body)
        return self.msg


class BaseFailHandler(object):
    """A base class for fail handlers.

    Child classes should at least define handle()
    """
    success_status_codes = ['200', '201', '204', '304']
    
    def __init__(self, url, method, body, headers):
        """Don't store any of the provided information as we don't need it"""
        pass

    def handle(self, response, body):
        raise NotImplementedError()

    def was_error(self, response):
        """Returns True if 'response' is a failure"""
        return response.get('status') not in self.success_status_codes

class ExceptionFailHandler(BaseFailHandler):
    """A fail handler that will raise APIErrors if anything goes wrong"""

    def handle(self, response, body):
        """Raise APIError if a strange status code is found"""
        if 'status' not in response:
            raise APIError('No status code in response')
        if self.was_error(response):
            raise APIError('%s: %s' % (response['status'], response), body)
        return body


class NoneFailHandler(BaseFailHandler):
    """A fail handler that returns None if anything goes wrong.

    You probably only want to use this if you really don't care about what
    went wrong.
    """
    def handle(self, response, body):
        """Return None if a strange status code is found"""
        if self.was_error(response):
            return None
        return body


class DictFailHandler(BaseFailHandler):
    """A fail handler that returns error information in a dict"""

    def handle(self, response, body):
        """Return a dict if a strange status code is found.

        The returned dict will have two keys:
         * 'response': the httplib2 response header dict
         * 'body': the response body, as a string
        """
        if self.was_error(response):
            return {'response': response, 'body': body}
        return body


class BadRequestError(APIError):
    """A 400 Bad Request response was received"""


class UnauthorizedError(APIError):
    """A 401 Bad Request response was received"""


class NotFoundError(APIError):
    """A 404 Not Found response was received"""


class InternalServerErrorError(APIError):
    """A 500 Internal Server Error response was received"""


class MultiExceptionFailHandler(BaseFailHandler):
    """A fail handler that raises an exception according to what goes wrong"""
    exceptions = {
        '400': BadRequestError,
        '401': UnauthorizedError,
        '404': NotFoundError,
        '500': InternalServerErrorError,
    }

    def handle(self, response, body):
        """Return an exception according to what went wrong.

        Status codes currently returning their own exception class are:
         * 400: BadRequestError,
         * 401: UnauthorizedError,
         * 404: NotFoundError, and
         * 500: InternalServerErrorError
        """
        if self.was_error(response):
            status = response.get('status')
            exception_class = self.exceptions.get(status, APIError)
            raise exception_class('%s: %s' % (status, response), body)
        return body

