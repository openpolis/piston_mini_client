# -*- coding: utf-8 -*-
# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Lesser General Public License version 3 (see the file LICENSE).

"""Classes that define ways for your API methods to serialize arguments
into a request."""

__all__ = [
    'JSONSerializer',
    'FormSerializer',
]

import simplejson
import urllib

from piston_mini_client import PistonSerializable

class JSONSerializer(object):
    """A serializer that renders JSON.

    This is the default serializer for content type *application/json*.
    """
    class PistonSerializableEncoder(simplejson.JSONEncoder):
        def default(self, o):
            if isinstance(o, PistonSerializable):
                return o._as_serializable()
            return simplejson.JSONEncoder.default(self, o)

    def serialize(self, obj):
        """Serialize ``obj`` into JSON.

        As well as the usual basic JSON-encodable types, this serializer knows
        how to serialize ``PistonSerializable`` objects.
        """
        return simplejson.dumps(obj, cls=self.PistonSerializableEncoder)


class FormSerializer(object):
    """A serializer that renders form-urlencoded content.

    This is the default serializer for content type
    *application/x-www-form-urlencoded*.

    .. note:: this serializer doesn't support nested structures.

    It should be initialized with a dictionary, sequence of pairs, or
    ``PistonSerializable``.
    """
    def serialize(self, obj):
        if isinstance(obj, PistonSerializable):
            obj = obj._as_serializable()
        try:
            return urllib.urlencode(obj)
        except TypeError:
            raise TypeError("Attempted to serialize invalid object %s" % obj)


serializers = {
    'application/json': JSONSerializer(),
    'application/x-www-form-urlencoded': FormSerializer(),
}


def get_serializer(content_type):
    return serializers.get(content_type)
