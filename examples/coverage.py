#!/usr/bin/python

from openshift import *

try:

    print "Projects created by users:", \
        oc.selector("projects").narrow(
            lambda project: project.metadata.annotations["openshift.io/requester"] is not Missing
        ).names()

    oc.selector("projects").narrow(
        # Eliminate any projects created by the system
        lambda project: project.metadata.annotations["openshift.io/requester"] is not Missing
    ).narrow(
        # Select from user projects any which violate privileged naming convention
        lambda project:
        project.metadata.name == "openshift" or
        project.metadata.name.startswith("openshift-") or
        project.metadata.name == "kubernetes" or
        project.metadata.name.startswith("kube-") or
        project.metadata.name.startswith("kubernetes-")
    ).for_each(
        lambda project: error("Invalid project: %s" % project.metadata.name)
    )

    with timeout(5):
        success, obj = oc.selector("pods").until_any(lambda pod: pod.status.phase == "Succeeded")
        if success:
            print "Found one pod was successful: " + str(obj)

    with timeout(5):
        success, obj = oc.selector("pods").narrow("pod").until_any(
            lambda pod: pod.status.conditions.can_match({"type": "Ready", "status": False, "reason": "PodCompleted"}))
        if success:
            print "Found one pod was successful: " + str(obj)



    with project("myproject"):

        oc.create_if_absent(
            {
                "apiVersion": "v1",
                "kind": "User",
                "fullName": "Jane Doe",
                "groups": null,
                "identities": [
                    "github:19783215"
                ],
                "metadata": {
                    "name": "jane"
                }
            }
        )

        oc.create_if_absent(
            {
                "apiVersion": "v1",
                "kind": "User",
                "fullName": "John Doe",
                "groups": null,
                "identities": [
                    "github:19783216"
                ],
                "metadata": {
                    "name": "john"
                }
            }
        )


        pods = oc.selector("pod")
        print "Pods: " + str(pods.names())

        users = oc.selector("user/john", "user/jane")

        print "Describing users:\n"
        users.describe()

        for user in users:
            print str(user)

        john = oc.selector("user/john")
        john.label({"mylabel": None})  # remove a label

        label_selector = oc.selector("users", labels={"mylabel": "myvalue"})

        print "users with label step 1: " + str(label_selector.names())

        john.label({"mylabel": "myvalue"})  # add the label back

        print "users with label step 2: " + str(label_selector.names())

        assert(label_selector.names()[0] == u'users/john')

        users.label({"another_label": "another_value"})

        john.patch({
                "groups": null,
                "identities": [
                    "github: 19783215"
                ]
            },
        )

        # Unmarshal json into py objects
        user_objs = users.objects()

        print "Unmarshalled %d objects" % len(user_objs)

        for user in user_objs:
            if user.metadata.labels.another_label is not Missing:
                print "Value of label: " + user.metadata.labels.another_label
            if user.notthere.dontcare.wontbreak is not Missing:
                print "Should see this, but also shouldn't see exception"

        oc.delete_if_present("user/bark", "user/bite")

        bark_obj = {
            "apiVersion": "v1",
            "kind": "User",
            "fullName": "Bark Doe",
            "groups": null,
            "identities": [
                "github:9999"
            ],
            "metadata": {
                "name": "bark"
            }
        }

        bite_obj = {
            "apiVersion": "v1",
            "kind": "User",
            "fullName": "Bite Doe",
            "groups": null,
            "identities": [
                "github:10000"
            ],
            "metadata": {
                "name": "bite"
            }
        }

        bark_bite_sel = oc.create([bark_obj, bite_obj])

        print "How were they created?\n" + str(bark_bite_sel)

        try:
            oc.create(bark_obj)  # Should create an error
            assert False
        except OpenShiftException as create_err:
            print "What went wrong?: " + str(create_err)

        bark_bite_sel.until_any(lambda obj: obj.metadata.name == "bite")



except OpenShiftException as e:
    print "An exception occurred: " + str(e)
