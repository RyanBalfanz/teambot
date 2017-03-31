def directory_to_dict(directory):
    """
    >>> import shelve
    >>> directory = shelve.open('test')
    >>> directory['foo'] = ['bar']
    >>> directory_to_dict(directory)
    {'foo': ['bar']}
    """
    data = {}
    keys = directory.keys()
    for k, key in enumerate(keys):
        values = directory.get(key)
        data[key] = list(values)
    return data


class DirectorySerializer(object):
    """
    >>> import shelve
    >>> directory = shelve.open('test')
    >>> directory['foo'] = ['bar']
    >>> serializer = DirectorySerializer(directory)
    >>> serializer.data
    {'foo': ['bar']}
    """
    def __init__(self, directory):
        super(DirectorySerializer, self).__init__()
        self.directory = directory
        self._data = None

    @property
    def data(self):
        if self._data is None:
            self._data = directory_to_dict(self.directory)
        return self._data


class JSONRenderer(object):
    """
    >>> d = {'foo': ['bar']}
    >>> JSONRenderer().render(d)
    '{"foo": ["bar"]}'
    """
    def __init__(self, indent=None):
        super(JSONRenderer, self).__init__()
        self.indent = indent

    def render(self, data):
        import json
        return json.dumps(data, indent=self.indent)
