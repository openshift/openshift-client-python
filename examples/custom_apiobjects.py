#!/usr/bin/env python

import openshift as oc
from openshift import APIObject


class MyCustomPodClass(APIObject):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def super_cool_awesomeness(self):
        print('Calling: super_cool_awesomeness() on pod: {}/{}'.format(self.model.metadata.namespace, self.model.metadata.name))


if __name__ == '__main__':
    with oc.client_host():
        with oc.project('openshift-monitoring'):

            objs = oc.selector('pods', labels={'app': 'prometheus'}).objects(cls=MyCustomPodClass)

            for obj in objs:
                print(type(obj))
                obj.super_cool_awesomeness()
