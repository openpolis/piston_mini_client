# -*- coding: utf-8 -*-
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Lesser General Public License version 3 (see the file LICENSE).

import httplib2
import simplejson
import urllib
from functools import wraps
from urlparse import urlparse, urlunparse

from failhandlers import ExceptionFailHandler, APIError

class OfflineModeException(Exception):
    pass

def returns_json(func):
    """The response data will be deserialized using a simple JSON decoder"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        body = func(*args, **kwargs)
        if not isinstance(body, basestring):
            return body
        return simplejson.loads(body)
    return wrapper


def returns(cls, none_allowed=False):
    """The response data will be deserialized into an instance of ``cls``.

    The provided class should be a descendant of ``PistonResponseObject``,
    or some other class that provides a ``from_response`` method.

    ``none_allowed``, defaulting to ``False``, specifies whether or not
    ``None`` is a valid response. If ``True`` then the api can return ``None``
    instead of a ``PistonResponseObject``.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            body = func(self, *args, **kwargs)
            if not isinstance(body, basestring):
                return body
            return cls.from_response(body, none_allowed)
        return wrapper
    return decorator

def returns_list_of(cls):
    """The response data will be deserialized into a list of ``cls``.

    The provided class should be a descendant of ``PistonResponseObject``,
    or some other class that provides a ``from_response`` method.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            body = func(self, *args, **kwargs)
            if not isinstance(body, basestring):
                return body
            data = simplejson.loads(body)
            items = []
            for datum in data:
                items.append(cls.from_dict(datum))
            return items
        return wrapper
    return decorator


class PistonResponseObject(object):
    """Base class for objects that are returned from api calls."""
    @classmethod
    def from_response(cls, body, none_allowed=False):
        data = simplejson.loads(body)
        if none_allowed and data is None:
            return data
        obj = cls.from_dict(data)
        return obj

    @classmethod
    def from_dict(cls, data):
        obj = cls()
        for key, value in data.items():
            setattr(obj, key, value)
        return obj

class PistonSerializable(object):
    """Base class for objects that want to be used as api call arguments.

    Children classes should at least redefine ``_atts`` to state the list of
    attributes that will be serialized into each request.
    """
    _atts = ()

    def __init__(self, **kwargs):
        for (key, value) in kwargs.items():
            setattr(self, key, value)

    def _as_serializable(self):
        data = {}
        for att in self._atts:
            if not hasattr(self, att):
                raise ValueError("Attempted to serialize attribute '%s'"
                    % att)
            data[att] = getattr(self, att)
        return data


class PistonAPI(object):
    """This class provides methods to make http requests slightly easier.

    It's a small wrapper around ``httplib2`` to allow for a bit of state to
    be stored (like the service root) so that you don't need to repeat
    yourself as much.
    It's not intended to be used directly.  Children classes should implement
    methods that actually call out to the api methods.

    When you define your API's methods you'll
    want to just call out to the ``_get``, ``_post``, ``_put`` methods
    provided by this class.
    """

    default_service_root = ''

    default_content_type = 'application/json'

    fail_handler = ExceptionFailHandler

    def __init__(self, service_root=None, cachedir=None, auth=None,
                 offline_mode=False):
        """Initialize a ``PistonAPI``.

        ``service_root`` is the url to the server's service root.
        Children classes can provide a ``default_service_root`` class
        attribute that will be used if ``service_root`` is ``None``.

        ``cachedir`` will be used as ``httplib2``'s cache directory if
        provided.

        ``auth`` can be an instance of ``BasicAuthorizer`` or
        ``OAuthAuthorizer`` or any object that provides a ``sign_request``
        method.  If ``auth`` is ``None`` you'll only be able to make public
        API calls.  See :ref:`authentication` for details.

        ``offline_mode`` will not touch the network
        """
        if service_root is None:
            service_root = self.default_service_root
        if not service_root:
            raise ValueError("No service_root provided, and no default found")
        parsed_service_root = urlparse(service_root)
        if parsed_service_root.scheme not in ['http', 'https']:
            raise ValueError("service_root's scheme must be http or https")
        self._service_root = service_root
        self._parsed_service_root = list(parsed_service_root)
        self._cachedir = cachedir
        self._auth = auth
        self._offline_mode = offline_mode

    def _get(self, path, args=None, scheme=None):
        """Perform an HTTP GET request.

        The provided ``path`` is appended to this resource's ``_service_root``
        attribute to obtain the absolute URL that will be requested.

        If provided, ``args`` should be a dict specifying additional GET
        arguments that will be encoded on to the end of the url.

        ``scheme`` must be one of *http* or *https*, and will determine the
        scheme used for this particular request.  If not provided the
        service_root's scheme will be used.
        """
        if args is not None:
            if '?' in path:
                path += '&'
            else:
                path += '?'
            path += urllib.urlencode(args)
        return self._request(path, method='GET', scheme=scheme)

    def _post(self, path, data=None, content_type=None, scheme=None):
        """Perform an HTTP POST request.

        The provided path is appended to this api's ``_service_root``
        attribute to obtain the absolute URL that will be requested.  Data
        should be:
         - A string, in which case it will be used directly as the request's
           body, or
         - A ``list``, ``dict``, ``int``, ``bool`` or ``PistonSerializable``
           (something with an ``_as_serializable`` method) or even ``None``,
           in which case it will be encoded into ``content_type`` using the
           right serializer from ``serializers``.

        If ``content_type`` is ``None``, ``self.default_content_type`` will
        be used.

        ``scheme`` must be one of *http* or *https*, and will determine the
        scheme used for this particular request.  If not provided the
        service_root's scheme will be used.
        """
        body, headers = self._prepare_request(path, data, content_type)
        return self._request(path, method='POST', body=body,
            headers=headers, scheme=scheme)


    def _delete(self, path, scheme=None):
        """Perform an HTTP DELETE request.

        The provided ``path`` is appended to this resource's ``_service_root``
        attribute to obtain the absolute URL that will be deleted.

        ``scheme`` must be one of *http* or *https*, and will determine the
        scheme used for this particular request.  If not provided the
        service_root's scheme will be used.
        """
        return self._request(path, method='DELETE', scheme=scheme)

    def _put(self, path, data=None, content_type=None, scheme=None):
        """Perform an HTTP PUT request.

        The provided path is appended to this api's ``_service_root``
        attribute to obtain the absolute URL that will be requested.  Data
        should be:
         - A string, in which case it will be used directly as the request's
           body, or
         - A ``list``, ``dict``, ``int``, ``bool`` or ``PistonSerializable``
           (something with an ``_as_serializable`` method) or even ``None``,
           in which case it will be encoded into ``content_type`` using the
           right serializer from ``serializers``.

        If ``content_type`` is ``None``, ``self.default_content_type`` will be
        used.

        ``scheme`` must be one of *http* or *https*, and will determine the
        scheme used for this particular request.  If not provided the
        service_root's scheme will be used.
        """
        body, headers = self._prepare_request(path, data, content_type)
        return self._request(path, method='PUT', body=body,
            headers=headers, scheme=scheme)

    def _prepare_request(self, path, data=None, content_type=None):
        """Parse data and return request body and headers."""
        body = data
        if content_type is None:
            content_type = self.default_content_type
        if not isinstance(data, basestring):
            # Import here to avoid a circular import
            from piston_mini_client.serializers import get_serializer
            serializer = get_serializer(content_type)
            body = serializer.serialize(data)
        headers = {
            'Content-type': content_type,
        }
        return (body, headers)

    def _request(self, path, method, body='', headers=None, scheme=None):
        """Perform an HTTP request.

        You probably want to call one of the ``_get``, ``_post``, ``_put``
        methods instead.
        """
        http = httplib2.Http(cache=self._cachedir)
        if headers is None:
            headers = {}
        if scheme not in [None, 'http', 'https']:
            raise ValueError('Invalid scheme %s' % scheme)
        url = self._path2url(path, scheme=scheme)
        
        # in offline mode either get it from the cache or return None
        if self._offline_mode:
            if method in ('POST', 'PUT'):
                err = "method '%s' not allowed in offline-mode" % method
                raise OfflineModeException(err)
            return self._get_from_cache(url)

        if self._auth:
            self._auth.sign_request(url, method, body, headers)
        try:
            response, body = http.request(url, method=method, body=body,
                headers=headers)
            
        except AttributeError, e:
            # Special case out httplib2's way of telling us unable to connect
            if e.args[0] == "'NoneType' object has no attribute 'makefile'":
                raise APIError('Unable to connect to %s' % self._service_root)
            else:
                raise
        handler = self.fail_handler(url, method, body, headers)
        body = handler.handle(response, body)
        return body

    def _get_from_cache(self, url):
        """ get a given url from the cachedir even if its expired
            or return None if no data is available
        """
        http = httplib2.Http(cache=self._cachedir)
        if http.cache:
            cached_value = http.cache.get(httplib2.urlnorm(url)[-1])
            if cached_value:
                info, content = cached_value.split('\r\n\r\n', 1)
                return content
        return None

    def _path2url(self, path, scheme=None):
        if scheme is None:
            service_root = self._service_root
        else:
            parts = [scheme] + self._parsed_service_root[1:]
            service_root = urlunparse(parts)
        return service_root.strip('/') + '/' + path.lstrip('/')

