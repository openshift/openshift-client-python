#!/usr/bin/env python

import openshift as oc

if __name__ == '__main__':
    with oc.tracking() as tracker:
        try:
            print('Current project: {}'.format(oc.get_project_name()))
            print('Current user: {}'.format(oc.whoami()))
        except:
            print('Error acquire details about project/user')

        # Print out details about the invocations made within this context.
        print tracker.get_result()
