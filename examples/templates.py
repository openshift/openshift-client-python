#!/usr/bin/python

import openshift_client as oc

'''
This example will scan all the templates, on the cluster, and look specifically for the openshift/nginx-example
template.  If the template is located, it clears the namespace (to prevent an error when calling 'oc process'),
updates any template parameter(s), processes the template, and then creates the objects in the current namespace.
'''
if __name__ == '__main__':
    with oc.client_host():
        templates = oc.selector('templates', all_namespaces=True)

        for template in templates.objects():
            if template.model.metadata.namespace == 'openshift' and template.model.metadata.name == 'nginx-example':
                template.model.metadata.namespace = ''

                obj = oc.APIObject(dict_to_model=template.as_dict())

                parameters = {
                    'NAME': 'my-nginx',
                }

                processed_template = obj.process(parameters=parameters)
                obj_sel = oc.create(processed_template)

                for obj in obj_sel.objects():
                    print('Created: {}/{}'.format(obj.model.kind, obj.model.metadata.name))
                    print(obj.as_json(indent=4))
